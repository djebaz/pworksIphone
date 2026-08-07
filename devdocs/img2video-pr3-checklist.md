<!-- VERSION$00070$ | Edited: 07/08 | TIME: 10:45 -->
# Img2Video Safari Multi-Prompt/Execution — Acceptance Checklist

Tracks the acceptance criteria for the PR that added multi-prompt Motion controls, the Execution section, and this set of devdocs to `shortcuts/img2video/index.html`.

| # | Criterion | Status |
|---|---|---|
| 1 | UI keeps the same visual design language and mobile compactness | Done — no new fonts, colors, or layout primitives; new controls reuse `.field`, `.switchrow`, `.segment`, `.btn`, `.range` |
| 2 | Motion section supports multiple prompts as ordered items | Done — `promptList` array, one `.promptitem` per entry |
| 3 | Users can add, reorder, and delete prompts | Done — `+ Add prompt`, `↑ Move up` / `↓ Move down` / `✕ Delete` per prompt |
| 4 | Chain/Parallel appears only for 2+ prompts | Done — `updateMotionVisibility()` |
| 5 | Combine Videos appears only for 2+ prompts | Done — `updateMotionVisibility()` |
| 6 | Max Parallel Tasks appears only for Parallel with 2+ prompts | Done — `updateMotionVisibility()` |
| 7 | Processing keeps interpolation target values 24/25/30/50/60 | Done — unchanged from prior UI |
| 8 | Interpolation target enabled only when interpolation is ON | Done — unchanged from prior UI (`applyInterpolationState`) |
| 9 | Execution section exposes output directory and play-result-when-finished | Deviated — `#playOnFinish` only. Output directory was dropped at the user's request once it was clear iOS Safari can't back a real folder picker (see judgment calls below); `--output` is always omitted now |
| 10 | Command Preview reflects all these options correctly | Done — see `img2video-execution-model.md`; verified in a headless browser (add/reorder/delete prompts, mode switch, sound flag, empty-prompt submit validation, preset-apply leaves prompts/filename untouched, reset) |
| 11 | No create/save/delete preset feature exists | Done — dropdown only lists built-in `presets.txt` entries; "Custom" is derived, not stored |
| 12 | Devdocs added under `devdocs/` | Done — `img2video-safari-ux-spec.md`, `img2video-presets-settings-contract.md`, `img2video-execution-model.md`, this checklist |
| 13 | Preset/settings/local-state architecture remains unchanged | Done — presets and settings-import still touch only the nine generation/processing fields; motion and execution fields are explicitly out of scope (documented in the settings contract doc) |

## Notable judgment calls (documented, not silent)

- The spec's Execution section named a `--open-video` flag for "Play result when finished." `app/img2video_iphone.py` has no such flag; its actual play-on-completion flag is `-s`/`--sound`. The UI sends `--sound` and labels it as such rather than emitting a flag the client doesn't understand.
- Output directory was initially implemented as a text field (omit `--output` when blank, join a given directory with the fixed filename `img2video_output.mp4` when set) and then **removed entirely** after review: iOS Safari has no API that lets a page open a native folder picker and return a real filesystem path (no File System Access API, no working `webkitdirectory`), so a manually-typed field would have looked like a picker without behaving like one. `--output` is now always omitted; the client's own default (`<photo-name>_video.mp4` beside the source image) applies. Real folder selection, if wanted later, belongs in the Shortcut itself, which does have genuine Files access.
- Max Parallel Tasks defaults to 6 in the UI, matching `app/artworks_settings.example.txt`'s `maxParallelTasks=6`, even though the bare Python client's own argparse fallback (absent any settings file) is 3.
- The Command Preview panel wraps one argument per line for readability. This is a display-only transform — `Copy command` and the actual Shortcut hand-off both use the single-line functional command, so nothing about execution semantics changed.
