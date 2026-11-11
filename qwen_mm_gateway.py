"""Launch the upstream Qwen MM servers with Magpie's compatible API settings."""

from __future__ import annotations

import base64
import importlib
import json
import mimetypes
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import urlopen

CONFIG = Path('~/.config/magpie/qwen-mm/config').expanduser()


def settings():
    from shared.env import _parse_config

    config = _parse_config(CONFIG.read_text()) if CONFIG.is_file() else {}
    # Magpie disconnect removes the connection keys but keeps the saved model choices.
    return config if config.get('DASHSCOPE_BASE_URL') and config.get('DASHSCOPE_API_KEY') else {}


def origin(url):
    parsed = urlsplit(url)
    port = parsed.port or {'http': 80, 'https': 443}.get(parsed.scheme.lower())
    return parsed.scheme.lower(), (parsed.hostname or '').lower(), port


def endpoint(arguments, original):
    config = settings()
    configured = config.get('DASHSCOPE_BASE_URL')
    explicit = arguments.get('base_url')
    if not configured:
        return original(arguments)
    if explicit and origin(explicit) != origin(configured):
        url, key = original(arguments)
        if not arguments.get('api_key') and key == config.get('DASHSCOPE_API_KEY'):
            key = 'EMPTY'
        return url, key
    return explicit or configured, arguments.get('api_key') or config.get('DASHSCOPE_API_KEY') or 'EMPTY'


def audio_file(part):
    audio = part['input_audio']
    data = audio['data']
    fmt = audio.get('format', 'wav').lower().lstrip('.')
    mime = 'audio/wav' if fmt in ('wav', 'wave') else mimetypes.guess_type('audio.' + fmt)[0] or 'application/octet-stream'
    if data.startswith(('http://', 'https://')):
        with urlopen(data) as response:
            data = base64.b64encode(response.read()).decode('ascii')
    elif data.startswith('data:'):
        header, data = data.split(',', 1)
        if not header.endswith(';base64'):
            raise ValueError('Audio data URL must be base64 encoded')
        declared = header[5:-7]
        if declared:
            mime = declared
    return {'type': 'file', 'file': {'filename': 'audio.' + fmt, 'file_data': f'data:{mime};base64,{data}'}}


def video_parts(part):
    from shared import omni_media

    source = part['video_url']['url']
    with tempfile.TemporaryDirectory(prefix='qwen-mm-gateway-', dir='/tmp') as directory:
        if source.startswith('data:'):
            header, data = source.split(',', 1)
            if not header.endswith(';base64'):
                raise ValueError('Video data URL must be base64 encoded')
            path = Path(directory) / 'video'
            path.write_bytes(base64.b64decode(data, validate=True))
            source = str(path)
        cleanup = []
        try:
            parts = omni_media.frames_and_audio_parts(
                source, part.get('fps', 1.0), part.get('max_pixels', 200704), cleanup
            )
            return adapt_parts(parts)
        finally:
            omni_media.cleanup_files(cleanup)


def adapt_parts(parts):
    result = []
    for part in parts:
        kind = part.get('type')
        if kind == 'input_audio':
            result.append(audio_file(part))
        elif kind == 'video_url':
            result.extend(video_parts(part))
        elif kind == 'video' and isinstance(part.get('video'), list):
            if part.get('fps'):
                result.append({'type': 'text', 'text': f"Video frames in chronological order at {part['fps']} fps:"})
            result.extend({'type': 'image_url', 'image_url': {'url': frame}} for frame in part['video'])
        else:
            result.append(part)
    return result


def adapt_messages(messages):
    return [{**message, 'content': adapt_parts(message['content'])}
            if isinstance(message.get('content'), list) else message for message in messages]


def adapt_for_model(messages, model):
    if model.startswith(('google/gemini-', 'agy-cli/gemini-')):
        messages = adapt_messages(messages)
    if model.startswith('agy-cli/gemini-'):
        for message in messages:
            content = message.get('content')
            if isinstance(content, list) and any(
                part.get('type') == 'file' and part.get('file', {}).get('file_data', '').startswith('data:audio/')
                for part in content
            ):
                raise ValueError('agy-cli Gemini 当前渠道不支持音频输入；请选择 Gemini Native 或 Qwen Omni。')
    return messages


def install():
    from shared import api_openai, api_omni

    original_endpoint = api_openai.resolve_openai_endpoint
    original_vl = api_openai.resolve_vl_model
    original_omni = api_omni.resolve_omni_model
    original_chat = api_openai.call_openai_chat
    original_call_omni = api_omni.call_omni

    def resolve_endpoint(arguments):
        return endpoint(arguments, original_endpoint)

    def resolve_vl(model=None):
        return model or settings().get('QWEN_MM_API_VL_MODEL') or original_vl(model)

    def resolve_omni(model=None):
        return model or settings().get('QWEN_MM_API_OMNI_MODEL') or original_omni(model)

    def chat(**kwargs):
        kwargs['messages'] = adapt_for_model(kwargs['messages'], kwargs.get('model') or '')
        return original_chat(**kwargs)

    def omni(**kwargs):
        model = resolve_omni(kwargs.get('model'))
        kwargs['messages'] = adapt_for_model(kwargs['messages'], model)
        return original_call_omni(**kwargs)

    api_openai.resolve_openai_endpoint = resolve_endpoint
    api_openai.resolve_vl_model = resolve_vl
    api_openai.call_openai_chat = chat
    api_omni.resolve_openai_endpoint = resolve_endpoint
    api_omni.resolve_omni_model = resolve_omni
    api_omni.call_omni = omni
    from qwen_mm_audio import install as install_audio
    from qwen_mm_search import install as install_search
    install_audio(settings)
    install_search(settings)


def main():
    entries = {'video-spatio': 'qwen_mm_plugins_video_spatio',
               'api': 'qwen_mm_plugins_api', 'core': 'qwen_mm_plugins_core',
               'search': 'qwen_mm_plugins_search', 'audio': 'qwen_mm_magpie_audio'}
    if len(sys.argv) < 2 or sys.argv[1] not in entries:
        raise SystemExit('Usage: python qwen_mm_gateway.py {video-spatio|api|core|search|audio} [args...]')
    entry = entries[sys.argv.pop(1)]
    install()
    if entry == 'qwen_mm_magpie_audio':
        from types import ModuleType
        from mcp_framework import run_main
        import qwen_mm_plugins_api as api
        module = ModuleType(entry)
        module.__version__ = json.loads(Path(__file__).with_name('package.json').read_text())['version']
        module.SPECS = [spec for spec in api.SPECS if spec.name in ('transcribe_audio', 'synthesize_speech')]
        module.USAGE_NOTE = 'Speech via Magpie. Provider/model selects the channel; provider credentials stay in Magpie.'
        sys.modules[entry] = module
        run_main(entry)
    else:
        importlib.import_module(entry + '.__main__').main()


if __name__ == '__main__':
    main()
