<!-- VERSION$00001$ | Edited: 07/08 | TIME: 19:08 -->
# PWA Reliability Boundaries

## Purpose

Record the failure windows that remain even after adopting a recovery-first PWA architecture for ArtWorks tasks.

The core model remains valid: once ArtWorks has accepted a task, the remote job can continue while iOS suspends the PWA, and the client can later reconcile by task ID. The items below identify where that model still has structural risk or provider-dependent assumptions.

## Evidence vocabulary

- **Documented** — stated by authoritative platform/provider documentation.
- **Confirmed** — reproduced by repository evidence or saved runtime output.
- **Inferred** — architecture reasoning consistent with current evidence but not yet provider-confirmed.
- **Unknown** — the current project and public research do not establish the capability.

## 1. Submission orphan window

### Failure mode

There is an unavoidable client-side race around task creation:

```text
persist local intent
    |
    v
POST /api/v3/tasks
    |
    |  ArtWorks may accept and create a billable task
    v
receive { id }
    |
    v
persist remote task ID
```

If iOS suspends/terminates the PWA, the network drops, or the response is otherwise lost after the server has accepted the task but before the returned task ID is durably stored, the task may continue remotely while the PWA has no authoritative ID from which to resume.

This is different from ordinary polling interruption. Recovery-by-known-task-ID cannot repair a task whose ID was never observed or persisted.

### Preferred provider capabilities

Any one of the following can close or greatly reduce this structural hole:

1. **Idempotent task creation** — a client-generated stable idempotency key/request ID is supplied with submission; retrying the same logical submission returns/reuses the same remote task rather than creating another billable task.
2. **Task discovery/listing** — authenticated listing/search can find tasks created in a narrow time window and correlate them with known request metadata.
3. **Provider-side client correlation field with query support** — a client-generated identifier/tag can later be used to locate the task reliably.

### Current ArtWorks status

**Unknown.** Current repository evidence documents task creation returning an `id`, direct lookup by known task ID, cancellation, and priority changes. The current project contract does not establish an idempotency header/key, a unique client request field with deduplication semantics, or a task-list/search endpoint suitable for orphan recovery.

`batchId` and `tags` exist in the request contract, but current project evidence does not establish either as an idempotency mechanism or as a queryable recovery key. Do not silently repurpose them without provider evidence.

Public web research performed on 2026-08-07 did not locate authoritative ArtWorks documentation establishing idempotent creation, task listing/search, or webhook registration. Absence from search results is not proof of non-existence.

### Client-side mitigation even before provider support is known

Persist a local submission-intent record *before* issuing POST. At minimum record:

- local run ID and step ID;
- a client-generated submission UUID;
- request fingerprint/hash excluding the image payload itself where practical;
- prompt index;
- model and generation parameters;
- wall-clock submission-intent timestamp;
- status `submitting`;
- no remote task ID yet.

After the response arrives, atomically advance that record to `submitted` with the returned task ID.

This does **not** solve the orphan window by itself. It makes the ambiguous state explicit and provides the correlation material needed if ArtWorks exposes discovery later.

### Required implementation rule

Never automatically re-submit an ambiguous `submitting` record after restart unless the architecture has a provider-backed way to prove that the first submission did not create a task.

A blind retry can duplicate billable work.

## 2. Result lifetime / signed-URL TTL

### Failure mode

Foreground-only discovery is safe only if a completed result remains retrievable long enough for realistic user-return intervals.

If `results.data.video.url` is a short-lived signed URL and the PWA is suspended for longer than the URL lifetime, a completed generation may become undiscoverable or require a provider endpoint that can issue a fresh URL.

The relevant contract is therefore not merely "does the task remain completed?" but:

```text
completed task retention
+ ability to re-fetch task metadata
+ result URL lifetime / refresh behavior
+ media object retention
```

### Current ArtWorks status

**Unknown.** Current project evidence confirms where the completed video URL has been observed, but does not establish:

- whether that URL is signed;
- its expiration time, if any;
- whether a later `GET /api/v3/tasks/{id}` returns a refreshed URL;
- how long completed task records remain queryable;
- how long generated media remains retained by ArtWorks.

Public web research performed on 2026-08-07 did not find authoritative ArtWorks TTL documentation.

### Architecture consequence

This is a provider-number question with architectural impact.

If retention comfortably exceeds normal return intervals, foreground reconciliation is acceptable. If retention is short or refresh is unavailable, unattended result preservation requires another mechanism, such as a provider callback plus relay, server-side retrieval, or a more immediate foreground/download requirement.

### Validation target

Before declaring foreground-only result recovery production-safe, establish with provider documentation or a controlled test:

1. task remains queryable after completion;
2. completed result URL remains usable after representative delays;
3. if the URL expires, re-fetching task metadata either refreshes it or exposes another retrieval mechanism.

Avoid generating extra billable tasks solely for TTL testing if an already completed task can answer the question.

## 3. Credential durability and browser storage durability

### Credential ownership

The selected product direction remains user-owned credentials, not application-shared credentials.

Preferred credential persistence remains the system password manager / Safari Password AutoFill, with the active credential held only in runtime memory while unlocked.

Ordinary task/run/recovery state belongs in IndexedDB.

### Home Screen storage behavior

**Documented by WebKit:** the first-party domain of a Home Screen web application is explicitly exempt from Intelligent Tracking Prevention's seven-day script-writable-storage removal algorithm.

This means the historic seven-day Safari website-storage cap should not be treated as the normal retention limit for the installed Img2Video PWA.

### Persistent storage mode

**Documented by WebKit:** Safari/WebKit supports the Storage API, including:

- `navigator.storage.persisted()` to inspect whether the origin is persistent;
- `navigator.storage.persist()` to request persistent mode;
- automatic grant/deny heuristics, including whether the site is opened as a Home Screen web app;
- persistence mode remembered across sessions after relevant WebKit fixes.

Persistent mode exempts the origin from normal browser-driven eviction; explicit user removal remains possible.

### Correct launch policy

On every application launch:

1. call `navigator.storage.persisted()` when available;
2. if it returns `false`, call `navigator.storage.persist()`;
3. record/report whether persistence was granted;
4. continue to handle storage loss defensively even when persistence was previously granted.

Do **not** assume `persist()` itself must be re-requested unconditionally every launch. Primary WebKit documentation says persistent mode is remembered across sessions. Field reports suggesting unconditional repeated requests are weaker evidence than the platform documentation and should be treated as device-test observations, not the contract.

### Recovery UX

Credential re-entry and state-loss recovery must remain normal product flows rather than exceptional crash paths:

- task/history database missing → explain local state was unavailable/reset;
- password not available in memory → offer Password AutoFill / credential entry;
- persistence denied → show a non-alarming durability warning and continue;
- task ID known but credential locked → display task as `authentication required` rather than altering/removing it.

## 4. Wall-clock recovery semantics

Browser timers are not clocks of record.

When iOS suspends the PWA, timer callbacks stop while real time continues. Therefore retry schedules, promotion thresholds, phase timers, and timeouts must be reconstructed from persisted wall-clock timestamps.

Persist values such as:

- task submission timestamp;
- last successful poll timestamp;
- consecutive-poll-failure metadata;
- next eligible retry timestamp, if using exponential backoff;
- current observed phase and phase-observed-at timestamp;
- priority-promotion deadline;
- overall task deadline.

On resume, compute the next action from `Date.now()` and those persisted values. Do not resume an in-memory tick counter as if suspension duration were zero.

### Timing precision

If the task changed remote state while the PWA was suspended, the exact transition time is unknown unless ArtWorks reports it. The UI should distinguish:

- local observed transition time;
- provider-reported timestamp where available;
- derived elapsed interval spanning an observation gap.

## 5. Wake Lock as an attended-mode enhancement

Screen Wake Lock is not background execution and must never be used to claim it.

It is nevertheless a legitimate optional feature for Img2Video when the user intentionally keeps the progress screen open and wants uninterrupted foreground monitoring.

Recommended behavior:

- user-controlled opt-in or context-appropriate automatic request after a user gesture;
- acquire only during meaningful active monitoring;
- release when the run finishes or the user leaves the active monitoring view;
- expect the lock to be released when visibility is lost;
- re-acquire only after visibility returns and the user expectation remains valid;
- clearly communicate battery cost.

Wake Lock improves the attended path. It does not change the recovery-first correctness model.

## 6. Narrow notification relay escape hatch

A future server component does not necessarily require moving ArtWorks credentials or task results off-device.

A narrow relay could store only:

```text
opaque ArtWorks task ID / client correlation ID
<-> push subscription
```

Its sole job would be to receive a trusted provider completion event and send a Web Push notification to the correct device. It would not need to:

- know the user's reusable ArtWorks password;
- poll ArtWorks;
- fetch generated media;
- store prompts or result URLs.

### Required provider capability

This architecture only works cleanly if ArtWorks can emit a callback/webhook or equivalent event that can be registered/correlated by the device using the user's own authenticated session.

If webhook registration requires exposing a reusable ArtWorks credential to the relay, the design no longer preserves the selected credential boundary.

### Current ArtWorks status

**Unknown.** No authoritative webhook/callback capability has been established by current project evidence or public research.

This should remain an explicit capability question rather than being assumed absent.

## 7. Updated reliability model

The pure-PWA architecture remains viable if the following provider properties are acceptable:

```text
Task submission can be made orphan-safe enough
AND
completed tasks/results remain recoverable long enough
AND
direct browser authentication/CORS works
```

The runtime model is:

```text
intent persisted
   -> submit
   -> task ID persisted immediately
   -> poll while active
   -> tolerate suspension
   -> reconcile known IDs on foreground
   -> download / chain-advance while active
```

The two structurally provider-dependent gaps are:

1. **before task-ID persistence** — orphan prevention/discovery;
2. **after remote completion but before local retrieval** — task/result retention and URL lifetime.

Everything between those boundaries is largely solvable with durable client state and foreground reconciliation.

## 8. Discovery checklist

Resolve these before implementation is considered reliability-complete:

- [ ] Verify browser CORS/preflight for Basic `Authorization` and all required ArtWorks methods.
- [ ] Determine whether task creation supports an idempotency key or unique client request ID.
- [ ] Determine whether tasks can be listed/searched by time, tag, batch, or client correlation field.
- [ ] Determine whether `batchId` or `tags` have any reliable query/discovery semantics; do not assume.
- [ ] Determine completed task retention duration.
- [ ] Determine video URL lifetime and whether task re-fetch refreshes expired result URLs.
- [ ] Determine whether ArtWorks exposes webhook/callback registration and what authentication model it uses.
- [ ] On target iPhone, verify Home Screen IndexedDB persistence and `navigator.storage.persisted()` behavior across relaunch/reboot.
- [ ] Verify Password AutoFill in installed Home Screen mode.
- [ ] Verify automatic result export/download after long suspension intervals.

## Sources reviewed

Platform storage findings were cross-checked against current WebKit Storage Policy documentation, WebKit's Home Screen ITP carve-out documentation, and MDN Storage API documentation on 2026-08-07.

ArtWorks-specific idempotency, listing, result TTL, and webhook capabilities remain provider questions. Current project evidence and public search did not establish them.
