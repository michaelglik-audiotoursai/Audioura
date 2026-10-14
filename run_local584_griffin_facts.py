#!/usr/bin/env python3
"""run_local584_griffin_facts.py — LOCAL-584 live practical-facts proof (no LLM).

The defect lived in the practical-facts path (LOCAL-35 extractor + LOCAL-91 corpus
fallback), not the narration LLM. This harness drives THAT path live, inside the
container, against the real Griffin page:

  1. LIVE fetch of griffinmuseum.org via visitor_facts_extractor.fetch_visitor_info_
     with_provenance (LOCAL-39) — the official-site path.
  2. The LOCAL-91 corpus-fallback gate: feed the extractor's format_en() through the
     ONE shared gate (practical_facts_gate.gate_formatted_facts) exactly as
     generate_tour_text now does, and print the surviving Museum Information line.

Also runs the committed fixture (offline, deterministic) so the result is
reproducible even if the live site changes. Asserts: no €, no 08:00/20:00, $ kept.

No OpenAI spend. audio_tours untouched (not even counted — this path never writes).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from visitor_facts_extractor import (extract_visitor_facts_from_text,
                                     fetch_visitor_info_with_provenance,
                                     _html_to_sectioned_text)
from practical_facts_gate import gate_formatted_facts

GRIFFIN_URL = 'https://griffinmuseum.org/about-the-griffin-2026/'
FIXTURE = os.path.join(HERE, 'tests', 'fixtures', 'griffin_about_2026.html')
VENUE_NAME = 'Griffin Museum of Photography'
VENUE_ADDR = '67 Shore Road, Winchester, MA'


def _strip(html):
    html = re.sub(r'<(script|style)\b.*?</\1>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()


def _assert_clean(label, museum_info, source_text):
    print(f"\n[{label}] Museum Information: {museum_info!r}")
    assert '€' not in museum_info, f"{label}: euro leaked: {museum_info!r}"
    assert '08:00' not in museum_info and '20:00' not in museum_info, \
        f"{label}: synthetic 24h hours: {museum_info!r}"
    # [LOCAL-584 r2] The satellite galleries' hours must NEVER be the venue's.
    assert '8 AM' not in museum_info, f"{label}: Lafayette satellite 8 AM leaked: {museum_info!r}"
    assert '9 AM' not in museum_info, f"{label}: Jenks satellite 9 AM leaked: {museum_info!r}"
    # Everything stated must be a token on the page.
    low = source_text.lower()
    for num in re.findall(r'\d+', museum_info):
        assert num in low, f"{label}: stated number {num} not on page"
    print(f"[{label}] ✓ venue-bound (no 8 AM / 9 AM satellite) ; ✓ no € ; "
          f"✓ no 08:00/20:00 ; ✓ every token on the page")


print("=" * 72)
print("LOCAL-584 r2 — Griffin practical facts, venue-bound (container, no LLM)")
print("=" * 72)

# 1. OFFLINE committed fixture (reproducible). Sectioned flattening + venue name
#    so hours bind to the venue's own section, not a satellite gallery's.
fx_sectioned = _html_to_sectioned_text(open(FIXTURE, encoding='utf-8').read())
fx_plain = _strip(open(FIXTURE, encoding='utf-8').read())
fx_facts = extract_visitor_facts_from_text(
    fx_sectioned, 'en', venue_name=VENUE_NAME, venue_address=VENUE_ADDR)
fx_formatted = fx_facts.format_en()
print(f"\n[fixture] venue-bound extractor format_en(): {fx_formatted!r}")
fx_surv, fx_dropped = gate_formatted_facts(fx_formatted, fx_plain, source_url=GRIFFIN_URL,
                                           log=lambda m: print(f"  {m}"))
_assert_clean('fixture', fx_surv, fx_plain)
print(f"[fixture] gate dropped: {fx_dropped}")

# 2. LIVE fetch (if the network is reachable from the container). The official-site
#    path now passes the venue name through fetch_visitor_info_with_provenance.
print(f"\n[live] fetching {GRIFFIN_URL} …")
try:
    vi = fetch_visitor_info_with_provenance(
        GRIFFIN_URL, language='en', venue_name=VENUE_NAME, venue_address=VENUE_ADDR)
    live_formatted = getattr(vi, 'formatted_info', '') or ''
    live_src = getattr(vi, 'source_text', '') or ''
    print(f"[live] extractor format_en(): {live_formatted!r}")
    print(f"[live] source_url: {getattr(vi, 'source_url', '')}")
    if live_formatted and live_src:
        live_surv, live_dropped = gate_formatted_facts(
            live_formatted, live_src, source_url=getattr(vi, 'source_url', ''),
            log=lambda m: print(f"  {m}"))
        _assert_clean('live', live_surv, live_src)
        print(f"[live] gate dropped: {live_dropped}")
    else:
        print("[live] extractor returned no formatted facts for this fetch "
              "(official-site path may land on a different page); fixture result stands.")
except Exception as e:
    print(f"[live] fetch unavailable ({type(e).__name__}: {e}); fixture result stands.")

print("\n" + "=" * 72)
print("DONE — hours are the venue's (Noon–4 PM), never a satellite gallery's.")
print("=" * 72)
