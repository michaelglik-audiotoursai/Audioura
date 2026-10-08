"""test_local619_real_conclusion.py — LOCAL-619 / LOCAL-619B acceptance tests.

[LOCAL-619B / Michael D634, 2026-10-07] The conclusion is about the TOUR, not a
list of stops: "Naming all stops, especially if there are more than 3, will be
very annoying to the listeners: the conclusion should be about our tour: what are
the common elements in the stops and the theme of the tour."

LOCAL-619 built one conclusion on every path with the count read from the final
text — but it still ENUMERATED ("From X to Y … That's N stops … Along the way …
<stop>: … <stop>: …"). LOCAL-619B replaces that with a THEMATIC conclusion: a
thread/theme sentence, a one-line meaning, an optional SINGLE example, the count
only when correct, and the restaurant offer last. No "From X to Y", no roll-call.

Fixtures are the ACTUAL delivered ``tour_content`` of audio_tours 440 (Boijmans),
441 (Sevilla) and 442 (Rouen) — the LOCAL-618 live tours. Each delivers THREE
stops (one header is glued onto the prior sentence, so the raw line-start count
is 2 until the builder recovers it). The exports live in
tests/fixtures/local619/tour_44*.txt.

The ticket's thematic acceptance criteria, as tests:
  1. NO STOP LIST: at most ONE delivered title appears in the conclusion;
  2. NO "From … to …";
  3. every FACTUAL noun in the conclusion appears in the stops (claim/G4);
  4. the RESTAURANT offer is the last sentence;
  5. the stop COUNT is correct when present.
Plus the still-valid structural contracts: three stops recovered from a glued
header, one conclusion per tour, Sources preserved, idempotency, and a late-gate
drop recomputing the count.

Pure/offline: no DB, no network, no LLM — the builder's deterministic template is
exercised (the LLM path is a separate, injected-``llm_fn`` test below).

Run: python3 -m pytest tests/test_local619_real_conclusion.py -q
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tour_conclusion as tc

try:
    import claim_check
except Exception:  # pragma: no cover
    claim_check = None

_FIX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "local619")

_FIXTURES = {
    440: "Museum Boijmans Van Beuningen",
    441: "Museo de Bellas Artes de Sevilla",
    442: "Musee des Beaux-Arts de Rouen",
}

# A legacy enumerating splice ("That's N stops — …") must never survive.
_SPLICE_RE = re.compile(r"That['\u2019]s\s+\d+\s+stops?\s+[\u2014-]")
_COUNT_RE = re.compile(r"That['\u2019]s\s+(\d+)\s+stops?")
# The thematic opener (the one conclusion sentence). No "From … to …".
_THEMATIC_RE = re.compile(
    r"(?im)^(?:This tour|Across these stops|Across the stops|Taken together|"
    r"Together,? these|What connects|The works on this tour|"
    r"The stops on this tour|On this tour)\b")
_FROM_TO_RE = re.compile(r"\bFrom\s+.+?\s+to\s+.+?,", re.IGNORECASE)
_RESTAURANT_RE = re.compile(r"we can build you a restaurant tour", re.IGNORECASE)


def _load(tid):
    with open(os.path.join(_FIX_DIR, f"tour_{tid}.txt"), encoding="utf-8") as f:
        return f.read()


def _conclusion_only(rebuilt):
    """Return just the conclusion block (thematic opener → end, minus Sources)."""
    body = re.split(r'(?mi)^\s*Sources:', rebuilt)[0]
    m = _THEMATIC_RE.search(body)
    return body[m.start():].strip() if m else ""


def _delivered_titles(rebuilt):
    """Titles of every delivered ``Stop N:`` header in the rebuilt tour."""
    out = []
    for m in re.finditer(r'(?m)^Stop\s+\d+:\s*(.+?)\s*$', rebuilt):
        t = m.group(1).strip()
        t = re.sub(r',\s*\d{3,4}\s*$', '', t)
        t = re.sub(r'\s+by\s+.+$', '', t, flags=re.IGNORECASE)
        if t:
            out.append(t.strip())
    return out


def _delivered_narration_passages(rebuilt):
    """The delivered stops' narration — the corpus the conclusion is checked
    against (every factual claim in the conclusion must be supported here)."""
    import stop_pool_store as sps
    stops = sps.parse_delivered_stops(tc.normalise_stop_headers(rebuilt))
    return [(s.get("narration") or "").strip() for s in stops
            if (s.get("narration") or "").strip()]


class TestFixturesPresentAndDeliverThree(unittest.TestCase):
    """The fixtures must be the real tours, each delivering three stops once the
    glued header is recovered."""

    def test_fixtures_exist(self):
        for tid in _FIXTURES:
            self.assertTrue(
                os.path.exists(os.path.join(_FIX_DIR, f"tour_{tid}.txt")),
                f"missing fixture tour_{tid}.txt")

    def test_fixtures_each_deliver_three_stops(self):
        for tid in _FIXTURES:
            raw = len(re.findall(r'(?m)^Stop \d+:', _load(tid)))
            self.assertEqual(raw, 2,
                             f"tour {tid}: raw line-start count should be the "
                             f"broken 2 (one header is glued)")
            self.assertEqual(tc.count_delivered_stops(_load(tid)), 3,
                             f"tour {tid} should deliver exactly 3 stops once the "
                             f"glued header is recovered")


class TestThematicConclusionCriteria(unittest.TestCase):
    """The five thematic acceptance criteria (D634), on the rebuilt conclusion."""

    def _rebuilt(self, tid):
        return tc.rebuild_conclusion(_load(tid), venue_name=_FIXTURES[tid])

    # Criterion 1 — NO STOP LIST: at most one delivered title appears.
    def test_1_no_stop_list_at_most_one_title(self):
        for tid in _FIXTURES:
            out = self._rebuilt(tid)
            concl = _conclusion_only(out)
            self.assertTrue(concl, f"tour {tid}: no thematic conclusion found")
            named = 0
            for t in _delivered_titles(out):
                if len(t) < 4:
                    continue
                if re.search(r'\b' + re.escape(t) + r'\b', concl, re.IGNORECASE):
                    named += 1
            self.assertLessEqual(
                named, 1,
                f"tour {tid}: conclusion names {named} delivered titles "
                f"(a stop list); at most 1 allowed:\n{concl}")

    # Criterion 2 — NO "From … to …".
    def test_2_no_from_to(self):
        for tid in _FIXTURES:
            concl = _conclusion_only(self._rebuilt(tid))
            self.assertIsNone(
                _FROM_TO_RE.search(concl),
                f"tour {tid}: conclusion contains a 'From … to …' enumeration:\n{concl}")

    # Criterion 3 — every FACTUAL noun in the conclusion appears in the stops.
    @unittest.skipIf(claim_check is None, "claim_check unavailable")
    def test_3_every_factual_noun_appears_in_stops(self):
        for tid in _FIXTURES:
            out = self._rebuilt(tid)
            concl = _conclusion_only(out)
            # Strip the fixed house restaurant sentence (not a tour fact) and the
            # count sentence (verified separately in criterion 5).
            checkable = _RESTAURANT_RE.sub("", concl)
            checkable = _COUNT_RE.sub("", checkable)
            passages = _delivered_narration_passages(out)
            result = claim_check.check_paragraph(
                checkable, stop_title="", venue_name=_FIXTURES[tid],
                passages=passages, other_stop_passages=None)
            vc = result.get("verdict_counts", {}) or {}
            bad = int(vc.get("unsupported", 0)) + int(vc.get("contradicted", 0))
            self.assertEqual(
                bad, 0,
                f"tour {tid}: conclusion carries {bad} factual claim(s) not "
                f"supported by the delivered stops: "
                f"{[c for c in result.get('claims', []) if c.get('verdict') in ('UNSUPPORTED','CONTRADICTED')]}\n{concl}")

    # Criterion 4 — the RESTAURANT offer is the last sentence.
    def test_4_restaurant_offer_is_last_sentence(self):
        for tid in _FIXTURES:
            out = self._rebuilt(tid)
            body = re.split(r'(?mi)^\s*Sources:', out)[0].strip()
            last_line = [ln for ln in body.splitlines() if ln.strip()][-1]
            self.assertTrue(
                _RESTAURANT_RE.search(last_line),
                f"tour {tid}: last conclusion sentence is not the restaurant "
                f"offer: {last_line!r}")

    # Criterion 5 — the stop COUNT is correct when present.
    def test_5_count_correct_when_present(self):
        for tid in _FIXTURES:
            out = self._rebuilt(tid)
            delivered = tc.count_delivered_stops(out)
            m = _COUNT_RE.search(out)
            if m is not None:  # the count is OPTIONAL; when present it must match
                self.assertEqual(
                    int(m.group(1)), delivered,
                    f"tour {tid}: stated count {m.group(1)} != delivered {delivered}")
            self.assertEqual(delivered, 3, f"tour {tid}: should be 3 stops")

    # Structural contracts carried over from LOCAL-619.
    def test_one_conclusion_per_tour(self):
        for tid in _FIXTURES:
            out = self._rebuilt(tid)
            self.assertEqual(
                len(_THEMATIC_RE.findall(out)), 1,
                f"tour {tid}: expected exactly one thematic conclusion")

    def test_no_legacy_splice_survives(self):
        for tid in _FIXTURES:
            self.assertIsNone(_SPLICE_RE.search(self._rebuilt(tid)),
                              f"tour {tid}: a 'That's N stops —' splice survived")

    def test_sources_block_preserved(self):
        for tid in _FIXTURES:
            self.assertIn("Sources:", self._rebuilt(tid),
                          f"tour {tid}: Sources block was lost")

    def test_idempotent(self):
        for tid in _FIXTURES:
            once = self._rebuilt(tid)
            twice = tc.rebuild_conclusion(once, venue_name=_FIXTURES[tid])
            self.assertEqual(once, twice, f"tour {tid}: rebuild is not idempotent")


class TestLateGateDropUpdatesCount(unittest.TestCase):
    """A late-gate drop recomputes the conclusion count and the orientation's
    'first stop' name — all from the final text — without re-introducing a list."""

    def _drop_first_stop(self, tour_text):
        body, sources = tc._split_tail(tour_text)
        blocks = re.split(r'(?m)(?=^Stop \d+:)', body)
        head = blocks[0]
        stop_blocks = blocks[1:]
        self.assertGreaterEqual(len(stop_blocks), 2)
        kept = head + "".join(stop_blocks[1:])
        if sources:
            kept = kept.rstrip() + "\n\n" + sources
        return kept

    def test_drop_updates_count_and_stays_thematic(self):
        tid = 442
        text = tc.rebuild_conclusion(_load(tid), venue_name=_FIXTURES[tid])
        self.assertEqual(tc.count_delivered_stops(text), 3)

        dropped = self._drop_first_stop(text)
        rebuilt = tc.rebuild_conclusion(dropped, venue_name=_FIXTURES[tid])

        self.assertEqual(tc.count_delivered_stops(rebuilt), 2)
        m = _COUNT_RE.search(rebuilt)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 2)
        # Still thematic, still no From→to, restaurant still last.
        self.assertEqual(len(_THEMATIC_RE.findall(rebuilt)), 1)
        self.assertIsNone(_FROM_TO_RE.search(_conclusion_only(rebuilt)))
        body = re.split(r'(?mi)^\s*Sources:', rebuilt)[0].strip()
        last_line = [ln for ln in body.splitlines() if ln.strip()][-1]
        self.assertTrue(_RESTAURANT_RE.search(last_line))

    def test_drop_to_single_stop_omits_count(self):
        # One stop left: the count sentence is omitted (a count on a single stop
        # reads oddly), and there is still no From→to.
        tid = 442
        text = tc.rebuild_conclusion(_load(tid), venue_name=_FIXTURES[tid])
        once = self._drop_first_stop(text)
        twice = self._drop_first_stop(
            tc.rebuild_conclusion(once, venue_name=_FIXTURES[tid]))
        rebuilt = tc.rebuild_conclusion(twice, venue_name=_FIXTURES[tid])
        self.assertEqual(tc.count_delivered_stops(rebuilt), 1)
        self.assertIsNone(_COUNT_RE.search(rebuilt),
                          "a 1-stop tour should not state a stop count")
        self.assertIsNone(_FROM_TO_RE.search(rebuilt))

    def test_orientation_first_stop_follows_delivered_text(self):
        synthetic = (
            "Step-by-Step Audio Guided Tour: Demo Museum\n\n"
            "Prepare to encounter two works. Your first stop is Alpha.\n\n"
            "Stop 1: Alpha\n\n"
            "Alpha depicts a quiet harbour at dawn, painted in oil on canvas in 1700.\n\n"
            "Stop 2: Beta\n\n"
            "Beta shows a bustling market, rendered in tempera around 1710.\n\n"
            "Across these stops, one thread runs through: harbour life. "
            "Seen together, the works show how differently that subject could be imagined. "
            "That's 2 stops in all.\n\n"
            "If you would like to eat nearby we can build you a restaurant tour.\n"
        )
        self.assertEqual(tc.first_stop_name(synthetic), "Alpha")
        body, sources = tc._split_tail(synthetic)
        blocks = re.split(r'(?m)(?=^Stop \d+:)', body)
        dropped = blocks[0] + "".join(blocks[2:])
        if sources:
            dropped = dropped.rstrip() + "\n\n" + sources
        self.assertIn("Your first stop is Alpha", dropped)
        fixed = tc.fix_orientation_first_stop(dropped)
        self.assertIn("Your first stop is Beta", fixed)
        self.assertNotIn("Your first stop is Alpha", fixed)
        self.assertEqual(tc.first_stop_name(fixed), "Beta")


class TestGluedStopHeaderRecovered(unittest.TestCase):
    """A ``Stop N:`` header glued onto a prior sentence (a lost newline) must
    still be counted (the live tour 448 defect)."""

    GLUED = (
        "Step-by-step audio guided tour of the Demo Museum in Town, Country, is a museum tour.\n\n"
        "Stop 1: Nana\n\n"
        "Nana depicts an actress at her mirror, painted in oil in 1877.\n\n"
        "Stop 2: Das Eismeer\n\n"
        "Das Eismeer shows an ice-locked sea, painted between 1823 and 1824. "
        "Your final stop in Demo Museum: Atelierwand.Stop 3: Atelierwand\n\n"
        "Atelierwand studies the wall of the artist's studio in close detail.\n\n"
        "Across these stops, one thread runs through: the sea. "
        "Seen together, the works show how differently that subject could be imagined. "
        "That's 2 stops in all.\n\n"
        "If you would like to eat nearby we can build you a restaurant tour.\n"
    )

    def test_glued_header_counted(self):
        self.assertEqual(len(re.findall(r'(?m)^Stop \d+:', self.GLUED)), 2)
        self.assertEqual(tc.count_delivered_stops(self.GLUED), 3)

    def test_rebuild_recovers_three_stops(self):
        out = tc.rebuild_conclusion(self.GLUED, venue_name="Demo Museum")
        self.assertEqual(len(re.findall(r'(?m)^Stop \d+:', out)), 3)
        m = _COUNT_RE.search(out)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 3)
        self.assertEqual(out, tc.rebuild_conclusion(out, venue_name="Demo Museum"))


class TestLLMThematicBodyValidation(unittest.TestCase):
    """The cheap-LLM path writes (a)+(b) from the delivered stops only, VALIDATED
    by the claim/G4 machinery, and FALLS BACK to the deterministic template on any
    failure. Exercised with an injected ``llm_fn`` so the test is offline."""

    TOUR = (
        "Tour.\n\n"
        "Stop 1: Nana\n\n"
        "Nana depicts an actress at her mirror, painted in oil in 1877.\n\n"
        "Stop 2: Olympia\n\n"
        "Olympia is a portrait of a reclining woman, painted in 1863.\n\n"
        "If you would like to eat nearby we can build you a restaurant tour.\n"
    )

    def _concl(self, out):
        return _conclusion_only(out)

    def test_grounded_draft_accepted(self):
        draft = ("Across these stops, the painted woman returns again and again. "
                 "Together they ask who gets to look and who is looked at.")
        out = tc.build_conclusion(self.TOUR, venue_name="V", use_llm=True,
                                  llm_fn=lambda p, k: draft, api_key="x")
        self.assertIn("painted woman returns again and again", out)

    def test_smuggled_fact_rejected_falls_back(self):
        # 1912 and "the king" are NOT in the delivered text → claim/G4 rejects.
        draft = ("Across these stops, the figures were all painted in 1912 for "
                 "the king. Together they changed art forever.")
        out = tc.build_conclusion(self.TOUR, venue_name="V", use_llm=True,
                                  llm_fn=lambda p, k: draft, api_key="x")
        self.assertNotIn("1912", out)
        self.assertNotIn("the king", out)
        # Fell back to the deterministic template (a true thread sentence).
        self.assertTrue(_THEMATIC_RE.search(out))

    def test_from_to_draft_rejected(self):
        draft = "From Nana to Olympia you followed the thread. Together they matter."
        out = tc.build_conclusion(self.TOUR, venue_name="V", use_llm=True,
                                  llm_fn=lambda p, k: draft, api_key="x")
        self.assertNotIn("From Nana to Olympia", out)

    def test_two_titles_draft_rejected(self):
        draft = ("Across these stops, Nana and Olympia both show women. "
                 "Together they matter.")
        out = tc.build_conclusion(self.TOUR, venue_name="V", use_llm=True,
                                  llm_fn=lambda p, k: draft, api_key="x")
        self.assertFalse("Nana" in out and "Olympia" in out,
                         "an LLM draft naming two titles must be rejected")

    def test_no_key_no_llm_fn_uses_template(self):
        # No api_key and no injected llm_fn → the deterministic template ships.
        out = tc.build_conclusion(self.TOUR, venue_name="V", use_llm=True,
                                  api_key="")
        self.assertTrue(_THEMATIC_RE.search(out))
        self.assertTrue(out.rstrip().endswith(
            "we can build you a restaurant tour."))


if __name__ == "__main__":
    unittest.main(verbosity=2)
