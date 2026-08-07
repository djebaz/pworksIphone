<!-- VERSION$00093$ | Edited: 07/08 | TIME: 14:24 -->
# Img2Video Safari UX — Acceptance Checklist

Tracks the shipped multi-prompt/execution work from PR #5 plus the corrective UX pass in PR #6.

| # | Criterion | Status |
|---|---|---|
| 1 | Preserve existing synthwave visual system and mobile compactness | Done — no global redesign/resizing pass |
| 2 | Motion section supports ordered multiple prompts | Done |
| 3 | Add/reorder/delete prompts, minimum 1 | Done |
| 4 | Chain/Parallel appears only for 2+ prompts | Done |
| 5 | Combine Videos appears only for 2+ prompts | Done |
| 6 | Max Parallel Tasks appears only for Parallel with 2+ prompts | Done |
| 7 | Processing keeps interpolation target values 24/25/30/50/60 | Done |
| 8 | Interpolation target enabled only when interpolation is ON | Done |
| 9 | Execution contains only Play result when finished | Done — real flag is `--sound`; no output-directory UI |
| 10 | Parallel + Combine OFF does not emit an unusable `--sound` | Done — playback control disabled, preference retained |
| 11 | Generation includes explicit signed-64-bit Seed | Done — default Seed is `42`; value stored as text and validated when active |
| 12 | Seed can be disabled explicitly | Done — `No CLI seed` disables the field and suppresses `--seed` |
| 13 | Compact `presets.txt` schema remains unchanged | Done — Seed and `seedDisabled` are deliberately not preset-scoped |
| 14 | Settings import recognizes Seed | Done — non-empty valid `seed=` enables explicit Seed; empty `seed=` selects `No CLI seed`; invalid/out-of-range values are skipped |
| 15 | `Custom` is derived only | Done — shown when no preset matches; not a selectable preset-menu item |
| 16 | Command Preview starts collapsed | Done — header toggles body; state not persisted |
| 17 | Expanded Command Preview shows command, Copy, Reset | Done |
| 18 | Manual preview copy remains shell-safe | Done — display lines use shell continuation markers |
| 19 | Copy/Launch still use one canonical single-line command | Done |
| 20 | `--output` precedence is documented correctly | Done — CLI > settings `output=` > `<photo>_video.mp4` fallback |
| 21 | Sticky Launch Shortcut footer and READY/status indicator remain unchanged | Done |
| 22 | Reset clears working + legacy keys and reloads `presets.txt` | Done — restores `seed=42` with explicit Seed enabled |

## Compatibility notes

- The Python client's play-on-completion flag is `-s`/`--sound`; there is no `--open-video` flag.
- The Safari UI intentionally has no output-directory picker or output-folder text field.
- Max Parallel Tasks defaults to 6 in the UI, matching the tracked example settings file.
- Seed is represented as text in the browser so values across the full signed 64-bit range are not rounded through JavaScript `Number`.
- `seedDisabled` is working-state only; presets neither store nor match it.
- `Custom` is a derived display label, not a preset that can be selected.
