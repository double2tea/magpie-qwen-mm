from functools import wraps
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import qwen_mm_plugins_search as package
from qwen_mm_plugins_search.tools import image_search, web_extractor, web_search

import qwen_mm_search as search


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.config = {'DASHSCOPE_BASE_URL': 'http://127.0.0.1:3425/v1',
                       'DASHSCOPE_API_KEY': 'agent-test-key'}
        self.original_search = web_search.handle
        self.original_extractor = web_extractor.handle
        self.addCleanup(setattr, web_search, 'handle', self.original_search)
        self.addCleanup(setattr, web_extractor, 'handle', self.original_extractor)
        for name in ('SPECS', 'get_handler', 'list_tools'):
            self.addCleanup(setattr, package, name, getattr(package, name))

    def test_install_refreshes_package_registry(self):
        old_handler = package.get_handler
        image_handler = image_search.handle
        search.install(lambda: self.config)
        self.assertIs(old_handler('web_search'), self.original_search)
        specs = {spec.name: spec for spec in package.SPECS}
        for name, handler in [('web_search', web_search.handle),
                              ('web_extractor', web_extractor.handle),
                              ('image_search', image_handler)]:
            self.assertIs(specs[name].handle, handler)
            self.assertIs(package.get_handler(name), handler)
        tools = {tool['name']: tool for tool in package.list_tools()}
        self.assertIn('queries', tools['web_search']['inputSchema']['properties'])
        self.assertIn('goal', tools['web_extractor']['inputSchema']['properties'])

    def test_search_preserves_magpie_citations_and_multiple_queries(self):
        search.install(lambda: self.config)
        results = ['Answer [web:1]\nSources: https://example.com/a',
                   'More [web:2]\nSources: https://example.com/b']
        with patch.object(search, '_call_magpie', return_value=results) as call:
            blocks = web_search.handle({'queries': ['first', 'second']})
        self.assertEqual(call.call_args.args[1], [('web_search', {'query': 'first', 'count': 10}),
                                                  ('web_search', {'query': 'second', 'count': 10})])
        self.assertEqual(blocks, [{'type': 'text', 'text': '## Query: first\n' + results[0] +
                                  '\n\n## Query: second\n' + results[1]}])
        self.assertNotIn('Serper', blocks[0]['text'])

    def test_extractor_preserves_url_goal_and_content(self):
        search.install(lambda: self.config)
        with patch.object(search, '_call_magpie', return_value=['# Page\n[link](https://example.com)']) as call:
            blocks = web_extractor.handle({'urls': ['https://example.com'], 'goal': 'Find details'})
        self.assertEqual(call.call_args.args[1], [('web_fetch', {'url': 'https://example.com', 'max_chars': 8000})])
        self.assertEqual(blocks[0]['text'], '## https://example.com\n(Goal: Find details)\n\n# Page\n[link](https://example.com)')

    def test_disconnect_restores_originals_and_reconnect_uses_magpie(self):
        original_search = unittest.mock.Mock(return_value=[{'type': 'text', 'text': 'native search'}])
        original_extract = unittest.mock.Mock(return_value=[{'type': 'text', 'text': 'native extract'}])

        @wraps(self.original_search, updated=())
        def native_search(arguments):
            return original_search(arguments)

        @wraps(self.original_extractor, updated=())
        def native_extract(arguments):
            return original_extract(arguments)

        web_search.handle = native_search
        web_extractor.handle = native_extract
        search.install(lambda: self.config)
        replacement_config = {}
        search.install(lambda: replacement_config)
        self.assertEqual(package.get_handler('web_search')({'queries': ['a'], 'api_key': 'native'})[0]['text'], 'native search')
        self.assertEqual(package.get_handler('web_extractor')({'urls': ['a'], 'goal': 'g'})[0]['text'], 'native extract')
        original_search.assert_called_once_with({'queries': ['a'], 'api_key': 'native'})
        original_extract.assert_called_once_with({'urls': ['a'], 'goal': 'g'})
        replacement_config.update(DASHSCOPE_BASE_URL='http://localhost:3425/v1', DASHSCOPE_API_KEY='key')
        with patch.object(search, '_call_magpie', return_value=['connected']) as call:
            self.assertEqual(package.get_handler('web_search')({'queries': ['a']})[0]['text'], 'connected')
        self.assertIs(call.call_args.args[0], replacement_config)

    def test_explicit_key_and_empty_inputs_are_rejected(self):
        search.install(lambda: self.config)
        with patch.object(search, '_call_magpie') as call:
            for handler, arguments in [(web_search.handle, {'queries': ['a'], 'api_key': 'other'}),
                                       (web_extractor.handle, {'urls': ['a'], 'goal': '', 'api_key': ''}),
                                       (web_search.handle, {'queries': []}),
                                       (web_extractor.handle, {'urls': [], 'goal': ''})]:
                self.assertTrue(handler(arguments)[0]['text'].startswith('Error:'))
            call.assert_not_called()

    def test_failure_does_not_fall_back_or_disclose_key(self):
        original = unittest.mock.Mock()

        @wraps(self.original_search, updated=())
        def native_search(arguments):
            return original(arguments)

        web_search.handle = native_search
        search.install(lambda: self.config)
        with patch.object(search, '_call_magpie', side_effect=ValueError('agent-test-key')):
            result = web_search.handle({'queries': ['a']})
        self.assertEqual(result[0]['text'], 'Error: Magpie Search request failed.')
        original.assert_not_called()

    def test_mcp_transport_initializes_session_and_sends_calls(self):
        requests = []
        replies = [({'result': {'protocolVersion': '2025-03-26'}}, {'Mcp-Session-Id': 'session'}),
                   (None, {}),
                   ({'result': {'content': [{'type': 'text', 'text': 'Answer [web:1] https://example.com'}]}}, {})]

        def urlopen(request, timeout):
            requests.append((request, timeout))
            payload, headers = replies.pop(0)
            response = io.BytesIO(json.dumps(payload).encode() if payload is not None else b'')
            response.headers = headers
            return response

        with patch.object(search, 'urlopen', side_effect=urlopen):
            result = search._call_magpie(self.config, [('web_search', {'query': 'hello'})])
        self.assertEqual(result, ['Answer [web:1] https://example.com'])
        self.assertEqual([json.loads(req.data)['method'] for req, _ in requests],
                         ['initialize', 'notifications/initialized', 'tools/call'])
        self.assertTrue(all(req.full_url == 'http://127.0.0.1:3425/mcp/magpie/web-search' for req, _ in requests))
        self.assertEqual(requests[0][0].get_header('Authorization'), 'Bearer agent-test-key')
        self.assertEqual(requests[2][0].get_header('Mcp-session-id'), 'session')
        self.assertEqual(json.loads(requests[2][0].data)['params'],
                         {'name': 'web_search', 'arguments': {'query': 'hello'}})

    def test_transport_error_is_reported_without_retry(self):
        search.install(lambda: self.config)
        error = HTTPError('http://localhost', 403, 'denied', {}, None)
        with patch.object(search, 'urlopen', side_effect=error) as call:
            result = web_search.handle({'queries': ['a']})
        self.assertEqual(result[0]['text'], 'Error: Magpie Search request failed.')
        call.assert_called_once()


if __name__ == '__main__':
    unittest.main()
