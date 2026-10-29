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

__all__ = ["is_disambiguation_text", "strip_disambiguation_lines"]

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


# ─────────────────────────────────────────────────────────────────────────────
# [LOCAL-811] Text-level line/sentence drop. The ticket's fix 2: a final guard for
# ALL tours drops any sentence/paragraph that IS a Wikipedia disambiguation line
# ("X may refer to:", "X may also refer to", and the DE/FR/IT/ES/NL equivalents),
# wherever it came from — pooled reuse, fresh research, or a cached delivery that
# predates the LOCAL-809 entity/text guards. ``is_disambiguation_text`` above
# DECIDES a whole extract is a stub (so the corpus is never accepted); this REMOVES
# an individual disambiguation line that nonetheless reached the delivered text.
# ─────────────────────────────────────────────────────────────────────────────

# A "may refer to"/"steht für:"/… CLAUSE anywhere in a sentence or line (NOT
# anchored to a lead window — a delivered body may carry the stub line mid-text).
# Same phrase set as _MAY_REFER_RE, reused directly.
_DISAMBIG_LINE_RE = _MAY_REFER_RE

# Sentence splitter: keep it simple and deterministic. A disambiguation lead is a
# short declarative line; splitting on sentence punctuation + newlines isolates it
# from surrounding real prose so only the stub clause is removed.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?:])\s+|\n")


# A WHOLE-paragraph disambiguation stub BEGINS with "<Short Name> may refer to"
# (or a marker) as its very first clause — the title plus the clause IS the lead,
# with no real sentence before it. Anchored at the start so a stop body that only
# CONTAINS the clause after a genuine sentence does not match (it falls to the
# sentence-level removal, which drops just the stub sentence). The name before the
# clause is short (a title, not prose): up to ~40 characters, no sentence-ending
# punctuation.
_STUB_LEAD_RE = re.compile(
    r"(?is)^\s*[^.!?\n]{0,40}?(?:"
    r"may\s+(?:also\s+)?refer\s+to|can\s+refer\s+to|refers?\s+to\s*:|"
    r"steht\s+f[üu]r\s*:|kann\s+sich\s+beziehen\s+auf|"
    r"peut\s+(?:faire\s+r[ée]f[ée]rence\s+[àa]|d[ée]signer)|"
    r"pu[òo]\s+riferirsi\s+a|puede\s+referirse\s+a|hace\s+referencia\s+a|"
    r"kan\s+verwijzen\s+naar"
    r")")


def _line_is_disambiguation(fragment: str) -> bool:
    """True when a single sentence/line IS a disambiguation stub line — a terse
    "<Name> may refer to" / marker line where the clause is the line's OWN opening
    statement, not a real sentence that uses the words deep in explanatory prose.

    Two signals, both conservative:
      * a STUB-LEAD shape (``_STUB_LEAD_RE``): a short name (<= ~40 chars, no
        sentence punctuation) immediately followed by the "may refer to" clause —
        "Belvedere may refer to:". A real sentence ("In art-historical usage the
        term baroque may refer to a sweeping movement …") has substantial prose
        before the clause and does NOT match; or
      * an explicit disambiguation MARKER ("(disambiguation)", "Begriffsklärung",
        …) in a short fragment.

    The length bound alone is not enough (a real sentence can be short), so the
    decisive test is the anchored stub-lead shape."""
    f = (fragment or "").strip()
    if not f:
        return False
    if len(f) > 200:
        return False
    if _STUB_LEAD_RE.search(f):
        return True
    if _DISAMBIG_MARKER_RE.search(f) and len(f) <= 120:
        return True
    return False


def strip_disambiguation_lines(text: str):
    """[LOCAL-811] Remove any Wikipedia DISAMBIGUATION line from ``text``, wherever
    it appears, and return ``(cleaned_text, dropped_count)``.

    Operates paragraph by paragraph, then sentence by sentence within a paragraph:
      * a WHOLE paragraph that is itself a disambiguation stub (its text passes
        ``is_disambiguation_text`` — e.g. "Belvedere may refer to:" followed by a
        list) is dropped entirely;
      * otherwise each sentence/line is tested with ``_line_is_disambiguation`` and
        a matching one is dropped, leaving the rest of the paragraph intact.

    Deterministic, offline, idempotent (a second pass drops nothing). Non-fatal by
    construction — it only removes; it never rewrites surrounding prose. A real
    article sentence that uses "may refer to" inside a long explanation is NOT a
    stub line (it exceeds the length bound / is not the sentence's own statement)
    and is kept. Returns the input unchanged (0 dropped) on empty text."""
    if not text or not isinstance(text, str):
        return text, 0

    dropped = 0
    # Split into paragraphs on blank lines, preserving the blank-line separators so
    # the rejoin keeps the document's paragraph spacing.
    paragraphs = re.split(r"(\n\s*\n)", text)
    out_parts = []
    for part in paragraphs:
        # Separator chunks (the captured \n\s*\n) pass through untouched.
        if re.fullmatch(r"\n\s*\n", part or ""):
            out_parts.append(part)
            continue
        para = part
        stripped = para.strip()
        if not stripped:
            out_parts.append(para)
            continue
        # Whole-paragraph stub: drop it ONLY when the paragraph BEGINS as a terse
        # disambiguation stub — "Belvedere may refer to:" as its own opening clause
        # (the title + "may refer to" IS the lead), optionally followed by a short
        # list. A real stop body that merely contains the stub clause after one or
        # more genuine sentences ("Welcome to the Belvedere. Belvedere may refer
        # to: …") does NOT begin as a stub, so it falls through to the sentence-
        # level removal below and only the stub sentence is dropped — the stop body
        # is never wiped. ~60 chars in is where a "<Name> may refer to" lead sits.
        _head = stripped[:60]
        if (len(stripped) <= 300
                and (_STUB_LEAD_RE.search(stripped)
                     or _DISAMBIG_MARKER_RE.search(_head))
                and is_disambiguation_text(stripped)):
            dropped += 1
            out_parts.append("")
            continue
        # Sentence/line level: drop only the disambiguation fragment(s).
        if _DISAMBIG_LINE_RE.search(para) or _DISAMBIG_MARKER_RE.search(para):
            fragments = _SENTENCE_SPLIT_RE.split(para)
            kept_fragments = []
            any_dropped = False
            for frag in fragments:
                if _line_is_disambiguation(frag):
                    dropped += 1
                    any_dropped = True
                    continue
                kept_fragments.append(frag)
            if any_dropped:
                para = " ".join(f.strip() for f in kept_fragments if f.strip())
        out_parts.append(para)

    cleaned = "".join(out_parts)
    # Collapse any runs of 3+ newlines left by a dropped whole paragraph to the
    # normal paragraph gap; never touch intra-paragraph single newlines.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, dropped
