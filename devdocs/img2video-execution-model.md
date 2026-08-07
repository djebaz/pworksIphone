<!-- VERSION$00063$ | Edited: 07/08 | TIME: 10:27 -->
# Img2Video Execution Model — UI State → CLI

This document explains how the Safari UI's live form state becomes the exact command line handed to `app/img2video_iphone.py`, and from there to the Shortcut.

## Current UI state

The UI keeps one in-memory state object (`state()` in `index.html`), rebuilt from the DOM on every input/change event:

```text
imagePath, prompts[], model, resolution, performance, fps, frames, priority,
optimizations, interpolation, interpolationFps,
generationMode, combineVideos, maxParallelTasks,
outputDir, playOnFinish
```

`prompts` is an ordered array of strings — the ordered prompt list from the Motion section, sanitized (newlines collapsed to spaces, trimmed) at read time. Everything else is a single scalar sourced from the matching form control.

## CLI generation

`command(state)` builds one flat argv-style string in this fixed order:

1. `python <script path>`
2. One `--prompt '<text>'` per entry in `prompts`, in list order
3. `--model`, `--resolution`, `--performance`, `--fps`, `--frames`, `--priority`
4. `--optimizations`/`--no-optimizations`, `--interpolation`/`--no-interpolation`
5. `--interpolate <target>` — only when `interpolation` is true
6. `--mode`, `--combine-videos`/`--no-combine-videos`, `--max-parallel-tasks` — only when `prompts.length > 1` (and `--max-parallel-tasks` only when `generationMode === "parallel"`)
7. `--output <dir>/img2video_output.mp4` — only when `outputDir` is non-empty
8. `--sound` — only when `playOnFinish` is true

The **Command Preview** panel renders the same argument groups one per line for readability, but that formatting is display-only. The value actually copied by "Copy command" and actually sent to the Shortcut (as the `cmd` field of the launch payload) is always the single space-joined line — no literal newlines are ever placed inside the executed command, so what a-Shell runs is identical either way.

## Prompt list encoding

Each prompt becomes its own `--prompt` argument, shell-quoted with the existing `quote()` helper (POSIX single-quote escaping). This matches `img2video_iphone.py`'s `--prompt` argument, which uses `action="append"` — the Python client already supports and expects repeated `--prompt` flags, and treats their order as both task order and, in chain/combine mode, assembly order (`app/img2video_iphone.py`, prompt-order docstring around the multi-prompt argument group). The UI does not invent this behavior; it exposes a capability the client already had.

## Chain mode

`--mode chain`. Sent whenever there are 2+ prompts and the Generation-mode segmented control is set to Chain (the default). Each prompt's task starts from the final frame of the previous prompt's generated result.

## Parallel mode

`--mode parallel`. Sent whenever there are 2+ prompts and Generation mode is set to Parallel. Each prompt's task starts independently from the original source image.

`--mode` is omitted entirely for a single prompt — the flag is only meaningful once there is more than one task to sequence or parallelize.

## Combine videos

`--combine-videos` / `--no-combine-videos`. Sent whenever there are 2+ prompts, regardless of chain/parallel mode. ON (the default) assembles every completed task's video into one sequence in prompt order; OFF leaves the outputs as separate files.

## Max parallel tasks

`--max-parallel-tasks <1-6>`. Sent only when there are 2+ prompts **and** Generation mode is Parallel — it has no effect in chain mode, so the UI never sends it there. Range and default (6) match `app/artworks_settings.example.txt`'s `maxParallelTasks=6`; the bare Python client's own fallback (when no settings file supplies a value) is 3.

## Execution-only settings

Two fields never influence the generation request payload sent to ArtWorks.ai — they only affect how the local run behaves:

- **Output directory** → `--output <dir>/img2video_output.mp4`, omitted when blank. When omitted, `img2video_iphone.py` falls back to its own default of `<photo-name>_video.mp4` saved beside the source image. When set, the UI joins the given directory with the fixed filename `img2video_output.mp4` (matching the previous Safari UI's hardcoded output convention) rather than requiring the user to type a full file path.
- **Play result when finished** → `--sound` (the client's actual flag, also spelled `-s`; there is no `--open-video` flag). Plays the completed video locally after a successful generation run.

Both are excluded from `presets.txt` and from "Import settings.txt" — see `img2video-presets-settings-contract.md` for why.

## Shortcut hand-off

The final payload sent via `shortcuts://run-shortcut?...&text=<payload>` is:

```json
{"version": 1, "filename": "<basename only>", "cmd": "<single-line command from above>"}
```

The Shortcut (`Run Img2Video in a-Shell`, reconstructed in `devdocs/shortcut/README.md`) resolves `filename` to a real file in Files/Photos, changes into the a-Shell "File Provider Storage" directory, appends the resolved path to `cmd`, and runs the result as one a-Shell command. Nothing in the Shortcut depends on a fixed output path, so making `--output` optional in the UI does not change anything on the Shortcut side.
