<!-- VERSION$00047$ | Edited: 07/08 | TIME: 07:21 -->
# Derived Image-to-Video Runtime Contract

`image-to-video-runtime-contract.schema.json` is the project's machine-readable production request contract for ArtWorks.ai PaaS v3 `image-to-video` tasks.

It is deliberately **derived**. It is not the provider's authenticated OpenAPI/Swagger document and must not be presented as one.

## Why this exists

The provider schema, runtime validators, and generated media do not always agree. The project therefore keeps those layers separate:

| Source | Role |
|---|---|
| Provider OpenAPI/Swagger | **Documented** API surface and shared DTO constraints |
| [`api.md`](api.md) | Evidence report covering documented, confirmed, inferred, and user-reported behavior |
| [`../AGENTS.md`](../AGENTS.md) | Mandatory implementation, validation, recovery, logging, and API-safety rules |
| [`image-to-video-runtime-contract.schema.json`](image-to-video-runtime-contract.schema.json) | Derived client-side contract for requests this project considers safe to submit |

The derived contract may be stricter than the provider schema where confirmed runtime constraints or explicit project safety policy justify it, but conflicting or path-specific runtime evidence must not be promoted into universal validation rules.

## Three separate FPS concepts

The project keeps these concepts distinct:

1. **Generation request FPS — `payload.fps`**
   - Wan: `8` through `16`.
   - LTX: `8` through `24`.
   - This field does not reliably equal the final MP4 frame rate.

2. **Native/non-interpolated encoded FPS**
   - This is a property of the generated media and must be measured from the completed file.
   - Wan output is currently user-reported at 16 FPS without interpolation.
   - Existing LTX measurements encode at approximately 24 FPS.
   - These output rates are not interpolation targets.

3. **Interpolation target FPS — `interpolationFps`**
   - `applyInterpolation` is the boolean that enables or disables interpolation.
   - The authenticated OpenAPI schema documents `interpolationFps` as an integer with default `24` and enum `24`, `25`, `30`, `50`, `60`.
   - `interpolationFps` is independent from the model's native/non-interpolated output FPS.
   - In particular, Wan's 16 FPS native/output observation does not make `16` a documented interpolation target.

Using an interpolation target equal to an already-native output rate would not represent temporal upsampling, so the earlier derived mapping `Wan -> 16` and `LTX -> 24` has been removed.

## What the contract enforces

The schema validates the request envelope used by `POST /api/v3/tasks`:

- `type` must be `image-to-video`;
- `priority` is explicit and limited to `1` through `5`;
- deprecated `isFast` is not part of the accepted request shape;
- `payload.model` is mandatory and explicit;
- supported models are `wan-2.2` and `ltx-2.3`;
- request FPS is `8` through `16` for Wan and `8` through `24` for LTX;
- requested frames are `24` through `160` for Wan and `24` through `361` for LTX;
- resolution is limited to `480p`, `720p`, or `1080p`;
- performance is explicit and limited to `speed`, `quality`, or `express`;
- `applyOptimizations` is boolean;
- `applyInterpolation` is boolean;
- LoRA weights are limited to `-2` through `2`;
- `interpolationFps` is omitted when interpolation is disabled;
- when interpolation is enabled, `interpolationFps` is a separate target and must use the documented enum `24 | 25 | 30 | 50 | 60`.

The schema does **not** impose a model-specific interpolation target based on native/output FPS.

## Conflicting interpolation runtime evidence

Historical runtime evidence must remain visible without being generalized beyond what it proves:

- A creation-path probe accepted an extreme invalid `interpolationFps`, showing that the public enum was not enforced at creation in that path.
- On 2026-08-05, a documented `interpolationFps=30` task was accepted and later failed in one internal executor path with a `body.fps` error mentioning `None`, `16`, or `24`.
- The user has separately observed Wan interpolation at `30` working.

The internal `body.fps` error is evidence about one downstream execution path. It is **not** the public `interpolationFps` schema and does not justify replacing the documented enum with `{16, 24}`.

Until a reproducible saved task resolves the discrepancy, the runtime support of each documented interpolation target remains model/path dependent or otherwise unresolved. Do not claim that `30` universally succeeds or universally fails.

## Evidence boundary

Hard schema constraints are limited to:

1. **Documented** provider constraints that the project intentionally adopts;
2. **Confirmed** runtime constraints reproduced by API responses or completed media measurements; and
3. explicit project safety policy from `AGENTS.md`.

The following findings are not promoted into hard interpolation rules:

- user-reported native/non-interpolated 16 FPS output for explicit Wan;
- the measured approximately 24 FPS LTX encoded rate as an interpolation target;
- the historical single-path `interpolationFps=30` failure as a universal rejection rule;
- the user-reported working Wan `30` case as proof that every model/path supports 30;
- the inferred LTX `8n + 1` output-frame normalization rule;
- assumptions about visual quality, latency, billing, seed determinism, or LoRA cross-model compatibility.

Those findings remain in `api.md` with their evidence labels.

## Relationship to the provider OpenAPI document

Do not edit an official `openapi3.json` snapshot to make it agree with runtime behavior. That would erase the distinction between what ArtWorks documents and what this project has observed.

When a new authenticated provider schema is available:

1. preserve or replace the provider snapshot as provider evidence;
2. compare it with the previous provider schema;
3. update `api.md` with documented changes or remaining mismatches;
4. use focused runtime probes only when a documented change needs confirmation;
5. update this derived contract only when the evidence level supports a production validation rule;
6. keep conflicting, inferred, and user-reported runtime behavior out of universal hard constraints until it is reproducibly resolved.

A schema refresh does not, by itself, justify submitting a billable generation task.

## Example without interpolation

```json
{
  "type": "image-to-video",
  "priority": 1,
  "tags": ["img2video-iphone"],
  "payload": {
    "image": "data:image/jpeg;base64,...",
    "prompt": "Static camera, subtle natural movement.",
    "model": "ltx-2.3",
    "fps": 24,
    "numFrames": 360,
    "resolution": "480p",
    "performance": "quality",
    "applyOptimizations": true,
    "applyInterpolation": false,
    "loras": []
  }
}
```

Because interpolation is disabled, `interpolationFps` is intentionally absent.

## Example with interpolation enabled

```json
{
  "type": "image-to-video",
  "priority": 1,
  "payload": {
    "image": "data:image/jpeg;base64,...",
    "prompt": "Static camera, subtle natural movement.",
    "model": "wan-2.2",
    "fps": 16,
    "numFrames": 160,
    "resolution": "480p",
    "performance": "quality",
    "applyOptimizations": true,
    "applyInterpolation": true,
    "interpolationFps": 30,
    "loras": []
  }
}
```

This example is schema-valid because `30` is a documented interpolation target. It is not a claim that every Wan executor path will complete successfully at 30; runtime evidence is currently conflicting and must remain labeled accordingly.

## Validation

The contract is strict JSON, so it intentionally has **no project VERSION comment on line 1**. Adding a comment would invalidate JSON.

Syntax can be checked with standard-library Python:

```bash
python3 -m json.tool devdocs/image-to-video-runtime-contract.schema.json >/dev/null
```

A JSON Schema Draft 2020-12 validator can additionally validate the schema and sample requests, but such a validator is not a runtime dependency of the iPhone client.

No ArtWorks API request is required to validate this file locally.
