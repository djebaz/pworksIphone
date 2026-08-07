<!-- VERSION$00032$ | Edited: 07/08 | TIME: 04:47 -->
# pworksIphone

Image-to-video workflow designed for iPhone, a-Shell Mini, iOS Shortcuts, and the ArtWorks.ai API.

The repository separates production runtime files, Shortcut-facing UI, reusable development tools, experiments, and developer documentation.

## Repository structure

```text
pworksIphone/
├── README.md
├── AGENTS.md
├── .gitignore
│
├── app/
│   ├── img2video_iphone.py
│   └── artworks_settings.example.txt
│
├── shortcuts/
│   └── img2video/
│       └── index.html
│
├── tools/
│   ├── shortcuts/
│   │   └── dlshort.py
│   └── probes/
│       ├── probe_img2video_effective_timing.py
│       ├── probe_img2video_discover_values.py
│       ├── probe_img2video_using_client.py
│       └── img2video_iphone_timing_probe.py
│
├── experiments/
│   └── multipart-candidates/
│       └── img2video_iphone_multipart_candidates.py
│
└── devdocs/
    ├── README.md
    ├── api.md
    ├── shortcut/
    │   ├── README.md
    │   ├── annotated-en.html
    │   └── annotated-fr.html
    └── references/
        └── styles.css
```

## Main components

### `app/`

Production Python runtime for image-to-video generation on iPhone. `img2video_iphone.py` is the main application script. The tracked settings file is an example; personal credentials, mutable settings, prompts, recovery state, and generated media should remain local.

### `shortcuts/`

Runtime components directly involved in the iOS Shortcut workflow. `shortcuts/img2video/index.html` is the current Safari UI that prepares the `{filename, cmd}` payload and launches `Run Img2Video in a-Shell`.

### `tools/`

Reusable development utilities. `tools/shortcuts/dlshort.py` downloads and extracts unsigned iCloud Shortcut data. ArtWorks API discovery and timing probes live under `tools/probes/`.

Some probe commands may create real ArtWorks tasks and may therefore be billable. Read their help and `AGENTS.md` before running them.

### `experiments/`

Non-production implementations and prototypes. Experimental behavior should be merged into the production application only after validation.

### `devdocs/`

Developer documentation and reference material. See [`devdocs/README.md`](devdocs/README.md) for the documentation map.

## Agent instructions

Read [`AGENTS.md`](AGENTS.md) before modifying code that creates, validates, polls, cancels, downloads, or analyzes ArtWorks.ai image-to-video tasks.

The project distinguishes API behavior as **Documented**, **Confirmed**, **Inferred**, or **User-reported**. Preserve those distinctions in code comments, reports, tests, and documentation.

## Local files and secrets

Do not commit credentials, mutable runtime state, personal prompt/configuration files, logs, generated media, or temporary outputs. The repository `.gitignore` contains the standard exclusions for this workflow.
