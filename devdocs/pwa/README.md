<!-- VERSION$00004$ | Edited: 07/08 | TIME: 18:57 -->
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
- [`implementation-plan.md`](implementation-plan.md) — staged plan for creating the PWA without disturbing the working implementation.

## Current direction

The target is an installable PWA hosted by GitHub Pages under a dedicated path, preserving the existing UI and file-picker behavior as much as practical while moving ArtWorks task submission and monitoring into the PWA itself.

Future PWA runtime source belongs in repository-root `pwa/`; the existing Safari/Shortcut/Python implementation remains untouched during discovery and early PWA development.

The application does not need functional offline generation because ArtWorks requires network access. It should still show clear network/offline state and preserve all remote task IDs so interrupted work can be reconciled when connectivity/application execution returns.

The current background-execution recommendation is foreground-first orchestration with durable IndexedDB recovery. A Service Worker must not be treated as a persistent poller. It becomes useful when a concrete event-driven feature such as Web Push is implemented.

Modern iOS Home Screen web apps can receive Web Push, but a server-side push sender and a meaningful external completion event are required. ArtWorks webhook/callback availability is currently unknown.

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

## Research discipline

Platform/provider claims in these documents should distinguish documented browser behavior from project observations and architecture inference.

Unknowns must remain explicit. In particular, do not assume:

- ArtWorks permits browser CORS until verified;
- ArtWorks has or lacks a webhook until authoritative evidence is found;
- a Service Worker continues running after the app is backgrounded;
- automatic iOS downloads behave like desktop Chrome;
- Password AutoFill behaves identically in every installed-PWA context until device-tested;
- browser credential encryption eliminates XSS risk.

No discovery-only API test should create a potentially billable task merely to answer a platform question that can be resolved by documentation, preflight, or a rejected validation request.
