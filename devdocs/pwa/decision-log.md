<!-- VERSION$00002$ | Edited: 07/08 | TIME: 18:43 -->
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

### Public Pages path

**Decision:** publish the PWA at a dedicated GitHub Pages path rather than replacing the existing deployed root.

The precise pathname can be finalized with the deployment workflow, but the deployment design must support the PWA as a distinct application surface. PR previews should preserve the same isolation so a PWA branch can be exercised without replacing production.

### Offline mode

**Decision:** no functional offline mode is wanted for the first PWA because generation requires the ArtWorks API.

**Decision:** when connectivity is unavailable, show a clear offline/network-unavailable state rather than attempting to make generation work offline.

Implication: offline application-shell caching is not itself a product requirement.

### Service Worker, background execution, and notifications

**Open capability investigation:** determine whether a Service Worker or related browser facilities can improve asynchronous task monitoring, background progress handling, and notifications.

Desired direction: if the target platform safely supports meaningful background work and/or completion notifications, use it.

Do not assume a Service Worker is a persistent backend or that iOS will keep it alive continuously. The implementation must degrade correctly when background execution or notifications are unavailable.

### Icon

**Decision:** do not create a temporary application icon. A final icon is currently being prepared and will be added when available.

### Standalone iOS appearance

**Decision:** standalone mode should visually blend with the existing dark application background and safe-area treatment.

### ArtWorks execution

**Decision:** the PWA should ultimately handle ArtWorks API calls itself rather than only launching the current Shortcut/Python execution path.

This is a target architecture, not yet an implementation claim. CORS, browser lifecycle, recovery, chain mode, downloads, and media-processing feasibility still require validation.

### Credential ownership and storage

**Decision:** use user-supplied ArtWorks credentials rather than shared application credentials.

Each user provides their own credentials in the PWA. They are retained only on that user's device and must never be committed to the repository or injected into the public GitHub Pages build.

Device-local persistence is desired so credentials do not need to be re-entered every launch. The exact browser storage mechanism still requires a security review; local persistence must be designed with the public/static-host and XSS threat model in mind.

**Known constraint:** GitHub Actions secrets or build-time environment variables do not remain secret after being emitted into browser-delivered HTML or JavaScript.

### File picker

**Decision:** preserve the current HTML file-selection behavior.

Do not redesign the picker during PWA bootstrap.

### Updates

**Decision:** newly deployed application versions should be picked up naturally on a later navigation/reload.

No custom "update available" UI is currently wanted.

### Cache strategy

**Open:** cache policy depends on whether a Service Worker is ultimately justified for lifecycle/background features.

Because there is no offline-generation requirement, do not start from an application-shell precache assumption.

### Custom installation UI

**Decision:** no custom Safari install button or banner for the initial version.

Use the normal browser/OS installation flow.

### Google Fonts dependency

**Open:** decide whether to retain the current external JetBrains Mono stylesheet, accept system fallback, or self-host later.

Because no offline mode is planned, this is not currently blocking PWA installation.

## 2026-08-07 — Product parity and task lifecycle decisions

### Functional parity target

**Decision:** target the same useful generation capabilities as the Python client rather than beginning with a deliberately reduced single-task product.

The existing Python implementation remains the behavioral reference for task submission, polling, chain/parallel semantics, recovery, validation, and progress reporting where those concepts translate to the browser.

### FFmpeg and output assembly

**Decision:** the PWA will not concatenate generated videos with FFmpeg.

Each ArtWorks output remains an independent downloaded media file. Browser parity does not require reproducing the Python client's local FFmpeg concatenation/assembly behavior.

### Completed-output handling

**Decision:** automatically download each completed API video output.

Do not require a separate manual-download queue for the initial design.

### Progress and history presentation

**Decision:** provide a task-progress/history view, but no embedded video gallery is required.

The important UI is the execution record: task/step state, progress, errors, and completed download status.

### Per-step timers

**Decision:** preserve detailed timing visibility.

Each execution should record and display useful phase timings, including the stages that can be observed from the browser/API flow, such as submission/upload preparation, queue/waiting, processing/generation, download, and total elapsed time. Exact phase labels must follow what can actually be measured rather than inventing provider-side timing that the API does not expose.

### Full session recovery

**Decision:** reopening the PWA should restore the full working session, not just finished history.

Persist enough state to recover:

- current configuration;
- prompt sets;
- active chain/parallel execution state;
- remote task IDs;
- last known statuses and timing data;
- completed and pending download state;
- execution history.

### Re-poll unfinished tasks

**Decision:** after reload/reopen, any previously submitted non-terminal ArtWorks task must be re-queried rather than duplicated.

Persist remote task IDs immediately after successful submission. Recovery must resume polling the existing task and must not create another potentially billable task merely because the PWA was interrupted.

This mirrors the reliability goal of the Python recovery state.

### Tabs / navigation

**Decision:** the PWA may move beyond the existing one-page layout where doing so improves operational clarity.

At minimum, progress/history can live in a dedicated tab or view rather than forcing all execution history into the configuration screen. Preserve the current visual language rather than redesigning the product gratuitously.

### Presets and imported settings

**Decision:** preserve the configuration ownership model used by the existing HTML launcher:

- application presets are built in, version-controlled, and immutable from the UI;
- the user can import an `artworks_settings` settings file;
- imported/current working configuration is stored locally for the PWA session/workspace.

The PWA should not turn built-in presets into user-editable records unless that is requested later.

### Chain failure and resume semantics

**Decision:** chain steps are recoverable independently.

If a step fails, the execution should be able to resume from the failed/incomplete step rather than requiring successful earlier steps to be submitted again.

Do not duplicate already completed billable work during recovery.

### Prompt and run history reuse

**Decision:** retain the prompts and relevant generation parameters associated with past executions.

History is not only an audit log: it should support reusing prior work.

**Decision:** the user should be able to select a previously executed prompt set and use it to pre-fill a new run configuration.

A previous run may therefore be duplicated/reused as the starting point for a new session without automatically resubmitting it.

## Questions still open after this session

The following remain discovery items rather than settled implementation claims:

1. Exact dedicated production and PR-preview URL layout for `pwa/` in the existing GitHub Pages workflow.
2. Whether direct browser-to-ArtWorks requests are permitted by the provider's CORS policy.
3. Exact secure device-local credential storage UX and threat model.
4. Which background execution, Background Sync, notification, and Web Push capabilities are dependable on the targeted iOS/PWA versions.
5. How automatic downloads behave in installed iOS PWAs and what user gesture/browser restrictions apply.
6. Which Python media-processing behaviors beyond concatenation are needed in browser form, and which should intentionally be omitted.
7. Exact persistent storage model for recovery/history, including whether IndexedDB should replace or supplement `localStorage` for structured task state.
8. Final application icon assets and manifest icon set.
9. Whether the external JetBrains Mono dependency should remain, fall back, or be self-hosted.
