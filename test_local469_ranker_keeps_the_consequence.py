#!/usr/bin/env python3
"""test_local469_ranker_keeps_the_consequence.py — the ranker must not discard stakes.

Measured 2026-08-18 on MFA Unbound stop 2, round 2 of the iteration chart:

    stakes_score  mean 0.0 of 15   — 0% of the term, on 8 of 8 stories

The detector is not broken; three control sentences fire it. The stories genuinely
carry no consequence. Tracing that back one stage:

    retrieved (raw)                  7 of 80 snippets carry a stakes marker
    survived the ranker (kept)       2 of 20

and the single best one never reached the writer:

    "Moses and Monotheism was the last major work, and it was the most reckless."

`score_snippet` scores a named person (+3), a verb of consequence (+3), a date (+2),
a place (+1) and production facts (+3) — but **nothing for stakes**: the contrast
and finality markers (`only`, `never`, `the last`, `unfinished`, `despite`,
`destroyed`) that `evaluate_story` then measures the story on. We rank for one thing
and score for another, so the material the score wants is thrown away before the
writer can use it.

`_VERBS_OF_CONSEQUENCE` is a different signal — it matches the ACTION (met, printed,
donated). `_STAKES` matches what the action COST. A story needs both.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from snippet_ranker import score_snippet, rank_and_cap_snippets   # noqa: E402
from story_opportunity_scan import _STAKES                        # noqa: E402


def snip(text, tier='tier1'):
    return {'title': '', 'snippet': text, 'url': 'https://example.org/x', 'tier': tier}


# The real snippet the ranker discarded, verbatim from the round-2 run.
THE_DISCARDED = ("Moses and Monotheism was the last major work, and it was the "
                 "most reckless. Freud argued that Moses was not a Hebrew.")

# Matched pair: same people, same date, same shape — one has a consequence.
NEUTRAL = ("Salvador Dalí met Sigmund Freud in London in 1938 at a house in "
           "Hampstead, and made a portrait study.")
WITH_STAKES = ("Salvador Dalí met Sigmund Freud in London in 1938, the only "
               "time the two ever met, and Freud never saw the portrait.")


class TestStakesAreScored:

    def test_the_fixtures_actually_differ_in_stakes(self):
        """Guard: if the detector cannot separate these, the rest is void."""
        assert not _STAKES.search(NEUTRAL), NEUTRAL
        assert _STAKES.search(WITH_STAKES), WITH_STAKES
        assert _STAKES.search(THE_DISCARDED), THE_DISCARDED
        print("  ✅ fixtures differ: neutral has no stakes, the other two do")

    def test_a_consequence_outranks_the_same_fact_without_one(self):
        a = score_snippet(snip(NEUTRAL), artist='Salvador Dalí')
        b = score_snippet(snip(WITH_STAKES), artist='Salvador Dalí')
        assert b > a, (f"stakes bought nothing: neutral={a} with_stakes={b} — "
                       f"this is the LOCAL-469 defect")
        print(f"  ✅ with-stakes {b} > neutral {a}")

    def test_the_discarded_snippet_scores_above_zero(self):
        s = score_snippet(snip(THE_DISCARDED), artist='Salvador Dalí')
        assert s > 0, f"the best consequence in the corpus scored {s}"
        print(f"  ✅ the discarded snippet scores {s}")

    def test_it_survives_the_cap_against_neutral_filler(self):
        """The end-to-end claim: it must reach the writer, not just score well."""
        pool = [snip(NEUTRAL + f' Variant {i}.') for i in range(9)]
        pool.append(snip(THE_DISCARDED))
        kept, _ = rank_and_cap_snippets(pool, 'Salvador Dalí', cap=5,
                                        work_title='Moses and Monotheism')
        texts = ' '.join(k.get('snippet', '') for k in kept)
        assert 'most reckless' in texts, (
            "the consequence snippet was capped out by neutral filler")
        print(f"  ✅ survives the cap ({len(kept)} kept)")


class TestNothingElseMoved:
    """Standing check D242 #1 — the fix must be able to be wrong."""

    def test_biography_only_is_still_rejected(self):
        bio = snip("Salvador Dalí was a Spanish surrealist painter born in "
                   "Figueres in 1904. He is known for melting clocks.")
        assert score_snippet(bio, artist='Salvador Dalí') == -999
        print("  ✅ biography-only still hard-rejected")

    def test_stakes_alone_do_not_rescue_a_biography(self):
        """A stakes word must not become a loophole through the hard reject."""
        bio = snip("Salvador Dalí was a Spanish surrealist painter, the only "
                   "child born in Figueres in 1904, and never left Spain.")
        assert score_snippet(bio, artist='Salvador Dalí') == -999
        print("  ✅ stakes do not defeat the biography reject")

    def test_empty_snippet_still_rejected(self):
        assert score_snippet(snip(''), artist='X') == -999
        print("  ✅ empty snippet still rejected")


def run_all():
    passed = failed = total = 0
    for cls in (TestStakesAreScored, TestNothingElseMoved):
        print(f"\n{'=' * 62}\n  {cls.__name__}\n{'=' * 62}")
        inst = cls()
        for name in sorted(dir(inst)):
            if not name.startswith('test_'):
                continue
            total += 1
            try:
                getattr(inst, name)()
                passed += 1
            except AssertionError as e:
                failed += 1
                print(f"  ❌ {name}: {e}")
            except Exception as e:
                failed += 1
                print(f"  ❌ {name}: EXCEPTION: {type(e).__name__}: {e}")
    print(f"\n{'=' * 62}\n  RESULTS: {passed}/{total} passed, {failed} failed\n{'=' * 62}")
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(run_all())
