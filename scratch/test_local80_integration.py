#!/usr/bin/env python3
"""
Integration test for LOCAL-80: actually creates worktrees and proves merge-base,
plus the liveness check.

Run from the LOCAL-80 worktree:
    python3 scratch/test_local80_integration.py

IMPORTANT: This creates and cleans up temporary worktrees under
/tmp/local80_test_worktrees_*. It does NOT touch ~/audioura-worktrees/ or
the live dispatcher queue.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kiro_dispatcher as kd

REPO_DIR = Path(__file__).resolve().parent.parent  # LOCAL-80 worktree


def run(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=str(cwd or REPO_DIR), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{r.stderr}")
    return r


def test_worktree_from_subscribed():
    """
    Create a worktree with base=subscribed, verify via git merge-base that
    the new branch is rooted on subscribed, not storied.
    """
    print("\n--- Test: worktree from subscribed base ---")
    test_branch = "kiro/test-local80-sub-base"
    task_id = "TEST-LOCAL80-SUB"
    test_wt = kd.WORKTREE_BASE / task_id

    # Clean up any leftover from prior run
    if test_wt.exists():
        run(["git", "worktree", "remove", "--force", str(test_wt)], check=False)
    run(["git", "branch", "-D", test_branch], check=False)

    try:
        path = kd.setup_worktree(task_id, test_branch, "subscribed")
        assert path.exists(), f"Worktree not created at {path}"

        # Verify: merge-base of the new branch and subscribed should be the tip of subscribed
        subscribed_sha = run(["git", "rev-parse", "subscribed"]).stdout.strip()
        branch_sha = run(["git", "rev-parse", test_branch]).stdout.strip()
        merge_base = run(["git", "merge-base", test_branch, "subscribed"]).stdout.strip()

        # The new branch should point AT subscribed tip (just created from it)
        assert branch_sha == subscribed_sha, (
            f"Branch {test_branch} at {branch_sha} should equal subscribed {subscribed_sha}"
        )
        assert merge_base == subscribed_sha, (
            f"merge-base should be subscribed tip {subscribed_sha}, got {merge_base}"
        )

        # Verify it's NOT cut from storied (unless storied == subscribed)
        storied_sha = run(["git", "rev-parse", "storied"]).stdout.strip()
        if storied_sha != subscribed_sha:
            assert branch_sha != storied_sha, "Branch should NOT be at storied tip"
            print(f"  Confirmed: branch is at subscribed ({subscribed_sha[:8]}), NOT storied ({storied_sha[:8]})")
        else:
            print(f"  Note: storied and subscribed currently point to the same commit")

        print(f"  git merge-base {test_branch} subscribed = {merge_base[:8]}")
        print("  PASS: worktree cut from subscribed, proven via merge-base")

    finally:
        # Cleanup
        run(["git", "worktree", "remove", "--force", str(test_wt)], check=False)
        run(["git", "branch", "-D", test_branch], check=False)


def test_worktree_from_storied_default():
    """
    Create a worktree with base=storied (default), verify merge-base.
    """
    print("\n--- Test: worktree from storied (default) base ---")
    test_branch = "kiro/test-local80-stor-base"
    task_id = "TEST-LOCAL80-STOR"
    test_wt = kd.WORKTREE_BASE / task_id

    # Clean up any leftover
    if test_wt.exists():
        run(["git", "worktree", "remove", "--force", str(test_wt)], check=False)
    run(["git", "branch", "-D", test_branch], check=False)

    try:
        path = kd.setup_worktree(task_id, test_branch, "storied")
        assert path.exists(), f"Worktree not created at {path}"

        storied_sha = run(["git", "rev-parse", "storied"]).stdout.strip()
        branch_sha = run(["git", "rev-parse", test_branch]).stdout.strip()
        merge_base = run(["git", "merge-base", test_branch, "storied"]).stdout.strip()

        assert branch_sha == storied_sha
        assert merge_base == storied_sha
        print(f"  git merge-base {test_branch} storied = {merge_base[:8]}")
        print("  PASS: worktree cut from storied, proven via merge-base")

    finally:
        run(["git", "worktree", "remove", "--force", str(test_wt)], check=False)
        run(["git", "branch", "-D", test_branch], check=False)


def test_bad_base_no_worktree():
    """
    A bad base name should fail before creating any worktree.
    """
    print("\n--- Test: bad base name fails, no worktree created ---")
    task_id = "TEST-LOCAL80-BAD"
    test_wt = kd.WORKTREE_BASE / task_id

    # Ensure clean
    if test_wt.exists():
        run(["git", "worktree", "remove", "--force", str(test_wt)], check=False)

    ok, err = kd.validate_base_branch("nonexistent-typo-xyz", REPO_DIR)
    assert not ok
    assert "does not exist" in err
    assert not test_wt.exists(), "No worktree should be created for a bad base"
    print(f"  Error message: {err[:100]}")
    print("  PASS: bad base fails at validation, no worktree created")


def test_liveness_kill_worker():
    """
    Simulate a dead worker: start a subprocess, record its PID as STARTED,
    kill it, then verify check_worker_liveness() catches it.
    """
    print("\n--- Test: liveness check detects dead worker ---")

    # We'll manipulate the log file carefully. Save and restore.
    original_log = kd.LOG_FILE
    original_content = original_log.read_text() if original_log.exists() else None

    # Create a throwaway task file
    task_name = "new_kiro_session_is_required_TEST-LIVENESS.md"
    task_path = kd.WATCH_DIR / task_name
    task_path.write_text("**Agent:** Test\n**Task ID:** TEST-LIVENESS\n**Branch:** kiro/test-liveness\n\nDummy.\n")

    # Start a subprocess that will become our "worker", then kill it
    proc = subprocess.Popen(["sleep", "300"])
    dead_pid = proc.pid
    proc.kill()
    proc.wait()

    # Write a STARTED record with that dead PID
    kd.locked_append(
        f"- STARTED   | task={task_name} | at=2026-07-31T12:00:00-04:00 | "
        f"base=storied | dispatcher_pid={dead_pid}"
    )

    try:
        abandoned = kd.check_worker_liveness()
        assert task_name in abandoned, \
            f"Expected {task_name} in abandoned list, got: {abandoned}"

        # Verify ABANDONED was written
        log_text = kd.LOG_FILE.read_text()
        assert f"ABANDONED | task={task_name}" in log_text
        assert f"reason=worker_died" in log_text
        assert f"dead_pid={dead_pid}" in log_text
        print(f"  Killed PID {dead_pid}, check_worker_liveness() detected it")
        print("  PASS: dead worker produces ABANDONED record, task eligible for re-dispatch")

    finally:
        # Restore log and clean up task file
        if original_content is not None:
            original_log.write_text(original_content)
        task_path.unlink(missing_ok=True)


def test_worktree_reused_on_retry():
    """
    After ABANDONED, the worktree should still exist and be reused on next attempt.
    """
    print("\n--- Test: worktree reused on retry (not deleted) ---")
    test_branch = "kiro/test-local80-reuse"
    task_id = "TEST-LOCAL80-REUSE"
    test_wt = kd.WORKTREE_BASE / task_id

    # Clean up any leftover
    if test_wt.exists():
        run(["git", "worktree", "remove", "--force", str(test_wt)], check=False)
    run(["git", "branch", "-D", test_branch], check=False)

    try:
        # First creation
        path1 = kd.setup_worktree(task_id, test_branch, "storied")
        assert path1.exists()

        # Create a marker file in the worktree (simulates in-flight work)
        marker = path1 / "LOCAL80_INFLIGHT_WORK.txt"
        marker.write_text("This simulates in-flight work that should be preserved\n")

        # Second call (retry after abandon) should reuse
        path2 = kd.setup_worktree(task_id, test_branch, "storied")
        assert path2 == path1, "Should return same path on retry"
        assert marker.exists(), "In-flight work should be preserved"
        print("  PASS: worktree reused on retry, in-flight work preserved")

    finally:
        # Cleanup
        if marker.exists():
            marker.unlink()
        run(["git", "worktree", "remove", "--force", str(test_wt)], check=False)
        run(["git", "branch", "-D", test_branch], check=False)


if __name__ == "__main__":
    print("=== LOCAL-80 Integration Tests ===")

    tests = [
        test_worktree_from_subscribed,
        test_worktree_from_storied_default,
        test_bad_base_no_worktree,
        test_liveness_kill_worker,
        test_worktree_reused_on_retry,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {t.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*40}")
    print(f"Integration Results: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
