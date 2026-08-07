# VERSION$00037$ | Edited: 07/08 | TIME: 05:47
# Exporting a Public iOS Shortcut as JSON — External Reference

Source: https://gist.github.com/aont/560515bbd627b5f60f3cf25559262242

## Why this reference is kept

The linked gist documents a useful end-to-end path for inspecting a publicly shared iOS Shortcut. It complements `tools/shortcuts/dlshort.py` and is retained as external implementation/reference material, not as the project's production Shortcut tool.

## Workflow summarized

Given a public iCloud Shortcut URL such as:

```text
https://www.icloud.com/shortcuts/<ID>
```

retrieve its metadata from:

```text
https://www.icloud.com/shortcuts/api/records/<ID>
```

Then read the unsigned workflow asset URL from:

```text
records[0].fields.shortcut.value.downloadURL
```

Download that plist and decode it with a plist parser. In Python, the standard-library `plistlib` module can load the binary/XML plist and the resulting Python object can be serialized to JSON for inspection.

## Project-specific note

The gist's reference Python implementation uses the third-party `requests` package. For this iPhone/a-Shell Mini project, prefer the existing `tools/shortcuts/dlshort.py` implementation because the project favors portable standard-library Python and minimal dependencies.

Treat iCloud record metadata and temporary asset URLs as transient evidence. Do not commit expiring CloudKit URLs, device identifiers, or unrelated record metadata unless they are deliberately sanitized and needed for a reproducible report.
