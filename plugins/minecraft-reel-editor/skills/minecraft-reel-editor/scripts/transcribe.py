#!/usr/bin/env python3
"""Transcribe a video locally into normalized word-timestamp JSON and Markdown."""

from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path
from typing import Any

from common import (
    ReelError,
    clean_join,
    format_time,
    media_duration,
    probe_media,
    save_json,
)


MLX_MODEL = "mlx-community/whisper-large-v3-turbo"
FASTER_MODEL = "turbo"


def choose_backend(requested: str) -> str:
    if requested != "auto":
        return requested
    if sys.platform == "darwin" and platform.machine().lower() in {"arm64", "aarch64"}:
        return "mlx"
    return "faster"


def mlx_result(source: Path, model: str) -> dict[str, Any]:
    try:
        import mlx_whisper
    except ImportError as exc:
        raise ReelError("mlx-whisper is not installed. Run bootstrap.py first.") from exc
    return mlx_whisper.transcribe(
        str(source),
        path_or_hf_repo=model,
        language="en",
        word_timestamps=True,
        condition_on_previous_text=False,
        verbose=False,
    )


def faster_result(source: Path, model: str, device: str) -> dict[str, Any]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ReelError("faster-whisper is not installed. Run bootstrap.py first.") from exc
    compute_type = "int8" if device == "cpu" else "default"
    whisper = WhisperModel(model, device=device, compute_type=compute_type)
    generated, info = whisper.transcribe(
        str(source),
        language="en",
        beam_size=5,
        word_timestamps=True,
        condition_on_previous_text=False,
        vad_filter=False,
    )
    segments: list[dict[str, Any]] = []
    for segment in generated:
        segments.append(
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "words": [
                    {
                        "start": word.start,
                        "end": word.end,
                        "word": word.word,
                        "probability": word.probability,
                    }
                    for word in (segment.words or [])
                ],
            }
        )
    return {
        "text": " ".join(segment["text"].strip() for segment in segments),
        "segments": segments,
        "language": getattr(info, "language", "en"),
    }


def normalize(
    raw: dict[str, Any],
    *,
    source: Path,
    backend: str,
    model: str,
    duration: float,
) -> dict[str, Any]:
    normalized_segments: list[dict[str, Any]] = []
    normalized_words: list[dict[str, Any]] = []
    word_number = 1
    for segment_number, raw_segment in enumerate(raw.get("segments", []), start=1):
        segment_id = f"s{segment_number:04d}"
        segment_words: list[dict[str, Any]] = []
        for raw_word in raw_segment.get("words") or []:
            start = raw_word.get("start")
            end = raw_word.get("end")
            text = str(raw_word.get("word", raw_word.get("text", ""))).strip()
            if start is None or end is None or not text or float(end) <= float(start):
                continue
            word = {
                "id": f"w{word_number:06d}",
                "segment_id": segment_id,
                "start": round(float(start), 3),
                "end": round(float(end), 3),
                "text": text,
            }
            probability = raw_word.get("probability")
            if probability is not None:
                word["probability"] = round(float(probability), 4)
            word_number += 1
            segment_words.append(word)
            normalized_words.append(word)
        if not segment_words:
            continue
        normalized_segments.append(
            {
                "id": segment_id,
                "start": segment_words[0]["start"],
                "end": segment_words[-1]["end"],
                "text": clean_join(segment_words),
                "start_word": segment_words[0]["id"],
                "end_word": segment_words[-1]["id"],
            }
        )
    if not normalized_words:
        raise ReelError("Transcription produced no word timestamps.")
    return {
        "schema_version": 1,
        "source": str(source.resolve()),
        "language": "en",
        "duration": round(duration, 3),
        "backend": "mlx-whisper" if backend == "mlx" else "faster-whisper",
        "model": model,
        "segments": normalized_segments,
        "words": normalized_words,
    }


def write_markdown(path: Path, transcript: dict[str, Any]) -> None:
    lines = [
        "# Timestamped transcript",
        "",
        f"- Source: `{transcript['source']}`",
        f"- Backend: `{transcript['backend']}`",
        f"- Model: `{transcript['model']}`",
        f"- Duration: {format_time(transcript['duration'])}",
        "",
        "Use the word-ID ranges as immutable edit anchors.",
        "",
    ]
    for segment in transcript["segments"]:
        lines.append(
            f"- **{format_time(segment['start'])}–{format_time(segment['end'])}** "
            f"`{segment['start_word']}–{segment['end_word']}` — {segment['text']}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--backend", choices=["auto", "mlx", "faster"], default="auto")
    parser.add_argument("--model")
    parser.add_argument("--device", default="auto", help="faster-whisper device: auto, cpu, or cuda")
    args = parser.parse_args()

    source = args.input.expanduser().resolve()
    if not source.exists():
        raise ReelError(f"Input does not exist: {source}")
    probe = probe_media(source)
    backend = choose_backend(args.backend)
    model = args.model or (MLX_MODEL if backend == "mlx" else FASTER_MODEL)
    raw = (
        mlx_result(source, model)
        if backend == "mlx"
        else faster_result(source, model, args.device)
    )
    transcript = normalize(
        raw,
        source=source,
        backend=backend,
        model=model,
        duration=media_duration(probe),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    save_json(args.output_dir / "transcript.json", transcript)
    write_markdown(args.output_dir / "transcript.md", transcript)
    print(args.output_dir / "transcript.json")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReelError as error:
        raise SystemExit(str(error)) from error
