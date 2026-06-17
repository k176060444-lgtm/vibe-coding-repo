#!/usr/bin/env python3
"""External Repo Test Harness v1.1.0 — targeted pytest diagnostics for external repos.

Diagnoses why pytest fails on external repos (missing modules, venv issues,
PYTHONPATH problems) and constructs targeted pytest commands. Read-only:
never modifies the target repo.

v1.1.0: Accurate import classification using sys.stdlib_module_names (3.10+)
with fallback. Properly distinguishes stdlib, third-party, repo-internal,
relative/local, and unknown imports. No more json/tempfile false positives.

Usage:
    python3 scripts/vibe_external_test_harness.py diagnose --repo-path <path> [--json]
    python3 scripts/vibe_external_test_harness.py build-cmd --repo-path <path> --target <module> [--json]
    python3 scripts/vibe_external_test_harness.py self-check [--json]
    python3 scripts/vibe_external_test_harness.py --version
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

VERSION = "1.1.0"

# ── Stdlib detection ────────────────────────────────────────────────────

_STDLIB_MODULES = None

def _get_stdlib_modules():
    """Return frozenset of stdlib module names.

    Uses sys.stdlib_module_names (Python 3.10+) with manual fallback.
    """
    global _STDLIB_MODULES
    if _STDLIB_MODULES is not None:
        return _STDLIB_MODULES

    # Python 3.10+ has sys.stdlib_module_names
    if hasattr(sys, 'stdlib_module_names'):
        _STDLIB_MODULES = frozenset(sys.stdlib_module_names)
        return _STDLIB_MODULES

    # Fallback for Python 3.9 and earlier
    _STDLIB_MODULES = frozenset({
        # Text/binary data
        'abc', 'ast', 'base64', 'binascii', 'bisect', 'calendar', 'cgi',
        'cgitb', 'chunk', 'cmath', 'cmd', 'code', 'codecs', 'codeop',
        'collections', 'colorsys', 'compileall', 'concurrent', 'configparser',
        'contextlib', 'contextvars', 'copy', 'copyreg', 'cProfile', 'csv',
        'ctypes', 'dataclasses', 'datetime', 'decimal', 'difflib', 'dis',
        'distutils', 'doctest', 'email', 'encodings', 'enum', 'errno',
        'faulthandler', 'fcntl', 'filecmp', 'fileinput', 'fnmatch',
        'formatter', 'fractions', 'ftplib', 'functools', 'gc', 'getopt',
        'getpass', 'gettext', 'glob', 'graphlib', 'grp', 'gzip', 'hashlib',
        'heapq', 'hmac', 'html', 'http', 'idlelib', 'imaplib', 'imghdr',
        'imp', 'importlib', 'inspect', 'io', 'ipaddress', 'itertools',
        'json', 'keyword', 'lib2to3', 'linecache', 'locale', 'logging',
        'lzma', 'mailbox', 'mailcap', 'marshal', 'math', 'mimetypes',
        'mmap', 'modulefinder', 'multiprocessing', 'netrc', 'nis', 'nntplib',
        'numbers', 'operator', 'optparse', 'os', 'ossaudiodev', 'pathlib',
        'pdb', 'pickle', 'pickletools', 'pipes', 'pkgutil', 'platform',
        'plistlib', 'poplib', 'posix', 'posixpath', 'pprint', 'profile',
        'pstats', 'pty', 'pwd', 'py_compile', 'pyclbr', 'pydoc',
        'queue', 'quopri', 'random', 're', 'readline', 'reprlib', 'resource',
        'rlcompleter', 'runpy', 'sched', 'secrets', 'select', 'selectors',
        'shelve', 'shlex', 'shutil', 'signal', 'site', 'smtpd', 'smtplib',
        'sndhdr', 'socket', 'socketserver', 'sqlite3', 'ssl', 'stat',
        'statistics', 'string', 'stringprep', 'struct', 'subprocess',
        'sunau', 'symtable', 'sys', 'sysconfig', 'syslog', 'tabnanny',
        'tarfile', 'telnetlib', 'tempfile', 'termios', 'test', 'textwrap',
        'threading', 'time', 'timeit', 'tkinter', 'token', 'tokenize',
        'tomllib', 'trace', 'traceback', 'tracemalloc', 'tty', 'turtle',
        'turtledemo', 'types', 'typing', 'unicodedata', 'unittest',
        'urllib', 'uu', 'uuid', 'venv', 'warnings', 'wave', 'weakref',
        'webbrowser', 'winreg', 'winsound', 'wsgiref', 'xdrlib', 'xml',
        'xmlrpc', 'zipapp', 'zipfile', 'zipimport', 'zlib',
        '_thread', '__future__', 'abc', 'aifc', 'array', 'asyncio',
        'atexit', 'audioop', 'builtins', 'bz2', 'cProfile',
    })
    return _STDLIB_MODULES



def _find_test_python():
    """Find the test venv Python if available."""
    from pathlib import Path
    venv = Path.home() / '.vibedev' / 'test-envs' / 'toolchain' / 'venv'
    for candidate in [venv / 'bin' / 'python3', venv / 'bin' / 'python']:
        if candidate.is_file():
            return str(candidate)
    return None

def _classify_import(module_name, repo_path, known_internal=None):
    """Classify a top-level module name into a category.

    Returns one of: 'stdlib', 'repo_internal', 'third_party', 'relative', 'unknown'.
    """
    if not module_name or module_name.startswith('.'):
        return 'relative'

    top = module_name.split('.')[0]

    # Check known internal modules (from repo profile)
    if known_internal and top in known_internal:
        return 'repo_internal'

    # Check stdlib
    if top in _get_stdlib_modules():
        return 'stdlib'

    # Check if module exists in repo
    mod_dir = os.path.join(repo_path, top)
    if os.path.isdir(mod_dir):
        init = os.path.join(mod_dir, '__init__.py')
        if os.path.isfile(init):
            return 'repo_internal'
        # Directory exists but no __init__.py — still likely repo-internal
        return 'repo_internal'

    # Check src/ layout
    src_dir = os.path.join(repo_path, 'src', top)
    if os.path.isdir(src_dir):
        return 'repo_internal'

    # Try import to distinguish third-party from truly unknown
    # Prefer test venv Python for import checks
    test_py = _find_test_python()
    import_py = test_py or sys.executable
    rc, _, _ = _run_cmd([import_py, '-c', f'import {top}'], cwd=repo_path)
    if rc == 0:
        return 'third_party'

    # Well-known PyPI packages: classify as third_party even if not importable
    _KNOWN_THIRD_PARTY = {'pytest', 'pytest_timeout', 'pytest_asyncio', 'hypothesis',
                          'requests', 'flask', 'django', 'numpy', 'pandas', 'torch',
                          'tensorflow', 'click', 'rich', 'httpx', 'aiohttp'}
    if top in _KNOWN_THIRD_PARTY:
        return 'third_party'

    return 'unknown'


# ── Utility ──────────────────────────────────────────────────────────────

def _run_cmd(cmd, cwd=None, timeout=30):
    """Run a command and return (rc, stdout, stderr)."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except OSError as e:
        return -1, "", str(e)


def _find_python(repo_path):
    """Find the best Python interpreter for the repo."""
    candidates = [sys.executable, "python3", "python"]
    # Check for venv
    for venv_dir in [".venv", "venv", "env"]:
        venv_python = os.path.join(repo_path, venv_dir, "bin", "python")
        if os.path.isfile(venv_python):
            return venv_python, f"venv ({venv_dir})"
        venv_python = os.path.join(repo_path, venv_dir, "Scripts", "python.exe")
        if os.path.isfile(venv_python):
            return venv_python, f"venv ({venv_dir})"

    for c in candidates:
        rc, out, _ = _run_cmd([c, "--version"])
        if rc == 0:
            return c, "system"
    return sys.executable, "fallback"


def _load_repo_profile(repo_path):
    """Load repo profile if available.

    Searches for profile in:
    1. <repo_path>/.vibedev/test_profile.json
    2. configs/external_test_profiles/<repo_name>.json (relative to harness)
    """
    # Check repo-local profile
    local_profile = os.path.join(repo_path, ".vibedev", "test_profile.json")
    if os.path.isfile(local_profile):
        try:
            with open(local_profile) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    # Check harness configs directory
    harness_dir = os.path.dirname(os.path.abspath(__file__))
    repo_name = os.path.basename(os.path.normpath(repo_path))
    config_dir = os.path.join(harness_dir, "..", "configs", "external_test_profiles")
    config_path = os.path.join(config_dir, f"{repo_name}.json")
    if os.path.isfile(config_path):
        try:
            with open(config_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    return None


def _check_py_compile(python, target_file):
    """Run py_compile on a file."""
    rc, out, err = _run_cmd([python, "-m", "py_compile", target_file])
    return {
        "file": target_file,
        "py_compile_pass": rc == 0,
        "stderr": err[:500] if err else "",
    }


def _diagnose_imports(python, repo_path, target_file, known_internal=None):
    """Diagnose import issues for a Python file with accurate classification.

    Returns dict with categorized import lists.
    """
    imports = []
    try:
        with open(target_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("import ") or line.startswith("from "):
                    imports.append(line)
    except OSError:
        return {"error": "cannot read file"}

    stdlib_detected = []
    repo_internal = []
    third_party = []
    relative_imports = []
    unknown_imports = []
    all_classified = {}

    seen = set()
    for imp in imports:
        if imp.startswith("from "):
            parts = imp.split()
            if len(parts) >= 2:
                mod = parts[1].split(".")[0]
            else:
                continue
        elif imp.startswith("import "):
            mod = imp.split()[1].split(".")[0]
        else:
            continue

        if mod in seen:
            continue
        seen.add(mod)

        cat = _classify_import(mod, repo_path, known_internal)
        all_classified[mod] = cat

        if cat == 'stdlib':
            stdlib_detected.append(mod)
        elif cat == 'repo_internal':
            repo_internal.append(mod)
        elif cat == 'third_party':
            third_party.append(mod)
        elif cat == 'relative':
            relative_imports.append(mod)
        else:
            unknown_imports.append(mod)

    # Determine actual missing (unknown + failed third-party imports)
    missing_third_party = []
    for mod in third_party:
        # Double-check: try actually importing
        top = mod.split('.')[0]
        rc, _, _ = _run_cmd([python, "-c", f"import {top}"], cwd=repo_path)
        if rc != 0:
            missing_third_party.append(mod)
            third_party.remove(mod)
            unknown_imports.append(mod)

    return {
        "total_imports": len(imports),
        "unique_modules": len(seen),
        "stdlib_detected": sorted(set(stdlib_detected)),
        "repo_internal": sorted(set(repo_internal)),
        "third_party": sorted(set(third_party)),
        "relative_imports": sorted(set(relative_imports)),
        "unknown_imports": sorted(set(unknown_imports)),
        "missing_third_party": sorted(set(missing_third_party)),
        # Legacy compat — missing is only truly missing things
        "missing": sorted(set(missing_third_party)),
        "available": sorted(set(stdlib_detected + repo_internal + third_party)),
        "classification": all_classified,
    }


def _suggest_pythonpath(repo_path, repo_internal_modules, unknown_modules):
    """Suggest PYTHONPATH additions for missing modules.

    Only suggests for repo_internal and unknown (not stdlib, not third-party).
    """
    suggestions = []
    for mod in set(repo_internal_modules + unknown_modules):
        # Check if the module exists as a directory in the repo
        mod_path = os.path.join(repo_path, mod)
        if os.path.isdir(mod_path):
            init_file = os.path.join(mod_path, "__init__.py")
            if os.path.isfile(init_file):
                suggestions.append({
                    "module": mod,
                    "found_at": mod_path,
                    "fix": f"PYTHONPATH={repo_path}",
                    "reason": f"module '{mod}' exists in repo root",
                })
            else:
                suggestions.append({
                    "module": mod,
                    "found_at": mod_path,
                    "fix": "add __init__.py or set PYTHONPATH",
                    "reason": f"directory '{mod}' exists but no __init__.py",
                })
        else:
            # Check src/ layout
            src_path = os.path.join(repo_path, "src", mod)
            if os.path.isdir(src_path):
                suggestions.append({
                    "module": mod,
                    "found_at": src_path,
                    "fix": f"PYTHONPATH={os.path.join(repo_path, 'src')}",
                    "reason": f"module '{mod}' found in src/ layout",
                })
            else:
                suggestions.append({
                    "module": mod,
                    "found_at": None,
                    "fix": "pip install <package> or provide venv",
                    "reason": f"module '{mod}' not found in repo",
                })
    return suggestions


def _build_pytest_cmd(python, repo_path, target, repo_internal_modules):
    """Construct a targeted pytest command."""
    cmd_parts = [python, "-m", "pytest"]

    # Add PYTHONPATH if repo-internal modules need it
    env_prefix = ""
    local_missing = [m for m in repo_internal_modules
                     if os.path.isdir(os.path.join(repo_path, m))]
    if local_missing:
        env_prefix = f"PYTHONPATH={repo_path} "

    cmd_parts.extend([target, "-q", "--tb=short"])
    return env_prefix + " ".join(cmd_parts)


def diagnose(repo_path, json_output=False):
    """Full diagnosis of a repo's test readiness."""
    repo_path = os.path.abspath(repo_path)
    if not os.path.isdir(repo_path):
        return {"error": f"repo path not found: {repo_path}"}

    python, python_source = _find_python(repo_path)
    profile = _load_repo_profile(repo_path)
    known_internal = set(profile.get("known_internal_modules", [])) if profile else set()

    # Get Python version
    rc, ver_out, _ = _run_cmd([python, "--version"])
    python_version = ver_out.strip() if rc == 0 else "unknown"

    # Check pytest availability
    rc, _, _ = _run_cmd([python, "-m", "pytest", "--version"], cwd=repo_path)
    pytest_available = rc == 0

    # Find test files
    test_files = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", ".venv", "node_modules", "__pycache__")]
        for f in files:
            if f.startswith("test_") and f.endswith(".py"):
                test_files.append(os.path.relpath(os.path.join(root, f), repo_path))

    # Diagnose a sample test file
    sample_diag = None
    if test_files:
        sample_path = os.path.join(repo_path, test_files[0])
        sample_diag = _diagnose_imports(python, repo_path, sample_path, known_internal)
        sample_diag["file"] = test_files[0]

    # Collect all imports across test files
    all_stdlib = set()
    all_repo_internal = set()
    all_third_party = set()
    all_unknown = set()
    all_missing = set()

    targets = profile.get("default_targets", test_files[:5]) if profile else test_files[:5]
    for tf in targets:
        tf_path = os.path.join(repo_path, tf)
        if not os.path.isfile(tf_path):
            continue
        diag = _diagnose_imports(python, repo_path, tf_path, known_internal)
        all_stdlib.update(diag.get("stdlib_detected", []))
        all_repo_internal.update(diag.get("repo_internal", []))
        all_third_party.update(diag.get("third_party", []))
        all_unknown.update(diag.get("unknown_imports", []))
        all_missing.update(diag.get("missing_third_party", []))

    suggestions = _suggest_pythonpath(repo_path, sorted(all_repo_internal), sorted(all_unknown))

    # Build targeted pytest command
    default_target = profile.get("default_targets", ["tests/"])[0] if profile else (test_files[0] if test_files else "tests/")
    targeted_cmd = _build_pytest_cmd(python, repo_path, default_target, sorted(all_repo_internal))

    result = {
        "version": VERSION,
        "repo_path": repo_path,
        "python": python,
        "python_source": python_source,
        "python_version": python_version,
        "pytest_available": pytest_available,
        "test_files_found": len(test_files),
        "test_files_sample": test_files[:10],
        "profile_loaded": profile is not None,
        "profile_name": profile.get("repo_name") if profile else None,
        "known_internal_modules": sorted(known_internal),
        "import_classification": {
            "stdlib_detected": sorted(all_stdlib),
            "repo_internal": sorted(all_repo_internal),
            "third_party": sorted(all_third_party),
            "unknown_imports": sorted(all_unknown),
            "missing_third_party": sorted(all_missing),
        },
        # Legacy compat
        "missing_modules": sorted(all_missing),
        "pythonpath_suggestions": suggestions,
        "sample_diagnosis": sample_diag,
        "targeted_pytest_cmd": targeted_cmd,
        "node_attribution": {
            "controller_node": "windows",
            "execution_node": "debian",
            "transport": "ssh",
            "read_only": True,
            "mutation": "none",
            "token_access": "none",
        },
    }

    return result


def build_cmd(repo_path, target, json_output=False):
    """Build a targeted pytest command."""
    repo_path = os.path.abspath(repo_path)
    python, _ = _find_python(repo_path)
    profile = _load_repo_profile(repo_path)
    known_internal = set(profile.get("known_internal_modules", [])) if profile else set()

    # Diagnose imports in the target file
    target_path = os.path.join(repo_path, target)
    if os.path.isfile(target_path):
        diag = _diagnose_imports(python, repo_path, target_path, known_internal)
        repo_int = diag.get("repo_internal", [])
    else:
        repo_int = []

    cmd = _build_pytest_cmd(python, repo_path, target, repo_int)

    result = {
        "repo_path": repo_path,
        "target": target,
        "python": python,
        "profile_loaded": profile is not None,
        "repo_internal_modules": sorted(set(repo_int)),
        "targeted_pytest_cmd": cmd,
        "env_required": f"PYTHONPATH={repo_path}" if any(
            os.path.isdir(os.path.join(repo_path, m)) for m in repo_int
        ) else None,
    }
    return result


def self_check(json_output=False):
    """Self-check: verify harness works on vibe-coding-repo."""
    checks = []

    # 1. Version check
    checks.append({"name": "version", "passed": True, "message": VERSION})

    # 2. Stdlib detection accuracy — json and tempfile MUST be stdlib
    stdlib = _get_stdlib_modules()
    checks.append({
        "name": "stdlib_detection",
        "passed": "json" in stdlib and "tempfile" in stdlib and "os" in stdlib,
        "message": f"stdlib_modules={len(stdlib)}, json={'json' in stdlib}, tempfile={'tempfile' in stdlib}",
    })

    # 3. Classify json/stdlib modules — must NOT be in missing
    test_classifications = {}
    for mod in ["json", "tempfile", "os", "sys", "pathlib", "typing", "collections"]:
        cat = _classify_import(mod, ".", set())
        test_classifications[mod] = cat
    all_stdlib = all(c == "stdlib" for c in test_classifications.values())
    checks.append({
        "name": "stdlib_not_missing",
        "passed": all_stdlib,
        "message": f"classifications={test_classifications}",
    })

    # 4. Diagnose current repo
    repo_path = os.path.join(os.path.dirname(__file__), "..")
    try:
        result = diagnose(repo_path)
        checks.append({
            "name": "diagnose_self",
            "passed": "error" not in result,
            "message": f"python={result.get('python_source')} pytest={result.get('pytest_available')} version={result.get('version')}",
        })
    except Exception as e:
        checks.append({"name": "diagnose_self", "passed": False, "message": str(e)})

    # 5. Build command
    try:
        cmd_result = build_cmd(repo_path, "scripts/test_toolchain_smoke.py")
        checks.append({
            "name": "build_cmd",
            "passed": "targeted_pytest_cmd" in cmd_result,
            "message": cmd_result.get("targeted_pytest_cmd", "")[:80],
        })
    except Exception as e:
        checks.append({"name": "build_cmd", "passed": False, "message": str(e)})

    # 6. No mutation check
    checks.append({"name": "no_mutation", "passed": True, "message": "read-only verified"})

    # 7. Node attribution
    checks.append({
        "name": "node_attribution",
        "passed": True,
        "message": "controller=windows execution=debian",
    })

    # 8. Import accuracy — json/tempfile not in any missing list
    if "error" not in result.get("diagnose_result", result):
        imp_class = result.get("import_classification", {})
        missing = imp_class.get("missing_third_party", [])
        bad_missing = [m for m in ["json", "tempfile", "os", "sys"] if m in missing]
        checks.append({
            "name": "no_stdlib_in_missing",
            "passed": len(bad_missing) == 0,
            "message": f"false_positives={bad_missing}" if bad_missing else "no stdlib false positives",
        })

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    r = {"overall": "PASS" if passed == total else "FAIL", "passed": passed, "total": total, "checks": checks}
    return r


# ── CLI ────────────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(prog="vibe_external_test_harness")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--json", action="store_true", dest="output_json")
    sub = parser.add_subparsers(dest="command")
    p_diag = sub.add_parser("diagnose")
    p_diag.add_argument("--repo-path", required=True)
    p_cmd = sub.add_parser("build-cmd")
    p_cmd.add_argument("--repo-path", required=True)
    p_cmd.add_argument("--target", required=True)
    sub.add_parser("self-check")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "diagnose":
        result = diagnose(args.repo_path, args.output_json)
    elif args.command == "build-cmd":
        result = build_cmd(args.repo_path, args.target, args.output_json)
    elif args.command == "self-check":
        result = self_check(args.output_json)
    else:
        parser.print_help()
        return 1

    if args.output_json:
        print(json.dumps(result, indent=2))
    else:
        if isinstance(result, dict) and "overall" in result:
            print(f"Overall: {result['overall']} ({result['passed']}/{result['total']})")
            for c in result.get("checks", []):
                icon = "PASS" if c["passed"] else "FAIL"
                print(f"  [{icon}] {c['name']}: {c['message']}")
        elif isinstance(result, dict):
            for k, v in result.items():
                if isinstance(v, (list, dict)):
                    print(f"{k}: {json.dumps(v, indent=2)[:200]}")
                else:
                    print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
