#!/usr/bin/env python3
"""test_local473 — two production holes found by the D472 release run.

**A. `extract_role_claims` matched PASSIVE VOICE ONLY**, so the Hogarth Press
fabrication shipped for the fifth time with the gate reporting `0 role claims`:

    "This work was printed by The Hogarth Press."                  -> 1 claim
    "The Hogarth Press ... printed this work, ensuring that ..."   -> 0 claims

This is a false NEGATIVE in a safety gate — the opposite of every other defect
found on 2026-08-18 and the more dangerous direction. Everything else this session
made the pipeline less likely to throw away a true story; this one let a known
fabrication through, and it is the single claim Michael has objected to most.

**B. A figure named in the WORK'S TITLE was read as a collaborator.** The same run
produced:

    [LOCAL-402] 'Moses' died in -1200, cannot have collaboration with in 1974

on a sentence about *Dalí's illustrations for Moses and Monotheism*. Nobody has
ever claimed Dalí collaborated with Moses. The temporal gate exists to catch an
impossible interaction between real contemporaries; a three-thousand-year gap is a
category error, not a factual one, and reporting it as a falsehood is how a gate
throws away a true sentence. Same class as the `World War` / `Maresfield Gardens`
misreadings of D447/D449.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stop_claim_audit import extract_role_claims               # noqa: E402
from temporal_coherence_gate import check_temporal_coherence   # noqa: E402


# Verbatim from TOUR_MFA_RELEASE_20260818_1514.txt, stop 3.
THE_SHIPPED_FABRICATION = (
    "The Hogarth Press, known for its groundbreaking publications, printed this "
    "work, ensuring that the collaboration reached an audience ready for bold "
    "interpretations.")

THE_FALSE_REJECTION = (
    "Dalí's illustrations for Moses and Monotheism, created in 1974, embody an "
    "essential tension between image and text.")


class TestActiveVoiceRoleClaims:
    """Defect A."""

    def test_the_shipped_fabrication_is_detected(self):
        claims = extract_role_claims(THE_SHIPPED_FABRICATION)
        assert claims, "the Hogarth sentence STILL produces no role claim"
        agents = [c['agent'] for c in claims]
        assert any('Hogarth' in a for a in agents), agents
        print(f"  ✅ detected: {claims[0]['role']} -> {claims[0]['agent']}")

    def test_plain_active_voice(self):
        for s in ("Tériade published this book in 1955.",
                  "Mourlot Frères printed the edition.",
                  "Louis Broder commissioned this work."):
            assert extract_role_claims(s), f"no claim from: {s}"
        print("  ✅ plain active voice detected")

    def test_passive_voice_still_works(self):
        assert extract_role_claims("This work was printed by The Hogarth Press.")
        assert extract_role_claims("Published by Tériade in 1955.")
        print("  ✅ passive voice unchanged")

    def test_the_agent_is_not_swallowed_by_the_appositive(self):
        """The clause between agent and verb must not become part of the name."""
        c = extract_role_claims(THE_SHIPPED_FABRICATION)[0]
        assert 'known for' not in c['agent'], f"agent captured the clause: {c['agent']!r}"
        assert len(c['agent']) < 40, c['agent']
        print(f"  ✅ agent is clean: {c['agent']!r}")

    def test_ordinary_prose_is_not_a_role_claim(self):
        """Standing check D242 #1 — this must be able to be wrong."""
        for s in ("Dalí printed his own name on the cover.",
                  "The exhibition published a catalogue of visitor numbers.",
                  "Freud wrote this book late in his career."):
            claims = extract_role_claims(s)
            agents = [c['agent'] for c in claims]
            assert not any(a.strip().lower() in ('the exhibition', 'dalí')
                           for a in agents), f"{s} -> {agents}"
        print("  ✅ ordinary prose does not manufacture role claims")


class TestTitleFiguresAreNotCollaborators:
    """Defect B."""

    def test_the_moses_sentence_survives(self):
        r = check_temporal_coherence(THE_FALSE_REJECTION)
        assert r is None, f"still rejected: {r['reason']}"
        print("  ✅ the Moses sentence survives")

    def test_an_ancient_figure_is_never_an_interaction_partner(self):
        for s in ("Dalí collaborated with Moses in this portfolio.",
                  "The artist met Moses through the text."):
            r = check_temporal_coherence(s)
            assert r is None or 'Moses' not in r['reason'], \
                f"ancient figure treated as a partner: {r}"
        print("  ✅ ancient figures never produce a temporal verdict")

    def test_real_contemporaries_are_still_checked(self):
        """The gate must keep working on the case it exists for."""
        r = check_temporal_coherence(
            "In 1974, Salvador Dalí collaborated with Sigmund Freud on this book.")
        assert r is not None and '1939' in r['reason'], r
        print(f"  ✅ still rejects: {r['reason']}")

    def test_d466_and_d471_still_hold(self):
        gris = ('"Au Soleil du Plafond," created by Juan Gris in collaboration '
                'with Pierre Reverdy, was published in 1955.')
        assert check_temporal_coherence(gris) is None
        near = ('Created in 1974-75, this set captures Dalí\'s fascination with '
                'Freud, whom he met only once in 1938.')
        assert check_temporal_coherence(near) is None
        print("  ✅ D466 and D471 unaffected")


def run_all():
    passed = failed = total = 0
    for cls in (TestActiveVoiceRoleClaims, TestTitleFiguresAreNotCollaborators):
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
