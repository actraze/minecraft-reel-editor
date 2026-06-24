from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    ROOT
    / "plugins"
    / "minecraft-reel-editor"
    / "skills"
    / "minecraft-reel-editor"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS))

from captions import generate_ass, phrase_groups  # noqa: E402
from common import (  # noqa: E402
    ReelError,
    build_pieces,
    clean_join,
    expected_duration,
    validate_selection,
)
from prepare_proposal import make_plan, proposal_markdown  # noqa: E402


def transcript_fixture(source: str = "/tmp/source.mp4") -> dict:
    words = [
        {"id": "w000001", "segment_id": "s0001", "start": 0.20, "end": 0.42, "text": "I"},
        {"id": "w000002", "segment_id": "s0001", "start": 0.44, "end": 0.68, "text": "built"},
        {"id": "w000003", "segment_id": "s0001", "start": 0.70, "end": 0.95, "text": "this."},
        {"id": "w000004", "segment_id": "s0002", "start": 1.80, "end": 2.02, "text": "It"},
        {"id": "w000005", "segment_id": "s0002", "start": 2.04, "end": 2.25, "text": "actually"},
        {"id": "w000006", "segment_id": "s0002", "start": 2.27, "end": 2.48, "text": "works!"},
    ]
    return {
        "schema_version": 1,
        "source": source,
        "language": "en",
        "duration": 3.0,
        "backend": "fixture",
        "model": "fixture",
        "segments": [],
        "words": words,
    }


def selection_fixture() -> dict:
    return {
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
                "rationale": "Direct setup.",
            },
            {
                "id": "payoff",
                "role": "payoff",
                "start_word": "w000004",
                "end_word": "w000006",
                "layout": "full_frame",
                "pause_mode": "preserve",
                "rationale": "Visible result.",
            },
        ],
        "omissions": ["Removed a failed take."],
    }


class CoreTests(unittest.TestCase):
    def test_clean_join_punctuation(self) -> None:
        self.assertEqual(
            clean_join([{"text": "Hello"}, {"text": "world!"}]),
            "Hello world!",
        )

    def test_plan_uses_only_selected_words(self) -> None:
        transcript = transcript_fixture()
        plan = make_plan(transcript, selection_fixture())
        self.assertEqual(plan["clips"][0]["text"], "I built this.")
        self.assertEqual(plan["clips"][1]["text"], "It actually works!")
        self.assertFalse(plan["approved"])
        self.assertLess(plan["estimated_duration_seconds"], 3)

    def test_duplicate_words_are_rejected(self) -> None:
        transcript = transcript_fixture()
        selection = selection_fixture()
        selection["clips"][1]["start_word"] = "w000003"
        with self.assertRaises(ReelError):
            validate_selection(transcript, selection)

    def test_long_plan_is_rejected(self) -> None:
        transcript = transcript_fixture()
        selection = selection_fixture()
        selection["target_duration_seconds"] = 0.5
        with self.assertRaises(ReelError):
            make_plan(transcript, selection)

    def test_gap_compression_builds_multiple_pieces(self) -> None:
        transcript = transcript_fixture()
        selection = selection_fixture()
        selection["clips"] = [
            {
                "id": "story",
                "role": "hook",
                "start_word": "w000001",
                "end_word": "w000006",
                "layout": "center_crop",
                "pause_mode": "compress",
            }
        ]
        plan = make_plan(transcript, selection)
        pieces = build_pieces(transcript, plan)
        self.assertEqual(len(pieces), 2)
        self.assertLess(expected_duration(pieces), 2)

    def test_captions_highlight_exact_words(self) -> None:
        transcript = transcript_fixture()
        plan = make_plan(transcript, selection_fixture())
        ass = generate_ass(transcript, plan)
        self.assertIn("PIXELIFY", ass.upper())
        self.assertIn("BUILT THIS.", ass)
        self.assertIn("ACTUALLY WORKS!", ass)
        self.assertIn("&H0055FFFF&", ass)

    def test_phrase_groups_do_not_cross_clip_boundaries(self) -> None:
        groups = phrase_groups(
            [
                {"text": "one", "clip_id": "a"},
                {"text": "two", "clip_id": "a"},
                {"text": "three", "clip_id": "b"},
            ]
        )
        self.assertEqual([[word["text"] for word in group] for group in groups], [["one", "two"], ["three"]])

    def test_proposal_contains_approval_gate(self) -> None:
        markdown = proposal_markdown(make_plan(transcript_fixture(), selection_fixture()))
        self.assertIn("not approved", markdown)
        self.assertIn("w000001", markdown)

    def test_json_round_trip_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "selection.json"
            path.write_text(json.dumps(selection_fixture()), encoding="utf-8")
            self.assertEqual(json.loads(path.read_text())["clips"][0]["id"], "hook")


if __name__ == "__main__":
    unittest.main()
