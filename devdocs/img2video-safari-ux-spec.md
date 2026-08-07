<!-- VERSION$00076$ | Edited: 07/08 | TIME: 13:26 -->
# Img2Video Safari UX Spec

Canonical UX specification for `shortcuts/img2video/index.html`, the Safari-facing launcher that hands a `{filename, cmd}` payload to the `Run Img2Video in a-Shell` Shortcut.

This is a feature-completion spec, not a redesign brief. The existing synthwave palette, card surfaces, borders, typography, compact spacing, control sizes, iPhone-first layout, and sticky launch footer are the production visual system. Changes in this revision must reuse those primitives rather than introduce a broad redesign or global resizing pass.

## Overview

The page is a single scrollable form (`#form`) inside `<main>`, followed by a fixed `<footer>` launch bar. Live form state becomes one shell command line and is handed to the Shortcut through a `shortcuts://run-shortcut` URL.

## Section layout

Sections remain in this fixed order:

1. Preset
2. Source
3. Motion
4. Generation
5. Processing
6. Execution
7. Command Preview
8. Launch Shortcut (sticky footer, not a form section)

## Preset behavior

- The preset dropdown is populated from `presets.txt`, fetched at load time.
- Selecting a preset applies only the existing nine compact preset fields: `model`, `resolution`, `performance`, `fps`, `frames`, `priority`, `optimizations`, `interpolation`, `interpolationFps`.
- Seed is not part of the compact preset schema or preset matching. It is a separate per-run Generation value.
- "Custom" is a derived label, not a stored preset. There is no create/save/rename/delete preset UI.
- "Import settings.txt" may also import `seed`, but still does not import prompts, source selection, generation mode, combine-videos, max-parallel-tasks, playback preference, or output paths.

## Source behavior

- `Choose image` opens a native file picker; only the selected filename is handed onward.
- Once a filename is present, the button label switches to `Change image`.
- Editing the filename field directly clears any live preview that can no longer be trusted to match.

## Motion / multi-prompt model

Motion is an ordered list of prompt blocks matching the Python client's repeatable `--prompt` semantics.

- The section header shows `N prompt` / `N prompts`.
- Each prompt has Move up, Move down, and Delete actions.
- At least one prompt always remains.
- `+ Add prompt` appends and focuses a new prompt.
- Reordering changes execution and assembly order.
- Reset returns to one default prompt: `Static camera, subtle natural movement.`

### Generation mode (Chain / Parallel)

- Hidden with one prompt; visible with 2+ prompts.
- Chain → `--mode chain`.
- Parallel → `--mode parallel`.
- Default: Chain.

### Combine videos

- Hidden with one prompt; visible with 2+ prompts.
- ON → `--combine-videos`; OFF → `--no-combine-videos`.
- Default: ON.

### Max parallel tasks

- Visible only with 2+ prompts in Parallel mode.
- Range + number control, 1–6.
- Default: 6.

## Generation controls

Generation contains:

- Model
- Resolution
- Performance
- Request FPS
- Requested frames
- **Seed**
- Queue priority

FPS/frame limits remain model-specific and use the existing range/number controls.

### Seed

- Seed is optional; blank means no explicit `--seed` is emitted.
- It uses the same compact control sizing and typography as the existing Generation inputs.
- A clearly labeled **Randomize** action sits beside it.
- Entered values must fit the Python client's signed 64-bit range.
- Randomize generates a signed 64-bit value using Web Crypto when available.
- Seed is persisted in local working state and may be imported from `settings.txt`.
- Seed is not added to `presets.txt` and does not change which preset is considered active.

## Processing controls

Unchanged: Optimizations and Interpolation toggles plus interpolation target values `24`, `25`, `30`, `50`, `60`.

- The interpolation target is disabled visually and functionally while Interpolation is OFF.
- Its selected preference remains stored and returns when Interpolation is turned back ON.

## Execution controls

Execution stays intentionally minimal and contains **only**:

- **Play result when finished** → real Python flag `--sound`.

Do not add an output-directory picker, output-folder field, or `--open-video` control.

When a multi-prompt Parallel run has Combine videos OFF, there are several independent output files and the Python client has no single final result to play. In that configuration the Play-result control is disabled and `--sound` is omitted. Its checked preference may remain stored so it becomes effective again when the configuration returns to a single playable result.

The Safari UI omits `--output`; the Python client's own precedence still applies: a configured `output=` in `artworks_settings.txt` may supply the path, otherwise the client falls back to `<photo-name>_video.mp4` beside the input.

## Command Preview

Command Preview is intentionally secondary to the main controls.

- It starts **collapsed on every page load**.
- Tapping its header toggles expanded/collapsed state.
- Expanded state contains:
  - generated command;
  - Copy command;
  - Reset.
- The expanded/collapsed state is not persisted to `localStorage`.
- The preview uses shell continuation markers between display lines. This keeps the readable multi-line representation executable if a user must press-and-hold copy it because the Clipboard API is unavailable.
- `Copy command` still copies the canonical single-line command.
- Launch also uses that same single-line command.
- Validation errors may expand the panel automatically so the existing inline error toast remains visible.

## Launch flow

Submitting validates:

- filename exists;
- every prompt is non-empty;
- Seed is blank or a valid signed 64-bit integer.

It then navigates to `shortcuts://run-shortcut?...` with `{version, filename, cmd}`.

## Visibility rules

Always visible: Preset, Source, Motion, Generation, Processing, Execution, Command Preview header, sticky Launch footer.

| Condition | Generation mode | Combine videos | Max parallel tasks | Play result |
|---|---|---|---|---|
| 1 prompt | hidden | hidden | hidden | available |
| 2+ prompts, Chain | shown | shown | hidden | available |
| 2+ prompts, Parallel + Combine ON | shown | shown | shown | available |
| 2+ prompts, Parallel + Combine OFF | shown | shown | shown | disabled |

Command Preview body is hidden until expanded.

## Reset behavior

Reset clears the current working-state key plus known legacy keys, restores defaults (including blank Seed and one default prompt), and re-fetches `presets.txt`. Reset does not require a page reload.

## Mobile UX principles

- Keep the existing single-column `main{width:min(760px,100%)}` iPhone-first layout and safe-area padding.
- Keep existing synthwave colors, cards, borders, typography, spacing, and control sizing.
- Keep Launch Shortcut fixed at the bottom with the READY/status pill.
- New Seed/Randomize and Command Preview interactions must reuse existing control primitives rather than trigger a global CSS resizing pass.
