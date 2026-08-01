#!/usr/bin/env python3
"""
run_tests.py — Suite runner for AudioTours AI.

Runs all test files and reports results that mean something.
Green means green: only tests that CAN pass without external services
or missing pip packages are included by default.

Usage:
    python3 run_tests.py                      # live tests only (default)
    python3 run_tests.py --include-services   # include needs-services tests
    python3 run_tests.py --include-deps       # include needs-dependency tests
    python3 run_tests.py --all                # include everything
    python3 run_tests.py --services-only      # ONLY needs-services tests
    python3 run_tests.py --deps-only          # ONLY needs-dependency tests

Exit codes:
    0  — all included tests passed
    1  — at least one test failed
    7  — infrastructure unavailable (only with --include-services)
"""
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
NEEDS_SERVICES_FILE = PROJECT_ROOT / "tests" / "NEEDS_SERVICES.txt"
NEEDS_DEPENDENCY_FILE = PROJECT_ROOT / "tests" / "NEEDS_DEPENDENCY.txt"
TOOLS_DIR = PROJECT_ROOT / "tools"

# Exit code convention (matches tests/db_connection.py)
EXIT_DB_UNREACHABLE = 7


def load_skip_list(filepath):
    """Load a skip-list file (one path per line, # comments)."""
    entries = set()
    if filepath.exists():
        for line in filepath.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                entries.add(line)
    return entries


def discover_tests():
    """Find all test files (test_*.py and run_*.py) excluding tools/."""
    tests = []
    # Root-level test files
    for f in sorted(PROJECT_ROOT.glob("test_*.py")):
        tests.append(str(f.relative_to(PROJECT_ROOT)))
    # tests/ directory
    tests_dir = PROJECT_ROOT / "tests"
    if tests_dir.exists():
        for f in sorted(tests_dir.glob("test_*.py")):
            tests.append(str(f.relative_to(PROJECT_ROOT)))
        for f in sorted(tests_dir.glob("run_*.py")):
            tests.append(str(f.relative_to(PROJECT_ROOT)))
    return tests


def run_test(test_path, timeout=60):
    """Run a single test file. Returns (exit_code, duration, output_snippet)."""
    start = time.time()
    try:
        env = os.environ.copy()
        # Ensure project root is importable from all test scripts
        pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(PROJECT_ROOT) + (os.pathsep + pythonpath if pythonpath else "")
        proc = subprocess.run(
            [sys.executable, test_path],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(PROJECT_ROOT), env=env,
        )
        duration = time.time() - start
        output = proc.stdout + proc.stderr
        # Truncate for display
        snippet = output.strip().split("\n")[-3:] if output.strip() else []
        return proc.returncode, duration, "\n".join(snippet)
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        return -1, duration, "(timeout)"


def main():
    include_services = "--include-services" in sys.argv or "--all" in sys.argv
    include_deps = "--include-deps" in sys.argv or "--all" in sys.argv
    services_only = "--services-only" in sys.argv
    deps_only = "--deps-only" in sys.argv

    needs_services = load_skip_list(NEEDS_SERVICES_FILE)
    needs_dependency = load_skip_list(NEEDS_DEPENDENCY_FILE)

    all_tests = discover_tests()

    # Filter
    if services_only:
        tests_to_run = [t for t in all_tests if t in needs_services]
    elif deps_only:
        tests_to_run = [t for t in all_tests if t in needs_dependency]
    else:
        skip_set = set()
        if not include_services:
            skip_set |= needs_services
        if not include_deps:
            skip_set |= needs_dependency
        tests_to_run = [t for t in all_tests if t not in skip_set]

    svc_skip = len([t for t in all_tests if t in needs_services])
    dep_skip = len([t for t in all_tests if t in needs_dependency])

    print("=" * 70)
    print(f"  TEST SUITE RUNNER — {len(tests_to_run)} tests")
    skip_parts = []
    if not include_services and not services_only and not deps_only:
        skip_parts.append(f"{svc_skip} needs-services")
    if not include_deps and not services_only and not deps_only:
        skip_parts.append(f"{dep_skip} needs-dependency")
    if skip_parts:
        print(f"  (skipping {', '.join(skip_parts)})")
    print("=" * 70)
    print()

    passed = []
    failed = []
    infra_failed = []

    for test_path in tests_to_run:
        rc, duration, snippet = run_test(test_path)

        if rc == 0:
            status = "\033[32mPASS\033[0m"
            passed.append(test_path)
        elif rc == EXIT_DB_UNREACHABLE:
            status = "\033[33mSKIP\033[0m (infra)"
            infra_failed.append(test_path)
        elif rc == -1:
            status = "\033[33mTIMEOUT\033[0m"
            if test_path in needs_services:
                infra_failed.append(test_path)
            else:
                failed.append(test_path)
        else:
            status = "\033[31mFAIL\033[0m"
            failed.append(test_path)

        print(f"  {status}  {duration:5.1f}s  {test_path}")

    print()
    print("=" * 70)
    print(f"  RESULTS: {len(passed)} passed, {len(failed)} failed", end="")
    if infra_failed:
        print(f", {len(infra_failed)} infra-skipped", end="")
    print(f" (of {len(tests_to_run)} total)")
    print("=" * 70)

    if failed:
        print("\n  FAILURES:")
        for f in failed:
            print(f"    ✗ {f}")

    if infra_failed:
        print("\n  INFRA-SKIPPED (exit 7 / timeout on services test):")
        for f in infra_failed:
            print(f"    ⊘ {f}")

    print()

    if failed:
        return 1
    if infra_failed and include_services:
        return EXIT_DB_UNREACHABLE
    return 0


if __name__ == "__main__":
    sys.exit(main())
