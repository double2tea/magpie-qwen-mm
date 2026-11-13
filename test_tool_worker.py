import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import tool_worker as worker


class NativeWorkerTests(unittest.TestCase):
    def test_packaged_upstream_schemas_match_pinned_registry(self):
        manifest = json.loads(Path(worker.__file__).with_name('tools.json').read_text())
        import qwen_mm_plugins_video_spatio as video
        import qwen_mm_plugins_search as search
        from qwen_mm_audio import install
        import qwen_mm_plugins_api as api
        from qwen_mm_gateway import settings
        install(settings)
        for entry, module in [('video-spatio', video), ('search', search), ('audio', api)]:
            actual = {spec['name']: spec for spec in module.list_tools() if entry != 'audio' or spec['name'] in ('transcribe_audio', 'synthesize_speech')}
            packaged = {spec['name']: {k: v for k, v in spec.items() if k != 'entry'} for spec in manifest if spec['entry'] == entry}
            self.assertEqual(packaged, actual)

    def test_geometry_reaches_real_handler(self):
        result = worker.execute('video-spatio', 'select_keyframes', {'strategy': 'uniform', 'n': 3, 'total_frames': 9})
        self.assertEqual(json.loads(result[0]['text'])['frames'], [0, 4, 8])

    def test_upstream_text_error_is_failure(self):
        with self.assertRaises(ValueError):
            worker.execute('video-spatio', 'select_keyframes', {'strategy': 'uniform'})

    def test_worker_rejects_unregistered_tools_before_execution(self):
        with patch.object(worker.sys, 'stdin', io.StringIO(json.dumps({'entry': 'search', 'name': 'not_registered', 'arguments': {}}))), patch.object(worker, 'execute') as execute:
            with self.assertRaisesRegex(ValueError, 'manifest'):
                worker.main()
            execute.assert_not_called()

    def test_loopback_client_ignores_bad_proxy_environment_and_is_closed(self):
        import os
        import openai
        original = openai.OpenAI
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://proxy.invalid:not-a-port', 'HTTPS_PROXY': 'http://proxy.invalid:not-a-port'}):
            with worker.local_gateway_clients():
                client = openai.OpenAI(base_url='http://127.0.0.1:3425/v1', api_key='fixture')
                self.assertFalse(client.is_closed())
            self.assertTrue(client.is_closed())
        self.assertIs(openai.OpenAI, original)

    def test_external_clients_keep_proxy_and_user_client_policy(self):
        import openai
        supplied = object()
        with patch.object(openai, 'OpenAI') as constructor:
            with worker.local_gateway_clients():
                openai.OpenAI(base_url='https://provider.example/v1', api_key='fixture')
                self.assertNotIn('http_client', constructor.call_args.kwargs)
                openai.OpenAI(base_url='http://127.0.0.1:3425/v1', api_key='fixture', http_client=supplied)
                self.assertIs(constructor.call_args.kwargs['http_client'], supplied)

    def test_swallowed_visual_request_error_cannot_be_a_success(self):
        from shared import api_openai
        import qwen_mm_plugins_video_spatio as video
        def handler(arguments):
            try:
                api_openai.call_openai_chat()
            except RuntimeError:
                return [{'type': 'text', 'text': '{"verified": false, "vlm_answer": "vlm unavailable"}'}]
        with patch.object(worker, 'install'), patch.object(video, 'get_handler', return_value=handler), patch.object(api_openai, 'call_openai_chat', side_effect=RuntimeError('private upstream detail')):
            with self.assertRaises(worker.ModelRequestError) as result:
                worker.execute('video-spatio', 'verify_grounding', {})
        self.assertNotIn('private upstream detail', str(result.exception))

    def test_nonfinite_results_do_not_emit_invalid_json(self):
        output = io.StringIO()
        with patch.object(worker.sys, 'stdin', io.StringIO(json.dumps({'entry': 'search', 'name': 'web_search', 'arguments': {}}))), patch.object(worker, 'execute', return_value={'invalid': float('nan')}), contextlib.redirect_stdout(output):
            with self.assertRaises(ValueError):
                worker.main()
        self.assertEqual(output.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
