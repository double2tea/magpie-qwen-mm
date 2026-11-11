# Why the agy-cli Gemini route does not receive audio

Investigation date: 2026-11-11. This document describes the versions inspected, not every future agy release.

## Observed behavior

A synthetic four-second clip contained red frames followed by blue frames and the spoken sentence “The secret number is seven”. The Qwen wrapper's original request to `agy-cli/gemini-3.8-flash` returned unavailable. Converting the clip to ordered images plus an audio file attachment let that channel identify the colors, but its speech transcription remained unavailable. The same representation worked through `google/gemini-3.8-flash`.

Two independent boundaries explain this behavior:

1. **Protocol conversion:** the agy provider declares the Anthropic SDK protocol. Magpie converts a generic file attachment into text in that protocol, so inline WAV becomes `[attachment audio/wav]` and its bytes do not reach the adapter. Images have their own supported representation and survive.
2. **CLI capability:** the installed Antigravity ACP Server **1.5.3** reported `promptCapabilities: {"image": true, "audio": false, "embeddedContext": true}` in a local initialize handshake. Audio support therefore cannot be enabled by changing this wrapper's request format alone.

This is a restriction of the inspected integration path. It is not evidence that the Gemini model itself lacks audio understanding.

## Conversion trace

```text
OpenAI-compatible request: file(audio/wav) + image_url frames
  -> Magpie internal representation: File + Image
  -> agy provider's Anthropic protocol
  -> File becomes text "[attachment audio/wav]"; Image remains image
  -> agy bridge constructs ACP text/image prompt parts
  -> agy ACP 1.5.3 advertises image=true, audio=false
```

The native Google path instead maps both `Image` and `File` to Gemini `inlineData`, preserving audio bytes.

## Source and local checks

The inspected Magpie binary reported application version 0.1.3734 while its Go build module metadata named v0.1.3749. Source references below are pinned to that module tag. The live binary contains the attachment placeholder string; no captured production request body or credentials are included here.

- [Magpie `anthropicBody`, `case File`](https://github.com/yetone/magpie/blob/v0.1.3749/internal/gateway/anthropic.go#L945): emits a text block using `attachmentText`.
- [Attachment placeholder construction](https://github.com/yetone/magpie/blob/v0.1.3749/internal/gateway/ir.go#L118): renders the media type and optional URL as text.
- [Chat file parsing](https://github.com/yetone/magpie/blob/v0.1.3749/internal/gateway/chat.go#L209): recognizes compatible file attachments as internal files.
- [Plugin SDK protocol selection](https://github.com/yetone/magpie/blob/v0.1.3749/internal/provider/plugins.go#L248): selects Anthropic for `@ai-sdk/anthropic`.
- [Gemini inline media conversion](https://github.com/yetone/magpie/blob/v0.1.3749/internal/gateway/codeassist.go#L409): preserves image and file media.

The installed `@magpie-community/opencode-agy-cli-auth` **0.1.18** was inspected separately. Its model declaration advertises text and image input; its ACP prompt construction handles text/images, and binary documents or explicit audio content blocks are rejected. Isolated checks against a copy of the installed adapter confirmed these behaviors without changing the live package. Its upstream lives in [magpie-community/plugins, packages/agy-cli](https://github.com/magpie-community/plugins/tree/main/packages/agy-cli).

A local `agy acp` initialization, with no model prompt, independently confirmed the CLI's advertised `audio: false` capability.

## Practical implications

For audio or audiovisual requests, use a verified audio-capable route such as Gemini Native or Qwen Omni. This plugin leaves saved choices untouched, warns for the inspected agy channel and refuses its audio input explicitly instead of silently sending a text placeholder.

To support audio through agy, the CLI needs to support ACP audio, the bridge needs to map and advertise audio, and Magpie needs a path that preserves those bytes through the bridge protocol. Changing only the model ID or treating audio as an image does not satisfy these requirements.

Newer CLI versions and the backend's behavior after genuine ACP audio forwarding were not tested. The discovery result does not justify claiming that an agy update alone already fixes the issue. No issue or message was sent to upstream maintainers as part of this investigation.
