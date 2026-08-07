<!-- VERSION$00091$ | Edited: 07/08 | TIME: 14:24 -->
# Img2Video Execution Model — UI State → CLI

This document explains how the Safari UI's live form state becomes the exact command line handed to `app/img2video_iphone.py`, and from there to the Shortcut.

## Current UI state

The UI keeps one in-memory state object (`state()` in `index.html`), rebuilt from the DOM on every input/change event:

```text
imagePath, prompts[], model, resolution, performance, fps, frames, seed, seedDisabled, priority,
optimizations, interpolation, interpolationFps,
generationMode, combineVideos, maxParallelTasks,
playOnFinish
```

`prompts` is an ordered array of strings — the ordered prompt list from the Motion section, sanitized (newlines collapsed to spaces, trimmed) at read time. `seed` is stored as text so the UI can preserve the full signed 64-bit integer range without JavaScript `Number` precision loss. `seedDisabled` is a boolean UI-state flag that records whether Safari should omit an explicit `--seed`. Everything else is a single scalar sourced from the matching form control.

## CLI generation

`command(state)` builds one flat argv-style string in this fixed order:

1. `python <script path>`
2. One `--prompt '<text>'` per entry in `prompts`, in list order
3. `--model`, `--resolution`, `--performance`, `--fps`, `--frames`
4. `--seed <integer>` only when `seedDisabled === false` and Seed contains a valid value
5. `--priority`
6. `--optimizations`/`--no-optimizations`, `--interpolation`/`--no-interpolation`
7. `--interpolate <target>` — only when `interpolation` is true
8. `--mode`, `--combine-videos`/`--no-combine-videos`, `--max-parallel-tasks` — only when `prompts.length > 1` (and `--max-parallel-tasks` only when `generationMode === "parallel"`)
9. `--sound` — only when `playOnFinish` is true **and** the current run has one unambiguous final result to play

When `seedDisabled === true`, Safari omits `--seed` regardless of the stored Seed value.

The **Command Preview** starts collapsed. Tapping its header expands the generated command plus Copy and Reset actions. The display wraps argument groups with shell continuation markers (`\`) so press-and-hold copying remains executable even if the Clipboard API is unavailable. `Copy command` and the Shortcut hand-off still use the canonical single space-joined command with no display line breaks.

## Seed

Seed is an explicit signed 64-bit integer accepted by the Python client through `--seed`, with an independent Safari opt-out state.

- Default Seed is `42`.
- Default `seedDisabled` is `false`, so the default Safari command emits `--seed 42`.
- `seed` is stored as text and validated against `-9223372036854775808` through `9223372036854775807`, avoiding JavaScript safe-integer precision loss.
- `seedDisabled` is a boolean working-state flag.
- The **No CLI seed** control sets `seedDisabled=true`, disables the Seed input, retains the stored Seed value, and suppresses `--seed` in the generated command.
- Returning to explicit Seed sets `seedDisabled=false`; the retained Seed value becomes active again.
- Copy and Launch validate Seed only when `seedDisabled=false`.
- A non-empty valid `seed=` imported from `settings.txt` loads that value and enables explicit Seed.
- An empty `seed=` imported from `settings.txt` selects `No CLI seed`.

Both `seed` and `seedDisabled` are persisted in the local working state. Seed remains intentionally outside the compact `presets.txt` schema and preset matching. See `img2video-presets-settings-contract.md`.

## Prompt list encoding

Each prompt becomes its own `--prompt` argument, shell-quoted with the existing `quote()` helper (POSIX single-quote escaping). This matches `img2video_iphone.py`'s `--prompt` argument, which uses `action="append"` — the Python client already supports and expects repeated `--prompt` flags, and treats their order as both task order and, in chain/combine mode, assembly order.

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

Execution deliberately contains one control only:

- **Play result when finished** → `--sound` (the client's actual flag, also spelled `-s`). There is no `--open-video` flag.

For a multi-prompt Parallel run with **Combine videos OFF**, the Python client finishes with several independent output files and has no single result to select for playback. In that state the UI disables Play result when finished and omits `--sound`. The checked preference is preserved so it becomes effective again if the run returns to a configuration with a single playable result.

There is intentionally no output-directory picker or output-folder text field.

The Safari UI always omits an explicit `--output` argument. That does **not** necessarily mean the Python client always uses `<photo-name>_video.mp4`: `argparse` first takes `output=` from the real `artworks_settings.txt` when one is configured, and only falls back to `<photo-name>_video.mp4` beside the input when neither CLI nor settings provides an output path. The effective precedence is therefore:

```text
explicit --output CLI
    > artworks_settings.txt output=
    > <photo-name>_video.mp4 beside the input
```

## Shortcut hand-off

The final payload sent via `shortcuts://run-shortcut?...&text=<payload>` is:

```json
{"version": 1, "filename": "<basename only>", "cmd": "<single-line command from above>"}
```

The Shortcut (`Run Img2Video in a-Shell`, reconstructed in `devdocs/shortcut/README.md`) resolves `filename` to a real file in Files/Photos, changes into the a-Shell "File Provider Storage" directory, appends the resolved path to `cmd`, and runs the result as one a-Shell command.
