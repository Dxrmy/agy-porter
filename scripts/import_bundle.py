"""import_bundle.py - Import and fork Antigravity CLI session bundles.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from bundle import Manifest, SecurityError, SessionBundle
else:
    from .bundle import Manifest, SecurityError, SessionBundle


def inspect_bundle(bundle_path: Path) -> Tuple[Manifest, List[str], List[str]]:
    """Inspects bundle manifest and contents without extracting."""
    return SessionBundle.inspect(bundle_path)


def print_inspection_report(manifest: Manifest, files: List[str], warnings: List[str]) -> None:
    """Print human-readable inspection summary."""
    print("=" * 60)
    print(" ANTIGRAVITY SESSION BUNDLE INSPECTION")
    print("=" * 60)
    print(f"Schema Version   : {manifest.schema_version}")
    print(f"Conversation ID  : {manifest.conversation_id}")
    print(f"Exported At      : {manifest.exported_at}")
    print(f"Turn Count       : {manifest.turn_count}")
    print(f"Model            : {manifest.model}")
    print(f"Sanitize Level   : {manifest.security.get('sanitize_level', 'unknown')}")
    print(f"Total Files      : {len(files)}")
    print("-" * 60)
    print("Files Included:")
    for f in sorted(files):
        size = manifest.files.get(f, {}).get("size_bytes", 0)
        print(f"  * {f:<40} ({size:,} bytes)")
    print("-" * 60)

    if warnings:
        print("[!] SECURITY WARNINGS:")
        for w in warnings:
            print(f"  ! {w}")
        print("\nNote: Use --trust when importing to allow executable scripts or MCP tools.")
    else:
        print("[OK] Security Check: No suspicious scripts or MCP configurations found.")
    print("=" * 60)


def fork_bundle(
    bundle_path: Path,
    target_app_data_dir: Path,
    trust: bool = False,
    dry_run: bool = False,
    target_workspace: Optional[Path] = None,
) -> Tuple[str, Path]:
    """Forks a session bundle into a new conversation ID in target_app_data_dir."""
    manifest, files, warnings = inspect_bundle(bundle_path)

    has_scripts = any("Executable script" in w or "MCP" in w for w in warnings)
    if has_scripts and not trust:
        raise SecurityError(
            "Bundle contains executable scripts or MCP configurations. "
            "Re-run with --trust if you trust this bundle's source."
        )

    new_conv_id = str(uuid.uuid4())
    dest_brain_dir = target_app_data_dir / "brain" / new_conv_id

    if dry_run:
        print(f"[DRY-RUN] Would create new conversation: {new_conv_id}")
        print(f"[DRY-RUN] Destination: {dest_brain_dir}")
        print(f"[DRY-RUN] Unpacking {len(files)} files...")
        return new_conv_id, dest_brain_dir

    # Safely extract into a temporary directory first
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        SessionBundle.extract_safe(bundle_path, temp_dir, allow_scripts=trust)

        # Create destination structure
        dest_brain_dir.mkdir(parents=True, exist_ok=True)
        logs_dir = dest_brain_dir / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        old_conv_id = manifest.conversation_id

        # Move and update files
        for root, _, extracted_files in os.walk(temp_dir):
            rel_root = Path(root).relative_to(temp_dir)
            for f in extracted_files:
                src_file = Path(root) / f
                arc_path = (rel_root / f).as_posix()

                if arc_path == "manifest.json":
                    # Update manifest with new conversation ID
                    data = json.loads(src_file.read_text(encoding="utf-8"))
                    data["conversation_id"] = new_conv_id
                    data["forked_from"] = old_conv_id
                    dest_file = dest_brain_dir / "manifest.json"
                    dest_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                elif arc_path in ("transcript.jsonl", "transcript_full.jsonl"):
                    text = src_file.read_text(encoding="utf-8", errors="replace")
                    if old_conv_id:
                        text = text.replace(old_conv_id, new_conv_id)
                    # Place in .system_generated/logs/
                    (logs_dir / f).write_text(text, encoding="utf-8")
                    # Also write to root for convenient direct access
                    (dest_brain_dir / f).write_text(text, encoding="utf-8")
                elif arc_path.startswith("artifacts/"):
                    sub_path = arc_path[len("artifacts/"):]
                    target_art = dest_brain_dir / sub_path
                    target_art.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, target_art)
                elif arc_path.startswith("customizations/") and target_workspace:
                    sub_path = arc_path[len("customizations/"):]
                    custom_dest = target_workspace / ".agents" / sub_path
                    custom_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, custom_dest)

    return new_conv_id, dest_brain_dir


def extract_customizations_only(
    bundle_path: Path,
    target_workspace: Path,
    trust: bool = False,
    dry_run: bool = False,
) -> int:
    """Extracts only customizations into target_workspace/.agents/."""
    manifest, files, warnings = inspect_bundle(bundle_path)
    custom_files = [f for f in files if f.startswith("customizations/")]

    if not custom_files:
        print("No customizations found in bundle.")
        return 0

    has_scripts = any("Executable script" in w or "MCP" in w for w in warnings)
    if has_scripts and not trust:
        raise SecurityError(
            "Customizations contain executable scripts/MCP configurations. "
            "Re-run with --trust to import."
        )

    if dry_run:
        print(f"[DRY-RUN] Would extract {len(custom_files)} customizations into {target_workspace / '.agents'}")
        return 0

    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        SessionBundle.extract_safe(bundle_path, temp_dir, allow_scripts=trust)

        for cf in custom_files:
            src = temp_dir / cf
            rel_sub = cf[len("customizations/"):]
            dest = target_workspace / ".agents" / rel_sub
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            print(f"Extracted customization: {rel_sub}")

    return len(custom_files)


def parse_args(args: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="import_bundle",
        description="Import, fork, inspect, or review Antigravity CLI session bundles.",
    )
    parser.add_argument(
        "bundle_file",
        type=Path,
        help="Path to the .agy.tar.gz or bundle file to import.",
    )
    parser.add_argument(
        "--mode",
        choices=["fork", "inspect", "review", "customizations-only"],
        default="fork",
        help="Import mode: 'fork' (create new session), 'inspect'/'review' (view summary & security), 'customizations-only'.",
    )
    parser.add_argument(
        "--target-app-data-dir",
        type=Path,
        default=None,
        help="Path to Antigravity CLI app data directory (default: ~/.gemini/antigravity-cli).",
    )
    parser.add_argument(
        "--target-workspace",
        type=Path,
        default=None,
        help="Target workspace root for customizations or context.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate import without modifying files.",
    )
    parser.add_argument(
        "--trust",
        action="store_true",
        help="Acknowledge and allow importing bundles containing executable scripts or MCP definitions.",
    )
    return parser.parse_args(args)


def main(args: Optional[list[str]] = None) -> int:
    parsed = parse_args(args)

    bundle_path = parsed.bundle_file
    if not bundle_path.is_file():
        print(f"Error: Bundle file not found: {bundle_path}", file=sys.stderr)
        return 1

    app_data_dir = parsed.target_app_data_dir
    if not app_data_dir:
        candidates = [
            Path.home() / ".gemini" / "antigravity",
            Path.home() / ".gemini" / "antigravity-cli",
        ]
        app_data_dir = next((c for c in candidates if c.is_dir()), candidates[0])
    target_workspace = parsed.target_workspace or Path.cwd()

    try:
        if parsed.mode in ("inspect", "review"):
            manifest, files, warnings = inspect_bundle(bundle_path)
            print_inspection_report(manifest, files, warnings)
            return 0

        elif parsed.mode == "customizations-only":
            count = extract_customizations_only(
                bundle_path=bundle_path,
                target_workspace=target_workspace,
                trust=parsed.trust,
                dry_run=parsed.dry_run,
            )
            print(f"Successfully processed {count} customizations.")
            return 0

        elif parsed.mode == "fork":
            new_id, dest_dir = fork_bundle(
                bundle_path=bundle_path,
                target_app_data_dir=app_data_dir,
                trust=parsed.trust,
                dry_run=parsed.dry_run,
                target_workspace=target_workspace,
            )
            print(f"Successfully forked session!")
            print(f"  New Conversation ID : {new_id}")
            print(f"  Destination Path    : {dest_dir}")
            print("\nYou can now open or resume this session with:")
            print(f"  agy --conversation-id {new_id}")
            return 0

    except SecurityError as se:
        print(f"Security Alert: {se}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Import error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
