"""formatters.py - Human-readable Markdown and HTML transcript formatters.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any, Dict, List, Optional


def clean_user_content(content: str) -> str:
    """Extract core user request while preserving tags if needed."""
    if not isinstance(content, str):
        return str(content)
    # Check if wrapped in <USER_REQUEST>
    req_match = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", content, re.DOTALL)
    if req_match:
        return req_match.group(1).strip()
    return content.strip()


def parse_json_lines(transcript_text: str) -> List[Dict[str, Any]]:
    """Parse JSONL content into list of step dictionaries."""
    steps = []
    for line in transcript_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            steps.append(json.loads(line))
        except Exception:
            continue
    return steps


def transcript_to_markdown(
    steps: List[Dict[str, Any]],
    title: str = "Antigravity Session Transcript",
    conversation_id: str = "",
    model_name: str = "",
) -> str:
    """Formats transcript steps into human-readable GitHub-flavored Markdown."""
    lines: List[str] = [
        f"# {title}",
        "",
        f"- **Conversation ID**: `{conversation_id or 'N/A'}`",
        f"- **Model**: {model_name or 'Unknown'}",
        f"- **Total Steps**: {len(steps)}",
        "",
        "---",
        "",
    ]

    for step in steps:
        step_idx = step.get("step_index", "?")
        source = step.get("source", "")
        step_type = step.get("type", "")
        created_at = step.get("created_at", "")
        thinking = step.get("thinking", "")
        tool_calls = step.get("tool_calls", [])
        content = step.get("content", "")

        # Role heading
        if source == "USER_EXPLICIT" or step_type == "USER_INPUT":
            role_badge = "👤 **User**"
            display_content = clean_user_content(content)
        elif source == "MODEL" and step_type == "PLANNER_RESPONSE":
            role_badge = "🤖 **Antigravity Agent**"
            display_content = content
        elif source == "MODEL" and step_type == "GENERIC":
            role_badge = "⚙️ **Tool Execution Output**"
            display_content = content
        elif source == "SYSTEM":
            role_badge = "🖥️ **System Message**"
            display_content = content
        else:
            role_badge = f"📝 **{source or step_type or 'Step'}**"
            display_content = content

        time_str = f" `{created_at}`" if created_at else ""
        lines.append(f"### Step {step_idx} — {role_badge}{time_str}\n")

        # Thinking block
        if thinking and thinking.strip():
            lines.append("<details>")
            lines.append("<summary>💭 <i>Agent Thinking Process</i></summary>\n")
            lines.append(f"{thinking.strip()}\n")
            lines.append("</details>\n")

        # Tool calls
        if tool_calls:
            for tc in tool_calls:
                t_name = tc.get("name", "tool")
                t_args = tc.get("args", {})
                lines.append(f"🔧 **Tool Call**: `{t_name}`\n")
                lines.append("```json")
                lines.append(json.dumps(t_args, indent=2))
                lines.append("```\n")

        # Main content
        if display_content and display_content.strip():
            if step_type == "GENERIC" or "File Path:" in display_content:
                lines.append("<details>")
                lines.append("<summary>📄 View Output</summary>\n")
                lines.append("```text")
                lines.append(display_content.strip())
                lines.append("```\n")
                lines.append("</details>\n")
            else:
                lines.append(f"{display_content.strip()}\n")

        lines.append("---\n")

    return "\n".join(lines)


def transcript_to_html(
    steps: List[Dict[str, Any]],
    title: str = "Antigravity Session Transcript",
    conversation_id: str = "",
    model_name: str = "",
) -> str:
    """Formats transcript steps into a standalone, styled HTML document with collapsible sections."""
    escaped_title = html.escape(title)
    escaped_conv_id = html.escape(conversation_id or "N/A")
    escaped_model = html.escape(model_name or "Unknown")

    html_parts: List[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="UTF-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f"  <title>{escaped_title}</title>",
        "  <style>",
        "    :root {",
        "      --bg: #1e1e2e;",
        "      --surface: #252538;",
        "      --border: #3b3b54;",
        "      --text: #cdd6f4;",
        "      --text-muted: #a6adc8;",
        "      --accent: #89b4fa;",
        "      --code-bg: #181825;",
        "      --user-badge: #a6e3a1;",
        "      --agent-badge: #89b4fa;",
        "      --tool-badge: #fab387;",
        "    }",
        "    body {",
        "      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;",
        "      background-color: var(--bg);",
        "      color: var(--text);",
        "      line-height: 1.6;",
        "      margin: 0;",
        "      padding: 2rem 1rem;",
        "    }",
        "    .container {",
        "      max-width: 900px;",
        "      margin: 0 auto;",
        "    }",
        "    header {",
        "      border-bottom: 2px solid var(--border);",
        "      padding-bottom: 1.5rem;",
        "      margin-bottom: 2rem;",
        "    }",
        "    h1 { color: #fff; margin-top: 0; }",
        "    .meta { display: flex; gap: 1.5rem; flex-wrap: wrap; color: var(--text-muted); font-size: 0.95rem; }",
        "    .meta-tag { background: var(--surface); padding: 0.3rem 0.6rem; border-radius: 4px; border: 1px solid var(--border); }",
        "    .step-card {",
        "      background: var(--surface);",
        "      border: 1px solid var(--border);",
        "      border-radius: 8px;",
        "      padding: 1.25rem;",
        "      margin-bottom: 1.5rem;",
        "      box-shadow: 0 4px 6px rgba(0,0,0,0.1);",
        "    }",
        "    .step-header {",
        "      display: flex;",
        "      justify-content: space-between;",
        "      align-items: center;",
        "      margin-bottom: 0.75rem;",
        "      border-bottom: 1px solid rgba(255,255,255,0.06);",
        "      padding-bottom: 0.5rem;",
        "    }",
        "    .badge {",
        "      font-weight: 600;",
        "      font-size: 0.85rem;",
        "      padding: 0.2rem 0.6rem;",
        "      border-radius: 4px;",
        "      text-transform: uppercase;",
        "    }",
        "    .badge-user { background: rgba(166, 227, 161, 0.15); color: var(--user-badge); }",
        "    .badge-agent { background: rgba(137, 180, 250, 0.15); color: var(--agent-badge); }",
        "    .badge-tool { background: rgba(250, 179, 135, 0.15); color: var(--tool-badge); }",
        "    .timestamp { font-size: 0.8rem; color: var(--text-muted); font-family: monospace; }",
        "    pre, code { font-family: 'JetBrains Mono', Consolas, Monaco, monospace; }",
        "    pre {",
        "      background: var(--code-bg);",
        "      padding: 1rem;",
        "      border-radius: 6px;",
        "      overflow-x: auto;",
        "      border: 1px solid var(--border);",
        "      margin: 0.5rem 0;",
        "      font-size: 0.9rem;",
        "    }",
        "    details {",
        "      background: rgba(0,0,0,0.15);",
        "      border: 1px solid var(--border);",
        "      border-radius: 6px;",
        "      margin: 0.75rem 0;",
        "      padding: 0.5rem 0.75rem;",
        "    }",
        "    summary { cursor: pointer; font-weight: 500; color: var(--accent); }",
        "    .tool-box { margin-top: 0.5rem; }",
        "    .tool-title { font-weight: 600; color: var(--tool-badge); font-size: 0.9rem; }",
        "    .content-body { white-space: pre-wrap; word-break: break-word; font-size: 0.95rem; }",
        "  </style>",
        "</head>",
        "<body>",
        '  <div class="container">',
        "    <header>",
        f"      <h1>{escaped_title}</h1>",
        '      <div class="meta">',
        f'        <div class="meta-tag">🆔 ID: {escaped_conv_id}</div>',
        f'        <div class="meta-tag">🤖 Model: {escaped_model}</div>',
        f'        <div class="meta-tag">📊 Turns: {len(steps)}</div>',
        "      </div>",
        "    </header>",
        '    <main class="steps">',
    ]

    for step in steps:
        step_idx = step.get("step_index", "?")
        source = step.get("source", "")
        step_type = step.get("type", "")
        created_at = step.get("created_at", "")
        thinking = step.get("thinking", "")
        tool_calls = step.get("tool_calls", [])
        content = step.get("content", "")

        badge_class = "badge-agent"
        badge_label = "Agent"

        if source == "USER_EXPLICIT" or step_type == "USER_INPUT":
            badge_class = "badge-user"
            badge_label = "User"
            display_content = clean_user_content(content)
        elif source == "MODEL" and step_type == "PLANNER_RESPONSE":
            badge_class = "badge-agent"
            badge_label = "Agent"
            display_content = content
        elif source == "MODEL" and step_type == "GENERIC":
            badge_class = "badge-tool"
            badge_label = "Tool Output"
            display_content = content
        else:
            badge_class = "badge-tool"
            badge_label = source or step_type or "Step"
            display_content = content

        html_parts.append('      <div class="step-card">')
        html_parts.append('        <div class="step-header">')
        html_parts.append(f'          <span class="badge {badge_class}">{html.escape(badge_label)} (Step {step_idx})</span>')
        if created_at:
            html_parts.append(f'          <span class="timestamp">{html.escape(created_at)}</span>')
        html_parts.append("        </div>")

        # Thinking
        if thinking and thinking.strip():
            html_parts.append("        <details>")
            html_parts.append("          <summary>💭 Agent Thinking Process</summary>")
            html_parts.append(f"          <pre>{html.escape(thinking.strip())}</pre>")
            html_parts.append("        </details>")

        # Tool calls
        if tool_calls:
            for tc in tool_calls:
                t_name = html.escape(str(tc.get("name", "tool")))
                t_args_str = json.dumps(tc.get("args", {}), indent=2)
                html_parts.append('        <div class="tool-box">')
                html_parts.append(f'          <div class="tool-title">🔧 Tool Call: {t_name}</div>')
                html_parts.append(f"          <pre>{html.escape(t_args_str)}</pre>")
                html_parts.append("        </div>")

        # Main content
        if display_content and display_content.strip():
            if step_type == "GENERIC" or "File Path:" in display_content:
                html_parts.append("        <details>")
                html_parts.append("          <summary>📄 View Output Data</summary>")
                html_parts.append(f"          <pre>{html.escape(display_content.strip())}</pre>")
                html_parts.append("        </details>")
            else:
                html_parts.append(f'        <div class="content-body">{html.escape(display_content.strip())}</div>')

        html_parts.append("      </div>")

    html_parts.extend([
        "    </main>",
        "  </div>",
        "</body>",
        "</html>",
    ])

    return "\n".join(html_parts)
