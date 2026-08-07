<!-- VERSION$00002$ | Edited: 07/08 | TIME: 20:09 -->
# Python Runtime to PWA Parity Analysis

## Purpose

Compare the current `app/img2video_iphone.py` execution model with the selected browser/PWA runtime and identify direct parity, intentional changes, and responsibilities that remain Python/probe-only.

This document is architecture analysis only. No ArtWorks request was made and no potentially billable task was submitted.

The current consolidated browser architecture is defined in [`runtime-architecture.md`](runtime-architecture.md).

## Executive conclusion

The PWA can reproduce most of the Python client's **ArtWorks orchestration state machine**, but it should not reproduce the Python process model.

The central browser rule is now stronger than the earlier polling-oriented comparison:

> **The durable ledger + reconciler owns correctness; foreground polling is only an optimization.**

The remote ArtWorks task continues independently while either a-Shell or a PWA is suspended. The browser must assume suspension is normal and make every externally meaningful transition reconstructible from durable state.

## Current Python reliability model

The Python client contains both process-local and persistent recovery mechanisms.

### Process-local state

The current client uses structures such as `TRACKED_TASKS` for IDs that matter while the process is alive.

That process-local structure disappears when the Python process exits.

### Persistent recovery

The current settings/runtime also support persisted recovery state (`resumeInterruptedTasks`, `artworks_tasks.json`) and save task IDs/progress so interrupted work can resume.

Therefore it would be inaccurate to say that Python has no recovery after process loss.

The PWA change is architectural emphasis and structure:

- persistent recovery is no longer an exceptional/fallback path;
- the durable ledger becomes the primary execution model;
- run/step/task history remains structured in IndexedDB across normal browser suspension/relaunch;
- the foreground poll controller never becomes authoritative.

## Core parity table

| Python/a-Shell behavior | PWA equivalent | Current status |
|---|---|---|
| Validate request configuration | Plain JavaScript validation from the same contract | Direct |
| Explicit model/FPS/frame/interpolation rules | Same client-side validation | Direct |
| Encode selected image for request | Browser `File`/`Blob`/Base64 handling | Direct |
| Submit `POST /api/v3/tasks` | `fetch()` after CORS validation | Direct subject to CORS |
| Save creation intent before billable POST | IndexedDB task intent record | Stronger explicit browser requirement |
| Persist returned remote ID | Immediate ledger update | Direct and mandatory |
| Poll known task ID | Foreground `fetch()` loop | Direct while active |
| Reconcile after interruption | Load ledger + GET known IDs | Primary browser execution model |
| Bounded GET retries/backoff | Wall-clock retry controller | Direct |
| Handle `unknown` defensively | Bounded unknown observations while preserving ID | Direct |
| Handle `preparing` | Non-terminal queued/preparing state | Direct |
| Terminal-state handling | Same completed/failed/canceled/timeout model | Direct |
| Priority promotion | Same provider operation from persisted elapsed time | Direct when foreground execution returns |
| Cancel queued task | Same provider operation | Direct when allowed by remote state |
| Parallel remote tasks | Multiple known IDs active concurrently | Direct |
| Parallel task creation | **Serialized** potentially billable POSTs | Intentional change for orphan safety |
| Per-phase timers | Persisted wall-clock observation timestamps | Direct with suspension-aware semantics |
| Persistent run history | IndexedDB Run/Step/Task ledger | Browser-native replacement |
| Reuse prompt sets | IndexedDB/history UI | Direct |
| Download completed output | Browser staging/export flow | Requires iPhone validation |
| Atomic `.part` filesystem workflow | OPFS/browser-private staging where useful | Platform substitute |
| FFmpeg final-frame extraction | Mediabunny/WebCodecs decoded final sample | Browser-native substitute |
| FFmpeg concatenation | Not implemented | Product decision |
| Shell command/Shortcut handoff | None | Intentionally removed |
| `ffprobe`-grade media analysis | Python/project probes remain authoritative | Deliberate dual runtime |

## The lifecycle difference

### Python/a-Shell

The Python client is a conventional long-running process when iOS allows it to remain active. It can:

- sleep between polls;
- keep worker/thread state alive;
- hold active credentials in process memory;
- download immediately after observing completion;
- continue to the next Chain step;
- persist recovery state incrementally.

But iOS suspension/termination remains possible, and the Python client already contains recovery/suspension-aware logic.

### PWA

The PWA starts from the opposite assumption:

```text
foreground execution exists now
background execution may disappear at any boundary
```

Therefore:

- every important local transition is persisted;
- timer ticks are never authoritative;
- missed polling does not imply missing remote work;
- return to foreground always invokes reconciliation;
- locked credentials pause reconciliation without mutating task truth.

## Durable ledger

The selected browser schema is conceptually:

```text
Run
  -> Step
      -> Task
```

Important task fields include:

```text
localRunId
localStepId
clientSubmissionUuid
requestFingerprint
status
remoteTaskId | null
intentAt
submitStartedAt
remoteIdBoundAt
lastPollAt
nextEligibleActionAt
phaseObservedAt
terminalObservedAt
result/export state
error evidence
```

The request fingerprint excludes raw image bytes and should use normalized parameters plus a source identity/digest where useful.

## Submission safety

The browser makes the orphan window explicit:

```text
commit intent
    -> POST
    -> receive {id}
    -> commit remote ID
```

If interruption occurs between provider acceptance and durable remote-ID binding, local state becomes `ambiguous-submit`.

The current authenticated provider contract does not document creation idempotency or task listing/search, so the PWA must never blindly repeat that POST.

### Serialized submission in parallel mode

The earlier parity draft suggested a bounded Promise worker pool for submissions. That is no longer the selected design.

**Current decision:** only one potentially billable creation POST is in flight at a time.

Once each remote task ID has been durably captured, multiple remote tasks can execute and be reconciled/polled concurrently with bounded concurrency.

This changes throughput only for the brief creation phase while limiting the orphan blast radius to one task.

## Polling and reconciliation

The poll loop exists only while the page is active.

The reconciler runs on cold start, visibility return, and network return and can also be invoked from `pageshow`.

For each known non-terminal remote ID:

```text
GET /api/v3/tasks/{id}
```

Then:

- `pending` / `preparing` / `processing` -> persist observation and schedule next eligible foreground action;
- `unknown` -> preserve ID and apply bounded defensive handling;
- `completed` -> persist result state and continue only missing staging/export/Chain work;
- `failed` / `canceled` / `timeout` -> persist terminal evidence.

The authenticated OpenAPI schema includes `preparing` and `unknown`; the shorter AGENTS lifecycle list does not enumerate them. The PWA should preserve the broader documented provider enum while following AGENTS' terminal-state rules.

## Timing parity

The PWA should retain detailed phase visibility without pretending it observed transitions while suspended.

Useful fields include:

```text
intentAt
submitStartedAt
remoteIdBoundAt
firstPendingObservedAt
firstPreparingObservedAt
firstProcessingObservedAt
terminalObservedAt
stagingStartedAt
stagingCompletedAt
exportedAt
```

If the application is suspended for ten minutes and returns to find a completed task, it only knows completion happened **during that observation gap** unless the provider supplies an authoritative transition timestamp.

The UI should distinguish exact local action durations from observed remote-state timings.

## Async endpoint choice

The authenticated provider contract documents:

```text
POST /api/v3/tasks       production
POST /api/v3/tasks-sync  testing/debugging
```

The async endpoint is also the safer PWA lifecycle shape because it returns a task ID before the long remote generation period.

A synchronous request can remain open for the whole generation. If iOS terminates the browser transaction before its response arrives, the local client may have no task ID to reconcile.

Production PWA code therefore uses only `/tasks`.

## Parallel mode

Parallel mode is now defined as:

```text
serialize creation
    -> task A ID persisted
    -> task B ID persisted
    -> task C ID persisted

then bounded concurrent known-ID reconciliation/staging
```

Partial completion is first-class. Three completed outputs out of five remain three useful deliverables and three immutable historical task records.

Retrying one failed/incomplete step must not recreate completed remote work.

## Chain mode

Chain requires:

1. task N completes remotely;
2. the PWA obtains the final displayed frame;
3. that frame becomes task N+1's image.

No FFmpeg/ffmpeg.wasm is selected for this operation.

### Preferred media path

```text
completed ArtWorks MP4 URL
    -> Mediabunny UrlSource
    -> Input({ formats: [MP4] })
    -> primary video track
    -> track.canDecode()
    -> VideoSampleSink.getSample(Infinity)
    -> final sample in presentation order
    -> canvas/JPEG-or-PNG Blob
    -> persist transition state
    -> submit next async task
```

This is more deterministic than approximate end seeking through `<video>` because Mediabunny's documented sample sink handles presentation order and explicitly defines `getSample(Infinity)` as final-sample retrieval.

Project constraints:

- pinned locally served dependency;
- MP4-only format imports, not `ALL_FORMATS`;
- bounded `UrlSource` retries rather than its default infinite policy;
- prompt `VideoSample.close()` and `Input.dispose()` cleanup;
- CORS/partial-read validation against the actual ArtWorks result host.

MP4Box.js + direct WebCodecs remains a low-level debug fallback. `<video>` + canvas remains the minimal compatibility experiment.

### Chain behavior across suspension

The PWA does not promise that dependent task N+1 is submitted while backgrounded.

On return:

```text
reconcile N
    -> completed
    -> obtain/refresh result URL
    -> decode final transition frame
    -> persist transition artifact/state
    -> create N+1
    -> persist N+1 ID
```

This is recoverable but may increase total wall-clock completion time relative to an a-Shell process that happens to remain active.

## Outputs and export

The product decision intentionally simplifies parity:

- no combined final video;
- every ArtWorks output remains an independent deliverable.

The PWA separates:

```text
remote completion
browser/private staging
user-visible export
```

OPFS is a candidate private staging mechanism on WebKit/iOS. User-visible Files/Photos/share behavior must still be validated on the target device.

Where practical, use streaming/bounded memory rather than retaining an entire large MP4 in JS heap.

## Orion extension comparison

The supplied Orion extensions reinforce the lightweight division of labor.

### RedGifs Downloader

The extension resolves a direct MP4 URL and delegates it to the privileged extension `downloads.download()` API. It does no JavaScript MP4 decode/transcode.

This privilege model does not transfer to a normal PWA and does not prove CORS access.

### Orion Lite

The extension controls the page's existing `HTMLVideoElement` for seeking, speed, playback, sizing and inline presentation. The browser itself owns media networking/demux/decode.

Therefore the PWA should keep normal preview/playback browser-native and use a media library only where exact sample access is required.

## Credentials

Python can use local credential files/environment variables because it is a local process.

The browser model is intentionally different:

- user-owned credentials;
- Password AutoFill/system password manager for persistence;
- active credentials in memory only after fill/unlock;
- no reusable password in raw local storage or the task ledger.

A known task may be visible while credentials are locked. That is an authentication-required state, not a task failure.

## Service Worker / notifications

A Service Worker does not replace the Python process and does not own polling correctness.

Foreground orchestration + durable reconciliation remains the baseline.

The previously discussed credential-free notification relay is no longer an active implementation stage because ArtWorks webhook/callback registration is not documented in the current authenticated contract. A relay that polls the provider would require the reusable credential and violate the selected boundary.

## Features that can be stronger in the PWA

The PWA can provide a more structured persistent product surface than process-local CLI state:

- normalized Run/Step/Task history;
- explicit ambiguous-submission records;
- automatic reconciliation on lifecycle/network return;
- independent partial-run outputs;
- locked/unlocked credential UX;
- reusable prompt/config history;
- durable staging/export status.

This does not mean Python lacks persistence; the current Python runtime already persists recovery state. The distinction is that the browser ledger is designed as the normal operating model rather than a recovery file around a long-running process.

## Features intentionally not ported

Current product decisions omit:

- shell command generation;
- Shortcut hand-off;
- a-Shell execution;
- FFmpeg concatenation/combined final output;
- unrestricted local filesystem path semantics;
- local subprocess playback as a core workflow.

## Measurement boundary

Mediabunny gives the browser useful media visibility including codec strings, dimensions, duration, packet count, average packet rate/FPS, average bitrate and sample timing.

That does not automatically satisfy every evidence requirement in AGENTS.md.

Keep:

```text
PWA + Mediabunny
    -> production orchestration and lightweight media operations

Python + ffprobe/project probes
    -> authoritative provider discovery and deep media measurement
```

## Remaining blockers before production parity can be claimed

1. ArtWorks API CORS from the intended trusted production origin.
2. ArtWorks result-media CORS/partial-read behavior.
3. Completed-task/result TTL and URL refresh behavior.
4. Password AutoFill behavior in the installed Home Screen app.
5. Installed-PWA staging/export behavior on the physical iPhone.
6. Mediabunny decode/final-frame extraction on representative Wan/LTX outputs.
7. Origin trust model for PR/fork previews before real credentials are used.

## Architecture recommendation

Port the Python **state machine**, not the Python **process**.

For every browser transition ask:

```text
If the page disappears immediately after this line,
can the next launch determine exactly what happened
without duplicating potentially billable work?
```

If yes at every external boundary, the PWA can preserve the important remote-task reliability while using a lifecycle model that matches iOS rather than fighting it.

## Sources used for this comparison

Repository/project sources:

- `app/img2video_iphone.py` — current orchestration, unknown/preparing handling, recovery, polling, parallel execution, FFmpeg chain/assembly, download validation, and configuration behavior.
- `artworks_settings.txt` / current runtime state configuration — persisted recovery and bounded retry semantics.
- authenticated ArtWorks OpenAPI — full task status enum and generic task surface.
- `AGENTS.md` — validation, polling, safety and evidence discipline.
- `devdocs/pwa/runtime-architecture.md` — consolidated selected browser architecture.
- `devdocs/pwa/chain-media-strategy.md` — current Mediabunny-first Chain design.
- supplied Mediabunny full guide — lazy reads, MP4 imports, media sinks, cleanup and runtime codec checks.
- supplied Orion extension packages — direct inspected iOS extension behavior.
