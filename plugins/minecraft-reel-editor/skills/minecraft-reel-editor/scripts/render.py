#!/usr/bin/env python3
"""Render an explicitly approved Minecraft reel edit plan with FFmpeg."""

from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path
from typing import Any

from captions import generate_ass
from common import (
    ReelError,
    build_pieces,
    expected_duration,
    has_audio,
    load_json,
    media_duration,
    parse_fps,
    probe_media,
    require_executable,
    resolve_source,
    run,
    save_json,
    video_stream,
)


def filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def copy_if_different(source: Path, destination: Path) -> None:
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)


def build_filter(
    pieces: list[dict[str, Any]],
    *,
    captions_path: Path,
    fonts_dir: Path,
    fps: float,
) -> str:
    count = len(pieces)
    filters: list[str] = []
    if count == 1:
        video_sources = ["[0:v]"]
        audio_sources = ["[0:a]"]
    else:
        video_labels = "".join(f"[vsrc{i}]" for i in range(count))
        audio_labels = "".join(f"[asrc{i}]" for i in range(count))
        filters.append(f"[0:v]split={count}{video_labels}")
        filters.append(f"[0:a]asplit={count}{audio_labels}")
        video_sources = [f"[vsrc{i}]" for i in range(count)]
        audio_sources = [f"[asrc{i}]" for i in range(count)]

    for index, piece in enumerate(pieces):
        start = float(piece["source_start"])
        end = float(piece["source_end"])
        base = (
            f"{video_sources[index]}trim=start={start:.6f}:end={end:.6f},"
            "setpts=PTS-STARTPTS,settb=AVTB"
        )
        if piece["layout"] == "full_frame":
            filters.append(base + f"[vbase{index}]")
            filters.append(f"[vbase{index}]split=2[vbg{index}][vfg{index}]")
            filters.append(
                f"[vbg{index}]scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,boxblur=20:2[bg{index}]"
            )
            filters.append(
                f"[vfg{index}]scale=1080:1920:force_original_aspect_ratio=decrease,"
                f"setsar=1[fg{index}]"
            )
            filters.append(
                f"[bg{index}][fg{index}]overlay=(W-w)/2:(H-h)/2,"
                f"setsar=1[v{index}]"
            )
        else:
            filters.append(
                base
                + ",scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,setsar=1[v{index}]"
            )
        filters.append(
            f"{audio_sources[index]}atrim=start={start:.6f}:end={end:.6f},"
            f"asetpts=PTS-STARTPTS,aresample=48000:async=1:first_pts=0[a{index}]"
        )

    if count == 1:
        video_concat = "[v0]"
        audio_concat = "[a0]"
    else:
        concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(count))
        filters.append(f"{concat_inputs}concat=n={count}:v=1:a=1[vjoined][ajoined]")
        video_concat = "[vjoined]"
        audio_concat = "[ajoined]"

    filters.append(
        f"{video_concat}ass=filename='{filter_path(captions_path)}':"
        f"fontsdir='{filter_path(fonts_dir)}',"
        f"fps={fps:.6f},format=yuv420p[vfinal]"
    )
    filters.append(
        f"{audio_concat}loudnorm=I=-16:TP=-1.5:LRA=11[afinal]"
    )
    return ";\n".join(filters)


def report_markdown(
    plan: dict[str, Any],
    source: Path,
    output: Path,
    pieces: list[dict[str, Any]],
    final_probe: dict[str, Any],
) -> str:
    stream = video_stream(final_probe)
    lines = [
        "# Minecraft reel edit report",
        "",
        f"- Source: `{source}`",
        f"- Output: `{output}`",
        f"- Approved by: `{plan['approval']['approved_by']}`",
        f"- Approved at: `{plan['approval']['approved_at']}`",
        f"- Retained clips: {len(plan['clips'])}",
        f"- Render pieces after pause compression: {len(pieces)}",
        f"- Final duration: {media_duration(final_probe):.2f} seconds",
        f"- Frame: {stream['width']}×{stream['height']}",
        f"- Video codec: `{stream['codec_name']}`",
        "",
        "## Retained script",
        "",
        "> " + " ".join(clip["text"] for clip in plan["clips"]),
        "",
        "## Clip decisions",
        "",
    ]
    for clip in plan["clips"]:
        lines.append(
            f"- **{clip['id']}** ({clip['role']}): `{clip['layout']}`, "
            f"`{clip['pause_mode']}` — {clip['text']}"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--preset", default="medium")
    args = parser.parse_args()

    plan = load_json(args.plan)
    transcript = load_json(args.transcript)
    if plan.get("approved") is not True or not isinstance(plan.get("approval"), dict):
        raise ReelError("Render refused: edit-plan.json has not been explicitly approved.")
    if plan.get("source") != transcript.get("source"):
        raise ReelError("Plan and transcript refer to different source files.")
    pieces = build_pieces(transcript, plan)
    duration = expected_duration(pieces)
    target = float(plan.get("target_duration_seconds", 30))
    if duration > target + 0.001:
        raise ReelError(f"Render duration {duration:.2f}s exceeds target {target:.2f}s.")

    source = resolve_source(args.transcript, transcript)
    source_probe = probe_media(source)
    if not has_audio(source_probe):
        raise ReelError("The source video must contain the mixed narration/game audio track.")
    source_video = video_stream(source_probe)
    source_fps = parse_fps(source_video.get("avg_frame_rate") or source_video.get("r_frame_rate"))
    output_fps = min(float(plan.get("render", {}).get("max_fps", 60)), source_fps)
    output_fps = max(1.0, output_fps)

    ffmpeg = require_executable("ffmpeg")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    captions_path = args.output_dir / "captions.ass"
    captions_path.write_text(generate_ass(transcript, plan), encoding="utf-8")
    fonts_dir = Path(__file__).resolve().parent.parent / "assets"
    font = fonts_dir / "PixelifySans[wght].ttf"
    if not font.exists():
        raise ReelError(f"Bundled caption font is missing: {font}")

    final_output = args.output_dir / "final-reel.mp4"
    with tempfile.TemporaryDirectory(prefix="minecraft-reel-") as temporary:
        filter_script = Path(temporary) / "filter.txt"
        filter_script.write_text(
            build_filter(
                pieces,
                captions_path=captions_path,
                fonts_dir=fonts_dir,
                fps=output_fps,
            ),
            encoding="utf-8",
        )
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-filter_complex_script",
            str(filter_script),
            "-map",
            "[vfinal]",
            "-map",
            "[afinal]",
            "-c:v",
            "libx264",
            "-preset",
            args.preset,
            "-crf",
            str(args.crf),
            "-profile:v",
            "high",
            "-level",
            "4.2",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(final_output),
        ]
        run(command)

    final_probe = probe_media(final_output)
    final_video = video_stream(final_probe)
    if int(final_video["width"]) != 1080 or int(final_video["height"]) != 1920:
        raise ReelError("Rendered video does not have the required 1080×1920 frame.")
    if media_duration(final_probe) > target + 0.25:
        raise ReelError("Rendered video exceeds the target duration.")

    copy_if_different(args.plan, args.output_dir / "approved-edit-plan.json")
    copy_if_different(args.transcript, args.output_dir / "transcript.json")
    report = {
        "schema_version": 1,
        "source": str(source),
        "output": str(final_output),
        "approved": plan["approval"],
        "duration": round(media_duration(final_probe), 3),
        "width": int(final_video["width"]),
        "height": int(final_video["height"]),
        "video_codec": final_video["codec_name"],
        "source_fps": round(source_fps, 3),
        "output_fps": round(output_fps, 3),
        "selected_clip_count": len(plan["clips"]),
        "render_piece_count": len(pieces),
    }
    save_json(args.output_dir / "edit-report.json", report)
    (args.output_dir / "edit-report.md").write_text(
        report_markdown(plan, source, final_output, pieces, final_probe),
        encoding="utf-8",
    )
    print(final_output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReelError as error:
        raise SystemExit(str(error)) from error
