<!-- VERSION$00069$ | Edited: 07/08 | TIME: 10:44 -->
# Img2Video Presets / Settings / Local-State Contract

This document explains the three configuration layers behind `shortcuts/img2video/index.html` and where each one's authority stops. It exists so the boundary between "preset library," "one-off settings import," and "current working UI state" stays intentional as the UI grows, instead of drifting field by field.

## Configuration layers

```text
presets.txt          → built-in preset library, generation/processing fields only, read-only in the UI
settings.txt import  → human-editable one-off import of the same generation/processing fields
localStorage          → current working UI state (everything the form can hold)
current UI state      → single source of truth used to generate the CLI command
```

There is no user-created, user-saved, or user-editable preset concept. That was explicitly removed from this project; do not reintroduce "Save as preset," "Delete preset," or similar controls.

## `presets.txt` format

Location: `shortcuts/img2video/presets.txt`, fetched by the Safari UI at load time (`PRESETS_URL`).

One preset per non-comment, non-blank line, pipe-delimited, exactly 10 columns:

```text
name|model|resolution|performance|fps|numFrames|priority|applyOptimizations|applyInterpolation|interpolationFps
```

- `name` must be non-empty and unique within the file.
- `model` must be `wan-2.2` or `ltx-2.3`; `resolution` one of `480p`/`720p`/`1080p`; `performance` one of `speed`/`quality`/`express`.
- `fps` and `numFrames` must fall inside that model's validated request range (`LIMITS` in the UI script, matching the Python client's model-specific limits).
- `priority` must be an integer 1–5; `interpolationFps` must be one of the documented enum values `24`, `25`, `30`, `50`, `60`.
- `applyOptimizations` / `applyInterpolation` are literal `true`/`false`.

Any line that fails these checks is skipped and counted; the UI reports how many valid presets loaded and how many lines were skipped, but never fails silently.

`presets.txt` intentionally cannot express a prompt, image, generation mode, combine-videos preference, max-parallel-tasks value, or play-on-finish preference — none of those are preset-scoped. See "What remains outside presets" below.

## `settings.txt` format

Two different things share this name and must not be confused:

1. **The Safari UI's "Import settings.txt" button.** It reads any local `key=value` text file the user picks and applies only the recognized generation/processing keys: `model`, `resolution`, `performance`, `fps`, `numFrames`, `priority`, `applyOptimizations`, `applyInterpolation`, `interpolationFps`. Unrecognized keys are counted as skipped, not applied. This mirrors the preset scope exactly — it is a one-off import of the same nine fields a preset can set, nothing more.
2. **The real `artworks_settings.txt`** consumed directly by `app/img2video_iphone.py` on the device (see `app/artworks_settings.example.txt`). That file is richer — it also carries `photo`, `promptFile`/`prompt`, `output`, `generationMode`, `combineVideos`, `maxParallelTasks`, polling/recovery tuning, and more. The Safari UI's importer is deliberately narrower than this file's full key set.

This is an intentional scope decision, not an oversight: the Safari UI's Preset section is documented as "Generation & processing only," and extending its import to prompts, execution, or multi-prompt fields would blur the same preset/local-state boundary this document exists to protect. If prompt- or execution-level import from a settings file is ever wanted, it should be a distinct, separately-labeled feature — not a silent expansion of "Import settings.txt."

## Preset matching

"Active preset" is derived, never stored. On every state change the UI compares the current values of the nine generation/processing fields against every loaded preset (`generationsEqual`); if one matches exactly, its name is shown, otherwise the dropdown shows "Custom" with helper text "No preset matches current settings." Applying a preset or an import always calls the same `applyGenerationFields` path, so both entry points guarantee they can only ever change generation/processing fields.

## What a preset may change

Exactly these nine fields, and nothing else:

```text
model, resolution, performance, fps, numFrames, priority,
applyOptimizations, applyInterpolation, interpolationFps
```

## What remains outside presets

Everything else in the current UI state is either a *motion* concern or an *execution* concern, and both are explicitly excluded from presets and from settings.txt import:

- **Motion** (per-run creative input, order-sensitive): the prompt list, generation mode (chain/parallel), combine-videos, max-parallel-tasks. See `img2video-execution-model.md` for how these become CLI flags.
- **Execution** (local device/run preferences, not part of the creative or generation request): play-result-when-finished.
- **Source**: the selected filename/image is never preset- or settings-derived.

## Reset and recovery

`localStorage` holds exactly one working-state entry, currently keyed `img2videoSafariV4`. Reset:

1. Clears the working-state key (`img2videoSafariV4`).
2. Clears known legacy keys from earlier UI schema versions (`img2videoSafariV3`, the pre-existing legacy preset cache key `img2videoPresetsV1`) so stale shapes never leak back in.
3. Restores every field, including the prompt list (back to a single default prompt) and the Execution section, to `DEFAULTS`.
4. Re-fetches `presets.txt` from scratch.

The working-state key is bumped whenever the persisted JSON shape changes incompatibly (as it did for this multi-prompt/execution PR), rather than attempting field-by-field migration of an old single-prompt shape into the new prompt-list shape.
