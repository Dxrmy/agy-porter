"""export_bundle.py - Export Antigravity CLI sessions to bundles, Markdown, or HTML.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from bundle import Manifest, SessionBundle
    from formatters import parse_json_lines, transcript_to_html, transcript_to_markdown
    from redactor import Redactor, SanitizeLevel
else:
    from .bundle import Manifest, SessionBundle
    from .formatters import parse_json_lines, transcript_to_html, transcript_to_markdown
    from .redactor import Redactor, SanitizeLevel


def find_default_app_data_dir(conversation_id: Optional[str] = None) -> Path:
    """Find default Antigravity app data directory (supporting Desktop App and CLI)."""
    home = Path.home()
    candidates = [
        home / ".gemini" / "antigravity",
        home / ".gemini" / "antigravity-cli",
    ]
    if conversation_id:
        for candidate in candidates:
            if (candidate / "brain" / conversation_id).is_dir():
                return candidate
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def find_latest_conversation(brain_dir: Path) -> Optional[str]:
    """Find the most recently modified conversation in the brain directory."""
    if not brain_dir.is_dir():
        return None

    conversations = []
    for item in brain_dir.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            try:
                mtime = item.stat().st_mtime
                conversations.append((mtime, item.name))
            except Exception:
                continue

    if not conversations:
        return None

    conversations.sort(reverse=True)
    return conversations[0][1]


def export_session(
    conversation_id: str,
    app_data_dir: Path,
    output_path: Path,
    export_format: str = "bundle",
    sanitize_level: str = "relaxed",
    workspace_dir: Optional[Path] = None,
) -> Path:
    """Core export function. Returns the created output file path."""
    brain_dir = app_data_dir / "brain" / conversation_id
    if not brain_dir.is_dir():
        raise FileNotFoundError(f"Conversation directory not found: {brain_dir}")

    # Set up redactor
    level = SanitizeLevel(sanitize_level.lower())
    redactor = Redactor(
        level=level,
        home_dir=Path.home(),
        workspace_dir=workspace_dir or Path.cwd(),
    )

    # Check for .env in workspace
    if workspace_dir:
        dotenv = workspace_dir / ".env"
        if dotenv.is_file():
            redactor.load_env_file(dotenv)

    # Locate transcript
    transcript_file = brain_dir / ".system_generated" / "logs" / "transcript.jsonl"
    if not transcript_file.exists():
        transcript_file = brain_dir / "transcript.jsonl"

    transcript_content = ""
    if transcript_file.exists():
        transcript_content = transcript_file.read_text(encoding="utf-8", errors="replace")
        if level != SanitizeLevel.NONE:
            transcript_content = redactor.redact_text(transcript_content)

    steps = parse_json_lines(transcript_content) if transcript_content else []
    turn_count, model_name = SessionBundle.parse_transcript_meta(transcript_content)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if export_format == "bundle":
        SessionBundle.create(
            output_tar_path=output_path,
            conversation_id=conversation_id,
            brain_dir=brain_dir,
            redactor=redactor,
            workspace_dir=workspace_dir,
        )
    elif export_format == "markdown":
        md_text = transcript_to_markdown(
            steps=steps,
            conversation_id=conversation_id,
            model_name=model_name,
        )
        output_path.write_text(md_text, encoding="utf-8")
    elif export_format == "html":
        html_text = transcript_to_html(
            steps=steps,
            conversation_id=conversation_id,
            model_name=model_name,
        )
        output_path.write_text(html_text, encoding="utf-8")
    else:
        raise ValueError(f"Unknown format: {export_format}")

    return output_path


def parse_args(args: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="export_bundle",
        description="Export an Antigravity CLI session to an archive bundle, Markdown, or HTML transcript.",
    )
    parser.add_argument(
        "--conversation-id",
        type=str,
        default=None,
        help="UUID of the conversation to export (defaults to current or latest session).",
    )
    parser.add_argument(
        "--app-data-dir",
        type=Path,
        default=None,
        help="Path to Antigravity CLI app data directory (default: ~/.gemini/antigravity-cli).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: ./agy-export-<id>-<timestamp>.<ext>).",
    )
    parser.add_argument(
        "--format",
        choices=["bundle", "markdown", "html"],
        default="bundle",
        help="Export format (bundle tarball, markdown transcript, or standalone HTML).",
    )
    parser.add_argument(
        "--sanitize",
        choices=["strict", "relaxed", "none"],
        default="relaxed",
        help="Data redaction level: 'strict' (all secrets + envs), 'relaxed' (standard API keys & paths), 'none'.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Path to workspace root for path anonymization and .env loading.",
    )
    return parser.parse_args(args)


def main(args: Optional[list[str]] = None) -> int:
    parsed = parse_args(args)

    conv_id = parsed.conversation_id
    if not conv_id:
        conv_id = os.environ.get("CONVERSATION_ID") or os.environ.get("AGY_CONVERSATION_ID")

    app_data_dir = parsed.app_data_dir or find_default_app_data_dir(conv_id)
    brain_dir = app_data_dir / "brain"

    if not conv_id:
        conv_id = find_latest_conversation(brain_dir)

    if not conv_id:
        print("Error: Could not determine conversation ID. Specify with --conversation-id.", file=sys.stderr)
        return 1

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    short_id = conv_id[:8]

    if parsed.output:
        out_path = parsed.output
    else:
        ext_map = {"bundle": "agy.tar.gz", "markdown": "md", "html": "html"}
        ext = ext_map.get(parsed.format, "agy.tar.gz")
        out_path = Path.cwd() / f"agy-export-{short_id}-{timestamp_str}.{ext}"

    workspace_dir = parsed.workspace or Path.cwd()

    try:
        final_path = export_session(
            conversation_id=conv_id,
            app_data_dir=app_data_dir,
            output_path=out_path,
            export_format=parsed.format,
            sanitize_level=parsed.sanitize,
            workspace_dir=workspace_dir,
        )
        print(f"Successfully exported session [{conv_id}] to: {final_path}")
        return 0
    except Exception as e:
        print(f"Export failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
