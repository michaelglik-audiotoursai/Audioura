#!/usr/bin/env python3
"""user_stop_verify.py — LOCAL-855D item 3.

The second bounce of LOCAL-855 proved that regexes cannot win the fabrication
fight. Every time the scrub learned a phrasing, the narrator invented a new one:

    Longan:    "a quiet homage to that mythic past" + Hagimex canned longan
    Crazy st.: "those tumultuous weeks when the city's fate was being decided"
    Thi Bar:   "opened doors for acceptance and set a precedent for other venues"
    Star:      "The story passed down through the neighborhood"
    Acoustic:  "played a critical role for many local artists"

None of these match a fixed pattern; all are fabrications about a venue with no
retrieved source naming it. The ticket's prescription, implemented here:

  * Build a FACT SHEET from what is actually KNOWN — the resolved name, kind,
    address, district, the Places types/examples, and the listener's own words.
  * Run ONE cheap verification call per tour (gpt-4.1-mini, ALL user stops
    batched in a single JSON request). It labels each body sentence:
        SUPPORTED  — follows from the fact sheet;
        SENSORY    — what to look at / notice, making NO claim of fact;
        UNSUPPORTED — a factual claim the fact sheet does not support.
  * Drop UNSUPPORTED sentences. If fewer than 2 remain, use the deterministic
    grounded_user_stop_body().
  * Log ``[LOCAL-855D] verify <stop> kept K dropped D``.
  * The existing regex scrub stays as a cheap first pass; NO new regex is added.
  * Added cost per tour is reported; it is well under $0.005.

This module adds NO regex for defect detection. The only regexes here are the
STRUCTURAL ones that parse a tour's "Stop N:" blocks into fields — the same
block grammar user_stop_narration.scrub_tour_text_user_stops already relies on —
so the verifier can find each user stop's narration paragraphs. The judgment of
whether a sentence is a fabrication is made by the model against the fact sheet,
not by a pattern.
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional, Tuple

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

from user_stop_narration import (
    _fold, _split_sentences, grounded_user_stop_body, is_user_stop,
)

__all__ = ["build_fact_sheet", "verify_user_stops_in_text"]

# Structural block grammar (mirrors user_stop_narration.scrub_tour_text_user_stops).
_STOP_HDR_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+?)\s*$")
_FIELD_LINE_RE = re.compile(
    r"(?mi)^(Coordinates|Type/Specialty|Specific Examples|Directions|"
    r"Tour-Category|Address):")
_TYPE_LINE_RE = re.compile(r"(?mi)^Type/Specialty:\s*(.+?)\s*$")
_EXAMPLES_LINE_RE = re.compile(r"(?mi)^Specific Examples:\s*(.+?)\s*$")
_ADDRESS_LINE_RE = re.compile(r"(?mi)^Address:\s*(.+?)\s*$")
_COORD_LINE_RE = re.compile(
    r"(?mi)^Coordinates:\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")

_MODEL_DEFAULT = os.environ.get("USER_STOP_VERIFY_MODEL", "gpt-4.1-mini")

# [LOCAL-855D] Documented monumental/institutional kinds whose dated facts ARE
# sourced (a cathedral, basilica, palace, museum, temple, …). Mirrors
# user_stop_narration._DOCUMENTED_KINDS. The verifier SKIPS a stop of such a kind
# so a famous monument keeps its sourced dates — Notre-Dame Cathedral Basilica of
# Saigon must keep "built 1863–1880" (the ticket's run-B requirement). A small
# private venue (bar/café/spa/shop/street/market) is NOT documented and is
# verified normally.
_DOCUMENTED_KINDS = {
    "cathedral", "basilica", "church", "temple", "pagoda", "palace",
    "museum", "memorial", "monument", "opera", "landmark", "shrine",
    "mausoleum", "fort", "citadel",
}

# A trailing TOUR CONCLUSION / cross-stop recap paragraph that is absorbed into
# the final stop's block (it has no "Stop N" header). It is NOT the stop's own
# narration, so the verifier must not treat its sentences as the stop's body.
_CONCLUSION_LEAD_RE = re.compile(
    r"(?i)^(across these stops|that'?s \d+ stops|if you would like to eat|"
    r"we hope you|as (?:you|this tour) )")


# ─────────────────────────────────────────────────────────────────────────────
# FACT SHEET
# ─────────────────────────────────────────────────────────────────────────────

def build_fact_sheet(poi: Dict, location: str = "",
                     outdoor_facts: Optional[List[str]] = None) -> dict:
    """Assemble the KNOWN facts about a user stop. Everything here is grounded —
    resolved metadata and the listener's own words — so the model can judge each
    narration sentence against it. Returns a plain dict (JSON-serialisable)."""
    name = (poi.get("name") or poi.get("title") or "").strip()
    kind = (poi.get("type_specialty") or "").strip()
    examples = (poi.get("specific_examples") or "").strip()
    addr = (poi.get("address") or "").strip()
    district = ""
    if addr:
        parts = [p.strip() for p in addr.split(",") if p.strip()]
        # Prefer a District/Quận fragment; fall back to a ward, then the
        # second-to-last component.
        for p in parts:
            if re.search(r"(?i)\b(?:district|qu[ậa]n)\b", p):
                district = p
                break
        if not district:
            for p in parts:
                if re.search(r"(?i)\bph[ưuờ]*ng\b", p):
                    district = p
                    break
        if not district and len(parts) >= 2:
            district = parts[-2]
    facts = {
        "name": name,
        "kind": kind,                    # the Places type / Type-Specialty
        "address": addr,
        "district": district,
        "examples": examples,            # what the listener said to expect
        "city": (location or "").split(",")[0].strip(),
    }
    # Any retrieved material that NAMES the venue (research/lore/customer voice)
    # is grounded too — list it so a sourced claim is judged SUPPORTED.
    srcs: List[str] = []
    if outdoor_facts:
        srcs.extend(str(f).strip() for f in outdoor_facts[:6] if str(f).strip())
    for key in ("_research", "_lore", "retrieval_facts", "_customer_voice",
                "_practicals"):
        v = poi.get(key)
        if isinstance(v, str) and v.strip():
            srcs.append(v.strip()[:400])
        elif isinstance(v, (list, tuple)):
            srcs.extend(str(x).strip() for x in v[:4] if str(x).strip())
    if srcs:
        facts["retrieved_sources"] = srcs[:8]
    return {k: v for k, v in facts.items() if v}


def _fact_sheet_text(facts: dict) -> str:
    """Render a fact sheet as compact, labelled lines for the prompt."""
    order = ["name", "kind", "address", "district", "city", "examples"]
    lines = []
    for k in order:
        if facts.get(k):
            lines.append(f"  {k}: {facts[k]}")
    for s in facts.get("retrieved_sources", []) or []:
        lines.append(f"  source: {s}")
    return "\n".join(lines) if lines else "  (no facts beyond the name)"


# ─────────────────────────────────────────────────────────────────────────────
# The single batched verification call
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM = (
    "You verify audio-tour narration against a FACT SHEET of what is actually "
    "known about each user-chosen venue. You do not add facts and you do not "
    "rewrite — you only LABEL each numbered sentence.\n\n"
    "For every sentence output exactly one label:\n"
    "  SUPPORTED  — the sentence's factual content follows from the fact sheet "
    "(the venue's name, kind, address/district, listed offerings, or a listed "
    "source). Naming the venue, its kind, its district or its listed offerings "
    "is SUPPORTED.\n"
    "  SENSORY    — a present-tense observation of what a visitor sees, hears, "
    "smells or notices on arriving, making NO claim of fact about history, "
    "people, events, dates, firsts, legends, or significance. Atmosphere is "
    "SENSORY.\n"
    "  UNSUPPORTED — any factual claim the fact sheet does not support: a date "
    "or founding year, a named person or performer, a historical event, a "
    "'first/pioneering/turning-point' claim, a legend or myth, a story 'passed "
    "down' or 'among regulars', a tie to a company/artwork/figure, regional or "
    "national history, or a significance/role claim ('played a critical role', "
    "'opened doors', 'set a precedent'). If a sentence mixes a sensory clause "
    "with an unsupported claim, label it UNSUPPORTED.\n\n"
    "Judge meaning, not wording. Return ONLY JSON of the exact shape:\n"
    '{"stops":[{"id":<int>,"labels":[{"i":<int>,"label":"SUPPORTED|SENSORY|'
    'UNSUPPORTED"}]}]}'
)


def _build_user_message(batch: List[dict]) -> str:
    parts = ["Label every sentence of every stop below.\n"]
    for item in batch:
        parts.append(f"STOP id={item['id']} — \"{item['name']}\"")
        parts.append("FACT SHEET:")
        parts.append(_fact_sheet_text(item["facts"]))
        parts.append("SENTENCES:")
        for i, s in enumerate(item["sentences"]):
            parts.append(f"  {i}. {s}")
        parts.append("")
    return "\n".join(parts)


def _call_openai(system: str, user: str, api_key: str, model: str,
                 timeout: int = 40) -> Tuple[Optional[dict], int, int]:
    """One JSON call. Returns (parsed_or_None, input_tokens, output_tokens)."""
    if requests is None or not api_key:
        return None, 0, 0
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            data=json.dumps({
                "model": model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": 0.0,
                "seed": 7,
                "max_tokens": 1500,
                "response_format": {"type": "json_object"},
            }),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None, 0, 0
        body = resp.json()
        usage = body.get("usage", {}) or {}
        content = body["choices"][0]["message"]["content"]
        return (json.loads(content),
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)))
    except Exception:
        return None, 0, 0


# ─────────────────────────────────────────────────────────────────────────────
# Tour-text integration
# ─────────────────────────────────────────────────────────────────────────────

def _folded_titles(titles):
    return {f for f in (_fold(t) for t in (titles or [])) if f}


def _title_is_user(title, folded_titles):
    f = _fold(title)
    if not f:
        return False
    return any(f == t or f in t or t in f for t in folded_titles)


def _collect_body_paragraphs(block_lines: List[str]):
    """Yield (line_index, is_orientation, value) for each narration paragraph in a
    stop block — the Orientation value and any standalone prose paragraph. Field
    lines (Coordinates/Type/Address/Directions), the header and Sources are
    skipped, exactly as the delivered scrub does."""
    for idx, ln in enumerate(block_lines):
        stripped = ln.strip()
        if not stripped:
            continue
        if (_FIELD_LINE_RE.match(ln) or _STOP_HDR_RE.match(ln)
                or stripped.lower().startswith("sources")):
            continue
        if ln.lower().startswith("orientation:"):
            _, _, val = ln.partition(":")
            if val.strip():
                yield idx, True, val.strip()
        else:
            if _CONCLUSION_LEAD_RE.match(stripped):
                # A trailing tour-conclusion / recap paragraph absorbed into the
                # final stop block — not the stop's narration. Skip it.
                continue
            yield idx, False, ln


def verify_user_stops_in_text(
        tour_text: str, user_titles: List[str], location: str = "",
        api_key: str = None, model: str = None, log=None,
        outdoor_facts_by_title: Optional[Dict[str, list]] = None,
        ) -> Tuple[str, dict]:
    """Fact-sheet verify every USER stop in an assembled tour text with ONE cheap
    batched gpt-4.1-mini call.

    For each user stop: build the fact sheet, number its body sentences, and send
    them all in a single JSON request. Drop every sentence the model labels
    UNSUPPORTED. If fewer than 2 sentences survive across the stop, replace the
    stop's narration with ``grounded_user_stop_body()``. Logs
    ``[LOCAL-855D] verify <stop> kept K dropped D`` per stop.

    Returns ``(new_text, report)`` where report carries::
        {'ran': bool, 'model': str, 'input_tokens', 'output_tokens', 'cost_usd',
         'stops': [{'stop','kept','dropped','grounded'}], 'dropped_total'}

    The call is skipped (ran=False, cost 0) when there are no user stops, no
    api_key, or requests is unavailable — the delivered text is returned
    unchanged and the earlier regex scrub stands as the first pass.
    """
    model = model or _MODEL_DEFAULT
    report = {"ran": False, "model": model, "input_tokens": 0,
              "output_tokens": 0, "cost_usd": 0.0, "stops": [],
              "dropped_total": 0}
    if not tour_text or not tour_text.strip() or not user_titles:
        return tour_text or "", report
    folded = _folded_titles(user_titles)
    if not folded:
        return tour_text, report

    lines = tour_text.split("\n")
    headers = [(i, m) for i, ln in enumerate(lines)
               for m in [_STOP_HDR_RE.match(ln)] if m]
    if not headers:
        return tour_text, report

    # 1) Collect each user stop: its poi (from the block fields), its body
    #    paragraph line-indices, and its numbered sentences.
    batch = []            # [{id, name, facts, sentences}]
    stop_meta = []        # parallel: {id, name, poi, start, end, para_lines, sent_map}
    for h_idx, (line_no, m) in enumerate(headers):
        title = m.group(2).strip()
        if not _title_is_user(title, folded):
            continue
        start = line_no + 1
        end = headers[h_idx + 1][0] if h_idx + 1 < len(headers) else len(lines)
        block = lines[start:end]
        block_text = "\n".join(block)
        poi = {"name": title, "title": title, "user_explicit": True}
        tm = _TYPE_LINE_RE.search(block_text)
        if tm:
            poi["type_specialty"] = tm.group(1).strip()
        am = _ADDRESS_LINE_RE.search(block_text)
        if am:
            poi["address"] = am.group(1).strip()
        xm = _EXAMPLES_LINE_RE.search(block_text)
        if xm:
            poi["specific_examples"] = xm.group(1).strip()
        cm = _COORD_LINE_RE.search(block_text)
        if cm:
            poi["coordinates"] = f"{cm.group(1)}, {cm.group(2)}"

        odf = None
        if outdoor_facts_by_title:
            for k, v in outdoor_facts_by_title.items():
                if _fold(k) == _fold(title):
                    odf = v
                    break
        facts = build_fact_sheet(poi, location, odf)

        # [LOCAL-855D] A documented monument/institution (cathedral, basilica,
        # palace, museum, …) is SOURCED — skip it so its dates survive
        # (Notre-Dame "built 1863–1880"). The 855B scrub already does not
        # date-gate these kinds; the verifier must match that, or it would
        # over-scrub the exact case the ticket's run B protects.
        _kind_fold = _fold(poi.get("type_specialty") or "")
        if set(_kind_fold.split()) & _DOCUMENTED_KINDS:
            if log:
                log(f"[LOCAL-855D] verify {title} skipped (documented monument "
                    f"kind — sourced dates kept)")
            continue

        # Number sentences across all body paragraphs of the stop, keeping a map
        # back to (block-line-index, is_orientation, sentence-within-paragraph).
        sentences = []
        sent_map = []     # [(abs_line_index, is_orientation)]
        para_sent_counts = {}   # abs_line_index -> list of sentences
        for rel_idx, is_or, val in _collect_body_paragraphs(block):
            abs_idx = start + rel_idx
            ss = _split_sentences(val)
            para_sent_counts[abs_idx] = (is_or, ss)
            for s in ss:
                sentences.append(s)
                sent_map.append((abs_idx, is_or))
        if not sentences:
            continue
        sid = len(batch)
        batch.append({"id": sid, "name": title, "facts": facts,
                      "sentences": sentences})
        stop_meta.append({"id": sid, "name": title, "poi": poi, "start": start,
                          "end": end, "sent_map": sent_map,
                          "para_sent_counts": para_sent_counts,
                          "sentences": sentences})

    if not batch:
        return tour_text, report

    # 2) ONE batched verification call.
    user_msg = _build_user_message(batch)
    if api_key is None:
        api_key = os.environ.get("OPENAI_API_KEY")
    parsed, in_tok, out_tok = _call_openai(_SYSTEM, user_msg, api_key, model)
    report["input_tokens"] = in_tok
    report["output_tokens"] = out_tok
    try:
        from cost_rates import llm_cost
        report["cost_usd"] = round(llm_cost(in_tok, out_tok, model), 6)
    except Exception:
        report["cost_usd"] = round(in_tok / 1e6 * 0.40 + out_tok / 1e6 * 1.60, 6)
    if parsed is None:
        # The call did not run / failed — leave the text as the regex scrub left
        # it (first pass stands). ran stays False.
        if log:
            log("[LOCAL-855D] verify call did not run (no key / error) — "
                "regex first pass stands")
        return tour_text, report
    report["ran"] = True

    # 3) Index labels: {stop_id: {sentence_index: label}}.
    labels_by_stop: Dict[int, Dict[int, str]] = {}
    for st in parsed.get("stops", []) or []:
        try:
            sid = int(st.get("id"))
        except Exception:
            continue
        lab = {}
        for item in st.get("labels", []) or []:
            try:
                lab[int(item.get("i"))] = str(item.get("label", "")).upper()
            except Exception:
                continue
        labels_by_stop[sid] = lab

    # 4) Apply: drop UNSUPPORTED; if <2 survive -> grounded body.
    for meta in stop_meta:
        sid = meta["id"]
        name = meta["name"]
        lab = labels_by_stop.get(sid, {})
        sentences = meta["sentences"]
        # A sentence with no returned label is KEPT (conservative — the model
        # only removes what it positively calls UNSUPPORTED).
        keep_flags = [lab.get(i, "SUPPORTED") != "UNSUPPORTED"
                      for i in range(len(sentences))]
        kept_n = sum(1 for f in keep_flags if f)
        dropped_n = len(sentences) - kept_n

        if kept_n < 2:
            # Not enough grounded material survives — use the deterministic body.
            grounded = grounded_user_stop_body(meta["poi"], location)
            grounded = (grounded or "").strip()
            if grounded:
                _apply_grounded(lines, meta, grounded)
                report["stops"].append({"stop": name, "kept": kept_n,
                                        "dropped": dropped_n, "grounded": True})
                report["dropped_total"] += dropped_n
                if log:
                    log(f"[LOCAL-855D] verify {name} kept {kept_n} dropped "
                        f"{dropped_n} -> grounded body")
                continue
            # No grounded body possible: keep as-is (never empty).
            report["stops"].append({"stop": name, "kept": len(sentences),
                                    "dropped": 0, "grounded": False})
            if log:
                log(f"[LOCAL-855D] verify {name} kept {len(sentences)} dropped 0 "
                    f"(no grounded fallback; left unchanged)")
            continue

        # Rewrite each body paragraph keeping only its non-UNSUPPORTED sentences.
        _apply_drops(lines, meta, keep_flags)
        report["stops"].append({"stop": name, "kept": kept_n,
                                "dropped": dropped_n, "grounded": False})
        report["dropped_total"] += dropped_n
        if log:
            log(f"[LOCAL-855D] verify {name} kept {kept_n} dropped {dropped_n}")

    return "\n".join(lines), report


def _apply_drops(lines: List[str], meta: dict, keep_flags: List[bool]):
    """Rewrite the stop's body paragraphs, dropping UNSUPPORTED sentences and
    preserving the Orientation label / paragraph structure. A paragraph that
    loses every sentence is blanked (its blank line is collapsed later)."""
    si = 0
    for abs_idx in sorted(meta["para_sent_counts"].keys()):
        is_or, ss = meta["para_sent_counts"][abs_idx]
        n = len(ss)
        flags = keep_flags[si:si + n]
        si += n
        new_val = _rebuild_paragraph(ss, flags)
        if is_or:
            label = lines[abs_idx].split(":", 1)[0]
            lines[abs_idx] = f"{label}: {new_val}" if new_val else f"{label}:"
        else:
            lines[abs_idx] = new_val


def _rebuild_paragraph(ss: List[str], flags: List[bool]) -> str:
    return " ".join(s for s, f in zip(ss, flags) if f).strip()


def _apply_grounded(lines: List[str], meta: dict, grounded: str):
    """Replace the stop's narration with the grounded body: the grounded text
    goes on the Orientation line (or the first body paragraph), and any other
    body paragraphs are blanked. Field/structure lines are untouched."""
    first = True
    for abs_idx in sorted(meta["para_sent_counts"].keys()):
        is_or, _ss = meta["para_sent_counts"][abs_idx]
        if first:
            if is_or:
                label = lines[abs_idx].split(":", 1)[0]
                lines[abs_idx] = f"{label}: {grounded}"
            else:
                lines[abs_idx] = grounded
            first = False
        else:
            lines[abs_idx] = ""
