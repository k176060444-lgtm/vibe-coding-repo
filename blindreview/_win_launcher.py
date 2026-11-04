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
    if len(sys.argv) != 4 or sys.platform != "win32":
        return 64
    spec_file, event_name, parent_pid_text = sys.argv[1:]
    try:
        parent_pid = int(parent_pid_text)
        if parent_pid <= 0:
            return 64
    except ValueError:
        return 64
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenEventW.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForMultipleObjects.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
                                              wintypes.BOOL, wintypes.DWORD]
    kernel.WaitForMultipleObjects.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # SYNCHRONIZE only; launcher cannot signal the event or control its parent.
    gate = kernel.OpenEventW(0x00100000, False, event_name)
    if not gate:
        return 74
    parent = kernel.OpenProcess(0x00100000, False, parent_pid)
    if not parent:
        kernel.CloseHandle(gate)
        return 75  # Worker exited before the launcher could be assigned.
    try:
        handles = (wintypes.HANDLE * 2)(gate, parent)
        # The Worker signals gate only after Job assignment. If it dies first,
        # its process handle becomes signalled and this launcher exits promptly.
        outcome = kernel.WaitForMultipleObjects(2, handles, False, 30000)
    finally:
        kernel.CloseHandle(parent)
        kernel.CloseHandle(gate)
    if outcome == 1:  # WAIT_OBJECT_0 + 1: Worker exited before gate release.
        return 75
    if outcome != 0:  # WAIT_OBJECT_0: gate released; timeout/WAIT_FAILED otherwise.
        return 76
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
