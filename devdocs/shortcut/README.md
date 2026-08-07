# VERSION$00028$ | Edited: 07/08 | TIME: 04:02

# Run Img2Video in a-Shell — Exact Shortcut Reconstruction

## Scope and evidence

This document reconstructs the **latest confirmed** version of the iOS Shortcut named:

```text
Run Img2Video in a-Shell
```

Evidence status for this revision:

- **Confirmed from extracted workflow files:** the binary plist and XML plist decode to the same 14-action workflow.
- **Confirmed from the CloudKit sharing record:** shared Shortcut name, signing status, and asset references.
- **Superseded:** the previous 18-action and 14-action reports are replaced by this revision.
- **Not inferred unless explicitly labeled:** all action order, parameters, output names, conditions, save locations, and a-Shell command payloads below come from the extracted Shortcut export.

Files used for this update:

```text
/mnt/data/Run_Img2Video_in_a-Shell(2).plist
/mnt/data/Run_Img2Video_in_a-Shell(2).xml
/mnt/data/Run_Img2Video_in_a-Shell.record(2).json
```

The binary plist and XML plist are structurally identical.

---

## High-level summary

This latest Shortcut version is shorter and more specific than the previous one:

- **14 actions** instead of 18.
- No extension whitelist list.
- No lowercase-normalization step.
- No intermediate list-plus-combine chain for the final command path.
- The existence test now compares the requested filename parts directly against the retrieved file's:
  - **Name**
  - **File Extension**
- The final a-Shell Mini action contains **two commands**:
  1. `cd  ~File\ Provider\ Storage/`
  2. `CMDfinal`

The currently confirmed Photos search contains **exactly two filters**:

1. `Name is trimmedFilename`
2. `Creation Date is after 06/01/2026 23:30`

There is **no Album filter** in this latest export.

---

## Shortcut-level configuration

### Share Sheet and input behavior

The Shortcut is configured as an Action Extension and accepts Share Sheet input.

**Confirmed workflow types:**

```text
Watch
ActionExtension
WFWorkflowTypeShowInSearch
```

**Confirmed accepted input content classes (19):**

```text
WFAppContentItem
WFAppStoreAppContentItem
WFArticleContentItem
WFContactContentItem
WFDateContentItem
WFEmailAddressContentItem
WFFolderContentItem
WFGenericFileContentItem
WFImageContentItem
WFiTunesProductContentItem
WFLocationContentItem
WFDCMapsLinkContentItem
WFAVAssetContentItem
WFPDFContentItem
WFPhoneNumberContentItem
WFRichTextContentItem
WFSafariWebPageContentItem
WFStringContentItem
WFURLContentItem
```

This corresponds to the UI wording:

```text
Apps et 18 de plus
```

**Confirmed no-input behavior:**

```text
If there is no input:
Ask for Text
```

The workflow-level no-input setting is:

```text
WFWorkflowNoInputBehaviorAskForInput
ItemClass = WFStringContentItem
```

---

## Expected input structure

The Shortcut expects its Share Sheet input to be convertible into a dictionary.

The visible keys used by the workflow are:

```text
filename
cmd
```

Conceptual structure:

```json
{
  "filename": "example.png",
  "cmd": "python3 ...existing command arguments..."
}
```

No additional required keys are referenced in the extracted workflow.

---

# Exact action sequence

## Action 1 — Convert the Shortcut input into a dictionary

**Action identifier:**

```text
is.workflow.actions.detect.dictionary
```

**Visible action meaning:**

```text
Get Dictionary from Shortcut Input
```

**Input:**

```text
Shortcut Input / Share Sheet input
```

**Output variable renamed to:**

```text
JSON
```

---

## Action 2 — Read the `filename` dictionary value

**Action identifier:**

```text
is.workflow.actions.getvalueforkey
```

**Dictionary key:**

```text
filename
```

**Input dictionary:**

```text
JSON
```

**Output variable renamed to:**

```text
filename
```

This contains the requested image filename.

---

## Action 3 — Attempt to retrieve the existing file

**Action identifier:**

```text
is.workflow.actions.documentpicker.open
```

**Visible action meaning:**

```text
Get File
```

**Confirmed storage provider:**

```text
Sur mon iPhone
└── File Provider Storage
```

**Confirmed path template:**

```text
~File\ Provider\ Storage/filename
```

In the exported action, the file path is dynamically built from:

- the literal path prefix `~File\ Provider\ Storage/`
- the magic variable `filename`

**Confirmed error behavior:**

```text
File not found error disabled
```

Internal flag:

```text
WFFileErrorIfNotFound = false
```

**Output variable renamed to:**

```text
Inputfile
```

Logical role:

```text
Attempt to retrieve the requested file from File Provider Storage without stopping the Shortcut if it is missing.
```

---

## Action 4 — Split `filename` on the dot character

**Action identifier:**

```text
is.workflow.actions.text.split
```

**Visible action meaning:**

```text
Split Text
```

**Input variable:**

```text
filename
```

**Separator type:**

```text
Custom
```

**Custom separator:**

```text
.
```

**Output variable renamed to:**

```text
CutDotList
```

Example:

```text
IMG_1234.png → ["IMG_1234", "png"]
```

---

## Action 5 — Get the first item of the split list

**Action identifier:**

```text
is.workflow.actions.getitemfromlist
```

**Input list:**

```text
CutDotList
```

**Selected item:**

```text
First Item
```

**Output variable renamed to:**

```text
trimmedFilename
```

Example:

```text
["IMG_1234", "png"] → "IMG_1234"
```

---

## Action 6 — Get the last item of the split list

**Action identifier:**

```text
is.workflow.actions.getitemfromlist
```

**Input list:**

```text
CutDotList
```

**Selected item:**

```text
Last Item
```

**Output variable renamed to:**

```text
TrimmedExr
```

Example:

```text
["IMG_1234", "png"] → "png"
```

The output name is spelled exactly as exported:

```text
TrimmedExr
```

---

## Action 7 — Test whether the retrieved file matches the requested filename

**Action identifier:**

```text
is.workflow.actions.conditional
```

**Control-flow mode:**

```text
If
```

**Confirmed logic:** all conditions must be true.

The plist stores two condition templates with `WFActionParameterFilterPrefix = 1`, which corresponds to the “all of the following are true” behavior.

### Condition 1

Compare:

```text
trimmedFilename
```

against the `Name` property of:

```text
Inputfile
```

**Confirmed relation:**

```text
is
```

### Condition 2

Compare:

```text
TrimmedExr
```

against the `File Extension` property of:

```text
Inputfile
```

**Confirmed relation:**

```text
is
```

**Equivalent logic:**

```text
if (
    trimmedFilename == Inputfile.Name
    and
    TrimmedExr == Inputfile.File Extension
)
```

### True branch

No actions are present in the true branch.

Logical meaning:

```text
The file already exists in File Provider Storage and matches the requested name and extension.
```

---

## Action 8 — Otherwise marker

**Action identifier:**

```text
is.workflow.actions.conditional
```

**Control-flow mode:**

```text
Otherwise
```

This begins the fallback branch used when the file is missing or does not match.

---

## Action 9 — Search the Photos library

**Action identifier:**

```text
is.workflow.actions.filter.photos
```

**Visible action meaning:**

```text
Find Photos
```

**Output variable renamed to:**

```text
FoundPhotoRoll
```

### Confirmed filters

The extracted workflow contains **exactly two filters**:

1. **Name**
   ```text
   Name is trimmedFilename
   ```

2. **Creation Date**
   ```text
   Creation Date is after 06/01/2026 23:30
   ```

The stored UTC date is:

```text
2026-01-06 22:30:00
```

which corresponds to:

```text
06/01/2026 23:30
```

in Europe/Paris in January.

### Confirmed filter combination mode

```text
All conditions must be true
```

### Confirmed sorting

```text
Sort by: Last Modified Date
Order: Latest First
```

### Confirmed result limit

```text
Limit enabled
Get 1 item
```

**Equivalent logic:**

```text
FoundPhotoRoll =
    latest modified photo where:
        photo.name == trimmedFilename
        and photo.creation_date > 06/01/2026 23:30
    limit 1
```

---

## Action 10 — Save the found photo into Files

**Action identifier:**

```text
is.workflow.actions.documentpicker.save
```

**Visible action meaning:**

```text
Save File
```

**Input variable:**

```text
FoundPhotoRoll
```

**Confirmed destination:**

```text
Sur mon iPhone
└── File Provider Storage
```

**Confirmed options:**

```text
Ask Where to Save: false
Overwrite Existing File: true
```

Internal flags:

```text
WFAskWhereToSave = false
WFSaveFileOverwrite = true
```

Logical meaning:

```text
Save the matching photo directly into File Provider Storage, using the preconfigured destination without asking.
```

---

## Action 11 — End the conditional branch

**Action identifier:**

```text
is.workflow.actions.conditional
```

**Control-flow mode:**

```text
End If
```

This closes the `If / Otherwise / End If` structure.

---

## Action 12 — Read the `cmd` dictionary value

**Action identifier:**

```text
is.workflow.actions.getvalueforkey
```

**Dictionary key:**

```text
cmd
```

**Input dictionary:**

```text
JSON
```

**Output variable renamed to:**

```text
CmdText
```

This contains the base Python command text provided by the caller.

---

## Action 13 — Construct the final one-line command

**Action identifier:**

```text
is.workflow.actions.gettext
```

**Visible action type:**

```text
Text
```

**Output variable renamed to:**

```text
CMDfinal
```

**Confirmed text structure:**

The exported token string contains:

- the variable `CmdText`;
- a literal space;
- the literal text `~File\ Provider\ Storage/`;
- the variable `filename`.

**Equivalent command formula:**

```text
CMDfinal = CmdText + " " + "~File\ Provider\ Storage/" + filename
```

**Example:**

```text
python3 img2video_iphone.py --prompt "Motion" ~File\ Provider\ Storage/IMG_1234.png
```

This replaces the older multi-step chain of:

- ImgFullPath
- List
- Combine Text

---

## Action 14 — Execute in a-Shell Mini

**Action identifier:**

```text
AsheKube.app.a-Shell-mini.ExecuteCommandIntent
```

This is the final action in the Shortcut.

### Confirmed parameter payload

The exported action stores `command` as a two-item sequence:

1. first command:

   ```text
   cd  ~File\ Provider\ Storage/
   ```

   This string contains **two spaces** after `cd` in the export.

2. second command:

   ```text
   CMDfinal
   ```

   inserted as the action output variable from Action 13.

**Equivalent behavior:**

```text
Execute these commands in a-Shell Mini:
1. cd  ~File\ Provider\ Storage/
2. <expanded CMDfinal>
```

No additional action parameters are stored in the export.

---

# Complete structured flow

```text
Receive Share Sheet input
    └─ If there is no input: Ask for Text

JSON = Get Dictionary from Shortcut Input

filename = Get "filename" from JSON

Inputfile = Get File from:
    On My iPhone/File Provider Storage
    path = ~File\ Provider\ Storage/filename
    error if missing = false

CutDotList = split filename at "."
trimmedFilename = first item of CutDotList
TrimmedExr = last item of CutDotList

If:
    trimmedFilename == Inputfile.Name
    and
    TrimmedExr == Inputfile.File Extension

    do nothing

Otherwise:
    FoundPhotoRoll = Find Photos where:
        Name is trimmedFilename
        AND Creation Date is after 06/01/2026 23:30
        Sort by Last Modified Date
        Order Latest First
        Limit 1

    Save FoundPhotoRoll to:
        On My iPhone/File Provider Storage
        Ask Where to Save = false
        Overwrite = true
End If

CmdText = Get "cmd" from JSON

CMDfinal = CmdText + " " + "~File\ Provider\ Storage/" + filename

Execute in a-Shell Mini:
    cd  ~File\ Provider\ Storage/
    CMDfinal
```

---

# Variable inventory

| Variable name | Produced by | Content |
|---|---|---|
| `JSON` | Action 1 | Parsed input dictionary |
| `filename` | Action 2 | Requested image filename |
| `Inputfile` | Action 3 | Retrieved file from File Provider Storage |
| `CutDotList` | Action 4 | `filename` split on `.` |
| `trimmedFilename` | Action 5 | First item of `CutDotList` |
| `TrimmedExr` | Action 6 | Last item of `CutDotList` |
| `FoundPhotoRoll` | Action 9 | First matching photo from Photos |
| `CmdText` | Action 12 | Base Python command string |
| `CMDfinal` | Action 13 | Final one-line command including image path |

---

# Differences from the previous report

Compared with **VERSION$00027$**, this latest confirmed export changes the report in these ways:

1. **Confirmed from export:** no Album filter is present.
2. The Shortcut has **14 actions**, not 18.
3. The extension-whitelist logic is gone.
4. The file-match test now compares:
   - requested basename vs `Inputfile.Name`
   - requested extension vs `Inputfile.File Extension`
5. The Photos search now sorts by:
   - `Last Modified Date`
   - `Latest First`
6. The final command assembly is now one Text action named `CMDfinal`.
7. The a-Shell Mini action now stores two commands:
   - `cd  ~File\ Provider\ Storage/`
   - `CMDfinal`

---

# Record metadata

The associated shared-record metadata confirms:

- Name:
  ```text
  Run Img2Video in a-Shell
  ```
- Signing status:
  ```text
  APPROVED
  ```
- Record type:
  ```text
  SharedShortcut
  ```

This metadata comes from:

```text
Run_Img2Video_in_a-Shell.record(2).json
```

It is supplementary and does not replace the workflow extraction.

---

# Validation performed

Performed for this report update:

- Decoded the binary plist successfully.
- Decoded the XML plist successfully.
- Verified the binary plist and XML plist are identical after decoding.
- Verified the action count is exactly 14.
- Verified the latest export contains no Album filter.
- Verified the save destination is `On My iPhone/File Provider Storage`.
- Verified the save flags `Ask Where to Save = false` and `Overwrite = true`.
- Verified the a-Shell Mini action stores two commands.
- Verified the CloudKit record name and signing status.

Not performed:

- No live Shortcut execution.
- No Share Sheet run on-device.
- No ArtWorks API call.
- No potentially billable task submission.

