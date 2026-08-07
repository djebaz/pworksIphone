<!-- VERSION$00001$ | Edited: 07/08 | TIME: 19:00 -->
# Python Runtime to PWA Parity Analysis

## Purpose

Compare the current `app/img2video_iphone.py` execution model with the proposed browser/PWA runtime and identify which behavior can be replicated directly, which behavior needs browser-native substitutes, and which behavior intentionally changes.

This document is architecture analysis only. No ArtWorks request was made and no potentially billable task was submitted.

## Executive conclusion

The PWA can reproduce most of the Python client's **orchestration logic**.

The most important conceptual difference is lifecycle:

- the Python process attempts to remain alive and poll continuously, but iOS may still suspend or terminate a-Shell;
- a PWA should assume suspension is normal whenever it is not foregrounded;
- the remote ArtWorks task continues independently in either case;
- durable task IDs and state allow either runtime to resume by querying the existing remote task rather than submitting a duplicate.

Therefore the PWA architecture can be thought of as the Python recovery model made primary:

```text
submit -> persist task ID -> poll while executable
                     |
                     +-> suspension / close / network loss
                                  |
                                  v
                         reopen / foreground
                                  |
                                  v
                       load durable state
                                  |
                                  v
                     query existing task ID
                                  |
                                  v
                      continue from real state
```

The PWA does not need a continuously running Service Worker to obtain Python-like correctness.

## Core state-machine parity

| Python/a-Shell behavior | PWA equivalent | Parity |
|---|---|---|
| Validate request configuration | Plain JavaScript validation using the same derived contract | Direct |
| Explicit model/FPS/frame/interpolation rules | Same browser-side validation rules | Direct |
| Encode selected image for API request | `File`/`Blob` + `FileReader` or `arrayBuffer()`/Base64 conversion | Direct |
| Submit `POST /api/v3/tasks` | `fetch()` if ArtWorks CORS permits | Direct subject to CORS |
| Save remote task ID immediately | IndexedDB transaction immediately after accepted submission | Direct and mandatory |
| Poll `GET /tasks/{id}` | `fetch()` loop while page is active | Direct in foreground |
| Bounded retry/backoff | Promise/AbortController-based retry logic | Direct |
| Detect terminal states | Same state machine | Direct |
| Preserve failed task ID/evidence | Persist `lastFailedTaskId`/error record in IndexedDB | Direct |
| Resume after interruption | Load IndexedDB and query existing task IDs | Direct, but normal rather than exceptional |
| Parallel submission | Bounded Promise worker pool | Direct |
| Parallel polling | Bounded Promise worker pool | Direct while foregrounded |
| Per-task phase timers | Persist timestamps and derive durations | Direct with better suspension semantics |
| Priority promotion | Same API call after elapsed pending time when foregrounded | Direct, with delayed observation after suspension |
| Completed video URL extraction | Same response parsing | Direct |
| Download completed media | `fetch()`/Blob/browser download-export flow | Mostly direct; iOS UX needs device testing |
| Download provenance/hash | Web Crypto `crypto.subtle.digest('SHA-256', ...)` where useful | Direct |
| Persistent run history | IndexedDB | Direct |
| Reuse prompt sets | IndexedDB/history UI | Direct |
| Cancel pending tasks | Same API endpoint while foregrounded | Direct |
| Play result | Browser media/open behavior if retained | Browser-native substitute |
| FFmpeg concatenation | Intentionally omitted | Not required by product decision |
| FFmpeg final-frame extraction for chain | Video element + frame callback + canvas/Blob | Browser-native substitute to validate |
| Local filesystem paths and atomic rename | Browser storage/download abstractions | Different platform model |
| `subprocess`, a-Shell commands | None | Intentionally removed |

## The major lifecycle difference

### Python/a-Shell

The current client is a conventional long-running process. It can:

- sleep between polls;
- keep thread pools alive;
- keep credentials and task state in process memory;
- download as soon as a result is observed;
- continue directly to the next chain step;
- write recovery state periodically.

However, the script already acknowledges iOS suspension as a real condition. It persists task IDs and execution state and warns when polling activity has been absent for a suspicious interval.

So even the Python implementation does **not** fundamentally depend on perfect continuous execution for correctness.

### PWA

The PWA should invert the assumption:

- foreground execution is available now;
- background suspension may happen at any time;
- no in-memory timer is authoritative;
- every important transition is persisted before moving on;
- on foreground/relaunch, reconciliation is always safe and routine.

This is not a weaker task model. For remote ArtWorks work it can be equally correct because ArtWorks owns the long-running generation after task submission.

What is lost during suspension is only **observation and local follow-up**, not the remote generation itself.

## Submission safety

The most important Python reliability rule transfers exactly:

> Once ArtWorks returns a task ID, persist it before doing anything that might be interrupted.

In the browser:

1. build/validate request;
2. submit request;
3. receive task ID;
4. commit task ID plus request identity/state into IndexedDB;
5. only then enter the normal polling loop.

If the page disappears after step 4, reopening the PWA must query that ID.

If failure occurs in the ambiguous network window where the browser cannot determine whether the submission reached ArtWorks and no task ID was received, the application must not blindly resubmit. This is the same distributed-systems ambiguity the Python client must treat carefully.

A future provider idempotency key would improve this further if ArtWorks supports one; current project evidence does not establish such support.

## Polling parity

The Python client polls periodically and tracks:

- status;
- consecutive request failures;
- unknown status counts;
- phase changes;
- task elapsed time;
- optional priority promotion;
- terminal success/failure.

All of this is straightforward in foreground JavaScript.

The PWA polling controller should stop or become irrelevant when the page is suspended. On return it should immediately perform reconciliation instead of trying to infer what happened from missed JavaScript timer ticks.

### Reconciliation

For each persisted non-terminal task:

```text
GET /api/v3/tasks/{taskId}
```

Then:

- if still `pending`/`processing`, resume normal foreground polling;
- if `completed`, record the result and start the pending download/export flow;
- if `failed`/`canceled`/`timeout`, persist terminal evidence and expose retry controls;
- never re-submit merely because local polling was interrupted.

## Timing parity

The Python client records `taskStartedAt`, `lastActiveAt`, phase start times, and accumulated phase durations.

The PWA should preserve the same conceptual fields, but timestamps become more important than interval timers.

Example:

```text
submittedAt
firstPendingObservedAt
firstProcessingObservedAt
terminalObservedAt
downloadStartedAt
downloadCompletedAt
```

If the PWA is suspended for ten minutes and returns to find a completed task, it knows the task completed **sometime during that gap**, not necessarily at `terminalObservedAt`.

The UI should distinguish:

- exact local action durations;
- observed state-transition timings;
- elapsed wall-clock time since submission.

This is more honest than pretending background JavaScript timers were running continuously.

## Parallel mode

Parallel mode maps very well to the web platform.

Python uses bounded thread pools for submission, polling, and downloads. JavaScript can use a bounded Promise pool with the same `maxParallelTasks` policy.

State remains per job:

```text
index
prompt
source image identity
parameters
taskId
taskStartedAt
lastStatus
phase timestamps
videoUrl
download/export state
error evidence
```

When the PWA is suspended, no new local polling occurs. Existing remote jobs continue on ArtWorks. Reopen -> reconcile every known task ID -> continue.

This is effectively the same recovery semantics already used by the Python parallel plan.

## Chain mode

Chain mode contains two separate operations:

1. wait for ArtWorks task N to finish;
2. derive the starting image for task N+1 from the final frame of task N.

The first part has direct parity.

The second part currently uses FFmpeg in Python and therefore needs a browser-native substitute.

Preferred candidate:

```text
completed video URL
    -> fetch as Blob when permitted
    -> local Blob URL / HTMLVideoElement
    -> seek to final decodable frame
    -> requestVideoFrameCallback()
    -> canvas draw
    -> canvas.toBlob()
    -> task N+1 input image
```

This must be validated against actual ArtWorks result media and iPhone Home Screen Safari.

### Chain behavior across suspension

A pure client PWA should not promise that step N+1 will submit while the app is suspended.

Instead:

- task N continues remotely;
- when the app becomes active, reconciliation sees task N completed;
- the PWA downloads/loads the result;
- extracts the transition frame;
- persists that transition artifact/state;
- submits task N+1;
- immediately persists the new task ID.

So chain mode remains fully recoverable, but wall-clock completion may be longer if the PWA spends time suspended between steps.

This is the largest practical behavior difference from an a-Shell process that happens to remain active continuously.

## Downloads and outputs

The user decision intentionally simplifies Python parity:

- no FFmpeg concatenation;
- every ArtWorks output remains independent;
- automatic download/export is attempted when the PWA can execute in the foreground.

The Python client can write directly to filesystem paths and atomically rename `.part` files. Browser code cannot assume the same unrestricted filesystem model.

The PWA should separate:

- **remote completion** — ArtWorks has produced the media;
- **browser staging** — media has been fetched into a Blob/possibly OPFS if used;
- **user-visible export/download** — browser/iOS has handed the file into the user's normal download/share flow.

Each of those states should be persisted so reopening the PWA can retry only the missing step.

## Credentials

Python can keep credentials in a local file and environment variables because it is a local process.

The PWA cannot reproduce that mechanism literally.

Selected browser direction:

- user owns/supplies credentials;
- prefer Safari/system Password AutoFill for persistence;
- keep active credentials only in memory after fill/unlock;
- do not store the reusable password in raw `localStorage`;
- keep task/history data independent in IndexedDB.

After a cold restart, the PWA may know that tasks need reconciliation while credentials remain locked. It can show those tasks and request AutoFill/unlock before querying ArtWorks.

## Service Worker role

A Service Worker does not replace the Python process.

It can support event-driven browser capabilities such as:

- future Web Push notifications;
- notification click handling;
- optional supported-browser retry hooks;
- communication with open app windows.

It should not own the core ArtWorks polling state machine.

The authoritative orchestration state remains IndexedDB + remote ArtWorks task state.

## Notifications

Web Push can improve the user experience but is not required for correctness.

Modern iOS Home Screen web apps support standards-based Web Push. However, a push sender needs an external signal that something changed.

With reusable ArtWorks credentials intentionally kept under user control/on-device, a remote push relay cannot simply poll ArtWorks unless the provider offers a webhook/callback or appropriately scoped delegated credential.

Until such a signal exists, the correct model remains:

```text
backgrounded PWA
   -> no guaranteed polling
remote ArtWorks task
   -> continues independently
user reopens PWA
   -> reconcile immediately
```

## Features that can be stronger in the PWA

The browser architecture also creates opportunities that are cleaner than the command-line client:

- structured task/run history instead of one recovery JSON file;
- searchable/reusable prompt-set history;
- richer state visualization and per-task timers;
- one persistent UI for chain and parallel jobs;
- direct task controls such as retry/cancel/priority actions;
- automatic reconciliation on `pageshow`, visibility return, and network return;
- explicit locked/unlocked credential state;
- installation as a dedicated Home Screen application.

## Features intentionally not ported

The following are not required for PWA parity under current product decisions:

- shell command generation;
- Shortcut hand-off;
- a-Shell execution;
- FFmpeg concatenation/combined final video;
- local subprocess playback;
- unrestricted filesystem path management.

## Remaining blockers before implementation parity can be claimed

1. **ArtWorks CORS** — direct browser authentication/submission/polling must be proven from the real Pages origin.
2. **Credential UX** — verify Safari Password AutoFill inside the installed Home Screen app.
3. **Chain frame extraction** — prove final-frame extraction from actual ArtWorks media on target iPhone/iOS.
4. **Automatic download/export** — verify installed-PWA behavior on physical iPhone.
5. **Persistent storage** — implement/test IndexedDB schema and eviction/persistence behavior.
6. **Background gap semantics** — make the UI clearly show observed vs exact phase timing.
7. **Optional notifications** — determine whether ArtWorks exposes a callback/webhook or delegated mechanism suitable for Web Push.

## Architecture recommendation

Treat the PWA as a durable event-driven state machine, not as a port of Python's control flow line by line.

The logical algorithm can remain almost the same:

```text
validate
prepare input
submit
persist task ID
poll
handle transitions
persist state
download result
advance chain or finish
```

The browser-specific rule is inserted between every step:

```text
"This process may disappear now; can the next launch reconstruct exactly what to do?"
```

If the answer is yes for every externally meaningful transition, the PWA can provide essentially the same remote-task reliability as the Python/a-Shell client while respecting iOS foreground/background constraints.

## Sources used for this comparison

Repository sources:

- `app/img2video_iphone.py` — current production task orchestration, recovery, polling, parallel execution, FFmpeg chain/assembly, download validation, and configuration behavior.
- `devdocs/img2video-execution-model.md` — current Safari -> Python chain/parallel and command execution model.
- `AGENTS.md` — required API validation, polling, state, safety, and evidence rules.

Platform sources:

- MDN Service Worker lifecycle/global-scope guidance: workers can be terminated when idle and must not rely on persistent global state.
- MDN Background Synchronization API: limited availability and designed for deferred synchronization rather than a portable long-running poller.
- WebKit Web Push documentation: standards-based Push/Notifications/Service Workers for Home Screen web apps on iOS/iPadOS 16.4+.
