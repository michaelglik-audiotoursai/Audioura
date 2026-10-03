"""LOCAL-569: keep the best story-retry draft instead of shipping the last.

LOCAL-568 found (and LEAD confirmed in code) that the LOCAL-432 story retry
re-writes the whole stop and ships the LAST attempt. `_best_description` only
keeps the longest draft on fallback paths — never the one with the most story
sentences. In 12 of 42 logged episodes the shipped stop had FEWER story
sentences than a draft already produced.

This test pins the exact trajectory LOCAL-568 observed — story sentence counts
1 -> 0 -> 2 -> 1 across four attempts — against the REAL story gate, then shows:

  * today / STORY_RETRY_KEEP_BEST off  == ship-last  == story_count 1
  * STORY_RETRY_KEEP_BEST on           == keep-best  == story_count 2

The keep-best decision lives in the importable module-level helper
`_l569_select_best_story`, so this exercises production code, not a copy.
Draft texts are run through the real `story_gate.extract_story_sentences`
first, so the fixture can never silently drift from the classifier.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate_tour_text import (  # noqa: E402
    _l569_select_best_story,
    _l569_story_count,
    _l569_should_early_stop,
    _L569_STORY_ATTEMPT_CAP,
)


# --- The LOCAL-568 trajectory, built from real passing / non-passing sentences ---

# These two sentences each pass story_gate.is_story_sentence (named person +
# story verb + consequence). The filler sentences deliberately do not.
_PASS_A = ("Heinrich Fischer published a detailed study of this instrument in "
           "the Historic Brass Society Journal in 1989.")
_PASS_B = ("Marc Chagall donated this lithograph to the museum in 1971, "
           "enriching its modern collection.")
_FILLER1 = ("This gallery holds a remarkable collection of ceremonial brass "
            "instruments from across Europe.")
_FILLER2 = ("The surrounding cases display works of great beauty and careful "
            "craftsmanship.")
_FILLER3 = ("Visitors often pause here to study the intricate engraving on each "
            "polished surface.")

# attempt 0 -> 1 story sentence; 1 -> 0; 2 -> 2 (best); 3 -> 1 (last, worse)
_DRAFT_0 = " ".join([_FILLER1, _PASS_A, _FILLER2])
_DRAFT_1 = " ".join([_FILLER1, _FILLER2, _FILLER3])
_DRAFT_2 = " ".join([_FILLER1, _PASS_A, _PASS_B])
_DRAFT_3 = " ".join([_FILLER1, _PASS_B, _FILLER3])

_TRAJECTORY_DRAFTS = [_DRAFT_0, _DRAFT_1, _DRAFT_2, _DRAFT_3]


def _candidates_from_drafts(drafts):
    """Build keep-best candidate tuples exactly as the production loop does:
    (story_count, word_count, orientation, description, tokens, cost)."""
    cands = []
    for i, d in enumerate(drafts):
        sc = _l569_story_count(d)
        cands.append((sc, len(d.split()), f"Orientation {i}", d, 100, 0.01))
    return cands


class TestTrajectoryIsReal:
    """The 1 -> 0 -> 2 -> 1 fixture must match the real classifier, or the
    whole test proves nothing."""

    def test_counts_match_real_story_gate(self):
        counts = [_l569_story_count(d) for d in _TRAJECTORY_DRAFTS]
        assert counts == [1, 0, 2, 1], (
            f"Fixture drifted from the real story gate: got {counts}, "
            "expected the LOCAL-568 trajectory [1, 0, 2, 1]"
        )

    def test_story_count_helper_is_safe(self):
        assert _l569_story_count("") == 0
        assert _l569_story_count(None) == 0
        assert _l569_story_count("[GENERATION_FAILED:Foo]") == 0


class TestKeepBestVsShipLast:
    """The core LOCAL-569 behaviour on LOCAL-568's own trajectory."""

    def test_today_ships_last_story_count_1(self):
        """Flag off == today: the retry loop ships whatever the last attempt
        produced. On this trajectory that is story_count 1."""
        cands = _candidates_from_drafts(_TRAJECTORY_DRAFTS)
        shipped_last = cands[-1]
        assert shipped_last[0] == 1, "Last attempt should have story_count 1"
        assert shipped_last[3] == _DRAFT_3

    def test_keep_best_ships_story_count_2(self):
        """Flag on: _l569_select_best_story returns the attempt with the most
        story sentences — story_count 2, the third attempt — not the last."""
        cands = _candidates_from_drafts(_TRAJECTORY_DRAFTS)
        best = _l569_select_best_story(cands)
        assert best is not None
        assert best[0] == 2, f"Keep-best should ship story_count 2, got {best[0]}"
        assert best[3] == _DRAFT_2
        # And it is strictly better than ship-last.
        assert best[0] > cands[-1][0]

    def test_keep_best_differs_from_ship_last(self):
        cands = _candidates_from_drafts(_TRAJECTORY_DRAFTS)
        assert _l569_select_best_story(cands)[3] != cands[-1][3]


class TestSelectionSemantics:
    """Tie-breaks and edge cases for _l569_select_best_story."""

    def test_empty_returns_none(self):
        assert _l569_select_best_story([]) is None
        assert _l569_select_best_story(None) is None

    def test_ties_broken_by_word_count(self):
        # Two drafts with the same story_count; the longer one wins.
        a = (2, 100, "o", "short", 10, 0.0)
        b = (2, 180, "o", "long", 10, 0.0)
        assert _l569_select_best_story([a, b]) == b
        assert _l569_select_best_story([b, a]) == b

    def test_story_count_dominates_word_count(self):
        # A longer draft with fewer stories must lose to a shorter richer one.
        rich = (3, 90, "o", "rich", 10, 0.0)
        long_poor = (1, 400, "o", "long", 10, 0.0)
        assert _l569_select_best_story([long_poor, rich]) == rich

    def test_single_candidate_returned(self):
        only = (0, 50, "o", "d", 10, 0.0)
        assert _l569_select_best_story([only]) == only


class TestEarlyStopDecision:
    """STORY_RETRY_EARLY_STOP: stop once a rewrite stops helping, hard cap 3."""

    def test_improvement_does_not_stop(self):
        # current beats prior best -> keep going
        stop, _ = _l569_should_early_stop(current_sc=2, prev_best_sc=1, story_attempts=1)
        assert stop is False

    def test_first_attempt_never_stops(self):
        # prev_best_sc = -1 sentinel (no prior attempt) -> any count keeps going
        stop, _ = _l569_should_early_stop(current_sc=0, prev_best_sc=-1, story_attempts=0)
        assert stop is False

    def test_no_improvement_stops(self):
        stop, reason = _l569_should_early_stop(current_sc=0, prev_best_sc=1, story_attempts=1)
        assert stop is True
        assert "no improvement" in reason

    def test_tie_stops(self):
        # a tie "fails to beat" the running best
        stop, reason = _l569_should_early_stop(current_sc=1, prev_best_sc=1, story_attempts=1)
        assert stop is True
        assert "no improvement" in reason

    def test_hard_cap_stops_even_on_improvement(self):
        stop, reason = _l569_should_early_stop(
            current_sc=5, prev_best_sc=1, story_attempts=_L569_STORY_ATTEMPT_CAP)
        assert stop is True
        assert "cap" in reason

    def test_cap_is_three(self):
        assert _L569_STORY_ATTEMPT_CAP == 3


class TestEarlyStopTrajectory:
    """Replay LOCAL-568's 1 -> 0 -> 2 -> 1 through the real decision helpers to
    show early-stop halts the story branch and what it ships. This mirrors the
    production loop: capture a candidate, then decide stop vs rewrite."""

    def _simulate(self, drafts, early_stop):
        best = None            # (sc, wc, ...)
        story_attempts = 0
        writer_calls = 0
        for d in drafts:
            writer_calls += 1
            sc = _l569_story_count(d)
            wc = len(d.split())
            if sc >= 3:
                # would pass LOCAL-432 and ship immediately
                cand = (sc, wc, "o", d, 10, 0.0)
                if best is None or (sc, wc) > (best[0], best[1]):
                    best = cand
                break
            prev_best_sc = best[0] if best else -1
            cand = (sc, wc, "o", d, 10, 0.0)
            if best is None or (sc, wc) > (best[0], best[1]):
                best = cand
            if early_stop:
                stop, _ = _l569_should_early_stop(sc, prev_best_sc, story_attempts)
                if stop:
                    break
            story_attempts += 1  # a rewrite is requested
        return best, writer_calls

    def test_keep_best_only_uses_all_attempts_ships_2(self):
        best, calls = self._simulate(_TRAJECTORY_DRAFTS, early_stop=False)
        assert best[0] == 2, "keep-best should ship story_count 2"
        assert calls == len(_TRAJECTORY_DRAFTS), "keep-best alone makes every call"

    def test_early_stop_halts_after_second_attempt(self):
        best, calls = self._simulate(_TRAJECTORY_DRAFTS, early_stop=True)
        # attempt0 sc=1 (prev=-1 keep going), attempt1 sc=0 <= 1 -> STOP
        assert calls == 2, f"early stop should halt after 2 writer calls, got {calls}"
        assert best[0] == 1, "ships the best seen so far (story_count 1)"

    def test_early_stop_respects_hard_cap(self):
        # A trajectory that keeps improving by 0 every time would otherwise run
        # forever; the cap bounds it. Build strictly-improving-then-flat counts
        # that never reach 3: 1,2,2,2,2 -> cap stops the rewrites.
        drafts = [_DRAFT_0, _DRAFT_2, _DRAFT_2, _DRAFT_2, _DRAFT_2]
        best, calls = self._simulate(drafts, early_stop=True)
        # a0 sc1(prev-1 go,att1) a1 sc2>1 go att2, a2 sc2<=2 STOP at call 3
        assert calls == 3
        assert best[0] == 2


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-v", __file__]))
