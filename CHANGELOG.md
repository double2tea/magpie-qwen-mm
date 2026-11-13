# Changelog

## 0.4.0 — 2026-11-13

- Replace three manual MCP registrations with native plugin tools and Magpie-owned Library lifecycle.
- Preserve the existing 24 tool schemas/handlers; add Agent-owned task queries and cancellation for long operations.
- Remove the stdio shell launcher and manual setup plan. Keep a read-only native installation checker.
- Preserve model settings, native keys, media adapters and WAV repair.

## 0.3.7 — 2026-11-13

- Add a read-only setup assistant that outputs installation-specific MCP arguments and checks available dependencies.
- Document the maintained community catalog and its review boundaries.
- Add three tests for paths with spaces, dependency checks and a configuration-free plan.

## 0.3.6 — 2026-11-13

- Finalize the exact known Bailian streaming placeholder sizes in downloaded PCM WAV artifacts. Files no longer appear approximately 12.4 hours long when the audio is only seconds long.
- Preserve PCM bytes, valid WAVs, unrecognized headers and other providers unchanged. Reject incomplete sample frames in the recognized placeholder layout.
- Add four targeted regression cases, bringing the complete suite to 10 JavaScript and 27 Python tests.
- Document community discovery requirements and manual installation boundaries.

This publishes the previously local fix for issue #1. No upstream Qwen-MM package, Agent defaults, routing priorities or provider credentials are changed.
