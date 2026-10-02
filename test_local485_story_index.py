#!/usr/bin/env python3
"""test_local485_story_index.py — Michael's step 5, tested by running it.

`apply_story_index` lives at module scope precisely so this suite can call it
with no key, no DB and no network (D421). Every assertion here exercises real
code; none greps the source, which is the defect D418 and D421 both bounced.

The load-bearing assertion is section [2]: **the pass cannot change a tour.**
That is what makes it safe to land first, ahead of the other six steps, and it
is the one property that must never quietly stop being true.

Run: python3 test_local485_story_index.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from story_index_pass import (  # noqa: E402
    apply_story_index, build_index_corpus, format_index_report,
    STORY_INDEX_DISABLED_ENV,
)

PASSED, FAILED = [], []


def check(label, got, want):
    if got == want:
        PASSED.append(label); print(f"  ✅ {label}")
    else:
        FAILED.append(f"{label} (got {got!r}, want {want!r})")
        print(f"  ❌ {label} — got {got!r}, want {want!r}")


RICH = ("In 1974, Salvador Dalí met the publisher Louis Broder in Paris. "
        "Broder had spent three years persuading him, and Dalí finally agreed "
        "to a suite of twelve drypoints on vellum. The edition ran to eighty "
        "copies, and Mourlot Frères printed every sheet by hand.")
THIN = "This work is displayed in the gallery. It is worth seeing."


def _pois():
    return [{'name': 'Rich stop', 'description': RICH},
            {'name': 'Thin stop', 'description': THIN},
            {'name': 'Placeholder', 'description': '[no description generated]'},
            {'name': 'Empty', 'description': ''}]


def fake_evaluator(text, corpus=''):
    """Deterministic stand-in. Tests the pass's logic, not the scorer's tuning.

    Asserting a specific index from the real scorer would go red every time the
    scorer is legitimately retuned — which is how a suite ends up deleted rather
    than fixed. The real scorer gets its own section below.
    """
    n = len(text.split())
    return {'valuation_index': min(100, n), 'historic': 10, 'detail': 20, 'social': 30}


def test_scores_and_skips():
    print("\n[1] scores real prose, skips placeholders and blanks")
    pois = _pois()
    stats = apply_story_index(pois, corpus='', evaluator=fake_evaluator)
    check("two stops scored", stats['scored'], 2)
    check("placeholder and empty skipped", stats['skipped'], 2)
    check("index written onto the rich POI", '_story_index' in pois[0], True)
    check("axes written onto the rich POI", '_story_axes' in pois[0], True)
    check("placeholder POI left unscored", '_story_index' in pois[2], False)
    check("weakest is the thin stop", stats['weakest'][0], 'Thin stop')


def test_pass_cannot_change_a_tour():
    """The property that makes this safe to land first. Do not let it lapse."""
    print("\n[2] the pass is incapable of editing a tour")
    pois = _pois()
    before = [p.get('description') for p in pois]
    apply_story_index(pois, corpus='', evaluator=fake_evaluator)
    after = [p.get('description') for p in pois]
    check("every description byte-identical after scoring", after, before)
    check("no POI was added or removed", len(pois), 4)


def test_disable_flag():
    print("\n[3] the env flag disables it, like every other gate in the chain")
    os.environ[STORY_INDEX_DISABLED_ENV] = '1'
    try:
        pois = _pois()
        stats = apply_story_index(pois, corpus='', evaluator=fake_evaluator)
        check("reports disabled", stats['disabled'], True)
        check("nothing scored", stats['scored'], 0)
        check("no index written", '_story_index' in pois[0], False)
    finally:
        del os.environ[STORY_INDEX_DISABLED_ENV]
    stats = apply_story_index(_pois(), corpus='', evaluator=fake_evaluator)
    check("re-enabled when the flag is cleared", stats['scored'], 2)


def test_a_failing_evaluator_cannot_break_generation():
    print("\n[4] a broken scorer degrades to a skip, never an exception")
    def boom(text, corpus=''):
        raise RuntimeError("scorer exploded")
    pois = _pois()
    stats = apply_story_index(pois, corpus='', evaluator=boom)
    check("all stops skipped", stats['scored'], 0)
    check("descriptions still intact", pois[0]['description'], RICH)


def test_corpus_builder():
    print("\n[5] the grounding corpus is assembled from what we already paid for")
    class FakeChecklist:
        page_text = "Salvador Dalí and Louis Broder are named on the museum page."
    corpus = build_index_corpus(
        FakeChecklist(),
        {'Rich stop': {'passages': ['Mourlot Frères printed the sheets.']}})
    check("includes the exhibition page", 'Louis Broder' in corpus, True)
    check("includes the stop corpus passages", 'Mourlot' in corpus, True)
    check("empty inputs give an empty corpus", build_index_corpus(None, {}), '')


def test_real_scorer_separates_rich_from_thin():
    """The real `evaluate_story`, on the only claim that must hold: ordering.

    Not an absolute threshold — those go stale when the scorer is retuned, and a
    stale threshold is how a suite stops being run. Rich prose must simply score
    above catalogue filler.
    """
    print("\n[6] the real scorer ranks rich prose above filler")
    pois = _pois()
    stats = apply_story_index(pois, corpus=RICH)
    check("both real stops scored", stats['scored'], 2)
    rich_idx = pois[0]['_story_index']
    thin_idx = pois[1]['_story_index']
    print(f"     (rich={rich_idx}, thin={thin_idx})")
    check("rich scores above thin", rich_idx > thin_idx, True)
    check("report renders without error", 'index mean' in format_index_report(stats), True)


def test_wired_into_production():
    """A grep — and it is honest about being one.

    D242 check 2 says grep for a production importer before believing a module
    does anything. This asserts only the import edge, which greps CAN establish;
    every behavioural claim above is made by running the code.
    """
    print("\n[7] production imports the pass (the edge greps can prove)")
    src = open(os.path.join(HERE, 'generate_tour_text.py'), encoding='utf-8').read()
    check("generate_tour_text imports story_index_pass",
          'from story_index_pass import' in src, True)
    check("and calls apply_story_index", 'apply_story_index(' in src, True)


def main():
    print("=" * 62)
    print("  LOCAL-485 — step 5: the story valuation index, wired")
    print("=" * 62)
    for t in (test_scores_and_skips, test_pass_cannot_change_a_tour,
              test_disable_flag, test_a_failing_evaluator_cannot_break_generation,
              test_corpus_builder, test_real_scorer_separates_rich_from_thin,
              test_wired_into_production):
        t()
    print("\n" + "=" * 62)
    print(f"  RESULTS: {len(PASSED)}/{len(PASSED) + len(FAILED)} passed, {len(FAILED)} failed")
    for f in FAILED:
        print(f"    FAILED: {f}")
    print("=" * 62)
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
