<!-- VERSION$00001$ | Edited: 07/08 | TIME: 18:24 -->
# PWA Discovery Decision Log

This file records explicit decisions and open choices from the PWA discovery session so later implementation work does not silently reinterpret them.

## 2026-08-07 — Initial PWA direction

### Hosting

**Decision:** host the PWA on GitHub Pages.

The current Pages workflow publishes `shortcuts/img2video/` as the deployed root. Future PWA deployment must deliberately update the artifact layout because the new runtime source will not live there.

### Runtime source location

**Decision:** all new PWA application code will live under repository-root:

```text
pwa/
```

Reason: isolate PWA work from the currently working Safari/Shortcut and Python scripts.

### Documentation location

**Decision:** all PWA discovery, architecture, security, planning, and later PWA-specific technical documentation belongs under:

```text
devdocs/pwa/
```

### Existing implementation preservation

**Decision:** do not modify the working `shortcuts/img2video/` launcher or `app/img2video_iphone.py` merely to begin PWA development.

They remain the behavioral reference during migration.

### Offline mode

**Decision:** no offline mode is wanted for the first PWA.

Implication: offline shell caching is not a product requirement. A Service Worker is optional unless another concrete requirement justifies it.

### Icon

**Decision:** no icon has been selected yet.

Icon design/generation is deferred.

### Standalone iOS appearance

**Decision:** standalone mode should visually blend with the existing dark application background and safe-area treatment.

### ArtWorks execution

**Decision:** the desired PWA should ultimately handle ArtWorks API calls itself rather than only launching the current Shortcut/Python execution path.

This is a target architecture, not yet an implementation claim. Credential security, CORS, browser lifecycle, recovery, chain mode, and media-processing feasibility must be resolved.

### File picker

**Decision:** preserve the current HTML file-selection behavior.

Do not redesign the picker during PWA bootstrap.

### Updates

**Decision:** newly deployed application versions should be picked up naturally on a later navigation/reload.

No custom "update available" UI is currently wanted.

### Cache strategy

**Open:** cache policy depends on whether a Service Worker is ultimately justified.

Because there is no offline requirement, do not start from an application-shell precache assumption.

### Custom installation UI

**Decision:** no custom Safari install button or banner for the initial version.

Use the normal browser/OS installation flow.

### Credentials / environment variables

**Open and high priority:** determine how ArtWorks credentials can be protected when the UI is hosted on public GitHub Pages.

Known constraint: browser-delivered environment variables are not secrets. GitHub Actions secrets must not be injected into public HTML/JavaScript or another Pages artifact.

Candidate directions currently under study:

1. user-supplied credentials held only on the device, with direct browser-to-ArtWorks requests if CORS permits;
2. a separate authenticated serverless/edge/backend proxy that keeps ArtWorks credentials server-side;
3. an ArtWorks-supported short-lived/scoped browser credential, if such a mechanism exists.

### Google Fonts dependency

**Open:** decide whether to retain the current external JetBrains Mono stylesheet, accept system fallback, or self-host later.

Because no offline mode is planned, this is not currently blocking PWA installation.

### Public Pages path

**Open:** the PWA source location is fixed as `pwa/`, but its final public Pages path is not yet selected.

Candidate deployment shapes include `/pwa/`, making the PWA the site root after parity, or publishing explicit legacy/PWA paths side by side.
