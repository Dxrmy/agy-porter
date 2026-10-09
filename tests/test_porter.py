"""test_porter.py - Unit and integration tests for agy-porter plugin.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Add plugin root to sys.path so modules can be imported
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.bundle import Manifest, SecurityError, SessionBundle, compute_sha256
from scripts.export_bundle import export_session, main as export_main
from scripts.formatters import parse_json_lines, transcript_to_html, transcript_to_markdown
from scripts.import_bundle import fork_bundle, inspect_bundle, main as import_main
from scripts.redactor import Redactor, SanitizeLevel


class TestRedactor(unittest.TestCase):
    """Tests sensitive data detection, secrets scrubbing, and path anonymization."""

    def setUp(self):
        self.home_dir = r"C:\Users\kmric"
        self.workspace_dir = r"C:\Users\kmric\workspace\myproject"
        self.redactor = Redactor(
            level=SanitizeLevel.STRICT,
            home_dir=self.home_dir,
            workspace_dir=self.workspace_dir,
        )

    def test_gemini_key_redaction(self):
        text = "My key is AIzaSyA1234567890abcdef1234567890abcde for Vertex."
        redacted = self.redactor.redact_text(text)
        self.assertNotIn("AIzaSyA", redacted)
        self.assertIn("<REDACTED_GEMINI_KEY>", redacted)

    def test_openai_key_redaction(self):
        sample_keys = [
            "sk-1234567890abcdef1234567890abcdef",
            "sk-proj-abcde1234567890_ABCDEFGHIJ1234567890",
        ]
        for key in sample_keys:
            text = f"Using OpenAI token: {key}."
            redacted = self.redactor.redact_text(text)
            self.assertNotIn(key, redacted)
            self.assertIn("<REDACTED_OPENAI_KEY>", redacted)

    def test_github_token_redaction(self):
        gh_pat = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        fine_grained = "github_pat_11ABCD123_4567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
        text = f"GitHub: {gh_pat} and {fine_grained}"
        redacted = self.redactor.redact_text(text)
        self.assertNotIn(gh_pat, redacted)
        self.assertNotIn(fine_grained, redacted)
        self.assertIn("<REDACTED_GITHUB_TOKEN>", redacted)

    def test_bearer_token_redaction(self):
        bearer = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        text = f"Authorization: {bearer}"
        redacted = self.redactor.redact_text(text)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIs", redacted)
        self.assertIn("Bearer <REDACTED_BEARER_TOKEN>", redacted)

    def test_aws_access_key_redaction(self):
        aws_key = "AKIAIOSFODNN7EXAMPLE"
        text = f"AWS_ACCESS_KEY_ID={aws_key}"
        redacted = self.redactor.redact_text(text)
        self.assertNotIn(aws_key, redacted)
        self.assertIn("<REDACTED_AWS_ACCESS_KEY>", redacted)

    def test_private_key_redaction(self):
        key = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA0Y3b...\n"
            "-----END RSA PRIVATE KEY-----"
        )
        text = f"Here is my key:\n{key}\nKeep it safe."
        redacted = self.redactor.redact_text(text)
        self.assertNotIn("MIIEowIBAAKCAQEA0Y3b", redacted)
        self.assertIn("<REDACTED_PRIVATE_KEY>", redacted)

    def test_password_in_strict_mode(self):
        text = 'db_config = {"password": "supersecretpassword123"}'
        redacted = self.redactor.redact_text(text)
        self.assertNotIn("supersecretpassword123", redacted)
        self.assertIn("<REDACTED_SECRET>", redacted)

    def test_path_anonymization(self):
        # Workspace path
        workspace_file = r"C:\Users\kmric\workspace\myproject\src\main.py"
        redacted = self.redactor.redact_text(workspace_file)
        self.assertIn("<WORKSPACE>", redacted)
        self.assertNotIn("kmric", redacted)

        # Home path
        home_file = r"C:\Users\kmric\.gemini\antigravity-cli\settings.json"
        redacted_home = self.redactor.redact_text(home_file)
        self.assertIn("<HOME>", redacted_home)
        self.assertNotIn("kmric", redacted_home)

        # Unix style path
        unix_path = "/home/kmric/project/test.py"
        redacted_unix = self.redactor.redact_text(unix_path)
        self.assertIn("<HOME>", redacted_unix)

    def test_env_var_redaction(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".env") as f:
            f.write("SECRET_DATABASE_URL=postgres://app:myhiddenpass@db:5432/appdb\n")
            f.write("CUSTOM_API_SECRET=super_secret_enterprise_token_xyz987\n")
            f.write("DEBUG=true\n")
            dotenv_path = f.name

        try:
            self.redactor.load_env_file(dotenv_path)
            sample_text = "Connecting to super_secret_enterprise_token_xyz987 now."
            redacted = self.redactor.redact_text(sample_text)
            self.assertNotIn("super_secret_enterprise_token_xyz987", redacted)
            self.assertIn("<REDACTED_CUSTOM_API_SECRET>", redacted)
        finally:
            os.remove(dotenv_path)

    def test_sanitize_levels(self):
        text = "Key: AIzaSyA1234567890abcdef1234567890abcde, Password: secretpassword999"
        # None
        r_none = Redactor(level=SanitizeLevel.NONE)
        self.assertEqual(r_none.redact_text(text), text)

        # Relaxed (Scrubs API key, leaves generic password text)
        r_relaxed = Redactor(level=SanitizeLevel.RELAXED)
        rel_res = r_relaxed.redact_text(text)
        self.assertIn("<REDACTED_GEMINI_KEY>", rel_res)
        self.assertIn("secretpassword999", rel_res)

        # Strict (Scrubs both API key and password)
        r_strict = Redactor(level=SanitizeLevel.STRICT)
        strict_res = r_strict.redact_text(text)
        self.assertIn("<REDACTED_GEMINI_KEY>", strict_res)
        self.assertNotIn("secretpassword999", strict_res)

    def test_redact_nested_object(self):
        data = {
            "key": "AIzaSyA1234567890abcdef1234567890abcde",
            "paths": [r"C:\Users\kmric\file.txt", "normal_string"],
            "nested": {"val": "clean"},
        }
        redacted = self.redactor.redact_object(data)
        self.assertIn("<REDACTED_GEMINI_KEY>", redacted["key"])
        self.assertIn("<HOME>", redacted["paths"][0])
        self.assertEqual(redacted["nested"]["val"], "clean")


class TestBundlePackaging(unittest.TestCase):
    """Tests archive creation, manifest generation, checksums, and safe extraction."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temp_dir.name)
        self.conv_id = "test-conv-1234-abcd"

        # Setup mock brain directory
        self.brain_dir = self.test_root / "brain" / self.conv_id
        logs_dir = self.brain_dir / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True)

        transcript_content = (
            '{"step_index":0,"source":"USER_EXPLICIT","type":"USER_INPUT","content":"Hello agent!"}\n'
            '{"step_index":1,"source":"MODEL","type":"PLANNER_RESPONSE","thinking":"Thinking...","content":"Hello!"}\n'
        )
        (logs_dir / "transcript.jsonl").write_text(transcript_content, encoding="utf-8")

        # Setup mock artifact
        art_dir = self.brain_dir / "artifacts"
        art_dir.mkdir(parents=True)
        (art_dir / "design.md").write_text("# Design Doc\nContent here.", encoding="utf-8")

        # Setup mock scratch
        scratch_dir = self.brain_dir / "scratch"
        scratch_dir.mkdir(parents=True)
        (scratch_dir / "calc.py").write_text("print('hello')", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_bundle_creation_and_checksums(self):
        output_tar = self.test_root / "bundle.agy.tar.gz"
        manifest = SessionBundle.create(
            output_tar_path=output_tar,
            conversation_id=self.conv_id,
            brain_dir=self.brain_dir,
            redactor=Redactor(level=SanitizeLevel.NONE),
        )

        self.assertTrue(output_tar.is_file())
        self.assertEqual(manifest.conversation_id, self.conv_id)
        self.assertEqual(manifest.turn_count, 2)
        self.assertIn("transcript.jsonl", manifest.files)
        self.assertIn("artifacts/artifacts/design.md", manifest.files)

        # Inspect bundle
        inspect_manifest, file_list, warnings = SessionBundle.inspect(output_tar)
        self.assertEqual(inspect_manifest.conversation_id, self.conv_id)
        self.assertIn("manifest.json", file_list)
        self.assertIn("transcript.jsonl", file_list)
        # Should detect scratch/calc.py as script
        self.assertTrue(any("calc.py" in w for w in warnings))

    def test_safe_extraction_success(self):
        output_tar = self.test_root / "bundle.agy.tar.gz"
        SessionBundle.create(
            output_tar_path=output_tar,
            conversation_id=self.conv_id,
            brain_dir=self.brain_dir,
        )

        dest_dir = self.test_root / "extracted"
        # Allow scripts since calc.py is in bundle
        SessionBundle.extract_safe(output_tar, dest_dir, allow_scripts=True)

        self.assertTrue((dest_dir / "manifest.json").exists())
        self.assertTrue((dest_dir / "transcript.jsonl").exists())
        self.assertTrue((dest_dir / "artifacts" / "artifacts" / "design.md").exists())

    def test_zip_slip_traversal_prevention(self):
        """Verify that malicious archive with directory traversal attempts raises SecurityError."""
        malicious_tar = self.test_root / "evil.agy.tar.gz"

        with tarfile.open(malicious_tar, "w:gz") as tar:
            # Manifest
            m_data = b'{"schema_version":"1.0.0","files":{}}'
            t_m = tarfile.TarInfo(name="manifest.json")
            t_m.size = len(m_data)
            tar.addfile(t_m, io.BytesIO(m_data))

            # Traversal member
            payload = b"evil content"
            evil_info = tarfile.TarInfo(name="../../evil.txt")
            evil_info.size = len(payload)
            tar.addfile(evil_info, io.BytesIO(payload))

        dest_dir = self.test_root / "evil_extracted"
        with self.assertRaises(SecurityError):
            SessionBundle.extract_safe(malicious_tar, dest_dir)

    def test_absolute_path_prevention(self):
        """Verify that members with absolute paths raise SecurityError."""
        malicious_tar = self.test_root / "evil_abs.agy.tar.gz"

        with tarfile.open(malicious_tar, "w:gz") as tar:
            m_data = b'{"schema_version":"1.0.0","files":{}}'
            t_m = tarfile.TarInfo(name="manifest.json")
            t_m.size = len(m_data)
            tar.addfile(t_m, io.BytesIO(m_data))

            payload = b"evil absolute"
            evil_info = tarfile.TarInfo(name="/etc/passwd")
            evil_info.size = len(payload)
            tar.addfile(evil_info, io.BytesIO(payload))

        dest_dir = self.test_root / "evil_abs_dest"
        with self.assertRaises(SecurityError):
            SessionBundle.extract_safe(malicious_tar, dest_dir)

    def test_untrusted_scripts_blocked_without_trust(self):
        """Verify that archives with executable scripts are blocked unless allow_scripts=True."""
        script_tar = self.test_root / "script.agy.tar.gz"

        with tarfile.open(script_tar, "w:gz") as tar:
            m_data = b'{"schema_version":"1.0.0","files":{"run.sh":{"size_bytes":10}}}'
            t_m = tarfile.TarInfo(name="manifest.json")
            t_m.size = len(m_data)
            tar.addfile(t_m, io.BytesIO(m_data))

            payload = b"#!/bin/bash\necho bad"
            s_info = tarfile.TarInfo(name="run.sh")
            s_info.size = len(payload)
            tar.addfile(s_info, io.BytesIO(payload))

        dest_dir = self.test_root / "untrusted_dest"
        with self.assertRaises(SecurityError) as ctx:
            SessionBundle.extract_safe(script_tar, dest_dir, allow_scripts=False)
        self.assertIn("trust", str(ctx.exception).lower())


class TestFormatters(unittest.TestCase):
    """Tests human-readable Markdown and HTML transcript formatters."""

    def setUp(self):
        self.sample_steps = [
            {
                "step_index": 0,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "created_at": "2026-10-09T10:00:00Z",
                "content": "<USER_REQUEST>\nImplement a feature\n</USER_REQUEST>",
            },
            {
                "step_index": 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-10-09T10:00:05Z",
                "thinking": "Analyzing requirements...",
                "tool_calls": [
                    {"name": "view_file", "args": {"path": "main.py"}}
                ],
                "content": "I will examine main.py.",
            },
            {
                "step_index": 2,
                "source": "MODEL",
                "type": "GENERIC",
                "created_at": "2026-10-09T10:00:10Z",
                "content": "File Path: main.py\nprint('code')",
            },
        ]

    def test_markdown_formatter(self):
        md = transcript_to_markdown(
            self.sample_steps,
            title="Exported Session",
            conversation_id="conv-1234",
            model_name="Gemini 3.8",
        )
        self.assertIn("# Exported Session", md)
        self.assertIn("`conv-1234`", md)
        self.assertIn("Gemini 3.8", md)
        self.assertIn("👤 **User**", md)
        self.assertIn("Implement a feature", md)
        self.assertIn("💭 <i>Agent Thinking Process</i>", md)
        self.assertIn("Analyzing requirements...", md)
        self.assertIn("🔧 **Tool Call**: `view_file`", md)
        self.assertIn('"main.py"', md)

    def test_html_formatter(self):
        html_doc = transcript_to_html(
            self.sample_steps,
            title="Exported Session",
            conversation_id="conv-1234",
            model_name="Gemini 3.8",
        )
        self.assertIn("<!DOCTYPE html>", html_doc)
        self.assertIn("<title>Exported Session</title>", html_doc)
        self.assertIn("Implement a feature", html_doc)
        self.assertIn("Agent Thinking Process", html_doc)
        self.assertIn("view_file", html_doc)
        self.assertIn("badge-user", html_doc)


class TestRoundtripAndCLI(unittest.TestCase):
    """Tests end-to-end export -> import fork workflows and CLI entrypoints."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temp_dir.name)
        self.app_data_dir = self.test_root / "app_data"
        self.workspace_dir = self.test_root / "workspace"
        self.workspace_dir.mkdir(parents=True)

        self.conv_id = "orig-conv-uuid-1111"
        self.brain_dir = self.app_data_dir / "brain" / self.conv_id
        logs_dir = self.brain_dir / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True)

        self.transcript = (
            f'{{"step_index":0,"source":"USER_EXPLICIT","type":"USER_INPUT","content":"Export me {self.conv_id}"}}\n'
            f'{{"step_index":1,"source":"MODEL","type":"PLANNER_RESPONSE","content":"OK!"}}\n'
        )
        (logs_dir / "transcript.jsonl").write_text(self.transcript, encoding="utf-8")

        art_dir = self.brain_dir / "reports"
        art_dir.mkdir(parents=True)
        (art_dir / "summary.md").write_text("# Summary\nDetails here.", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_roundtrip_fork_creates_new_valid_session(self):
        bundle_path = self.test_root / "session.agy.tar.gz"

        # 1. Export
        export_session(
            conversation_id=self.conv_id,
            app_data_dir=self.app_data_dir,
            output_path=bundle_path,
            export_format="bundle",
            sanitize_level="relaxed",
            workspace_dir=self.workspace_dir,
        )
        self.assertTrue(bundle_path.is_file())

        # 2. Fork into new session
        new_conv_id, new_brain = fork_bundle(
            bundle_path=bundle_path,
            target_app_data_dir=self.app_data_dir,
            trust=True,
            dry_run=False,
            target_workspace=self.workspace_dir,
        )

        self.assertNotEqual(new_conv_id, self.conv_id)
        self.assertTrue(new_brain.is_dir())
        self.assertTrue((new_brain / ".system_generated" / "logs" / "transcript.jsonl").is_file())
        self.assertTrue((new_brain / "manifest.json").is_file())
        self.assertTrue((new_brain / "reports" / "summary.md").is_file())

        # Verify old conversation ID was replaced with new ID in transcript
        new_transcript = (new_brain / ".system_generated" / "logs" / "transcript.jsonl").read_text(encoding="utf-8")
        self.assertIn(new_conv_id, new_transcript)
        self.assertNotIn(self.conv_id, new_transcript)

    def test_export_cli_main_markdown(self):
        output_md = self.test_root / "out.md"
        args = [
            "--conversation-id", self.conv_id,
            "--app-data-dir", str(self.app_data_dir),
            "--output", str(output_md),
            "--format", "markdown",
        ]
        ret = export_main(args)
        self.assertEqual(ret, 0)
        self.assertTrue(output_md.is_file())
        content = output_md.read_text(encoding="utf-8")
        self.assertIn("Antigravity Session Transcript", content)

    def test_export_cli_main_html(self):
        output_html = self.test_root / "out.html"
        args = [
            "--conversation-id", self.conv_id,
            "--app-data-dir", str(self.app_data_dir),
            "--output", str(output_html),
            "--format", "html",
        ]
        ret = export_main(args)
        self.assertEqual(ret, 0)
        self.assertTrue(output_html.is_file())
        content = output_html.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", content)

    def test_import_cli_inspect(self):
        bundle_path = self.test_root / "inspect_test.agy.tar.gz"
        export_session(
            conversation_id=self.conv_id,
            app_data_dir=self.app_data_dir,
            output_path=bundle_path,
        )

        ret = import_main([str(bundle_path), "--mode", "inspect"])
        self.assertEqual(ret, 0)

    def test_import_cli_dry_run(self):
        bundle_path = self.test_root / "dryrun_test.agy.tar.gz"
        export_session(
            conversation_id=self.conv_id,
            app_data_dir=self.app_data_dir,
            output_path=bundle_path,
        )

        ret = import_main([
            str(bundle_path),
            "--mode", "fork",
            "--dry-run",
            "--target-app-data-dir", str(self.app_data_dir),
        ])
        self.assertEqual(ret, 0)


if __name__ == "__main__":
    unittest.main()
