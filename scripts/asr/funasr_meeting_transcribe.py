#!/usr/bin/env python3
"""Local Chinese meeting transcription with FunASR SenseVoiceSmall + FSMN-VAD + CAM++.

Usage:
  . .venv_funasr/bin/activate
  python scripts/asr/funasr_meeting_transcribe.py input.mp3 -o output_dir
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

TAG_RE = re.compile(r"<\|[^|]+\|>")


def clean_text(s: str | None) -> str:
    if not s:
        return ""
    return TAG_RE.sub("", s).strip()


def ms_to_ts(ms: int | float | None) -> str:
    if ms is None:
        ms = 0
    ms = int(ms)
    h = ms // 3_600_000
    ms %= 3_600_000
    m = ms // 60_000
    ms %= 60_000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def ms_to_srt_ts(ms: int | float | None) -> str:
    return ms_to_ts(ms).replace(".", ",")


def ensure_wav_16k_mono(
    src: Path,
    keep: bool = False,
    start_s: float | None = None,
    duration_s: float | None = None,
) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    """Convert with ffmpeg for stable long-audio handling.

    Some long MP3 recordings contain a few corrupt frames (e.g. "Header missing").
    We ask ffmpeg to discard/ignore bad packets so a single damaged frame does not
    abort the whole meeting transcription.
    """
    if not src.exists():
        raise FileNotFoundError(src)
    tmp = tempfile.TemporaryDirectory(prefix="funasr_audio_")
    dst = Path(tmp.name) / (src.stem + ".16k.wav")
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-fflags",
        "+discardcorrupt",
        "-err_detect",
        "ignore_err",
        "-y",
    ]
    if start_s is not None:
        cmd += ["-ss", str(start_s)]
    cmd += ["-i", str(src)]
    if duration_s is not None:
        cmd += ["-t", str(duration_s)]
    cmd += ["-vn", "-sn", "-dn", "-ac", "1", "-ar", "16000", str(dst)]
    subprocess.run(cmd, check=True)
    if keep:
        suffix = ".16k.wav" if start_s is None and duration_s is None else f".clip_{start_s or 0}_{duration_s or 'end'}.16k.wav"
        kept = src.with_suffix(suffix)
        kept.write_bytes(dst.read_bytes())
        tmp.cleanup()
        return kept, None
    return dst, tmp


def flatten_sentences(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in results:
        if isinstance(item, dict) and item.get("sentence_info"):
            for sent in item["sentence_info"]:
                text = clean_text(sent.get("sentence") or sent.get("text"))
                if not text:
                    continue
                rows.append({
                    "start_ms": sent.get("start"),
                    "end_ms": sent.get("end"),
                    "speaker": sent.get("spk", sent.get("speaker", "")),
                    "text": text,
                })
        elif isinstance(item, dict):
            text = clean_text(item.get("text"))
            if text:
                rows.append({"start_ms": None, "end_ms": None, "speaker": "", "text": text})
    return rows


def write_outputs(rows: list[dict[str, Any]], raw: Any, outdir: Path, stem: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"{stem}.raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / f"{stem}.segments.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    txt_lines = []
    md_lines = [f"# {stem}", ""]
    srt_lines = []
    for i, r in enumerate(rows, 1):
        spk = r.get("speaker")
        label = f"SPK{spk}" if spk != "" and spk is not None else "SPK"
        start = ms_to_ts(r.get("start_ms")) if r.get("start_ms") is not None else "--:--:--.---"
        end = ms_to_ts(r.get("end_ms")) if r.get("end_ms") is not None else "--:--:--.---"
        text = r["text"]
        txt_lines.append(f"[{start} - {end}] {label}: {text}")
        md_lines.append(f"- `{start} - {end}` **{label}**：{text}")
        if r.get("start_ms") is not None and r.get("end_ms") is not None:
            srt_lines.extend([str(i), f"{ms_to_srt_ts(r.get('start_ms'))} --> {ms_to_srt_ts(r.get('end_ms'))}", f"{label}: {text}", ""])

    (outdir / f"{stem}.txt").write_text("\n".join(txt_lines) + "\n", encoding="utf-8")
    (outdir / f"{stem}.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    (outdir / f"{stem}.srt").write_text("\n".join(srt_lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="FunASR meeting transcription: SenseVoiceSmall + fsmn-vad + cam++")
    ap.add_argument("audio", type=Path, help="audio/video file accepted by ffmpeg")
    ap.add_argument("-o", "--outdir", type=Path, default=Path("temp/funasr_outputs"))
    ap.add_argument("--device", default="cpu", choices=["cpu", "mps"], help="cpu is safest for FunASR on macOS; mps may fail for some ops")
    ap.add_argument("--language", default="zh", help="zh/auto/yue/en/ja/ko")
    ap.add_argument("--batch-size-s", type=int, default=60)
    ap.add_argument("--merge-length-s", type=int, default=15)
    ap.add_argument("--no-convert", action="store_true", help="skip ffmpeg 16k mono wav conversion")
    ap.add_argument("--keep-wav", action="store_true", help="keep converted 16k mono wav next to source audio")
    ap.add_argument("--start-s", type=float, default=None, help="debug/partial run: start offset in seconds before transcription")
    ap.add_argument("--duration-s", type=float, default=None, help="debug/partial run: transcribe only this many seconds")
    args = ap.parse_args()

    from funasr import AutoModel

    audio = args.audio.expanduser().resolve()
    tmp = None
    if args.no_convert:
        model_input = audio
    else:
        model_input, tmp = ensure_wav_16k_mono(
            audio,
            keep=args.keep_wav,
            start_s=args.start_s,
            duration_s=args.duration_s,
        )

    print(f"[funasr] loading SenseVoiceSmall + fsmn-vad + cam++ on {args.device} ...", file=sys.stderr)
    model = AutoModel(
        model="iic/SenseVoiceSmall",
        vad_model="fsmn-vad",
        spk_model="cam++",
        device=args.device,
        disable_update=True,
    )
    print(f"[funasr] transcribing: {audio}", file=sys.stderr)
    t0 = time.time()
    res = model.generate(
        input=str(model_input),
        language=args.language,
        use_itn=True,
        batch_size_s=args.batch_size_s,
        merge_vad=True,
        merge_length_s=args.merge_length_s,
    )
    rows = flatten_sentences(res)
    stem = audio.stem
    write_outputs(rows, res, args.outdir, stem)
    print(f"[funasr] done in {time.time()-t0:.1f}s, segments={len(rows)}, outdir={args.outdir}", file=sys.stderr)
    if tmp is not None:
        tmp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
