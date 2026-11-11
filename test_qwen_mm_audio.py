import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import qwen_mm_audio as audio

CONFIG = {'DASHSCOPE_BASE_URL': 'http://127.0.0.1:3425/v1', 'DASHSCOPE_API_KEY': 'gateway-test-key'}


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='qwen-audio-test-', dir='/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'test.wav'
        self.path.write_bytes(b'RIFFaudio-fixture')

    def test_native_asr_uses_gateway_provider_and_documented_shape(self):
        with patch.object(audio, 'native', return_value={'output': {'text': 'hello'}}) as native:
            self.assertEqual(audio.transcribe_chunk(CONFIG, str(self.path), audio.ASR_MODEL, 'en', None), 'hello')
            args = native.call_args.args
            self.assertEqual(args[1], 'bailian-token-plan')
            self.assertEqual(args[3]['parameters'], {'format': 'wav', 'language_hints': ['en']})
            part = args[3]['input']['messages'][0]['content'][0]
            self.assertEqual(part['type'], 'input_audio')
            self.assertNotIn('gateway-test-key', json.dumps(args[3]))
        with self.assertRaisesRegex(ValueError, 'enable_itn'):
            audio.transcribe_chunk(CONFIG, str(self.path), audio.ASR_MODEL, None, False)

    def test_standard_asr_uses_multipart_and_qualified_model(self):
        with patch.object(audio, 'post', return_value=(b'{"text":"hello"}', 'application/json')) as post:
            result = audio.transcribe_chunk(CONFIG, str(self.path), 'mlx-audio-tools/local-asr', None, None)
            self.assertEqual(result, 'hello')
            self.assertEqual(post.call_args.args[1], '/audio/transcriptions')
            self.assertIn(b'mlx-audio-tools/local-asr', post.call_args.args[2])
            self.assertIn(self.path.read_bytes(), post.call_args.args[2])
            self.assertNotIn(b'gateway-test-key', post.call_args.args[2])

    def test_native_http_200_error_is_not_reported_as_success(self):
        with patch.object(audio, 'post', return_value=(b'{"code":"InvalidParameter","message":"bad input"}', 'application/json')):
            with self.assertRaisesRegex(ValueError, 'bad input'):
                audio.native(CONFIG, 'bailian-token-plan', '/test', {})

    def test_speech_download_has_no_gateway_auth(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'RIFFaudio'
        response.__enter__.return_value.headers = {'Content-Type': 'audio/wav'}
        with patch.object(audio, 'native', return_value={'output': {'audio': {'url': 'https://audio.example/out.wav'}}}), patch.object(audio, 'urlopen', return_value=response) as download:
            self.assertEqual(audio.synthesize(CONFIG, 'hello', audio.TTS_MODEL, 'longanhuan_v3.6', 'wav'), b'RIFFaudio')
            self.assertEqual(download.call_args.args, ('https://audio.example/out.wav',))
            self.assertEqual(download.call_args.kwargs, {'timeout': 60})
        with patch.object(audio, 'post', return_value=(b'{"error":"failed"}', 'application/json')):
            with self.assertRaisesRegex(ValueError, 'JSON'):
                audio.synthesize(CONFIG, 'hello', 'mlx-audio-tools/local-tts', 'default', 'wav')

    def test_speech_rejects_successful_http_error_pages(self):
        for content, content_type in [(b'<html>Error</html>', 'text/html'),
                                      (b'Provider unavailable', 'text/plain'),
                                      (b'["error"]', 'application/json')]:
            with self.subTest(content_type=content_type):
                with patch.object(audio, 'post', return_value=(content, content_type)):
                    with self.assertRaisesRegex(ValueError, 'instead of audio|non-audio'):
                        audio.synthesize(CONFIG, 'hello', 'mlx-audio-tools/local-tts', 'default', 'wav')
                response = MagicMock()
                response.__enter__.return_value.read.return_value = content
                response.__enter__.return_value.headers = {'Content-Type': content_type}
                with patch.object(audio, 'native', return_value={'output': {'audio': {'url': 'https://audio.example/out.wav'}}}), patch.object(audio, 'urlopen', return_value=response):
                    with self.assertRaisesRegex(ValueError, 'instead of audio|non-audio'):
                        audio.synthesize(CONFIG, 'hello', audio.TTS_MODEL, 'longanhuan_v3.6', 'wav')
        with patch.object(audio, 'post', return_value=(b'[raw PCM bytes', 'application/octet-stream')):
            self.assertEqual(audio.synthesize(CONFIG, 'hello', 'mlx-audio-tools/local-tts', 'default', 'pcm'), b'[raw PCM bytes')

    def test_registry_and_existing_file_protection(self):
        import qwen_mm_plugins_api as api
        from qwen_mm_plugins_api.others import asr
        originals = api.SPECS, api.get_handler, api.list_tools, asr.handle, asr.TOOL
        try:
            audio.install(lambda: CONFIG)
            audio.install(lambda: CONFIG)
            names = [tool['name'] for tool in api.list_tools()]
            self.assertEqual(names.count('transcribe_audio'), 1)
            self.assertEqual(names.count('synthesize_speech'), 1)
            with patch.object(audio, 'synthesize') as synthesize:
                output = api.get_handler('synthesize_speech')({'text': 'hello', 'output_path': str(self.path), 'voice': 'default'})
                self.assertIn('new absolute', str(output))
                synthesize.assert_not_called()
                self.assertEqual(self.path.read_bytes(), b'RIFFaudio-fixture')
        finally:
            api.SPECS, api.get_handler, api.list_tools, asr.handle, asr.TOOL = originals

    def test_reject_invalid_model_paths(self):
        for model in ['qwen3-asr-flash', '../model', '/model', 'provider/']:
            with self.assertRaises(ValueError):
                audio.split_model(model)


if __name__ == '__main__':
    unittest.main()
