# Install — native plugin tools (0.4.0)

## Requirements

- A current Magpie with community plugin tools and automatic per-plugin Library registration (the plugin `tool` hook and automatic Library registration).
- Git, uv/uvx, FFmpeg/ffprobe available on the Magpie host PATH. Node.js 22+ is recommended for development and read-only checks.
- Python 3.13 in the uv runtime; first tool use prepares the pinned upstream runtime with `uvx`.
- Your own providers and models configured in Magpie. Required service keys remain in your existing native configuration or Magpie.

No local model weights are downloaded. First tool use may download the pinned Python package and dependencies; plugin loading and tool enumeration do not.

## Install

```sh
magpie plugin add github:double2tea/magpie-qwen-mm
```

For a local checkout, register its stable directory instead:

```sh
git clone https://github.com/double2tea/magpie-qwen-mm.git "$HOME/.config/magpie/local-plugins/qwen-mm"
magpie plugin add "$HOME/.config/magpie/local-plugins/qwen-mm"
```

Use one copy. After loading, Magpie automatically creates the plugin-owned MCP entry in Library, serving its native tools. There are no manual Python MCP commands, shell variables or absolute script paths to enter. If the MCP router is enabled, its existing Agent access controls apply; otherwise choose permitted Agents on the automatic Library entry.

The Agent descriptor detects `~/.qwen-mm-plugins`. Create that directory if it does not already exist, open the Qwen-MM Agent in Magpie, connect it, and select VL and Omni independently on the plugin page. This preserves native upstream settings and uses `~/.config/magpie/qwen-mm/config` for compatible gateway calls. The settings page remains a token-protected loopback service on port 3496.

## Tools and long tasks

The plugin registers 24 business tools prefixed `qwen_` (two audio, three search and nineteen video-spatial tools), plus `qwen_task_status` and `qwen_task_cancel`.

Each business call returns `{job_id,status,result?}`. Fast tasks complete in the call; a task exceeding 20 seconds returns `running`, and the Agent polls `qwen_task_status`. The existing audio parameter names remain `file_path`, `start_time`, `end_time`, `format`, etc. Generated speech requires `text`, `voice` and `output_path`.

Tasks have a 15-minute runtime limit, at most eight running tasks, a bounded in-memory result list, and 30-minute completed-result retention. A plugin-host restart loses tickets; cancelled/failed work does not silently report success. Tickets are restricted to their calling Agent identity, not to an individual conversation: two conversations using the same Agent can access a ticket if they know its ID. Results do not persist across host restarts. Cancel signals the complete task process group on macOS/Linux; Windows cancellation cannot guarantee descendant termination.

Native tools run a worker only on use. No companion Python MCP service remains, and no additional daemon is installed. The plugin does not change Agent defaults or routing.

## Read-only check

```sh
node /actual/plugin/path/setup.mjs --check
```

This checks packaged files and executable availability and reports native tool count. It does not emit manual MCP registration instructions, write Library, enable Agents or download dependencies. Magpie started from the Dock may have a different PATH from your shell.

## Remove

Remove the plugin in Magpie or run `magpie plugin rm <installed-spec>`. Magpie removes its plugin-owned tool entry; it owns that lifecycle. User-native upstream settings and generated output files are retained. Disabling stops listing tools, but existing running tasks should be cancelled before disabling or updating.

This version has one native registration path. Old hand-written `qwen-mm-audio`, `qwen-mm-plugins-search` and `qwen-mm-plugins-video-spatio` entries are obsolete and should not coexist with the native plugin. They are not created by the new package. Removing pre-existing user entries is an explicit administration action, not a hidden install hook.
