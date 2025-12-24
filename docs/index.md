# uvb76-gen

uvb76-gen is a small Python tool that generates UVB-76 inspired number-group broadcasts.
It can produce 5-digit groups, a Russian TTS friendly script, and an optional audio mix that overlays a static bed and a buzzer around a spoken message.

This project is for educational and creative use.
It is not affiliated with any real transmitter or organization, and it is not meant to be used for real secrecy.

## Background: what are numbers stations?

Numbers stations are shortwave radio transmissions that broadcast sequences of numbers, letters, or codewords.
They are typically anonymous, repeat on schedules, and often use a distinctive prelude sound or melody.
A common theory is that these broadcasts are a simple way to send one-way messages to field agents, where the payload is encrypted and then read out loud over the air.
Properly used one-time pads are widely discussed as a plausible method because they can make the plaintext infeasible to recover without the pad.

Well known examples that are often discussed by hobbyists include:

- UVB-76, also known as “The Buzzer”
- E03 “The Lincolnshire Poacher”
- “Swedish Rhapsody”
- Recordings collected in “The Conet Project”

## UVB-76, “The Buzzer”, in a nutshell

UVB-76 is a shortwave station associated with a persistent buzzing tone on 4625 kHz.
Public monitoring reports date it back to the late 1970s, and the modern buzzer style is commonly described as having replaced an earlier marker tone around 1990.
The station sometimes interrupts the buzzer with voice transmissions, and its purpose is not officially confirmed.
Common guesses include military communications, readiness checks, or a channel marker for a wider system, but these remain speculative.

## What this repository does

- Generates plaintext-to-groups output similar in spirit to classic numbers stations.
- Renders a Russian TTS friendly broadcast script (callsign, codewords, digit words, and an explicit “КОНЕЦ.” ending).
- Decodes groups back to plaintext given the same key and mask key.
- Optionally renders an audio mix using FFmpeg:
  - a continuous pink-noise static bed
  - a synthesized buzzer that plays only at the start and end windows
  - a processed voice track (compression, soft clipping, tremolo, echo/reverb)

## Tooling and dependencies

Runtime:

- Python 3.11+ (3.12 recommended)
- ffmpeg and ffprobe available in PATH (used for audio rendering and duration probing)

Python libraries:

- typer (CLI)
- rich (CLI output)
- ruff, mypy, pytest (development)

Optional:

- piper (TTS) if you want to synthesize voice audio from the generated broadcast script

## How the cipher works

The cipher is intentionally simple and “UVB-ish”. It is not designed to be cryptographically strong.

1) Plaintext sanitization

- Plaintext is uppercased and stripped to A-Z only.
- Non A-Z characters are removed.

2) Vigenere step

- A classic Vigenere transform is applied over the A-Z alphabet (A=0..Z=25).
- Encryption: c[i] = (p[i] + k[i mod len(k)]) mod 26
- Decryption: p[i] = (c[i] - k[i mod len(k)] + 26) mod 26

3) Group encoding

- Cipher symbols are padded to a multiple of 3 using a sentinel value 26.
- Each triplet (a, b, c) is packed into base-27:
  - N = a * 27 * 27 + b * 27 + c, where N is in [0..19682]
- A deterministic per-triplet offset is added so that the result fits into 5 digits:
  - offset = xorshift32(seed32(mask_key)) % 80318
  - group = N + offset, then zero-padded to 5 digits
- Decoding subtracts the same offsets and reverses the base-27 packing, then removes the padding sentinel.

The key is used for the Vigenere step.
The mask key is used only for the deterministic offsets that scramble the 5-digit groups.

## Installation

Clone the repository:

```bash
git clone <your-repo-url>
cd uvb76-gen
```

If you use uv:

```bash
uv sync
```

Or with pip:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

For audio rendering, make sure ffmpeg and ffprobe are installed:

```bash
ffmpeg -version
ffprobe -version
```

## Usage

### Generate a broadcast script and groups

```bash
uv run uvb76-gen gen   --text "IF YOU SOLVE THIS, EMAIL ME"   --key "NECDET"   --callsign "УВБ76"   --out-dir out
```

Outputs:

- out/groups_raw.txt (raw 5-digit groups)
- out/groups.txt (Russian digit words)
- out/broadcast.txt (Russian TTS friendly script)

You can override the codewords using repeated --name flags:

```bash
uv run uvb76-gen gen   --text "HELLO"   --key "NECDET"   --name "НИКОЛАЙ" --name "ЕЛЕНА"   --out-dir out
```

### Decode groups back to plaintext

```bash
uv run uvb76-gen decode --key "NECDET" --groups-file out/groups_raw.txt
```

You can also pass groups as text via --groups.
The decoder accepts either raw 5-digit groups or Russian digit words.

### Render the UVB-ish audio mix

The audio renderer expects a voice track (wav, mp3, etc) as input and produces a final mix.

```bash
uv run uvb76-gen render-audio   --voice-wav out/voice.wav   --out out/mix.mp3
```

Duration behavior:

- If you do not provide --duration, the renderer computes the minimum duration required to fit the whole timeline.
- If you provide --duration, it must be at least that minimum or the command fails with an error that prints the minimum.

## End-to-end example with Piper TTS

1) Generate the script:

```bash
uv run uvb76-gen gen --text "IF YOU SOLVE THIS, EMAIL ME" --key "NECDET" --out-dir out
```

2) Synthesize voice audio from the broadcast script:

```bash
cat out/broadcast.txt | piper   --model assets/piper/ru_RU-ruslan-medium/ru_RU-ruslan-medium.onnx   --config assets/piper/ru_RU-ruslan-medium/ru_RU-ruslan-medium.onnx.json   --output_file out/voice.wav   --length_scale 1   --sentence_silence 0.9   --noise_scale 0.55   --noise_w 0.25
```

3) Render the final mix:

```bash
uv run uvb76-gen render-audio --voice-wav out/voice.wav --out out/mix.mp3
```

## Development

Run the test suite:

```bash
uv run pytest
```

Lint and typecheck:

```bash
uv run ruff check .
uv run mypy src
```

## License

See the license file in this repository: [LICENSE](license.md).
