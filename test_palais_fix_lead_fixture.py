"""LEAD verification fixture for PALAIS-FIX hardening (bounce items B1-B3).

Tests the PALAIS-FIX filter logic:
  D1: REJECTED candidates (wrong-venue) must NOT be restored by Fix 1.
  D2: Canonical-renamed works must NOT be re-added as duplicates.

Also retains the original T1-T4 correctness assertions from commit 49c5a9a.
"""

import sys


def _new_poi(name, address="", verified=True):
    poi = {"name": name, "address": address}
    if not verified:
        poi["verified"] = False
    return poi


# ---------- Evidence log simulation (D1v2 results) ----------

def _simulate_d1v2_evidence_log(candidates, verified_pois):
    """Simulate the evidence_log dict that D1v2 produces.
    Each verified work gets status=VERIFIED + canonical_title.
    Each rejected work gets status=REJECTED + reason."""
    log = {}
    verified_names = {p['name'] for p in verified_pois}
    for c in candidates:
        if c['name'] in verified_names:
            log[c['name']] = {"status": "VERIFIED", "canonical_title": c['name'], "snippet": "..."}
        else:
            log[c['name']] = {"status": "REJECTED", "reason": "not_found_at_venue"}
    return log


def pipeline_after_d1v2(candidates, verified, tier, requested_stops, fixed=True,
                        evidence_log=None):
    """Replicates the post-D1v2 flow with PALAIS-FIX filtering:
    [PALAIS-FIX] restore -> R4 cap -> BLOCKER1.

    When evidence_log is provided and fixed=True, the restore step filters out
    REJECTED candidates (D1 fix) and avoids re-adding canonical-renamed works (D2 fix).
    """
    poi_list = list(verified)
    _pre_d1v2_candidates = list(candidates)
    total_stops = requested_stops
    _verification_tier = tier

    # ---- Fix 1 (only in fixed version) — with PALAIS-FIX D1/D2 filtering ----
    if fixed:
        if _verification_tier == 'thin' and len(poi_list) < 3 and len(_pre_d1v2_candidates) >= 3:
            _verified_names = set(p['name'].lower() for p in poi_list)

            # [PALAIS-FIX D1] Also collect canonical titles from evidence_log
            # to avoid restoring REJECTED candidates
            _rejected_names = set()
            _canonical_titles = set()
            if evidence_log:
                for cname, ev in evidence_log.items():
                    if isinstance(ev, dict):
                        if ev.get('status') == 'REJECTED':
                            _rejected_names.add(cname.lower())
                        if ev.get('canonical_title'):
                            _canonical_titles.add(ev['canonical_title'].lower())

            _unverified = []
            for p in _pre_d1v2_candidates:
                pname_lower = p['name'].lower()
                # Skip if already in verified list
                if pname_lower in _verified_names:
                    continue
                # [PALAIS-FIX D1] Skip REJECTED candidates
                if pname_lower in _rejected_names:
                    continue
                # [PALAIS-FIX D2] Skip if name overlaps with a canonical title
                # (prevents duplicates from renames)
                _is_canonical_dup = False
                for ct in _canonical_titles:
                    if ct in pname_lower or pname_lower in ct:
                        _is_canonical_dup = True
                        break
                if _is_canonical_dup:
                    continue
                # Tag as unverified for narration hedging
                p['verified'] = False
                _unverified.append(p)
            poi_list = list(poi_list) + _unverified[:5]

    # ---- R4 cap — verbatim logic ----
    if _verification_tier in ('medium', 'thin'):
        if fixed and _verification_tier == 'thin' and len(poi_list) < 3:
            _thin_cap = min(total_stops, 5)
            total_stops = _thin_cap
        else:
            total_stops = len(poi_list)

    replenish_would_run = len(poi_list) < total_stops

    # ---- BLOCKER1 — verbatim logic ----
    _VENUE_INDICATORS = ('musée', 'museum', 'galerie', 'gallery', 'palais',
                         'villa', 'château', 'castle', 'cathedral', 'church',
                         'basilica', 'temple', 'theatre', 'theater', 'opera',
                         'bibliothèque', 'library', 'institut', 'centre')
    _museum_venue_name = "Musée du Palais Lascaris"
    _venue_norm = _museum_venue_name.lower()
    _suspect_venues = []
    for p in poi_list:
        _pname = p['name'].lower()
        for indicator in _VENUE_INDICATORS:
            if indicator in _pname and _venue_norm not in _pname and _pname not in _venue_norm:
                _suspect_venues.append(p['name'])
                break
    if fixed:
        rejected = len(_suspect_venues) >= max(1, len(poi_list) // 2)
    else:
        rejected = len(_suspect_venues) >= len(poi_list) // 2

    return poi_list, total_stops, rejected, replenish_would_run, _suspect_venues


# ========== Test data ==========

PALAIS_CANDIDATES = [_new_poi(n) for n in [
    "The Annunciation", "The Adoration of the Magi", "The Holy Family",
    "Raquel", "Baroque Ceiling Frescoes", "Tembang Antique Harp",
    "Portrait of a Nobleman",
]]
PALAIS_VERIFIED = [_new_poi("Raquel")]

results = []

# ========== Original T1-T4 correctness tests ==========

# --- T1: pre-fix code zero-rejects the Palais scenario (reproduces bug) ---
pl, ts, rej, rep, sus = pipeline_after_d1v2(PALAIS_CANDIDATES, PALAIS_VERIFIED, 'thin', 6, fixed=False)
results.append(("T1 pre-fix reproduces failure (BLOCKER1 rejects with 0 suspects)",
                rej is True and len(sus) == 0 and ts == 1))

# --- T2: fixed code passes the Palais scenario with 6 stops ---
pl, ts, rej, rep, sus = pipeline_after_d1v2(PALAIS_CANDIDATES, PALAIS_VERIFIED, 'thin', 6, fixed=True)
results.append(("T2 fixed code yields 6 POIs, total_stops=6, BLOCKER1 passes",
                len(pl) == 6 and ts == 6 and rej is False))
results.append(("T2b verified work is first stop", pl[0]['name'] == "Raquel"))

# --- T3: rich/medium tiers unaffected (fix conditions can't fire) ---
med_verified = [_new_poi(f"W{i}") for i in range(4)]
pl_f, ts_f, rej_f, _, _ = pipeline_after_d1v2(PALAIS_CANDIDATES, med_verified, 'medium', 6, fixed=True)
pl_o, ts_o, rej_o, _, _ = pipeline_after_d1v2(PALAIS_CANDIDATES, med_verified, 'medium', 6, fixed=False)
results.append(("T3 medium tier identical before/after fix",
                (len(pl_f), ts_f, rej_f) == (len(pl_o), ts_o, rej_o)))

# --- T4: BLOCKER1 still rejects a genuine city-tour misread (majority suspects) ---
city_pois = [_new_poi(n) for n in ["Musée Matisse", "Villa Masséna", "Opéra de Nice", "Raquel"]]
_, _, rej, _, sus = pipeline_after_d1v2(city_pois, city_pois, 'rich', 4, fixed=True)
results.append(("T4 BLOCKER1 still fires on real city-scatter",
                rej is True and len(sus) >= 2))


# ========== [PALAIS-FIX B3] D1 test: REJECTED candidate NOT restored ==========

d1_evidence = {
    "Raquel": {"status": "VERIFIED", "canonical_title": "Raquel", "snippet": "..."},
    "The Annunciation": {"status": "REJECTED", "reason": "not_found_at_venue"},
    "The Adoration of the Magi": {"status": "REJECTED", "reason": "not_found_at_venue"},
    "The Holy Family": {"status": "REJECTED", "reason": "not_found_at_venue"},
    "Baroque Ceiling Frescoes": {"status": "VERIFIED", "canonical_title": "Baroque Ceiling Frescoes", "snippet": "..."},
    "Tembang Antique Harp": {"status": "REJECTED", "reason": "located_elsewhere"},
    "Portrait of a Nobleman": {"status": "REJECTED", "reason": "not_found_at_venue"},
}
# Only Raquel verified by D1v2
d1_verified = [_new_poi("Raquel")]
d1_candidates = PALAIS_CANDIDATES[:]

pl, ts, rej, rep, sus = pipeline_after_d1v2(
    d1_candidates, d1_verified, 'thin', 6, fixed=True, evidence_log=d1_evidence
)
d1_restored_names = [p['name'] for p in pl]

# REJECTED works should NOT appear in restored list
results.append(("D1 REJECTED 'The Annunciation' is NOT restored",
                "The Annunciation" not in d1_restored_names))
results.append(("D1 REJECTED 'Tembang Antique Harp' is NOT restored",
                "Tembang Antique Harp" not in d1_restored_names))
# Verified work should still be there
results.append(("D1 VERIFIED 'Raquel' remains",
                "Raquel" in d1_restored_names))


# ========== [PALAIS-FIX B3] D2 test: canonical rename NOT re-added ==========

# Scenario: D1v2 verified "The Raquel Portrait" and renamed it to canonical "Raquel"
d2_evidence = {
    "The Raquel Portrait": {"status": "VERIFIED", "canonical_title": "Raquel", "snippet": "..."},
    "The Annunciation": {"status": "VERIFIED", "canonical_title": "The Annunciation", "snippet": "..."},
    "The Holy Family": {"status": "VERIFIED", "canonical_title": "The Holy Family", "snippet": "..."},
}
# Verified list uses canonical name "Raquel" (post-rename)
d2_verified = [_new_poi("Raquel")]
# Candidates still have original name "The Raquel Portrait"
d2_candidates = [_new_poi("The Raquel Portrait"), _new_poi("The Annunciation"), _new_poi("The Holy Family")]

pl, ts, rej, rep, sus = pipeline_after_d1v2(
    d2_candidates, d2_verified, 'thin', 6, fixed=True, evidence_log=d2_evidence
)
d2_names = [p['name'] for p in pl]

# "The Raquel Portrait" should NOT be re-added because its canonical title "Raquel"
# overlaps with the already-verified "Raquel"
results.append(("D2 canonical-renamed 'The Raquel Portrait' is NOT re-added alongside 'Raquel'",
                "The Raquel Portrait" not in d2_names))
results.append(("D2 canonical 'Raquel' still present",
                "Raquel" in d2_names))
# Non-conflicting verified candidates can still be restored (they're VERIFIED, not REJECTED)
# Since The Annunciation and The Holy Family are VERIFIED in evidence_log, they won't be
# filtered by D1 (only REJECTED are filtered). They may or may not appear depending on
# whether they match verified_names. Let's verify the list is sane.
results.append(("D2 total POI count is reasonable (1-3)",
                1 <= len(pl) <= 3))


# ========== B1 verified=False propagation check ==========

# When Fix 1 restores unverified candidates, they should be tagged verified=False
b1_evidence = {
    "Raquel": {"status": "VERIFIED", "canonical_title": "Raquel", "snippet": "..."},
    "Baroque Ceiling Frescoes": {"status": "REJECTED", "reason": "not_found_at_venue"},
    "Portrait of a Nobleman": {"status": "REJECTED", "reason": "not_found_at_venue"},
}
# Only candidates that are NOT REJECTED and NOT already verified can be restored
b1_candidates = [_new_poi("Raquel"), _new_poi("Safe Work A"), _new_poi("Safe Work B")]
b1_evidence_ext = dict(b1_evidence)
b1_evidence_ext["Safe Work A"] = {"status": "UNRESOLVED", "canonical_title": None}
b1_evidence_ext["Safe Work B"] = {"status": "UNRESOLVED", "canonical_title": None}
b1_verified = [_new_poi("Raquel")]

pl, ts, rej, rep, sus = pipeline_after_d1v2(
    b1_candidates, b1_verified, 'thin', 6, fixed=True, evidence_log=b1_evidence_ext
)
# Restored works should have verified=False
b1_unverified_stops = [p for p in pl if p.get('verified') == False]
results.append(("B1 restored stops are tagged verified=False",
                len(b1_unverified_stops) >= 1))
# Original verified stop should NOT have verified=False
b1_raquel = next((p for p in pl if p['name'] == "Raquel"), None)
results.append(("B1 verified 'Raquel' does NOT have verified=False",
                b1_raquel is not None and b1_raquel.get('verified', True) is True))


# ========== Print results ==========

print("=" * 78)
print("PALAIS-FIX LEAD FIXTURE — B3 hardening tests")
print("=" * 78)
fails = 0
for name, ok in results:
    status = "PASS" if ok else "FAIL"
    print(f"  {status}  {name}")
    if not ok:
        fails += 1
print("=" * 78)
print(f"{len(results) - fails}/{len(results)} assertions hold")
if fails > 0:
    print(f"  *** {fails} FAILURE(S) ***")
    sys.exit(1)
else:
    print("  All tests passed.")
    sys.exit(0)
