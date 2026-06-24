#!/usr/bin/env python3
"""Render representative source frames for guarded crop decisions."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from common import (
    ReelError,
    load_json,
    require_executable,
    resolve_source,
    run,
    save_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--columns", type=int, default=3)
    args = parser.parse_args()

    transcript = load_json(args.transcript)
    plan = load_json(args.plan)
    source = resolve_source(args.transcript, transcript)
    clips = plan.get("clips", [])
    if not clips:
        raise ReelError("Edit plan contains no clips.")
    if args.columns < 1:
        raise ReelError("--columns must be at least 1.")

    samples = [
        {
            "clip_id": clip["id"],
            "time": round((float(clip["source_start"]) + float(clip["source_end"])) / 2, 3),
            "layout": clip.get("layout", "center_crop"),
        }
        for clip in clips[:12]
    ]
    ffmpeg = require_executable("ffmpeg")
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    for sample in samples:
        command.extend(["-ss", str(sample["time"]), "-i", str(source)])

    cell_width, cell_height = 426, 240
    filters: list[str] = []
    labels: list[str] = []
    for index, sample in enumerate(samples):
        filters.append(
            f"[{index}:v]scale={cell_width}:{cell_height}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={cell_width}:{cell_height}:(ow-iw)/2:(oh-ih)/2:color=black"
            f"[cell{index}]"
        )
        labels.append(f"[cell{index}]")
    columns = min(args.columns, len(samples))
    rows = math.ceil(len(samples) / columns)
    layout = "|".join(
        f"{(index % columns) * cell_width}_{(index // columns) * cell_height}"
        for index in range(len(samples))
    )
    filters.append(
        "".join(labels)
        + f"xstack=inputs={len(samples)}:layout={layout}:fill=black[grid]"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[grid]",
            "-frames:v",
            "1",
            str(args.output),
        ]
    )
    run(command)
    save_json(
        args.output.with_suffix(".json"),
        {
            "schema_version": 1,
            "source": str(source),
            "columns": columns,
            "rows": rows,
            "samples": samples,
        },
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReelError as error:
        raise SystemExit(str(error)) from error
