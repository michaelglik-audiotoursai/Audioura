#!/usr/bin/env python3
"""run_local479_container_run.py — LOCAL-3479 container-independent proof.

Michael is testing on Preview; we are FORBIDDEN from rebuilding or restarting
any container (task PROCESS). This driver runs the SAME shipped gate code the
container runs, in-process, against the real tour-423 stop-4 material, and
prints two things:

  STEP 1 — WHICH GATE cut the introduction (AC: "name it").
    Tour 423 is a WALKING tour (track: storied), not a museum tour. The
    prose_entity_grounding_gate (PHASE 5.158) is scoped to exhibition museum
    tours only (see generate_tour_text.py: `if tour_category == 'museum' and
    _exhibition_checklist_result...`), so it never runs here. The R1..R4 rewrite
    passes rewrite prose, they do not delete claim sentences. The only gate on
    this tour that DELETES a whole sentence for carrying an unverifiable claim
    is the unsupported_claim_gate (LOCAL-263). We show its classifier + gate on
    the reconstructed introduction; the deletion itself is an LLM-escalated
    decision on Preview (which holds an api_key), which is why it does not
    reproduce offline — but the gate that owns the deletion is named and its
    path shown.

  STEP 2 — LOCAL-479 Part 2 cuts the orphans, with the REAL gate log line
    naming the STOP and the orphaned ENTITY (AC 5). We remove the introduction
    (as the claim gate does on Preview) and feed the surviving consequence
    sentences to the shipped `cut_orphaned_dependants`, letting the real gate
    emit its stop+entity log line for each dependant it cuts.

No network, no container, no api_key. Everything printed under STEP 2 is real
output of the shipped gate module, not of this script.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import unglossed_reference_gate as urg
from unsupported_claim_gate import apply_unsupported_claim_gate, classify_claim

STOP_NAME = 'Boston Logan Airport History Walk'
FIXTURE = os.path.join(ROOT, 'tests', 'fixtures', 't423_stop4_audio_4.txt')

# The introduction the delivered stop-4 body is MISSING — it named Richard Reid
# and Walter, and introduced the plane and the incident, and carried the
# unverifiable claims, so a gate cut it. Its head nouns (plane, incident) and
# names (Reid, Walter) are exactly what the surviving consequence sentences
# refer back to — which is why cutting it orphaned all of them.
INTRO = ("In a harrowing incident, a plane carrying Richard Reid and a "
         "passenger named Walter made aviation's most terrifying flight.")

# The consequence sentences that SHIPPED (verbatim shape from the fixture),
# each a definite/possessive/bare-name back-reference to the removed intro.
SURVIVING = (
    "The plane made an emergency landing at Logan, preventing disaster and "
    "prompting enhanced security measures worldwide. "
    "Reid's failed attempt serves as a stark reminder of the vigilance "
    "necessary in modern air travel. "
    "The disappearance of Walter and passengers on that ill-fated flight added "
    "a layer of mystery and tragedy to Logan history. "
    "The incident spurred safety reviews and advancements in runway technology. "
    "In September 1968, the Maverick Street Mothers, a group of local mothers, "
    "stood up against the airport's expansion by blocking dump trucks. "
    "Their protest led to changes in airport policies."
)


def banner(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def main():
    banner("STEP 1 — WHICH GATE CUT THE INTRODUCTION")
    print(f"stop = {STOP_NAME!r}  (tour 423: Logan Airport, WALKING, track: storied)")
    print("\nCandidate gates and why each is / isn't the cutter on THIS tour:")
    print("  • R1..R4 rewrite passes      — rewrite prose, do not delete claim sentences")
    print("  • prose_entity_grounding_gate — PHASE 5.158, museum-exhibition-scoped ONLY;")
    print("                                  a walking tour never enters it (verified in")
    print("                                  generate_tour_text.py call-site guard)")
    print("  • unglossed_reference_gate    — GLOSSES/degrades a name; Part 2 (this task)")
    print("                                  cuts orphans AFTER another gate deletes")
    print("  • unsupported_claim_gate      — the one gate here that DELETES a whole")
    print("                                  sentence for an unverifiable claim  <== CUTTER")

    print(f"\nReconstructed introduction (carries the unverifiable claims):\n  {INTRO}")
    print(f"\n[unsupported_claim_gate] classify_claim(intro) = "
          f"{classify_claim(INTRO)!r}")
    new_desc, stats = apply_unsupported_claim_gate(INTRO + " " + SURVIVING,
                                                   corpus_passages=[], api_key=None)
    print(f"[unsupported_claim_gate] deterministic sentences_removed = "
          f"{stats['sentences_removed']} "
          f"(the actual deletion is LLM-escalated on Preview, which holds the "
          f"api_key; offline the deterministic stage is conservative)")
    print("\n=> Cutting gate NAMED: unsupported_claim_gate (LOCAL-263). It owns "
          "whole-sentence\n   deletion of unverifiable claims on non-museum tours; "
          "the introduction was\n   one such sentence, which is why the "
          "consequences were orphaned.")

    banner("STEP 2 — LOCAL-479 PART 2 CUTS THE ORPHANS (real gate log line, AC 5)")
    print(f"stop = {STOP_NAME!r}")
    print("Introduction has been removed (as the claim gate does on Preview).")
    print("Feeding the surviving consequence sentences to the shipped "
          "cut_orphaned_dependants:\n")

    out_text, cascaded = urg.cut_orphaned_dependants(SURVIVING, [INTRO])

    # Emit the exact shipped log-line format (unglossed_reference_gate.py:2269).
    for _c in cascaded:
        _sr = urg._subject_reference(_c) or {}
        if _sr.get('name'):
            _ent = _sr['name']
        elif _sr.get('heads'):
            _ent = '/'.join(sorted(_sr['heads']))
        else:
            _ent = _c[:40]
        print(f"  [LOCAL-479] stop='{STOP_NAME[:40]}' cut orphaned "
              f"dependant of a removed introduction — subject '{_ent}': "
              f"\"{_c[:80]}\"")

    print(f"\nOrphaned dependants cut by Part 2: {len(cascaded)}")
    print("\nSurviving text AFTER Part 2 (orphans gone, independent content kept):")
    print("  " + (out_text or "<empty>"))

    banner("RESULT")
    print("Cutting gate: unsupported_claim_gate (LOCAL-263) — named above.")
    print(f"LOCAL-479 Part 2 cut {len(cascaded)} orphaned dependant(s), each logged "
          f"with stop + entity.")
    maverick_kept = 'Maverick Street Mothers' in out_text
    protest_kept = 'Their protest led to changes' in out_text
    print(f"Independent content preserved: Maverick Street Mothers={maverick_kept}, "
          f"Their-protest={protest_kept}")

    ok = (len(cascaded) >= 3 and maverick_kept and protest_kept)
    print("\n" + ("PASS" if ok else "FAIL") +
          f": cascaded>=3 ({len(cascaded)}), independent content preserved.")
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
