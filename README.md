<!-- VERSION$00039$ | Edited: 07/08 | TIME: 05:57 -->
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
│   ├── artworks_credentials.example.txt
│   ├── artworks_settings.example.txt
│   ├── prompts.example.txt
│   └── randomprompt.example.txt
│
├── shortcuts/
│   └── img2video/
│       ├── index.html
│       └── dist/
│           └── Run_Img2Video_in_a-Shell.shortcut
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
        ├── export-public-shortcut-as-json.md
        └── styles.css
```

## Main components

### `app/`

Production Python runtime for image-to-video generation on iPhone. `img2video_iphone.py` is the main application script. The tracked settings, credentials, and prompt files are examples only; real credentials, mutable settings, personal prompts, recovery state, and generated media should remain local.

### `shortcuts/`

Runtime components directly involved in the iOS Shortcut workflow.

- `shortcuts/img2video/index.html` is the Safari launcher/UI. It prepares the `{filename, cmd}` payload and launches `Run Img2Video in a-Shell`.
- `shortcuts/img2video/dist/` contains the signed, installable Shortcut artifact (`Run_Img2Video_in_a-Shell.shortcut`) that users import into the iOS Shortcuts app. This binary is not modified by hand; it is exported/signed from the Shortcuts app itself.

### `tools/`

Reusable development utilities. `tools/shortcuts/dlshort.py` is the project utility used to download and extract unsigned iCloud Shortcut data. ArtWorks API discovery and timing probes live under `tools/probes/`.

Some probe commands may create real ArtWorks tasks and may therefore be billable. Read their help and `AGENTS.md` before running them.

### `experiments/`

Non-production implementations and prototypes. Experimental behavior should be merged into the production application only after validation.

### `devdocs/`

Developer documentation and reference material. `devdocs/shortcut/` contains reconstruction and reference documentation for the Shortcut workflow, not the installable Shortcut itself — the installable artifact lives at `shortcuts/img2video/dist/`. See [`devdocs/README.md`](devdocs/README.md) for the full documentation map.

## Local setup

The production client looks for its local configuration files beside `app/img2video_iphone.py`.

1. Copy `app/artworks_credentials.example.txt` to `app/artworks_credentials.txt`, then fill in your own ArtWorks username and password locally.
2. Copy `app/artworks_settings.example.txt` to `app/artworks_settings.txt` when you want a local editable settings file.
3. Copy `app/prompts.example.txt` to `app/prompts.txt` and/or `app/randomprompt.example.txt` to `app/randomprompt.txt` when you want file-based prompts. Edit those local copies as needed.

The real `artworks_credentials.txt`, personal prompt files, mutable settings, runtime/recovery state, logs, generated media, and temporary files are intentionally untracked. Never commit real credential values.

## Agent instructions

Read [`AGENTS.md`](AGENTS.md) before modifying code that creates, validates, polls, cancels, downloads, or analyzes ArtWorks.ai image-to-video tasks.

The project distinguishes API behavior as **Documented**, **Confirmed**, **Inferred**, or **User-reported**. Preserve those distinctions in code comments, reports, tests, and documentation.

## Local files and secrets

Do not commit credentials, mutable runtime state, personal prompt/configuration files, logs, generated media, or temporary outputs. The repository `.gitignore` contains the standard exclusions for this workflow while explicitly allowing the tracked `.example.txt` templates.
