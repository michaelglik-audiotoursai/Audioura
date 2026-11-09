#!/usr/bin/env python3
"""thin_stop_delivery.py — LOCAL-873B: the post-narration thin check.

LOCAL-873 counted "thin" BEFORE narration (at the LOCAL-872C evidence point) and
escalated only stops that were thin then. LEAD read the DELIVERED tour and found
that was not enough:

  * Bạch Đằng Pier had >= 3 sourced specifics at the pre-narration point (its
    geo-gated Wikipedia evidence), so LOCAL-873 did NOT escalate it — yet the
    DELIVERED body carried only ~2 concrete facts (end of the war; boats to Củ
    Chi). The rest was mood ("a tangible boundary where history pivoted").
  * Ho Chi Minh City Hall delivered 3 sentences.
  * Nguyễn Văn Bình Book Street WAS escalated to 13 facts, but the gates and the
    fact-sheet verify dropped them, leaving two content sentences in the body.

Michael's bar is on the DELIVERED text, so the check must be too. This module:

  1. Parses the assembled tour into "Stop N:" blocks (the same block grammar the
     855B final scrub and user_stop_verify use).
  2. For each stop, counts the SOURCED SPECIFICS actually present in the
     delivered body (a body sentence that carries a year or a concrete cue AND is
     traceable to a known/escalation fact, OR simply carries a concrete specific
     when no fact list is supplied). This is `count_delivered_specifics`.
  3. If a stop has fewer than ``MIN_SPECIFICS`` (3) and it was NOT already
     escalated, it ESCALATES NOW (``thin_stop_search.escalate_thin_stop``, same
     cost cap ~$0.01/stop). Whether escalated now or earlier, it then REBUILDS
     the body ONCE from the sourced facts: it appends plain fact sentences (each
     traceable to a fact) until the body carries at least ``MIN_SPECIFICS``
     fact-traceable sentences, without exceeding the facts available.

The rebuild is DETERMINISTIC — it composes from facts already extracted (no new
LLM call for the rewrite), so it adds no cost beyond a possible one-time
escalation. Everything is injectable (``escalate_fn``, ``facts_by_title``) so the
module is fully offline-testable; pure helpers never raise.
"""
from __future__ import annotations

import os
import re
from typing import Callable, Dict, List, Optional, Tuple

from sentence_split import split_sentences
from thin_stop_search import count_specifics, fold

__all__ = [
    "MIN_SPECIFICS", "count_delivered_specifics", "fact_sentences",
    "rebuild_thin_delivered_stops",
]

MIN_SPECIFICS = int(os.environ.get("THIN_DELIVERED_MIN_SPECIFICS", "3"))

# Block grammar — mirrors user_stop_narration / user_stop_verify exactly.
_STOP_HDR_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+?)\s*$")
_FIELD_LINE_RE = re.compile(
    r"(?mi)^(Coordinates|Type/Specialty|Specific Examples|Directions|"
    r"Tour-Category|Address|Operational Details):")
_ORIENT_RE = re.compile(r"(?i)^orientation:")
_DIRECTIONS_RE = re.compile(r"(?i)^directions:")

# A year or a concrete cue — the same notion of "specific" as thin_stop_search,
# used to decide whether a DELIVERED body sentence carries a sourced fact.
_YEAR_RE = re.compile(r"(?<![\d.,])(1[0-9]{3}|20[0-9]{2})(?!\d)")
_COORD_RE = re.compile(r"(?mi)^Coordinates:\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")
_TYPE_RE = re.compile(r"(?mi)^Type/Specialty:\s*(.+?)\s*$")
_SPECIFIC_CUE = re.compile(
    r"(?i)\b(built|construct\w*|completed|opened|founded|established|designed|"
    r"architect|renovat\w*|named after|named for|length|metres?|meters?|"
    r"kilomet\w*|wide|high|tall|capacity|population|dynasty|century|war|battle|"
    r"river|bridge|statue|monument|trade|port|ferry|market|temple|emperor|king|"
    r"french|colonial|reunification|stall|book|cafe|café|publisher|rating|"
    r"review|floor|storey|story building|apartment|band|events?)\b")


def _is_specific(sentence: str) -> bool:
    s = (sentence or "").strip()
    if len(s) < 15:
        return False
    return bool(_YEAR_RE.search(s) or _SPECIFIC_CUE.search(s))


def _fact_texts(facts) -> List[str]:
    out: List[str] = []
    for f in facts or []:
        if isinstance(f, dict):
            t = str(f.get("text") or f.get("fact") or f.get("snippet") or "")
        else:
            t = str(f or "")
        t = t.strip()
        if t:
            out.append(t)
    return out


def _content_tokens(text: str) -> set:
    return {w for w in fold(text).split() if len(w) >= 4}


def _traceable(sentence: str, fact_token_sets: List[set]) -> bool:
    """True when a body sentence shares enough content with SOME fact to be
    considered drawn from it (>= 3 content tokens in common). With no facts
    supplied, any specific sentence counts (back-compat / standalone use)."""
    if not fact_token_sets:
        return _is_specific(sentence)
    stoks = _content_tokens(sentence)
    if not stoks:
        return False
    for ftoks in fact_token_sets:
        if len(stoks & ftoks) >= 3:
            return True
    return False


def count_delivered_specifics(body: str, facts=None) -> int:
    """Count the SOURCED specifics present in a delivered body.

    A body sentence counts when it carries a year/concrete cue AND (when a fact
    list is supplied) is traceable to one of the facts. Deterministic.

    With NO fact list supplied, this delegates to thin_stop_search.count_specifics
    over the body sentences — the SAME metric the live PASS check uses — so the
    rebuild trigger and the acceptance measure never disagree (the Pier shipped 7
    body sentences but only 2 sourced specifics; this must see 2, not a looser
    count)."""
    sents = split_sentences(body or "")
    fact_texts = _fact_texts(facts)
    if not fact_texts:
        return count_specifics(sents)
    fact_token_sets = [_content_tokens(t) for t in fact_texts]
    fact_token_sets = [s for s in fact_token_sets if s]
    n = 0
    seen = set()
    for sent in sents:
        if not _is_specific(sent):
            continue
        if fact_token_sets and not _traceable(sent, fact_token_sets):
            continue
        key = fold(sent)[:80]
        if key in seen:
            continue
        seen.add(key)
        n += 1
    return n


_FIELD_LABEL_RE = re.compile(
    r"(?i)^(address|coordinates|type/specialty|specific examples|directions|"
    r"operational details|sources|orientation|tour-category)\s*:\s*")


def _is_truncated(text: str) -> bool:
    """A fact cut mid-sentence (ends with '...', an ellipsis, a trailing comma,
    a dangling conjunction/preposition, or a mid-list clause) is unusable as a
    delivered sentence."""
    s = (text or "").strip()
    if not s:
        return True
    if s.endswith("...") or s.endswith("…") or s.endswith(",") or s.endswith(";"):
        return True
    # ends on a number + nothing ("each side has 9 floors," already caught; also
    # "Originally built in 1960's" with no real end) — require a terminal stop OR
    # a reasonably complete clause.
    core = s.rstrip(".!?")
    toks = core.split()
    last = toks[-1].lower().strip(",;:") if toks else ""
    _DANGLERS = {"and", "or", "but", "from", "to", "of", "with", "the", "a",
                 "an", "in", "on", "for", "as", "that", "which", "by", "at",
                 "including", "such", "like", "each", "both"}
    if last in _DANGLERS:
        return True
    return False


def _strip_field_label(text: str) -> str:
    """Remove a leading 'Address:' / 'Coordinates:' style label that would
    collide with the stop-block field grammar if appended to the body."""
    return _FIELD_LABEL_RE.sub("", (text or "").strip()).strip()


def fact_sentences(facts, limit: int = 6, require_specific: bool = True) -> List[str]:
    """Turn sourced facts into plain delivered-body sentences. Each fact is one
    sentence; the extractor already returns a single sentence, so this normalises
    terminal punctuation. Drops TRUNCATED facts and strips any leading field
    label (a fact beginning "Address: …" must not be mistaken for a block field
    line). With ``require_specific`` (the default), keeps only facts carrying a
    year/concrete cue — those count toward sourced-specific coverage. With
    ``require_specific=False``, also keeps clean, substantial venue facts that
    lack a hard cue as sentence-floor filler. Deduped."""
    out: List[str] = []
    seen = set()
    for t in _fact_texts(facts):
        s = _strip_field_label(t)
        if _is_truncated(s):
            continue
        # a fact that still carries an embedded field-label grammar is unreliable
        if _FIELD_LABEL_RE.search(s):
            continue
        if require_specific and not _is_specific(s):
            continue
        if not require_specific and len(s) < 25:
            continue
        if not s.endswith((".", "!", "?")):
            s += "."
        key = fold(s)[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= limit:
            break
    return out


def _parse_blocks(tour_text: str):
    """Yield (header_line_index, stop_num, title, start, end) for each stop."""
    lines = tour_text.split("\n")
    headers = [(i, m) for i, ln in enumerate(lines)
               for m in [_STOP_HDR_RE.match(ln)] if m]
    for h_idx, (line_no, m) in enumerate(headers):
        start = line_no + 1
        end = headers[h_idx + 1][0] if h_idx + 1 < len(headers) else len(lines)
        yield line_no, m.group(1), m.group(2).strip(), start, end


def _body_line_indices(lines: List[str], start: int, end: int) -> List[int]:
    """Indices of the stop's standalone narration paragraphs (NOT the Orientation
    label line, field lines, Directions or Sources)."""
    out = []
    for i in range(start, end):
        ln = lines[i]
        s = ln.strip()
        if not s:
            continue
        if (_FIELD_LINE_RE.match(ln) or _STOP_HDR_RE.match(ln)
                or _ORIENT_RE.match(s) or _DIRECTIONS_RE.match(s)
                or s.lower().startswith("sources")):
            continue
        out.append(i)
    return out


def rebuild_thin_delivered_stops(
        tour_text: str, location: str = "", *,
        facts_by_title: Optional[Dict[str, List]] = None,
        escalate_fn: Optional[Callable] = None,
        pins_by_title: Optional[Dict[str, Tuple[float, float]]] = None,
        aliases_by_title: Optional[Dict[str, List[str]]] = None,
        types_by_title: Optional[Dict[str, str]] = None,
        min_specifics: int = MIN_SPECIFICS,
        min_sentences: int = 5,
        trigger_sentences: int = 4,
        fact_filter: Optional[Callable] = None,
        cost_cap: float = 0.01, log: Optional[Callable] = None,
        ) -> Tuple[str, Dict]:
    """Post-narration thin check on the DELIVERED text.

    For each stop whose delivered body has fewer than ``min_specifics`` sourced
    specifics OR fewer than ``min_sentences`` content sentences: if we have no
    facts for it yet, escalate ONCE (``escalate_fn`` or
    ``thin_stop_search.escalate_thin_stop``, cost-capped); then append fact
    sentences so the body carries at least ``min_specifics`` fact-traceable
    sentences AND at least ``min_sentences`` content sentences (bounded by the
    facts available). Returns ``(new_text, report)``.

    Deterministic rebuild (no LLM for the rewrite). Never raises."""
    report = {
        "ran": True, "checked": 0, "rebuilt": 0, "escalated": 0,
        "added_cost_usd": 0.0, "stops": [],
    }
    log = log or (lambda *_a, **_k: None)
    if not tour_text or not tour_text.strip():
        report["ran"] = False
        return tour_text or "", report
    facts_by_title = dict(facts_by_title or {})
    lines = tour_text.split("\n")

    def _facts_for(title):
        for k, v in facts_by_title.items():
            if fold(k) == fold(title):
                return v
        return None

    try:
        blocks = list(_parse_blocks(tour_text))
    except Exception:
        report["ran"] = False
        return tour_text, report

    for _hdr, stop_num, title, start, end in reversed(blocks):
        report["checked"] += 1
        body_idx = _body_line_indices(lines, start, end)
        body_text = "\n".join(lines[i] for i in body_idx)
        facts = _facts_for(title)
        before = count_delivered_specifics(body_text, facts)
        body_sent_n = len(split_sentences(body_text))
        # Trigger: thin on sourced specifics, OR fewer than trigger_sentences
        # content sentences. (The trigger is 4 so a healthy 4-sentence stop is not
        # disturbed; once a stop IS rebuilt it is filled to min_sentences=5 so a
        # rebuilt stop like Book Street clears the ticket's >= 5 bar.)
        if before >= min_specifics and body_sent_n >= trigger_sentences:
            continue

        # Escalate now if we have no facts for this stop yet.
        if not facts:
            _esc = escalate_fn
            if _esc is None and os.environ.get("THIN_STOP_SEARCH", "1").strip() != "0":
                try:
                    import thin_stop_search as _ts
                    _esc = _ts.escalate_thin_stop
                except Exception:
                    _esc = None
            if _esc is not None:
                _blk = "\n".join(lines[start:end])
                pin = (pins_by_title or {}).get(title)
                if pin is None:
                    _cm = _COORD_RE.search(_blk)
                    if _cm:
                        try:
                            pin = (float(_cm.group(1)), float(_cm.group(2)))
                        except Exception:
                            pin = None
                aliases = (aliases_by_title or {}).get(title) or []
                ptype = (types_by_title or {}).get(title) or ""
                if not ptype:
                    _tm = _TYPE_RE.search(_blk)
                    if _tm:
                        ptype = _tm.group(1).strip()
                try:
                    rep = _esc(title, location, existing_facts=[], pin=pin,
                               aliases=aliases, places_type=ptype,
                               cost_cap=cost_cap)
                except Exception as e:
                    log(f"  [LOCAL-873B] delivered escalate skipped {title!r}: {e}")
                    rep = None
                if rep and rep.get("facts"):
                    facts = rep["facts"]
                    facts_by_title[title] = facts
                    report["escalated"] += 1
                    report["added_cost_usd"] += float(rep.get("cost_usd", 0.0) or 0.0)

        if not facts:
            continue

        # Which fact sentences are not already in the body? Compare on DISTINCTIVE
        # content only — strip the venue-name tokens (which repeat in every
        # sentence of the stop) and generic words, or a fact that merely names the
        # venue is wrongly judged a duplicate (Book Street: every fact shares
        # {nguyen, binh, book, street} with the body, so all 14 were filtered).
        _name_toks = {w for w in fold(title).split() if len(w) >= 4}
        _GENERIC = {"this", "that", "with", "from", "into", "here", "there",
                    "street", "city", "book", "place", "space", "known", "years",
                    "recent", "which", "where", "their", "these", "those"}

        def _distinctive(s):
            return {w for w in _content_tokens(s)
                    if w not in _name_toks and w not in _GENERIC}

        present = [_distinctive(s) for s in split_sentences(body_text)]
        additions = []
        spec_added = 0

        def _try_add(candidates, *, counts_as_specific):
            nonlocal spec_added
            for fs in candidates:
                if (before + spec_added >= min_specifics
                        and body_sent_n + len(additions) >= min_sentences):
                    return
                if fact_filter is not None:
                    try:
                        if not fact_filter(title, fs, "\n".join(lines[start:end])):
                            continue
                    except Exception:
                        pass
                ftoks = _distinctive(fs)
                if ftoks and any(len(ftoks & p) >= 3 for p in present):
                    continue
                if fs in additions:
                    continue
                additions.append(fs)
                present.append(ftoks)
                if counts_as_specific:
                    spec_added += 1

        # Phase 1 — SPECIFIC facts (cover the >= min_specifics sourced-specific bar).
        _try_add(fact_sentences(facts, limit=min_sentences + 6,
                                require_specific=True), counts_as_specific=True)
        # Phase 2 — clean non-specific venue facts, only to reach the SENTENCE floor.
        if body_sent_n + len(additions) < min_sentences:
            _try_add(fact_sentences(facts, limit=min_sentences + 6,
                                    require_specific=False), counts_as_specific=False)
        if not additions:
            continue

        # Append the fact sentences to the stop's LAST body paragraph (or create
        # one just before Directions if the stop has no body paragraph).
        add_text = " ".join(additions)
        if body_idx:
            tgt = body_idx[-1]
            sep = "" if lines[tgt].rstrip().endswith((".", "!", "?")) else "."
            lines[tgt] = f"{lines[tgt].rstrip()}{sep} {add_text}".strip()
        else:
            # insert before the Directions line, else at end of block
            insert_at = end
            for i in range(start, end):
                if _DIRECTIONS_RE.match(lines[i].strip()):
                    insert_at = i
                    break
            lines.insert(insert_at, add_text)
            # indices after insert_at shift by 1; safe because we recompute blocks
            # only via stored start/end which we no longer use after this stop.
        report["rebuilt"] += 1
        report["stops"].append({
            "stop": stop_num, "title": title,
            "specifics_before": before,
            "specifics_after": before + spec_added,
            "added_sentences": len(additions),
        })
        log(f"  [LOCAL-873B] delivered-body thin check: stop {stop_num} "
            f"{title[:40]!r} had {before} sourced specific(s) (< {min_specifics}); "
            f"rebuilt from facts -> +{len(additions)} fact sentence(s)")

    report["added_cost_usd"] = round(report["added_cost_usd"], 6)
    return "\n".join(lines), report
