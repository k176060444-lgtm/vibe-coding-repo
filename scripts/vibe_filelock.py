#!/usr/bin/env python3
"""vibe_filelock.py — Cross-platform file locking for ClaimStore.

POSIX: fcntl.flock (per-fd advisory lock)
Windows: msvcrt.locking (per-fd byte-range lock)

Both provide:
  - Exclusive lock acquisition with timeout
  - Context manager support
  - Atomic lock/unlock semantics
  - Same timeout behavior
"""

__version__ = "1.0.0"

import os
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    import msvcrt

    class FileLock:
        """Windows file lock using msvcrt.locking."""

        def __init__(self, lock_path: str, timeout: float = 10.0):
            self.lock_path = Path(lock_path)
            self.timeout = timeout
            self._fd = None

        def acquire(self):
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._fd = open(str(self.lock_path), "wb")
            deadline = time.monotonic() + self.timeout
            while True:
                try:
                    msvcrt.locking(self._fd.fileno(), msvcrt.LK_NBLCK, 1)
                    return
                except (IOError, OSError):
                    if time.monotonic() > deadline:
                        self._fd.close()
                        self._fd = None
                        raise TimeoutError(
                            "FileLock timeout after %.1fs on %s"
                            % (self.timeout, self.lock_path)
                        )
                    time.sleep(0.05)

        def release(self):
            if self._fd:
                try:
                    msvcrt.locking(self._fd.fileno(), msvcrt.LK_UNLCK, 1)
                    self._fd.close()
                except Exception:
                    try:
                        self._fd.close()
                    except Exception:
                        pass
                finally:
                    self._fd = None

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, *exc):
            self.release()
            return False

else:
    import fcntl

    class FileLock:
        """POSIX file lock using fcntl.flock."""

        def __init__(self, lock_path: str, timeout: float = 10.0):
            self.lock_path = Path(lock_path)
            self.timeout = timeout
            self._fd = None

        def acquire(self):
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._fd = open(str(self.lock_path), "w")
            deadline = time.monotonic() + self.timeout
            while True:
                try:
                    fcntl.flock(self._fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return
                except (IOError, OSError):
                    if time.monotonic() > deadline:
                        self._fd.close()
                        self._fd = None
                        raise TimeoutError(
                            "FileLock timeout after %.1fs on %s"
                            % (self.timeout, self.lock_path)
                        )
                    time.sleep(0.05)

        def release(self):
            if self._fd:
                try:
                    fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
                    self._fd.close()
                except Exception:
                    try:
                        self._fd.close()
                    except Exception:
                        pass
                finally:
                    self._fd = None

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, *exc):
            self.release()
            return False
