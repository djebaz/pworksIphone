<!-- VERSION$00092$ | Edited: 07/08 | TIME: 14:24 -->
# Img2Video Presets / Settings / Local-State Contract

This document explains the three configuration layers behind `shortcuts/img2video/index.html` and where each one's authority stops. It exists so the boundary between "preset library," "one-off settings import," and "current working UI state" stays intentional as the UI grows, instead of drifting field by field.

## Configuration layers

```text
presets.txt          → built-in compact preset library, read-only in the UI
settings.txt import  → human-editable one-off import of supported generation/processing values
localStorage          → current working UI state (everything the form can hold)
current UI state      → single source of truth used to generate the CLI command
```

There is no user-created, user-saved, or user-editable preset concept. Do not reintroduce "Save as preset," "Delete preset," or similar controls.

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

Any line that fails these checks is skipped and counted; the UI reports how many valid presets loaded and how many lines were skipped, but never silently normalizes an invalid preset row.

The compact preset format intentionally remains unchanged in this revision. It cannot express a prompt, image, Seed, Seed enabled/disabled state, generation mode, combine-videos preference, max-parallel-tasks value, or play-on-finish preference.

## `settings.txt` import

The Safari UI's "Import settings.txt" button reads a local `key=value` text file and applies these recognized values:

```text
model
resolution
performance
fps
numFrames
seed
priority
applyOptimizations
applyInterpolation
interpolationFps
```

`seed` is validated as a signed 64-bit integer and is stored as text in the UI so its exact value is not rounded by JavaScript.

Seed import semantics are explicit:

- a non-empty valid `seed=<value>` loads that value and enables explicit Seed (`seedDisabled=false`);
- an empty `seed=` selects **No CLI seed** (`seedDisabled=true`) without making Seed part of the preset model;
- invalid or out-of-range Seed values are counted as skipped.

The real `artworks_settings.txt` consumed directly by `app/img2video_iphone.py` is richer — it also carries `photo`, `promptFile`/`prompt`, `output`, `generationMode`, `combineVideos`, `maxParallelTasks`, polling/recovery tuning, and more. The Safari importer remains deliberately narrower: it does not import prompts, source selection, multi-prompt execution state, playback preference, output path, or recovery/network settings.

## Preset matching

"Active preset" is derived, never stored. On every state change the UI compares the current values of the nine compact preset fields against every loaded preset (`generationsEqual`); if one matches exactly, its name is shown, otherwise the preset button displays `Custom`.

`Custom` is a derived display state only. It does **not** appear as a selectable preset-menu entry.

Seed is deliberately **not** part of preset matching. The Seed value and `seedDisabled` flag may change while the same generation/processing preset remains active. This preserves the existing 10-column preset contract instead of turning a per-run reproducibility value into a preset-library migration.

## What a preset may change

Exactly these nine fields, and nothing else:

```text
model, resolution, performance, fps, numFrames, priority,
applyOptimizations, applyInterpolation, interpolationFps
```

A preset never changes the stored Seed value and never changes whether explicit Seed is enabled or `No CLI seed` is active.

## What remains outside presets

- **Seed**: per-run generation value plus `seedDisabled` working-state flag, persisted locally and importable from settings, but never preset-scoped.
- **Motion**: prompt list, generation mode (chain/parallel), combine-videos, max-parallel-tasks.
- **Execution**: play-result-when-finished.
- **Source**: selected filename/image.

## Reset and recovery

`localStorage` holds one working-state entry, currently keyed `img2videoSafariV4`. Reset:

1. Clears the working-state key (`img2videoSafariV4`).
2. Clears known legacy keys (`img2videoSafariV3`, `img2videoPresetsV1`).
3. Restores every field, including `seed=42` with explicit Seed enabled (`seedDisabled=false`), the prompt list, and Execution, to `DEFAULTS`.
4. Re-fetches `presets.txt` from scratch with the existing no-cache behavior.

The Command Preview expanded/collapsed state is not persisted; a fresh page load starts with it collapsed.
