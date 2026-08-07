<!-- VERSION$00003$ | Edited: 07/08 | TIME: 19:08 -->
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

## 2026-08-07 — Reliability boundary decisions

### Submission intent and orphan safety

**Decision:** persist a local submission-intent record before sending each potentially billable ArtWorks task-creation request.

The intent should include a client-generated UUID/correlation value, the local run/step identity, request fingerprint/parameters, and a wall-clock timestamp. After ArtWorks returns a task ID, update the same logical record immediately with that ID.

**Decision:** an ambiguous submission record with no returned task ID must never be blindly auto-resubmitted after restart. The first request may have created a billable task even though the response was lost.

**Open provider blocker:** determine whether ArtWorks provides task-creation idempotency, a queryable client request/correlation field, or authenticated task listing/search sufficient to recover the POST-accepted / ID-not-persisted orphan window.

Current project evidence does not establish those capabilities. `batchId` and `tags` must not be treated as idempotency/recovery keys without provider evidence.

### Completed-result retention

**Open provider blocker:** determine completed task retention, result-media retention, video URL lifetime, and whether re-fetching a completed task refreshes an expired result URL.

Foreground-only recovery is acceptable only if the provider's retention behavior covers realistic return intervals or exposes a reliable refresh/retrieval path.

### Browser storage persistence

**Decision:** use IndexedDB for structured non-secret task/run/history state and request persistent storage when supported.

**Decision:** on launch, call `navigator.storage.persisted()`; call `navigator.storage.persist()` only if persistence is not already granted.

Primary WebKit documentation states persistent mode is remembered across sessions, so unconditional `persist()` on every launch is not the documented requirement.

**Documented platform finding:** first-party storage for installed Home Screen web apps is explicitly exempt from WebKit ITP's historic seven-day script-writable-storage deletion rule. This does not eliminate other storage-loss scenarios, so state-loss UX remains required.

### Wall-clock recovery

**Decision:** all retry backoff, task timeout, priority-promotion, phase-duration, and progress timing logic must derive from persisted wall-clock timestamps.

Do not resume JavaScript tick counters after suspension. The callbacks stopped; real time did not.

If a remote state transition happened while the PWA was suspended and the provider does not expose an authoritative transition timestamp, show the timing as observed/derived rather than exact.

### Screen Wake Lock

**Decision:** Screen Wake Lock may be used as an optional attended-mode enhancement while the user intentionally watches an active generation.

It must not be described or implemented as background execution. Expect the lock to be released when visibility is lost and re-acquire only when the attended state still applies.

### Narrow notification relay

**Open architecture option:** preserve the possibility of a minimal push relay that stores only an opaque ArtWorks task/correlation identifier mapped to a Web Push subscription.

Such a relay would not hold the reusable ArtWorks credential, poll ArtWorks, fetch results, or store prompts/media. It becomes viable only if ArtWorks provides a trusted completion callback/webhook or equivalent provider-side event that can be registered/correlated from the device's own authenticated session.

Webhook/callback availability remains unknown.

## Questions still open after this session

The following remain discovery items rather than settled implementation claims:

1. Exact dedicated production and PR-preview URL layout for `pwa/` in the existing GitHub Pages workflow.
2. Whether direct browser-to-ArtWorks requests are permitted by the provider's CORS policy, including Basic `Authorization` preflight.
3. Whether ArtWorks task creation supports an idempotency key, unique client request ID, or another duplicate-safe submission mechanism.
4. Whether ArtWorks exposes task listing/search or queryable `tag`/`batchId`/correlation semantics suitable for recovering orphaned submissions.
5. Completed-task retention, result-media retention, result URL TTL, and result URL refresh behavior.
6. Whether ArtWorks exposes webhook/callback registration or another provider-side completion event, and its authentication model.
7. Exact secure device-local credential UX in installed Home Screen mode, including Password AutoFill behavior.
8. How automatic downloads behave in installed iOS PWAs and what user gesture/browser restrictions apply.
9. Reliable browser-native final-frame extraction from real ArtWorks result media for Chain mode.
10. Final application icon assets and manifest icon set.
11. Whether the external JetBrains Mono dependency should remain, fall back, or be self-hosted.
