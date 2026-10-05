#!/usr/bin/env python3
"""test_local584_practical_facts_currency.py — LOCAL-584.

Defect (Michael's tour 391, Griffin Museum of Photography, Winchester MA):
Stop 1 said "Museum Information: €12", and the log showed
"[LOCAL-91] Corpus fallback Museum Information: 08:00–20:00. €12" extracted from
griffinmuseum.org/about-the-griffin-2026/. The page says $12 (also $8, $ 12.00),
has NO €, and NO 08:00 (its times are AM/PM). Two bugs plus a gap:

  1. visitor_facts_extractor normalised ANY price to € (venue-language/default).
  2. It rewrote AM/PM hours to 24h even when the 24h token is nowhere on the page.
  3. The LOCAL-91 corpus fallback stated the result WITHOUT the literal-token check
     LOCAL-582 added, so the wrong facts shipped.

These tests pin all three. They are RED on storied (1691f65) and GREEN after the fix:
  - Griffin fixture -> currency is '$', NEVER '€'; hours are never '08:00'/'20:00'.
  - A French fixture (Musée Matisse / Palais Lascaris) still yields '€' correctly.
  - The shared gate drops the old buggy '08:00–20:00. €12' and keeps '8 AM–8 PM. $12'.

Run: python3 -m pytest test_local584_practical_facts_currency.py -q
"""
import os
import re
import unittest

from visitor_facts_extractor import extract_visitor_facts_from_text

# The shared gate (added by this ticket). Imported lazily so the extractor-only
# tests below still COLLECT and FAIL with clear assertion errors on storied
# (where gate_formatted_facts does not yet exist), rather than erroring at import.
try:
    from practical_facts_gate import gate_formatted_facts, claim_tokens_in_source
    _GATE_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only on pre-fix storied
    _GATE_AVAILABLE = False

    def gate_formatted_facts(*_a, **_k):  # type: ignore
        raise AssertionError("practical_facts_gate.gate_formatted_facts missing (pre-LOCAL-584)")

    def claim_tokens_in_source(*_a, **_k):  # type: ignore
        raise AssertionError("practical_facts_gate.claim_tokens_in_source missing (pre-LOCAL-584)")

_FIX_DIR = os.path.join(os.path.dirname(__file__), 'tests', 'fixtures')
_GRIFFIN_FIXTURE = os.path.join(_FIX_DIR, 'griffin_about_2026.html')


def _strip_html(html: str) -> str:
    html = re.sub(r'<(script|style)\b.*?</\1>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<[^>]+>', ' ', html)
    return re.sub(r'\s+', ' ', html).strip()


with open(_GRIFFIN_FIXTURE, encoding='utf-8') as _fh:
    _GRIFFIN_TEXT = _strip_html(_fh.read())


# A French municipal museum page (Musée Matisse, Nice) — the € currency IS on the
# page, so the fix must still emit €. Mirrors tests/test_local35_visitor_facts.py.
_MATISSE_EN_TEXT = """
Practical information Getting here Musée Matisse 164, avenue des Arènes de Cimiez 06000 Nice
Opening times Museum open daily except Tuesdays
From November 1st to March 31th: open from 10 am to 5 pm
From April 1st to October 31st: open from 10 am to 6 pm
Closed on January 1st, Easter Sunday, May 1st and December 25th.
Museum Tickets Musée Matisse – 12€
Nice Museums Pass The pass is free for residents of Nice and the towns located
within the Métropole Nice Côte d'Azur.
"""

_PALAIS_FR_TEXT = """
Palais Lascaris Informations pratiques Adresse 15 rue Droite 06300 Nice
Horaires de visite du 1 janvier au 31 décembre
Lundi : 10h00 - 18h00
Mardi : Fermé
Fermé le 1er janvier, dimanche de Pâques, 1er mai et 25 décembre.
Tarifs Entrée unique 5 € 4 €
Pass Musées de Nice : un accès gratuit pour les habitants de la Métropole !
"""


class TestGriffinCurrencyAndHours(unittest.TestCase):
    """The Griffin (US) page: $ stays $, hours stay AM/PM — the exact tour-391 defect."""

    @classmethod
    def setUpClass(cls):
        cls.facts = extract_visitor_facts_from_text(_GRIFFIN_TEXT, 'en')
        cls.formatted = cls.facts.format_en()

    def test_fixture_sanity(self):
        # The page really is $-priced, AM/PM, and has no € / no 08:00.
        self.assertIn('$12', _GRIFFIN_TEXT)
        self.assertNotIn('€', _GRIFFIN_TEXT)
        self.assertNotIn('08:00', _GRIFFIN_TEXT)

    def test_admission_currency_is_dollar_not_euro(self):
        self.assertIn('$', self.facts.admission,
                      f"admission should keep '$': {self.facts.admission!r}")
        self.assertNotIn('€', self.facts.admission,
                         f"admission must NOT be rewritten to €: {self.facts.admission!r}")

    def test_admission_amount_is_12(self):
        self.assertIn('12', self.facts.admission,
                      f"admission should state the $12 price: {self.facts.admission!r}")

    def test_formatted_never_contains_euro(self):
        self.assertNotIn('€', self.formatted,
                         f"formatted facts must never contain €: {self.formatted!r}")

    def test_hours_never_0800_to_2000(self):
        # The whole point: the 24h schedule must not be synthesised for an AM/PM page.
        for h in self.facts.hours:
            self.assertNotIn('08:00', h['time'],
                             f"hours must not synthesise 08:00: {self.facts.hours}")
            self.assertNotIn('20:00', h['time'],
                             f"hours must not synthesise 20:00: {self.facts.hours}")
        self.assertNotIn('08:00', self.formatted)
        self.assertNotIn('20:00', self.formatted)

    def test_formatted_tokens_are_on_the_page(self):
        # Every digit the formatted facts carries must be a token on the page.
        src = _GRIFFIN_TEXT.lower()
        self.assertTrue(claim_tokens_in_source(self.formatted, src),
                        f"formatted facts carry a token not on the page: {self.formatted!r}")


class TestSharedGateDropsBuggyFacts(unittest.TestCase):
    """The ONE gate: the old buggy string is fully dropped; the corrected one survives."""

    def test_old_buggy_facts_fully_dropped(self):
        surviving, dropped = gate_formatted_facts(
            '08:00–20:00. €12', _GRIFFIN_TEXT, source_url='griffinmuseum.org')
        self.assertEqual(surviving, '',
                         f"old euro/24h facts must not survive: {surviving!r}")
        self.assertEqual(len(dropped), 2,
                         f"both segments should be dropped: {dropped}")

    def test_corrected_facts_survive(self):
        surviving, dropped = gate_formatted_facts(
            '8 AM–8 PM. $12', _GRIFFIN_TEXT, source_url='griffinmuseum.org')
        self.assertIn('$12', surviving)
        self.assertNotIn('€', surviving)
        self.assertNotIn('08:00', surviving)
        self.assertEqual(dropped, [], f"page-supported facts should not be dropped: {dropped}")

    def test_euro_claim_on_dollar_page_dropped_by_literal_check(self):
        # Direct guard: a € price claim is rejected when the source has no €.
        self.assertFalse(claim_tokens_in_source('€12', _GRIFFIN_TEXT.lower()))
        # ...but the real $ price passes.
        self.assertTrue(claim_tokens_in_source('$12', _GRIFFIN_TEXT.lower()))

    def test_dropped_segments_are_logged_with_local584_prefix(self):
        logged = []
        gate_formatted_facts('08:00–20:00. €12', _GRIFFIN_TEXT,
                             source_url='griffinmuseum.org', log=logged.append)
        self.assertTrue(logged, "the gate must log dropped facts")
        self.assertTrue(all('[LOCAL-584] dropped unsupported practical fact:' in m for m in logged),
                        f"log lines must carry the LOCAL-584 prefix: {logged}")


class TestFrenchStillEuro(unittest.TestCase):
    """A French page where € IS on the page must still yield € (no regression)."""

    def test_matisse_admission_is_euro(self):
        facts = extract_visitor_facts_from_text(_MATISSE_EN_TEXT, 'en')
        self.assertIn('€12', facts.admission,
                      f"Matisse admission should be €12: {facts.admission!r}")
        self.assertNotIn('$', facts.admission)

    def test_palais_admission_is_euro(self):
        facts = extract_visitor_facts_from_text(_PALAIS_FR_TEXT, 'fr')
        self.assertIn('€5', facts.admission,
                      f"Palais admission should be €5: {facts.admission!r}")
        self.assertNotIn('$', facts.admission)

    def test_palais_hours_stay_24h(self):
        # The Palais page is genuinely 24h ("10h00 - 18h00") → 24h is page-supported.
        facts = extract_visitor_facts_from_text(_PALAIS_FR_TEXT, 'fr')
        self.assertTrue(facts.hours)
        self.assertIn('18:00', facts.hours[0]['time'],
                      f"Palais 24h hours should be kept: {facts.hours}")

    def test_matisse_euro_facts_survive_gate_against_euro_source(self):
        facts = extract_visitor_facts_from_text(_MATISSE_EN_TEXT, 'en')
        surviving, dropped = gate_formatted_facts(
            facts.format_en(), _MATISSE_EN_TEXT, source_url='musee-matisse-nice.org')
        self.assertIn('€12', surviving,
                      f"Matisse €12 must survive against a € source: {surviving!r} dropped={dropped}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
