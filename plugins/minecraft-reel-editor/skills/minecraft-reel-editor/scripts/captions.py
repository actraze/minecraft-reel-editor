#!/usr/bin/env python3
"""Generate Pixelify Sans ASS captions with the current word highlighted."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from common import (
    ReelError,
    build_pieces,
    load_json,
    timeline_words,
)


ACTIVE_ASS = "&H0055FFFF&"  # ASS uses BGR: Minecraft yellow #FFFF55
WHITE_ASS = "&H00FFFFFF&"


def ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{fraction:02d}"


def escape_ass(text: str) -> str:
    text = text.replace("\\", r"\\")
    text = text.replace("{", r"\{").replace("}", r"\}")
    return text.replace("\n", r"\N")


def phrase_groups(words: list[dict[str, Any]], maximum: int = 5) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    previous_clip: str | None = None
    for word in words:
        clip_id = str(word["clip_id"])
        if current and clip_id != previous_clip:
            groups.append(current)
            current = []
        current.append(word)
        previous_clip = clip_id
        punctuation_break = bool(re.search(r"[.!?;:]$", str(word["text"])))
        if len(current) >= maximum or punctuation_break:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def highlighted_phrase(group: list[dict[str, Any]], active_index: int) -> str:
    output: list[str] = []
    for index, word in enumerate(group):
        token = escape_ass(str(word["text"]).strip().upper())
        if index == active_index:
            token = rf"{{\c{ACTIVE_ASS}}}{token}{{\c{WHITE_ASS}}}"
        output.append(token)
    text = " ".join(output)
    return re.sub(r"\s+([,.;:!?])", r"\1", text)


def generate_ass(
    transcript: dict[str, Any],
    plan: dict[str, Any],
    *,
    font_name: str = "Pixelify Sans",
) -> str:
    pieces = build_pieces(transcript, plan)
    words = timeline_words(pieces)
    if not words:
        raise ReelError("No timeline words are available for captions.")
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "ScaledBorderAndShadow: yes",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Reel,{font_name},78,{WHITE_ASS},{ACTIVE_ASS},&H00101010,"
        "&H80000000,-1,0,0,0,100,100,1,0,1,6,2,2,90,90,330,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for group in phrase_groups(words):
        for index, word in enumerate(group):
            start = float(word["output_start"])
            if index + 1 < len(group):
                end = max(float(word["output_end"]), float(group[index + 1]["output_start"]))
            else:
                end = max(float(word["output_end"]), start + 0.12)
            end = max(end, start + 0.04)
            lines.append(
                "Dialogue: 0,"
                f"{ass_time(start)},{ass_time(end)},Reel,,0,0,0,,"
                f"{highlighted_phrase(group, index)}"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    transcript = load_json(args.transcript)
    plan = load_json(args.plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(generate_ass(transcript, plan), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReelError as error:
        raise SystemExit(str(error)) from error
