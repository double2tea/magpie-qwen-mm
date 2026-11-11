import base64
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

import qwen_mm_gateway as gateway


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='qwen-mm-test-', dir='/tmp')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'gateway'
        self.config.write_text('DASHSCOPE_BASE_URL=https://gateway.example/v1\n'
                               'DASHSCOPE_API_KEY=gateway-test-key\n'
                               'QWEN_MM_API_VL_MODEL=google/gemini-vl\n'
                               'QWEN_MM_API_OMNI_MODEL=google/gemini-omni\n')
        self.config_patch = patch.object(gateway, 'CONFIG', self.config)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)

    def test_endpoint_precedence_and_native_config(self):
        from shared import env
        native = self.root / 'native'
        native.write_text('DASHSCOPE_API_KEY=native-test-key\n')
        with patch.dict(os.environ, {'QWEN_MM_CONFIG': str(native)}, clear=True):
            self.assertEqual(env.get_env('DASHSCOPE_API_KEY'), 'native-test-key')
            original = lambda args: (args.get('base_url', 'https://native.example/v1'),
                                     args.get('api_key', 'native-test-key'))
            self.assertEqual(gateway.endpoint({}, original), ('https://gateway.example/v1', 'gateway-test-key'))
            self.assertEqual(gateway.endpoint({'api_key': 'explicit'}, original)[1], 'explicit')
            self.assertEqual(gateway.endpoint({'base_url': 'https://gateway.example/other'}, original)[1], 'gateway-test-key')
            self.assertEqual(gateway.endpoint({'base_url': 'https://elsewhere.example/v1'}, original)[1], 'native-test-key')
            self.assertEqual(gateway.endpoint({'base_url': 'https://elsewhere.example/v1', 'api_key': 'explicit'}, original)[1], 'explicit')
            self.assertEqual(gateway.endpoint({'base_url': 'https://elsewhere.example/v1'},
                                              lambda args: (args['base_url'], 'gateway-test-key'))[1], 'EMPTY')
            self.assertEqual(env.get_env('DASHSCOPE_API_KEY'), 'native-test-key')
            self.assertEqual(os.environ['QWEN_MM_CONFIG'], str(native))

    def test_model_resolution_and_gemini_only(self):
        from shared import api_openai, api_omni
        seen = []
        names = [(api_openai, 'resolve_openai_endpoint'), (api_openai, 'resolve_vl_model'),
                 (api_openai, 'call_openai_chat'), (api_omni, 'resolve_openai_endpoint'),
                 (api_omni, 'resolve_omni_model'), (api_omni, 'call_omni')]
        originals = [(module, name, getattr(module, name)) for module, name in names]
        self.addCleanup(lambda: [setattr(module, name, value) for module, name, value in originals])
        api_openai.call_openai_chat = lambda **kwargs: seen.append(kwargs)
        api_omni.call_omni = lambda **kwargs: seen.append(kwargs)
        gateway.install()
        self.assertEqual(api_openai.resolve_vl_model(), 'google/gemini-vl')
        self.assertEqual(api_omni.resolve_omni_model(), 'google/gemini-omni')
        self.assertEqual(api_openai.resolve_vl_model('explicit-vl'), 'explicit-vl')
        self.assertEqual(api_omni.resolve_omni_model('explicit-omni'), 'explicit-omni')
        messages = [{'role': 'user', 'content': [{'type': 'input_audio', 'input_audio': {'data': 'dGVzdA==', 'format': 'wav'}}]}]
        api_omni.call_omni(model='qwen-omni', messages=messages)
        self.assertEqual(seen[-1]['messages'], messages)
        api_omni.call_omni(model='google/gemini-test', messages=messages)
        self.assertEqual(seen[-1]['messages'][0]['content'][0]['file']['file_data'], 'data:audio/wav;base64,dGVzdA==')
        api_openai.call_openai_chat(model='google/gemini-test', messages=messages)
        self.assertEqual(seen[-1]['messages'][0]['content'][0]['type'], 'file')
        self.assertEqual(messages[0]['content'][0]['type'], 'input_audio')

    def test_disconnect_uses_native_models_and_endpoint(self):
        self.config.write_text('QWEN_MM_API_VL_MODEL=google/gemini-vl\n'
                               'QWEN_MM_API_OMNI_MODEL=google/gemini-omni\n')
        self.assertEqual(gateway.settings(), {})
        original = lambda args: ('https://native.example/v1', 'native-test-key')
        self.assertEqual(gateway.endpoint({}, original), original({}))

    def test_agy_visual_channel_rejects_audio_explicitly(self):
        image = {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,aGVsbG8='}}
        visual = [{'role': 'user', 'content': [image]}]
        self.assertEqual(gateway.adapt_for_model(visual, 'agy-cli/gemini-3.8-flash'), visual)
        audio = [{'role': 'user', 'content': [{'type': 'input_audio', 'input_audio': {
            'data': 'data:audio/wav;base64,aGVsbG8=', 'format': 'wav'}}]}]
        with self.assertRaisesRegex(ValueError, 'agy-cli.*音频'):
            gateway.adapt_for_model(audio, 'agy-cli/gemini-3.8-flash')
        self.assertEqual(gateway.adapt_for_model(audio, 'google/gemini-3.8-flash')[0]['content'][0]['type'], 'file')
        self.assertIs(gateway.adapt_for_model(audio, 'qwen-cn/qwen3.8-omni-flash'), audio)

    def test_audio_and_image(self):
        raw = base64.b64encode(b'test audio').decode()
        for data in (raw, 'data:;base64,' + raw, 'data:audio/wav;base64,' + raw):
            part = gateway.audio_file({'input_audio': {'data': data, 'format': 'wav'}})
            self.assertEqual(part['file']['file_data'], 'data:audio/wav;base64,' + raw)
        image = {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,YQ=='}}
        self.assertEqual(gateway.adapt_parts([image]), [image])
        frames = gateway.adapt_parts([{'type': 'video', 'video': ['data:image/jpeg;base64,YQ=='], 'fps': 2}])
        self.assertIn('2 fps', frames[0]['text'])
        self.assertEqual(frames[1], image)
        self.assertEqual(gateway.audio_file({'input_audio': {'data': raw, 'format': 'mp3'}})['file']['file_data'],
                         'data:audio/mpeg;base64,' + raw)

    def make_video(self, name, audio):
        path = self.root / name
        command = ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=red:s=128x128:r=4:d=2']
        if audio:
            command += ['-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-c:a', 'aac', '-shortest']
        command += ['-c:v', 'mpeg4', '-y', str(path)]
        subprocess.run(command, check=True, capture_output=True)
        return path

    def test_real_video_with_and_without_audio(self):
        for audio in (False, True):
            path = self.make_video(f'{audio}.mp4', audio)
            data = base64.b64encode(path.read_bytes()).decode()
            parts = gateway.adapt_parts([{'type': 'video_url', 'video_url': {'url': 'data:video/mp4;base64,' + data}, 'fps': 1}])
            types = [part['type'] for part in parts]
            self.assertGreaterEqual(types.count('image_url'), 2)
            self.assertIn('text', types)
            self.assertEqual('file' in types, audio)
            if audio:
                self.assertTrue(next(p for p in parts if p['type'] == 'file')['file']['file_data'].startswith('data:audio/mpeg;base64,'))

    def test_http_media(self):
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

        self.make_video('clip.mp4', True)
        audio = self.root / 'audio.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=1', '-y', str(audio)],
                       check=True, capture_output=True)
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(self.root)))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}'
            parts = gateway.adapt_parts([{'type': 'video_url', 'video_url': {'url': url + '/clip.mp4'}}])
            self.assertIn('image_url', [part['type'] for part in parts])
            self.assertIn('file', [part['type'] for part in parts])
            part = gateway.audio_file({'input_audio': {'data': url + '/audio.wav', 'format': 'wav'}})
            self.assertEqual(base64.b64decode(part['file']['file_data'].split(',', 1)[1]), audio.read_bytes())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_pure_audio_from_upstream(self):
        from shared.api_omni import omni_audio_part
        path = self.root / 'audio.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-y', str(path)],
                       check=True, capture_output=True)
        result = gateway.adapt_parts([omni_audio_part(str(path))])
        self.assertTrue(result[0]['file']['file_data'].startswith('data:audio/wav;base64,'))


if __name__ == '__main__':
    unittest.main()
