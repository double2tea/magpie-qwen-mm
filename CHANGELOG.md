# Changelog

## 0.3.6 — 2026-11-13

- Finalize the exact known Bailian streaming placeholder sizes in downloaded PCM WAV artifacts. Files no longer appear approximately 12.4 hours long when the audio is only seconds long.
- Preserve PCM bytes, valid WAVs, unrecognized headers and other providers unchanged. Reject incomplete sample frames in the recognized placeholder layout.
- Add four targeted regression cases, bringing the complete suite to 10 JavaScript and 27 Python tests.
- Document community discovery requirements and manual installation boundaries.

This publishes the previously local fix for issue #1. No upstream Qwen-MM package, Agent defaults, routing priorities or provider credentials are changed.
