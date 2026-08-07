<!-- VERSION$00001$ | Edited: 07/08 | TIME: 18:20 -->
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

- [`discovery.md`](discovery.md) — current findings, user decisions, verified repository constraints, and unresolved questions.
- [`security-and-api-architecture.md`](security-and-api-architecture.md) — credential handling and browser/API architecture options.
- [`implementation-plan.md`](implementation-plan.md) — staged plan for creating the PWA without disturbing the working implementation.

## Current direction

The target is an installable PWA hosted by GitHub Pages, preserving the existing UI and file-picker behavior as much as practical while eventually moving ArtWorks task submission and monitoring into the PWA itself.

The first PWA version is not intended to provide an offline mode. Installation and standalone presentation are separate concerns from offline caching.

The desired iOS standalone appearance should blend into the application's existing dark background/safe-area design.

No application icon has been selected yet.

## Important unresolved architecture question

GitHub Pages is a public static host. It cannot keep a runtime secret from browser JavaScript. The existing Python client uses ArtWorks credentials for HTTP Basic authentication, so credential handling must be designed explicitly before API calls are moved into the browser.

Do not commit credentials, inject them into generated JavaScript, or assume that GitHub Actions secrets become private browser environment variables.
