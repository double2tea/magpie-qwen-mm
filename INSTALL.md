# Install

This repository is a Magpie wrapper for [Qwen-MM-Plugins](https://github.com/QwenLM/Qwen-MM-Plugins), not a fork. The launcher and MCP commands use the upstream tag `qwen-mm-plugins-video-spatio-v1.1.0` with the `api`, `search`, and `video-spatio` extras.

## Requirements

- Magpie with community plugins, agent providers, and Library → MCP support.
- Git, Node.js 22 or later, Python 3.13, [uv / uvx](https://docs.astral.sh/uv/getting-started/installation/), and FFmpeg on `PATH`. Magpie's MCP process must also be able to find `uvx` and FFmpeg.
- Your own providers and models configured in Magpie. Choose a vision model for VL and a model supporting your intended audio/video inputs for Omni.

The first `uvx` launch downloads the pinned upstream package and its dependencies. API-backed tools require your own configured services; this wrapper does not install local model weights.

## Register the plugin

Clone to a known location so the MCP servers can use a stable absolute path:

```sh
mkdir -p "$HOME/.config/magpie/local-plugins" "$HOME/.qwen-mm-plugins"
git clone https://github.com/double2tea/magpie-qwen-mm.git "$HOME/.config/magpie/local-plugins/qwen-mm"
magpie plugin add "$HOME/.config/magpie/local-plugins/qwen-mm"
```

Create `~/.qwen-mm-plugins` before registering: Magpie uses this directory to detect the `qwen-mm` agent. It is separate from the plugin's source directory.

Magpie also supports direct GitHub installation:

```sh
magpie plugin add github:double2tea/magpie-qwen-mm
```

Use one installation method. For a GitHub installation, resolve its actual installed directory before configuring MCP; do not assume it is the clone location above. `magpie plugin list --json` can help inspect the registered plugin. If it does not expose a usable source path, use the fixed local clone method.

## Connect and choose models

```sh
magpie qwen-mm provider magpie
```

Open the **magpie-agent-qwen-mm-plugins** page in Magpie and select VL and Omni independently from your own providers/models. The page service listens locally on port `3496`; open it through Magpie. The managed agent configuration is `~/.config/magpie/qwen-mm/config`.

Provider IDs are specific to your Magpie setup. No provider named `qwen-cn` or `bailian-token-plan` is required for selecting VL and Omni. Provider credentials remain managed in Magpie; do not paste them into this repository, MCP arguments, or logs. The connection command writes Magpie's gateway connection to the managed config; installation does not replace your native upstream API keys.

## Add the MCP servers

Generate the exact entries for the installed directory, without writing any configuration:

```sh
node /actual/plugin/path/setup.mjs --check
```

The result contains names, commands and argument arrays ready to copy into Library → MCP. It checks executable availability on the current PATH and prints installed Node/Python versions. It does not install dependencies, create environments, download models, overwrite existing MCP entries or enable Agents. Magpie's GUI process may have a different PATH; a shell check is not a full runtime compatibility test. Review the requirements above (including Python 3.13 and Node 22+) against the reported versions.


In **Magpie → Library → MCP**, manually add these three stdio entries. Enable the ones you need for your agent:

| Suggested name | Final argument (`ENTRY`) |
| --- | --- |
| `qwen-mm-audio` | `audio` |
| `qwen-mm-search` | `search` |
| `qwen-mm-video-spatio` | `video-spatio` |

Use `uvx` as the command for each entry, with this argument array:

```json
[
  "--from",
  "qwen-mm-plugins[api,search,video-spatio] @ git+https://github.com/QwenLM/Qwen-MM-Plugins.git@qwen-mm-plugins-video-spatio-v1.1.0",
  "python",
  "/ABSOLUTE/HOME/.config/magpie/local-plugins/qwen-mm/qwen_mm_gateway.py",
  "ENTRY"
]
```

Replace `ENTRY` with the corresponding table value and `/ABSOLUTE/HOME` with your actual home directory. JSON arguments do **not** expand `~`, `$HOME`, or shell variables. For a different installation location, use that plugin's actual absolute `qwen_mm_gateway.py` path. Do not point these entries directly at the upstream modules: the gateway applies the Magpie adapters.

The bundled `qwen-mm` executable runs the same pinned wrapper, for example:

```sh
"$HOME/.config/magpie/local-plugins/qwen-mm/qwen-mm" audio
```

## Speech and search services

Speech defaults use `bailian-token-plan/qwen-audio-3.0-asr-flash` and `bailian-token-plan/qwen-audio-3.0-tts-plus`. These defaults only work if that provider exists in your Magpie setup. Otherwise pass an explicit `model` as `your-provider-id/your-model` to the speech tool and ensure the provider supports the relevant transcription or speech endpoint. Selecting the page's Omni model does not change these speech defaults.

When connected, `web_search` and `web_extractor` use Magpie's configured web-search service. `image_search` still uses upstream Serper and needs your own `SERPER_API_KEY` in the upstream/native configuration. The pinned search dependencies include `requests`. For direct native upstream use, configure your own required API keys following the [upstream documentation](https://github.com/QwenLM/Qwen-MM-Plugins/tree/qwen-mm-plugins-video-spatio-v1.1.0); registration does not provision those keys. Keep keys out of logs and shared configuration examples.

## Verify locally

From the repository directory:

```sh
node --test settings.test.mjs server.test.mjs page.test.mjs
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp uvx --python 3.13 --from 'qwen-mm-plugins[api,search,video-spatio] @ git+https://github.com/QwenLM/Qwen-MM-Plugins.git@qwen-mm-plugins-video-spatio-v1.1.0' python -m unittest -q test_qwen_mm_gateway test_qwen_mm_audio test_qwen_mm_search
```

The tests use generated media, mocks, and local HTTP fixtures. They require FFmpeg but no API keys, external model calls, or local model downloads. Dependency installation requires network access unless already cached.

中文摘要：先创建 `~/.qwen-mm-plugins`，再克隆到固定本地目录并用绝对路径注册。运行 `magpie qwen-mm provider magpie` 后，在 magpie-agent-qwen-mm-plugins 页面分别选择自己已有的 VL、Omni 模型。Library → MCP 中手动添加上表三个入口，JSON 路径必须替换成真实绝对路径；语音默认 provider 与 Serper 图片搜索所需密钥需自行配置。
