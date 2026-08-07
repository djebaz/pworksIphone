<!-- VERSION$00001$ | Edited: 07/08 | TIME: 18:20 -->
# PWA Implementation Plan

## Purpose

Define a staged, reversible path from the existing Safari/Shortcut/a-Shell workflow to a new GitHub Pages-hosted PWA without destabilizing the working implementation.

No runtime changes are made by this discovery PR.

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

A `service-worker.js` is not assumed. Because offline mode is explicitly not required, it should only be added if a concrete later requirement justifies it.

Planning and technical evidence remain under:

```text
devdocs/pwa/
```

The working implementation remains untouched:

```text
shortcuts/img2video/
app/img2video_iphone.py
```

## Phase 0 — discovery and contracts

Status: in progress.

### Deliverables

- document current Safari UI behavior;
- inventory Python responsibilities that may need browser equivalents;
- document GitHub Pages deployment topology;
- determine credential architecture;
- determine ArtWorks CORS/browser feasibility;
- identify features that require native/FFmpeg functionality;
- choose the first PWA functional milestone.

### Exit criteria

No implementation begins until the authentication boundary is understood well enough that credentials will not be exposed accidentally.

## Phase 1 — isolated installable shell

Create `pwa/` without modifying or replacing the working launcher.

### Initial goals

- copy/preserve the current visual design and responsive layout as the starting UI;
- add a valid web app manifest;
- add iOS standalone metadata;
- add application icons once an icon direction is selected;
- use `display: "standalone"`;
- choose theme/background colors that visually blend with the existing dark UI;
- keep the current image-picker behavior;
- keep local state behavior where useful;
- avoid offline caching;
- avoid framework/build-system dependencies.

### Validation

- normal Safari tab works;
- Add to Home Screen launches cleanly on iPhone/iPad;
- standalone safe areas are correct;
- Chromium recognizes the manifest/installable app metadata;
- the new PWA is isolated from the working application.

## Phase 2 — API proof of concept

Implement only enough API functionality to prove the selected authentication architecture and browser connectivity.

### Scope

- authenticate using the selected safe architecture;
- submit one explicit image-to-video task;
- persist the task ID immediately;
- poll task status;
- display terminal success/failure;
- expose/download the result video;
- preserve documented model/request constraints from the project contract.

### Safety

- avoid full test matrices;
- use non-billable validation where possible;
- treat any accepted generation request as potentially billable;
- record task IDs;
- do not log credentials or full Base64 image data.

### Required evidence

- browser CORS/preflight behavior;
- result-media browser behavior;
- iOS standalone networking behavior;
- interruption/resume behavior.

## Phase 3 — robust single-prompt parity

Port the reliable parts of the Python execution lifecycle that make sense in the browser:

- input validation;
- explicit model selection;
- model-specific FPS/frame constraints;
- interpolation contract;
- task status transitions;
- bounded retry logic;
- persisted task/recovery state;
- completed-result download;
- useful error reporting;
- duplicate-submission prevention after interruption/reload.

Prefer browser-native APIs and small plain-JavaScript modules.

## Phase 4 — multi-prompt and parallel behavior

Study and, where feasible, port:

- ordered multiple prompts;
- parallel submission limits;
- per-task progress;
- recovery of partially completed parallel runs;
- preservation of every completed output as soon as it becomes available.

Do not assume browser background execution is equivalent to a long-running Python process. iOS may suspend a standalone PWA when it is backgrounded. Recovery must therefore be based on persisted remote task IDs rather than continuous execution assumptions.

## Phase 5 — chain mode feasibility

Chain mode is a separate technical problem because the existing Python client extracts the last video frame through FFmpeg and uses that frame as the next image.

Study browser-native alternatives before adding FFmpeg/WASM:

1. load the completed video into a browser video element;
2. seek reliably to the final decodable frame;
3. draw the frame to a canvas;
4. export a Blob suitable for the next ArtWorks image payload;
5. verify cross-origin permissions on result media;
6. verify reliability on iPhone Safari/standalone mode.

If this is unreliable, compare that limitation with the cost/size/memory impact of FFmpeg/WASM or a server-side media helper.

Do not add a large WASM media stack without evidence that it is necessary and viable on the target iPhone.

## Phase 6 — video assembly feasibility

The existing Python client can concatenate/re-encode outputs with FFmpeg. Browser parity is not automatic.

Investigate separately:

- whether assembly is truly required in the PWA milestone;
- browser-native WebCodecs/MediaRecorder feasibility on target iOS;
- direct source-stream compatibility where concatenation might avoid re-encoding;
- a server-side assembly option;
- FFmpeg/WASM only as a last-resort client-side option.

A PWA should not silently claim full Python feature parity until output assembly is verified.

## Phase 7 — Pages deployment

The current Pages workflow publishes `shortcuts/img2video/` as the site root and PR snapshots under `/preview/pr-<number>/`.

When the PWA is ready for deployment, explicitly choose the public layout.

Preferred discovery candidates:

### Candidate A — PWA under `/pwa/`

- existing launcher remains at the current Pages root;
- new app is independently reachable at `/pwa/`;
- lowest migration risk;
- manifest `start_url` and `scope` stay relative to the PWA directory.

### Candidate B — PWA becomes the Pages root

- clean final URL;
- requires a conscious migration of the current launcher;
- higher blast radius;
- should happen only after parity is established.

### Candidate C — explicit legacy and PWA paths

- both applications receive stable named paths;
- root can redirect or provide a small selector later;
- more deployment structure but clear long-term ownership.

No candidate is selected in this discovery PR.

## Update behavior

The desired UX is simple: a new deployment should be acquired on a subsequent navigation/reload without a custom update banner.

If no Service Worker is used, normal HTTP/browser cache semantics handle this naturally.

If a Service Worker is introduced later, its lifecycle and cache strategy must be designed so it does not trap users on stale application code. A Service Worker must not be added merely for the PWA label.

## Icon plan

Deferred until an icon direction is selected.

When implemented, provide at least:

- 192x192 PNG;
- 512x512 PNG;
- 512x512 maskable PNG where appropriate;
- Apple touch icon metadata for Home Screen use.

Do not embed large icon data directly into HTML.

## Acceptance principles

At every phase:

- existing `shortcuts/img2video/` continues to work;
- existing `app/img2video_iphone.py` continues to work;
- PWA failures cannot corrupt the working path;
- secrets never enter the repository or public Pages output;
- potentially billable API calls are deliberate;
- browser limitations are documented rather than hidden by feature claims;
- behavior is verified on a real HTTPS Pages deployment and target iPhone before declaring parity.
