"""
LOCAL-644 parity harness — structured stops THROUGH the STOP-POOL delivery.
===========================================================================
LOCAL-643 rendered stops from records only on the normal path. In the shared
stack, fresh tours go through stop_pool_orchestrator → assemble_building_tour,
which re-renders from parsed TEXT, and reuse tours assemble pooled units — so
STRUCTURED_STOPS=1 had NO effect on any pool/reuse delivery (R14 A/B: "path =
structured" 0 times).

This test proves the fix OFFLINE — no DB, no network, no LLM, ZERO paid calls:

  * fresh-via-pool: the generator's Stop records (built here from the stored tour
    via stop_records.tour_to_record_dicts, standing in for the generator's own
    _LAST_STRUCTURED_RECORDS) are carried into assemble_building_tour as the new
    stops' records; the body is rendered via stop_records.render_tour.

  * reuse-via-pool: the stored tour is parsed into audio-independent pool units
    (stop_pool_store.parse_delivered_stops), each carrying a derived structured
    record (stop_pool_store._record_from_unit); assemble_building_tour renders
    them via the record path.

For every stored tour (485, 488, 495, 531, 553–556) and for the structured path
we assert the structure holds (D640: each stop's own orientation, no glued
header, no duplicate block, no bare empty label) and run the
.continuous_dev/bench/detectors.py structural checks on the rendered text —
expecting 0 structural failures.

Run: python3 -m pytest test_local644_pool_structured.py -q
     STRUCTURED_STOPS=1 python3 -m pytest test_local644_pool_structured.py -q
"""
import os
import re
import unittest

import stop_records as sr
import stop_pool_store as store
import stop_pool_assembly as asm

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "tests", "fixtures")
TOURS = ["485", "488", "495", "531", "553", "554", "555", "556"]

_STOP_HEADER_RE = re.compile(r'^Stop\s+(\d+):\s*(.+?)\s*$')
_FIELD_RE = re.compile(
    r'^(Address|Coordinates|Type/Specialty|Specific Examples|'
    r'Operational Details|Museum Information|Orientation|Directions):')


# ── Detector checks (ported from .continuous_dev/bench/detectors.py) ──────────
# The live detectors read tour_content from the DB; here we run the SAME
# structural checks directly on rendered text so the parity proof is fully
# offline. We split them into two groups:
#   RENDERER checks — defects a renderer can create or prevent (glued header,
#     duplicate block, double Orientation, bare empty label, lost/extra stop,
#     restaurant-not-last). These MUST be empty on the structured render.
#   INHERITED checks — artifacts of the stored SOURCE narration (e.g. a blanked
#     quoted title "“ ”" that was already in tour 485). A renderer neither
#     creates nor removes these; the test only requires that the structured
#     render introduces NO NEW inherited failure versus the legacy render.
_RENDERER_CHECKS = {
    "stop_count", "header_glued_to_field", "bare_empty_field",
    "double_orientation", "duplicate_sentence", "restaurant_not_last",
    "raw_label_dup", "markers", "venue_as_stop",
}


def detector_failures(spoken: str, requested: int, venue: str = ""):
    spoken = spoken.split("\nSources:")[0]
    fails = []

    def chk(name, cond, detail=""):
        if cond:
            fails.append((name, detail))

    titles = re.findall(r"(?m)^Stop \d+:\s*(.+)$", spoken)
    chk("stop_count", len(titles) != requested,
        f"{len(titles)} delivered vs {requested} requested")
    chk("venue_as_stop",
        any(venue and (venue.split(',')[0].lower() in x.lower()
                       or x.lower() in venue.lower()) for x in titles), str(titles))
    chk("raw_label_dup",
        bool(re.search(r"(?i)\bopen open\b|admission is (single|standard) ticket", spoken)))
    chk("markers", "<!--" in spoken or "-->" in spoken)
    # Structural duplicate-sentence check (the duplicate-block bug class).
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", spoken) if len(s.strip()) > 40]
    dups = {s for s in sents if sents.count(s) > 1}
    chk("duplicate_sentence", bool(dups), list(dups)[:1])
    chk("restaurant_not_last",
        "restaurant tour" in spoken and not spoken.rstrip().endswith("restaurant tour."))
    chk("empty_title_quotes", bool(re.search(r'"\s+"|\u201c\s*\u201d', spoken)))
    # A header must never share its line with a field label (the flatten bug).
    for line in spoken.split("\n"):
        if _STOP_HEADER_RE.match(line.strip()) and re.search(
                r'\b(Address|Coordinates|Orientation|Directions|'
                r'Type/Specialty|Specific Examples|Operational Details|'
                r'Museum Information):', line):
            chk("header_glued_to_field", True, line[:80])
            break
    # No bare empty field label.
    for line in spoken.split("\n"):
        if re.match(r'^(Address|Coordinates|Directions|Orientation|'
                    r'Type/Specialty|Specific Examples|Operational Details):\s*$',
                    line.strip()):
            chk("bare_empty_field", True, line[:80])
            break
    # At most one Orientation label per stop block.
    for b in re.split(r'(?=^Stop\s+\d+:)', spoken, flags=re.MULTILINE):
        if b.strip().startswith("Stop ") and len(
                re.findall(r'^Orientation:', b, flags=re.MULTILINE)) > 1:
            chk("double_orientation", True, b[:60])
            break
    return fails


def renderer_failures(spoken, requested, venue=""):
    """Only the renderer-affectable structural failures (must be empty)."""
    return [(n, d) for (n, d) in detector_failures(spoken, requested, venue)
            if n in _RENDERER_CHECKS]


def _structure(text):
    sig = []
    cur = None
    for line in text.split("\n"):
        s = line.strip()
        hm = _STOP_HEADER_RE.match(s)
        if hm:
            cur = {"index": int(hm.group(1)), "title": hm.group(2), "labels": []}
            sig.append(cur)
            continue
        fm = _FIELD_RE.match(s)
        if fm and cur is not None:
            cur["labels"].append(fm.group(1))
    return sig


def _load(tid):
    p = os.path.join(FIXTURE_DIR, f"tour_{tid}_r2.txt")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return f.read()


def _header_meta(text):
    """(venue, header_category) parsed from the title block."""
    first = text.split("\n", 1)[0]
    cat = "museum"
    m = re.search(r'^Tour-Category:\s*(.+)$', text, re.M)
    if m:
        cat = m.group(1).strip().lower()
    venue = ""
    mv = re.search(r'Audio Guided Tour:\s*(.+?)(?:\s+-\s+.*)?$', first)
    if mv:
        venue = mv.group(1).strip()
    return venue, cat


def _reuse_units(text):
    """Pool-style audio-independent units with a derived structured record each
    (mirrors stop_pool_store.get_pool_stops after a round-trip through the DB)."""
    parsed = store.parse_delivered_stops(text)
    units = []
    for i, u in enumerate(parsed):
        rec = store._record_from_unit(u, i + 1)
        rec["narration"] = [p.strip() for p in re.split(r'\n\s*\n', u["narration"])
                            if p.strip()]
        rec["orientation"] = ""
        rec["directions"] = ""
        units.append({
            "title": u["title"], "artist": u["artist"], "year": u["year"],
            "narration": u["narration"], "orientation": "",
            "address": u["address"], "coordinates": u["coordinates"],
            "type_specialty": u["type_specialty"],
            "specific_examples": u["specific_examples"],
            "operational_details": u["operational_details"],
            "_stop_record": rec, "_pool_reused": True,
        })
    return units


def _fresh_units(text):
    """New-stop units carrying the generator's OWN records (built here from the
    stored tour via stop_records.tour_to_record_dicts, standing in for the
    generator's _LAST_STRUCTURED_RECORDS)."""
    _title, by_title, _op, _cl = sr.tour_to_record_dicts(text)
    parsed = store.parse_delivered_stops(text)
    units = []
    for s in parsed:
        rec = by_title.get(s["title"])
        units.append({
            "title": s["title"], "artist": s["artist"], "year": s["year"],
            "narration": s["narration"],
            "orientation": (rec or {}).get("orientation", ""),
            "address": s["address"], "coordinates": s["coordinates"],
            "type_specialty": s["type_specialty"],
            "specific_examples": s["specific_examples"],
            "operational_details": s["operational_details"],
            "_stop_record": rec, "_pool_reused": False,
        })
    return units


def _assemble(units, venue, cat, as_new):
    return asm.assemble_building_tour(
        location=venue, tour_type=cat, tour_category=cat,
        header_category=cat, display_category=cat.capitalize(),
        venue_name=venue.split(",")[0],
        new_stops=units if as_new else [],
        pooled_stops=[] if as_new else units,
        overall_orientation=None, sources_block="",
    )


class TestPoolStructuredParity(unittest.TestCase):
    def test_reuse_via_pool_renders_and_no_structural_failures(self):
        for tid in TOURS:
            text = _load(tid)
            if text is None:
                self.skipTest(f"fixture missing: {tid}")
            venue, cat = _header_meta(text)
            units = _reuse_units(text)
            n = len(units)
            self.assertGreaterEqual(n, 1, f"tour {tid}: no units parsed")
            os.environ["STRUCTURED_STOPS"] = "1"
            try:
                res = _assemble(units, venue, cat, as_new=False)
            finally:
                os.environ.pop("STRUCTURED_STOPS", None)
            sig = _structure(res.tour_text)
            self.assertEqual([s["index"] for s in sig], list(range(1, n + 1)),
                             f"tour {tid}: stop indices wrong on reuse")
            # Renderer-structural failures must be empty.
            rf = renderer_failures(res.tour_text, requested=n, venue=venue)
            self.assertEqual(rf, [], f"tour {tid} reuse renderer failures: {rf}")
            # And the structured render adds NO inherited failure beyond legacy.
            os.environ.pop("STRUCTURED_STOPS", None)
            legacy = _assemble(_reuse_units(text), venue, cat, as_new=False)
            new_inherited = (set(n for n, _ in detector_failures(res.tour_text, n, venue))
                             - set(n for n, _ in detector_failures(legacy.tour_text, n, venue)))
            self.assertEqual(new_inherited, set(),
                             f"tour {tid}: structured reuse added failures {new_inherited}")

    def test_fresh_via_pool_renders_and_no_structural_failures(self):
        for tid in TOURS:
            text = _load(tid)
            if text is None:
                self.skipTest(f"fixture missing: {tid}")
            venue, cat = _header_meta(text)
            units = _fresh_units(text)
            n = len(units)
            os.environ["STRUCTURED_STOPS"] = "1"
            try:
                res = _assemble(units, venue, cat, as_new=True)
            finally:
                os.environ.pop("STRUCTURED_STOPS", None)
            sig = _structure(res.tour_text)
            self.assertEqual([s["index"] for s in sig], list(range(1, n + 1)),
                             f"tour {tid}: stop indices wrong on fresh")
            rf = renderer_failures(res.tour_text, requested=n, venue=venue)
            self.assertEqual(rf, [], f"tour {tid} fresh renderer failures: {rf}")

    # Tours whose stored text is already well-formed round-trip byte-identically
    # between the legacy loop and the record renderer. Tours carrying a known
    # flatten/whitespace defect (495 NG; 531/553/554 minor) are NOT byte-identical
    # — the structured path RECOVERS the defect — so for those we assert the
    # structured render is never structurally WORSE than legacy instead.
    CLEAN_IDENTICAL = {"485", "488", "555", "556"}

    def test_legacy_equals_structured_on_clean_tours(self):
        """On already-well-formed tours the structured path is a drop-in: the
        legacy loop and the record renderer produce byte-identical tours."""
        for tid in self.CLEAN_IDENTICAL:
            text = _load(tid)
            if text is None:
                self.skipTest(f"fixture missing: {tid}")
            venue, cat = _header_meta(text)
            os.environ.pop("STRUCTURED_STOPS", None)
            legacy = _assemble(_reuse_units(text), venue, cat, as_new=False).tour_text
            os.environ["STRUCTURED_STOPS"] = "1"
            try:
                structured = _assemble(_reuse_units(text), venue, cat, as_new=False).tour_text
            finally:
                os.environ.pop("STRUCTURED_STOPS", None)
            self.assertEqual(legacy, structured,
                             f"tour {tid}: legacy != structured on a clean tour")

    def test_structured_never_worse_than_legacy(self):
        """For every tour the structured render carries NO renderer-structural
        failure that the legacy render did not already have (and recovers the
        flatten defects, e.g. NG 495, so it is strictly better there)."""
        for tid in TOURS:
            text = _load(tid)
            if text is None:
                self.skipTest(f"fixture missing: {tid}")
            venue, cat = _header_meta(text)
            n = len(_reuse_units(text))
            os.environ.pop("STRUCTURED_STOPS", None)
            legacy = _assemble(_reuse_units(text), venue, cat, as_new=False).tour_text
            os.environ["STRUCTURED_STOPS"] = "1"
            try:
                structured = _assemble(_reuse_units(text), venue, cat, as_new=False).tour_text
            finally:
                os.environ.pop("STRUCTURED_STOPS", None)
            lf = {x for x, _ in renderer_failures(legacy, n, venue)}
            sf = {x for x, _ in renderer_failures(structured, n, venue)}
            self.assertEqual(sf, set(),
                             f"tour {tid}: structured has renderer failures {sf}")
            self.assertTrue(sf.issubset(lf) or sf == set(),
                            f"tour {tid}: structured added failures {sf - lf}")

    def test_each_stop_keeps_its_own_orientation(self):
        """D640: each stop renders with ITS OWN orientation — none migrates."""
        for tid in TOURS:
            text = _load(tid)
            if text is None:
                self.skipTest(f"fixture missing: {tid}")
            venue, cat = _header_meta(text)
            units = _fresh_units(text)
            os.environ["STRUCTURED_STOPS"] = "1"
            try:
                res = _assemble(units, venue, cat, as_new=True).tour_text
            finally:
                os.environ.pop("STRUCTURED_STOPS", None)
            blocks = re.split(r'(?=^Stop\s+\d+:)', res, flags=re.MULTILINE)
            blocks = [b for b in blocks if b.strip().startswith("Stop ")]
            for b, u in zip(blocks, units):
                o = (u["_stop_record"] or {}).get("orientation", "").strip()
                if o and len(o) > 25:
                    self.assertIn(o[:25], b,
                                  f"tour {tid}: a stop's orientation missing/migrated")


if __name__ == "__main__":
    unittest.main(verbosity=2)
