#!/usr/bin/env bash
# End-to-end local Chinese meeting workflow:
# audio/video -> FunASR transcript -> MLX/Qwen meeting minutes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AUDIO=""
OUTDIR=""
MODEL="mlx-community/Qwen2.5-7B-Instruct-4bit"
LANGUAGE="zh"
MAX_CHARS="7200"
MAX_TOKENS_CHUNK="1800"
MAX_TOKENS_FINAL="2600"
SKIP_ASR="0"
TRANSCRIPT=""

usage() {
  cat <<EOF
Usage:
  $0 /path/to/audio.mp3 [-o outdir] [--model MODEL]
  $0 --transcript /path/to/transcript.txt [-o outdir] [--model MODEL]

Options:
  -o, --outdir DIR             Output directory. Default: ~/Downloads/meeting_transcript_<audio_stem>
  --model MODEL                MLX model. Default: $MODEL
  --language zh|auto|yue|en    ASR language. Default: zh
  --max-chars N                LLM chunk chars. Default: $MAX_CHARS
  --max-tokens-chunk N         Per-chunk output tokens. Default: $MAX_TOKENS_CHUNK
  --max-tokens-final N         Final merge output tokens. Default: $MAX_TOKENS_FINAL
  --transcript TXT             Skip ASR and only organize existing transcript.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--outdir) OUTDIR="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --language) LANGUAGE="$2"; shift 2 ;;
    --max-chars) MAX_CHARS="$2"; shift 2 ;;
    --max-tokens-chunk) MAX_TOKENS_CHUNK="$2"; shift 2 ;;
    --max-tokens-final) MAX_TOKENS_FINAL="$2"; shift 2 ;;
    --transcript) TRANSCRIPT="$2"; SKIP_ASR="1"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    *) if [[ -z "$AUDIO" ]]; then AUDIO="$1"; shift; else echo "Unexpected arg: $1" >&2; exit 2; fi ;;
  esac
done

if [[ "$SKIP_ASR" == "0" && -z "$AUDIO" ]]; then usage >&2; exit 2; fi

if [[ "$SKIP_ASR" == "1" ]]; then
  SRC_TXT="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).expanduser().resolve())' "$TRANSCRIPT")"
  STEM="$(basename "$SRC_TXT" .txt)"
  if [[ -z "$OUTDIR" ]]; then OUTDIR="$(dirname "$SRC_TXT")"; fi
else
  AUDIO_ABS="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).expanduser().resolve())' "$AUDIO")"
  STEM="$(basename "${AUDIO_ABS%.*}")"
  if [[ -z "$OUTDIR" ]]; then OUTDIR="$HOME/Downloads/meeting_transcript_${STEM}"; fi
  mkdir -p "$OUTDIR"
  echo "[workflow] ASR: $AUDIO_ABS -> $OUTDIR" >&2
  "$ROOT/scripts/asr/funasr_meeting.sh" "$AUDIO_ABS" -o "$OUTDIR" --language "$LANGUAGE"
  SRC_TXT="$OUTDIR/${STEM}.txt"
fi

mkdir -p "$OUTDIR"
SUMMARY="$OUTDIR/${STEM}_本地模型整理_Qwen7B.md"
CLEAN="$OUTDIR/${STEM}_本地模型整理_Qwen7B_清洗版.md"
LOG="$OUTDIR/${STEM}_workflow.log"

echo "[workflow] LLM organize: $SRC_TXT -> $SUMMARY" >&2
(
  cd "$ROOT"
  source "$ROOT/.venv_mlx/bin/activate"
  python "$ROOT/skills/meeting-audio-local-workflow/local_mlx_meeting_summarize.py" \
    "$SRC_TXT" \
    -o "$SUMMARY" \
    --model "$MODEL" \
    --max-chars "$MAX_CHARS" \
    --max-tokens-chunk "$MAX_TOKENS_CHUNK" \
    --max-tokens-final "$MAX_TOKENS_FINAL"
) 2>&1 | tee "$LOG"

python3 - "$SUMMARY" "$CLEAN" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
out=Path(sys.argv[2])
s=p.read_text(encoding='utf-8', errors='replace')
# Conservative markdown fence cleanup for accidental whole-document wrappers.
lines=s.splitlines()
if lines and lines[0].strip().startswith('```'):
    lines=lines[1:]
if lines and lines[-1].strip()=='```':
    lines=lines[:-1]
s='\n'.join(lines).replace('\n```\n---\n\n# 附：分段整理草稿', '\n---\n\n# 附：分段整理草稿')
out.write_text(s.strip()+'\n', encoding='utf-8')
print(out)
PY

echo "[workflow] done" >&2
echo "Transcript: $SRC_TXT"
echo "Summary:    $CLEAN"
echo "Partials:   ${SUMMARY%.md}.partial.md"
echo "Log:        $LOG"
