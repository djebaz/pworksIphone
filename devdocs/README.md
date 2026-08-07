<!-- VERSION$00071$ | Edited: 07/08 | TIME: 10:46 -->
# Developer Documentation

`devdocs/` contains the durable technical documentation and reference material for pworksIphone. Runtime code and reusable tools live elsewhere in the repository.

## Current contents

```text
devdocs/
├── README.md
├── api.md
├── derived-runtime-contract.md
├── image-to-video-runtime-contract.schema.json
├── img2video-safari-ux-spec.md
├── img2video-presets-settings-contract.md
├── img2video-execution-model.md
├── img2video-pr3-checklist.md
├── shortcut/
│   ├── README.md
│   ├── annotated-en.html
│   └── annotated-fr.html
└── references/
    ├── export-public-shortcut-as-json.md
    └── styles.css
```

## `api.md`

The ArtWorks.ai image-to-video API report. It records the authenticated schema, model-specific request validation, completed-media measurements, known API/runtime mismatches, safe request profiles, and unresolved questions.

API findings must retain their evidence level:

- **Documented** — stated by the authenticated Swagger/OpenAPI schema.
- **Confirmed** — observed in an API response or measured from completed output media.
- **Inferred** — consistent with current evidence but not exhaustively verified.
- **User-reported** — manually observed but not yet reproduced by saved automated evidence.

The API documentation keeps three FPS concepts separate: generation request `fps`, native/non-interpolated encoded FPS measured from media, and the separate `interpolationFps` target controlled by the boolean `applyInterpolation`. Native output FPS must not be reused as an interpolation constraint.

## Derived runtime contract

[`image-to-video-runtime-contract.schema.json`](image-to-video-runtime-contract.schema.json) is the machine-readable JSON Schema used to express the project's derived production request contract for ArtWorks.ai `image-to-video` tasks.

[`derived-runtime-contract.md`](derived-runtime-contract.md) explains why that contract is separate from the provider OpenAPI document, which evidence levels may become hard validation rules, how known Swagger/runtime mismatches are represented, and how the derived contract should be refreshed.

The derived schema is **not** an official ArtWorks OpenAPI document and must not be edited or described as though it were one. It follows the documented interpolation target enum `24 | 25 | 30 | 50 | 60`, keeps `applyInterpolation` boolean, and does not promote conflicting executor observations into a universal model-specific interpolation rule.

Because the contract is strict JSON, it intentionally has no line-1 VERSION comment; adding one would invalidate JSON.

## Img2Video Safari UI

Three documents cover the Safari-facing UI at `shortcuts/img2video/index.html` and its multi-prompt/execution capabilities:

- [`img2video-safari-ux-spec.md`](img2video-safari-ux-spec.md) is the canonical UX spec: section order, exact controls, visibility rules, and mobile UX principles.
- [`img2video-presets-settings-contract.md`](img2video-presets-settings-contract.md) explains the three configuration layers — `presets.txt`, `settings.txt` import, and `localStorage` working state — and exactly which fields each one may touch.
- [`img2video-execution-model.md`](img2video-execution-model.md) explains how the live UI state becomes the CLI command handed to `app/img2video_iphone.py`, including multi-prompt encoding, chain/parallel mode, and execution-only settings (play-on-finish).
- [`img2video-pr3-checklist.md`](img2video-pr3-checklist.md) tracks acceptance criteria and documents judgment calls made where the feature request and the actual Python client diverged (e.g. the real play-on-completion flag is `--sound`, not `--open-video`).

## `shortcut/`

Reconstruction and reference documentation for the current `Run Img2Video in a-Shell` integration — not the installable Shortcut itself.

`README.md` contains the exact reconstructed workflow and its `{filename, cmd}` contract. The annotated English and French HTML files provide visual references for the same Shortcut.

The live Safari-facing UI is not documentation and therefore lives at `shortcuts/img2video/index.html`.

The signed, installable Shortcut artifact is not documentation either and therefore lives at `shortcuts/img2video/dist/Run_Img2Video_in_a-Shell.shortcut`.

The project utility used to download and extract unsigned Shortcut data is `tools/shortcuts/dlshort.py`.

## `references/`

Material from other projects or external sources retained only as implementation or design reference.

`export-public-shortcut-as-json.md` documents an external workflow for taking a publicly shared iCloud Shortcut, retrieving its metadata through the iCloud `api/records/<ID>` endpoint, downloading the unsigned workflow plist, and decoding that plist for JSON inspection. It is reference material that complements `tools/shortcuts/dlshort.py`; it does **not** replace the project tool. For this iPhone/a-Shell Mini project, `tools/shortcuts/dlshort.py` remains the preferred implementation because it follows the project's portable standard-library Python approach.

`styles.css` is a reference stylesheet from another project. It is not a pworksIphone runtime dependency and should not be treated as the production stylesheet.

## Relationship with `AGENTS.md`

Root [`../AGENTS.md`](../AGENTS.md) contains mandatory implementation and API-safety rules for coding agents. It remains at repository root for discoverability.

`devdocs/` provides supporting technical context. If documentation and implementation appear to disagree, inspect the underlying evidence rather than silently changing an evidence classification or assuming undocumented runtime behavior.
