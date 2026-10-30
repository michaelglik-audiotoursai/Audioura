"""repro_local826b.py — reproduce the cached-path matcher failure (LOCAL-826B).

Loads the EXACT cached rows copied read-only from the live DB:
  * tests/fixtures/local826b/q23402_venue_corpus.json   (stale snapshot:
    canonical_titles_json + sparql_works_json written by an OLD miner)
  * tests/fixtures/local826b/q23402_venue_works_cache.json (fresh LOCAL-810
    cache: 300 works, source=sparql)

It runs the REAL matcher (venue_resolver.build_dynamic_aliases +
story_miner.build_bilingual_map_from_sparql + match_candidate_to_canonical)
against BOTH matchable sets, exactly as the generator's cache-HIT path does.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import story_miner as sm
from story_miner import match_candidate_to_canonical
from venue_resolver import build_dynamic_aliases, build_canonical_titles_from_works

FIX = os.path.join(os.path.dirname(__file__), "tests", "fixtures", "local826b")

FAMOUS = [
    "L'Origine du monde",
    "Olympia",
    "La Nuit étoilée",
    "La Naissance de Vénus",
]
CHURCH = "L'Église d'Auvers-sur-Oise"


def _load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


def _install_and_match(works, canonical_titles, label):
    sm.CANONICAL_ALIASES = build_dynamic_aliases(works)
    sm.build_bilingual_map_from_sparql(works)
    print(f"\n=== {label} ===")
    print(f"  canonical_titles: {len(canonical_titles)}  |  works: {len(works)}  "
          f"|  aliases: {len(sm.CANONICAL_ALIASES)}")
    verified, dropped = [], []
    for cand in FAMOUS:
        m = match_candidate_to_canonical(cand, canonical_titles, corpus="")
        if m:
            verified.append((cand, m[0]))
            print(f"  [D1v2] VERIFIED '{cand}' -> canonical: '{m[0]}'")
        else:
            dropped.append(cand)
            print(f"  [D1v2] DROPPED '{cand}' -- no canonical title match")
    ch = match_candidate_to_canonical(CHURCH, canonical_titles, corpus="")
    if ch:
        tag = "  <-- WRONG ACCEPT (Chaumes)" if "chaumes" in ch[0].lower() else ""
        print(f"  [D1v2] '{CHURCH}' -> '{ch[0]}'{tag}")
    else:
        print(f"  [D1v2] '{CHURCH}' -> (no match)")
    return verified, dropped, ch


def main():
    corpus_row = _load("q23402_venue_corpus.json")
    works_row = _load("q23402_venue_works_cache.json")

    stale_titles = set(corpus_row["canonical_titles"])
    stale_works = corpus_row["sparql_works"] or []
    _install_and_match(stale_works, stale_titles,
                       "A) STALE venue_corpus snapshot (today's cache-HIT path)")

    fresh_works = works_row["works"] or []
    fresh_titles = build_canonical_titles_from_works(fresh_works)
    _install_and_match(fresh_works, fresh_titles,
                       "B) FRESH venue_works_cache (refreshed corpus would use this)")


if __name__ == "__main__":
    main()
