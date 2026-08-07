<!-- VERSION$00003$ | Edited: 05/08 | TIME: 23:34 -->
# AGENTS.md

## Scope

These instructions apply to all code that creates, validates, polls, cancels, downloads, or analyzes ArtWorks.ai PaaS v3 `image-to-video` tasks.

The integration has important differences between:

- the authenticated Swagger/OpenAPI schema;
- model-specific request validation;
- the media actually produced after a task is accepted.

Do not treat those layers as interchangeable.

## Evidence labels

When documenting behavior or adding assertions, use these labels precisely:

- **Documented**: stated by the authenticated Swagger/OpenAPI schema.
- **Confirmed**: observed in an API response or measured from a completed output file.
- **Inferred**: consistent with current measurements but not yet exhaustively verified.
- **User-reported**: observed manually but not yet reproduced by an automated measurement in this repository.

Do not upgrade inferred or user-reported behavior to confirmed without a reproducible test and saved evidence.

---

## Non-negotiable integration rules

1. **Always send `payload.model` explicitly.**
   - Supported explicit values are `wan-2.2` and `ltx-2.3`.
   - Do not rely on the Swagger default.
   - Omitting `model` appears to invoke an undocumented legacy/default path rather than behaving identically to explicit `wan-2.2`.

2. **Use `priority`, not `isFast`.**
   - `isFast` is deprecated.
   - When `priority` is set, `isFast` is ignored.
   - Valid priority values are integers from `1` to `5`.
   - Lower values mean higher queue priority.
   - Default priority is `5`.

3. **Validate model-specific limits client-side.**
   - Swagger exposes broad shared limits, but Wan applies stricter runtime limits.
   - Do not validate only against the global DTO ranges.

4. **Do not use request `fps` to predict final video duration.**
   - The accepted request FPS is not necessarily the encoded MP4 frame rate.
   - Inspect the completed file.

5. **Do not request unsupported resolutions.**
   - The ArtWorks endpoint exposes only `480p`, `720p`, and `1080p`.
   - `2160p` was explicitly rejected.
   - Do not send `1440p`, `4K`, pixel-dimension strings, or arbitrary dimensions.

6. **Do not assume accepted values are realized exactly in the media.**
   - LTX accepted requested frame counts that were normalized before encoding.
   - Submission success is not proof of exact output FPS, frame count, duration, or dimensions.

7. **Validate `interpolationFps` client-side against `{16, 24}`.**
   - **Confirmed:** the interpolation executor accepts only `None`, `16` or `24`.
   - The Swagger enum is not enforced at task creation, so an unsupported value
     creates a real task that queues, runs and then fails late.
   - Omit the field entirely when `applyInterpolation` is `false`; `None` is accepted.
   - The visual effect of interpolation remains unverified even at accepted values.

8. **Never log credentials or full Base64 image payloads.**
   - Redact secrets.
   - Replace embedded image data with a length or hash in logs and reports.

---

## API endpoints

### Production task submission

```http
POST /api/v3/tasks
Content-Type: application/json
```

Expected success response:

```json
{
  "id": "task-id"
}
```

### Poll task status

```http
GET /api/v3/tasks/{task-id}
```

Known states:

- `pending`
- `processing`
- `completed`
- `failed`
- `canceled`
- `timeout`

Terminal states:

- `completed`
- `failed`
- `canceled`
- `timeout`

For completed image-to-video tasks, the working integration has observed the video URL at:

```text
results.data.video.url
```

Code must handle missing or differently shaped result data as an error rather than raising an unhelpful `KeyError`.

### Cancel a task

```http
POST /api/v3/tasks/{task-id}/cancel
```

Cancellation is intended for pending tasks. It may fail once processing begins.

### Change priority

```http
POST /api/v3/tasks/{task-id}/priority
Content-Type: application/json

{
  "priority": 1
}
```

### Synchronous execution

```http
POST /api/v3/tasks-sync
```

Use this endpoint only for testing and debugging. Use `/api/v3/tasks` for production workflows.

---

## Request structure

Use this outer structure:

```json
{
  "type": "image-to-video",
  "priority": 5,
  "tags": ["optional-tag"],
  "batchId": "optional-batch-id",
  "payload": {
    "image": "data:image/jpeg;base64,...",
    "prompt": "Static camera, subtle natural movement.",
    "model": "ltx-2.3",
    "fps": 24,
    "numFrames": 360,
    "resolution": "480p",
    "performance": "speed",
    "applyOptimizations": false,
    "applyInterpolation": false,
    "loras": []
  }
}
```

Required top-level fields:

- `type`
- `payload`

Required payload fields:

- `image`
- `prompt`

Although Swagger marks `image` as nullable, production code must require a real Base64/data reference or HTTPS URL.

---

## Parameter reference

### `model`

Documented explicit values:

```text
wan-2.2
ltx-2.3
```

Implementation rule:

- Require one of these explicit values.
- Do not silently omit the field.
- Do not silently substitute a model when the caller provided an invalid value.

### `fps`

Swagger global range:

```text
8 through 24
```

Model-specific request limits:

| Model | Minimum | Maximum |
|---|---:|---:|
| `wan-2.2` | 8 | 16 |
| `ltx-2.3` | 8 | 24 |

Important:

- This field is validated as a request parameter.
- It does not reliably control the final MP4 frame rate.

Observed output behavior:

- Explicit Wan output is user-reported as fixed at 16 FPS.
- LTX output was confirmed at approximately 24 FPS in two completed tests, despite requesting 10 FPS.

**Inferred (2026-08-05, unresolved):** these fixed rates may belong to the interpolation/post stage rather than to the models. The interpolation executor accepts exactly `{16, 24}`, which matches the two observed fixed encoded rates, and it validates them under the name `fps`. If this holds, a run with `applyInterpolation=false` may encode at the requested rate instead. Do not act on this until measured; see open question 5.

Recommended conservative values:

- `wan-2.2`: `fps: 16`
- `ltx-2.3`: `fps: 24`

Only use other request FPS values in an explicit experiment that measures the resulting media.

### `numFrames`

Swagger global range:

```text
24 through 361
```

Swagger also declares a default of `16`, which conflicts with the minimum. Do not rely on that default.

Model-specific request limits:

| Execution path | Minimum | Maximum |
|---|---:|---:|
| `wan-2.2` | 24 | 160 |
| `ltx-2.3` | 24 | 361 |
| Model omitted | not fully mapped | user-reported 128 |

LTX completed-output measurements:

| Requested | Encoded |
|---:|---:|
| 200 | 193 |
| 360 | 353 |

Both encoded frame counts satisfy `frames ≡ 1 (mod 8)`.

Current inferred normalization rule:

```text
actualFrames = 8 × floor((requestedFrames - 1) / 8) + 1
```

This rule is inferred from two measurements. It may be used for an estimate, but not as a substitute for measuring the completed file.

### `resolution`

Supported values:

```text
480p
720p
1080p
```

Default documented by Swagger:

```text
480p
```

Reject all other resolution strings client-side unless a new authenticated schema and runtime probe establish support.

The resolution label does not guarantee exact width and height for every source aspect ratio. Inspect the completed video when exact dimensions matter.

### `performance`

Supported values:

```text
speed
quality
express
```

Swagger default:

```text
speed
```

The accepted enum is confirmed. Relative quality, latency, billing, and model-specific effects remain unmeasured.

### `applyOptimizations`

- Type: boolean
- No documented default
- Runtime effect not yet measured

Send an explicit boolean.

### `applyInterpolation`

- Type: boolean
- No documented default
- Runtime effect not yet measured

Send an explicit boolean.

### `interpolationFps`

Documented values:

```text
24
25
30
50
60
```

Swagger default:

```text
24
```

**Confirmed executor-accepted values (2026-08-05):**

```text
None
16
24
```

The documented enum and the executable set disagree in both directions: `25`, `30`, `50` and `60` are documented but not executable, and `16` is executable but not documented.

Task creation does not validate this enum. A probe using `999999999` was accepted for both explicit models, and a run using the documented value `30` was accepted, queued, entered `processing`, and failed after approximately 71 seconds with:

```json
{"detail":[{"type":"literal_error","loc":["body","fps"],
  "msg":"Input should be None, 16 or 24","input":30,
  "ctx":{"expected":"None, 16 or 24"}}]}
```

The violation is reported against `body.fps`, not `body.interpolationFps`. **Inferred:** interpolation runs as a separate internal task whose `fps` field receives the submitted `interpolationFps`. See the note under `fps`.

Implementation rules:

- Omit the field when `applyInterpolation` is `false`.
- Otherwise send `16` for `wan-2.2` and `24` for `ltx-2.3`.
- Correct any other configured value locally, with a warning, rather than submitting it.
- Do not treat a documented value as safe merely because Swagger lists it.

Any interpolation experiment must inspect the completed output FPS, frame count, and duration.

### `seed`

- Type: signed 64-bit integer
- No documented default
- No documented range
- Reproducibility is unverified

Do not claim deterministic output without a dedicated repeatability test.

### `loras`

Type: array of objects.

Each item:

```json
{
  "modelName": "example.safetensors",
  "weight": 0.8
}
```

Rules:

- `modelName` is required.
- `weight` range is `-2` through `2`.
- Documented default weight is `0`.

LoRA compatibility with Wan and LTX is unverified. Do not assume a LoRA supports both models.

### `batchId`

- Optional string
- Tasks in the same batch are documented as using the priority of the first task in that batch.

### `tags`

- Optional array of strings
- Intended for categorization and filtering

---

## Capability matrix

| Capability | `wan-2.2` | `ltx-2.3` |
|---|---:|---:|
| Request FPS | 8–16 | 8–24 |
| Requested frames | 24–160 | 24–361 |
| `480p` | yes | yes |
| `720p` | yes | yes |
| `1080p` | yes | yes |
| `2160p` | no | no |
| Encoded FPS | user-reported 16 | confirmed ~24 |
| Frame normalization | not mapped | 200→193; 360→353 |
| Performance enum | speed, quality, express | speed, quality, express |

---

## Validation model

Assume three separate layers.

### Layer 1: shared DTO validation

This layer exposes broad constraints, such as:

- FPS from 8 to 24
- frame count from 24 to 361
- shared enums for model, resolution, and performance

An extreme invalid value can fail here before model-specific validation runs.

### Layer 2: model-specific validation

Confirmed explicit Wan restrictions:

- FPS maximum 16
- frame maximum 160

For capability discovery, do not conclude that a global maximum applies to every model merely because an extreme invalid value returned that maximum.

### Layer 3: generation and encoding normalization

Accepted request values may be changed in the produced file.

Confirmed LTX examples:

- requested `fps=10` → encoded at approximately 24 FPS
- requested 200 frames → encoded 193
- requested 360 frames → encoded 353

Code must separate:

- requested parameters;
- API acceptance;
- completed task metadata;
- measured media properties.

---

## Duration and media analysis

Never calculate final duration only as:

```text
requestedFrames / requestedFps
```

Confirmed LTX examples:

```text
200 requested frames at requested 10 FPS
→ 193 encoded frames at 24 FPS
→ 8.041667 seconds
```

```text
360 requested frames at requested 10 FPS
→ 353 encoded frames at 24 FPS
→ 14.708333 seconds
```

For LTX, an estimate may use:

```text
estimatedDuration =
    inferredNormalizedFrameCount(requestedFrames) / 24
```

Production code must still inspect the final MP4.

Use `ffprobe` when available and collect at least:

- codec;
- encoded width and height;
- `r_frame_rate`;
- `avg_frame_rate`;
- decoded or declared frame count;
- duration;
- file size.

Prefer a decoded frame count, such as `nb_read_frames`, over container metadata when both are available.

When deriving FPS from frame count and duration, retain enough precision to distinguish common rates such as 16, 24, 25, 30, 50, and 60.

---

## Polling requirements

Polling code must:

1. Store the task ID immediately after submission.
2. Poll until a terminal state.
3. Use a configurable interval.
4. Use a configurable overall timeout.
5. Report transitions between states.
6. Handle transient network failures with bounded retry behavior.
7. Return a clear error for `failed`, `canceled`, or `timeout`.
8. Preserve the task ID in error reports for later inspection.

Do not cancel a task that is intentionally being used for output timing or media analysis.

Validation-only probes should cancel unexpectedly accepted tasks immediately, but cancellation failure must be handled because the task may already be processing.

---

## Test safety and cost controls

API tests may create billable tasks.

Coding agents must follow these rules:

- Prefer schema inspection and rejected validation requests before completed-generation tests.
- Never assume an invalid value will be rejected.
- Treat interpolation probes as potentially billable.
- Default validation probes to immediate cancellation on unexpected acceptance.
- Require an explicit command-line flag or clearly named test mode for:
  - waiting for completion;
  - downloading output;
  - running multiple models;
  - running a Cartesian matrix;
  - testing high frame counts or high resolutions.
- Print the planned number of submissions before a batch test.
- Support `--plan` or dry-run behavior for multi-request scripts.
- Support chunking or limiting large matrices.
- Record every created task ID.

Do not perform a full matrix test when a focused boundary or threshold test can answer the question.

---

## Error handling and capability discovery

The API often returns useful validation details, including:

- available enum options;
- minimum constraints;
- maximum constraints;
- model-specific constraints.

Parse errors defensively:

- preserve the raw HTTP status;
- preserve the raw error body;
- extract the `errors` array when present;
- do not depend on one exact English sentence;
- store both parsed findings and raw text.

For enums, an impossible string can reveal available options.

For numeric limits, an extreme value may reveal only the shared DTO boundary. To discover a model-specific limit, probe inside the shared range or use a bounded threshold search.

Do not infer runtime output behavior from validation errors alone.

---

## Logging and reports

For every submitted task, record:

- timestamp;
- task ID;
- endpoint;
- explicit model;
- requested FPS;
- requested frame count;
- requested resolution;
- performance;
- interpolation and optimization flags;
- priority;
- acceptance or error;
- terminal status;
- queue and processing timing when available;
- output URL, redacted when necessary;
- downloaded file path;
- measured frame count;
- measured encoded FPS;
- measured duration;
- measured dimensions;
- codec;
- cancellation attempt and result.

Redact:

- username;
- password;
- authorization headers;
- full Base64 image payloads;
- other secrets.

Reports must distinguish documented, confirmed, inferred, and user-reported findings.

---

## Recommended request profiles

### Wan 2.2

```json
{
  "type": "image-to-video",
  "priority": 5,
  "payload": {
    "image": "data:image/jpeg;base64,...",
    "prompt": "Static camera, subtle natural movement.",
    "model": "wan-2.2",
    "fps": 16,
    "numFrames": 160,
    "resolution": "480p",
    "performance": "speed",
    "applyOptimizations": false,
    "applyInterpolation": false,
    "loras": []
  }
}
```

### LTX 2.3

```json
{
  "type": "image-to-video",
  "priority": 5,
  "payload": {
    "image": "data:image/jpeg;base64,...",
    "prompt": "Static camera, subtle natural movement.",
    "model": "ltx-2.3",
    "fps": 24,
    "numFrames": 360,
    "resolution": "480p",
    "performance": "speed",
    "applyOptimizations": false,
    "applyInterpolation": false,
    "loras": []
  }
}
```

These profiles minimize ambiguity. They are not claims that every field has been fully characterized.

---

## Prohibited assumptions

Do not write code or documentation that assumes any of the following:

- omitted `model` is equivalent to explicit `wan-2.2`;
- all models support the Swagger maximum of 24 FPS;
- all models support 361 frames;
- request FPS equals encoded FPS;
- requested frame count equals encoded frame count;
- `2160p` or native LTX 4K modes are available through ArtWorks;
- `interpolationFps` is validated at task creation;
- a value listed in the Swagger `interpolationFps` enum is executable;
- interpolation is known to work;
- optimization is known to improve quality or speed;
- seeds are deterministic;
- LoRAs are cross-model compatible;
- cancellation always succeeds after a task has been created.

---

## Open questions

Keep these behaviors marked unresolved until a reproducible test is added:

1. LTX output and motion behavior at requested FPS 8, 16, and 24.
2. LTX output for exactly 361 requested frames.
3. Explicit Wan encoded FPS and frame normalization measured with `ffprobe`.
4. Omitted-model behavior at 128 and 129 frames.
5. Interpolation effects, and whether the fixed 16/24 encoded rates originate in the post stage.
   - Compare one identical task with `applyInterpolation=false` against `true`.
   - Use only `24` and `16`. Do not probe `25`, `50` or `60`: they are confirmed
     late executor failures and are launched, and therefore billed, like any other task.
   - Primary measurement: with interpolation off, does the encoded rate follow the
     requested `fps`?
6. Exact output dimensions for each resolution and source aspect ratio.
7. Differences among `express`, `speed`, and `quality`.
8. Seed reproducibility.
9. LoRA compatibility and failure modes.

When resolving one of these questions, update this file with:

- the exact request;
- task ID or saved fixture reference;
- raw API result;
- measured media metadata;
- whether the finding is documented, confirmed, or inferred.

---

## Code review checklist

Before approving changes to image-to-video code, verify:

- [ ] `payload.model` is always explicit.
- [ ] Model-specific FPS and frame limits are enforced.
- [ ] Only `480p`, `720p`, and `1080p` are accepted.
- [ ] `priority` is used instead of `isFast`.
- [ ] Request FPS is not used as final encoded FPS.
- [ ] `interpolationFps` is restricted to 16 or 24 and matched to the model.
- [ ] `interpolationFps` is omitted when `applyInterpolation` is false.
- [ ] Values rejected only by the executor are corrected before submission, not paid for.
- [ ] Duration is measured or clearly labeled as estimated.
- [ ] Completed media is inspectable with `ffprobe`.
- [ ] Terminal states and timeouts are handled.
- [ ] Task IDs are preserved in logs and errors.
- [ ] Secrets and Base64 image data are redacted.
- [ ] Unexpectedly accepted validation probes are cancelled when appropriate.
- [ ] Billable multi-task tests require explicit opt-in.
- [ ] Documentation separates documented, confirmed, inferred, and user-reported behavior.
