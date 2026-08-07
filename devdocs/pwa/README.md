<!-- VERSION$00013$ | Edited: 07/08 | TIME: 20:41 -->
# PWA Discovery and Planning

This directory is the canonical home for discovery, architecture, security, and implementation planning for the future Img2Video Progressive Web App.

The PWA is a new application surface. Its runtime code will live under repository-root `pwa/` so development can proceed without modifying the currently working Safari/Shortcut/a-Shell implementation under `shortcuts/img2video/` and `app/`.

## Current project boundary

- Existing Safari launcher: `shortcuts/img2video/index.html`
- Existing preset library: `shortcuts/img2video/presets.txt`
- Existing iPhone Python client: `app/img2video_iphone.py`
- Future PWA runtime: `pwa/`
- PWA documentation and plans: `devdocs/pwa/`

The existing runtime remains the behavioral reference during discovery. PWA work must not silently change it.

## Documents

- [`decision-log.md`](decision-log.md) — explicit decisions and open choices from the discovery sessions.
- [`discovery.md`](discovery.md) — current findings, verified repository constraints, and unresolved questions.
- [`runtime-architecture.md`](runtime-architecture.md) — consolidated reconciler-led production architecture: credential layer, durable Run/Step/Task ledger, serialized creation, orphan handling, staging/export, Chain, provider surface assumptions, and implementation stages.
- [`security-and-api-architecture.md`](security-and-api-architecture.md) — selected user-owned credential model, Password AutoFill preference, same-origin preview/fork trust boundary, CSP direction, and browser/API constraints.
- [`background-execution-and-notifications.md`](background-execution-and-notifications.md) — Service Worker lifecycle, iOS background limitations, Web Push architecture, durable recovery, timers, chain-mode and download implications.
- [`external-research-review.md`](external-research-review.md) — review of the user-supplied August 2026 iOS PWA background-execution research, including Declarative Web Push, Safari 26 installability, Wake Lock, foreground checkpoints, server-vs-device tradeoffs, and the resulting Img2Video recommendations.
- [`python-runtime-parity.md`](python-runtime-parity.md) — direct comparison of the production Python state machine with browser/PWA equivalents, including serialized creation, reconciler-first execution, Chain, and the dual diagnostic/runtime boundary.
- [`reliability-boundaries.md`](reliability-boundaries.md) — first-class reliability analysis for the submission orphan window, result retention/URL TTL, storage persistence, wall-clock recovery, Wake Lock, CORS, and the narrow webhook-to-push relay concept.
- [`artworks-provider-capabilities.md`](artworks-provider-capabilities.md) — targeted review of the authenticated ArtWorks contract for CORS, idempotent creation, task discovery/listing, result retention/URL refresh, and webhook/callback support.
- [`chain-media-strategy.md`](chain-media-strategy.md) — selected no-FFmpeg Chain strategy, preferring Mediabunny for remote MP4 reading and presentation-order final-frame decoding, with MP4Box.js + direct WebCodecs retained as a lower-level fallback.
- [`orion-ios-extension-findings.md`](orion-ios-extension-findings.md) — direct inspection of two supplied Orion extension packages and the distinction between HTMLVideoElement control, privileged extension downloads, and PWA sample-level media access.
- [`existing-browser-media-implementations.md`](existing-browser-media-implementations.md) — direct inspection of the private `mothanext` and `StreamsDL` repositories: WebCodecs/Mediabunny processing, HLS/DASH acquisition, real `206` Range validation, OPFS staging, FFmpeg-WASM resource costs, and the subset applicable to Img2Video.
- [`implementation-plan.md`](implementation-plan.md) — current staged plan: non-billable viability gates, single prompt, serialized-submit parallel mode, Chain, and the conditions under which a relay/server decision could be reopened.

## Current direction

The target is an installable PWA hosted through a trusted HTTPS origin, preserving the existing UI/file-picker behavior as much as practical while moving ArtWorks task orchestration into the PWA itself.

Future PWA runtime source belongs in repository-root `pwa/`; the existing Safari/Shortcut/Python implementation remains untouched during discovery and early PWA development.

The application does not need functional offline generation because ArtWorks requires network access. It must preserve durable local execution state so work can be reconciled when connectivity/application execution returns.

## Runtime architecture

The central architectural decision is now explicit:

> **The reconciler is the center, not the poll loop.**

IndexedDB is the durable `Run -> Step -> Task` ledger. The foreground poll loop is only a responsiveness optimization.

For every potentially billable creation:

```text
persist local intent
    -> serialized POST /api/v3/tasks
    -> receive remote task ID
    -> immediately bind ID to the same ledger record
    -> foreground poll while active
    -> reconcile by known ID after visible/reopen/online
```

If a POST may have been accepted but no remote ID was durably captured, mark the local record ambiguous and never silently resubmit it.

Logical parallel mode serializes creation POSTs so only one task at a time can occupy that ambiguity window. Once IDs are durably known, remote execution, polling and output handling can proceed concurrently with bounded concurrency.

All retry/backoff/timeout/priority calculations derive from persisted wall-clock timestamps rather than JavaScript timer ticks.

The authenticated OpenAPI task-info schema includes `preparing` and `unknown` in addition to the shorter lifecycle summary in AGENTS.md. They must not be treated as terminal merely because the shorter list omits them; `unknown` receives bounded defensive handling while preserving the task ID.

## Python/PWA runtime relationship

The PWA can reproduce most of the Python client's orchestration logic, but the browser lifecycle is different.

The Python/a-Shell process attempts to remain active, while a PWA assumes suspension is normal. Remote ArtWorks work continues independently. On return, the PWA loads durable state and reconciles known IDs against the authoritative provider state.

The deliberate long-term boundary is:

### PWA

- production user interface;
- credential unlock/use in memory;
- durable ledger and reconciliation;
- submission/polling/cancel/priority controls;
- run history;
- normal output staging/export;
- Chain final-frame extraction.

### Python + project probes

- provider discovery;
- reproducible API experiments;
- `ffprobe`-grade media measurement;
- exact codec/container diagnostics;
- saved measurement evidence.

The PWA is therefore not a wholesale replacement for the diagnostic runtime even though it becomes the production interaction surface.

## Chain/media direction

Chain no longer has an FFmpeg dependency in the selected design.

Preferred production candidate:

```text
ArtWorks result URL
    -> Mediabunny UrlSource
    -> Input({ formats: [MP4] })
    -> primary video track
    -> track.canDecode()
    -> VideoSampleSink.getSample(Infinity)
    -> final presentation-order VideoSample
    -> canvas
    -> JPEG/PNG Blob
    -> persist transition state
    -> next asynchronous ArtWorks task
```

The supplied Mediabunny guide documents lazy partial reads, MP4-specific tree shaking, optimized `UrlSource` reads with bounded cache, runtime decodability checks, presentation-order sample sinks, direct last-sample retrieval, and explicit resource cleanup.

Project-specific constraints:

- do not use `ALL_FORMATS` in production Chain code;
- override `UrlSource`'s default infinite retry with bounded retry behavior;
- close samples/dispose inputs promptly;
- vendor a pinned reviewed build under the repository-controlled PWA;
- do not load credential-adjacent runtime JavaScript from a third-party CDN.

MP4Box.js + direct WebCodecs remains the low-level fallback/debug path. `<video>` + canvas remains the simplest compatibility experiment.

No video encoder, audio processing, output muxer, or ffmpeg.wasm is required for normal Chain advancement.

## Existing browser-media reference implementations

The owner's private `mothanext` and `StreamsDL` repositories provide directly inspected reference implementations for substantially harder browser-media workflows.

`mothanext` contains MP4 sample/range processing, explicit DTS/PTS and B-frame handling, WebCodecs decode/encode, deterministic frame cleanup, muxing, and a Mediabunny integration path. This is the closest existing reference for the low-level media mechanics beneath Chain.

`StreamsDL` contains HLS/DASH manifest parsing, segment acquisition, direct-MP4 metadata/range clipping, OPFS/internal staging, and FFmpeg-WASM remux/repair/merge/concat flows. Its Range guardrail is especially useful: when `Accept-Ranges` is absent, only a real one-byte `206 Partial Content` response establishes Range capability; a `200` full response must not be classified as proven random-access support.

StreamsDL also documents the real cost of the heavyweight fallback: its active vendored FFmpeg WASM cores are approximately 24 MiB each before runtime memory expansion, it enforces an approximately 800 MiB input ceiling, and its accepted runtime handling includes actual `WebAssembly.Memory()` allocation failure/fallback behavior.

These repositories reduce implementation uncertainty but do not change the selected production ordering:

1. Mediabunny for Chain;
2. `<video>` + canvas as the minimal compatibility experiment;
3. low-level MP4/WebCodecs techniques from `mothanext` for diagnostics/fallback;
4. FFmpeg-WASM techniques from `StreamsDL` only if a future requirement genuinely needs repair, format conversion, A/V muxing, or concatenation.

Extension host/download/offscreen privileges do not transfer to the PWA. ArtWorks media CORS and real Range behavior still require Stage 0 validation from the production origin.

## Orion iOS extension findings

Two supplied Orion packages were inspected directly.

### RedGifs Downloader for Orion 1.1.7

The extension uses explicit RedGifs host permissions plus the browser extension `downloads` permission. Its content script resolves a direct MP4 URL and its background service worker delegates that URL to `downloads.download()`.

It does **not** parse, decode, transcode, or transform the MP4 in JavaScript.

This demonstrates extension privilege, not normal PWA capability. It does not prove that an ArtWorks result URL is JavaScript-fetchable from GitHub Pages or that a Home Screen PWA has the extension downloads API.

### Orion Lite AutoNext 0.2.19

The extension has only storage permission and controls the site's existing `HTMLVideoElement`: play/pause, current time, playback rate, sizing, muted state, inline-playback hints and normal media lifecycle events.

The browser owns network, demux, decode, rendering and audio. The content script does no media-byte processing.

The practical lesson is to keep ordinary playback/preview browser-native and bring media bytes into JavaScript only where sample-level access is genuinely required, chiefly Chain final-frame extraction.

## ArtWorks provider capability status

The authenticated ArtWorks OpenAPI snapshot currently available to the project narrows several provider questions:

- **CORS/preflight:** still **Unknown**; OpenAPI does not define runtime CORS policy.
- **Task-creation idempotency:** **Not documented**; no duplicate-safe creation contract is exposed.
- **Task listing/search:** **Not documented**; `/api/v3/tasks` exposes POST, while task retrieval is documented only by known ID at `/api/v3/tasks/{task}`.
- **Tags:** documented for categorization/filtering and returned with task info, but no list/filter operation is exposed in the same contract.
- **`batchId`:** documented for shared queue-priority behavior, not orphan recovery.
- **Completed-task/media retention and result URL refresh:** **Unknown**.
- **Webhook/callback registration:** **Not documented**.
- **`run-ffmpeg`:** present in the authenticated generic task-type enum, but payload schema, account entitlement, URL-to-URL semantics and billing are not established by current project evidence.

"Not documented" is deliberately narrower than "does not exist". The production architecture simply does not depend on those capabilities.

## Reliability boundaries

Foreground recovery solves interruptions only after a remote task ID has been durably captured.

The two structural provider-dependent boundaries remain:

1. **submission orphan window** — provider may accept creation before local ID persistence;
2. **post-completion retrieval window** — result recovery depends on task/media retention and URL refresh behavior.

A local UUID/intent record is mandatory but cannot prove whether an ambiguous POST created billable work. An optional deterministic ArtWorks tag is useful forward-compatible correlation evidence, not a current discovery mechanism.

Do not send an undocumented `Idempotency-Key` by default; it has no current provider contract and would also change CORS preflight requirements.

## Background execution and relay status

Foreground-first orchestration with durable IndexedDB recovery remains the portable baseline.

A Service Worker must not be treated as a persistent poller. Background Sync, Periodic Background Sync, keep-alive timers, sockets, looping audio and Wake Lock do not provide dependable unattended execution on iOS. Wake Lock remains an attended-mode enhancement only.

A credential-free push relay has been removed from the active implementation stages because webhook/callback registration is not documented in the current provider contract. A relay that polls ArtWorks would require the reusable credential and violate the selected device-owned boundary.

Revisit the relay only if a provider-side trusted completion event becomes available.

## Credentials

**Selected direction:** each user supplies their own ArtWorks credentials; reusable credentials are never injected into GitHub Pages assets or committed to the repository.

**Preferred persistence approach:** use Safari/system Password AutoFill through semantic username/current-password fields, then keep the active credential only in memory while the PWA is unlocked.

A known task with locked credentials is an authentication-required state, not a failed/missing task.

Raw `localStorage` is rejected for ArtWorks credentials. Encrypted IndexedDB + Web Crypto remains a fallback only if real-device Password AutoFill testing is insufficient.

Direct browser-to-ArtWorks requests remain contingent on verified CORS/preflight support.

## Storage and outputs

Use IndexedDB for the structured task/run/history ledger.

On launch, check `navigator.storage.persisted()` and call `navigator.storage.persist()` only when not already persistent.

OPFS is a browser-supported candidate for origin-private media staging, not a user-visible Files location. Treat output states separately:

```text
remote-completed -> staged -> exported
```

Prefer streaming/bounded-memory staging. User-visible Files/Photos/share behavior remains a physical-iPhone validation item.

## Deployment security direction

The previously preferred path layout remains mechanically useful:

```text
Production:  /pwa/
PR preview:  /preview/pr-<number>/pwa/
```

However, path separation is **not** origin isolation.

Before any real ArtWorks credential is used, decide whether PR/fork preview content is fully trusted. If untrusted code can be published beneath the same credential-bearing origin, the production PWA needs a separate trusted origin/hostname or the preview model must change.

Relative manifest/icon/Service Worker paths/scopes remain required, but Service Worker scope does not solve same-origin credential/storage trust.

## Implementation stages

The active plan is now:

1. **Stage 0 — non-billable viability gates:** API CORS, result-media JavaScript access including a real `206` Range probe, origin trust, local Mediabunny fixture.
2. **Stage 1 — single prompt:** credential flow, ledger, reconciler, one serialized async creation, polling, staging/export.
3. **Stage 2 — multi-prompt/parallel:** serialized creation, bounded concurrent known-ID work, durable partial completion.
4. **Stage 3 — Chain:** Mediabunny final-frame extraction and persisted dependent-step advancement.

No active server/relay stage exists under the current provider contract.

Video concatenation/assembly remains intentionally out of scope by product decision.

## Remaining highest-value unknowns

- ArtWorks API CORS from the real intended production origin;
- ArtWorks result-media CORS/partial reads, including whether a one-byte Range request returns a valid `206 Partial Content` response;
- completed-task/result TTL and URL refresh behavior;
- target-iPhone Password AutoFill behavior;
- target-iPhone installed-PWA export behavior;
- real Wan/LTX MP4 decode/final-frame extraction through Mediabunny;
- `run-ffmpeg` entitlement/payload/cost only if future server-side transforms are considered.

## Research discipline

Platform/provider claims in these documents must distinguish documented behavior from project observations, user-selected decisions and architecture inference.

Do not assume:

- ArtWorks permits browser CORS until verified;
- undocumented provider capabilities are available;
- result URLs remain retrievable for a particular duration until verified;
- extension host/download privileges apply to PWAs;
- Service Workers continue running after backgrounding;
- automatic iOS export behaves like desktop Chrome;
- Password AutoFill behaves identically in every installed-PWA context until device-tested;
- browser credential encryption eliminates XSS risk.

No discovery-only API test should create a potentially billable task merely to answer a question that can be resolved by documentation, preflight, a local fixture, or an already-paid task/result.
