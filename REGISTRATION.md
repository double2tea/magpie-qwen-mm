# Registration and community review

This independent repository is discoverable by Magpie through its public `magpie-plugin` GitHub topic. Its package declares the native Agent, page and host entry. Native OpenCode-compatible `tool` hooks expose 24 business tools and two task-control tools.

Magpie owns automatic per-plugin Library MCP registration at `/mcp/magpie/tools/<plugin-id>`. Tool schemas are loaded without Python startup or dependency downloads. Router-enabled Agents inherit the router's access scope; otherwise the user selects Agents on the automatic Library entry. Disable/uninstall behavior belongs to Magpie. This plugin does not write Library as an install side effect.

Sources:
- https://github.com/yetone/magpie/blob/main/docs/subsystems/plugin-tools.md
- https://github.com/yetone/magpie/blob/main/internal/library/plugin_tools.go
- https://github.com/yetone/magpie/blob/main/internal/plugin/github.go

## Maintained catalog request

Review request: https://github.com/magpie-community/plugins/issues/1091

The maintainer's response on 2026-11-13 placed this request on hold pending personal review; no changes were required for discovery. They intend to verify the release checksum, run `setup.mjs --check`, and install/remove on a separate machine without calling Qwen against a real account.

Version 0.4.0 replaces the manual three-MCP arrangement completely. `setup.mjs --check` remains read-only for review but now checks native tool packaging and host dependencies instead of generating old MCP commands. The upstream package is still fetched on first actual uvx use, and the existing token-protected settings page remains a local service on port 3496. Those characteristics must remain visible to reviewers.

Installation needs a current Magpie supporting automatic plugin tools; legacy releases without this interface are not supported by this version. Do not install both the old manual MCPs and this native entry. Removing pre-existing explicit entries is a separate administration action; the package does not silently delete user configuration.

See INSTALL.md for task timeouts, Agent-level ticket ownership, limits, dependency preparation and removal semantics. Community discovery is not a security audit, catalog approval or Qwen endorsement.
