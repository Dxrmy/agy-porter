---
name: import
description: >-
  Import, inspect, or fork Antigravity CLI session bundles (.agy.tar.gz / .agypack).
  Allows loading previous transcripts, artifacts, and customizations into new or
  existing workspaces. Use when the user invokes /import, "import session",
  "load session bundle", or "resume session from file".
---

# Session Import Skill (`/import`)

This skill allows Antigravity agents to import and fork session bundles, inspect their contents and security posture, or extract customizations safely.

## Overview

When the user requests an import, invoke the `import_bundle.py` script located in this plugin's `scripts/` directory using `run_command`.

### Plugin Script Location
```text
C:\Users\kmric\.agents\plugins\agy-porter\scripts\import_bundle.py
```

## How to Execute

Use `run_command` to execute Python with the bundle file and desired mode.

```powershell
python "C:\Users\kmric\.agents\plugins\agy-porter\scripts\import_bundle.py" <PATH_TO_BUNDLE> [OPTIONS]
```

### Command Options

Flag | Default | Description
:--- | :--- | :---
`<bundle_file>` | Required | Path to the `.agy.tar.gz` or `.agypack` bundle.
`--mode <MODE>` | `fork` | Operation mode: `fork` (creates new conversation), `inspect` or `review` (summary & security check), `customizations-only`.
`--target-app-data-dir <PATH>` | `~/.gemini/antigravity-cli` | Target application data directory.
`--target-workspace <PATH>` | Current working directory | Destination directory for customizations or artifacts.
`--dry-run` | `false` | Inspect the planned import actions without writing any files to disk.
`--trust` | `false` | Acknowledge and allow importing bundles containing executable scripts or MCP definitions.

## Usage Scenarios

### 1. Inspect / Review a Bundle Before Importing
Always check bundle contents, metadata, and security status first if from an external source:
```powershell
python "C:\Users\kmric\.agents\plugins\agy-porter\scripts\import_bundle.py" "./agy-export.agy.tar.gz" --mode inspect
```

### 2. Fork into a New Conversation
Unpacks transcripts and artifacts under a freshly generated UUID, updating internal IDs so the session can be resumed independently:
```powershell
python "C:\Users\kmric\.agents\plugins\agy-porter\scripts\import_bundle.py" "./agy-export.agy.tar.gz" --mode fork
```

### 3. Dry-Run Import
Simulate the fork operation to verify destination directories and unpacked items without writing:
```powershell
python "C:\Users\kmric\.agents\plugins\agy-porter\scripts\import_bundle.py" "./agy-export.agy.tar.gz" --mode fork --dry-run
```

### 4. Import Trusted Bundles with Scripts or MCP Tools
If the bundle contains helper scripts or MCP server definitions, provide the `--trust` flag:
```powershell
python "C:\Users\kmric\.agents\plugins\agy-porter\scripts\import_bundle.py" "./team-bundle.agy.tar.gz" --mode fork --trust
```

### 5. Extract Customizations Only
Import only workspace skills, rules, and configurations into the current `.agents/` folder:
```powershell
python "C:\Users\kmric\.agents\plugins\agy-porter\scripts\import_bundle.py" "./bundle.agy.tar.gz" --mode customizations-only
```

## Post-Import Actions
- In **fork** mode: Inform the user of the new conversation ID and explain how to resume it using `agy --conversation-id <NEW_UUID>`.
- In **inspect** mode: Summarize the turn count, model, files, and any security warnings detected.
