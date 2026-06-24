# Minecraft Reel Editor

A shareable Codex plugin that turns a messy narrated Minecraft recording into an approved vertical reel under 30 seconds.

It transcribes locally, proposes an exact-word edit using the best takes, waits for approval, then uses FFmpeg to cut the video, tighten pauses, frame it vertically, and burn pixel-style captions.

## Install

Prerequisites:

- Codex CLI
- Python 3.10 or newer
- FFmpeg with `ffprobe`, `libx264`, and `libass`

Install directly from GitHub:

```bash
codex plugin marketplace add actraze/minecraft-reel-editor
codex plugin add minecraft-reel-editor@minecraft-reels
```

Start a new Codex thread, then invoke:

```text
Use $minecraft-reel-editor on /absolute/path/to/my-recording.mp4
```

The first run creates an isolated local transcription environment. Apple Silicon uses MLX Whisper; Windows, Linux, and other Macs use faster-whisper. Model files download locally and footage is not uploaded.

## How approval works

The plugin first produces:

- an exact proposed spoken script;
- selected source timestamps and take choices;
- expected duration;
- crop decisions and omissions.

It will not render until you explicitly approve that proposal. The render script also refuses any plan whose approval flag has not been set.

## Output

- `final-reel.mp4`
- `captions.ass`
- `approved-edit-plan.json`
- `transcript.json`
- `edit-report.md`

Defaults are 1080×1920 H.264/AAC, at the source frame rate capped at 60 FPS.

## Develop

```bash
python -m unittest discover -s tests -v
python /path/to/skill-creator/scripts/quick_validate.py \
  plugins/minecraft-reel-editor/skills/minecraft-reel-editor
python /path/to/plugin-creator/scripts/validate_plugin.py \
  plugins/minecraft-reel-editor
```

Sample footage and generated media are intentionally ignored by Git.

## License

Code is MIT licensed. Pixelify Sans is bundled under the SIL Open Font License; see its adjacent `OFL.txt`.
