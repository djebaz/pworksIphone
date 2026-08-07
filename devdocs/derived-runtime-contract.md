<!-- VERSION$00043$ | Edited: 07/08 | TIME: 06:54 -->
# Derived Image-to-Video Runtime Contract

`image-to-video-runtime-contract.schema.json` is the project's machine-readable
production request contract for ArtWorks.ai PaaS v3 `image-to-video` tasks.

It is deliberately **derived**. It is not the provider's authenticated
OpenAPI/Swagger document and must not be presented as one.

## Why this exists

The provider schema, runtime validators, and generated media do not always agree.
The project therefore keeps those layers separate:

| Source | Role |
|---|---|
| Provider OpenAPI/Swagger | **Documented** API surface and shared DTO constraints |
| [`api.md`](api.md) | Evidence report covering documented, confirmed, inferred, and user-reported behavior |
| [`../AGENTS.md`](../AGENTS.md) | Mandatory implementation, validation, recovery, logging, and API-safety rules |
| [`image-to-video-runtime-contract.schema.json`](image-to-video-runtime-contract.schema.json) | Derived client-side contract for requests this project considers safe to submit |

The derived contract is intentionally stricter than the provider schema where
the project has confirmed runtime constraints or explicit safety policy.

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
- optimization and interpolation switches are explicit booleans;
- LoRA weights are limited to `-2` through `2`;
- `interpolationFps` must be omitted when interpolation is disabled;
- when interpolation is enabled, Wan requires `16` and LTX requires `24`.

That last rule intentionally follows the **confirmed executor behavior**, not the
Swagger enum. The provider schema advertises interpolation values that can be
accepted at task creation and then fail later during execution.

## Evidence boundary

Hard schema constraints are limited to:

1. **Documented** provider constraints that the project intentionally adopts;
2. **Confirmed** runtime constraints reproduced by API responses or completed
   media measurements; and
3. explicit project safety policy from `AGENTS.md`.

The following findings are **not** promoted into validation rules because their
evidence level does not justify that:

- user-reported fixed 16 FPS output for explicit Wan;
- user-reported omitted-model behavior and the reported 128-frame ceiling;
- the inferred LTX `8n + 1` output-frame normalization rule;
- the inferred relationship between the interpolation stage and encoded FPS;
- assumptions about visual quality, latency, billing, seed determinism, or LoRA
  cross-model compatibility.

Those findings remain in `api.md` with their evidence labels.

## Relationship to the provider OpenAPI document

Do not edit an official `openapi3.json` snapshot to make it agree with runtime
behavior. That would erase the distinction between what ArtWorks documents and
what this project has observed.

When a new authenticated provider schema is available:

1. preserve or replace the provider snapshot as provider evidence;
2. compare it with the previous provider schema;
3. update `api.md` with any documented changes or remaining mismatches;
4. use focused runtime probes only when a documented change needs confirmation;
5. update this derived contract only when the evidence level supports a
   production validation rule;
6. keep inferred and user-reported behavior out of hard constraints until it is
   reproducibly confirmed.

A schema refresh does not, by itself, justify submitting a billable generation
task.

## Example valid request

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

For interpolation-enabled requests:

```text
wan-2.2  -> interpolationFps = 16
ltx-2.3  -> interpolationFps = 24
```

## Validation

The contract is strict JSON, so it intentionally has **no project VERSION
comment on line 1**. Adding a comment would invalidate JSON.

Syntax can be checked with standard-library Python:

```bash
python3 -m json.tool devdocs/image-to-video-runtime-contract.schema.json >/dev/null
```

A JSON Schema Draft 2020-12 validator can additionally validate the schema and
sample requests, but such a validator is not a runtime dependency of the iPhone
client.

No ArtWorks API request is required to validate this file locally.
