<!-- VERSION$00007$ | Edited: 07/08 | TIME: 19:08 -->
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
- [`security-and-api-architecture.md`](security-and-api-architecture.md) — selected device-local/user-owned credential model, Password AutoFill preference, threat model, CSP direction, and browser/API constraints.
- [`background-execution-and-notifications.md`](background-execution-and-notifications.md) — Service Worker lifecycle, iOS background limitations, Web Push architecture, durable recovery, timers, chain-mode and download implications.
- [`external-research-review.md`](external-research-review.md) — review of the user-supplied August 2026 iOS PWA background-execution research, including Declarative Web Push, Safari 26 installability, Wake Lock, foreground checkpoints, server-vs-device tradeoffs, and the resulting Img2Video recommendations.
- [`python-runtime-parity.md`](python-runtime-parity.md) — direct comparison of the production Python state machine with browser/PWA equivalents, including foreground suspension semantics and remaining parity blockers.
- [`reliability-boundaries.md`](reliability-boundaries.md) — first-class reliability analysis for the submission orphan window, result retention/URL TTL, storage persistence, wall-clock recovery, Wake Lock, and the narrow webhook-to-push relay option.
- [`implementation-plan.md`](implementation-plan.md) — staged plan for creating the PWA without disturbing the working implementation.

## Current direction

The target is an installable PWA hosted by GitHub Pages under a dedicated path, preserving the existing UI and file-picker behavior as much as practical while moving ArtWorks task submission and monitoring into the PWA itself.

Future PWA runtime source belongs in repository-root `pwa/`; the existing Safari/Shortcut/Python implementation remains untouched during discovery and early PWA development.

The application does not need functional offline generation because ArtWorks requires network access. It should still show clear network/offline state and preserve all remote task IDs so interrupted work can be reconciled when connectivity/application execution returns.

## Python/PWA runtime relationship

The current parity analysis finds that most of the Python client's **orchestration logic** can be reproduced directly in a PWA:

- request validation;
- task submission;
- immediate task-ID persistence;
- status polling and bounded retries;
- terminal-state/error handling;
- parallel execution;
- cancellation and priority operations;
- detailed task/run history;
- per-phase timing;
- download state;
- prompt-set reuse;
- interruption recovery without duplicate submissions.

The largest difference is lifecycle, not API capability.

The Python/a-Shell process attempts to keep polling continuously, while the PWA must assume iOS can suspend it outside the foreground. The remote ArtWorks task continues independently. When the PWA becomes active again it loads IndexedDB, queries existing task IDs, and resumes from the authoritative remote state.

In that sense, the Python client's recovery model becomes the PWA's normal execution model.

Chain mode remains feasible in principle but requires validation of browser-native final-frame extraction from the previous result. The current candidate uses an `HTMLVideoElement`, `requestVideoFrameCallback()`, canvas extraction, and a Blob rather than FFmpeg.

The PWA intentionally does not reproduce shell execution or FFmpeg video concatenation; every ArtWorks output remains independent.

The current background-execution recommendation is foreground-first orchestration with durable IndexedDB recovery. A Service Worker must not be treated as a persistent poller. It becomes useful when a concrete event-driven feature such as Web Push is implemented.

The August 2026 external research review reinforces that Background Sync, Periodic Background Sync, keep-alive timers, WebSockets, audio tricks, and Wake Lock do not provide dependable iOS background execution. Wake Lock may still be useful as an optional foreground UX feature. Classic Web Push can briefly wake a Service Worker but requires a visible notification; Declarative Web Push is preferable for pure notifications because it deliberately avoids JavaScript execution.

Modern iOS Home Screen web apps can receive Web Push, but a server-side push sender and a meaningful external completion event are required. ArtWorks webhook/callback availability is currently unknown.

## Reliability boundaries

Foreground recovery solves interruptions only after a remote task ID has been durably captured. The PWA therefore treats two provider-dependent boundaries as first-class discovery blockers:

1. **submission orphan window** — ArtWorks may accept a POST before the PWA persists the returned task ID; safe recovery requires provider idempotency or a reliable task-discovery/correlation mechanism;
2. **post-completion retrieval window** — result recovery depends on completed-task retention, video URL lifetime, and the ability to refresh/retrieve a result after a long suspension.

A local submission-intent record should be persisted before POST, but that record alone cannot prove whether an ambiguous request created a billable task. Blind automatic re-submission of an ambiguous intent is therefore prohibited until provider behavior closes that gap.

Retry schedules, phase timers, priority-promotion thresholds, and timeouts must be reconstructed from persisted wall-clock timestamps after suspension rather than resumed from JavaScript tick counters.

A narrow future relay remains possible without moving reusable ArtWorks credentials off-device: if ArtWorks can emit authenticated completion callbacks, a relay could map opaque task/correlation IDs to Web Push subscriptions and only notify the device. Webhook/callback availability remains unknown.

## Credentials

**Selected direction:** each user supplies their own ArtWorks credentials; reusable credentials are never injected into GitHub Pages assets or committed to the repository.

**Preferred persistence approach:** use Safari/system Password AutoFill through a semantic username/password form, then keep the active credential in application memory while the PWA is unlocked. This delegates persistent credential storage to the user's password manager rather than creating an application-owned plaintext secret database.

If the requirement is literally one physical device with no password-manager synchronization, the user's system Passwords/iCloud sync policy matters and must be treated separately from PWA storage.

Raw `localStorage` is rejected for ArtWorks credentials. Encrypted IndexedDB + Web Crypto with an explicit unlock secret is a fallback to investigate only if real-device Password AutoFill testing is insufficient.

Direct browser-to-ArtWorks requests remain contingent on verified CORS/preflight support.

## Recovery and history

The PWA is intended to persist enough non-secret state to recover active and historical work safely:

- configuration and prompt sets;
- remote ArtWorks task IDs;
- chain/parallel progress;
- last known task state and phase timestamps;
- completed/pending download state;
- reusable run history.

Use IndexedDB as the structured task/run/history store.

After interruption, the PWA should re-query existing non-terminal task IDs rather than creating duplicate potentially billable tasks. If credentials are locked after a cold restart, persisted tasks remain visible and can show an authentication-required state until the user uses Password AutoFill or enters the credential again.

Per-step timers are derived from persisted timestamps. They must not rely on browser timers continuing while iOS has suspended the PWA.

For storage durability, check `navigator.storage.persisted()` on launch and call `navigator.storage.persist()` only when the origin is not already persistent. WebKit documents persistent mode as remembered across sessions. Home Screen first-party storage is also explicitly exempt from ITP's historic seven-day script-writable-storage deletion rule. Storage loss must nevertheless remain a handled recovery path.

## Outputs and chain behavior

Each completed ArtWorks output is an independent file; the PWA will not reproduce Python FFmpeg concatenation.

Automatic output export/download remains a foreground/browser capability that needs physical-device testing on iOS. Durable export state should allow retry after interruption.

Chain mode still needs the previous output's last frame. The current browser-native candidate uses a video element, `requestVideoFrameCallback()`, canvas extraction, and a Blob rather than FFmpeg. Automatic chain continuation should be designed to pause/recover cleanly if the page is suspended.

## Deployment direction

The PWA should be published separately from the working launcher. The preferred layout being studied is:

```text
Production:  /pwa/
PR preview:  /preview/pr-<number>/pwa/
```

Manifest, icon, and Service Worker paths should be relative so the same source works in production and preview directories without allowing a preview Service Worker to control production.

## Standalone presentation and installation

The desired iOS standalone appearance should blend into the application's existing dark background and safe-area design.

No custom installation banner is planned initially; use normal browser/OS installation flows.

The final application icon is being prepared separately, so no temporary icon should be introduced.

Safari/WebKit 26 no longer requires a manifest or Service Worker merely for Home Screen web-app installation. Img2Video should still ship a manifest because it provides stable application identity, icons, theme, display mode, start URL, scope, and cross-browser PWA semantics.

## Research discipline

Platform/provider claims in these documents should distinguish documented browser behavior from project observations and architecture inference.

Unknowns must remain explicit. In particular, do not assume:

- ArtWorks permits browser CORS until verified;
- ArtWorks has or lacks a webhook until authoritative evidence is found;
- ArtWorks supports task-creation idempotency or task listing/search until verified;
- completed ArtWorks task/result URLs remain retrievable for any particular duration until verified;
- a Service Worker continues running after the app is backgrounded;
- automatic iOS downloads behave like desktop Chrome;
- Password AutoFill behaves identically in every installed-PWA context until device-tested;
- browser credential encryption eliminates XSS risk.

No discovery-only API test should create a potentially billable task merely to answer a platform question that can be resolved by documentation, preflight, or a rejected validation request.
