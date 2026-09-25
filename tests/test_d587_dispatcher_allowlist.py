"""D587 — the dispatcher must not treat "a file exists" as "spend money on this".

2026-09-23: clearing the PAUSE sentinel dispatched 35 task files in a single tick
(97 kiro processes) against an intended four. The extra 34 were untracked files that
had appeared at the repo root, duplicating work already completed and merged the same
afternoon. 35 worktrees at ~280MB is ~10GB against 7.9GB free -- it would have filled
the disk and re-wedged Docker. Killed mid-checkout, nothing lost.
"""
import importlib
import pytest

kd = importlib.import_module('kiro_dispatcher')


@pytest.fixture
def allowlist(tmp_path, monkeypatch):
    f = tmp_path / 'RELEASED.txt'
    monkeypatch.setattr(kd, 'ALLOWLIST_FILE', f)
    return f


def test_absent_allowlist_dispatches_nothing(allowlist, monkeypatch):
    """Fails CLOSED. The failure mode of this dispatcher is spending money."""
    assert not allowlist.exists()
    assert kd.released_ids() == set()


def test_only_listed_ids_are_released(allowlist):
    allowlist.write_text('LOCAL-527\nLOCAL-529\n')
    assert kd.released_ids() == {'LOCAL-527', 'LOCAL-529'}


def test_comments_and_blank_lines_are_ignored(allowlist):
    allowlist.write_text('# a note\n\nLOCAL-530   # trailing comment\n\n')
    assert kd.released_ids() == {'LOCAL-530'}


def test_find_task_files_filters_by_allowlist(allowlist, tmp_path, monkeypatch):
    monkeypatch.setattr(kd, 'WATCH_DIR', tmp_path)
    for tid in ('LOCAL-527', 'LOCAL-3513', 'LOCAL-3514'):
        (tmp_path / f'new_kiro_session_is_required_{tid}.md').write_text('# task')
    allowlist.write_text('LOCAL-527\n')
    names = [p.name for p in kd.find_task_files()]
    assert names == ['new_kiro_session_is_required_LOCAL-527.md'], names


class TestSetupFailureRetry:
    """A worktree that could not be created means the task never ran.

    2026-09-23: killing a runaway 35-task dispatch mid-checkout left
    worktree_setup_failed records on four correctly-allowlisted tasks, and a FAILED
    record blocked them from ever running. No model was called and no work was
    attempted, so there was nothing to learn from not retrying.
    """

    def _log(self, tmp_path, monkeypatch, lines):
        f = tmp_path / 'kiro_sessions_ran.md'
        f.write_text('\n'.join(lines) + '\n')
        monkeypatch.setattr(kd, 'LOG_FILE', f)
        return f

    def test_setup_failure_is_retried(self, tmp_path, monkeypatch):
        self._log(tmp_path, monkeypatch, [
            '- FAILED    | task=new_kiro_session_is_required_LOCAL-527.md | '
            'reason=worktree_setup_failed: Preparing worktree (new branch)',
        ])
        assert kd.already_claimed('new_kiro_session_is_required_LOCAL-527.md') is False

    def test_a_real_failure_is_not_retried(self, tmp_path, monkeypatch):
        """The guard still does its original job."""
        self._log(tmp_path, monkeypatch, [
            '- FAILED    | task=new_kiro_session_is_required_LOCAL-524.md | '
            'reason=acceptance criteria not met',
        ])
        assert kd.already_claimed('new_kiro_session_is_required_LOCAL-524.md') is True

    def test_setup_failures_are_capped(self, tmp_path, monkeypatch):
        """Three is enough; a broken setup must not loop forever."""
        line = ('- FAILED    | task=new_kiro_session_is_required_LOCAL-527.md | '
                'reason=worktree_setup_failed: Preparing worktree (new branch)')
        self._log(tmp_path, monkeypatch, [line] * 3)
        assert kd.already_claimed('new_kiro_session_is_required_LOCAL-527.md') is True

    def test_completed_still_blocks(self, tmp_path, monkeypatch):
        self._log(tmp_path, monkeypatch, [
            '- COMPLETED | task=new_kiro_session_is_required_LOCAL-526.md | id=T1',
        ])
        assert kd.already_claimed('new_kiro_session_is_required_LOCAL-526.md') is True
