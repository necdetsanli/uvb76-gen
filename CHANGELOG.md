# Changelog

## [0.1.0] - 2025-12-24

Initial release of **uvb76-gen**, a UVB-76 inspired numbers-station style generator with optional audio rendering.

### Added
- `uvb76-gen gen` command to:
  - Encrypt plaintext (A–Z) into 5-digit number groups.
  - Generate Russian TTS-friendly `broadcast.txt` and `groups.txt`.
  - Also write `groups_raw.txt` for debugging/decoding.
- `uvb76-gen decode` command to recover plaintext from either:
  - Raw 5-digit groups (`groups_raw.txt` style), or
  - Russian digit-word formatted groups (`groups.txt` style).
- `uvb76-gen render-audio` command to render a UVB-ish mix using FFmpeg.
- Russian formatting utilities:
  - Digit-word rendering for groups.
  - Callsign spelling for Cyrillic/Latin letters and digits.
  - Key-to-codewords mapping (`codewords_from_key`) to derive spoken codewords from the provided key.
- FFmpeg-based audio renderer:
  - Noise bed across the full output.
  - Synthesized harmonic buzzer gated into two edge windows.
  - Voice processing chain (EQ, compression, soft clip, tremolo, reverb).
  - Deterministic timeline with intro/outro static-only sections and controlled buzzer/voice placement.
  - Automatic minimum duration computed from the input voice length plus padding; optional `--duration` to extend output.
  - Clear error message if requested duration is shorter than the computed minimum.

### Changed
- CLI defaults moved toward Russian-first output:
  - Default callsign set to `УВБ76`.
  - Names are derived from `--key` via Russian codewords unless explicitly provided via repeated `--name`.
- Audio duration semantics:
  - If `--duration` is omitted, renderer targets the computed minimum duration.
  - If `--duration` is provided and longer than minimum, extra time is inserted into the post-voice gap.
  - If `--duration` is shorter than minimum, an error is raised with the computed minimum.

### Fixed
- Prevented “voice appended at the end” behavior by trimming/placing voice strictly into the intended timeline.
- Hardened parsing and decode flow to accept both digit and Russian word group representations.
- Improved static+buzzer+voice timing to avoid buzzer and voice starting simultaneously.

### Developer experience
- Added/standardized docstrings across public modules and functions.
- Lint/type/test tooling wired via `ruff`, `mypy`, `pytest`.
- Packaging configured via `hatchling`; CLI entrypoint registered as `uvb76-gen`.

### Notes
- TTS generation (Piper) is supported as an external tool workflow and is not bundled as a Python dependency.
- Audio rendering requires FFmpeg available on the system.
