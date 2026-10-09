"""bundle.py - Archive packaging, manifest generation, and safe extraction.
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if __package__ in (None, ""):
    from redactor import Redactor, SanitizeLevel
else:
    from .redactor import Redactor, SanitizeLevel


class SecurityError(Exception):
    """Raised when an archive contains unsafe paths or potential attacks."""
    pass


@dataclasses.dataclass
class Manifest:
    schema_version: str
    conversation_id: str
    exported_at: str
    turn_count: int
    model: str
    files: Dict[str, Dict[str, Any]]
    security: Dict[str, Any]
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Manifest:
        return cls(
            schema_version=data.get("schema_version", "1.0.0"),
            conversation_id=data.get("conversation_id", ""),
            exported_at=data.get("exported_at", ""),
            turn_count=data.get("turn_count", 0),
            model=data.get("model", "unknown"),
            files=data.get("files", {}),
            security=data.get("security", {}),
            metadata=data.get("metadata", {}),
        )


def compute_sha256(data: bytes) -> str:
    """Compute hex SHA-256 digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(filepath: Path) -> str:
    """Compute hex SHA-256 digest of a file on disk."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class SessionBundle:
    """Handles creating, inspecting, and safely extracting Antigravity session bundles."""

    SCHEMA_VERSION = "1.0.0"

    EXECUTABLE_EXTENSIONS = {
        ".sh", ".bash", ".bat", ".cmd", ".ps1", ".exe", ".msi", ".dll", ".so", ".dylib", ".vbs"
    }

    @staticmethod
    def parse_transcript_meta(transcript_content: str) -> Tuple[int, str]:
        """Extract turn count and last detected model from transcript lines."""
        turn_count = 0
        model_name = "unknown"

        for line in transcript_content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                turn_count += 1
                content = item.get("content", "")
                if isinstance(content, str) and "Model Selection" in content:
                    match = re_model = None
                    import re
                    match = re.search(r"Model Selection` from None to ([^.\n]+)", content)
                    if match:
                        model_name = match.group(1).strip()
            except Exception:
                continue

        return turn_count, model_name

    @classmethod
    def create(
        cls,
        output_tar_path: Path,
        conversation_id: str,
        brain_dir: Path,
        redactor: Optional[Redactor] = None,
        workspace_dir: Optional[Path] = None,
        customizations_dir: Optional[Path] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Manifest:
        """Packages transcripts, artifacts, scratch files, and manifest into a .tar.gz bundle."""
        output_tar_path = Path(output_tar_path)
        output_tar_path.parent.mkdir(parents=True, exist_ok=True)

        bundle_files: Dict[str, bytes] = {}
        contains_scripts = False
        contains_mcp = False

        # 1. Transcripts
        transcript_path = brain_dir / ".system_generated" / "logs" / "transcript.jsonl"
        if not transcript_path.exists():
            transcript_path = brain_dir / "transcript.jsonl"

        transcript_full_path = brain_dir / ".system_generated" / "logs" / "transcript_full.jsonl"
        if not transcript_full_path.exists():
            transcript_full_path = brain_dir / "transcript_full.jsonl"

        turn_count = 0
        model_name = "unknown"

        if transcript_path.exists():
            content = transcript_path.read_text(encoding="utf-8", errors="replace")
            turn_count, model_name = cls.parse_transcript_meta(content)
            if redactor:
                content = redactor.redact_text(content)
            bundle_files["transcript.jsonl"] = content.encode("utf-8")

        if transcript_full_path.exists():
            full_content = transcript_full_path.read_text(encoding="utf-8", errors="replace")
            if redactor:
                full_content = redactor.redact_text(full_content)
            bundle_files["transcript_full.jsonl"] = full_content.encode("utf-8")

        # 2. Artifacts and Scratch files in brain_dir
        for root, dirs, files in os.walk(brain_dir):
            rel_root = Path(root).relative_to(brain_dir)
            # Skip internal system logs/chunks/tasks/messages (we already extracted transcript)
            parts = rel_root.parts
            if parts and parts[0] == ".system_generated":
                continue

            for file in files:
                abs_file = Path(root) / file
                archive_rel_path = (rel_root / file).as_posix()

                ext = Path(file).suffix.lower()
                if ext in cls.EXECUTABLE_EXTENSIONS or ext == ".py":
                    contains_scripts = True

                try:
                    data = abs_file.read_bytes()
                    # Redact if text file and redactor enabled
                    if redactor and redactor.level != SanitizeLevel.NONE:
                        try:
                            text = data.decode("utf-8")
                            redacted_text = redactor.redact_text(text)
                            data = redacted_text.encode("utf-8")
                        except UnicodeDecodeError:
                            pass
                    bundle_files[f"artifacts/{archive_rel_path}"] = data
                except Exception:
                    pass

        # 3. Optional customizations
        if customizations_dir and customizations_dir.exists():
            for root, _, files in os.walk(customizations_dir):
                rel_root = Path(root).relative_to(customizations_dir)
                for file in files:
                    abs_file = Path(root) / file
                    arc_path = f"customizations/{rel_root / file}".replace("\\", "/")
                    if "mcp" in arc_path.lower():
                        contains_mcp = True
                    ext = Path(file).suffix.lower()
                    if ext in cls.EXECUTABLE_EXTENSIONS or ext == ".py":
                        contains_scripts = True
                    try:
                        bundle_files[arc_path] = abs_file.read_bytes()
                    except Exception:
                        pass

        # 4. Manifest creation
        files_manifest: Dict[str, Dict[str, Any]] = {}
        for name, data in bundle_files.items():
            files_manifest[name] = {
                "sha256": compute_sha256(data),
                "size_bytes": len(data),
            }

        manifest = Manifest(
            schema_version=cls.SCHEMA_VERSION,
            conversation_id=conversation_id,
            exported_at=datetime.now(timezone.utc).isoformat(),
            turn_count=turn_count,
            model=model_name,
            files=files_manifest,
            security={
                "contains_scripts": contains_scripts,
                "contains_mcp": contains_mcp,
                "sanitize_level": redactor.level.value if redactor else "none",
            },
            metadata=extra_metadata or {},
        )

        manifest_bytes = json.dumps(manifest.to_dict(), indent=2).encode("utf-8")

        # 5. Write tarball
        with tarfile.open(output_tar_path, "w:gz") as tar:
            # Add manifest
            m_info = tarfile.TarInfo(name="manifest.json")
            m_info.size = len(manifest_bytes)
            m_info.mtime = int(datetime.now(timezone.utc).timestamp())
            tar.addfile(m_info, io.BytesIO(manifest_bytes))

            # Add each file
            for name, data in bundle_files.items():
                t_info = tarfile.TarInfo(name=name)
                t_info.size = len(data)
                t_info.mtime = int(datetime.now(timezone.utc).timestamp())
                tar.addfile(t_info, io.BytesIO(data))

        return manifest

    @classmethod
    def inspect(cls, tar_path: Path) -> Tuple[Manifest, List[str], List[str]]:
        """Inspects an archive and returns (Manifest, file_list, security_warnings)."""
        tar_path = Path(tar_path)
        if not tar_path.is_file():
            raise FileNotFoundError(f"Bundle file not found: {tar_path}")

        file_list: List[str] = []
        warnings: List[str] = []
        manifest_data: Optional[Dict[str, Any]] = None

        with tarfile.open(tar_path, "r:*") as tar:
            for member in tar.getmembers():
                cls.validate_member_path(member.name, Path("."))
                file_list.append(member.name)
                ext = Path(member.name).suffix.lower()
                if ext in cls.EXECUTABLE_EXTENSIONS or ext == ".py":
                    warnings.append(f"Executable script detected: {member.name}")
                if "mcp" in member.name.lower():
                    warnings.append(f"MCP configuration detected: {member.name}")

                if member.name == "manifest.json":
                    f = tar.extractfile(member)
                    if f:
                        manifest_data = json.load(f)

        if not manifest_data:
            manifest = Manifest(
                schema_version="unknown",
                conversation_id="unknown",
                exported_at="unknown",
                turn_count=0,
                model="unknown",
                files={},
                security={"contains_scripts": bool(warnings), "contains_mcp": False},
            )
        else:
            manifest = Manifest.from_dict(manifest_data)

        return manifest, file_list, warnings

    @classmethod
    def validate_member_path(cls, member_name: str, target_dir: Path) -> Path:
        """Validates that a tar member does not perform path traversal (Zip-Slip).

        Raises SecurityError if member attempts to escape target_dir.
        """
        # Block absolute paths or drive letters
        if (
            member_name.startswith("/")
            or member_name.startswith("\\")
            or (len(member_name) > 1 and member_name[1] == ":")
        ):
            raise SecurityError(
                f"Absolute paths are forbidden in archive: {member_name}"
            )

        # Normalize and resolve destination
        target_resolved = target_dir.resolve()
        destination = (target_dir / member_name).resolve()

        try:
            destination.relative_to(target_resolved)
        except ValueError:
            raise SecurityError(
                f"Path traversal detected in archive member: {member_name}"
            )

        # Explicit check for .. components
        normalized_parts = Path(member_name).parts
        if ".." in normalized_parts:
            raise SecurityError(
                f"Path traversal ('..') detected in member name: {member_name}"
            )

        return destination

    @classmethod
    def extract_safe(
        cls,
        tar_path: Path,
        target_dir: Path,
        allow_scripts: bool = False,
    ) -> Manifest:
        """Safely extracts a bundle into target_dir with path validation and integrity checks."""
        tar_path = Path(tar_path)
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        manifest, _, warnings = cls.inspect(tar_path)

        if warnings and not allow_scripts:
            # Check if there are scripts
            script_warnings = [w for w in warnings if "Executable script" in w]
            if script_warnings:
                raise SecurityError(
                    f"Archive contains executable scripts but --trust was not provided: {script_warnings[0]}"
                )

        with tarfile.open(tar_path, "r:*") as tar:
            for member in tar.getmembers():
                dest = cls.validate_member_path(member.name, target_dir)

                if member.isdir():
                    dest.mkdir(parents=True, exist_ok=True)
                elif member.isreg():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    f = tar.extractfile(member)
                    if f:
                        data = f.read()
                        # Checksum verification against manifest
                        if member.name in manifest.files:
                            expected_sha = manifest.files[member.name].get("sha256")
                            if expected_sha and compute_sha256(data) != expected_sha:
                                raise SecurityError(
                                    f"Checksum mismatch for member {member.name}"
                                )
                        dest.write_bytes(data)
                elif member.issym() or member.islnk():
                    raise SecurityError(f"Symlinks/hardlinks not permitted in bundle: {member.name}")

        return manifest
