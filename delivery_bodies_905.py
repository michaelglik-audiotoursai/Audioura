"""[LOCAL-905] Never deliver a stop with no body; the closing's "That's N stops in all." equals the delivered count.

Applied to the FINAL delivered text of every path (including the pool). A stop with no content sentence is
refilled in the 904 order (its own evidence -> one clean sentence of a same-site neighbour -> the honest
D760 disclosure body) or, if no refill can be built, removed (stops renumbered). Pure and free; never raises.
"""
import re
from typing import Callable, Dict, List, Optional

_COUNT = re.compile(r"(?i)\bThat['\u2019]s\s+(\d+)\s+stops?\s+in\s+all\b")
_COUNT_ANY = re.compile(r"(?i)\bThat['\u2019]s\s+(\d+)\s+(stops?)\b")


def _rc():
    import route_content_896 as rc
    return rc


def _body_sentences(lines: List[str], last: bool, rc) -> List[int]:
    """Indices of prose lines that carry the stop's own body. On the last stop a single prose paragraph that
    holds the closing ("That's N stops") IS the closing, not a body."""
    idx = [i for i, ln in enumerate(lines)
           if i > 0 and ln.strip() and not rc._KEYED.match(ln) and not rc._CLOSING_LINE.match(ln.strip())]
    if last and len(idx) == 1 and _COUNT_ANY.search(lines[idx[0]]):
        return []
    return idx[:1] if last and idx else idx


def _has_content(lines: List[str], last: bool, rc) -> bool:
    for i in _body_sentences(lines, last, rc):
        for s in rc.split_sentences(lines[i]):
            if len(re.findall(r"[A-Za-z0-9']+", s)) >= 3 and not rc._CLOSING_LINE.match(s):
                return True
    return False


def _blocked_906f(title: str, sentence: str) -> bool:
    """[LOCAL-906F] The sentence repeats a claim a contradiction gate blocked: a refill never brings it back."""
    try:
        import key_fact_coverage as _kfc
        return bool(_kfc.is_denied(title, sentence, ""))
    except Exception:
        return False


def _bar_906k(s: str, title: str, blob: str, tour: Optional[str], log) -> bool:
    """[LOCAL-906K] True = the sentence fails the refill quality bar (logged)."""
    try:
        import refill_quality_906k as _k
        return _k.reject_logged(s, title, tour, log, "?", _k.source_of(s, blob, title), "", bool(blob))
    except Exception:  # pragma: no cover
        return False


def _own_evidence_sentence(title: str, ev_map: Dict[str, str], rc, tour: Optional[str] = None, log=None) -> Optional[str]:
    blob = ev_map.get(rc.fold(title)) or ""
    for s in rc.split_sentences(blob):
        if (6 <= len(s.split()) <= 40 and s[-1:] in ".!?" and not rc.is_fragment(s)
                and not rc.is_mood_filler(s, set()) and not _blocked_906f(title, s)
                and not _bar_906k(s, title, blob, tour, log)):
            return s
    return None


def ensure_bodies(text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                  log: Optional[Callable[[str], None]] = None) -> str:
    emit = log or (lambda _m: None)
    if not text or not isinstance(text, str):
        return text
    try:
        rc = _rc()
        blocks = rc._stop_blocks(text)
        if not blocks:
            return text
        try:   # [LOCAL-906H] no evidence passed -> the job's delivery-evidence store (filled by every producer)
            import delivery_evidence_906h as _de906h
            evidence_by_title = _de906h.resolve(evidence_by_title)
            _de906h.report(text, emit, evidence_by_title)
        except Exception:  # pragma: no cover
            pass
        try:   # [LOCAL-906F] removals first (blocked claims, promo, cross-stop conflicts ...): a stop they empty is refilled below
            import leftovers_906f as _c906f
            text = _c906f.run_pass(text, evidence_by_title, emit)
            blocks = rc._stop_blocks(text)
        except Exception as _e906f:  # pragma: no cover
            emit(f"  [LOCAL-906F] pre-pass skipped (non-fatal): {_e906f}")
        ev = dict(getattr(rc, "_EVIDENCE_904", {}) or {})
        ev.update({str(k): v for k, v in (evidence_by_title or {}).items()})
        ev_map = {rc.fold(k): v for k, v in ev.items()}
        out, pos, removed = [], 0, 0
        for k, (s, e, num, title) in enumerate(blocks):
            out.append(text[pos:s])
            pos = e
            block = text[s:e]
            lines = block.split("\n")
            last = k == len(blocks) - 1
            if _has_content(lines, last, rc):
                out.append(block)
                continue
            body = _own_evidence_sentence(title, ev_map, rc, text, emit)
            how = "own evidence"
            if not body:
                try:
                    import place_names_900 as pn
                    neigh = pn.neighbour_sentence(pn.short_place_name(title),
                                                  rc._neighbour_evidence(blocks, k, ev_map, text), rc.split_sentences)
                except Exception:
                    neigh = None
                if neigh and _bar_906k(neigh, title, "", text, emit):
                    neigh = None
                body, how = neigh, "neighbour sentence"
            if body and _blocked_906f(title, body):
                emit(f"  [LOCAL-906F] Stop {num}: refill sentence repeats a blocked claim -> not used")
                body = None
            if not body:
                try:
                    import strict_grounding_gate as sgg
                    body = " ".join(sgg.sensory_body(title, [sgg.NO_HISTORY_DISCLOSURE],
                                                     sgg.MIN_NO_EVIDENCE_SENTENCES - 1, register="driving"))
                    how = "honest body"
                except Exception:
                    body = None
            if not body and len(blocks) - removed > 1:
                removed += 1
                emit(f"  [LOCAL-905] Stop {num} '{title[:40]}': no body and no refill -> removed")
                if out and out[-1]:
                    # the previous stop must not hand off to a stop that is gone
                    out[-1] = "\n".join(
                        ln for ln in out[-1].split("\n")
                        if not (re.match(r"(?i)^directions\s*:", ln) and rc.fold(title) in rc.fold(ln)))
                if last:   # the tour's closing paragraph belongs to the tour, not to the removed stop
                    tail = [ln for ln in lines[1:] if ln.strip() and not rc._KEYED.match(ln)]
                    if tail:
                        out.append("\n".join(tail) + "\n")
                continue
            if not body:
                out.append(block)
                continue
            at = next((i for i, ln in enumerate(lines)
                       if i > 0 and (re.match(r"(?i)^directions\s*:", ln) or rc._CLOSING_LINE.match(ln.strip())
                                     or (last and _COUNT_ANY.search(ln)))), None)
            if at is None:
                while len(lines) > 1 and not lines[-1].strip():
                    lines.pop()
                lines += ["", body, "", ""]
            else:
                lines[at:at] = [body, ""]
            emit(f"  [LOCAL-905] Stop {num} '{title[:40]}': empty body on delivery -> refilled ({how})")
            out.append("\n".join(lines))
        out.append(text[pos:])
        final = "".join(out)
        try:   # [LOCAL-906C] on every path: scope-matched claims, the "You see X here is" opener, distinct filler bodies
            import leftovers_906c as _c906c
            final = _c906c.final_pass(final, evidence_by_title, emit)
        except Exception as _e906c:  # pragma: no cover
            emit(f"  [LOCAL-906C] final pass skipped (non-fatal): {_e906c}")
        try:   # [LOCAL-906I] a stop left with <= 3 sentences by the removals is refilled from its evidence (up to 5)
            import leftovers_906f as _c906f2
            _thin = _c906f2.refill_thin_stops(final, evidence_by_title, emit)
            if _thin != final:
                final = _c906f2.run_pass(_thin, evidence_by_title, emit)
        except Exception as _e906i:  # pragma: no cover
            emit(f"  [LOCAL-906I] thin-stop refill skipped (non-fatal): {_e906i}")
        try:   # [LOCAL-906P] the last word: a refilled sentence is hedged / cleaned like any other
            import owner_junk_906p as _o906p
            final = _o906p.final_pass(_o906p.run_pass(final, evidence_by_title, emit), evidence_by_title, emit)
        except Exception as _e906p:  # pragma: no cover
            emit(f"  [LOCAL-906P] last guard skipped (non-fatal): {_e906p}")
        try:   # [LOCAL-906R] the very last word: a broken measure splice is cut and a stop it leaves thin is refilled
            import splice_copy_906r as _r906r
            final = _r906r.last_word(final, evidence_by_title, emit)
        except Exception as _e906r:  # pragma: no cover
            emit(f"  [LOCAL-906R] last word skipped (non-fatal): {_e906r}")
        try:   # [LOCAL-906S] foreign-language / caption / title-as-place / fragment / Their / filler / measure guards; a factless stop refilled
            import language_dest_906s as _s906s
            final = _s906s.last_word(final, evidence_by_title, emit)
        except Exception as _e906s:  # pragma: no cover
            emit(f"  [LOCAL-906S] last word skipped (non-fatal): {_e906s}")
        try:   # [LOCAL-906U] A-to-B orientation, headline / hours copy, one disclosure, dangling start, two distances, colour, refill bar
            import final_906u as _u906u
            final = _u906u.last_word(final, evidence_by_title, emit)
        except Exception as _e906u:  # pragma: no cover
            emit(f"  [LOCAL-906U] last word skipped (non-fatal): {_e906u}")
        return fix_counts(final, emit, renumber=bool(removed))
    except Exception as err:  # pragma: no cover
        emit(f"  [LOCAL-905] body guard skipped (non-fatal): {err}")
        return text


def fix_counts(text: str, log: Optional[Callable[[str], None]] = None, renumber: bool = False) -> str:
    """Make "That's N stops in all." equal the delivered 'Stop N:' count (and renumber headings 1..n when a
    stop was removed)."""
    emit = log or (lambda _m: None)
    heads = list(re.finditer(r"(?m)^(Stop\s+)(\d+)(\s*:)", text))
    if not heads:
        return text
    n = len(heads)
    final = text
    if renumber:
        out, pos = [], 0
        for i, m in enumerate(heads, 1):
            out.append(text[pos:m.start()])
            out.append(f"{m.group(1)}{i}{m.group(3)}")
            pos = m.end()
        out.append(text[pos:])
        final = "".join(out)

    def _sub(m):
        if m.group(1) == str(n):
            return m.group(0)
        emit(f"  [LOCAL-905] closing count {m.group(1)} -> {n} (delivered stops)")
        return f"That's {n} {'stop' if n == 1 else 'stops'} in all"
    final = _COUNT.sub(_sub, final)
    try:   # [LOCAL-906H] exactly one count sentence per tour
        import delivery_evidence_906h as _de906h
        final = _de906h.dedupe_count_sentences(final, emit)
    except Exception:  # pragma: no cover
        pass
    return final
