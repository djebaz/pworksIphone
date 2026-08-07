<!-- VERSION$00001$ | Edited: 07/08 | TIME: 19:29 -->
# ArtWorks Provider Capabilities for the PWA

## Purpose

Record the ArtWorks-specific capabilities that determine whether the Img2Video PWA can safely use direct browser-to-ArtWorks orchestration without introducing a credential-holding backend.

This report focuses on five questions:

1. browser CORS/preflight support;
2. idempotent task creation;
3. task discovery/listing after an ambiguous submission;
4. completed-task/result retention and video URL refresh behavior;
5. webhook/callback support.

No generation task was submitted while preparing this report.

## Evidence basis

The strongest provider evidence currently available to the project is the authenticated ArtWorks OpenAPI 3.1.0 snapshot captured on 2026-08-05 as `openapi3-live.json`, together with the current project API report and production Python client.

Evidence labels used here:

- **Documented** — present in the authenticated ArtWorks OpenAPI or project API contract derived from it.
- **Confirmed** — reproduced by saved project/runtime evidence.
- **Inferred** — architecture reasoning based on the documented contract.
- **Unknown** — not established by the current provider contract or saved runtime evidence.

An operation being absent from the current authenticated OpenAPI means **not documented in the current contract**. It is not proof that ArtWorks has no private, newer, or undocumented capability.

## Capability matrix

| Capability | Current status | PWA consequence |
|---|---|---|
| Direct browser CORS/preflight | **Unknown** | Blocks direct browser API implementation until runtime-tested from the Pages origin. |
| Idempotent task creation | **Not documented** | The POST-response orphan window remains structurally unresolved. |
| Task listing/search/discovery | **Not documented** | An orphaned task cannot currently be recovered from the documented API without its task ID. |
| Result/task retention and URL refresh | **Unknown** | Foreground-only reconciliation is not yet proven safe for long user absences. |
| Webhook/callback support | **Not documented** | The narrow task-ID-to-Web-Push relay cannot yet be implemented from the documented contract. |

## 1. CORS and browser preflight

### What the API contract establishes

**Documented:** production authentication uses HTTP Basic authentication and task operations are ordinary HTTPS endpoints under `https://api.artworks.ai`.

The PWA would need to send an `Authorization` header and, for task creation and other JSON POST operations, `Content-Type: application/json`.

### What remains unknown

OpenAPI does not establish server CORS policy. It does not tell us whether ArtWorks returns the response headers a browser requires for the GitHub Pages origin.

A browser request carrying `Authorization` is subject to CORS preflight. Before direct PWA requests can be considered viable, the server must accept an `OPTIONS` request equivalent to:

```http
OPTIONS /api/v3/tasks
Origin: https://djebaz.github.io
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
```

The resulting response must allow the deployed PWA origin and required methods/headers, particularly `Authorization` and `Content-Type`.

The same principle must be checked for:

- `GET /api/v3/tasks/{task}`;
- `POST /api/v3/tasks/{task}/cancel`;
- `POST /api/v3/tasks/{task}/priority`;
- `GET /api/v3/resources` if the PWA validates provider resources.

### Research status

A non-billable direct preflight attempt from the current research runtime could not reach `api.artworks.ai` because that runtime failed DNS/network resolution. Public search also did not expose authoritative ArtWorks CORS documentation.

**Status: Unknown.** The failed research-runtime connection is not evidence that ArtWorks rejects CORS.

### Required validation

Run the preflight from either:

1. the actual GitHub Pages PWA/preview origin in browser JavaScript; or
2. a network environment that can send an `OPTIONS` request with the exact Pages `Origin` header.

No generation POST is required to answer this question.

## 2. Task-creation idempotency

### Documented creation contract

The authenticated OpenAPI exposes:

```http
POST /api/v3/tasks
```

The documented success response is an object containing:

```json
{
  "id": "task-id"
}
```

The documented top-level request fields include:

- `type`;
- `payload`;
- `priority`;
- `tags`;
- `batchId`;
- deprecated `isFast`.

### Idempotency mechanisms searched

The current authenticated OpenAPI does **not** document:

- an `Idempotency-Key` request header;
- a client request ID with deduplication semantics;
- a task-creation token;
- a documented retry-safe creation operation;
- any statement that repeated identical POST bodies return the same task.

**Status: Not documented.**

### Architecture consequence

The PWA must continue to treat a task-creation POST as non-idempotent and potentially billable.

Persist a local `submitting` intent before issuing POST, but never automatically repeat an ambiguous submission after restart merely because no task ID was persisted.

## 3. Task listing, filtering, and orphan discovery

### Documented task operations

The authenticated OpenAPI path set documents:

```text
POST /api/v3/tasks
GET  /api/v3/tasks/{task}
POST /api/v3/tasks/{task}/cancel
POST /api/v3/tasks/{task}/fast       # deprecated
POST /api/v3/tasks/{task}/priority
```

The `/api/v3/tasks` path contains a documented **POST** operation but no documented **GET** list/search operation.

### `tags`

The creation schema describes `tags` as:

> Optional tags for task categorization and filtering

Task-info responses also expose `tags`.

However, the same authenticated schema does not expose a task-list/filter endpoint on which a tag filter could be applied.

Therefore:

- **Documented:** tags exist, are returned with task data, and are intended for categorization/filtering.
- **Not documented:** an API operation that lists or searches the user's tasks by tag.
- **Inferred:** filtering may exist in another/private interface or the OpenAPI description may anticipate a capability not exposed in this snapshot. This must not be relied upon.

### `batchId`

The documented description of `batchId` is queue-related: tasks in the batch use the same priority as the first task in that batch.

No documented task-search or idempotency semantics are attached to `batchId`.

Do not repurpose `batchId` as an orphan-recovery identifier.

### Future-compatible client correlation

Even though it does not currently solve recovery, the PWA can consider adding a unique, non-secret correlation tag to every submitted step, for example:

```text
img2video-pwa
client-step:<uuid>
```

This has two potential benefits:

- the identifier is preserved remotely if task info is later recovered;
- if ArtWorks later exposes tag-based task discovery, existing PWA submissions are already correlatable.

This is an **inferred forward-compatibility measure**, not a current orphan-recovery solution.

## 4. Completed-task retention and video URL lifetime

### What is established

**Confirmed by the working integration:** a completed image-to-video task can expose its result URL at:

```text
results.data.video.url
```

The production client downloads that URL after observing task completion.

### What is not established

The current OpenAPI and available saved evidence do not establish:

- how long completed task records remain queryable;
- how long generated media remains retained;
- whether `results.data.video.url` is a signed/expiring URL;
- its TTL if it is expiring;
- whether a later `GET /api/v3/tasks/{task}` returns a newly signed/refreshed URL;
- whether another retrieval endpoint exists after an old URL expires.

The available project/file evidence did not surface an actual saved completed result URL suitable for safe expiration analysis.

**Status: Unknown.**

### Required validation

Prefer one of these, in order:

1. authoritative provider documentation/support answer;
2. re-query an already completed known task after representative delays and compare/test its returned result URL;
3. if an actual result URL is available, inspect its query parameters and HTTP behavior without creating another task.

Do not create an extra billable generation solely to test URL TTL if existing task evidence can be used instead.

## 5. Webhook/callback support

### Current documented contract

The authenticated OpenAPI does not expose a webhook registration path or a provider callback operation for task state changes.

No documented operation currently lets the client register a callback URL for a task or batch.

The current project and public research also did not establish an authoritative webhook/callback facility.

**Status: Not documented in the current contract.**

This is not proof that ArtWorks has no undocumented or newer webhook capability.

### Why this matters

A provider callback would enable a very narrow notification relay while preserving device-owned ArtWorks credentials:

```text
ArtWorks completion event
        -> minimal relay
        -> Web Push subscription
        -> installed PWA notification
```

The relay could store only an opaque correlation/task identifier and push subscription. It would not need the reusable ArtWorks password, prompt, media, or result URL.

Without a provider callback or delegated provider credential, the relay cannot independently know that a task completed without becoming a poller with access to ArtWorks authentication.

## Provider-facing questions worth asking directly

If an ArtWorks support/developer channel is available, the highest-value questions are:

1. Does `api.artworks.ai` intentionally support browser CORS for arbitrary customer origins using HTTP Basic `Authorization`?
2. Is there an idempotency header or client-generated request identifier for `POST /api/v3/tasks`?
3. Is there an authenticated task-list/search endpoint, especially by `tags`, `batchId`, task type, or creation time?
4. How long are completed task records and generated media retained?
5. Do returned media URLs expire, and does re-fetching the task issue a fresh URL?
6. Is there a webhook/callback mechanism for task completion/failure, and can it be registered per task or per account without sharing reusable credentials with the callback receiver?

## Current architecture verdict

The direct client-owned architecture remains plausible but is not yet reliability-complete.

Three provider properties are required for the strongest form of the design:

```text
browser CORS works
AND
submission orphaning has a safe provider-backed recovery path
AND
completed task/results remain recoverable for realistic return intervals
```

Webhook support is optional for correctness but valuable for timely notifications.

At present:

- CORS: **Unknown**;
- creation idempotency: **Not documented**;
- task discovery/listing: **Not documented**;
- result retention/URL refresh: **Unknown**;
- webhook/callback: **Not documented**.

The implementation should therefore preserve the recovery-first state-machine design while keeping these provider boundaries explicit until verified.
