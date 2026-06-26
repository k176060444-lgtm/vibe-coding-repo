#!/usr/bin/env python3
"""tests/test_vibe_filelock.py — Unit tests for scripts/vibe_filelock.py

Covers POSIX FileLock behavior on the current Debian environment:
  T1: acquire creates parent directory and lock file
  T2: acquire sets _fd to a non-None file handle
  T3: release sets _fd back to None and closes the file handle
  T4: calling release twice does not raise
  T5: context manager (__enter__/__exit__) acquires and releases
  T6: __exit__ releases the lock even if the block raises
  T7: a second acquire on the same path with short timeout raises TimeoutError
  T8: after a successful acquire+release, a new acquire on same path works
  T9: lock_path can be passed as string (normalized to Path internally)
"""
import os
import sys

import pytest

# Add scripts dir to path so we can import the module under test
SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)

from vibe_filelock import FileLock  # noqa: E402

# Skip on non-POSIX (the POSIX branch is what we test here)
if sys.platform == "win32":
    pytest.skip("POSIX FileLock tests only run on POSIX", allow_module_level=True)


def test_acquire_creates_parent_directory_and_file(tmp_path):
    """T1: acquire creates the lock path and parent directories."""
    lock_path = tmp_path / "subdir" / "nested" / "lock.lk"
    lock = FileLock(str(lock_path), timeout=1.0)
    lock.acquire()
    try:
        assert lock_path.parent.is_dir(), "parent directory should be created"
        assert lock_path.is_file(), "lock file should exist"
    finally:
        lock.release()


def test_acquire_sets_fd(tmp_path):
    """T2: after acquire, _fd is a non-None file handle."""
    lock_path = tmp_path / "lock.lk"
    lock = FileLock(str(lock_path), timeout=1.0)
    assert lock._fd is None, "_fd should be None before acquire"
    lock.acquire()
    try:
        assert lock._fd is not None, "_fd should be set after acquire"
        assert not lock._fd.closed, "_fd should be open after acquire"
    finally:
        lock.release()


def test_release_clears_fd(tmp_path):
    """T3: release closes the file handle and sets _fd back to None."""
    lock_path = tmp_path / "lock.lk"
    lock = FileLock(str(lock_path), timeout=1.0)
    lock.acquire()
    fd = lock._fd
    assert fd is not None
    lock.release()
    assert lock._fd is None, "_fd should be None after release"
    assert fd.closed, "file handle should be closed after release"


def test_release_is_idempotent_safe(tmp_path):
    """T4: calling release twice does not raise."""
    lock_path = tmp_path / "lock.lk"
    lock = FileLock(str(lock_path), timeout=1.0)
    lock.acquire()
    lock.release()
    # Second release should be a no-op, not raise
    lock.release()
    assert lock._fd is None


def test_context_manager_acquires_and_releases(tmp_path):
    """T5: with FileLock(...) acquires on enter and releases on exit."""
    lock_path = tmp_path / "lock.lk"
    with FileLock(str(lock_path), timeout=1.0) as lock:
        assert lock._fd is not None, "should be acquired inside context"
        assert not lock._fd.closed
    # After context exit, fd should be cleared
    assert lock._fd is None, "should be released after context exit"


def test_context_manager_releases_on_exception(tmp_path):
    """T6: __exit__ releases the lock even if the block raises."""
    lock_path = tmp_path / "lock.lk"
    lock_ref = {"obj": None}

    with pytest.raises(RuntimeError, match="boom"):
        with FileLock(str(lock_path), timeout=1.0) as lock:
            lock_ref["obj"] = lock
            assert lock._fd is not None
            raise RuntimeError("boom")

    # Lock should still be released despite exception
    assert lock_ref["obj"]._fd is None, "should be released even on exception"


def test_concurrent_acquire_raises_timeout(tmp_path):
    """T7: second acquire on same path with short timeout raises TimeoutError."""
    import fcntl

    lock_path = tmp_path / "lock.lk"
    # Hold the lock with a raw file handle so the second FileLock cannot get it
    fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        second = FileLock(str(lock_path), timeout=0.3)
        with pytest.raises(TimeoutError) as excinfo:
            second.acquire()
        assert "timeout" in str(excinfo.value).lower()
        # After TimeoutError, _fd should be cleaned up
        assert second._fd is None, "_fd should be cleaned up after TimeoutError"
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_acquire_succeeds_after_release(tmp_path):
    """T8: after acquire+release, a new acquire on same path works."""
    lock_path = tmp_path / "lock.lk"

    first = FileLock(str(lock_path), timeout=1.0)
    first.acquire()
    first.release()
    assert first._fd is None

    # New instance should acquire without timing out
    second = FileLock(str(lock_path), timeout=1.0)
    second.acquire()
    try:
        assert second._fd is not None
    finally:
        second.release()


def test_lock_path_accepts_string(tmp_path):
    """T9: lock_path can be passed as a plain string, normalized to Path."""
    lock_path = str(tmp_path / "lock.lk")
    lock = FileLock(lock_path, timeout=1.0)
    lock.acquire()
    try:
        assert lock._fd is not None
        # lock_path should be normalized to Path internally
        from pathlib import Path
        assert isinstance(lock.lock_path, Path)
    finally:
        lock.release()