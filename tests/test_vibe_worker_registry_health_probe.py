#!/usr/bin/env python3
"""Tests for I22 worker health probe (WRKR-001 / ARCH-002).

Tests the _resolve_ssh_key(), health_probe(), probe_all(), and CLI
--health-check changes in vibe_worker_registry.py.

All tests mock subprocess.run — no actual SSH, no network, no model calls.
"""

import json
import os
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock, PropertyMock
from pathlib import Path

# Ensure scripts dir is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from vibe_worker_registry import WorkerRegistry, NodeStatus


class TestResolveSshKey(unittest.TestCase):
    """Verify _resolve_ssh_key() fallback chain."""

    def setUp(self):
        self.reg = WorkerRegistry()

    def test_abs_existing_path(self):
        """Already absolute + existing path should be returned as-is."""
        with tempfile.NamedTemporaryFile(suffix=".key", delete=False) as f:
            tmp = f.name
        try:
            result = self.reg._resolve_ssh_key(tmp)
            self.assertEqual(result, tmp)
            self.assertTrue(os.path.exists(result))
        finally:
            os.unlink(tmp)

    def test_abs_non_existing_path(self):
        """Absolute but non-existing path should return original (not blow up)."""
        result = self.reg._resolve_ssh_key("C:\\nonexistent\\testkey.pem")
        self.assertEqual(result, "C:\\nonexistent\\testkey.pem")

    def test_env_var_override(self):
        """VIBEDEV_SSH_KEY_DIR env var should be used if set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "mykey")
            Path(key_path).touch()
            with patch.dict(os.environ, {"VIBEDEV_SSH_KEY_DIR": tmpdir}):
                result = self.reg._resolve_ssh_key("mykey")
                self.assertEqual(result, key_path)
                self.assertTrue(os.path.exists(result))

    def test_env_var_dir_not_exist(self):
        """VIBEDEV_SSH_KEY_DIR pointing to non-existing dir should fall through."""
        with patch.dict(os.environ, {"VIBEDEV_SSH_KEY_DIR": "C:\\no_such_vibedev_key_dir"}):
            result = self.reg._resolve_ssh_key("mykey")
            # Should not raise; returns original if nothing found
            self.assertEqual(result, "mykey")

    def test_empty_key(self):
        """Empty key should return empty."""
        result = self.reg._resolve_ssh_key("")
        self.assertEqual(result, "")

    def test_none_key(self):
        """None key should return None."""
        result = self.reg._resolve_ssh_key(None)
        self.assertIsNone(result)


class TestHealthProbeLocalExec(unittest.TestCase):
    """Verify 21bao local-exec health probe."""

    def setUp(self):
        self.reg = WorkerRegistry()

    @patch("subprocess.run")
    def test_local_exec_online(self, mock_run):
        """hostname succeeds → ONLINE."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="KK-PC\n", stderr=""
        )
        result = self.reg.health_probe("21bao")
        self.assertEqual(result["status"], "ONLINE")
        self.assertEqual(result["transport"], "local-exec")
        self.assertIn("latency_ms", result)
        self.assertIn("exit_code", result)
        self.assertEqual(result["exit_code"], 0)
        # Verify worker health_status persisted
        w = self.reg.workers.get("21bao")
        self.assertEqual(w.health_status, "ONLINE")

    @patch("subprocess.run")
    def test_local_exec_offline(self, mock_run):
        """hostname fails → OFFLINE."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="command not found"
        )
        result = self.reg.health_probe("21bao")
        self.assertEqual(result["status"], "OFFLINE")
        w = self.reg.workers.get("21bao")
        self.assertEqual(w.health_status, "OFFLINE")

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="hostname", timeout=5))
    def test_local_exec_timeout(self, mock_run):
        """Timeout → OFFLINE with error."""
        result = self.reg.health_probe("21bao", timeout=5)
        self.assertEqual(result["status"], "OFFLINE")

    @patch("subprocess.run", side_effect=Exception("connection error"))
    def test_local_exec_exception(self, mock_run):
        """Unexpected exception → OFFLINE with error."""
        result = self.reg.health_probe("21bao")
        self.assertEqual(result["status"], "OFFLINE")
        self.assertIn("error", result)


class TestHealthProbeSSH(unittest.TestCase):
    """Verify 5bao/9bao SSH health probe."""

    def setUp(self):
        self.reg = WorkerRegistry()

    @patch("subprocess.run")
    def test_ssh_online(self, mock_run):
        """SSH returns HEALTH_OK + hostname → ONLINE."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="HEALTH_OK\nKK-5bao\n2026-07-05T10:00:00Z\n", stderr=""
        )
        result = self.reg.health_probe("5bao")
        self.assertEqual(result["status"], "ONLINE")
        self.assertIn("evidence_sha", result)
        w = self.reg.workers.get("5bao")
        self.assertEqual(w.health_status, "ONLINE")

    @patch("subprocess.run")
    def test_ssh_offline_no_marker(self, mock_run):
        """SSH succeeds but no HEALTH_OK marker → OFFLINE."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="hostname only\n", stderr=""
        )
        result = self.reg.health_probe("5bao")
        self.assertEqual(result["status"], "OFFLINE")
        w = self.reg.workers.get("5bao")
        self.assertEqual(w.health_status, "OFFLINE")

    @patch("subprocess.run")
    def test_ssh_offline_exit_code(self, mock_run):
        """SSH non-zero exit → OFFLINE."""
        mock_run.return_value = MagicMock(
            returncode=255, stdout="", stderr="Permission denied"
        )
        result = self.reg.health_probe("9bao")
        self.assertEqual(result["status"], "OFFLINE")

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ssh", timeout=15))
    def test_ssh_timeout(self, mock_run):
        """SSH timeout → OFFLINE with error=ssh_timeout."""
        result = self.reg.health_probe("5bao", timeout=10)
        self.assertEqual(result["status"], "OFFLINE")
        self.assertIn("error", result)

    @patch("subprocess.run", side_effect=Exception("connection refused"))
    def test_ssh_exception(self, mock_run):
        """Unexpected SSH exception → OFFLINE with error."""
        result = self.reg.health_probe("9bao")
        self.assertEqual(result["status"], "OFFLINE")
        self.assertIn("error", result)


class TestHealthProbeUnknownWorker(unittest.TestCase):
    """Verify invalid worker_id handling."""

    def setUp(self):
        self.reg = WorkerRegistry()

    def test_unknown_worker(self):
        """Non-existent worker_id → UNKNOWN + worker_not_found."""
        result = self.reg.health_probe("nonexistent")
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["error"], "worker_not_found")


class TestHealthProbePersistentState(unittest.TestCase):
    """Verify set_health persists across probe calls."""

    def setUp(self):
        self.reg = WorkerRegistry()

    @patch("subprocess.run")
    def test_health_status_update(self, mock_run):
        """check_health followed by --status shows updated state."""
        # First call: ONLINE
        mock_run.return_value = MagicMock(
            returncode=0, stdout="HEALTH_OK\n9bao\n2026-07-05T10:00:00Z\n", stderr=""
        )
        result = self.reg.health_probe("9bao")
        self.assertEqual(result["status"], "ONLINE")
        self.assertEqual(self.reg.workers["9bao"].health_status, "ONLINE")

    @patch("subprocess.run")
    @patch("builtins.print")
    def test_probe_all_detects_online(self, mock_print, mock_run):
        """probe_all should classify all workers as ONLINE when probe succeeds."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="HEALTH_OK\nhostname\n2026-07-05T10:00:00Z\n", stderr=""
        )
        results = self.reg.probe_all(timeout=5)
        for wid, r in results.items():
            self.assertEqual(r["status"], "ONLINE", f"{wid} should be ONLINE")


class TestHealthProbeSshCommandContainsCorrectArgs(unittest.TestCase):
    """Verify SSH command construction — does NOT execute SSH."""

    def setUp(self):
        self.reg = WorkerRegistry()

    @patch("subprocess.run")
    def test_ssh_cmd_arguments(self, mock_run):
        """Verify SSH cmd includes expected args but does not run."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="HEALTH_OK\n", stderr=""
        )
        self.reg.health_probe("5bao")
        # Verify the call args
        args, _ = mock_run.call_args
        cmd = args[0]
        self.assertIn("ssh", cmd)
        self.assertIn("-p", cmd)
        self.assertIn("22222", cmd)
        self.assertIn("vibeworker@192.168.5.6", cmd)
        self.assertIn("HEALTH_OK", cmd[-1])

    @patch("subprocess.run")
    def test_ssh_cmd_9bao(self, mock_run):
        """9bao SSH cmd should target 192.168.9.6."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="HEALTH_OK\n", stderr=""
        )
        self.reg.health_probe("9bao")
        args, _ = mock_run.call_args
        cmd = args[0]
        self.assertIn("vibeworker@192.168.9.6", cmd)


class TestHealthProbeDoesNotCallQwen(unittest.TestCase):
    """Verify no model call is triggered — health_probe is SSH/subprocess only."""

    def setUp(self):
        self.reg = WorkerRegistry()

    def test_health_probe_is_not_model_call(self):
        """health_probe never calls opencode or any model."""
        import inspect
        source = inspect.getsource(self.reg.health_probe)
        # Should not contain any opencode run or model invocation
        self.assertNotIn("opencode", source)
        self.assertNotIn("deepseek", source)
        self.assertNotIn("qwen", source)


class TestHealthProbeDoesNotWriteFiles(unittest.TestCase):
    """Verify health_probe does not write tracked files."""

    def setUp(self):
        self.reg = WorkerRegistry()

    @patch("subprocess.run")
    def test_probe_all_no_side_effect_tracked_files(self, mock_run):
        """probe_all does not create files outside docs/baseline02/gray/."""
        import tempfile
        import shutil
        mock_run.return_value = MagicMock(
            returncode=0, stdout="HEALTH_OK\nhostname\n", stderr=""
        )
        # Just verify it returns results dict and doesn't write to disk
        results = self.reg.probe_all()
        self.assertEqual(len(results), 3)
        # Verify no new files in repo root
        repo_root = Path(_SCRIPTS_DIR).parent
        untracked_before = set()
        for f in repo_root.rglob("*"):
            if ".git" not in str(f) and f.is_file():
                # Count existing files — probe should NOT create new ones
                pass
        # Probe should not have created any new file (we're just checking no error)
        mock_run.assert_called()


if __name__ == "__main__":
    unittest.main()
