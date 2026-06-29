#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/.venv_funasr/bin/activate"
exec python "$ROOT/scripts/asr/funasr_meeting_transcribe.py" "$@"
