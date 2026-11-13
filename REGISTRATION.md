# Magpie community discovery

This repository is an independent wrapper for Qwen-MM-Plugins, not an official Qwen or Magpie plugin.

## Discovery requirements

Magpie's community discovery searches public GitHub repositories with the `magpie-plugin` topic, excluding archived repositories and forks. It reads root `package.json` metadata for the package name, version, kind and icon. This repository supplies:

- `magpie.agent`: the native Qwen-MM Agent descriptor.
- `magpie.page`: the model configuration page.
- `main`: the native plugin host for its settings service.
- Name, localized description, icon, Apache-2.0 license and source repository metadata.

Source: https://github.com/yetone/magpie/blob/main/internal/plugin/github.go

The repository is tagged `magpie-plugin`; npm publication and a separate enrollment request are not required for GitHub discovery. Discovery is not a maintainer review, security audit or endorsement. Client indexing/cache can delay display.

## Installation scope

The plugin is installable with:

```sh
magpie plugin add github:double2tea/magpie-qwen-mm
```

Follow [INSTALL.md](INSTALL.md) afterward. Installing the plugin alone does not install uv/FFmpeg or register all companion MCP services. The Agent detection directory must exist. MCP commands need the actual stable installed path; do not register a second copy alongside a local checkout.

Manual prerequisites are explicit to avoid hidden dependency downloads or broad changes to the user's Library. First `uvx` use downloads the pinned upstream package and its dependencies. Runtime usage requires the user's own providers and billing authorization.

## Boundaries

The configuration page manages separate VL/Omni models. The wrapper adapts its own supported media calls; it does not fix generic Agent attachment conversion. The separate Magpie Media Adapter handles gateway request normalization. Dedicated native ASR/TTS and search paths have their own protocol constraints.

Agy CLI remains available for visual use but is not a supported Omni audio route. Long-form media and exact temporal alignment are not universally validated. CI validates isolated fixtures without real credentials; successful tests do not certify every third-party model or operating system.

Future simplification should use a supported Magpie lifecycle API to offer MCP registration with explicit scope and reversible removal. The current plugin does not silently rewrite Library entries or install system dependencies merely to qualify for discovery.

## Requesting curated inclusion

Magpie also reads a maintained community catalog from [magpie-community/plugins](https://github.com/magpie-community/plugins). Its [README](https://github.com/magpie-community/plugins#write-your-own) describes supported plugin types. This is distinct from topic-based discovery; there is no promise of automatic review or inclusion.

A reasonable next step is to ask those maintainers whether an externally hosted Agent/page wrapper belongs in their catalog, linking a tagged release, license, tests, source and manual installation boundaries. Do not describe inclusion as official Qwen endorsement or a security audit. Do not open a PR adding guessed catalog fields before maintainers confirm the expected format.

Before submitting, verify a fresh installation and removal on an isolated Magpie profile, preserve the explicit dependency/MCP opt-in, and disclose the settings service on loopback port 3496 and upstream package pin. The read-only `setup.mjs --check` assistant reduces path-copy errors but does not claim one-click installation.
