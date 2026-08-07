<!-- VERSION$00001$ | Edited: 07/08 | TIME: 19:04 -->
# External Research Review — iOS PWA Background Execution

## Purpose

Review the user-supplied August 2026 research bundle on iOS PWA background execution and compare it with the project's existing PWA findings.

This document records what the new source set corroborates, what it adds, where it changes emphasis, and which conclusions should affect the Img2Video architecture.

No ArtWorks API request was made while preparing this review.

## Evidence discipline

The supplied research intentionally ranks Apple/WebKit/W3C-WICG material above secondary articles and community reports. That matches this project's evidence discipline.

For architecture decisions below:

- **Documented** means stated by Apple, WebKit, MDN, standards documentation, or another primary platform source.
- **Confirmed** means reproduced in this project or saved runtime evidence.
- **Inferred** means an architectural consequence derived from documented platform behavior plus current project constraints.
- **User-reported** means manually observed but not yet reproduced by saved project evidence.

Secondary sources remain useful for field failure modes, but must not override primary platform documentation when they conflict.

## Overall result

The external research strongly corroborates the project's current recovery-first PWA model.

The key conclusion remains:

> A pure iOS PWA cannot be treated as a continuously running background worker.

The Img2Video PWA should therefore reproduce the Python client's orchestration and recovery state machine, while treating foreground execution as opportunistic and suspension as normal.

The remote ArtWorks task continues independently after submission. What stops during iOS suspension is the local JavaScript that polls, downloads, extracts a chain transition frame, or submits the next dependent task.

## Where the external research matches our current findings

### Service Worker is not a daemon

**Documented / corroborated.** The supplied sources reinforce that a Service Worker is event-driven, short-lived, and browser-controlled. It cannot safely host an infinite loop, a persistent socket, or a self-scheduled polling process.

This exactly matches the current project rule: Service Worker memory is never authoritative task state.

### Background Sync is not an iOS solution

**Documented / corroborated.** Background Sync and Periodic Background Sync remain unavailable in WebKit/iOS and therefore cannot be the basis of Img2Video polling or chain progression.

Even where Background Sync exists, it is a retry/deferred-write mechanism, not a reliable multi-minute or multi-hour task monitor.

### Background Fetch is not the answer

**Documented / corroborated.** The platform does not provide a dependable iOS PWA Background Fetch facility that can own our long-running result download workflow.

Completed ArtWorks media export therefore remains a foreground/recovery operation for the pure PWA architecture.

### Push is server-triggered, not self-triggered

**Documented / corroborated.** Web Push can wake an installed Home Screen web app, but some external sender has to send the push. The device cannot use Push as its own periodic scheduler.

That means Push cannot replace direct polling unless another system knows when an ArtWorks task changed state.

### No silent Web Push

**Documented / corroborated.** The research strongly reinforces the `userVisibleOnly` model on iOS: classic Web Push must produce a visible notification.

Therefore Push is suitable for meaningful completion/failure notifications, not hidden periodic synchronization.

### Foreground reconciliation is mandatory

**Inferred / corroborated.** Reconcile authoritative remote state whenever execution returns:

- cold launch;
- `pageshow`;
- `visibilitychange` to visible;
- `online`;
- explicit refresh/retry;
- notification click or another future event that reopens/focuses the app.

This is the same model already selected for persisted ArtWorks task IDs.

## Important additions from the supplied research

### Declarative Web Push

The research adds a useful modern distinction.

**Documented:** Declarative Web Push is available for iOS/iPadOS Home Screen web apps from iOS 18.4. It allows the system to display the notification without starting JavaScript in a Service Worker.

Architecture consequence:

- use **Declarative Web Push** when the goal is purely to show a notification and no client-side logic must run;
- use **classic Web Push + Service Worker** only when a short event handler genuinely needs to execute before the visible notification.

Declarative Push is intentionally not a background-compute mechanism.

### iOS 26 installability change

**Documented:** Safari/WebKit 26 allows any site to be added to the Home Screen and opened as a web app; a manifest or Service Worker is no longer an installability prerequisite.

Architecture consequence:

The manifest remains valuable for Img2Video identity, name, icons, theme, start URL, scope, and cross-browser PWA semantics, but must not be justified by an obsolete claim that iOS requires it merely to install.

### Screen Wake Lock is a foreground extension only

**Documented:** Screen Wake Lock can help keep the app visible during an actively watched operation, but the lock is released when visibility is lost and it does not grant background execution.

Possible Img2Video role:

- optional user-controlled `Keep screen awake while monitoring` behavior during an active run;
- never a correctness dependency;
- never a substitute for persisted recovery state.

### `visibilitychange` as the last useful checkpoint

The supplied research highlights `visibilitychange` to hidden, with `pagehide` as a secondary signal, as the last useful foreground transition before likely suspension.

Possible Img2Video role:

- synchronously persist all in-memory task/run timestamps to IndexedDB;
- mark the local UI/session as entering background;
- cancel no remote work merely because visibility changed;
- optionally use `sendBeacon()` or `fetch(..., {keepalive:true})` only for small future telemetry/checkpoint messages if a backend ever exists.

For the current static/client-only design, IndexedDB persistence is more important than a network beacon.

### Avoid background keep-alive tricks

The supplied primary/community evidence reinforces that the following are architectural dead ends:

- `setInterval()` / `setTimeout()` heartbeat;
- Web Worker heartbeat;
- WebSocket/SSE/WebRTC keep-alive;
- silent looping audio;
- Screen Wake Lock as fake background execution;
- assuming a Service Worker stays alive;
- wrapping the site in WKWebView without moving the actual work to native code.

Do not spend implementation time on these techniques.

## Comparison with the user research's server-first recommendation

The supplied report correctly describes a server-owned loop as the most reliable architecture when the requirement is:

> continue arbitrary polling and follow-up work even when the phone is suspended, terminated, rebooted, unused, or offline.

That architecture would be:

```text
server/worker -> polls ArtWorks -> stores authoritative state -> sends Web Push
PWA           -> displays/reconciles state
```

For a general production monitoring product, this is the stronger background architecture.

However, Img2Video currently has a different selected trust boundary:

- each user supplies their own reusable ArtWorks credentials;
- those credentials should stay under the user's device/password-manager control;
- GitHub Pages remains a static frontend;
- no server-side credential owner has been selected.

Therefore the pure PWA baseline deliberately accepts a different tradeoff:

```text
PWA foreground -> submit ArtWorks task -> persist task ID
ArtWorks        -> continues remote task independently
PWA suspended   -> local polling/chain/download logic pauses
PWA foreground -> query same task ID -> reconcile -> continue
```

This is not guaranteed unattended background execution, but it is still correct and duplicate-safe if the state machine is designed properly.

## Why this maps well to the existing Python client

The current a-Shell Python client already contains the essential conceptual pattern:

- persist remote task IDs;
- track last activity/status;
- tolerate iOS suspension;
- resume by re-querying existing tasks;
- preserve completed work;
- avoid duplicate billable submissions;
- continue parallel work from saved task records;
- continue chain work from the next incomplete step.

The PWA can therefore port the **state machine**, while replacing the persistence and execution substrate:

| Python / a-Shell | PWA equivalent |
|---|---|
| JSON recovery file | IndexedDB |
| Python process loop | foreground JavaScript loop |
| `urllib` API requests | `fetch()` |
| thread pool | bounded Promise concurrency |
| terminal progress | task/history UI |
| elapsed timers | persisted timestamps + derived durations |
| resume after a-Shell suspension | reconcile on launch/visibility/online |
| FFmpeg final-frame extraction | browser video/canvas extraction, if validated |
| FFmpeg concatenation | intentionally omitted |

The architectural motto remains:

> Port the Python state machine, not the Python process.

## Chain mode implication

Chain mode is where foreground suspension matters most.

For independent/parallel tasks, all task IDs can be submitted and ArtWorks can continue every task while the PWA is suspended.

For a chain:

1. task N is submitted;
2. ArtWorks completes it remotely;
3. the PWA must obtain the result;
4. the PWA must extract the last frame;
5. the PWA must submit task N+1.

Steps 3-5 require local execution. If iOS suspends the app between steps 2 and 5, the chain pauses safely and resumes when foreground execution returns.

This is an acceptable product limitation if the UI makes it explicit and state recovery is reliable.

## Parallel mode implication

Parallel mode maps particularly well to a PWA.

Once all independent task IDs have been created and persisted, no local process needs to remain alive for ArtWorks to keep generating them.

On the next foreground reconciliation, each saved ID can independently become:

- still pending;
- processing;
- completed and ready for download;
- failed/canceled/timeout;
- temporarily unknown because of a transient request error.

This closely matches the current Python parallel recovery behavior.

## Web Push role for Img2Video

The supplied research makes the recommended role precise:

> Push is for humans, not for polling.

Potential future Push events:

- `Generation completed`;
- `Generation failed`;
- `All parallel tasks completed`;
- possibly `Chain step ready — open Img2Video to continue` if no server can perform the next chain transition.

But some external system still needs a legitimate signal that the task changed state.

Potential sources remain:

1. an ArtWorks webhook/callback;
2. a provider-issued scoped/delegated token usable by a minimal relay;
3. a future server architecture that intentionally owns polling.

None of those has been selected yet.

## Native fallback

The supplied research also correctly notes that even a native iOS app does not gain a guaranteed arbitrary scheduler.

A native shell could provide opportunistic improvements such as:

- BGAppRefreshTask;
- BGProcessingTask;
- background URLSession for file transfer;
- silent/background push under native rules.

But those still do not provide guaranteed periodic execution at an exact interval.

Therefore a native wrapper should not be introduced merely to chase a false promise of permanent background execution.

Keep native as a future option only if a specific missing capability justifies its complexity.

## Updated recommended baseline

For Img2Video PWA v1:

1. Use the existing Python client as the orchestration/recovery behavioral reference.
2. Persist run/task state in IndexedDB before each non-idempotent transition.
3. Persist each ArtWorks task ID immediately after submission.
4. Poll only while useful foreground execution exists.
5. On `visibilitychange` to hidden, flush state to IndexedDB; do not cancel remote tasks.
6. On foreground/launch/online, reconcile every non-terminal saved task ID.
7. Derive timers from persisted timestamps rather than active JS timers.
8. Treat Parallel mode as naturally suspension-tolerant after submission.
9. Treat Chain mode as pause-and-resume between dependent steps.
10. Download/export completed outputs when foreground execution is available and persist export state for retry.
11. Do not add Background Sync/Periodic Sync/keep-alive hacks for iOS.
12. Add a Service Worker only for a concrete event-driven role such as Push/notification handling.
13. Consider optional Screen Wake Lock only as a foreground UX control.
14. Revisit server-side polling only if guaranteed unattended completion follow-up becomes a product requirement.

## Primary sources highlighted by the supplied research

The following primary sources should be preferred when future platform claims are updated:

- WebKit — Web Push for Web Apps on iOS and iPadOS: https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/
- WebKit — Features in Safari 16.4: https://webkit.org/blog/13966/webkit-features-in-safari-16-4/
- WebKit — Meet Declarative Web Push: https://webkit.org/blog/16535/meet-declarative-web-push/
- WebKit — Features in Safari 18.4: https://webkit.org/blog/16574/webkit-features-in-safari-18-4/
- Apple Developer WWDC25 — Learn more about Declarative Web Push: https://developer.apple.com/videos/play/wwdc2025/235/
- WebKit — Features in Safari 26.0: https://webkit.org/blog/17333/webkit-features-in-safari-26-0/
- WebKit standards position — Web Background Synchronization: https://github.com/WebKit/standards-positions/issues/14
- Apple Developer Forums/DTS background-execution guidance cited in the supplied research bundle.

Secondary compatibility/community sources are useful for field reports but should remain secondary to Apple/WebKit documentation.

## Remaining validation items

The research resolves the generic iOS background-execution question sufficiently for architecture planning. The project-specific questions that remain are:

1. ArtWorks CORS/preflight support from the GitHub Pages PWA origin.
2. ArtWorks webhook/callback or scoped/delegated authentication availability.
3. Browser-native last-frame extraction reliability on actual ArtWorks MP4 outputs.
4. Automatic download/export behavior in an installed iOS PWA.
5. Password AutoFill behavior in the installed PWA context.
6. Whether Screen Wake Lock materially improves the desired user experience without unacceptable battery cost.
7. Web Push lifecycle/reliability on the target device if notification work is implemented.
