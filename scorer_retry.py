#!/usr/bin/env python3
"""scorer_retry.py — the missing gate (LOCAL-540).

For three weeks every task spec said the defect suite in ``tour_quality`` "gates".
It never did. ``tour_quality.score_tour`` is read only by standalone measurement
scripts (``run_local*.py``, ``run_round*.py``). The generation path in
``generate_tour_text.py`` never imported the module, so a tour that failed every
REQUIRED_CLEAN check was written, packed, cached and shipped exactly as if it had
passed. Round 9 shipped "Gustave Eiffel's iconic Control Tower" at Boston Logan
because nothing was ever going to stop it.

This module is the piece that acts on a score:

    result = score_and_retry(text, requested_stops=N, is_building_tour=..., regenerate_section=fn)

* Score the assembled tour with ``tour_quality.score_tour`` (same arguments the
  reference caller ``run_round9.py`` passes).
* If any REQUIRED_CLEAN defect is present, attribute each offending quote to the
  section it lives in — a specific ``Stop N`` block when the defect is
  attributable to a stop; the whole-tour ``orientation`` (stop-1 preview) or
  ``epilog`` section otherwise — and regenerate ONLY those sections, once, via the
  ``regenerate_section`` callback the caller supplies (a single LLM rewrite per
  section).
* Re-score. Then STOP. D577's principle holds: one retry, then ship with the
  defect recorded. A tour that cannot be made clean must still reach the listener,
  but the before/after defect sets are returned so the failure is visible
  afterwards, not swallowed.

The caller owns the LLM call (this module has no API keys and issues no network
requests of its own) and reports its token/dollar cost back through the callback's
return value, so the retry's cost is folded into the generation's cost record.
"""

import re

import tour_quality as tq


# The section a defect is attributed to. A stop section carries its 1-based stop
# number; whole-tour sections carry the sentinel index -1.
ORIENTATION = 'orientation'
EPILOG = 'epilog'
STOP = 'stop'


# ── quote extraction ─────────────────────────────────────────────────────────
# score_tour() collapses each defect to a human string, but the raw detectors it
# calls return the offending quote(s) verbatim. Re-running those detectors is the
# most reliable way to get quotes to locate in the text; we fall back to pulling
# quoted spans out of the defect string when a detector is not separately callable.

_QUOTED = re.compile(r'"([^"]{4,})"|\'([^\']{4,})\'')


def _quotes_from_defect_string(msg):
    """Best-effort: pull any quoted spans out of a score_tour defect message."""
    out = []
    for m in _QUOTED.finditer(msg or ''):
        q = m.group(1) or m.group(2)
        if q and q.strip():
            out.append(q.strip())
    return out


def defect_quotes(text, defect_key, defect_msg):
    """Return the raw offending quote(s) for a defect, richest source first.

    For the structured detectors (offsite_entity, self_contradiction,
    fabricated_attribution) we call the underlying tour_quality function so we get
    the exact spans, not the truncated summary. Everything else falls back to the
    quoted spans embedded in the defect message.
    """
    quotes = []
    try:
        if defect_key == 'offsite_entity':
            for place, frame in tq.find_offsite_entities(text):
                quotes.append(frame)
                quotes.append(place)
        elif defect_key == 'self_contradiction':
            for subcheck, why, qa, qb in tq._find_self_contradictions(text):
                for q in (qa, qb):
                    # drop the bracketed synthetic markers ("[title] ...",
                    # "[delivered] ...") — they are not locatable spans
                    if q and not q.lstrip().startswith('['):
                        quotes.append(q)
        elif defect_key == 'fabricated_attribution':
            for kind, verb, year, name in tq._find_fabricated_attributions(text):
                quotes.append(f"{verb} in {year} by {name}")
    except Exception:
        pass
    # Always add whatever the summary string quoted, as a backstop.
    quotes.extend(_quotes_from_defect_string(defect_msg))
    # De-dup preserving order.
    seen, out = set(), []
    for q in quotes:
        k = q.strip()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


# ── stop / section boundaries ────────────────────────────────────────────────
_STOP_HDR = re.compile(r'^Stop\s+(\d+):', re.M)


def stop_blocks(text):
    """[(stop_number:int, start:int, end:int), ...] over the delivered text.

    A block runs from its ``Stop N:`` header to the next header (or end of text).
    """
    hdrs = list(_STOP_HDR.finditer(text or ''))
    blocks = []
    for i, m in enumerate(hdrs):
        num = int(m.group(1))
        start = m.start()
        end = hdrs[i + 1].start() if i + 1 < len(hdrs) else len(text)
        blocks.append((num, start, end))
    return blocks


def _orientation_span(text, block_start, block_end):
    """Span (start,end) of the first ``Orientation:`` paragraph inside a block, or
    None. The paragraph ends at the next blank line or block end."""
    m = re.search(r'^Orientation:.*$', text[block_start:block_end], re.M)
    if not m:
        return None
    s = block_start + m.start()
    # extend to the end of the paragraph (blank line) so a multi-line orientation
    # is captured whole
    nl = text.find('\n\n', s, block_end)
    e = nl if nl != -1 else block_end
    return (s, e)


def attribute_defect(text, defect_key, defect_msg):
    """Attribute a single REQUIRED_CLEAN defect to a section.

    Returns a dict: {'kind': STOP|ORIENTATION|EPILOG, 'stop': int|None,
                     'span': (start,end)|None, 'quotes': [...]}.

    Rules (from the task):
      * A defect whose offending quote sits inside a ``Stop N`` block is
        attributed to that stop.
      * A whole-tour orientation preview mismatch (the stop-1 ``Orientation:``
        sentence that names endpoints/places that are not delivered stops) is
        attributed to the ORIENTATION section.
      * A whole-tour epilog recap mismatch is attributed to the EPILOG section.
    """
    quotes = defect_quotes(text, defect_key, defect_msg)
    blocks = stop_blocks(text)

    # Whole-tour framing sub-checks of self_contradiction / offsite_entity live in
    # the stop-1 orientation preview or the epilog. Detect those first so we
    # regenerate the smallest correct section.
    epilog = tq._epilog_text(text)
    orient = tq._orientation_text(text)

    # Does any quote belong to the epilog recap?
    if epilog:
        for q in quotes:
            if q and (q in epilog or epilog in q):
                # epilog is the last "That's N stops" paragraph
                idx = text.rfind(epilog)
                if idx != -1:
                    return {'kind': EPILOG, 'stop': None,
                            'span': (idx, idx + len(epilog)), 'quotes': quotes}

    # Does any quote belong to the stop-1 orientation preview?
    if orient and blocks:
        for q in quotes:
            if q and (q in orient or orient in q or (len(q) > 20 and q[:20] in orient)):
                num, bstart, bend = blocks[0]
                span = _orientation_span(text, bstart, bend)
                if span:
                    return {'kind': ORIENTATION, 'stop': num,
                            'span': span, 'quotes': quotes}

    # Otherwise: locate the quote inside a stop block.
    for q in quotes:
        if not q:
            continue
        pos = text.find(q)
        if pos == -1 and len(q) > 40:
            pos = text.find(q[:40])
        if pos != -1:
            for num, bstart, bend in blocks:
                if bstart <= pos < bend:
                    return {'kind': STOP, 'stop': num,
                            'span': (bstart, bend), 'quotes': quotes}

    # Fallback: no locatable quote. Attribute to stop 1's orientation if present
    # (the most common home of framing defects), else to stop 1's whole block.
    if blocks:
        num, bstart, bend = blocks[0]
        span = _orientation_span(text, bstart, bend)
        if span:
            return {'kind': ORIENTATION, 'stop': num, 'span': span, 'quotes': quotes}
        return {'kind': STOP, 'stop': num, 'span': (bstart, bend), 'quotes': quotes}
    return {'kind': STOP, 'stop': None, 'span': None, 'quotes': quotes}


def plan_regeneration(text, defects):
    """Group REQUIRED_CLEAN defects by the section that must be regenerated.

    Returns a list of targets, one per distinct section:
        {'kind', 'stop', 'span', 'defects': {key: msg}, 'quotes': [...]}
    Sections are de-duplicated so a stop implicated by two defects is regenerated
    once, and an orientation defect subsumes a plain stop defect for the same stop.
    """
    required = [(k, v) for k, v in defects.items() if k in tq.REQUIRED_CLEAN]
    by_section = {}
    for key, msg in required:
        att = attribute_defect(text, key, msg)
        # section identity: orientation/epilog are unique; stop keyed by number
        if att['kind'] == EPILOG:
            skey = ('epilog', None)
        elif att['kind'] == ORIENTATION:
            skey = ('orientation', att['stop'])
        else:
            skey = ('stop', att['stop'])
        slot = by_section.setdefault(skey, {
            'kind': att['kind'], 'stop': att['stop'], 'span': att['span'],
            'defects': {}, 'quotes': [],
        })
        slot['defects'][key] = msg
        for q in att['quotes']:
            if q not in slot['quotes']:
                slot['quotes'].append(q)
        # If a later defect gives a span and the slot had none, adopt it.
        if slot['span'] is None and att['span'] is not None:
            slot['span'] = att['span']

    # Collapse a plain ('stop', N) target into ('orientation', N) if both exist —
    # regenerating the orientation is the more targeted fix and covers the block.
    orient_stops = {stop for (kind, stop) in by_section if kind == 'orientation'}
    for skey in list(by_section):
        kind, stop = skey
        if kind == 'stop' and stop in orient_stops:
            # merge its defects into the orientation slot, drop the stop slot
            osk = ('orientation', stop)
            by_section[osk]['defects'].update(by_section[skey]['defects'])
            del by_section[skey]

    return list(by_section.values())


def apply_regenerated_section(text, span, new_section):
    """Splice ``new_section`` into ``text`` over ``span`` and return the new text."""
    if not span:
        return text
    s, e = span
    return text[:s] + new_section.rstrip() + text[e:]


# ── orchestration ────────────────────────────────────────────────────────────
def score_and_retry(text, requested_stops=None, is_building_tour=False,
                    anchor=None, geocoder=None, verify_attribution=None,
                    regenerate_section=None, log=print):
    """Score the tour, retry ONCE on a REQUIRED_CLEAN defect, re-score, and return
    a record.

    Parameters
    ----------
    text : str
        The fully-assembled tour.
    requested_stops, is_building_tour, anchor, geocoder, verify_attribution :
        Passed straight through to ``tour_quality.score_tour``.
    regenerate_section : callable or None
        ``regenerate_section(target, full_text) -> (new_section_text, cost)``.
        ``target`` is one entry from :func:`plan_regeneration`. ``cost`` is a dict
        with at least ``{'total_cost': float, 'total_tokens': int}`` describing what
        that one rewrite cost. If None, no retry is attempted (score-only).
    log : callable
        Where to write the log lines the acceptance requires. Defaults to print.

    Returns
    -------
    dict with keys:
        before          : score_tour result on the original text
        after           : score_tour result on the (possibly) retried text
        text            : the final text (retried if a rewrite ran, else original)
        retried         : bool — whether any section was regenerated
        retry_cost      : {'total_cost': float, 'total_tokens': int}
        targets         : the regeneration plan that was executed
        defects_before  : dict of defect key -> message BEFORE retry
        defects_after   : dict of defect key -> message AFTER retry
        removed         : sorted list of REQUIRED_CLEAN defect keys the retry cleared
        remaining       : sorted list of REQUIRED_CLEAN defect keys still present
    """
    before = tq.score_tour(text, requested_stops, is_building_tour,
                           anchor, geocoder, verify_attribution)
    before_defects = dict(before['defects'])
    required_before = {k for k in before_defects if k in tq.REQUIRED_CLEAN}

    log(f"  [LOCAL-540] scorer ran on assembled tour "
        f"({before['metrics'].get('chars', 0)} chars, "
        f"{before['metrics'].get('stops_delivered')}/{requested_stops} stops)")
    if before_defects:
        log(f"  [LOCAL-540] defects seen: {sorted(before_defects.keys())}")
        for k in sorted(before_defects):
            tag = 'REQUIRED_CLEAN' if k in tq.REQUIRED_CLEAN else 'advisory'
            log(f"  [LOCAL-540]   {k} [{tag}]: {before_defects[k][:160]}")
    else:
        log(f"  [LOCAL-540] no defects — tour is clean")

    retry_cost = {'total_cost': 0.0, 'total_tokens': 0}
    targets = []
    new_text = text
    retried = False

    if required_before and callable(regenerate_section):
        targets = plan_regeneration(text, before_defects)
        log(f"  [LOCAL-540] REQUIRED_CLEAN defect present "
            f"({sorted(required_before)}) — issuing ONE retry over "
            f"{len(targets)} section(s)")
        # All spans were computed against the ORIGINAL text. Splice back-to-front
        # (highest span start first) so an earlier splice never shifts the offsets
        # of a section not yet processed. Targets without a span sort last.
        ordered = sorted(
            targets,
            key=lambda t: (t.get('span') or (-1, -1))[0],
            reverse=True,
        )
        for t in ordered:
            where = (t['kind'] if t['stop'] is None
                     else f"{t['kind']} (stop {t['stop']})")
            log(f"  [LOCAL-540] retry: regenerating {where} for "
                f"{sorted(t['defects'].keys())}")
            try:
                out = regenerate_section(t, new_text)
            except Exception as e:
                log(f"  [LOCAL-540] retry: regeneration raised {type(e).__name__}: {e}"
                    f" — keeping original section")
                out = None
            if not out:
                continue
            new_section, cost = out
            if new_section and t.get('span'):
                new_text = apply_regenerated_section(new_text, t['span'], new_section)
                retried = True
            if isinstance(cost, dict):
                retry_cost['total_cost'] += float(cost.get('total_cost', 0.0) or 0.0)
                retry_cost['total_tokens'] += int(cost.get('total_tokens', 0) or 0)

    after = tq.score_tour(new_text, requested_stops, is_building_tour,
                          anchor, geocoder, verify_attribution)
    after_defects = dict(after['defects'])
    required_after = {k for k in after_defects if k in tq.REQUIRED_CLEAN}

    if retried:
        log(f"  [LOCAL-540] rescored after retry: "
            f"defects {sorted(before_defects.keys())} -> {sorted(after_defects.keys())}")
        removed = sorted(required_before - required_after)
        remaining = sorted(required_after)
        if removed:
            log(f"  [LOCAL-540] retry removed: {removed}")
        if remaining:
            log(f"  [LOCAL-540] retry did NOT remove: {remaining} "
                f"— shipping with defect recorded (D577)")
        if not remaining:
            log(f"  [LOCAL-540] retry cleared all REQUIRED_CLEAN defects")

    return {
        'before': before,
        'after': after,
        'text': new_text,
        'retried': retried,
        'retry_cost': retry_cost,
        'targets': targets,
        'defects_before': before_defects,
        'defects_after': after_defects,
        'removed': sorted(required_before - required_after),
        'remaining': sorted(required_after),
    }
