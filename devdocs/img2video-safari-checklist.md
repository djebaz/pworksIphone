<!-- VERSION$00077$ | Edited: 07/08 | TIME: 13:26 -->
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
| 11 | Generation includes optional Seed | Done — signed 64-bit validation, `--seed` only when non-empty |
| 12 | Seed has a clear Randomize action | Done — Web Crypto signed 64-bit generation with fallback |
| 13 | Compact `presets.txt` schema remains unchanged | Done — Seed is deliberately not preset-scoped |
| 14 | Settings import recognizes Seed | Done — invalid/out-of-range seed is skipped |
| 15 | Command Preview starts collapsed | Done — header toggles body; state not persisted |
| 16 | Expanded Command Preview shows command, Copy, Reset | Done |
| 17 | Manual preview copy remains shell-safe | Done — display lines use shell continuation markers |
| 18 | Copy/Launch still use one canonical single-line command | Done |
| 19 | `--output` precedence is documented correctly | Done — CLI > settings `output=` > `<photo>_video.mp4` fallback |
| 20 | Sticky Launch Shortcut footer and READY/status indicator remain unchanged | Done |
| 21 | Reset clears working + legacy keys and reloads `presets.txt` | Done |

## Compatibility notes

- The Python client's play-on-completion flag is `-s`/`--sound`; there is no `--open-video` flag.
- The Safari UI intentionally has no output-directory picker or output-folder text field.
- Max Parallel Tasks defaults to 6 in the UI, matching the tracked example settings file.
- Seed is represented as text in the browser so values across the full signed 64-bit range are not rounded through JavaScript `Number`.
