#!/usr/bin/env python3
"""Shared, dependency-free helpers for the Minecraft reel editor."""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable


ALLOWED_LAYOUTS = {"center_crop", "full_frame"}
ALLOWED_PAUSE_MODES = {"compress", "preserve"}
ALLOWED_ROLES = {"hook", "setup", "bridge", "escalation", "payoff"}


class ReelError(RuntimeError):
    """User-facing workflow or validation error."""


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: str | Path, data: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def require_executable(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise ReelError(f"Required executable not found: {name}")
    return found


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=capture,
    )


def probe_media(path: str | Path) -> dict[str, Any]:
    ffprobe = require_executable("ffprobe")
    result = run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        capture=True,
    )
    return json.loads(result.stdout)


def media_duration(probe: dict[str, Any]) -> float:
    raw = probe.get("format", {}).get("duration")
    if raw is not None:
        return float(raw)
    durations = [
        float(stream["duration"])
        for stream in probe.get("streams", [])
        if stream.get("duration") is not None
    ]
    if not durations:
        raise ReelError("Could not determine media duration.")
    return max(durations)


def video_stream(probe: dict[str, Any]) -> dict[str, Any]:
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    raise ReelError("Input has no video stream.")


def has_audio(probe: dict[str, Any]) -> bool:
    return any(stream.get("codec_type") == "audio" for stream in probe.get("streams", []))


def parse_fps(value: str | None) -> float:
    if not value or value == "0/0":
        return 30.0
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        denominator_value = float(denominator)
        return float(numerator) / denominator_value if denominator_value else 30.0
    return float(value)


def format_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return f"{minutes:02d}:{remainder:05.2f}"


def clean_join(words: Iterable[dict[str, Any]]) -> str:
    tokens = [str(word.get("text", "")).strip() for word in words]
    text = " ".join(token for token in tokens if token)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def transcript_word_map(transcript: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    words = transcript.get("words")
    if not isinstance(words, list) or not words:
        raise ReelError("Transcript contains no word timestamps.")
    index: dict[str, int] = {}
    previous_end = -math.inf
    for position, word in enumerate(words):
        word_id = word.get("id")
        if not isinstance(word_id, str) or word_id in index:
            raise ReelError("Transcript word IDs are missing or duplicated.")
        start = float(word["start"])
        end = float(word["end"])
        if start < 0 or end <= start:
            raise ReelError(f"Invalid timestamp for {word_id}.")
        if start + 0.05 < previous_end:
            raise ReelError(f"Transcript word timestamps move backwards near {word_id}.")
        previous_end = max(previous_end, end)
        index[word_id] = position
    return words, index


def words_for_clip(
    transcript: dict[str, Any],
    start_word: str,
    end_word: str,
) -> list[dict[str, Any]]:
    words, index = transcript_word_map(transcript)
    if start_word not in index or end_word not in index:
        raise ReelError(f"Unknown word range: {start_word}–{end_word}")
    start_index = index[start_word]
    end_index = index[end_word]
    if end_index < start_index:
        raise ReelError(f"Reversed word range: {start_word}–{end_word}")
    return words[start_index : end_index + 1]


def validate_selection(transcript: dict[str, Any], selection: dict[str, Any]) -> None:
    if selection.get("schema_version") != 1:
        raise ReelError("selection.json must use schema_version 1.")
    clips = selection.get("clips")
    if not isinstance(clips, list) or not clips:
        raise ReelError("selection.json must contain at least one clip.")
    used_word_ids: set[str] = set()
    clip_ids: set[str] = set()
    for clip in clips:
        clip_id = clip.get("id")
        if not isinstance(clip_id, str) or not clip_id or clip_id in clip_ids:
            raise ReelError("Every clip needs a unique non-empty id.")
        clip_ids.add(clip_id)
        role = clip.get("role")
        if role not in ALLOWED_ROLES:
            raise ReelError(f"Clip {clip_id} has invalid role: {role}")
        layout = clip.get("layout", "center_crop")
        if layout not in ALLOWED_LAYOUTS:
            raise ReelError(f"Clip {clip_id} has invalid layout: {layout}")
        pause_mode = clip.get("pause_mode", "compress")
        if pause_mode not in ALLOWED_PAUSE_MODES:
            raise ReelError(f"Clip {clip_id} has invalid pause mode: {pause_mode}")
        selected = words_for_clip(transcript, clip["start_word"], clip["end_word"])
        duplicates = used_word_ids.intersection(word["id"] for word in selected)
        if duplicates:
            duplicate = sorted(duplicates)[0]
            raise ReelError(f"Word {duplicate} is selected more than once.")
        used_word_ids.update(word["id"] for word in selected)
        head_padding = float(clip.get("head_padding", 0.08))
        tail_padding = float(clip.get("tail_padding", 0.08))
        if not 0 <= head_padding <= 1:
            raise ReelError(f"Clip {clip_id} head_padding must be between 0 and 1 second.")
        if not 0 <= tail_padding <= 3:
            raise ReelError(f"Clip {clip_id} tail_padding must be between 0 and 3 seconds.")


def build_pieces(
    transcript: dict[str, Any],
    plan: dict[str, Any],
    *,
    gap_threshold: float = 0.55,
    kept_edge: float = 0.09,
) -> list[dict[str, Any]]:
    """Map approved clips to source pieces after optional narration-gap compression."""
    duration = float(transcript.get("duration", 0))
    pieces: list[dict[str, Any]] = []
    output_cursor = 0.0
    for clip in plan.get("clips", []):
        selected = words_for_clip(transcript, clip["start_word"], clip["end_word"])
        source_start = max(0.0, float(clip["source_start"]))
        source_end = min(duration or float(clip["source_end"]), float(clip["source_end"]))
        if source_end <= source_start:
            raise ReelError(f"Clip {clip['id']} has an empty source range.")

        groups: list[list[dict[str, Any]]] = []
        if clip.get("pause_mode", "compress") == "preserve":
            groups = [selected]
        else:
            current = [selected[0]]
            for word in selected[1:]:
                previous = current[-1]
                if float(word["start"]) - float(previous["end"]) > gap_threshold:
                    groups.append(current)
                    current = [word]
                else:
                    current.append(word)
            groups.append(current)

        for group_index, group in enumerate(groups):
            if len(groups) == 1:
                piece_start = source_start
                piece_end = source_end
            else:
                piece_start = (
                    source_start
                    if group_index == 0
                    else max(source_start, float(group[0]["start"]) - kept_edge)
                )
                piece_end = (
                    source_end
                    if group_index == len(groups) - 1
                    else min(source_end, float(group[-1]["end"]) + kept_edge)
                )
            if piece_end <= piece_start:
                continue
            piece_duration = piece_end - piece_start
            piece = {
                "clip_id": clip["id"],
                "role": clip["role"],
                "layout": clip.get("layout", "center_crop"),
                "source_start": round(piece_start, 6),
                "source_end": round(piece_end, 6),
                "output_start": round(output_cursor, 6),
                "output_end": round(output_cursor + piece_duration, 6),
                "words": [],
            }
            for word in group:
                start = max(piece_start, float(word["start"]))
                end = min(piece_end, float(word["end"]))
                if end <= start:
                    continue
                piece["words"].append(
                    {
                        **word,
                        "output_start": round(output_cursor + start - piece_start, 6),
                        "output_end": round(output_cursor + end - piece_start, 6),
                        "clip_id": clip["id"],
                    }
                )
            pieces.append(piece)
            output_cursor += piece_duration
    if not pieces:
        raise ReelError("The edit plan produced no renderable pieces.")
    return pieces


def timeline_words(pieces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for piece in pieces:
        words.extend(piece["words"])
    return words


def expected_duration(pieces: list[dict[str, Any]]) -> float:
    return float(pieces[-1]["output_end"]) if pieces else 0.0


def resolve_source(transcript_path: str | Path, transcript: dict[str, Any]) -> Path:
    source = Path(str(transcript.get("source", ""))).expanduser()
    if not source.is_absolute():
        source = Path(transcript_path).resolve().parent / source
    source = source.resolve()
    if not source.exists():
        raise ReelError(f"Source video does not exist: {source}")
    return source
