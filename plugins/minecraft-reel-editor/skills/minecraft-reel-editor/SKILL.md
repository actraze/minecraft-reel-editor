---
name: minecraft-reel-editor
description: Edit long, messy narrated Minecraft gameplay recordings into polished English vertical reels under 30 seconds. Use when Codex must locally transcribe a Minecraft video, identify mistakes and repeated takes, rearrange only words actually spoken into a hook-setup-payoff script, obtain explicit approval, then render cuts, tightened pauses, guarded vertical framing, and pixel-style captions with FFmpeg.
---

# Minecraft Reel Editor

Turn one narrated Minecraft recording with false starts, mistakes, and retakes into one coherent reel. Keep every spoken word grounded in the source transcript. Never invent, paraphrase, or synthesize dialogue.

## Required workflow

1. Locate this skill directory and use its `scripts/` and `assets/` paths directly.
2. Run `python scripts/bootstrap.py`. If it creates a runtime environment, use the Python path it prints for transcription.
3. Run:

   ```bash
   <runtime-python> scripts/transcribe.py INPUT_VIDEO --output-dir WORK_DIR
   ```

4. Read `references/minecraft-reel-scripting.md`, `WORK_DIR/transcript.md`, and `WORK_DIR/transcript.json`.
5. Analyze the transcript for false starts, corrections, repeated takes, weak tangents, and the strongest single hook-to-payoff story.
6. Write `WORK_DIR/selection.json` using `references/formats.md`. Select complete word ranges by word ID. Reorder ranges when it improves the story.
7. Run:

   ```bash
   python scripts/prepare_proposal.py \
     --transcript WORK_DIR/transcript.json \
     --selection WORK_DIR/selection.json \
     --output-dir WORK_DIR
   ```

8. Generate the crop review sheet:

   ```bash
   python scripts/contact_sheet.py \
     --plan WORK_DIR/edit-plan.json \
     --transcript WORK_DIR/transcript.json \
     --output WORK_DIR/contact-sheet.png
   ```

9. Inspect the contact sheet. Keep `center_crop` unless important side UI, chat, inventory, coordinates, text, or an off-center build would be lost. Change those clips to `full_frame`, regenerate the proposal, and show the user:
   - the exact proposed script;
   - the cut table and take choices;
   - expected duration;
   - crop choices and omissions.
10. Stop. Do not render until the user explicitly approves this proposal.
11. After explicit approval, run:

    ```bash
    python scripts/mark_approved.py WORK_DIR/edit-plan.json --approved-by USER
    python scripts/render.py \
      --plan WORK_DIR/edit-plan.json \
      --transcript WORK_DIR/transcript.json \
      --output-dir OUTPUT_DIR
    ```

12. Report the final reel, captions, approved manifest, transcript, and edit report.

## Editorial invariants

- Use only contiguous word ranges from the transcript. Do not type rewritten dialogue into the plan.
- Prefer the cleanest complete take. Do not splice individual words merely to manufacture a sentence.
- Target one idea under 30 seconds: hook, necessary setup, payoff.
- Preserve chronology only when it helps clarity; reordered complete phrases are allowed.
- Use `pause_mode: compress` for ordinary narration and `pause_mode: preserve` when an in-game action or comedic beat needs the original timing.
- Treat Whisper timestamps as edit anchors. Preserve protective padding around speech.
- Preserve the inseparable source mix. Do not claim to isolate, duck, or remix narration and gameplay audio.
- Default to a stable center crop. Never introduce continuously tracking or panning crops.
- Use `full_frame` over a blurred background when center cropping hides information required to understand the clip.
- Reject a render when `edit-plan.json` is not explicitly approved.

## Resources

- Read `references/minecraft-reel-scripting.md` before proposing an edit.
- Read `references/formats.md` when creating or debugging transcript, selection, or plan files.
- Use `scripts/captions.py` independently when only an ASS caption file is needed.
- Use the bundled Pixelify Sans font from `assets/`.
