#!/usr/bin/env python3
"""Create an isolated local transcription runtime and verify media tools."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def cache_root() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "minecraft-reel-editor"


def candidate_pythons() -> list[list[str]]:
    candidates: list[list[str]] = []
    if os.name == "nt" and shutil.which("py"):
        candidates.extend([["py", "-3.12"], ["py", "-3.11"], ["py", "-3.10"]])
    for executable in ("python3.12", "python3.11", "python3.10", "python3", "python"):
        if shutil.which(executable):
            candidates.append([executable])
    candidates.append([sys.executable])
    return candidates


def choose_python() -> list[str]:
    seen: set[tuple[str, ...]] = set()
    fallbacks: list[list[str]] = []
    for candidate in candidate_pythons():
        key = tuple(candidate)
        if key in seen:
            continue
        seen.add(key)
        try:
            result = subprocess.run(
                candidate + ["-c", "import sys; print(sys.version_info.major, sys.version_info.minor)"],
                check=True,
                text=True,
                capture_output=True,
            )
            major, minor = map(int, result.stdout.strip().split())
        except (OSError, subprocess.CalledProcessError, ValueError):
            continue
        if major == 3 and 10 <= minor <= 13:
            return candidate
        if major == 3 and minor >= 9:
            fallbacks.append(candidate)
    if fallbacks:
        return fallbacks[0]
    raise RuntimeError("Python 3.10 or newer is required.")


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def backend_name() -> str:
    if sys.platform == "darwin" and platform.machine().lower() in {"arm64", "aarch64"}:
        return "mlx"
    return "faster"


def check_ffmpeg() -> dict[str, object]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    status: dict[str, object] = {
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "libx264": False,
        "libass": False,
    }
    if not ffmpeg or not ffprobe:
        return status
    encoders = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"],
        text=True,
        capture_output=True,
        check=False,
    )
    filters = subprocess.run(
        [ffmpeg, "-hide_banner", "-filters"],
        text=True,
        capture_output=True,
        check=False,
    )
    status["libx264"] = "libx264" in encoders.stdout
    status["libass"] = " ass " in filters.stdout or " subtitles " in filters.stdout
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Only report dependency status.")
    parser.add_argument("--reinstall", action="store_true", help="Reinstall the transcription package.")
    parser.add_argument("--runtime-dir", type=Path, default=cache_root() / "venv")
    args = parser.parse_args()

    ffmpeg_status = check_ffmpeg()
    selected_backend = backend_name()
    report = {
        "platform": sys.platform,
        "machine": platform.machine(),
        "backend": selected_backend,
        **ffmpeg_status,
    }
    if args.check:
        print(json.dumps(report, indent=2))
        return 0 if all(
            [
                report["ffmpeg"],
                report["ffprobe"],
                report["libx264"],
                report["libass"],
            ]
        ) else 1

    missing = [
        name
        for name in ("ffmpeg", "ffprobe")
        if not report[name]
    ]
    if missing:
        raise SystemExit(
            "Missing FFmpeg tools: "
            + ", ".join(missing)
            + ". Install FFmpeg, then rerun this script."
        )
    if not report["libx264"] or not report["libass"]:
        raise SystemExit("FFmpeg must include libx264 and libass/subtitles support.")

    runtime_dir = args.runtime_dir.expanduser().resolve()
    python_path = venv_python(runtime_dir)
    if not python_path.exists():
        runtime_dir.parent.mkdir(parents=True, exist_ok=True)
        selected_python = choose_python()
        subprocess.run(selected_python + ["-m", "venv", str(runtime_dir)], check=True)

    subprocess.run(
        [str(python_path), "-m", "pip", "install", "--upgrade", "pip"],
        check=True,
    )
    package = "mlx-whisper==0.4.3" if selected_backend == "mlx" else "faster-whisper==1.2.1"
    install = [str(python_path), "-m", "pip", "install"]
    if args.reinstall:
        install.append("--force-reinstall")
    subprocess.run(install + [package], check=True)

    print(
        json.dumps(
            {
                **report,
                "runtime_python": str(python_path),
                "package": package,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
