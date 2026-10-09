---
name: export
description: >-
  Export Antigravity CLI sessions, transcripts, and artifacts into portable,
  sanitized archives (.agy.tar.gz), Markdown files, or standalone HTML transcripts.
  Use when the user invokes /export, "export session", "save session bundle",
  or "export transcript".
---

# Session Export Skill (`/export`)

This skill allows Antigravity agents to package the current or specified session, including its full transcript, generated artifacts, scratch files, and metadata into a shareable bundle or human-readable format.

## Overview

When the user requests an export, invoke the `export_bundle.py` script located in this plugin's `scripts/` directory using `run_command`.

### Plugin Script Location
```text
C:\Users\kmric\.agents\plugins\agy-porter\scripts\export_bundle.py
```

## How to Execute

Use `run_command` to execute Python with the desired options.

```powershell
python "C:\Users\kmric\.agents\plugins\agy-porter\scripts\export_bundle.py" [OPTIONS]
```

### Command Options

Flag | Default | Description
:--- | :--- | :---
`--conversation-id <UUID>` | Current session | Conversation UUID to export. Defaults to the active session.
`--app-data-dir <PATH>` | `~/.gemini/antigravity-cli` | Antigravity CLI application state directory.
`--output <PATH>` | `./agy-export-<id>-<timestamp>.<ext>` | Destination file path.
`--format <TYPE>` | `bundle` | Export format: `bundle` (`.agy.tar.gz`), `markdown` (`.md`), or `html` (`.html`).
`--sanitize <LEVEL>` | `relaxed` | Redaction level: `strict` (all secrets, tokens, .env, and passwords), `relaxed` (API keys, tokens, user home paths), or `none` (no sanitization).
`--workspace <PATH>` | Current working directory | Project root for relative path anonymization and `.env` discovery.

## Usage Scenarios

### 1. Standard Session Bundle Export (Recommended)
Packages full transcripts and artifacts with relaxed sanitization (scrubbing keys and paths):
```powershell
python "C:\Users\kmric\.agents\plugins\agy-porter\scripts\export_bundle.py" --format bundle --sanitize relaxed
```

### 2. Export as Human-Readable Markdown Transcript
Creates a clean, formatted Markdown document with collapsible tool calls and thinking processes:
```powershell
python "C:\Users\kmric\.agents\plugins\agy-porter\scripts\export_bundle.py" --format markdown --output "./session-transcript.md"
```

### 3. Export as Standalone HTML
Generates a self-contained, beautifully styled HTML transcript:
```powershell
python "C:\Users\kmric\.agents\plugins\agy-porter\scripts\export_bundle.py" --format html --output "./session-transcript.html"
```

### 4. High-Security / Strict Redaction
Redacts all passwords, API keys, and environment variables from transcripts:
```powershell
python "C:\Users\kmric\.agents\plugins\agy-porter\scripts\export_bundle.py" --sanitize strict
```

## Post-Export Response
After executing the export command:
1. Confirm the destination file path created.
2. Note the sanitization level applied.
3. If Markdown or HTML was generated, provide a clickable file link to the user.
