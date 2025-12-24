#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

usage() {
  cat <<'EOF'
Usage:
  scripts/piper_tts.sh [--in <textfile>] [--out <wavfile>] [--model-dir <dir>] \
    [--length-scale <float>] [--sentence-silence <float>] [--noise-scale <float>] [--noise-w <float>]

Defaults:
  --in               out/broadcast.txt
  --out              out/voice.wav
  --model-dir         assets/piper/ru_RU-ruslan-medium
  --length-scale      1
  --sentence-silence  0.9
  --noise-scale       0.55
  --noise-w           0.25

Notes:
  - Requires `piper` to be available in PATH.
  - Expects model files:
      <model-dir>/ru_RU-ruslan-medium.onnx
      <model-dir>/ru_RU-ruslan-medium.onnx.json
EOF
}

err() {
  printf "Error: %s\n" "$1" >&2
  exit 1
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

IN_FILE="${REPO_ROOT}/out/broadcast.txt"
OUT_FILE="${REPO_ROOT}/out/voice.wav"
MODEL_DIR="${REPO_ROOT}/assets/piper/ru_RU-ruslan-medium"

LENGTH_SCALE="1"
SENTENCE_SILENCE="0.9"
NOISE_SCALE="0.55"
NOISE_W="0.25"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --in)
      IN_FILE="$2"
      shift 2
      ;;
    --out)
      OUT_FILE="$2"
      shift 2
      ;;
    --model-dir)
      MODEL_DIR="$2"
      shift 2
      ;;
    --length-scale)
      LENGTH_SCALE="$2"
      shift 2
      ;;
    --sentence-silence)
      SENTENCE_SILENCE="$2"
      shift 2
      ;;
    --noise-scale)
      NOISE_SCALE="$2"
      shift 2
      ;;
    --noise-w)
      NOISE_W="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      err "Unknown argument: $1 (use --help)"
      ;;
  esac
done

command -v piper >/dev/null 2>&1 || err "piper not found in PATH"

MODEL_ONNX="${MODEL_DIR}/ru_RU-ruslan-medium.onnx"
MODEL_JSON="${MODEL_DIR}/ru_RU-ruslan-medium.onnx.json"

[[ -f "$IN_FILE" ]] || err "Input text file not found: $IN_FILE"
[[ -f "$MODEL_ONNX" ]] || err "Model not found: $MODEL_ONNX"
[[ -f "$MODEL_JSON" ]] || err "Model config not found: $MODEL_JSON"

mkdir -p "$(dirname "$OUT_FILE")"

piper \
  --model "$MODEL_ONNX" \
  --config "$MODEL_JSON" \
  --output_file "$OUT_FILE" \
  --length_scale "$LENGTH_SCALE" \
  --sentence_silence "$SENTENCE_SILENCE" \
  --noise_scale "$NOISE_SCALE" \
  --noise_w "$NOISE_W" \
  < "$IN_FILE"

printf "Wrote: %s\n" "$OUT_FILE"
