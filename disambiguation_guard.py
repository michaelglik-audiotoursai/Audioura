"""disambiguation_guard.py — [LOCAL-809] reject a Wikipedia DISAMBIGUATION page
as corpus / venue text.

Belvedere Museum, Vienna (tour 861, score 3.5): stop 1 contained the literal line
"Belvedere may refer to:" — the lead of Wikipedia's DISAMBIGUATION page for the
bare name "Belvedere". The venue resolved from the bare name "Belvedere" to the
wrong entity and that disambiguation page's TEXT was accepted as the museum's
corpus, so the tour opened with a list of unrelated Belvederes and every pin was
~1 km off (the wrong "Belvedere" place).

The Wikidata ENTITY-level filter (venue_resolver._filter_disambiguation_pages,
P31 = Q4167410) catches a disambiguation ITEM, but the venue text / stop corpus is
also fetched by TITLE through several Wikipedia ``prop=extracts`` paths
(three_class_retrieval, story_miner, stop_subject_acquisition, rag_retriever), and
those accept the extract TEXT without ever asking whether the text itself is a
disambiguation stub. This module is the missing TEXT-level guard:

  is_disambiguation_text(text, title="") -> bool
      True when ``text`` is a Wikipedia disambiguation page — it opens with an
      "X may refer to" / "may also refer to" line (EN + the live-venue languages),
      or carries an unmistakable disambiguation marker. Pure: no network, no I/O,
      deterministic, so every rule is unit-testable and cannot drift at runtime.

Kept deliberately tight so a real article is never discarded: the "may refer to"
test is anchored to the FIRST ~400 characters (a disambiguation stub says it in
its lead), and the phrase list is explicit.
"""
from __future__ import annotations

import re

__all__ = ["is_disambiguation_text"]

# "X may refer to", "X may also refer to", "X can refer to", "X refers to:" — the
# canonical disambiguation lead, across the live-venue languages (EN, DE, FR, IT,
# ES, NL). Anchored near the start so only a LEAD line counts; a later mention
# inside a real article ("the term may refer to several schools …") is not a stub.
_MAY_REFER_RE = re.compile(
    r"(?i)\bmay\s+(?:also\s+)?refer\s+to\b"
    r"|\bcan\s+refer\s+to\b"
    r"|\brefers?\s+to\s*:\s*$"
    # German: "… steht für:" / "… ist der Name" (disambig lead)
    r"|\bsteht\s+f[üu]r\s*:"
    r"|\bkann\s+sich\s+beziehen\s+auf"
    # French: "… peut faire référence à" / "… peut désigner"
    r"|\bpeut\s+(?:faire\s+r[ée]f[ée]rence\s+[àa]|d[ée]signer)\b"
    # Italian / Spanish: "… può riferirsi a" / "… puede referirse a"
    r"|\bpu[òo]\s+riferirsi\s+a\b"
    r"|\bpuede\s+referirse\s+a\b"
    r"|\bhace\s+referencia\s+a\b"
    # Dutch: "… kan verwijzen naar"
    r"|\bkan\s+verwijzen\s+naar\b")

# Explicit disambiguation markers a scraped extract sometimes carries verbatim.
_DISAMBIG_MARKER_RE = re.compile(
    r"(?i)\b(?:disambiguation(?:\s+page)?|begriffskl[äa]rung|"
    r"homonymie|disambigua|desambiguaci[óo]n|doorverwijspagina)\b")

# How far into the text a "may refer to" lead must appear to count as a stub lead.
_LEAD_WINDOW = 400


def is_disambiguation_text(text: str, title: str = "") -> bool:
    """[LOCAL-809] True when ``text`` is a Wikipedia DISAMBIGUATION page and must
    never be used as corpus / venue text.

    Detects, deterministically and offline:
      * a disambiguation LEAD — an "X may refer to" / "may also refer to" / "can
        refer to" / "refers to:" opener (and its DE/FR/IT/ES/NL equivalents)
        within the first ~400 characters of the extract (where a stub states it);
      * an explicit disambiguation MARKER anywhere ("(disambiguation)",
        "Begriffsklärung", "Homonymie", …).

    Conservative: the "may refer to" test is anchored to the LEAD so a real
    article that mentions the phrase deep in its body is not discarded, and an
    empty/whitespace text returns False (absence of text is handled by the caller's
    own length check, not here)."""
    t = (text or "").strip()
    if not t:
        return False

    lead = t[:_LEAD_WINDOW]
    if _MAY_REFER_RE.search(lead):
        return True

    # A "(disambiguation)" title is itself conclusive.
    if title and _DISAMBIG_MARKER_RE.search(title):
        return True

    # A disambiguation marker in the lead (verbatim scraped) is conclusive.
    if _DISAMBIG_MARKER_RE.search(lead):
        return True

    return False
