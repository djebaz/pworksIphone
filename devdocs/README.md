<!-- VERSION$00033$ | Edited: 07/08 | TIME: 04:47 -->
# Developer Documentation

`devdocs/` contains the durable technical documentation and reference material for pworksIphone. Runtime code and reusable tools live elsewhere in the repository.

## Current contents

```text
devdocs/
├── README.md
├── api.md
├── shortcut/
│   ├── README.md
│   ├── annotated-en.html
│   └── annotated-fr.html
└── references/
    └── styles.css
```

## `api.md`

The ArtWorks.ai image-to-video API report. It records the authenticated schema, model-specific request validation, completed-media measurements, known API/runtime mismatches, safe request profiles, and unresolved questions.

API findings must retain their evidence level:

- **Documented** — stated by the authenticated Swagger/OpenAPI schema.
- **Confirmed** — observed in an API response or measured from completed output media.
- **Inferred** — consistent with current evidence but not exhaustively verified.
- **User-reported** — manually observed but not yet reproduced by saved automated evidence.

## `shortcut/`

Documentation for the current `Run Img2Video in a-Shell` integration.

`README.md` contains the exact reconstructed workflow and its `{filename, cmd}` contract. The annotated English and French HTML files provide visual references for the same Shortcut.

The live Safari-facing UI is not documentation and therefore lives at `shortcuts/img2video/index.html`.

The utility used to download unsigned Shortcut data is a reusable tool and therefore lives at `tools/shortcuts/dlshort.py`.

## `references/`

Material from other projects retained only as implementation or design reference.

`styles.css` is a reference stylesheet from another project. It is not a pworksIphone runtime dependency and should not be treated as the production stylesheet.

## Relationship with `AGENTS.md`

Root [`../AGENTS.md`](../AGENTS.md) contains mandatory implementation and API-safety rules for coding agents. It remains at repository root for discoverability.

`devdocs/` provides supporting technical context. If documentation and implementation appear to disagree, inspect the underlying evidence rather than silently changing an evidence classification or assuming undocumented runtime behavior.
