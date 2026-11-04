"""Trusted Windows process-launch shim.

The shim runs no Harness until its Win32 event is signalled by the Worker
AFTER assignment to a kill-on-close Job Object. Using ordinary Popen directly
creates a race where grandchildren can escape before the Job assignment.
"""
from __future__ import annotations

import ctypes
import json
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3 or sys.platform != "win32":
        return 64
    spec_file, event_name = sys.argv[1:]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenEventW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # SYNCHRONIZE only; launcher is physically incapable of signalling itself.
    handle = kernel.OpenEventW(0x00100000, False, event_name)
    if not handle:
        return 74
    try:
        outcome = kernel.WaitForSingleObject(handle, 30000)
    finally:
        kernel.CloseHandle(handle)
    if outcome != 0:  # WAIT_OBJECT_0
        return 75
    try:
        config = json.loads(Path(spec_file).read_text(encoding="utf-8"))
        argv = config["argv"]
        if not isinstance(argv, list) or not argv or not all(isinstance(v, str) for v in argv):
            raise ValueError("Approved command must be a nonempty argument list")
        # Inherit only the preconfigured stdin/stdout/stderr handles, already
        # restricted environment and cwd from the trusted parent Worker.
        with subprocess.Popen(argv, stdin=sys.stdin.buffer, stdout=sys.stdout.buffer,
                              stderr=sys.stderr.buffer, close_fds=True) as harness:
            return harness.wait()
    except Exception as ex:
        print("Windows launch shim failed: " + type(ex).__name__, file=sys.stderr)
        return 76


if __name__ == "__main__":
    sys.exit(main())
