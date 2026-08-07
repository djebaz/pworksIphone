<!-- VERSION$00002$ | Edited: 05/08 | TIME: 23:34 -->
# ArtWorks.ai Image-to-Video API: Parameters, Features, and Runtime Behavior

**Report date:** 2026-08-05  
**API:** ArtWorks PaaS API v3  
**Task type:** `image-to-video`

## 1. Scope and evidence

This report combines four evidence levels:

1. **Authenticated OpenAPI/Swagger schema**
   - `openapi3.json`
   - `Redoc.pdf`

2. **Runtime validation discovery**
   - `img2video_discovery_20260805_203617.json`
   - Deliberately invalid values were sent to expose enums and numeric validation messages.

3. **Boundary acceptance tests**
   - `img2video_matrix_boundary_20260805_201717.json`
   - Explicit values were submitted for `wan-2.2` and `ltx-2.3`.

4. **Completed output-video measurements**
   - `ltx-2.3`, requested 200 frames at 10 FPS:
     - actual 193 frames
     - actual duration 8.041667 seconds
     - actual encoded rate approximately 24 FPS
   - `ltx-2.3`, requested 360 frames at 10 FPS:
     - actual 353 frames
     - actual duration 14.708333 seconds
     - actual encoded rate approximately 24 FPS
   - User-reported additional behavior:
     - explicit Wan output is always encoded at 16 FPS
     - omitting `model` appears to select another legacy/default path with 16 FPS and a 128-frame maximum

5. **Deferred executor validation**
   - two live failures on 2026-08-05 with `interpolationFps=30`
   - the interpolation stage accepts only `None`, `16` or `24` and reports the
     violation against `body.fps`

Items described as **documented** come from Swagger. Items described as **confirmed** come from API responses or completed media measurements. Items described as **inferred** need additional tests.

---

## 2. Executive summary

ArtWorks exposes image-to-video through the generic task API:

- `POST /api/v3/tasks` for normal asynchronous production use
- `POST /api/v3/tasks-sync` for testing and debugging
- `GET /api/v3/tasks/{task}` for status and results
- `POST /api/v3/tasks/{task}/cancel` to cancel a pending task
- `POST /api/v3/tasks/{task}/priority` to change queue priority

The authenticated schema advertises two explicit models:

- `wan-2.2`
- `ltx-2.3`

The effective model-specific acceptance limits are:

| Execution path | Accepted request FPS | Accepted requested frames | Resolutions | Measured/observed encoded FPS |
|---|---:|---:|---|---:|
| `model` omitted | not fully mapped | user reports max 128 | not fully mapped | user reports 16 |
| `wan-2.2` | 8–16 | 24–160 | 480p, 720p, 1080p | user reports fixed 16 |
| `ltx-2.3` | 8–24 | 24–361 | 480p, 720p, 1080p | confirmed 24 in two completed runs |

The request field `fps` should not currently be interpreted as the final MP4 frame rate:

- LTX accepted `fps=10` but encoded both measured outputs at 24 FPS.
- Wan reportedly encodes at 16 FPS.
- The request FPS may still affect internal generation or motion pacing; that has not yet been isolated.

For LTX, requested frame counts were normalized downward:

- 200 requested → 193 encoded
- 360 requested → 353 encoded

Both results fit an `8n + 1` frame lattice. The current best-fit rule is:

```text
encodedFrames = 8 × floor((requestedFrames − 1) / 8) + 1
```

This is an inference from two measurements, not yet a complete guarantee across the full range.

---

## 3. Task lifecycle

### 3.1 Submit a production task

```http
POST /api/v3/tasks
Content-Type: application/json
```

The normal endpoint returns a task identifier:

```json
{
  "id": "task-id"
}
```

### 3.2 Poll task status

```http
GET /api/v3/tasks/{task-id}
```

Documented states include:

- `pending`
- `processing`
- `completed`
- `failed`
- `canceled`
- `timeout`

Terminal states are:

- `completed`
- `failed`
- `canceled`
- `timeout`

Successful image-to-video tasks observed through the working client expose the output URL at:

```text
results.data.video.url
```

### 3.3 Cancel a task

```http
POST /api/v3/tasks/{task-id}/cancel
```

Swagger describes this as cancellation of a **pending** task. Cancellation is therefore not guaranteed after the task reaches `processing`.

### 3.4 Change queue priority

```http
POST /api/v3/tasks/{task-id}/priority
Content-Type: application/json

{
  "priority": 1
}
```

Priority range:

- minimum: `1`
- maximum: `5`
- default: `5`

Lower values mean higher priority.

### 3.5 Synchronous endpoint

```http
POST /api/v3/tasks-sync
```

Swagger states that this endpoint is intended for testing and debugging. The asynchronous `/tasks` endpoint is recommended for production integrations.

---

## 4. Top-level task parameters

A normal request has this outer structure:

```json
{
  "type": "image-to-video",
  "priority": 5,
  "tags": ["optional-tag"],
  "batchId": "optional-batch-id",
  "payload": {
    "...": "image-to-video parameters"
  }
}
```

### `type`

- Type: string
- Required: yes
- Required value for this operation: `image-to-video`

### `payload`

- Type: object
- Required: yes
- Contains the model and generation parameters.

### `priority`

- Type: integer
- Range: 1–5
- Default: 5
- Lower number means faster/higher-priority queue placement.

This is the current queue-control field.

### `isFast`

- Type: boolean
- Deprecated: yes
- Swagger says to use `priority`.
- When both are present, `priority` takes precedence and `isFast` is ignored.

### `batchId`

- Type: string
- Optional
- Tasks in the same batch are documented as using the same priority as the first task in that batch.

### `tags`

- Type: array of strings
- Optional
- Used for task categorization and filtering.

---

## 5. Image-to-video payload parameters

## 5.1 `image`

- Type: string
- Required: yes
- Documented forms:
  - Base64 image reference
  - HTTPS URL
- Schema peculiarity: it is marked required but also nullable.

Recommended practice:

- Use a valid Base64/data reference or HTTPS URL.
- Do not send JSON `null`, despite the schema's nullable marker, unless deliberately testing behavior.

## 5.2 `prompt`

- Type: string
- Required: yes
- No prompt length limit is stated in the authenticated schema.

## 5.3 `model`

Documented enum:

```text
wan-2.2
ltx-2.3
```

Swagger-declared default:

```text
wan-2.2
```

Runtime caveat:

The user observed that omitting `model` does not behave like explicitly sending `wan-2.2`. The omitted path appears to use another legacy/default implementation with:

- encoded output at 16 FPS
- maximum 128 requested frames

This contradicts or bypasses the Swagger default. Until the omitted path is measured by the same timing probe, integrations should **send the model explicitly**.

## 5.4 `fps`

- Type: integer
- Swagger global range: 8–24
- Swagger default: 16

Runtime request-validation limits:

| Model | Minimum accepted | Maximum accepted |
|---|---:|---:|
| `wan-2.2` | 8 | 16 |
| `ltx-2.3` | 8 | 24 |

Important distinction:

`fps` is accepted and validated as a request field, but it does not necessarily set the final container frame rate.

Confirmed LTX measurements:

| Requested | Encoded result |
|---|---|
| 200 frames at `fps=10` | 193 frames at ~24 FPS |
| 360 frames at `fps=10` | 353 frames at ~24 FPS |

User-reported Wan behavior:

- final video is always encoded at 16 FPS

Current interpretation:

- Wan has a native/final output rate of 16 FPS.
- LTX has a native/final output rate of 24 FPS.
- The request FPS may be ignored for output encoding, normalized internally, or used for another generation-stage purpose.

Recommended conservative request values:

- `wan-2.2`: send `fps: 16`
- `ltx-2.3`: send `fps: 24`

Use other request FPS values only when explicitly testing whether they alter motion or content pacing.

## 5.5 `numFrames`

- Type: integer
- Swagger global range: 24–361
- Swagger-declared default: 16

The declared default is internally inconsistent because 16 is below the declared minimum of 24.

Runtime request-validation limits:

| Execution path | Minimum | Maximum |
|---|---:|---:|
| model omitted | not fully tested | user reports 128 |
| `wan-2.2` | 24 | 160 |
| `ltx-2.3` | 24 | 361 |

Confirmed LTX output normalization:

| Requested frames | Actual encoded frames | Difference |
|---:|---:|---:|
| 200 | 193 | −7 |
| 360 | 353 | −7 |

Both actual counts satisfy:

```text
frames ≡ 1 (mod 8)
```

Best current inference:

```text
actual = 8 × floor((requested − 1) / 8) + 1
```

Under that inferred rule:

| Requested | Predicted actual |
|---:|---:|
| 200 | 193 |
| 360 | 353 |
| 361 | 361 |

The 361-frame prediction has not yet been measured.

Duration should be calculated from the actual encoded file, not solely from request values.

For measured LTX output:

```text
duration ≈ actualEncodedFrames / 24
```

## 5.6 `resolution`

Documented and runtime-confirmed enum:

```text
480p
720p
1080p
```

Swagger default:

```text
480p
```

The API explicitly rejected `2160p` and returned the three available options.

No support was found through this ArtWorks endpoint for:

- `1440p`
- `2160p`
- `4K`
- `2560x1440`
- `3840x2160`
- arbitrary width × height strings

The resolution labels do not, by themselves, establish the exact encoded width and height for every input aspect ratio. Measure the completed video when exact dimensions matter.

## 5.7 `performance`

- Type: string or null
- Documented and runtime-confirmed enum:

```text
speed
quality
express
```

- Swagger default: `speed`

The schema and validation confirm accepted names, but the current probes do not quantify:

- generation-time differences
- output-quality differences
- billing differences
- model-specific support differences

## 5.8 `applyOptimizations`

- Type: boolean
- No Swagger default is stated.
- Actual visual and performance effects have not been tested.

## 5.9 `applyInterpolation`

- Type: boolean
- No Swagger default is stated.
- Intended to control output interpolation.

Actual behavior has not yet been measured.

## 5.10 `interpolationFps`

Swagger declares:

- Type: integer
- Default: 24
- Enum:

```text
24
25
30
50
60
```

Runtime anomaly:

The invalid-value probe sent `interpolationFps=999999999` with interpolation enabled for both explicit models. Both requests were unexpectedly accepted.

**Confirmed 2026-08-05:** validation is deferred to the interpolation executor, not skipped. A task submitted with `interpolationFps=30` (a declared enum value) was accepted, queued, entered `processing`, and then failed after approximately 71 seconds with:

```json
{"detail":[{"type":"literal_error","loc":["body","fps"],
  "msg":"Input should be None, 16 or 24","input":30,
  "ctx":{"expected":"None, 16 or 24"}}]}
```

The effective accepted set is therefore:

```text
None | 16 | 24
```

Consequences:

- Of the five values declared in Swagger, only `24` is actually executable. `25`, `30`, `50` and `60` are accepted at creation and fail at execute.
- `16` is executable but is **not** declared in the Swagger enum.
- `None` is executable, so omitting the field entirely is the safest default.
- This eliminates the earlier hypotheses that the field is ignored, normalized, or nonfunctional.

The error names `body.fps`, not `body.interpolationFps`. This indicates that interpolation runs as a **separate internal task whose `fps` field receives the submitted `interpolationFps` value**. See section 8.4 for the consequence.

Operational warning:

An unsupported `interpolationFps` is not rejected at submission. It creates a task that queues, occupies the executor and fails late, with the associated billing and latency cost. Validate this field client-side before submitting.

Client-side rule:

- omit `interpolationFps` when `applyInterpolation` is `false`
- otherwise send `16` for `wan-2.2` and `24` for `ltx-2.3`
- correct any other value locally rather than letting the API consume it

## 5.11 `seed`

- Type: signed 64-bit integer in Swagger
- No documented default
- No documented minimum or maximum
- Reproducibility has not been tested.

## 5.12 `loras`

- Type: array
- Each item is an object with:
  - `modelName`: string, required
  - `weight`: number, default 0, range −2 to 2

Example:

```json
{
  "loras": [
    {
      "modelName": "example.safetensors",
      "weight": 0.8
    }
  ]
}
```

The schema exposes LoRAs for image-to-video, but the current runtime tests do not establish:

- which LoRAs are compatible with Wan
- which LoRAs are compatible with LTX
- whether incompatible LoRAs fail at submission or processing
- whether weights are interpreted identically by both models

---

## 6. Confirmed model capability matrix

| Capability | `wan-2.2` | `ltx-2.3` |
|---|---|---|
| Explicit model accepted | yes | yes |
| Request FPS minimum | 8 | 8 |
| Request FPS maximum | 16 | 24 |
| Request frames minimum | 24 | 24 |
| Request frames maximum | 160 | 361 |
| 480p accepted | yes | yes |
| 720p accepted | yes | yes |
| 1080p accepted | yes | yes |
| 2160p accepted | no | no |
| Measured encoded FPS | user reports 16 | confirmed ~24 |
| Measured frame normalization | not yet mapped | 200→193, 360→353 |
| Performance enum | speed, quality, express | speed, quality, express |

---

## 7. Validation architecture

The API appears to validate requests in layers.

### Layer 1: shared DTO/schema validation

Examples:

- global FPS range 8–24
- global frame range 24–361
- shared enums for model, resolution and performance

An extremely high value can fail here before model-specific validation runs.

### Layer 2: model-specific validation

Examples confirmed for explicit Wan:

- `fps=24` is rejected with a Wan-specific maximum of 16
- `numFrames=360` and `361` are rejected with a Wan-specific maximum of 160

This explains why an extreme invalid-value probe reported the global maximum of 24 FPS and 361 frames even for Wan: the request failed at the shared layer first.

### Layer 3: generation/encoding normalization

Examples confirmed for LTX:

- accepted `fps=10`, encoded at 24 FPS
- accepted 200 frames, encoded 193
- accepted 360 frames, encoded 353

Submission acceptance therefore does not guarantee exact media-level realization of the requested values.

---

## 8. Swagger inconsistencies and runtime mismatches

### 8.1 `numFrames` default violates its minimum

Swagger says:

- default: 16
- minimum: 24

Both cannot be simultaneously valid for normal explicit validation.

### 8.2 Omitted model behavior may not equal Swagger default

Swagger says omitted `model` defaults to `wan-2.2`.

User observation indicates omitted model uses another path:

- 16 FPS
- maximum 128 frames

This needs a dedicated omitted-model timing and limit probe.

### 8.3 The `interpolationFps` enum is both wrong and unenforced at creation

Two independent defects:

1. **Unenforced at creation.** `999999999` and `30` were both accepted by `POST /api/v3/tasks`.
2. **Incorrect as documented.** The executor accepts only `None`, `16` or `24`. Four of the five documented values cannot execute, and the executable value `16` is undocumented.

The practical effect is a deferred, billable failure rather than a rejected request.

### 8.4 Request FPS differs from encoded FPS

LTX accepted `fps=10` but encoded at 24 FPS.

**Open hypothesis (2026-08-05):** the fixed encoded rates may belong to the interpolation/post stage rather than to the models themselves.

Evidence:

- The interpolation executor accepts exactly `{16, 24}`.
- The observed fixed encoded rates are exactly 16 for Wan and 24 for LTX.
- The rejection surfaced on `body.fps`, implying the post stage is itself an `fps`-parameterized task.

If correct, "Wan is always 16 FPS" and "LTX is always 24 FPS" would be restatements of the post stage's two permitted rates, and disabling interpolation might allow the encoded rate to follow the requested `fps`.

This is **inferred**, not confirmed. The decisive test is cheap: measure a completed run with `applyInterpolation=false` and compare the encoded rate against the requested `fps`. If they match, conclusions 5, 6 and 7 in section 12 require revision.

### 8.5 Requested frame count differs from encoded frame count

LTX accepted 200 and 360 but returned 193 and 353 encoded frames.

---

## 9. Recommended explicit request profiles

These profiles minimize ambiguity based on current evidence.

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
    "interpolationFps": 24,
    "loras": []
  }
}
```

Expected request limits:

- FPS: 8–16
- frames: 24–160
- encoded output reportedly 16 FPS

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
    "interpolationFps": 24,
    "loras": []
  }
}
```

Expected request limits:

- FPS: 8–24
- frames: 24–361
- native/final encoded output: 24 FPS in measured runs
- 360 requested frames produced 353 actual frames

### Why explicitly send every important field

Explicit values avoid reliance on:

- the contradictory `numFrames` default
- the potentially misleading `model` default
- undocumented defaults for the optimization/interpolation booleans

---

## 10. Duration planning

Do not calculate duration from `requestedFrames / requestedFps` without inspecting the output.

### LTX confirmed examples

Requested:

```text
200 / 10 = 20 seconds
```

Actual:

```text
193 / 24 = 8.041667 seconds
```

Requested:

```text
360 / 10 = 36 seconds
```

Actual:

```text
353 / 24 = 14.708333 seconds
```

For LTX, the current practical estimate is:

```text
estimatedDuration =
    normalizedLtxFrameCount(requestedFrames) / 24
```

where the best current normalization hypothesis is:

```text
normalizedLtxFrameCount(n) =
    8 × floor((n − 1) / 8) + 1
```

For production, always read the final MP4 metadata with `ffprobe` rather than relying only on the estimate.

---

## 11. Recommended remaining tests

The highest-value unresolved tests are:

1. **LTX request-FPS isolation**
   - same image, seed, prompt and frame count
   - request FPS: 8, 16 and 24
   - compare actual encoded FPS, duration and visual motion pacing

2. **LTX 361 frames**
   - verify whether actual output is exactly 361 frames
   - expected duration at 24 FPS: approximately 15.041667 seconds

3. **Wan timing**
   - measure explicit Wan with request FPS 8, 10 and 16
   - verify fixed 16 FPS with `ffprobe`
   - map actual frame normalization

4. **Omitted-model path**
   - omit `payload.model`
   - probe 128 and 129 frames
   - complete a timing run
   - compare codec, dimensions, frame rate and duration against explicit Wan

5. **Interpolation** (highest value, lowest cost)
   - identical source task with interpolation off and on
   - use `24`, then `16`; do **not** probe 25, 50 or 60, which are guaranteed
     late executor failures and are billed like any other launched task
   - measure frame rate, frame count and duration in each case
   - primary question: with interpolation off, does the encoded rate follow the
     requested `fps` instead of the model-fixed 16/24? See section 8.4.

6. **Resolution dimensions**
   - complete 480p, 720p and 1080p runs for landscape and portrait inputs
   - record exact encoded dimensions and aspect-ratio behavior

7. **Performance modes**
   - compare `express`, `speed` and `quality`
   - record queue time, processing time, output size, visual differences and billing

8. **Seed reproducibility**
   - submit identical requests twice with the same seed
   - compare hashes or perceptual similarity

9. **LoRA compatibility**
   - test model-specific LoRAs and invalid model names
   - identify whether failures happen during submission or processing

---

## 12. Integration conclusions

1. Always send `model` explicitly.
2. Treat Swagger ranges as global DTO limits, not complete model-specific guarantees.
3. Use explicit model limits:
   - Wan: FPS up to 16, frames up to 160
   - LTX: FPS up to 24, frames up to 361
4. Do not request 2160p; the ArtWorks endpoint only exposes 480p, 720p and 1080p.
5. Do not use request FPS to predict final duration.
6. For measured LTX output, use 24 FPS and the actual encoded frame count.
7. Expect LTX frame-count normalization to an apparent `8n + 1` lattice.
8. Use `priority`, not deprecated `isFast`.
9. Omit `interpolationFps` unless interpolating; `None` is explicitly accepted. When interpolating, send only 16 or 24, matched to the model. Unsupported values are not rejected at submission: they fail late, after the task has queued and run.
10. Inspect every completed MP4 with `ffprobe` when exact duration, dimensions or frame count matter.
