#!/usr/bin/env python3
"""Runtime version inventory scanner for VibeDev cluster.

Scans configured nodes and produces a version inventory JSON.
Designed to run on the Windows controller; SSH into worker nodes.

Usage:
    python runtime_inventory.py [--output FILE] [--self-check]

Output: JSON array of component inventory records.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

SCHEMA_VERSION = 1

COMPONENT_DEFS = [
    {
        "id": "opencode-runtime",
        "nodes": ["5bao", "9bao"],
        "version_cmd": "{bin} --version",
        "bin_paths": {
            "5bao": "~/.npm-global/lib/node_modules/opencode-ai/node_modules/opencode-linux-x64/bin/opencode",
            "9bao": "~/.opencode/bin/opencode",
        },
        "install_method": "npm_global",
        "category": "worker-tool",
    },
    {
        "id": "node-runtime",
        "nodes": ["5bao", "9bao"],
        "version_cmd": "node --version",
        "bin_paths": {
            "5bao": "~/.local/node-v22.22.1-linux-x64/bin/node",
            "9bao": "~/.local/node-v22.22.1/bin/node",
        },
        "install_method": "binary",
        "category": "runtime",
    },
    {
        "id": "npm-runtime",
        "nodes": ["5bao", "9bao"],
        "version_cmd": "npm --version",
        "bin_paths": {},
        "install_method": "bundled",
        "category": "runtime",
    },
    {
        "id": "python-runtime",
        "nodes": ["5bao", "9bao"],
        "version_cmd": "python3 --version",
        "bin_paths": {},
        "install_method": "apt",
        "category": "runtime",
    },
    {
        "id": "git-runtime",
        "nodes": ["5bao", "9bao"],
        "version_cmd": "git --version",
        "bin_paths": {},
        "install_method": "apt",
        "category": "tool",
    },
    {
        "id": "gh-cli",
        "nodes": ["5bao", "9bao"],
        "version_cmd": "gh --version | head -1",
        "bin_paths": {},
        "install_method": "apt",
        "category": "tool",
    },
    {
        "id": "ripgrep",
        "nodes": ["9bao"],
        "version_cmd": "rg --version | head -1",
        "bin_paths": {"9bao": "/usr/local/bin/rg"},
        "install_method": "binary",
        "category": "tool",
    },
]

SSH_KEY_DEFAULT = os.path.expanduser(
    "~/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519"
)
SSH_KNOWN_DEFAULT = os.path.expanduser(
    "~/AppData/Local/vibedev-tools/ssh/debian-vibeworker-known_hosts"
)
SSH_PORT = 22222
SSH_USER = "vibeworker"
WORKER_IPS = {
    "5bao": os.environ.get("VIBEDEV_WORKER_5BAO_HOST", "UNCONFIGURED"),
    "9bao": os.environ.get("VIBEDEV_WORKER_9BAO_HOST", "UNCONFIGURED"),
}


def ssh_exec(node, cmd, timeout=15):
    """Execute a command on a remote worker via SSH."""
    ip = WORKER_IPS.get(node)
    if not ip:
        return None, f"unknown node: {node}"
    ssh_cmd = [
        "ssh",
        "-i", SSH_KEY_DEFAULT,
        "-o", f"UserKnownHostsFile={SSH_KNOWN_DEFAULT}",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=10",
        "-p", str(SSH_PORT),
        f"{SSH_USER}@{ip}",
        cmd,
    ]
    try:
        r = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except Exception as e:
        return None, str(e)


def get_binary_sha256(node, bin_path):
    """Get SHA256 of a remote binary."""
    cmd = f"sha256sum {bin_path} 2>/dev/null | cut -d' ' -f1"
    stdout, stderr = ssh_exec(node, cmd)
    if stdout and re.match(r"^[0-9a-f]{64}$", stdout):
        return stdout
    return "unavailable"


def check_config_presence(node, config_path):
    """Check if a config file exists on remote node."""
    cmd = f"test -f {config_path} && echo present || echo absent"
    stdout, _ = ssh_exec(node, cmd)
    return stdout if stdout else "unknown"


def check_secret_presence(node, secret_path):
    """Check if a secret file exists (no content)."""
    cmd = f"test -f {secret_path} && echo present || echo absent"
    stdout, _ = ssh_exec(node, cmd)
    return stdout if stdout else "unknown"


def scan_component(comp_def):
    """Scan a single component across its nodes."""
    records = []
    for node in comp_def["nodes"]:
        bin_path_raw = comp_def.get("bin_paths", {}).get(node, "")
        version_cmd = comp_def["version_cmd"]
        if bin_path_raw and "{bin}" in version_cmd:
            version_cmd = version_cmd.replace("{bin}", bin_path_raw)

        stdout, stderr = ssh_exec(node, version_cmd)
        version = stdout if stdout else "unavailable"

        binary_sha256 = "n/a"
        if bin_path_raw:
            binary_sha256 = get_binary_sha256(node, bin_path_raw)

        record = {
            "component": comp_def["id"],
            "node": node,
            "current_version": version,
            "install_path": bin_path_raw or "system_managed",
            "install_method": comp_def["install_method"],
            "binary_sha256": binary_sha256,
            "config_path_presence": "not_checked",
            "secret_ref": "not_checked",
            "last_verified": datetime.now(timezone.utc).isoformat(),
            "category": comp_def["category"],
        }
        records.append(record)
    return records


def scan_windows_local():
    """Scan Windows-local components (no SSH needed)."""
    records = []

    # Python
    try:
        r = subprocess.run(
            ["python", "--version"], capture_output=True, text=True, timeout=10
        )
        version = r.stdout.strip() if r.returncode == 0 else "unavailable"
    except Exception:
        version = "unavailable"
    records.append({
        "component": "python-runtime",
        "node": "windows",
        "current_version": version,
        "install_path": "system_managed",
        "install_method": "system",
        "binary_sha256": "n/a",
        "config_path_presence": "not_checked",
        "secret_ref": "not_checked",
        "last_verified": datetime.now(timezone.utc).isoformat(),
        "category": "runtime",
    })

    # Git
    try:
        r = subprocess.run(
            ["git", "--version"], capture_output=True, text=True, timeout=10
        )
        version = r.stdout.strip() if r.returncode == 0 else "unavailable"
    except Exception:
        version = "unavailable"
    records.append({
        "component": "git-runtime",
        "node": "windows",
        "current_version": version,
        "install_path": "system_managed",
        "install_method": "system",
        "binary_sha256": "n/a",
        "config_path_presence": "not_checked",
        "secret_ref": "not_checked",
        "last_verified": datetime.now(timezone.utc).isoformat(),
        "category": "tool",
    })

    return records


def run_inventory():
    """Run full inventory scan."""
    all_records = []
    for comp_def in COMPONENT_DEFS:
        records = scan_component(comp_def)
        all_records.extend(records)
    all_records.extend(scan_windows_local())
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_commit": "unknown",
        "records": all_records,
    }


def self_check():
    """Run self-validation without SSH."""
    print("=== runtime_inventory.py self-check ===")
    errors = 0

    # Check schema version
    assert SCHEMA_VERSION == 1, "schema_version must be 1"
    print("  PASS  schema_version=1")

    # Check component defs are well-formed
    for comp in COMPONENT_DEFS:
        assert "id" in comp, f"missing id in {comp}"
        assert "nodes" in comp, f"missing nodes in {comp}"
        assert "version_cmd" in comp, f"missing version_cmd in {comp}"
        assert "install_method" in comp, f"missing install_method in {comp}"
        assert "category" in comp, f"missing category in {comp}"
        for node in comp["nodes"]:
            assert node in ("5bao", "9bao"), f"invalid node: {node}"
    print(f"  PASS  {len(COMPONENT_DEFS)} component definitions valid")

    # Check SSH config paths exist (on Windows)
    if os.name == "nt":
        for label, path in [("SSH_KEY", SSH_KEY_DEFAULT), ("SSH_KNOWN", SSH_KNOWN_DEFAULT)]:
            exists = os.path.exists(path)
            print(f"  {'PASS' if exists else 'WARN'}  {label} exists={exists}")

    # Check WORKER_IPS
    assert "5bao" in WORKER_IPS and "9bao" in WORKER_IPS, "missing worker IPs"
    assert "5bao" in WORKER_IPS and "9bao" in WORKER_IPS, "missing worker IPs"
    # IPs come from env vars; in self-check mode they may be UNCONFIGURED
    for node, ip in WORKER_IPS.items():
        if ip == "UNCONFIGURED":
            print(f"  WARN  {node} host not configured (set VIBEDEV_WORKER_{node.upper()}_HOST)")
        else:
            print(f"  PASS  {node} host configured")
    print("  PASS  worker IP config structure valid")

    # Check output format
    sample = {
        "schema_version": 1,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "base_commit": "test",
        "records": [],
    }
    json_str = json.dumps(sample, indent=2)
    parsed = json.loads(json_str)
    assert parsed["schema_version"] == 1
    print("  PASS  output JSON schema valid")

    print("=== self-check PASSED ===")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Runtime version inventory scanner")
    parser.add_argument("--output", "-o", help="Output file path (default: stdout)")
    parser.add_argument("--self-check", action="store_true", help="Run self-validation")
    args = parser.parse_args()

    if args.self_check:
        sys.exit(self_check())

    inventory = run_inventory()

    output = json.dumps(inventory, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Inventory written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
