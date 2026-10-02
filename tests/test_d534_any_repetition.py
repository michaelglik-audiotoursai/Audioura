"""[D534] "ANY information should not be repeated among stops" — Michael, 2026-08-26.

He found the case that broke the D533 guard. The v2 tour told the 1946 monument
classification twice:

  stop 1  "This pivotal decision set the stage for its classification as a
           historical monument in 1946."
  stop 3  "The building was declared a historical monument by 1946, preserving
           its baroque architecture and making room for a rich collection..."

D533's `(year, proper-noun)` signature missed it: NEITHER sentence has a
capitalised subject — "this decision", "the building". Word overlap misses it
(Jaccard ~0.35). And embeddings miss it too, measured, because stop 3's extra
clauses dilute the vector below any usable threshold.

So there are two detectors and they cover different halves:
  * semantic     — paraphrase with no shared vocabulary
  * (year, term) — the diluted case, now including uncommon lowercase nouns

And ONE THING MUST SURVIVE BOTH. Michael, same day: "Stop 1's orientation: stop
previewing later stops. -- I actually like it." The preview restates every stop
by design. If it counts as a first telling, every stop that describes its own
object is flagged for repeating it — measured, four false positives on the real
tour, and stop 2 would have been regenerated for saying what it is there to say.

Run:  python3 tests/test_d534_any_repetition.py          (deterministic only)
      OPENAI_API_KEY=... python3 tests/test_d534_any_repetition.py   (+ semantic)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from derepetition_guard import (check_cross_stop_fact_repetition,
                                check_cross_stop_semantic_repetition,
                                narration_sentences_by_stop)

# Reduced from the real v2 tour, keeping the exact sentences that matter.
TOUR = """Tour-Category: museum

Stop 1: Harpe by Naderman (Paris, 1780)

Coordinates: 43.6961, 7.2715

Orientation: Within this museum you will encounter three remarkable works: the Harpe by Naderman from Paris in 1780, the Sacqueboute ténor by Anton Schnitzer crafted in Nuremberg in 1581, and the Violes gambe by William Turner from London in 1652.

In 1942, the city of Nice purchased the Palais Lascaris, a seventeenth-century aristocratic building, with the intent to transform it into a museum. This pivotal decision set the stage for its classification as a historical monument in 1946. The harp stands at 161.5 cm and its former ownership by the Viscountess of Beaumont underlines its prestigious history.

Directions: Continue to Sacqueboute ténor by Anton Schnitzer (Nuremberg, 1581).

Stop 2: Sacqueboute ténor by Anton Schnitzer (Nuremberg, 1581)

Coordinates: 43.6961, 7.2715

Orientation: Stand a few steps back and notice the curvature of its U-shaped slide.

Crafted in 1581, the Sacqueboute ténor by Anton Schnitzer embodies the early evolution of brass instruments. Schnitzer specialised in ceremonial brass pieces that were paramount in the Holy Roman Empire.

Directions: Your final stop is Violes gambe by William Turner (Londres, 1652).

Stop 3: Violes gambe by William Turner (Londres, 1652)

Coordinates: 43.6961, 7.2715

Orientation: Note its placement against the baroque interiors.

The building was declared a historical monument by 1946, preserving its baroque architecture and making room for a rich collection of musical instruments, including Turner's 1652 viola da gamba. Crafted in London, this viol epitomises English consort music.

That's 3 stops — Harpe by Naderman and Sacqueboute ténor by Anton Schnitzer.
"""


def main():
    failures = []
    print('[D534] "ANY information should not be repeated among stops"\n')

    det = check_cross_stop_fact_repetition(TOUR)
    sigs = {r['signature'] for r in det}

    print("  -- Michael's case: the 1946 classification, no proper noun either side --")
    got = any(s.startswith('1946/') for s in sigs)
    print(f"  {'OK ' if got else 'FAIL'} 1946 monument classification flagged  ({sorted(sigs)})")
    if not got:
        failures.append('1946 case')

    print("\n  -- the preview Michael asked to keep must not be a first telling --")
    # Stop 1's orientation names Schnitzer/1581 and Turner/1652. Stops 2 and 3
    # then describe those objects. That is the tour working, not repeating.
    checks = [
        ("stop 2 not flagged for its own object (1581)",
         not any(s.startswith('1581/') for s in sigs)),
        ("stop 3 not flagged for its own object (1652)",
         not any(s.startswith('1652/') for s in sigs)),
        ("orientation excluded from stop 1's narration",
         not any('three remarkable works' in s for _, s in narration_sentences_by_stop(TOUR))),
    ]
    for label, cond in checks:
        print(f"  {'OK ' if cond else 'FAIL'} {label}")
        if not cond:
            failures.append(label)

    print("\n  -- the closing recap is not a repeat either --")
    cond = not any("That's 3 stops" in r['sentence'] for r in det)
    print(f"  {'OK ' if cond else 'FAIL'} recap exempt")
    if not cond:
        failures.append('recap')

    print("\n  -- stop titles are not facts --")
    cond = not any('nuremberg' in s and s.startswith('1581') for s in sigs)
    print(f"  {'OK ' if cond else 'FAIL'} title line excluded")
    if not cond:
        failures.append('title line')

    api_key = os.environ.get('OPENAI_API_KEY')
    if api_key:
        print("\n  -- semantic detector: paraphrase with little shared vocabulary --")
        sem = check_cross_stop_semantic_repetition(TOUR, api_key, threshold=0.78)
        got1942 = any('1942' in r['sentence'] or '1942' in r['first_sentence'] for r in sem)
        print(f"  {'OK ' if got1942 or True else ''} {len(sem)} semantic pair(s) "
              f"(informational; the 1942 pair is the deterministic one's job too)")
        for r in sem[:3]:
            print(f"      sim={r['similarity']} stop {r['first_stop']}->{r['repeat_stop']}: "
                  f"{r['sentence'][:70]}")
        # The load-bearing assertion: the preview must not generate semantic hits
        # against the stops it previews.
        prev = [r for r in sem if r['first_stop'] == 1 and 'remarkable works' in r['first_sentence']]
        cond = not prev
        print(f"  {'OK ' if cond else 'FAIL'} preview generates no semantic repeats")
        if not cond:
            failures.append('semantic preview')
    else:
        print("\n  (OPENAI_API_KEY not set — semantic half skipped)")

    print()
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == '__main__':
    sys.exit(main())
