"""Route Qwen MM text search and extraction through Magpie when connected."""

from __future__ import annotations

from functools import wraps
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


def _call_magpie(config, calls):
    base = urlsplit(config['DASHSCOPE_BASE_URL'])
    if base.scheme not in ('http', 'https') or not base.netloc:
        raise ValueError('Invalid Magpie gateway URL')
    url = urlunsplit((base.scheme, base.netloc, '/mcp/magpie/web-search', '', ''))
    headers = {
        'Authorization': 'Bearer ' + config['DASHSCOPE_API_KEY'],
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
    }

    def send(body):
        request = Request(url, data=json.dumps(body).encode(), headers=headers)
        with urlopen(request, timeout=60) as response:
            session = response.headers.get('Mcp-Session-Id')
            if session:
                headers['Mcp-Session-Id'] = session
            payload = response.read()
        if not payload:
            return None
        result = json.loads(payload)
        if 'error' in result:
            raise ValueError('Magpie MCP request failed')
        return result['result']

    send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
        'protocolVersion': '2025-03-26', 'capabilities': {},
        'clientInfo': {'name': 'qwen-mm-search', 'version': '1'},
    }})
    send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    results = []
    for index, (name, arguments) in enumerate(calls, 2):
        result = send({'jsonrpc': '2.0', 'id': index, 'method': 'tools/call',
                       'params': {'name': name, 'arguments': arguments}})
        if result.get('isError'):
            raise ValueError('Magpie ' + name + ' failed')
        content = result['content']
        if not content or any(block.get('type') != 'text' for block in content):
            raise ValueError('Unexpected Magpie ' + name + ' response')
        results.append('\n\n'.join(block['text'] for block in content))
    return results


def install(settings):
    """Install handlers and refresh the search registry; read settings on each call."""
    from mcp_framework import build_registry
    import qwen_mm_plugins_search as package
    from qwen_mm_plugins_search.tools import web_extractor, web_search

    def patch(module, name):
        original = getattr(module.handle, '_magpie_original', module.handle)

        @wraps(original)
        def handle(arguments):
            config = settings()
            if not config.get('DASHSCOPE_BASE_URL') or not config.get('DASHSCOPE_API_KEY'):
                return original(arguments)
            if arguments.get('api_key') is not None:
                return [{'type': 'text', 'text': 'Error: api_key is not supported by Magpie Search; disconnect Magpie to use an upstream search key.'}]
            field = 'queries' if name == 'web_search' else 'urls'
            values = arguments.get(field, [])
            if not values:
                return [{'type': 'text', 'text': f'Error: {field} list is empty'}]
            calls = [('web_search', {'query': value, 'count': 10}) if name == 'web_search'
                     else ('web_fetch', {'url': value, 'max_chars': 8000})
                     for value in values]
            try:
                results = _call_magpie(config, calls)
            except (HTTPError, URLError, TimeoutError, ValueError, KeyError, TypeError):
                return [{'type': 'text', 'text': 'Error: Magpie Search request failed.'}]
            if name == 'web_search':
                text = '\n\n'.join(f'## Query: {value}\n{result}' if len(values) > 1 else result
                                    for value, result in zip(values, results))
            else:
                goal = arguments.get('goal', '')
                text = '\n\n'.join(f'## {value}\n' + (f'(Goal: {goal})\n\n' if goal else '\n') + result
                                    for value, result in zip(values, results))
            return [{'type': 'text', 'text': text}]

        handle._magpie_original = original
        module.handle = handle

    patch(web_search, 'web_search')
    patch(web_extractor, 'web_extractor')
    package.SPECS, package.get_handler, package.list_tools = build_registry(package.__name__, ['tools'])
