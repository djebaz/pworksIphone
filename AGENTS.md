<!-- VERSION$00046$ | Edited: 07/08 | TIME: 14:32 -->
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

## File revision marker

Comment-compatible canonical files use the first-line marker:

```text
# VERSION$NNNNN$ | Edited: DD/MM | TIME: HH:MM
```

For Markdown and HTML files, use the equivalent valid comment syntax, for example:

```html
<!-- VERSION$00046$ | Edited: 07/08 | TIME: 14:32 -->
```

`VERSION` is a **per-file revision number**, not a project-wide edit serial.

Rules:

- Each canonical file maintains its own independent version sequence.
- When modifying a canonical file, read that file's current first-line `VERSION$NNNNN$` value and increment it by exactly 1.
- If that file has never had a valid VERSION marker, initialize it at `VERSION$00001$`.
- Do not scan, compare, synchronize, or derive VERSION numbers from other project files.
- Different files may legitimately have the same VERSION number.
- VERSION identifies successive revisions of one file only; Git provides project-wide history and edit ordering.
- Keep exactly five zero-padded ASCII digits.
- Update the Europe/Paris date and time after the final content modification and immediately before validation.
- Delivery copies retain exactly the same marker as their canonical file and do not increment the version.
- Never add a VERSION comment to strict JSON if doing so would invalidate the file.

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

7. **Keep request FPS, native/output FPS, and interpolation FPS separate.**
   - `payload.fps` is the generation request FPS and remains subject to model-specific request limits.
   - Native/non-interpolated encoded FPS is a property of the produced media and must be measured from the output file.
   - `applyInterpolation` is a boolean switch.
   - `interpolationFps` is a separate interpolation target. The authenticated OpenAPI schema documents `24`, `25`, `30`, `50`, and `60`, with default `24`.
   - Do not derive `interpolationFps` from the native/output rates of 16 FPS for Wan or 24 FPS for LTX. Using the same value as the native output would not represent temporal upsampling.
   - A historical `interpolationFps=30` run failed late in one executor path with an internal `body.fps` error, while the user has separately observed Wan interpolation at 30 working. Treat those as conflicting runtime evidence, not as a universal `{16, 24}` interpolation rule.
   - Omit `interpolationFps` when `applyInterpolation` is `false` unless a future provider contract requires otherwise.

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

These encoded rates are media-level observations and must remain separate from `interpolationFps`. In particular, Wan's reported 16 FPS output and LTX's measured ~24 FPS output are not evidence that interpolation targets should be 16 and 24.

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

Important separation:

- `applyInterpolation` is a boolean switch.
- `interpolationFps` is the requested interpolation target, not the model's native/non-interpolated encoded FPS.
- The currently observed native/output rates of 16 FPS for Wan and ~24 FPS for LTX must not be converted into a model-specific `interpolationFps` mapping.
- `16` is not part of the authenticated OpenAPI `interpolationFps` enum.

Historical runtime evidence must be retained without over-generalizing it:

- A probe using `999999999` was accepted at task creation for both explicit models, showing that task creation did not enforce the enum in that path.
- On 2026-08-05, a task submitted with documented `interpolationFps=30` was accepted, queued, entered `processing`, and then failed with an internal `body.fps` validation error saying `None`, `16` or `24`.
- The user has separately observed Wan interpolation at `30` working.

These observations conflict. The historical `body.fps` error describes one internal execution path; it does **not** establish a universal executable set for the public `interpolationFps` field. Do not rewrite the provider enum as `{16, 24}` from that error.

Implementation rules:

- Send `applyInterpolation` as an explicit boolean.
- Omit `interpolationFps` when `applyInterpolation` is `false`.
- When interpolation is enabled, validate `interpolationFps` against the documented enum `24 | 25 | 30 | 50 | 60`.
- Do not choose the interpolation target from the model's native/output FPS.
- Treat model/path-specific runtime failures as evidence to record and reproduce, not as universal schema constraints until confirmed across the relevant execution path.
- Any live interpolation test may create a billable task, so use focused tests and record the task ID.

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
- a value listed in the Swagger `interpolationFps` enum is executable in every model or executor path;
- native/non-interpolated output FPS determines the interpolation target;
- the historical `interpolationFps=30` failure proves that 30 always fails, or the user-reported Wan success proves that 30 always succeeds;
- interpolation behavior is fully characterized;
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
5. Interpolation behavior by model and executor path.
   - Keep native/non-interpolated output FPS separate from `interpolationFps`.
   - Reproduce the user-reported working Wan `interpolationFps=30` case and compare it with the historical 2026-08-05 late failure at 30.
   - Test documented interpolation targets only with explicit billable-test opt-in; do not run a full matrix when one focused reproduction can resolve the conflict.
   - Measure the final encoded FPS, frame count, and duration whenever interpolation completes.
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
- [ ] `applyInterpolation` is handled as an explicit boolean.
- [ ] `interpolationFps` uses the documented `24 | 25 | 30 | 50 | 60` target enum and is not derived from native/output FPS.
- [ ] `interpolationFps` is omitted when `applyInterpolation` is false.
- [ ] Conflicting runtime interpolation evidence is preserved as model/path-specific evidence rather than promoted to a universal constraint.
- [ ] Duration is measured or clearly labeled as estimated.
- [ ] Completed media is inspectable with `ffprobe`.
- [ ] Terminal states and timeouts are handled.
- [ ] Task IDs are preserved in logs and errors.
- [ ] Secrets and Base64 image data are redacted.
- [ ] Unexpectedly accepted validation probes are cancelled when appropriate.
- [ ] Billable multi-task tests require explicit opt-in.
- [ ] Documentation separates documented, confirmed, inferred, and user-reported behavior.