<!-- VERSION$00061$ | Edited: 07/08 | TIME: 10:25 -->
# Img2Video Safari UX Spec

Canonical UX specification for `shortcuts/img2video/index.html`, the Safari-facing launcher that hands a `{filename, cmd}` payload to the `Run Img2Video in a-Shell` Shortcut. This document describes the current, shipped behavior; if the UI and this spec ever disagree, treat the UI as a bug against this spec (or file a spec update alongside the fix) rather than assuming either side is silently authoritative.

This is a feature-completion spec, not a redesign brief. The synthwave palette, glassy `.card` panels, compact mobile spacing, segmented controls, amber toggle styling, and sticky footer CTA defined inline in `index.html` are the production stylesheet and are not touched by this document. `devdocs/references/styles.css` is reference material from an unrelated project and is not the production stylesheet.

## Overview

The page is a single scrollable form (`#form`) inside `<main>`, followed by a fixed `<footer>` launch bar. Every field's live value is combined into one shell command line, previewed at the bottom of the form, and shipped to the Shortcut as JSON via a `shortcuts://run-shortcut` URL on submit.

## Section layout

Sections appear in this fixed order and must not be reordered:

1. Preset
2. Source
3. Motion
4. Generation
5. Processing
6. Execution
7. Command Preview
8. Launch Shortcut (sticky footer, not a form section)

## Preset behavior

- The preset dropdown is populated from `presets.txt` (see `img2video-presets-settings-contract.md`), fetched at load time.
- Selecting a preset applies only the nine generation/processing fields (`model`, `resolution`, `performance`, `fps`, `frames`, `priority`, `optimizations`, `interpolation`, `interpolationFps`). It never touches the source image, filename, motion prompts, generation mode, combine-videos, max-parallel-tasks, output directory, or play-on-finish.
- "Custom" is a derived label, not a stored entry: whenever the current generation/processing fields don't exactly match any loaded preset, the dropdown shows "Custom" and the helper text reads "No preset matches current settings". There is no UI to create, save, rename, or delete a preset.
- "Import settings.txt" reads a local `key=value` file and applies only the same nine generation/processing keys it recognizes (see the settings contract doc for the exact key list). It does not import prompts, execution settings, or motion/multi-prompt fields, even though those keys exist in the real `artworks_settings.txt` consumed directly by the Python client.

## Source behavior

- `Choose image` opens a native file picker; the selected file's name is written into the filename field and only the filename (never image bytes or a full path) is sent onward — the Shortcut resolves the file in Files, then Photos.
- Once a filename is present, the button label switches to `Change image`.
- Editing the filename field directly clears any live image preview (since the preview can no longer be trusted to match).

## Motion / multi-prompt model

Motion replaces the old single-prompt textarea with an ordered list of prompt blocks, matching the Python client's `--prompt` (repeatable) and prompt-order-is-execution-order semantics.

- The section header shows a live count: "N prompt" / "N prompts".
- Each prompt block has a label (`Prompt 1`, `Prompt 2`, ...), a textarea, and three explicit action buttons: `↑ Move up`, `↓ Move down`, `✕ Delete`.
- `Move up` is disabled on the first prompt; `Move down` is disabled on the last; `Delete` is disabled whenever exactly one prompt remains — at least one prompt must always exist.
- `+ Add prompt` appends a new, empty prompt block and focuses its textarea.
- Reordering (`Move up` / `Move down`) changes the actual array order used to build the command, which is also the execution/assembly order sent to the Python client.
- On first load or after Reset, there is exactly one prompt, seeded with the default motion prompt (`Static camera, subtle natural movement.`).

### Generation mode (Chain / Parallel)

- Hidden when there is exactly one prompt.
- Shown as a two-way segmented control once there are 2+ prompts.
- **Chain**: each prompt starts from the final frame of the previous generated result (`--mode chain`).
- **Parallel**: each prompt starts independently from the original source image (`--mode parallel`).
- Default: Chain, matching the Python client's own default when `generationMode` is unset.

### Combine videos

- Hidden when there is exactly one prompt.
- Shown as a toggle once there are 2+ prompts, directly below Generation mode.
- ON assembles the generated results into one sequence in prompt order (`--combine-videos`); OFF keeps the outputs as separate files (`--no-combine-videos`).
- Default: ON.

### Max parallel tasks

- Shown only when there are 2+ prompts **and** Generation mode is Parallel; hidden in every other state, including Chain mode with 2+ prompts.
- A range + numeric field, styled like the Request FPS / Requested frames / Queue priority controls, bounded 1–6 (`--max-parallel-tasks`).
- Default: 6, matching the tracked example settings file (`app/artworks_settings.example.txt`); the bare Python client falls back to 3 only when no settings file supplies a value at all.

## Generation controls

Unchanged from the prior UI: Model, Resolution, Performance segmented controls; Request FPS, Requested frames, Queue priority range fields. FPS/frames bounds and their live range hints update automatically when the model changes (`applyModelLimits`), because Wan and LTX have different validated request ranges.

## Processing controls

Unchanged: `Optimizations` and `Interpolation` toggles (`--optimizations`/`--no-optimizations`, `--interpolation`/`--no-interpolation`). The interpolation target is a 5-way segmented control with the values `24`, `25`, `30`, `50`, `60` — the documented `interpolationFps` enum, not the request FPS.

- When `Interpolation` is OFF, the interpolation target control is visually dimmed and its inputs are disabled, but the previously selected target value is retained in state and reapplied the moment `Interpolation` is turned back ON.
- When `Interpolation` is ON, the target control is fully active.

## Execution controls

New section for local run preferences that are never part of a preset or `settings.txt` import:

- **Output directory (optional)**: a plain text field. Empty means the `--output` flag is omitted entirely, so the Python client falls back to its own default (`<photo-name>_video.mp4` beside the source image). A non-empty value is joined with the fixed output filename `img2video_output.mp4` and passed explicitly as `--output <dir>/img2video_output.mp4`.
- **Play result when finished**: an amber toggle, same visual language as every other switch. When ON it appends `--sound` (the Python client's actual play-on-completion flag, exposed as `-s`/`--sound`) to the generated command. There is no `--open-video` flag in the Python client; the UI's helper text names the real flag it sends.

## Command preview

- Rebuilt from the live form state on every change; nothing here is hand-typed.
- Multi-prompt runs render one repeated `--prompt '...'` argument per configured prompt, in list order, followed by the generation/processing flags, then (only for 2+ prompts) `--mode`, `--combine-videos`/`--no-combine-videos`, and (only in Parallel with 2+ prompts) `--max-parallel-tasks`, then the optional `--output` and `--sound` flags.
- The preview text wraps one argument group per line for readability. This is a *display-only* transform: the underlying command actually sent to the Shortcut (via Copy and via Launch) is always a single space-joined shell line — no real newlines are ever embedded in the executed command, so pasting it into a-Shell or letting the Shortcut run it behaves identically to a single-line command.
- `Copy command` copies that single-line functional command (not the multi-line display text) to the clipboard.
- `Reset` clears the persisted working state (`localStorage`), clears any legacy state/preset cache keys still lying around from earlier UI versions, reloads `presets.txt`, and restores every field — including the prompt list and Execution fields — to defaults.

## Launch flow

Submitting the form validates that a filename is present and that every configured prompt is non-empty, then navigates to `shortcuts://run-shortcut?...` with a JSON payload of `{version, filename, cmd}`, where `cmd` is the single-line functional command described above.

## Visibility rules (summary)

Always visible: Preset, Source, Motion, Generation, Processing, Execution, Command Preview, Launch footer.

Motion subcontrols:

| Condition | Generation mode | Combine videos | Max parallel tasks |
|---|---|---|---|
| 1 prompt | hidden | hidden | hidden |
| 2+ prompts, mode = Chain | shown | shown | hidden |
| 2+ prompts, mode = Parallel | shown | shown | shown |

Processing subcontrols: interpolation target is enabled only when `Interpolation` is ON; the selected value persists in state either way.

## Reset behavior

See Command preview above and `img2video-presets-settings-contract.md` for exactly which storage keys Reset clears and why.

## Mobile UX principles

- Single-column, `main{width:min(760px,100%)}` layout with safe-area-aware padding, designed for iPhone Safari first.
- All interactive controls keep a ≥32–48px min-height tap target (buttons, switches, range thumbs).
- The sticky footer keeps the primary CTA (`Launch Shortcut`) and a status pill on-screen regardless of scroll position.
- New Motion list controls (`Move up`/`Move down`/`Delete`) use explicit text+icon labels rather than icon-only buttons, since a compact icon alone would be ambiguous at this control density.
