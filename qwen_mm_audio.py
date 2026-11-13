"""Route Qwen API speech tools through the configured Magpie gateway."""
from __future__ import annotations

import base64
import json
import math
from pathlib import Path
import re
import struct
import tempfile
from types import SimpleNamespace
from typing import Literal
from urllib.request import Request, urlopen
from uuid import uuid4

ASR_MODEL = 'bailian-token-plan/qwen-audio-3.0-asr-flash'
TTS_MODEL = 'bailian-token-plan/qwen-audio-3.0-tts-plus'


def split_model(model):
    provider, separator, name = model.partition('/')
    if not separator or not re.fullmatch(r'[a-zA-Z0-9_-]+', provider) or not name:
        raise ValueError('Choose a Magpie model as provider/model')
    return provider, name


def post(config, path, body, content_type='application/json'):
    if isinstance(body, dict):
        body = json.dumps(body).encode()
    request = Request(config['DASHSCOPE_BASE_URL'].rstrip('/') + path, data=body,
                      headers={'Authorization': 'Bearer ' + config['DASHSCOPE_API_KEY'],
                               'Content-Type': content_type})
    with urlopen(request, timeout=90) as response:
        return response.read(), response.headers.get('Content-Type', '')


def native(config, provider, path, body):
    content, _ = post(config, '/magpie/native/' + provider + path, body)
    result = json.loads(content)
    if result.get('code') and result['code'] not in ('Success', '200'):
        raise ValueError(str(result.get('message') or result['code']))
    return result


def transcribe_chunk(config, path, model, language, enable_itn):
    provider, name = split_model(model)
    if provider in ('bailian-token-plan', 'qwen-cn'):
        data = 'data:audio/wav;base64,' + base64.b64encode(Path(path).read_bytes()).decode()
        if name.startswith('qwen-audio-'):
            if enable_itn is not None:
                raise ValueError('This Qwen Audio endpoint does not expose enable_itn; omit it')
            parameters = {'format': 'wav'}
            if language:
                parameters['language_hints'] = [language]
            content = [{'type': 'input_audio', 'input_audio': {'data': data}}]
        else:
            parameters = {'asr_options': {'enable_itn': True if enable_itn is None else enable_itn}}
            if language:
                parameters['asr_options']['language'] = language
            content = [{'audio': data}]
        result = native(config, provider, '/api/v1/services/aigc/multimodal-generation/generation',
                        {'model': name, 'input': {'messages': [{'role': 'user', 'content': content}]},
                         'parameters': parameters})
        output = result.get('output') or {}
        if name.startswith('qwen-audio-'):
            return output.get('text', '')
        return '\n'.join(part.get('text', '') for choice in output.get('choices', [])
                         for part in choice.get('message', {}).get('content', []))
    if enable_itn is not None:
        raise ValueError('OpenAI-compatible transcription does not expose enable_itn; omit it')
    boundary = 'qwen-mm-' + uuid4().hex
    body = bytearray()
    fields = {'model': model, 'response_format': 'json'}
    if language:
        fields['language'] = language
    for key, value in fields.items():
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode())
    body.extend(Path(path).read_bytes())
    body.extend(f'\r\n--{boundary}--\r\n'.encode())
    content, _ = post(config, '/audio/transcriptions', bytes(body), 'multipart/form-data; boundary=' + boundary)
    return json.loads(content)['text']


def finalize_wav(data):
    # Bailian TTS leaves streaming placeholder lengths in the finite OSS WAV.
    if (len(data) >= 44 and data[:4] == b'RIFF' and data[8:12] == b'WAVE'
            and data[12:20] == b'fmt \x10\x00\x00\x00' and data[20:22] == b'\x01\x00'
            and data[36:40] == b'data'
            and struct.unpack_from('<I', data, 4)[0] == 0x7FFFFFBF
            and struct.unpack_from('<I', data, 40)[0] == 0x7FFFFF9B):
        actual = len(data) - 44
        alignment = struct.unpack_from('<H', data, 32)[0]
        if not actual or not alignment or actual % alignment:
            raise ValueError('Speech provider returned an incomplete PCM frame in WAV audio')
        return data[:4] + struct.pack('<I', len(data) - 8) + data[8:40] + struct.pack('<I', actual) + data[44:]
    return data


def synthesize(config, text, model, voice, format):
    provider, name = split_model(model)
    if provider in ('bailian-token-plan', 'qwen-cn'):
        result = native(config, provider, '/api/v1/services/audio/tts/SpeechSynthesizer',
                        {'model': name, 'input': {'text': text, 'voice': voice, 'format': format}})
        audio = result.get('output', {}).get('audio', {})
        url = audio.get('url')
        if not url:
            raise ValueError('Speech provider returned no audio URL')
        # Download the generated artifact without forwarding the gateway credential.
        with urlopen(url, timeout=60) as response:
            data = response.read()
            content_type = response.headers.get('Content-Type', '')
    else:
        data, content_type = post(config, '/audio/speech', {'model': model, 'input': text, 'voice': voice,
                                                         'response_format': format})
    if not data:
        raise ValueError('Speech provider returned empty audio')
    media_type = content_type.partition(';')[0].strip().lower()
    if 'json' in media_type or (format != 'pcm' and data.lstrip().startswith((b'{', b'['))):
        raise ValueError('Speech provider returned JSON instead of audio')
    if not (media_type.startswith('audio/') or media_type in ('application/octet-stream', 'binary/octet-stream')):
        raise ValueError('Speech provider returned non-audio content: ' + (media_type or 'missing Content-Type'))
    return finalize_wav(data) if format == 'wav' and provider in ('bailian-token-plan', 'qwen-cn') else data


def install(settings):
    from pydantic import BaseModel
    from shared.content import text_error
    import qwen_mm_plugins_api as api
    from qwen_mm_plugins_api.others import asr
    from mcp_framework import _spec_from_module

    original = getattr(asr.handle, '_magpie_original', asr.handle)

    class TranscribeArgs(asr.TranscribeAudioArgs):
        model: str = ASR_MODEL
        enable_itn: bool | None = None

    class SpeechArgs(BaseModel):
        text: str
        output_path: str
        voice: str
        model: str = TTS_MODEL
        format: Literal['wav', 'mp3', 'pcm'] = 'wav'

    def transcribe(arguments):
        """Transcribe local audio/video through Magpie. Choose provider/model; the default uses
        Bailian Token Plan. language is a language code such as zh or en. SRT timestamps retain
        the upstream tool's coarse 60-second chunk boundaries. Provider keys stay in Magpie.
        Explicit enable_itn is supported only for legacy Qwen3-ASR models.

        Args:
            file_path: Existing local audio or video file.
            model: Magpie provider/model identifier; defaults to Bailian Token Plan ASR.
            start_time: Start offset in seconds, default zero.
            end_time: End offset in seconds, default full duration.
            format: Output format: srt, text, or json.
            language: Language code such as zh or en; omit for detection.
            enable_itn: Optional normalization flag for legacy Qwen3-ASR only.
            api_key: Omit when connected; provider credentials are managed by Magpie.
        """
        config = settings()
        if not config:
            local = dict(arguments)
            if local.get('model') in (None, ASR_MODEL):
                local.pop('model', None)
            if local.get('enable_itn') is None:
                local.pop('enable_itn', None)
            return original(local)
        try:
            if arguments.get('api_key'):
                raise ValueError('Manage speech provider credentials in Magpie; omit api_key')
            path = Path(arguments['file_path']).expanduser()
            if not path.is_file():
                raise ValueError('file_path must be an existing local audio/video file')
            model = arguments.get('model') or ASR_MODEL
            split_model(model)
            duration = asr._get_duration(str(path))
            start = arguments.get('start_time') or 0.0
            end = arguments.get('end_time')
            end = duration if end is None else end
            if not 0 <= start < end <= duration:
                raise ValueError('Require 0 <= start_time < end_time <= media duration')
            chunks = []
            with tempfile.TemporaryDirectory(prefix='qwen-mm-asr-', dir='/tmp') as temporary:
                for index in range(math.ceil((end - start) / asr.MAX_CHUNK_SECONDS)):
                    begin = start + index * asr.MAX_CHUNK_SECONDS
                    finish = min(begin + asr.MAX_CHUNK_SECONDS, end)
                    wav = str(Path(temporary) / f'{index}.wav')
                    asr._extract_audio(str(path), wav, start_time=begin, duration=finish - begin)
                    text = transcribe_chunk(config, wav, model, arguments.get('language'), arguments.get('enable_itn'))
                    chunks.append((begin, finish, [text] if text else []))
            format = arguments.get('format', 'srt')
            if format == 'srt':
                result = asr._format_srt(chunks)
            elif format == 'text':
                result = asr._format_text(chunks)
            elif format == 'json':
                result = json.dumps([{'start': begin, 'end': end, 'text': ' '.join(text)}
                                     for begin, end, text in chunks], ensure_ascii=False, indent=2)
            else:
                raise ValueError('format must be srt, text or json')
            return [{'type': 'text', 'text': result or 'Transcription completed but no speech detected.'}]
        except Exception as error:
            return text_error(str(error))

    def speech(arguments):
        """Generate speech through Magpie and save an audio artifact. output_path must be a new
        absolute file path. voice is required; Bailian Token Plan supports longanhuan_v3.6.
        Choose provider/model. Compatible providers use /audio/speech; Bailian uses Magpie's
        native API relay. Billing follows the selected provider; no provider key is accepted.

        Args:
            text: Text to speak.
            output_path: New absolute audio file path in an existing directory.
            voice: Provider voice identifier; Token Plan supports longanhuan_v3.6.
            model: Magpie provider/model identifier; defaults to Bailian Token Plan TTS.
            format: Output audio format: wav, mp3, or pcm.
        """
        try:
            config = settings()
            if not config:
                raise ValueError('Connect Qwen MM to Magpie before synthesizing speech')
            path = Path(arguments['output_path']).expanduser()
            if not path.is_absolute() or path.exists():
                raise ValueError('output_path must be a new absolute file path')
            if not arguments['text'].strip() or not arguments['voice'].strip():
                raise ValueError('text and voice must be nonempty')
            format = arguments.get('format', 'wav')
            if format not in ('wav', 'mp3', 'pcm'):
                raise ValueError('format must be wav, mp3 or pcm')
            if not path.parent.is_dir():
                raise ValueError('The output directory must already exist')
            data = synthesize(config, arguments['text'], arguments.get('model') or TTS_MODEL,
                              arguments['voice'], format)
            with path.open('xb') as output:
                output.write(data)
            return [{'type': 'text', 'text': json.dumps({'path': str(path), 'bytes': len(data),
                                                        'model': arguments.get('model') or TTS_MODEL})}]
        except Exception as error:
            return text_error(str(error))

    transcribe._magpie_original = original
    asr.handle = transcribe
    asr.TOOL = {'name': 'transcribe_audio', 'args': TranscribeArgs}
    speech_module = SimpleNamespace(TOOL={'name': 'synthesize_speech', 'args': SpeechArgs}, handle=speech)
    api.SPECS = [_spec_from_module(asr) if spec.name == 'transcribe_audio' else spec
                 for spec in api.SPECS if spec.name != 'synthesize_speech']
    api.SPECS.append(_spec_from_module(speech_module))
    handlers = {spec.name: spec.handle for spec in api.SPECS}
    api.get_handler = handlers.get
    api.list_tools = lambda: [spec.meta for spec in api.SPECS]
