"""
cross_stop_reference_guard.py — [LOCAL-616 item 4]
==================================================
A pooled stop's narration can carry a cross-reference to a stop from its ORIGINAL
tour — a stop that is NOT in the tour we are now delivering. Tour 414 (Musée Fabre)
shipped, inside Stop 1:

    "…mirrors … the earlier stops of this tour, such as La Vue du village…"

"La Vue du village" is not a stop in tour 414 — it was a stop in the earlier tour
whose narration was reused from the pool. A listener is told to recall a stop that
does not exist.

This module adds a deterministic (no-LLM) pass that strips any sentence making a
cross-stop reference whose NAMED title is not present in the delivered tour. It is
conservative: it only drops a sentence when BOTH
  (a) the sentence contains a cross-stop cue ("earlier stop(s)", "such as",
      "a few stops ago", "you saw/paused at/encountered …", "the <title> stop"), and
  (b) it names a title-like phrase (a quoted phrase, or a multi-word Capitalised
      run introduced by "such as"/"like") that does NOT match any delivered title.
A cross-reference to a title that IS delivered is kept; a sentence with no named
title is kept (other guards own vague recaps). Mirrors cross_stop_fact_dedupe:
takes ordered stop-unit dicts, returns (new_units, dropped) with narration rewritten.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Tuple


def _split_sentences(text: str) -> List[str]:
    try:
        from sentence_split import split_sentences as _shared
        return _shared(text or "")
    except Exception:  # pragma: no cover
        return [s.strip() for s in re.split(r'(?<=[.!?])\s+', (text or "").strip())
                if s.strip()]


def _norm(s: str) -> str:
    """Lowercase, de-accent, collapse whitespace, strip surrounding punctuation —
    for comparing a referenced phrase against delivered titles."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _title_core(title: str) -> str:
    """A stop title is often "Artist: Work" or "Work, 1782" — reduce it to the
    comparable work/subject core."""
    t = title or ""
    if ":" in t:
        t = t.split(":", 1)[1]
    t = re.sub(r",\s*\d{3,4}\s*$", "", t)       # trailing year
    t = re.sub(r"\s+by\s+.+$", "", t, flags=re.I)  # "… by Artist"
    return t.strip()


# Cross-stop cue phrases: a sentence that tells the listener to recall ANOTHER stop.
_CUE_RE = re.compile(
    r"(?i)\b("
    r"earlier stop|earlier stops|other stops? of this tour|"
    r"stops? of this tour|a few stops ago|"
    r"earlier (?:on )?(?:your|this) tour|previously on this tour|"
    r"as you saw at|you (?:saw|viewed|paused at|encountered|glimpsed|passed)|"
    r"recall(?:ing)? the|elsewhere (?:in|on) (?:this|your) tour"
    r")\b")

# A named-title candidate introduced by "such as"/"like", OR a quoted phrase.
# "such as La Vue du village" / "like The Oath of the Horatii" / 'such as "X"'.
_SUCH_AS_RE = re.compile(
    r"(?i)\b(?:such as|like|including|for example|e\.g\.,?)\s+"
    r"([\"'\u201c\u2018]?[A-Z\u00C0-\u017F][\w'\u00C0-\u017F.-]*"
    r"(?:\s+(?:de|du|des|la|le|les|of|the|and|von|van|di|della|a|an|in)?\s*"
    r"[A-Za-z\u00C0-\u017F][\w'\u00C0-\u017F.-]*){1,6}[\"'\u201d\u2019]?)")

# A quoted title anywhere in the sentence.
_QUOTED_RE = re.compile(r"[\"\u201c\u2018']([^\"\u201d\u2019']{3,80})[\"\u201d\u2019']")

# "the <Title> stop" / "in the <Title> gallery/room/hall" cross-reference.
_THE_X_STOP_RE = re.compile(
    r"(?i)\b(?:in |at )?the\s+([A-Z\u00C0-\u017F][\w'\u00C0-\u017F.-]*"
    r"(?:\s+[A-Z\u00C0-\u017F][\w'\u00C0-\u017F.-]*){0,5})\s+"
    r"(?:stop|gallery|room|hall)\b")


def _candidate_titles(sentence: str) -> List[str]:
    """Extract title-like phrases a cross-reference names in this sentence."""
    cands: List[str] = []
    for m in _SUCH_AS_RE.finditer(sentence):
        cands.append(m.group(1))
    for m in _QUOTED_RE.finditer(sentence):
        cands.append(m.group(1))
    for m in _THE_X_STOP_RE.finditer(sentence):
        cands.append(m.group(1))
    # Clean surrounding quotes/space.
    cleaned = []
    for c in cands:
        c = c.strip().strip("\"'\u201c\u201d\u2018\u2019").strip()
        c = c.rstrip(".,;:!?").strip()
        if c:
            cleaned.append(c)
    return cleaned


def _is_delivered(cand: str, delivered_norms: List[str]) -> bool:
    """True when the referenced phrase matches a delivered title (either direction
    of containment, after normalisation) — so a real cross-reference is kept."""
    cn = _norm(cand)
    if not cn:
        return True  # nothing concrete named → not a phantom
    for dn in delivered_norms:
        if not dn:
            continue
        if cn == dn or cn in dn or dn in cn:
            return True
    return False


def strip_phantom_references(
        ordered_units: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Drop sentences that cross-reference a title NOT present in the delivered
    tour. Returns (new_units, dropped). ``new_units`` is a fresh list with rewritten
    narration; originals are untouched. ``dropped`` entries are
    {stop, sentence, reason, phantom}.
    """
    # Delivered title set: full titles + their work cores, normalised.
    delivered_norms: List[str] = []
    for u in ordered_units:
        t = (u.get("title") or "").strip()
        if not t:
            continue
        delivered_norms.append(_norm(t))
        core = _title_core(t)
        if core:
            delivered_norms.append(_norm(core))
    delivered_norms = [d for d in delivered_norms if d]

    dropped: List[Dict] = []
    new_units: List[Dict] = []
    for i, unit in enumerate(ordered_units):
        stop_num = i + 1
        narration = unit.get("narration") or ""
        if not narration.strip():
            new_units.append(dict(unit))
            continue
        out_paras: List[str] = []
        for para in re.split(r"\n{2,}", narration):
            sentences = _split_sentences(para)
            if not sentences:
                out_paras.append(para)
                continue
            kept: List[str] = []
            for sent in sentences:
                if _CUE_RE.search(sent):
                    cands = _candidate_titles(sent)
                    phantom = next(
                        (c for c in cands if not _is_delivered(c, delivered_norms)),
                        None)
                    if phantom is not None:
                        dropped.append({
                            "stop": stop_num,
                            "sentence": sent.strip(),
                            "reason": "cross-reference to a title not in this tour",
                            "phantom": phantom,
                        })
                        continue  # drop this sentence
                kept.append(sent)
            out_paras.append(" ".join(kept).strip())
        new_narr = "\n\n".join(p for p in out_paras if p.strip()).strip()
        nu = dict(unit)
        nu["narration"] = new_narr
        new_units.append(nu)
    return new_units, dropped


# ─── [LOCAL-627 defect 9] Cross-stop callback / recap-phrase guard ────────────
#
# cross_stop_fact_dedupe collapses a repeated dated FACT; this guard governs the
# SOFT callback — the recap sentence that tells the listener to recall a previous
# stop. Tour 487 opened "…you stopped at a moment ago" / "think of the Portrait…
# you stopped at earlier" in EVERY stop. Michael's rule: at most ONE light
# thematic bridge per tour, and NEVER a recap of the PREVIOUS stop (the listener
# was just there). Deterministic: no network/LLM.

# A PREVIOUS-STOP recap: "you stopped at … a moment ago / just now / earlier",
# "the <X> you (just) saw", "a moment ago", "which we just left". These are the
# "you were just there" callbacks that must never appear.
_PREV_STOP_RECAP_RE = re.compile(
    r"(?i)("
    r"you\s+(?:stopped\s+at|saw|viewed|visited|passed|left|were\s+at)\b[^.?!]*"
    r"\b(?:a\s+moment\s+ago|just\s+now|moments?\s+ago|earlier|previously|"
    r"a\s+(?:few\s+)?(?:moments?|minutes?)\s+ago)\b|"
    r"\b(?:a\s+moment\s+ago|just\s+a\s+moment\s+ago|moments?\s+ago)\b|"
    r"(?:which|that)\s+(?:we|you)\s+just\s+(?:saw|left|visited|passed)|"
    r"\bjust\s+(?:saw|left|visited|passed)\s+(?:a\s+moment\s+ago)?"
    r")")

# A THEMATIC BRIDGE: a soft callback that connects stops by theme, without naming
# a "you were just there" recency. "Like the earlier stop", "as you saw earlier
# on this tour", "echoing a theme from a previous stop", "recall the …".
_THEMATIC_BRIDGE_RE = re.compile(
    r"(?i)("
    r"earlier\s+(?:on\s+)?(?:this|your)\s+tour|previously\s+on\s+this\s+tour|"
    r"as\s+you\s+saw\s+earlier|like\s+the\s+earlier\s+stop|"
    r"echo(?:es|ing)?\s+(?:a\s+)?(?:theme|motif|idea)\s+from|"
    r"recall(?:ing)?\s+the\b|"
    r"a\s+(?:previous|prior|earlier)\s+stop|other\s+stops?\s+(?:of|on)\s+this\s+tour"
    r")")


def limit_thematic_bridges(
        ordered_units: List[Dict],
        max_bridges: int = 1) -> Tuple[List[Dict], List[Dict]]:
    """[LOCAL-627 defect 9] Allow at most ``max_bridges`` light thematic bridges
    across the whole tour and drop EVERY previous-stop recap sentence.

    Walks stops in order. A sentence is DROPPED when:
      * it is a previous-stop recap ("…you stopped at a moment ago", "the X you
        just saw") — always, regardless of the bridge budget; or
      * it is a thematic bridge AND the per-tour bridge budget is already spent.

    The FIRST ``max_bridges`` thematic bridges (that are not also previous-stop
    recaps) are kept. Returns (new_units, dropped). Pure and deterministic; mirrors
    strip_phantom_references' shape.
    """
    bridges_kept = 0
    dropped: List[Dict] = []
    new_units: List[Dict] = []
    for i, unit in enumerate(ordered_units):
        stop_num = i + 1
        narration = unit.get("narration") or ""
        nu = dict(unit)
        if not narration.strip():
            new_units.append(nu)
            continue
        out_paras: List[str] = []
        for para in re.split(r"\n{2,}", narration):
            sentences = _split_sentences(para)
            if not sentences:
                out_paras.append(para)
                continue
            kept: List[str] = []
            for sent in sentences:
                is_recap = bool(_PREV_STOP_RECAP_RE.search(sent))
                is_bridge = bool(_THEMATIC_BRIDGE_RE.search(sent))
                if is_recap:
                    dropped.append({
                        "stop": stop_num, "sentence": sent.strip(),
                        "reason": "previous-stop recap"})
                    continue
                if is_bridge:
                    if bridges_kept >= max_bridges:
                        dropped.append({
                            "stop": stop_num, "sentence": sent.strip(),
                            "reason": "more than one thematic bridge"})
                        continue
                    bridges_kept += 1
                kept.append(sent)
            out_paras.append(" ".join(kept).strip())
        nu["narration"] = "\n\n".join(p for p in out_paras if p.strip()).strip()
        new_units.append(nu)
    return new_units, dropped
