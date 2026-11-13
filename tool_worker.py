"""Execute one native plugin tool; stdout is one JSON result, never SDK logging."""
import contextlib
import inspect
import asyncio
import json
import sys
from pathlib import Path

from qwen_mm_gateway import install
from urllib.parse import urlsplit


@contextlib.contextmanager
def local_gateway_clients():
    import openai
    import httpx
    original = openai.OpenAI
    with contextlib.ExitStack() as clients:
        def create(*args, **kwargs):
            target = urlsplit(str(kwargs.get('base_url', '')))
            if target.hostname in ('localhost', '127.0.0.1', '::1') and 'http_client' not in kwargs:
                kwargs['http_client'] = clients.enter_context(httpx.Client(trust_env=False))
            return original(*args, **kwargs)
        openai.OpenAI = create
        try:
            yield
        finally:
            openai.OpenAI = original


class ModelRequestError(RuntimeError):
    """A safe diagnostic for model errors swallowed by upstream expert helpers."""


def execute(entry, name, arguments):
    install()
    failures = []
    if entry == 'video-spatio':
        from shared import api_openai
        original = api_openai.call_openai_chat

        def checked_chat(**kwargs):
            try:
                return original(**kwargs)
            except Exception as error:
                import traceback
                frame = traceback.extract_tb(error.__traceback__)[-1]
                origin = ' at ' + Path(frame.filename).name + ':' + str(frame.lineno)
                failures.append(type(error).__name__ + origin)
                raise

        api_openai.call_openai_chat = checked_chat
    import importlib
    package = {'audio': 'qwen_mm_plugins_api', 'search': 'qwen_mm_plugins_search', 'video-spatio': 'qwen_mm_plugins_video_spatio'}[entry]
    module = importlib.import_module(package)
    handler = module.get_handler(name)
    if handler is None:
        raise ValueError('Unknown upstream tool')
    try:
        with local_gateway_clients():
            result = handler(arguments)
            result = asyncio.run(result) if inspect.isawaitable(result) else result
    finally:
        if entry == 'video-spatio':
            api_openai.call_openai_chat = original
    if failures:
        raise ModelRequestError('Visual model request failed (' + failures[0] + '); no visual verdict is available')
    if isinstance(result, list) and any(isinstance(part, dict) and part.get('type') == 'text' and part.get('text', '').startswith('Error:') for part in result):
        raise ValueError('Upstream tool returned an error')
    return result


def main():
    request = json.load(sys.stdin)
    manifest = json.loads(Path(__file__).with_name('tools.json').read_text())
    if not any(item['entry'] == request['entry'] and item['name'] == request['name'] for item in manifest):
        raise ValueError('Tool is not in the packaged manifest')
    with contextlib.redirect_stdout(sys.stderr):
        result = execute(request['entry'], request['name'], request['arguments'])
    payload = json.dumps({'result': result}, ensure_ascii=False, allow_nan=False)
    sys.stdout.write(payload)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # SDK exceptions can contain authorization data or signed URLs.
        print(json.dumps({'error': str(error) if isinstance(error, ModelRequestError) else type(error).__name__ + ': tool execution failed; check the selected provider and input'}))
        raise SystemExit(1)
