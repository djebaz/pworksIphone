<!-- VERSION$00003$ | Edited: 07/08 | TIME: 20:08 -->
# PWA Implementation Plan

## Purpose

Define a staged, reversible path from the existing Safari/Shortcut/a-Shell workflow to a new GitHub Pages-hosted PWA without destabilizing the working implementation.

No runtime changes are made by this discovery PR.

The implementation model is now defined in [`runtime-architecture.md`](runtime-architecture.md). This plan orders that architecture into go/no-go gates and product stages.

## Repository layout target

PWA runtime code will live independently at repository root:

```text
pwa/
├── index.html
├── manifest.webmanifest
├── icons/
│   ├── icon-192.png
│   ├── icon-512.png
│   └── icon-maskable-512.png
└── ...
```

Planning and technical evidence remain under:

```text
devdocs/pwa/
```

The working implementation remains untouched during discovery/bootstrap:

```text
shortcuts/img2video/
app/img2video_iphone.py
```

A `service-worker.js` is not assumed. No offline-generation requirement exists, and a Service Worker must not be added merely for the PWA label.

## Stage 0 — non-billable viability gates

**Status: in progress.**

Stage 0 adds no production ArtWorks workflow and submits no billable generation task.

Its purpose is to determine whether the selected pure-client architecture is viable before implementation cost or credentials are committed to it.

### Gate 0A — API CORS

From the intended GitHub Pages origin, probe ArtWorks browser access to the production asynchronous task API.

At minimum verify the preflight needed for:

```text
Origin: intended Pages origin
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization, content-type
```

Also verify browser access for the known-ID status/cancel/priority operations as needed.

**Go:** the real browser can send authenticated task operations from the selected origin.

**No-go:** direct browser -> ArtWorks architecture is blocked and the credential/network boundary must be redesigned before Stage 1.

No generation request is required for this gate.

### Gate 0B — result-media JavaScript access

Using an already-paid completed task/result if available, test the media URL separately from the API host.

Verify:

- JavaScript `fetch()` access under CORS;
- partial/random reads needed by the media reader;
- media bytes are readable by the PWA;
- relevant response headers are exposed if the implementation relies on them.

This gate is distinct from whether `<video>` can simply play the URL. A browser may play cross-origin media that JavaScript cannot inspect.

### Gate 0C — origin trust and preview topology

Credentials must not be introduced until the Pages deployment topology has a clear trust boundary.

Current PR previews are path-based under the same Pages origin. Path separation is **not** an origin-level security boundary for browser storage or credential-associated browser behavior.

Before real ArtWorks credentials are used:

- decide whether PR/fork preview content is fully trusted;
- if untrusted code can ever be published beneath the same credential-bearing origin, move the production PWA to a separate trusted origin/hostname or stop serving untrusted previews there;
- keep Service Worker scopes relative/path-limited, but do not mistake Service Worker scope for origin isolation.

This is a go/no-go security decision, not later polish.

### Gate 0D — Chain media fixture

Using a local/non-billable representative H.264 MP4 fixture on the target iPhone:

1. load the pinned Mediabunny subset;
2. use `Input({ formats: [MP4] })`;
3. verify `track.canDecode()`;
4. retrieve `VideoSampleSink.getSample(Infinity)`;
5. draw/export a non-empty JPEG/PNG Blob;
6. close/dispose media resources;
7. observe acceptable memory behavior.

Do not wait for a billable Chain run to discover a local codec/library incompatibility.

### Stage 0 exit criteria

All of the following must be known:

- production origin is trusted for credentials;
- ArtWorks API CORS either passes or the architecture has been redesigned;
- result-media JavaScript access is viable for Chain or Chain is explicitly disabled;
- Password AutoFill remains the selected credential persistence model;
- no undocumented provider feature is required for correctness.

## Stage 1 — single-prompt production slice

Build the smallest complete production flow. No Chain media processing is required.

### UI/bootstrap

- preserve the existing visual language and file-picker behavior;
- add the manifest and standalone iOS metadata;
- use the final icon when available; do not create a temporary icon;
- no custom install banner;
- no offline-generation simulation.

### Credential flow

- semantic username/current-password fields for Password AutoFill;
- active credentials in memory only after unlock/fill;
- locked/authentication-required state is normal and recoverable;
- no reusable ArtWorks password in IndexedDB/localStorage.

### Durable ledger

Implement `Run -> Step -> Task` records in IndexedDB.

Persist before POST:

- local run/step ID;
- client submission UUID;
- request fingerprint without raw image bytes;
- intent timestamp.

After successful task creation, bind the returned remote task ID immediately.

### Reconciler

Run on:

- cold start;
- visibility return;
- network return;
- optionally `pageshow` through the same idempotent entry point.

The poll loop is a foreground optimization. Correctness must come from ledger + reconciler.

### Task lifecycle

Use only asynchronous production creation:

```text
POST /api/v3/tasks
```

Do not use `/tasks-sync` for production.

Support the full authenticated status enum defensively, including `preparing` and bounded handling of `unknown`.

Never blindly retry an ambiguous creation POST.

### Completed output

Separate states:

```text
remote-completed -> staged -> exported
```

OPFS may be used as origin-private staging. Prefer streaming/bounded memory where practical. Reject obvious HTML/error payloads and non-video content types.

User-visible Files/Photos/share/export behavior must be tested on the target iPhone.

### Stage 1 acceptance

A single prompt can survive:

- page suspension;
- reload;
- loss/recovery of network;
- credential relock;

without duplicating a known or ambiguous potentially billable submission.

## Stage 2 — multi-prompt and parallel

Add multiple independent deliverables.

### Submission policy

**Serialize new task-creation POSTs.**

Parallel mode means multiple already-identified remote tasks may execute/poll concurrently. It does not mean multiple task-creation requests should simultaneously occupy the orphan window.

After each task ID is durably stored, permit bounded concurrent:

- status reconciliation/polling;
- output staging;
- export preparation.

### Partial completion

A partially completed run remains useful.

If three of five tasks complete, preserve those three outputs and their history. Retrying a failed/incomplete item must not recreate completed work.

### Stage 2 acceptance

- serialized submission is enforced;
- each remote ID is persisted independently;
- reload/reopen reconciles every known non-terminal task;
- completed outputs remain independently exportable;
- a failure in one item does not destroy the run ledger.

## Stage 3 — Chain

Add dependent steps only after Stage 1/2 reliability is stable and the Stage 0 media fixture passes.

### Selected media path

No FFmpeg/ffmpeg.wasm is required for normal Chain advancement.

Preferred path:

```text
ArtWorks result URL
  -> Mediabunny UrlSource
  -> Input({ formats: [MP4] })
  -> primary video track
  -> track.canDecode()
  -> VideoSampleSink.getSample(Infinity)
  -> final presentation-order VideoSample
  -> canvas
  -> JPEG/PNG Blob
  -> persist transition artifact/state
  -> next async ArtWorks task
```

### Mediabunny production constraints

- pin and vendor the reviewed build under `pwa/`;
- do not load it from a third-party CDN at runtime;
- import only the MP4 format required for ArtWorks output rather than `ALL_FORMATS`;
- override `UrlSource` default infinite retry with a bounded project policy;
- close `VideoSample` promptly and dispose the `Input` after use;
- keep packet-statistics scans out of the hot path unless needed for diagnostics.

Fallback/debug paths:

1. MP4Box.js + direct WebCodecs;
2. `<video>` + canvas as the simplest compatibility experiment.

### Chain suspension semantics

The dependent next POST occurs only while the PWA can execute.

If iOS suspends after task N completes remotely:

```text
reopen/visible
  -> reconciler finds task N completed
  -> obtain/refresh result URL
  -> extract transition frame
  -> persist transition state
  -> create task N+1
  -> persist N+1 task ID
```

Do not pretend Chain continues locally while the PWA is suspended.

### Stage 3 acceptance

- representative Wan/LTX output parses and decodes on target iPhone;
- the retrieved sample is the true final presentation frame;
- exported image Blob is valid;
- next ArtWorks request accepts the transition image;
- interruption at every local boundary resumes without repeating an already completed remote step.

## Server/relay stage — not currently planned

A credential-free Web Push relay remains conceptually attractive only if ArtWorks can emit a trusted completion callback/event.

Webhook/callback registration is **not documented** in the current authenticated contract.

A relay that polls ArtWorks would need the reusable ArtWorks credential and violates the selected device-owned credential boundary.

Therefore no relay stage is on the active plan. Revisit only if provider capabilities change.

## Video assembly

**Product decision:** the PWA does not concatenate/re-encode generated outputs into one final video.

Each ArtWorks output is an independent deliverable.

Do not add FFmpeg/WASM, Mediabunny conversion, WebCodecs encoding, or server-side assembly merely to reproduce the Python combine feature unless the product decision changes later.

The authenticated ArtWorks task-type enum contains `run-ffmpeg`, but its payload schema, account entitlement and billing are not yet established and it is not required by the selected PWA workflow.

## Python/probe relationship

Keep a deliberate dual runtime:

### PWA

- production interaction surface;
- credentials/use in memory;
- ledger/reconciliation;
- task orchestration;
- Chain transition-frame extraction;
- normal staging/export.

### Python + probes

- provider discovery;
- reproducible validation experiments;
- `ffprobe`-grade media measurement;
- exact codec/container diagnostics;
- saved evidence generation.

The PWA must not claim to replace measurement capabilities it cannot reproduce at the evidence level required by AGENTS.md.

## Pages deployment

The current workflow publishes `shortcuts/img2video/` as the site root and PR snapshots under `/preview/pr-<number>/`.

The previous preferred layout was:

```text
production: /pwa/
preview:    /preview/pr-<number>/pwa/
```

That path layout remains mechanically useful, but the **security origin decision is still open**. If untrusted PR/fork content can share the same origin as the credential-bearing PWA, path separation is insufficient.

Any future manifest/icons/Service Worker paths should remain relative, and Service Worker scope must not cross from preview into production.

## Update behavior

New deployments should be acquired through normal navigation/reload behavior without a custom update banner.

If a Service Worker is later justified by a concrete event-driven feature, its cache/lifecycle strategy must avoid trapping users on stale application code.

## Acceptance principles

At every stage:

- existing `shortcuts/img2video/` continues to work;
- existing `app/img2video_iphone.py` continues to work;
- PWA failures cannot corrupt the working path;
- secrets never enter repository/public build assets;
- potentially billable API calls are deliberate and recorded;
- ambiguous creation is never silently retried;
- browser/provider limitations are documented rather than hidden;
- runtime claims are verified on the actual HTTPS origin and target iPhone before parity is declared.
