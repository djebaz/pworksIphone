<!-- VERSION$00002$ | Edited: 07/08 | TIME: 19:29 -->
# PWA Reliability Boundaries

## Purpose

Record the failure windows that remain even after adopting a recovery-first PWA architecture for ArtWorks tasks.

The core model remains valid: once ArtWorks has accepted a task, the remote job can continue while iOS suspends the PWA, and the client can later reconcile by task ID. The items below identify where that model still has structural risk or provider-dependent assumptions.

The detailed ArtWorks provider-contract review is maintained in [`artworks-provider-capabilities.md`](artworks-provider-capabilities.md).

## Evidence vocabulary

- **Documented** — stated by authoritative platform/provider documentation.
- **Confirmed** — reproduced by repository evidence or saved runtime output.
- **Inferred** — architecture reasoning consistent with current evidence but not yet provider-confirmed.
- **Unknown** — the current project and provider evidence do not establish the capability.
- **Not documented** — absent from the current authenticated ArtWorks OpenAPI contract; this does not prove that no private/newer/undocumented capability exists.

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

### Current ArtWorks documented status

The authenticated OpenAPI snapshot exposes `POST /api/v3/tasks` and returns an `id`, but does **not** document an idempotency header, a deduplicating client request ID, or retry-safe creation semantics.

The same OpenAPI exposes `GET /api/v3/tasks/{task}` but does **not** document `GET /api/v3/tasks` for task listing/search.

`tags` are documented as optional values for task "categorization and filtering" and are returned in task info, but no documented task-list/filter operation is exposed in the same contract. This makes tags promising correlation metadata but not a currently usable orphan-recovery mechanism.

`batchId` is documented for shared queue-priority behavior inside a batch. No idempotency or discovery semantics are documented for it.

**Status:** idempotency and task discovery are **not documented in the current authenticated contract**.

Do not claim that ArtWorks lacks those capabilities entirely; the evidence only establishes that the current contract does not expose them.

### Client-side mitigation

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

### Forward-compatible correlation tag

Because tags are documented and returned with task info, the PWA may attach a unique non-secret correlation tag to each step, for example:

```text
img2video-pwa
client-step:<uuid>
```

This does not currently make an orphan discoverable because the documented API lacks a task-list/filter operation. It is an **inferred forward-compatibility measure** that could become useful if provider-side tag discovery is exposed later.

### Required implementation rule

Never automatically re-submit an ambiguous `submitting` record after restart unless the architecture has a provider-backed way to prove that the first submission did not create a task.

A blind retry can duplicate billable work.

## 2. Result lifetime / signed-URL TTL

### Failure mode

Foreground-only discovery is safe only if a completed result remains retrievable long enough for realistic user-return intervals.

If `results.data.video.url` is a short-lived signed URL and the PWA is suspended for longer than the URL lifetime, a completed generation may become unavailable through the old URL or require a provider endpoint that can issue a fresh URL.

The relevant contract is therefore not merely "does the task remain completed?" but:

```text
completed task retention
+ ability to re-fetch task metadata
+ result URL lifetime / refresh behavior
+ media object retention
```

### Current ArtWorks status

**Confirmed:** the working integration has observed completed image-to-video output at `results.data.video.url`.

**Unknown:** the current authenticated OpenAPI and saved project evidence do not establish:

- whether that URL is signed;
- its expiration time, if any;
- whether a later `GET /api/v3/tasks/{id}` returns a refreshed URL;
- how long completed task records remain queryable;
- how long generated media remains retained by ArtWorks.

The available project/file evidence did not surface an actual saved completed result URL suitable for safe TTL analysis.

Public research performed on 2026-08-07 did not find authoritative ArtWorks retention/TTL documentation.

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

### Current ArtWorks documented status

The current authenticated OpenAPI does **not** document a task webhook/callback registration operation or callback field on task creation.

Public research also did not establish an authoritative ArtWorks webhook mechanism.

**Status: Not documented in the current contract.**

This must not be broadened into a claim that no undocumented/newer provider feature exists.

## 7. CORS is a separate viability gate

Even if recovery semantics are correct, browser JavaScript cannot call ArtWorks directly unless the API permits the GitHub Pages origin through CORS.

The authenticated OpenAPI does not specify runtime CORS policy. A non-billable preflight from the current research runtime could not reach the ArtWorks host because the research environment itself failed network/DNS resolution; that result says nothing about ArtWorks policy.

**Status: Unknown.**

The required validation is an actual `OPTIONS` preflight from the Pages origin, or an equivalent request carrying:

```http
Origin: https://djebaz.github.io
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
```

No generation task is needed to test this.

## 8. Updated reliability model

The pure-PWA architecture remains viable if the following provider properties are acceptable:

```text
browser CORS works
AND
submission can be made orphan-safe enough
AND
completed tasks/results remain recoverable long enough
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

The two structurally provider-dependent recovery gaps are:

1. **before task-ID persistence** — orphan prevention/discovery;
2. **after remote completion but before local retrieval** — task/result retention and URL lifetime.

CORS is the separate gate that decides whether the browser can execute the provider operations at all.

Everything between the two recovery boundaries is largely solvable with durable client state and foreground reconciliation.

## 9. Discovery checklist

Resolve these before implementation is considered reliability-complete:

- [ ] Verify browser CORS/preflight for Basic `Authorization` and all required ArtWorks methods.
- [x] Review the current authenticated OpenAPI for a documented idempotency mechanism: none is documented.
- [x] Review the current authenticated OpenAPI for task listing/search: none is documented.
- [x] Establish documented semantics of `batchId`: shared batch priority only; do not treat it as idempotency/discovery.
- [x] Establish current documented `tags` semantics: categorization/filtering is stated, but no task-list/filter operation is exposed in the same contract.
- [ ] Determine whether ArtWorks has a newer/private/support-documented idempotency or task-discovery capability outside the current OpenAPI.
- [ ] Determine completed task retention duration.
- [ ] Determine video URL lifetime and whether task re-fetch refreshes expired result URLs.
- [x] Review the current authenticated OpenAPI for webhook/callback registration: none is documented.
- [ ] Determine whether ArtWorks has a newer/private/support-documented webhook/callback mechanism outside the current OpenAPI.
- [ ] On target iPhone, verify Home Screen IndexedDB persistence and `navigator.storage.persisted()` behavior across relaunch/reboot.
- [ ] Verify Password AutoFill in installed Home Screen mode.
- [ ] Verify automatic result export/download after long suspension intervals.

## Sources reviewed

Provider findings were cross-checked against the authenticated `openapi3-live.json` snapshot captured on 2026-08-05, the current project API report, and the production Python client.

Platform storage findings were cross-checked against current WebKit Storage Policy documentation, WebKit's Home Screen ITP carve-out documentation, and MDN Storage API documentation on 2026-08-07.

Public web search did not expose authoritative ArtWorks documentation that extends the authenticated contract for CORS, idempotency, task listing, result TTL, or webhooks.
