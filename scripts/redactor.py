"""redactor.py - Sensitive data and environment scrubbing for session bundles.
"""

from __future__ import annotations

import enum
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class SanitizeLevel(str, enum.Enum):
    NONE = "none"
    RELAXED = "relaxed"
    STRICT = "strict"


class Redactor:
    """Detects and redacts secrets, credentials, environment variables,

    and user-identifying filesystem paths.
    """

    # Common API keys and credential patterns
    PATTERNS: List[Tuple[str, re.Pattern, str]] = [
        # Google / Gemini API Keys (AIza...)
        ("gemini_key", re.compile(r"\bAIza[0-9A-Za-z\-_]{30,45}\b"), "<REDACTED_GEMINI_KEY>"),
        # OpenAI API Keys
        (
            "openai_key",
            re.compile(r"\bsk-(?:proj-|org-)?[a-zA-Z0-9\-_]{20,}\b"),
            "<REDACTED_OPENAI_KEY>",
        ),
        # GitHub Personal Access Tokens (Classic and Fine-grained)
        (
            "github_token",
            re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,50}|github_pat_[A-Za-z0-9_]{50,100})\b"),
            "<REDACTED_GITHUB_TOKEN>",
        ),
        # AWS Access Key IDs
        (
            "aws_access_key",
            re.compile(r"(?<![A-Z0-9])(AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])"),
            "<REDACTED_AWS_ACCESS_KEY>",
        ),
        # Slack Tokens
        (
            "slack_token",
            re.compile(r"\bxox[baprs]-[0-9a-zA-Z]{10,48}\b"),
            "<REDACTED_SLACK_TOKEN>",
        ),
        # Bearer Authorization Tokens
        (
            "bearer_token",
            re.compile(r"\bBearer\s+([A-Za-z0-9\-\._~+/]{20,}={0,2})", re.IGNORECASE),
            "Bearer <REDACTED_BEARER_TOKEN>",
        ),
        # Private Keys (RSA, OpenSSH, EC, generic)
        (
            "private_key",
            re.compile(
                r"-----BEGIN [A-Z0-9_\- ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z0-9_\- ]*PRIVATE KEY-----"
            ),
            "<REDACTED_PRIVATE_KEY>",
        ),
    ]

    # Strict-only patterns (passwords, secrets, connection strings)
    STRICT_PATTERNS: List[Tuple[str, re.Pattern, str]] = [
        (
            "password_assignment",
            re.compile(
                r"""(?i)(['"]?(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)['"]?\s*[:=]\s*['"]?)([^\s'",;&]{4,})(['"]?)"""
            ),
            r"\1<REDACTED_SECRET>\3",
        ),
        # Database connection strings with credentials (postgres://user:pass@host)
        (
            "db_connection",
            re.compile(r"(?i)\b([a-z]+://[^:\s]+:)([^@\s]+)(@[^/\s]+)"),
            r"\1<REDACTED_PASSWORD>\3",
        ),
    ]

    # Values that should never be redacted even if found in env
    TRIVIAL_ENV_VALUES: Set[str] = {
        "true", "false", "yes", "no", "1", "0", "none", "null", "undefined",
        "development", "production", "test", "staging", "utf-8", "utf8",
        "localhost", "127.0.0.1", "0.0.0.0", "amd64", "x86_64", "arm64",
        "windows", "linux", "darwin", "c:", "c:\\", "/", "/home", "/root",
    }

    def __init__(
        self,
        level: SanitizeLevel | str = SanitizeLevel.RELAXED,
        home_dir: Optional[str | Path] = None,
        workspace_dir: Optional[str | Path] = None,
        env_vars: Optional[Dict[str, str]] = None,
    ):
        if isinstance(level, str):
            self.level = SanitizeLevel(level.lower())
        else:
            self.level = level

        self.home_dir = str(home_dir or Path.home()).rstrip(r"\/")
        self.workspace_dir = str(workspace_dir).rstrip(r"\/") if workspace_dir else None
        self.env_vars: Dict[str, str] = {}

        if env_vars:
            self.add_env_vars(env_vars)

        self._build_path_replacers()

    def add_env_vars(self, env_dict: Dict[str, str]) -> None:
        """Add environment variables to scrub, ignoring trivial values."""
        for key, val in env_dict.items():
            val_str = str(val).strip()
            if len(val_str) < 5 or val_str.lower() in self.TRIVIAL_ENV_VALUES:
                continue
            # Ignore variables that look like standard paths unless explicitly secrets
            if key in {"PATH", "PSMODULEPATH", "PATHEXT", "TEMP", "TMP", "SYSTEMROOT", "COMSPEC"}:
                continue
            self.env_vars[key] = val_str

    def load_env_file(self, filepath: str | Path) -> None:
        """Parse a .env formatted file and add variables for scrubbing."""
        path = Path(filepath)
        if not path.is_file():
            return

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and v:
                            self.add_env_vars({k: v})
        except Exception:
            pass

    def _build_path_replacers(self) -> None:
        """Prepare patterns for path anonymization across Windows and Unix forms."""
        self.path_replacements: List[Tuple[re.Pattern, str]] = []

        # Workspace first (more specific than home if workspace is under home)
        if self.workspace_dir:
            self._add_dir_patterns(self.workspace_dir, "<WORKSPACE>")

        # Home directory
        if self.home_dir:
            self._add_dir_patterns(self.home_dir, "<HOME>")

        # Generic Windows user home directories (e.g. C:\Users\alice -> <HOME>)
        self.path_replacements.append((
            re.compile(r"""(?:[A-Za-z]:)?(?:\\\\|/|\\)Users(?:\\\\|/|\\)([A-Za-z0-9._-]+)""", re.IGNORECASE),
            "<HOME>",
        ))
        # Generic Unix user home directories (e.g. /home/alice or /Users/alice -> <HOME>)
        self.path_replacements.append((
            re.compile(r"""/(?:home|Users)/([A-Za-z0-9._-]+)"""),
            "<HOME>",
        ))

    def _add_dir_patterns(self, target_dir: str, replacement: str) -> None:
        """Add variants of a directory path (forward/backward slashes, escaped backslashes)."""
        clean = target_dir.replace("\\", "/")
        parts = [re.escape(p) for p in clean.split("/") if p]
        if not parts:
            return

        # Handle drive letter if on Windows (e.g. C:)
        if parts[0].endswith(":"):
            drive = parts[0]
            rest = parts[1:]
            # Pattern matching C:\path or C:\\path or C:/path with case insensitivity
            sep_pattern = r"(?:\\\\|/|\\)"
            pattern_str = rf"(?i)\b{drive}{sep_pattern}{sep_pattern.join(rest)}"
        else:
            sep_pattern = r"(?:\\\\|/|\\)"
            pattern_str = rf"(?:^|(?<=[\s\'\"`=:])){sep_pattern}?{sep_pattern.join(parts)}"

        try:
            self.path_replacements.append((re.compile(pattern_str), replacement))
        except re.error:
            pass

    def redact_text(self, text: str) -> str:
        """Redact sensitive information from a text string based on sanitize level."""
        if self.level == SanitizeLevel.NONE or not text:
            return text

        result = text

        # 1. Path anonymization (both relaxed and strict)
        for pattern, repl in self.path_replacements:
            result = pattern.sub(repl, result)

        # 2. Base secrets and API keys
        for _, pattern, repl in self.PATTERNS:
            result = pattern.sub(repl, result)

        # 3. Environment variable values (if loaded)
        for env_name, env_val in self.env_vars.items():
            if env_val in result:
                result = result.replace(env_val, f"<REDACTED_{env_name}>")

        # 4. Strict patterns
        if self.level == SanitizeLevel.STRICT:
            for _, pattern, repl in self.STRICT_PATTERNS:
                result = pattern.sub(repl, result)

        return result

    def redact_object(self, obj: Any) -> Any:
        """Recursively redact text in dictionaries, lists, or primitive values."""
        if self.level == SanitizeLevel.NONE:
            return obj

        if isinstance(obj, str):
            return self.redact_text(obj)
        elif isinstance(obj, dict):
            return {
                (self.redact_text(k) if isinstance(k, str) else k): self.redact_object(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [self.redact_object(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(self.redact_object(item) for item in obj)
        return obj
