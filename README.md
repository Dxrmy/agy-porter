# agy-porter 📦

**Portable session, artifact, and customization import/export plugin for Google Antigravity (Desktop App & `agy` CLI).**

`agy-porter` equips Antigravity with `/export` and `/import` capabilities, allowing you to package active conversation threads, plans, and diffs into sanitized bundles (`.agy.tar.gz`) or human-readable formats (Markdown and HTML), and resume or fork sessions across machines.

---

## ⚡ Quick Install (One-Line Commands)

### Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/Dxrmy/agy-porter/main/install.ps1 | iex
```
*or via git:*
```powershell
git clone https://github.com/Dxrmy/agy-porter.git "$HOME\.gemini\config\plugins\agy-porter"
```

### Linux / macOS (Bash / Zsh)
```bash
curl -fsSL https://raw.githubusercontent.com/Dxrmy/agy-porter/main/install.sh | bash
```
*or via git:*
```bash
git clone https://github.com/Dxrmy/agy-porter.git "$HOME/.gemini/config/plugins/agy-porter"
```

Once installed, restart or open Antigravity Desktop or run `agy`. The `/export` and `/import` skills are immediately active.

---

## 🚀 Features

- **🛡️ Multi-Level Secret Sanitization**: Scrubs API keys (Google Gemini, OpenAI, GitHub PATs, AWS, Slack, Bearer tokens, private keys) and environment variables (`.env`).
- **🔒 Zip-Slip Protection**: Hardened tarball extractor that rejects directory traversal attacks.
- **✨ Multiple Formats**:
  - **Archive Bundle** (`.agy.tar.gz`): Machine-readable package containing full step trajectories, models, and artifacts.
  - **Markdown Transcript** (`.md`): Turn-by-turn log with collapsible `<details>` for agent reasoning and tool executions.
  - **Standalone HTML** (`.html`): Responsive self-contained viewer with code syntax highlighting and cards.
- **🔀 Session Forking**: Unpack and resume any colleague's session with fresh UUIDs without clobbering existing local conversation logs.
- **🖥️ Dual Desktop & CLI Parity**: Works identically inside the Antigravity Desktop App chat canvas and the `agy` terminal interface.

---

## 📖 Usage

### Inside Antigravity Chat (Desktop App or CLI)

```text
/export
```
Exports the current conversation and artifacts into a sanitized `.agy.tar.gz` bundle.

```text
/export --format markdown
/export --format html
```
Generates a formatted report for GitHub PRs, issues, or offline review.

```text
/import ./session.agy.tar.gz --mode inspect
```
Safely inspects turn counts, model, and security tags without unpacking.

```text
/import ./session.agy.tar.gz --mode fork
```
Unpacks and forks the session so you can immediately resume coding from where it left off.

---

## 🧪 Testing

Run the included automated test suite:
```powershell
python -m unittest discover -s tests -v
```

All 23 unit and integration tests verify redaction patterns, path masking, bundle integrity, and roundtrip imports.
