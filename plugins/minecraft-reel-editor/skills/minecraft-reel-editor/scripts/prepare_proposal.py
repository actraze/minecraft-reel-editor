#!/usr/bin/env python3
"""Create an exact-word edit plan and readable approval proposal."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import (
    ReelError,
    build_pieces,
    clean_join,
    expected_duration,
    format_time,
    load_json,
    save_json,
    validate_selection,
    words_for_clip,
)


def make_plan(transcript: dict[str, Any], selection: dict[str, Any]) -> dict[str, Any]:
    validate_selection(transcript, selection)
    source_duration = float(transcript["duration"])
    clips: list[dict[str, Any]] = []
    for selected in selection["clips"]:
        words = words_for_clip(transcript, selected["start_word"], selected["end_word"])
        head_padding = float(selected.get("head_padding", 0.08))
        tail_padding = float(selected.get("tail_padding", 0.08))
        clips.append(
            {
                "id": selected["id"],
                "role": selected["role"],
                "start_word": selected["start_word"],
                "end_word": selected["end_word"],
                "text": clean_join(words),
                "source_start": round(max(0, float(words[0]["start"]) - head_padding), 3),
                "source_end": round(
                    min(source_duration, float(words[-1]["end"]) + tail_padding),
                    3,
                ),
                "layout": selected.get("layout", "center_crop"),
                "pause_mode": selected.get("pause_mode", "compress"),
                "rationale": str(selected.get("rationale", "")).strip(),
            }
        )
    plan: dict[str, Any] = {
        "schema_version": 1,
        "source": transcript["source"],
        "transcript_backend": transcript["backend"],
        "transcript_model": transcript["model"],
        "target_duration_seconds": float(selection.get("target_duration_seconds", 30)),
        "approved": False,
        "approval": None,
        "clips": clips,
        "omissions": selection.get("omissions", []),
        "render": {
            "width": 1080,
            "height": 1920,
            "max_fps": 60,
            "video_codec": "libx264",
            "audio_codec": "aac",
            "caption_font": "Pixelify Sans",
            "caption_active_color": "#FFFF55",
        },
    }
    pieces = build_pieces(transcript, plan)
    duration = expected_duration(pieces)
    target = float(plan["target_duration_seconds"])
    if duration > target + 0.001:
        raise ReelError(
            f"Estimated duration {duration:.2f}s exceeds the {target:.2f}s target. "
            "Shorten the selection before requesting approval."
        )
    plan["estimated_duration_seconds"] = round(duration, 3)
    plan["render_piece_count"] = len(pieces)
    return plan


def proposal_markdown(plan: dict[str, Any]) -> str:
    script = " ".join(clip["text"] for clip in plan["clips"])
    lines = [
        "# Minecraft reel edit proposal",
        "",
        "## Proposed exact spoken script",
        "",
        f"> {script}",
        "",
        f"**Estimated rendered duration:** {plan['estimated_duration_seconds']:.2f} seconds",
        "",
        "## Cut table",
        "",
        "| Order | Role | Source | Word range | Layout | Pauses | Exact retained words |",
        "|---:|---|---|---|---|---|---|",
    ]
    for number, clip in enumerate(plan["clips"], start=1):
        exact = clip["text"].replace("|", "\\|")
        lines.append(
            f"| {number} | {clip['role']} | "
            f"{format_time(clip['source_start'])}–{format_time(clip['source_end'])} | "
            f"`{clip['start_word']}–{clip['end_word']}` | "
            f"`{clip['layout']}` | `{clip['pause_mode']}` | {exact} |"
        )
        if clip.get("rationale"):
            lines.append(f"|  |  |  |  |  |  | _Why: {clip['rationale']}_ |")
    lines.extend(["", "## Omissions", ""])
    omissions = plan.get("omissions") or []
    if omissions:
        lines.extend(f"- {item}" for item in omissions)
    else:
        lines.append("- No omission notes supplied.")
    lines.extend(
        [
            "",
            "## Approval gate",
            "",
            "This plan is **not approved**. Rendering must not begin until the user explicitly accepts it.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    transcript = load_json(args.transcript)
    selection = load_json(args.selection)
    plan = make_plan(transcript, selection)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    save_json(args.output_dir / "edit-plan.json", plan)
    (args.output_dir / "proposal.md").write_text(
        proposal_markdown(plan),
        encoding="utf-8",
    )
    print(args.output_dir / "proposal.md")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReelError as error:
        raise SystemExit(str(error)) from error
