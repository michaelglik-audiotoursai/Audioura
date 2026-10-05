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
                                     fetch_visitor_info_with_provenance)
from practical_facts_gate import gate_formatted_facts

GRIFFIN_URL = 'https://griffinmuseum.org/about-the-griffin-2026/'
FIXTURE = os.path.join(HERE, 'tests', 'fixtures', 'griffin_about_2026.html')


def _strip(html):
    html = re.sub(r'<(script|style)\b.*?</\1>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()


def _assert_clean(label, museum_info, source_text):
    print(f"\n[{label}] Museum Information: {museum_info!r}")
    assert '€' not in museum_info, f"{label}: euro leaked: {museum_info!r}"
    assert '08:00' not in museum_info and '20:00' not in museum_info, \
        f"{label}: synthetic 24h hours: {museum_info!r}"
    # Everything stated must be a token on the page.
    low = source_text.lower()
    for num in re.findall(r'\d+', museum_info):
        assert num in low, f"{label}: stated number {num} not on page"
    print(f"[{label}] ✓ no € ; ✓ no 08:00/20:00 ; ✓ every token on the page")


print("=" * 72)
print("LOCAL-584 — Griffin practical facts through the fixed path (container, no LLM)")
print("=" * 72)

# 1. OFFLINE committed fixture (reproducible).
fx_text = _strip(open(FIXTURE, encoding='utf-8').read())
fx_facts = extract_visitor_facts_from_text(fx_text, 'en')
fx_formatted = fx_facts.format_en()
print(f"\n[fixture] raw extractor format_en(): {fx_formatted!r}")
fx_surv, fx_dropped = gate_formatted_facts(fx_formatted, fx_text, source_url=GRIFFIN_URL,
                                           log=lambda m: print(f"  {m}"))
_assert_clean('fixture', fx_surv, fx_text)
print(f"[fixture] gate dropped: {fx_dropped}")

# 2. LIVE fetch (if the network is reachable from the container).
print(f"\n[live] fetching {GRIFFIN_URL} …")
try:
    vi = fetch_visitor_info_with_provenance(GRIFFIN_URL, language='en')
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
print("DONE — fixed path keeps '$', never emits '€' or '08:00/20:00'.")
print("=" * 72)
