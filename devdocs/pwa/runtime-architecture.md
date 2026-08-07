<!-- VERSION$00001$ | Edited: 07/08 | TIME: 20:05 -->
# PWA Runtime Architecture

## Purpose

Define the current production-oriented browser architecture for Img2Video after the August 2026 discovery work.

This document consolidates the selected runtime model. It distinguishes project decisions from provider/platform evidence and does not treat undocumented ArtWorks capabilities as available.

No ArtWorks generation request was made while preparing this document.

## Evidence vocabulary

Use the repository evidence labels consistently:

- **Documented** — stated by the authenticated provider schema or primary platform/library documentation.
- **Confirmed** — observed in a saved provider response, measured output, or inspected implementation artifact.
- **Inferred** — architecture conclusion from documented/confirmed behavior that has not itself been reproduced end to end.
- **User-selected** — product or architecture decision supplied by the project owner.
- **Not documented** — absent from the current authenticated provider contract; this is deliberately narrower than claiming the capability can never exist privately or in a newer contract.
- **Unknown** — no sufficient project evidence yet.

## Core principle

**User-selected:** the reconciler is the center of the PWA, not the poll loop.

The PWA is a durable local state machine over remote ArtWorks tasks. Foreground polling is an optimization that makes the UI responsive while the application is active. Correctness must remain the same if the foreground poll loop never gets another JavaScript timeslice.

Conceptually:

```text
user intent
    |
    v
durable IndexedDB ledger
    |
    v
executor creates remote work
    |
    v
remote task IDs bound into ledger
    |
    +-----------------------------+
    |                             |
    v                             v
foreground polling          suspension / close / reboot
    |                             |
    v                             v
ledger updates             reopen / visible / online
                                  |
                                  v
                              reconciler
                                  |
                                  v
                        query authoritative remote state
                                  |
                                  v
                        advance only missing local work
```

## 1. Credential layer

**User-selected:** persistent reusable ArtWorks secrets belong to the system password manager, not the PWA's own durable data store.

Preferred flow:

1. semantic username/password fields allow Safari/system Password AutoFill;
2. after fill/unlock, credentials exist only in active application memory;
3. IndexedDB records never contain the reusable ArtWorks password;
4. after a cold start, durable task records may exist while credentials are locked.

A locked credential state is normal application state. A known remote task must display an authentication-required/locked condition rather than being marked failed or missing merely because the credential is not currently available.

Raw `localStorage` is not an acceptable credential store. Encrypted IndexedDB remains only a fallback architecture if Password AutoFill proves insufficient on the target installed-PWA configuration.

## 2. Durable ledger

**User-selected:** use IndexedDB as a run/step/task ledger.

Recommended logical hierarchy:

```text
Run
  -> Step
      -> Task
```

A task record should carry at least:

```text
localRunId
localStepId
clientSubmissionUuid
requestFingerprint
taskType
status
remoteTaskId | null
intentAt
submitStartedAt | null
remoteIdBoundAt | null
lastPollAt | null
nextEligibleActionAt | null
phaseObservedAt | null
terminalObservedAt | null
resultUrl | null
exportState
errorEvidence
```

The request fingerprint should describe the request identity without persisting full image bytes. It can include normalized non-secret generation parameters and a digest/identity for the source image where useful.

### Submission intent ordering

The ledger transaction establishing submission intent must commit **before** every potentially billable `POST /api/v3/tasks`.

After the provider returns `{id}`, bind that remote ID to the same logical record immediately before beginning normal polling or any dependent action.

This does not remove the distributed-systems ambiguity between provider acceptance and local persistence, but it makes the ambiguity explicit and auditable.

### Storage persistence

On launch:

```text
navigator.storage.persisted()
    -> if false, navigator.storage.persist()
```

Do not repeatedly request persistence when it is already granted.

OPFS is available in WebKit/iOS and may be used for private staging of larger media files, but it remains origin-private browser storage rather than a user-visible Files location. IndexedDB remains the authoritative structured ledger.

## 3. Reconciler

**User-selected:** the reconciler owns correctness.

Run reconciliation on at least:

- cold start;
- `visibilitychange` when the document becomes visible;
- `online` when network connectivity returns.

`pageshow` is also a useful implementation hook for browser lifecycle restoration and can trigger the same idempotent reconcile operation.

For every non-terminal ledger item:

1. inspect whether a remote task ID is known;
2. if known and credentials are available, query `GET /api/v3/tasks/{id}`;
3. update observed state/timestamps;
4. perform only the next missing local action;
5. never infer that missed JavaScript timers imply missed remote work.

All backoff, timeout, priority-promotion, and phase timing decisions must be recomputed from persisted wall-clock timestamps and `Date.now()`.

### Status model

The authenticated OpenAPI task-info schema documents:

```text
canceled
completed
failed
pending
preparing
processing
timeout
unknown
```

Terminal states remain:

```text
completed
failed
canceled
timeout
```

`preparing` and `unknown` are therefore not terminal merely because the shorter AGENTS lifecycle summary omits them. The current Python client already treats `unknown` with a bounded poll budget and includes `preparing` among cancelable queued states.

The PWA should preserve the same defensive distinction:

- `pending`, `preparing`, `processing` — continue/reconcile according to elapsed wall time;
- `unknown` — non-terminal initially, subject to a bounded consecutive-observation/request budget and preserved task ID;
- terminal states — persist terminal evidence and stop remote polling.

## 4. Executor and orphan strategy

### Serialized creation

**User-selected:** serialize potentially billable task creation even when the logical run is parallel.

Parallel mode may have many already-created remote tasks in flight, but only one new task-creation POST should be in the ambiguous submission window at a time.

This bounds the orphan blast radius to one submission rather than allowing N simultaneous POST outcomes to become ambiguous during interruption.

Once task IDs have been durably captured, status polling and completed-output handling may proceed concurrently with bounded concurrency.

### Ambiguous submission

If the network/page disappears after a POST may have been accepted but before a remote ID is durably bound:

```text
status = ambiguous-submit
```

Do **not** automatically resubmit.

The current authenticated provider contract does not document:

- creation idempotency;
- an `Idempotency-Key` contract;
- a duplicate-safe client request ID;
- `GET /api/v3/tasks` listing/search;
- a task query/filter operation by tag, batch, time, or client correlation value.

Therefore the current production architecture must work without those capabilities.

A local `clientSubmissionUuid` is still required for ledger identity. A deterministic non-secret ArtWorks tag such as `pwa-step:<uuid>` is reasonable forward-compatible correlation material because tags are documented, but the current contract exposes no retrieval operation that makes the tag an orphan-recovery mechanism.

Do not add an undocumented `Idempotency-Key` header by default. Besides lacking a provider contract, an extra request header changes the browser CORS preflight requirements. It may be tested later only as an explicit provider-compatibility experiment.

### User disposition

When a submission remains ambiguous and no provider recovery primitive exists, expose explicit user disposition instead of silently spending again. Preserve enough request evidence for the user to decide whether to abandon the local intent or deliberately create a replacement task.

## 5. Async endpoint choice

**Documented:** `/api/v3/tasks-sync` is intended for testing/debugging; `/api/v3/tasks` is the production integration path.

**Inferred reliability consequence:** asynchronous task creation is also the safer iOS lifecycle shape.

`POST /api/v3/tasks` returns a task ID quickly, allowing the client to durably bind remote identity before the long generation period.

By contrast, a synchronous request holds the HTTP transaction open while generation runs. If iOS suspends/terminates the page or the connection dies before the response is received, the browser may have no locally captured task ID even if remote work already occurred.

Therefore production PWA code must use the asynchronous endpoint.

## 6. Provider surface assumptions

The authenticated task surface currently documented for orchestration is:

```text
POST /api/v3/tasks
POST /api/v3/tasks-sync
GET  /api/v3/tasks/{task}
POST /api/v3/tasks/{task}/cancel
POST /api/v3/tasks/{task}/priority
GET  /api/v3/resources
```

The current architecture deliberately does not depend on undocumented collection listing, idempotency, usage/balance lookup, or webhook registration.

### `run-ffmpeg`

The authenticated task-type enum includes `run-ffmpeg`.

That establishes only that `run-ffmpeg` is a known task type in the generic task API. Current project evidence does **not** yet establish its payload schema, account entitlement, URL-to-URL behavior, output retention, billing model, or cost per invocation.

It is therefore not a dependency of the PWA Chain architecture. It can be investigated separately if future server-side transforms or assembly become desirable.

## 7. Background execution and notifications

The PWA must assume foreground execution can disappear at any time.

Correctness therefore does not depend on:

- Service Worker persistence;
- Background Sync;
- Periodic Background Sync;
- looping timers;
- WebSockets/SSE remaining alive;
- Wake Lock.

Screen Wake Lock is an attended-mode UX enhancement only.

### Relay status

A credential-free notification relay remains conceptually safe only if the provider can emit a trusted completion event carrying an opaque task/correlation value.

Webhook/callback registration is **not documented** in the current authenticated ArtWorks contract.

Therefore a notification relay is removed from the active implementation stages. Revisit it only if a newer/provider-specific contract establishes a trusted callback mechanism. Do not move reusable ArtWorks credentials to a relay merely to regain polling.

## 8. Output retrieval and export

Treat output completion, browser staging, and user-visible export as separate durable states:

```text
remote-completed
    -> result-retrievable
    -> staged
    -> exported
```

### Staging candidate

OPFS is a suitable browser-private staging candidate for completed video bytes because WebKit supports the origin private file system on iOS.

A robust download path should prefer streaming/bounded memory where browser APIs permit:

```text
fetch result
  -> validate HTTP/content type
  -> stream chunks to staging
  -> verify received byte count when trustworthy length metadata is available
  -> finalize staging record
  -> user-initiated export/share/save
```

For cross-origin media, JavaScript can only inspect headers such as `Content-Length` if CORS exposes them. Do not make byte-count verification depend on a header that the result origin does not expose.

Reject clearly non-video content types and HTML/error payloads rather than persisting them as successful videos.

The final save/share behavior on installed iOS PWAs still requires physical-device validation.

## 9. Chain media path

**User-selected:** no FFmpeg/ffmpeg.wasm for normal Chain advancement.

Preferred implementation candidate:

```text
ArtWorks MP4 result URL
    -> Mediabunny UrlSource
    -> Input({ formats: [MP4] })
    -> primary video track
    -> track.canDecode()
    -> VideoSampleSink.getSample(Infinity)
    -> final VideoSample in presentation order
    -> canvas draw
    -> JPEG/PNG Blob
    -> persist transition artifact/state
    -> next asynchronous ArtWorks POST
```

The supplied Mediabunny guide explicitly documents:

- lazy/partial input reads;
- MP4-specific import selection for tree shaking;
- remote `UrlSource` with an 8 MiB default cache;
- optimized network prefetching;
- `canDecode()` against the actual track/browser;
- `VideoSampleSink` presentation-order semantics;
- `getSample(Infinity)` for the last decoded sample;
- explicit `VideoSample.close()` and `Input.dispose()` cleanup.

### Project-specific Mediabunny constraints

- import only the MP4 input format needed for ArtWorks output; do not use `ALL_FORMATS` in production Chain code;
- override `UrlSource`'s default infinite retry behavior with a bounded project retry policy;
- close each decoded sample as soon as its image has been exported;
- dispose the `Input` after the transition frame is no longer needed;
- pin/vendor the reviewed dependency under `pwa/`; do not load credential-adjacent runtime JavaScript from a third-party CDN;
- keep expensive packet-statistics scans out of the Chain hot path unless explicitly needed for diagnostics.

Fallback/debug layers:

1. MP4Box.js + direct WebCodecs for low-level demux/decode investigation;
2. `<video>` + canvas for the simplest browser-native compatibility prototype.

## 10. Orion/iOS extension lessons

The inspected Orion extensions demonstrate two useful but distinct browser capability levels:

### RedGifs Downloader for Orion 1.1.7

Confirmed from the uploaded package:

- Manifest V3 extension;
- explicit RedGifs API/media host permissions;
- `downloads` permission;
- background service worker;
- content script resolves a direct RedGifs MP4 URL;
- background code delegates the URL to `downloads.download()`.

It does not parse, decode, transcode, or otherwise process the MP4 bytes in JavaScript.

This proves that an extension can use privileged host/download APIs, **not** that the same cross-origin URL is fetchable by an ordinary GitHub Pages PWA.

### Orion Lite AutoNext 0.2.19

Confirmed from the uploaded package:

- only `storage` permission;
- content scripts operate on the page's existing `HTMLVideoElement`;
- playback, seeking, playback rate, sizing, inline playback, and lifecycle events are browser-owned operations;
- no media-byte fetch/parse/decode pipeline exists in the extension.

The implementation explicitly applies `playsinline`/`webkit-playsinline` and uses bounded autoplay attempts instead of treating iOS media activation as guaranteed.

### Architectural consequence

Use the browser's native video element for everything it already does well: playback, attended preview, seeking UI, dimensions, and lifecycle presentation.

Bring media bytes into JavaScript only where the product genuinely requires it—currently exact Chain final-frame extraction and optionally validated staged downloads.

Do not use Orion extension behavior as evidence that PWA CORS or the `downloads` extension API exists in Safari Home Screen web apps.

## 11. Python/PWA boundary

The PWA is the intended production interaction surface, but it is not a wholesale replacement for the diagnostic Python runtime.

### PWA owns

- user workflow;
- credentials unlock/use in memory;
- durable ledger and reconciliation;
- submission/polling/cancel/priority controls;
- run history;
- Chain transition-frame extraction;
- normal output staging/export.

### Python + probes retain

- authenticated provider discovery;
- reproducible contract probing;
- `ffprobe`-grade media measurement;
- exact codec/container investigation;
- regression evidence and saved diagnostic artifacts;
- experiments that need shell/native tools.

Mediabunny can expose codec strings, dimensions, duration, packet count, average FPS/bitrate, timestamps, and decoded samples, but those browser observations are not automatically equivalent to every measurement required by AGENTS.md.

## 12. Implementation stages

### Stage 0 — non-billable viability gates

No production PWA submission code is justified until:

1. browser CORS/preflight to the ArtWorks task API is tested from the intended Pages origin;
2. result-media JavaScript access/partial reads are tested against an already-paid completed result where possible;
3. origin/deployment trust is settled so fork/PR preview origins do not receive real credentials accidentally;
4. the pinned Mediabunny subset can decode/export a representative local H.264 MP4 fixture on the target iPhone.

These are go/no-go gates, not performance tuning.

### Stage 1 — single prompt

Implement credential flow, durable ledger, reconciler, one serialized async submission, polling, completed-result staging, and explicit export.

No Chain dependency is required.

### Stage 2 — multi-prompt/parallel

Create tasks serially, then allow bounded concurrent polling/output handling after each remote ID has been durably bound.

Partial completion is a valid run outcome; completed work remains independently useful.

### Stage 3 — Chain

Enable only after a local decode/export self-test succeeds on the device.

Use Mediabunny for the exact final presentation frame and persist the transition image/state before creating the dependent next task.

### Relay/server stage

Not currently planned under device-owned credentials because provider webhook/callback registration is not documented. Reopen the decision only if the provider contract changes.

## 13. Remaining highest-value unknowns

1. **ArtWorks API CORS/preflight** from the real intended production origin.
2. **ArtWorks result-media CORS/partial-read behavior** for Mediabunny/browser JavaScript.
3. **Completed-task/result retention and URL refresh** — whether re-querying a known completed task remints/refreshes a usable media URL.
4. **Physical-device Password AutoFill behavior** in installed Home Screen mode.
5. **Installed-PWA export/save UX** on the target iPhone.
6. **Mediabunny real ArtWorks decode** on representative Wan/LTX outputs.
7. **`run-ffmpeg` entitlement/payload/cost**, only if a future server-side media operation is desired.

## Validation status

Verified while consolidating this architecture:

- current branch AGENTS.md was re-read;
- authenticated OpenAPI evidence was re-checked for task statuses and task types;
- current PWA discovery documents were re-read before editing;
- the uploaded Mediabunny full guide was reviewed;
- both uploaded Orion extension ZIPs were inspected directly for manifests and media-related code paths.

Not verified:

- live ArtWorks CORS behavior;
- result URL TTL/refresh;
- real ArtWorks MP4 decoding through Mediabunny on the target iPhone;
- iOS installed-PWA output export behavior;
- private/newer provider capabilities not present in the authenticated contract.

No ArtWorks generation request was made and no potentially billable task was submitted.
