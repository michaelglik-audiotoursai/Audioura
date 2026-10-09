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
from typing import Optional, Dict, List, Tuple


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
    r"you\s+(?:previously\s+|just\s+|already\s+)?"
    r"(?:stopped\s+at|saw|viewed|visited|passed|left|were\s+at|encountered|"
    r"observed|glimpsed|paused\s+at|looked\s+at)\b"
    r"[^.?!]*?\b(?:a\s+moment\s+ago|just\s+now|moments?\s+ago|earlier|previously|"
    r"a\s+(?:few\s+)?(?:moments?|minutes?)\s+ago)?\b|"
    r"\b(?:a\s+moment\s+ago|just\s+a\s+moment\s+ago|moments?\s+ago)\b|"
    r"(?:which|that)\s+(?:we|you)\s+(?:just|previously|earlier)\s+"
    r"(?:saw|left|visited|passed|encountered|observed)|"
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


# [D636, Michael 2026-10-08] Callbacks to earlier stops are CONTINUITY, welcome in moderation:
# "if it is done in a couple of instances in a tour, it provides continuity". The Uffizi 488
# defect was frequency plus stock wording, not the callbacks. Policy:
#   * stock recency phrasing ("a moment ago", "just now", "you just saw") is always dropped;
#   * any other callback (a named earlier work, a thematic echo) is kept up to a per-tour
#     budget of max(1, (n_stops + 1) // 3): 3 stops → 1, 5 → 2, 8 → 3.
_STOCK_RECENCY_RE = re.compile(
    r"(?i)\b(?:a\s+moment\s+ago|just\s+a\s+moment\s+ago|moments?\s+ago|just\s+now|"
    r"a\s+(?:few\s+)?minutes?\s+ago|you\s+just\s+(?:saw|left|visited|passed|stopped\s+at)|"
    r"(?:which|that)\s+(?:we|you)\s+just\s+(?:saw|left|visited|passed))\b")


def callback_budget(n_stops: int) -> int:
    return max(1, (int(n_stops or 0) + 1) // 3)


def limit_thematic_bridges(
        ordered_units: List[Dict],
        max_bridges: Optional[int] = None) -> Tuple[List[Dict], List[Dict]]:
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
    if max_bridges is None:
        max_bridges = callback_budget(len(ordered_units))
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
                if _STOCK_RECENCY_RE.search(sent):
                    dropped.append({
                        "stop": stop_num, "sentence": sent.strip(),
                        "reason": "stock recency callback"})
                    continue
                is_callback = bool(_PREV_STOP_RECAP_RE.search(sent)
                                   or _THEMATIC_BRIDGE_RE.search(sent))
                if is_callback:
                    if bridges_kept >= max_bridges:
                        dropped.append({
                            "stop": stop_num, "sentence": sent.strip(),
                            "reason": "callback over the per-tour budget"})
                        continue
                    bridges_kept += 1
                kept.append(sent)
            out_paras.append(" ".join(kept).strip())
        nu["narration"] = "\n\n".join(p for p in out_paras if p.strip()).strip()
        new_units.append(nu)
    return new_units, dropped


# ─── [LOCAL-627 defect 9] Text-level recap guard (normal delivery path) ───────
#
# limit_thematic_bridges operates on stop-unit dicts in the POOL assembly. The
# normal generate_tour_text path delivers assembled TEXT (never units), so a
# previous-stop recap on that path ("…his 'Leda col cigno' that you previously
# encountered", "…you observed earlier") was not caught. This text-level guard
# walks the delivered tour stop by stop and applies the SAME policy: drop every
# previous-stop recap sentence and every thematic bridge beyond the first.

_TEXT_STOP_HEADER_RE = re.compile(r'(?mi)^(Stop\s+\d+:\s*.+)$')
_TEXT_FIELD_LINE_RE = re.compile(
    r'(?mi)^(?:Address|Coordinates|Directions|Sources|Museum Information|'
    r'Type/Specialty|Specific Examples|Operational Details):')


def limit_thematic_bridges_in_text(tour_text: str,
                                   max_bridges: Optional[int] = None) -> Tuple[str, int]:
    """Apply the recap / one-bridge policy to a delivered tour's TEXT.

    Returns ``(cleaned_text, n_dropped)``. Walks each stop's prose paragraphs
    (field/header lines preserved verbatim), drops every previous-stop recap
    sentence, and keeps at most ``max_bridges`` thematic bridges tour-wide.
    Deterministic; the Orientation line's prose is included (a recap can live
    there too), but structured field lines are untouched.
    """
    if not tour_text:
        return tour_text or "", 0
    if max_bridges is None:
        max_bridges = callback_budget(len(_TEXT_STOP_HEADER_RE.findall(tour_text)))
    bridges_kept = 0
    dropped = 0
    out_lines: List[str] = []
    for raw in tour_text.split("\n"):
        stripped = raw.strip()
        if (not stripped or _TEXT_STOP_HEADER_RE.match(stripped)
                or _TEXT_FIELD_LINE_RE.match(stripped)):
            out_lines.append(raw)
            continue
        # A prose line (may be an "Orientation: ..." lead or a narration paragraph).
        lead = ""
        body = raw
        om = re.match(r'(?i)^(\s*orientation:\s*)', raw)
        if om:
            lead = raw[:om.end()]
            body = raw[om.end():]
        kept_sents: List[str] = []
        for sent in _split_sentences(body):
            if _STOCK_RECENCY_RE.search(sent):
                dropped += 1
                continue
            if _PREV_STOP_RECAP_RE.search(sent) or _THEMATIC_BRIDGE_RE.search(sent):
                if bridges_kept >= max_bridges:
                    dropped += 1
                    continue
                bridges_kept += 1
            kept_sents.append(sent)
        new_body = " ".join(kept_sents).strip()
        if lead or new_body:
            out_lines.append((lead + new_body).rstrip())
    out = "\n".join(out_lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out, dropped


# ─── [LOCAL-634] Callback to an UNSEEN work/artist ────────────────────────────
#
# D636 keeps real callbacks ("a couple per tour, for continuity"). But a callback
# may name ONLY artists and works the listener actually SAW — i.e. ones delivered
# as stops in THIS tour. Reina Sofía (tour 505) shipped:
#
#     "Picasso and Braque, whose works you have already seen"
#
# No Braque was delivered. The listener is told they saw a work that was never in
# the tour — the same phantom as a cross-reference to an absent stop title, but
# the entity named is an ARTIST, caught by neither strip_phantom_references
# (title phrases only) nor limit_thematic_bridges (frequency only). This guard
# drops a callback CLAUSE/sentence that asserts the listener already saw an
# artist or title that is NOT among the delivered stops.

# A "you already saw it" callback predicate: the sentence CLAIMS prior viewing.
_SEEN_CALLBACK_RE = re.compile(
    r"(?i)\b("
    r"(?:whose\s+works?\s+)?you\s+(?:have\s+)?already\s+seen|"
    r"you\s+(?:have\s+)?(?:already\s+)?(?:seen|viewed|encountered|met|observed|"
    r"passed|glimpsed|visited|saw)\b[^.?!]*?\b(?:earlier|already|"
    r"(?:previously|before)(?:\s+on\s+(?:this|your)\s+tour)?)|"
    r"(?:as|like)\s+you\s+(?:have\s+)?(?:already\s+)?(?:seen|saw|viewed|"
    r"encountered)\b|"
    r"(?:which|whom|whose\s+works?)\s+you\s+(?:have\s+)?already\s+(?:seen|met)|"
    r"you\s+(?:have\s+)?(?:just\s+)?(?:seen|viewed)\s+(?:works?\s+)?by"
    r")\b")

# ─── [LOCAL-635] Generalised recall phrase ───────────────────────────────────
#
# LOCAL-634 (_SEEN_CALLBACK_RE above) only caught "whose works you have already
# seen". Bench R2 showed two more recall shapes that reference a work NEVER
# delivered — not an artist-missing case, but a recall that resolves to NOTHING
# the listener was given:
#
#   Uffizi 488:  "…so distinct from the completed works you have already
#                 encountered"   — generic "completed works", no delivered title.
#   Marmottan 514: "the 1985 daylight theft you encountered at …"
#                 — recall of an EVENT that no earlier stop ever narrated.
#
# Michael's rule: ANY recall phrase (you may recall / you encountered / you saw /
# seen earlier / met earlier) must refer to a DELIVERED stop's TITLE or ARTIST,
# naming it in the SAME clause, BEFORE the recall verb (so "Botticelli's
# Adorazione dei Magi, which you may recall" is anchored, but a bare "the works
# you have already encountered" is not). Otherwise the clause is dropped. This
# mirrors the D638 ``recall_unseen_work`` detector, which fails a recall verb
# with no delivered title in the ≤80 chars that precede it. D636 callbacks that
# DO name a delivered stop stay.
#
# A recall VERB phrase, matched with its start position so we can inspect the
# text that PRECEDES it in the sentence (the detector's ≤80-char window). Kept
# in lock-step with the detector's own verb list.
_RECALL_PHRASE_RE = re.compile(
    r"(?i)\b(you\s+may\s+recall|"
    r"you\s+(?:have\s+)?(?:already\s+)?"
    r"(?:encountered|saw|seen|observed|met)"
    r"(?:\s+earlier|\s+before|\s+previously)?)\b")

# Window (characters) of text before the recall verb in which a delivered title
# or artist must appear for the recall to be anchored. Matches the detector's 80.
_RECALL_ANCHOR_WINDOW = 80

# A proper-noun run in a sentence (artist or title): a capitalised word, possibly
# multi-word with connectors, excluding a lone sentence-initial capital handled
# by the caller's position check.
_PROPER_RUN_RE = re.compile(
    r"\b([A-Z\u00C0-\u017F][\w'\u00C0-\u017F.\-]*"
    r"(?:\s+(?:de|du|des|la|le|les|van|von|di|della|del|y)?\s*"
    r"[A-Z\u00C0-\u017F][\w'\u00C0-\u017F.\-]*)*)\b")

# Capitalised function words that start a sentence but are not names.
_NAME_STOPWORDS = frozenset(w.lower() for w in (
    "The", "A", "An", "This", "That", "These", "Those", "It", "He", "She",
    "They", "Their", "His", "Her", "You", "Your", "We", "Our", "In", "On",
    "At", "By", "For", "From", "To", "With", "As", "And", "But", "Or", "Of",
    "Here", "There", "Now", "Then",
    "Stand", "Notice", "Look", "Step", "Move", "Turn", "Consider", "Imagine",
    "Like", "Recall", "Both", "Each", "Earlier", "Previously", "Unlike",
))


def _delivered_name_tokens(titles: List[str]) -> set:
    """Build the set of delivered artist/title tokens (normalised words) from the
    stop titles. A title is often "Artist: Work" or "Work by Artist"; we fold in
    every word of both the artist and the work so a callback naming either the
    artist or the title is recognised as delivered."""
    toks: set = set()
    for t in titles or []:
        if not t:
            continue
        core = _title_core(t)
        for piece in (t, core):
            for w in re.findall(r"[A-Za-z\u00C0-\u017F]{3,}", _norm(piece)):
                toks.add(w)
        # Artist side of "Artist: Work".
        if ":" in t:
            for w in re.findall(r"[A-Za-z\u00C0-\u017F]{3,}", _norm(t.split(":", 1)[0])):
                toks.add(w)
        # "... by Artist".
        bm = re.search(r"(?i)\bby\s+(.+)$", t)
        if bm:
            for w in re.findall(r"[A-Za-z\u00C0-\u017F]{3,}", _norm(bm.group(1))):
                toks.add(w)
    return toks


def _delivered_title_norms(titles: List[str]) -> List[str]:
    """[LOCAL-635] Normalised delivered titles (full title + work core) for the
    recall-anchor window check. Mirrors the delivered_norms built in
    strip_phantom_references."""
    norms: List[str] = []
    for t in titles or []:
        t = (t or "").strip()
        if not t:
            continue
        norms.append(_norm(t))
        core = _title_core(t)
        if core:
            norms.append(_norm(core))
    return [d for d in norms if d]


def _named_entities_in_sentence(sentence: str) -> List[str]:
    """Proper-noun names in a sentence, excluding sentence-initial function words
    and quoted strings handled elsewhere. Returns display forms."""
    out: List[str] = []
    for m in _PROPER_RUN_RE.finditer(sentence or ""):
        run = m.group(1).strip()
        # Skip a run that is only a stopword (e.g. sentence-initial "The").
        words = run.split()
        if len(words) == 1 and words[0].lower() in _NAME_STOPWORDS:
            continue
        out.append(run)
    return out


def _recall_is_anchored(sentence: str, delivered_tokens: set,
                        delivered_norms: List[str]) -> bool:
    """[LOCAL-635] True when every recall verb phrase in ``sentence`` is anchored
    to a delivered stop — i.e. a delivered TITLE or ARTIST token appears in the
    text BEFORE the recall verb (within ``_RECALL_ANCHOR_WINDOW`` chars, matching
    the D638 ``recall_unseen_work`` detector). A sentence with no recall verb is
    trivially anchored (returns True). A recall whose preceding window names no
    delivered entity is UNanchored → returns False, so the caller drops it.

    "Anchored" means the ≤80-char window before the verb contains either a
    normalised delivered title (any direction of containment) or at least one
    multi-letter delivered artist/title token. "the completed works you have
    already encountered" (488) and "the 1985 daylight theft you encountered at…"
    (514) both have windows naming no delivered work → unanchored."""
    s = sentence or ""
    found_recall = False
    for m in _RECALL_PHRASE_RE.finditer(s):
        found_recall = True
        start = m.start()
        window = s[max(0, start - _RECALL_ANCHOR_WINDOW):start]
        wn = _norm(window)
        if not wn:
            return False
        # (a) a delivered title appears (either direction of containment).
        anchored = any(dn and (dn in wn or wn in dn) for dn in delivered_norms)
        # (b) or a delivered artist/title token (3+ letters) appears in the window.
        if not anchored:
            win_words = set(re.findall(r"[A-Za-z\u00C0-\u017F]{3,}", wn))
            anchored = bool(win_words & delivered_tokens)
        if not anchored:
            return False
    return True if found_recall else True


def _callback_names_unseen(sentence: str, delivered_tokens: set,
                           delivered_norms: Optional[List[str]] = None) -> Optional[str]:
    """When ``sentence`` is a recall/"you already saw X" callback that resolves to
    something NOT delivered, return the offending phrase (the first unseen entity,
    or a short marker for an unanchored recall). Otherwise None.

    Two cases, both deterministic:
      * [LOCAL-634] a "you already saw" callback that NAMES an artist/title whose
        words are not all in the delivered token set ("Picasso and Braque, whose
        works you have already seen" with no Braque);
      * [LOCAL-635] ANY recall phrase (you may recall / you encountered / you
        saw / seen earlier / met earlier) that is NOT anchored to a delivered
        title or artist BEFORE the verb ("the completed works you have already
        encountered"; "the 1985 daylight theft you encountered at…").

    A name is "seen" when ALL of its significant word tokens appear among the
    delivered tokens (so "Pablo Picasso" matches a delivered "Picasso" title and
    "Braque" does not match anything delivered)."""
    # [LOCAL-634] named-but-undelivered artist/title in a seen-callback.
    if _SEEN_CALLBACK_RE.search(sentence or ""):
        for ent in _named_entities_in_sentence(sentence):
            words = [w for w in re.findall(r"[A-Za-z\u00C0-\u017F]{3,}", _norm(ent))]
            if not words:
                continue
            if all(w in delivered_tokens for w in words):
                continue  # every token of this name was delivered → a real callback
            # At least one word of this named entity was never delivered.
            return ent
    # [LOCAL-635] generalised unanchored recall phrase.
    if delivered_norms is not None and _RECALL_PHRASE_RE.search(sentence or ""):
        if not _recall_is_anchored(sentence, delivered_tokens, delivered_norms):
            m = _RECALL_PHRASE_RE.search(sentence or "")
            return f"unanchored recall: '{m.group(1).strip()}'" if m else "unanchored recall"
    return None


def strip_unseen_callbacks(
        ordered_units: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Drop any sentence that tells the listener they already saw an artist/title
    NOT delivered in this tour. Returns (new_units, dropped). Mirrors
    strip_phantom_references' shape; pure and deterministic."""
    _titles = [(u.get("title") or "") for u in ordered_units]
    delivered_tokens = _delivered_name_tokens(_titles)
    delivered_norms = _delivered_title_norms(_titles)
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
                unseen = _callback_names_unseen(sent, delivered_tokens,
                                                delivered_norms)
                if unseen is not None:
                    dropped.append({
                        "stop": stop_num, "sentence": sent.strip(),
                        "reason": "callback to an artist/work not delivered",
                        "unseen": unseen})
                    continue
                kept.append(sent)
            out_paras.append(" ".join(kept).strip())
        nu["narration"] = "\n\n".join(p for p in out_paras if p.strip()).strip()
        new_units.append(nu)
    return new_units, dropped


def strip_unseen_callbacks_in_text(tour_text: str) -> Tuple[str, int]:
    """Text-level sibling of strip_unseen_callbacks for the normal delivery path
    (tour 505 shipped the Braque callback on this path). Walks each stop, derives
    the delivered artist/title tokens from the Stop headers, and drops any
    sentence that claims the listener already saw an undelivered artist/title.
    Field/header lines are preserved verbatim. Returns (cleaned_text, n_dropped).
    """
    if not tour_text:
        return tour_text or "", 0
    titles = [m.group(1) for m in re.finditer(
        r'(?mi)^Stop\s+\d+:\s*(.+?)\s*$', tour_text)]
    delivered_tokens = _delivered_name_tokens(titles)
    delivered_norms = _delivered_title_norms(titles)
    dropped = 0
    out_lines: List[str] = []
    for raw in tour_text.split("\n"):
        stripped = raw.strip()
        if (not stripped or _TEXT_STOP_HEADER_RE.match(stripped)
                or _TEXT_FIELD_LINE_RE.match(stripped)):
            out_lines.append(raw)
            continue
        lead = ""
        body = raw
        om = re.match(r'(?i)^(\s*orientation:\s*)', raw)
        if om:
            lead = raw[:om.end()]
            body = raw[om.end():]
        kept_sents: List[str] = []
        for sent in _split_sentences(body):
            if _callback_names_unseen(sent, delivered_tokens,
                                      delivered_norms) is not None:
                dropped += 1
                continue
            kept_sents.append(sent)
        new_body = " ".join(kept_sents).strip()
        if lead or new_body:
            out_lines.append((lead + new_body).rstrip())
    out = "\n".join(out_lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out, dropped


# ─── [LOCAL-640] Comparison to an UNSEEN work ─────────────────────────────────
#
# The recall guards above catch "you may recall / you saw / already encountered".
# Bench R8 showed a THIRD cross-reference shape that names a work the listener was
# never given — a COMPARISON, not a recall:
#
#   Ny Carlsberg Glyptotek 532:
#     "…echoes the way Gauguin, in the 'Græshopperne og myrerne', …"
#   Courtauld 485:
#     "It echoes the social facades …"
#
# "echoes the way <Artist>, in '<Title>'" compares the current stop to a work
# ('Græshopperne og myrerne') that is NOT a delivered stop. The listener is told
# "this echoes that other work" when they have no "that other work" — the same
# phantom as a recall of an absent stop, through a comparison verb the recall
# regexes do not cover.
#
# D636 is explicit that a comparison to a DELIVERED stop is welcome continuity.
# So the rule is identical to strip_phantom_references: a comparison that NAMES a
# title (quoted, or introduced by "such as"/"like"/"as in") which is NOT among
# the delivered titles is dropped; a comparison to a delivered title stays; a
# comparison that names no concrete work is left to other guards (we never drop
# on a bare "echoes the social facades" — nothing concrete to falsify). This
# reuses _candidate_titles / _is_delivered so "delivered-ness" is decided exactly
# as the phantom-reference guard decides it.

# Comparison verbs that assert the current stop is LIKE some other work. The verb
# itself is the cue; a named undelivered title in the SAME sentence is the drop
# condition.
_COMPARISON_CUE_RE = re.compile(
    r"(?i)\b("
    r"echoes?|echoing|mirrors?|mirroring|evokes?|evoking|recalls?|"
    r"parallels?|paralleling|resembles?|resembling|reminiscent\s+of|"
    r"harks?\s+back\s+to|harkens?\s+back\s+to|in\s+the\s+manner\s+of|"
    r"much\s+like|just\s+as|akin\s+to|as\s+in"
    r")\b")


def _comparison_names_unseen(sentence: str,
                             delivered_norms: List[str]) -> Optional[str]:
    """When ``sentence`` is a comparison ("echoes/mirrors/… the way X, in
    '<Title>'") that NAMES a title NOT among the delivered titles, return that
    phantom title; otherwise None. A comparison naming no concrete title, or one
    naming a DELIVERED title, returns None (kept)."""
    if not _COMPARISON_CUE_RE.search(sentence or ""):
        return None
    for cand in _candidate_titles(sentence):
        if not _is_delivered(cand, delivered_norms):
            return cand
    return None


def _delivered_norms_from_units(ordered_units: List[Dict]) -> List[str]:
    """Normalised delivered titles + work cores from stop-unit dicts (mirrors the
    set strip_phantom_references builds)."""
    out: List[str] = []
    for u in ordered_units:
        t = (u.get("title") or "").strip()
        if not t:
            continue
        out.append(_norm(t))
        core = _title_core(t)
        if core:
            out.append(_norm(core))
    return [d for d in out if d]


def strip_unseen_comparisons(
        ordered_units: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """[LOCAL-640] Drop every sentence that compares the current stop to a NAMED
    work not delivered in this tour ("echoes the way Gauguin, in the
    'Græshopperne og myrerne'"). Returns (new_units, dropped). Comparisons to a
    delivered title are kept (D636). Pure and deterministic; mirrors
    strip_phantom_references' shape."""
    delivered_norms = _delivered_norms_from_units(ordered_units)
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
                phantom = _comparison_names_unseen(sent, delivered_norms)
                if phantom is not None:
                    dropped.append({
                        "stop": stop_num, "sentence": sent.strip(),
                        "reason": "comparison to a work not in this tour",
                        "phantom": phantom})
                    continue
                kept.append(sent)
            out_paras.append(" ".join(kept).strip())
        nu["narration"] = "\n\n".join(p for p in out_paras if p.strip()).strip()
        new_units.append(nu)
    return new_units, dropped


def strip_unseen_comparisons_in_text(tour_text: str) -> Tuple[str, int]:
    """Text-level sibling of strip_unseen_comparisons for the normal delivery
    path (Ny Carlsberg 532 shipped the Gauguin comparison on this path). Walks
    each stop, derives delivered titles from the Stop headers, and drops any
    sentence that compares the stop to a NAMED undelivered work. Field/header
    lines are preserved verbatim. Returns (cleaned_text, n_dropped)."""
    if not tour_text:
        return tour_text or "", 0
    titles = [m.group(1) for m in re.finditer(
        r'(?mi)^Stop\s+\d+:\s*(.+?)\s*$', tour_text)]
    delivered_norms: List[str] = []
    for t in titles:
        t = (t or "").strip()
        if not t:
            continue
        delivered_norms.append(_norm(t))
        core = _title_core(t)
        if core:
            delivered_norms.append(_norm(core))
    delivered_norms = [d for d in delivered_norms if d]
    dropped = 0
    out_lines: List[str] = []
    for raw in tour_text.split("\n"):
        stripped = raw.strip()
        if (not stripped or _TEXT_STOP_HEADER_RE.match(stripped)
                or _TEXT_FIELD_LINE_RE.match(stripped)):
            out_lines.append(raw)
            continue
        lead = ""
        body = raw
        om = re.match(r'(?i)^(\s*orientation:\s*)', raw)
        if om:
            lead = raw[:om.end()]
            body = raw[om.end():]
        kept_sents: List[str] = []
        for sent in _split_sentences(body):
            if _comparison_names_unseen(sent, delivered_norms) is not None:
                dropped += 1
                continue
            kept_sents.append(sent)
        new_body = " ".join(kept_sents).strip()
        if lead or new_body:
            out_lines.append((lead + new_body).rstrip())
    out = "\n".join(out_lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out, dropped
