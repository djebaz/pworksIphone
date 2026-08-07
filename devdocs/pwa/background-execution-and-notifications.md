<!-- VERSION$00001$ | Edited: 07/08 | TIME: 18:53 -->
# PWA Background Execution, Notifications, and Recovery

## Status

Architecture research for the Img2Video PWA. This document records current browser-platform evidence and the recommended baseline for long-running ArtWorks tasks on iPhone/iPad and other PWA-capable browsers.

No ArtWorks task was submitted while preparing this report.

## Executive conclusion

The PWA must not depend on a Service Worker remaining alive to poll a long-running ArtWorks task.

A Service Worker is event-driven and may be terminated when idle. Its in-memory state and timers are not a durable execution environment. The portable architecture is therefore:

1. submit a task while the application is active;
2. persist the remote task ID and timestamps immediately;
3. poll while the application remains active;
4. tolerate suspension or termination at any point;
5. reconcile every non-terminal task when the application becomes active again;
6. download completed outputs when the application can run in the foreground;
7. add Web Push later only if there is a reliable external event source that can tell a push sender when an ArtWorks task reached a meaningful state.

This is a recovery-first design rather than a continuous-background-process design.

## Evidence labels

The project evidence vocabulary is used below:

- **Documented** — stated by platform/vendor documentation.
- **Confirmed** — observed directly in this repository or a saved runtime result.
- **Inferred** — an architecture recommendation derived from documented capabilities and current project constraints.
- **User-reported** — manually observed by the user but not reproduced by saved automated evidence.

## Service Worker lifecycle

**Documented:** a Service Worker is not a daemon. The browser controls its lifetime, starts it for events, and may terminate it when idle. Code must not rely on global variables, `setInterval()`, or other in-memory state surviving between events.

**Inferred implementation rule:** all durable Img2Video execution state belongs in persistent browser storage. Service Worker memory may be used as a temporary optimization but never as the source of truth.

A Service Worker can still be valuable for:

- Web Push event handling;
- notification click handling;
- optional retry hooks on browsers that implement Background Sync;
- communication with visible application windows;
- future cache behavior if a concrete requirement appears.

It should not be introduced as a fake persistent task runner.

## Background Sync

**Documented:** Background Sync is intended to defer/retry failed outgoing work until connectivity returns. Browsers bound the lifetime and retry behavior of sync events.

**Documented platform constraint:** current Safari/iOS Safari does not provide Background Sync support comparable to Chromium.

**Inferred use for Img2Video:** on Chromium, Background Sync could later improve retry of a failed network submission or another idempotent write. It should not own task-status polling, because polling an ArtWorks generation may last far longer than a sync event and the API is unavailable on the primary iOS target.

Do not add Workbox only for Background Sync. Plain browser APIs are sufficient for the current architecture, and iOS still requires the recovery path.

## Periodic Background Sync

**Documented:** Periodic Background Sync is best-effort, permission/engagement dependent, and does not promise precise intervals.

**Documented platform constraint:** current Safari/iOS Safari does not support Periodic Background Sync.

**Decision consequence:** do not design task polling around periodic sync and do not present it as an iPhone background-monitoring solution.

## Background Fetch

**Documented:** Background Fetch is designed for user-visible long-running transfers rather than arbitrary background computation. It remains limited/experimental across the web platform and is not a dependable iOS baseline.

**Inferred use for Img2Video:** it is not required for the first PWA. Completed result transfer should use a foreground download/export flow with durable state so an interrupted export can be retried later.

## Web Push and notifications on iPhone/iPad

**Documented by WebKit:** Home Screen web apps on iOS/iPadOS 16.4 and later can use the standards-based Push API, Notifications API, and Service Workers for Web Push.

**Documented:** notification permission must be requested from a direct user interaction. Push delivery is designed to wake the Service Worker even when the application page is not currently open.

**Documented:** Web Push on Safari/iOS is not a silent background-execution channel. A push event must result in a user-visible notification. Push must therefore be used for meaningful user notifications, not as a hidden periodic wake-up mechanism.

### Required push architecture

A browser subscription alone is not enough. A push sender must possess the user's push subscription and send a message through the web-push service when there is something meaningful to report.

Typical architecture:

```text
ArtWorks state change
        |
        v
completion-event source
        |
        v
push sender / relay
        |
        v
Web Push service
        |
        v
installed PWA Service Worker
        |
        v
visible notification
```

The static GitHub Pages PWA cannot itself be the always-running push sender.

## Interaction with the device-local credential decision

The selected project direction is that each user supplies their own ArtWorks credentials and those credentials remain on that user's device.

That creates an important boundary:

- a remote push relay that does **not** possess the ArtWorks credential cannot independently poll the user's ArtWorks task;
- sending the reusable ArtWorks username/password to a remote relay would violate the selected credential architecture;
- using Web Push merely to wake the PWA and secretly poll is not suitable on iOS because push events must be user-visible.

### Best possible push design

The cleanest future design would be a provider-side completion event such as a webhook/callback, or a provider-supported scoped/delegated token that can be used by a minimal relay without holding the user's reusable password.

Current project documentation and the web research performed for this discovery did not identify an authoritative ArtWorks webhook/callback mechanism.

**Status: Unknown.** Absence from the sources searched is not proof that ArtWorks lacks such a feature. Do not claim either availability or non-availability until provider documentation or a reproducible endpoint is found.

If ArtWorks later provides an appropriate callback, a small relay can map the callback to a Web Push subscription and send a meaningful `completed` or `failed` notification without taking ownership of the user's main credential.

## Recommended task orchestration model

### Foreground behavior

While the PWA is visible/active:

- submit tasks;
- save the task ID before starting normal polling;
- poll with bounded retry/backoff behavior;
- record status transitions and phase timestamps;
- download completed output automatically where browser behavior permits;
- update history immediately.

### Suspension behavior

Assume the browser may suspend the page or Service Worker without warning.

Do not treat suspension as task cancellation. The remote task continues independently at ArtWorks.

### Reconciliation triggers

Reconcile non-terminal local records whenever useful execution becomes available again, including:

- initial application launch;
- `pageshow`;
- transition to `document.visibilityState === "visible"`;
- browser `online` event;
- explicit user refresh/retry;
- a future Service Worker message after a meaningful push event.

Reconciliation means querying the existing remote task ID. It must not create a duplicate billable task.

## Persistent state

Use IndexedDB for structured execution state rather than making `localStorage` the task database.

Recommended logical stores:

- `runs` — one user-visible execution/session and its prompt ordering;
- `tasks` — remote task IDs, status, retry metadata, parameters, and timestamps;
- `artifacts` — result URL, download/export state, local staging metadata, hashes where available;
- `promptSets` — reusable historical prompt sets and associated generation parameters;
- `settings` — non-secret user/application settings;
- secret material — separate from ordinary task state and governed by the security architecture document.

Consider requesting persistent storage with `navigator.storage.persist()` after the user has created important durable state, rather than on first page load. The request may be granted or denied; recovery must remain understandable either way.

## Timers and progress

The UI wants per-step timers. Those timers must be derived from persisted timestamps, not from the assumption that a JavaScript timer continued while the app was backgrounded.

Example persisted timestamps include:

- local preparation started/completed;
- submission started;
- task ID received;
- first observed `pending`/queue state;
- first observed `processing` state;
- terminal state observed;
- download started/completed.

On reopen, compute elapsed durations from these timestamps. If the API did not expose the exact transition while the PWA was suspended, label the timing as observed/derived rather than pretending the transition time is exact.

## Chain mode

The Python client currently extracts a completed video's final frame through FFmpeg and submits that frame as the next chain input.

The PWA intentionally will not ship FFmpeg merely for parity.

A browser-native foreground candidate is:

1. obtain the completed video as a same-origin/Blob-backed media source where possible;
2. load it into a hidden `HTMLVideoElement` with `playsinline`;
3. seek near the final decodable video frame;
4. synchronize frame access using `requestVideoFrameCallback()` where supported;
5. draw the current frame to a canvas;
6. export the canvas to a Blob for the next ArtWorks request.

Modern Safari also exposes WebCodecs capabilities, but WebCodecs is a lower-level fallback/optimization rather than the first implementation choice.

**Inferred constraint:** automatic chain continuation is initially a foreground feature in the pure client architecture. It should pause cleanly if the page is suspended and resume from persisted state when the PWA is active again. A Service Worker should not be expected to run DOM video/canvas extraction in the background.

## Completed output downloads

The user-selected behavior is automatic download of every independent completed API output.

On iOS, do not assume that a closed/suspended PWA can silently save arbitrary completed files to the user's Files/Downloads location. The File System Access `showSaveFilePicker()` API is not a portable Safari/iOS solution.

Recommended behavior:

- while foregrounded, fetch the completed result and trigger a normal Blob/download export when allowed;
- keep download/export state durable so failures can be retried;
- optionally stage large completed media in Origin Private File System (OPFS) where supported if that proves useful for retry/recovery;
- if a task completes while the PWA is suspended, discover that completion on the next reconciliation, then perform the export;
- if future Web Push is available, a completion notification can open/focus the PWA, which then re-checks authoritative state before exporting.

Physical-device testing is required because iOS download UX and user-gesture behavior can differ from desktop Chromium.

## Offline state

There is no product requirement for offline generation or shell caching.

The PWA should still communicate network state clearly. `navigator.onLine` is only a hint; actual request failure is authoritative. Preserve pending remote task IDs and retry reconciliation when connectivity returns.

A future Service Worker may therefore exist with no application-shell cache at all if its only concrete role is Push/notification handling.

## GitHub Pages and PR preview isolation

The runtime source will live at repository-root `pwa/` and the PWA should be published under a dedicated Pages path.

Preferred deployment layout:

```text
Production:
https://djebaz.github.io/pworksIphone/pwa/

PR preview:
https://djebaz.github.io/pworksIphone/preview/pr-<number>/pwa/
```

Use relative PWA URLs wherever possible:

- manifest link: `./manifest.webmanifest`;
- `start_url`: `./`;
- `scope`: `./`;
- Service Worker registration, if introduced: `./service-worker.js` with `scope: "./"`;
- icons: relative to the manifest/PWA directory.

This keeps a PR-preview Service Worker scoped to that preview and prevents it from controlling production.

Manifest application identity also needs deliberate preview handling. A hard-coded production manifest `id` reused by every PR preview can make browsers treat preview and production as the same installed application. Prefer either an environment-specific generated `id` or, initially, omit `id` so it resolves from each deployment's own `start_url`.

## Capability summary

| Capability | iOS PWA baseline | Role in Img2Video |
|---|---|---|
| Foreground polling | Yes | Primary live monitoring |
| Persisted task-ID recovery | Yes | Mandatory correctness mechanism |
| Service Worker persistent loop | No | Must not be assumed |
| Background Sync | Not an iOS baseline | Optional Chromium retry enhancement only |
| Periodic Background Sync | Not an iOS baseline | Do not use for task polling |
| Background Fetch | Not dependable cross-platform/iOS baseline | Not required initially |
| Web Push | Yes for installed Home Screen web apps on modern iOS | Valuable future completion/failure notification path |
| Silent push polling | No | Do not implement |
| Notification click -> reopen/reconcile | Yes with Web Push architecture | Recommended future flow |
| Background chain media processing | Not a dependable pure-PWA capability | Foreground/recovery model |

## Recommended implementation tiers

### Tier 1 — required baseline

- no assumption of background execution;
- IndexedDB task/run persistence;
- task IDs saved immediately;
- foreground polling;
- resume/re-poll on reopen;
- timestamp-derived progress timers;
- automatic foreground downloads with retry state;
- clear offline/network status.

### Tier 2 — Service Worker foundation

Add a minimal Service Worker only when one of its concrete event-driven capabilities is implemented. Do not add offline caching by default.

Potential responsibilities:

- receive Push events;
- show notifications;
- handle notification clicks;
- message an open PWA window;
- optional Chromium-only Background Sync for retryable outbound operations.

### Tier 3 — true completion notifications

Add only when there is a trustworthy external completion signal, such as an ArtWorks webhook/callback or an appropriately scoped provider credential available to a minimal relay.

The push relay should store only what it needs to deliver the notification and must not receive the user's reusable ArtWorks password under the selected architecture.

## Research sources

Primary platform references reviewed for this report:

- MDN, Offline and background operation / Background Sync / Periodic Background Sync / Background Fetch / Push and Notifications.
- MDN, Service Worker API lifecycle and global-scope lifetime guidance.
- WebKit, "Web Push for Web Apps on iOS and iPadOS".
- Apple Developer, web push notification guidance.
- Can I Use compatibility data for Background Sync, Periodic Background Sync, WebCodecs, and File System Access.
- web.dev, Service Worker lifecycle/storage guidance and persistent storage guidance.
- Workbox documentation, Background Sync queue/replay behavior (evaluated as a pattern, not selected as a dependency).
- `web-push-libs/web-push` and small iOS Web Push example repositories for the standard client-subscription/server-sender architecture.
- MDN video/canvas and `requestVideoFrameCallback()` documentation for browser-native chain-frame extraction.
- OWASP HTML5 Storage and Content Security Policy guidance, referenced by the separate security document.

## Validation still required

The following must be tested before implementation claims are upgraded:

- ArtWorks browser CORS/preflight behavior for the GitHub Pages origin;
- whether ArtWorks provides a webhook/callback or scoped/delegated auth mechanism not present in current project evidence;
- real-device iPhone behavior for automatic downloads from an installed Home Screen PWA;
- reliable last-frame extraction from actual ArtWorks result media on target iOS versions;
- Web Push subscription/notification lifecycle on the target device if notification work proceeds.
