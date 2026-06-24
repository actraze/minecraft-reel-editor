from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = (
    ROOT
    / "plugins"
    / "minecraft-reel-editor"
    / "skills"
    / "minecraft-reel-editor"
)
SCRIPTS = SKILL / "scripts"


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class RenderTests(unittest.TestCase):
    def run_script(self, name: str, *arguments: str, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / name), *arguments],
            text=True,
            capture_output=True,
        )
        if expect_success and result.returncode:
            self.fail(f"{name} failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
        return result

    def test_synthetic_end_to_end_render(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.mp4"
            subprocess.run(
                [
                    shutil.which("ffmpeg"),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=640x360:rate=24:duration=3",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:sample_rate=48000:duration=3",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(source),
                ],
                check=True,
            )
            transcript = {
                "schema_version": 1,
                "source": str(source),
                "language": "en",
                "duration": 3.0,
                "backend": "fixture",
                "model": "fixture",
                "segments": [],
                "words": [
                    {"id": "w000001", "segment_id": "s0001", "start": 0.20, "end": 0.42, "text": "I"},
                    {"id": "w000002", "segment_id": "s0001", "start": 0.44, "end": 0.68, "text": "built"},
                    {"id": "w000003", "segment_id": "s0001", "start": 0.70, "end": 0.95, "text": "this."},
                    {"id": "w000004", "segment_id": "s0002", "start": 1.80, "end": 2.02, "text": "It"},
                    {"id": "w000005", "segment_id": "s0002", "start": 2.04, "end": 2.25, "text": "works!"},
                ],
            }
            selection = {
                "schema_version": 1,
                "target_duration_seconds": 3,
                "clips": [
                    {
                        "id": "hook",
                        "role": "hook",
                        "start_word": "w000001",
                        "end_word": "w000003",
                        "layout": "center_crop",
                        "pause_mode": "compress",
                    },
                    {
                        "id": "payoff",
                        "role": "payoff",
                        "start_word": "w000004",
                        "end_word": "w000005",
                        "layout": "full_frame",
                        "pause_mode": "preserve",
                    },
                ],
                "omissions": [],
            }
            transcript_path = root / "transcript.json"
            selection_path = root / "selection.json"
            transcript_path.write_text(json.dumps(transcript), encoding="utf-8")
            selection_path.write_text(json.dumps(selection), encoding="utf-8")

            self.run_script(
                "prepare_proposal.py",
                "--transcript",
                str(transcript_path),
                "--selection",
                str(selection_path),
                "--output-dir",
                str(root),
            )
            contact = root / "contact.png"
            self.run_script(
                "contact_sheet.py",
                "--plan",
                str(root / "edit-plan.json"),
                "--transcript",
                str(transcript_path),
                "--output",
                str(contact),
            )
            self.assertTrue(contact.exists())

            available_filters = subprocess.run(
                [shutil.which("ffmpeg"), "-hide_banner", "-filters"],
                text=True,
                capture_output=True,
                check=False,
            ).stdout
            if " ass " not in available_filters and " subtitles " not in available_filters:
                self.skipTest("This FFmpeg build lacks the required libass subtitle filter")

            refused = self.run_script(
                "render.py",
                "--plan",
                str(root / "edit-plan.json"),
                "--transcript",
                str(transcript_path),
                "--output-dir",
                str(root / "rendered"),
                expect_success=False,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("not been explicitly approved", refused.stderr)

            self.run_script(
                "mark_approved.py",
                str(root / "edit-plan.json"),
                "--approved-by",
                "test-user",
            )
            output_dir = root / "rendered"
            self.run_script(
                "render.py",
                "--plan",
                str(root / "edit-plan.json"),
                "--transcript",
                str(transcript_path),
                "--output-dir",
                str(output_dir),
                "--preset",
                "ultrafast",
                "--crf",
                "28",
            )
            final_video = output_dir / "final-reel.mp4"
            self.assertTrue(final_video.exists())
            probe = subprocess.run(
                [
                    shutil.which("ffprobe"),
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(final_video),
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            media = json.loads(probe.stdout)
            video = next(stream for stream in media["streams"] if stream["codec_type"] == "video")
            self.assertEqual((video["width"], video["height"]), (1080, 1920))
            self.assertEqual(video["codec_name"], "h264")
            self.assertLess(float(media["format"]["duration"]), 3.25)
            self.assertTrue((output_dir / "captions.ass").exists())
            self.assertTrue((output_dir / "approved-edit-plan.json").exists())
            self.assertTrue((output_dir / "edit-report.md").exists())


if __name__ == "__main__":
    unittest.main()
