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

from text_polish import apply_orphan_rule, city_from_scope  # [LOCAL-860]

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
_ADDRESS_LINE_RE = re.compile(r"(?mi)^Address:[ \t]*(\S[^\n]*?)[ \t]*$")
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
    r"(?i)^(across these stops|across all these stops|across your stops|"
    r"that'?s \d+ stops? in all|if you would like to eat|"
    r"we hope you(?:'ve| have)? enjoyed|thanks for (?:riding|walking|touring)|"
    r"as (?:you|this tour) (?:conclude|wrap|finish|end|come to (?:a |an )?(?:close|end))|"
    r"as this tour (?:draws|comes))")


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
        "city": city_from_scope(location),
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
# [LOCAL-855E item 3 / D759] RETRIEVAL — one Serper search per user stop
# ─────────────────────────────────────────────────────────────────────────────
#
# The second bounce proved the narrator invents a fresh phrasing faster than a
# regex (or even the verifier) can learn it, because the verifier was judging
# against a fact sheet that had NOTHING retrieved about the venue — so a plausible
# invention ("played a critical role for many local artists") had nothing to
# contradict it and slipped through as SENSORY/atmosphere. D759's fix is to give
# the fact sheet REAL retrieved material: ONE Serper query per user stop,
# "<name>" <district or city>, keeping only the snippets that actually NAME the
# venue. The narrator and the verifier then have a concrete source to judge
# against (SUPPORTED), and a stop with no venue-naming snippet is written ONLY
# from the deterministic grounded body — no LLM invention at all.

_GENERIC_NAME_TOKENS = {
    "the", "a", "an", "and", "of", "bar", "spa", "cafe", "café", "restaurant",
    "club", "lounge", "shop", "store", "street", "saigon", "city", "house",
    "pub", "venue", "studio", "salon", "market", "star", "is", "born",
}

# Venue-kind words whose presence in a snippet corroborates that it is about an
# actual VENUE (not a coincidental word match or a same-named film/song).
_VENUE_KIND_SIGNAL = {
    "bar", "pub", "club", "lounge", "restaurant", "cafe", "café", "bistro",
    "spa", "salon", "massage", "wellness", "karaoke", "nightclub", "brewery",
    "shop", "store", "boutique", "gallery", "bakery", "teahouse", "hotel",
    "hostel", "venue", "eatery", "diner", "coffee", "street", "market",
}


def _name_tokens(name: str) -> list:
    """Distinctive folded tokens of a venue name (drop generic/kind words). Used
    to decide whether a snippet actually NAMES the venue."""
    toks = []
    for w in _fold(name).split():
        if len(w) >= 3 and w not in _GENERIC_NAME_TOKENS:
            toks.append(w)
    return toks


def _snippet_names_venue(name, title, snippet, poi=None, location=""):
    """True when a Serper result (title + snippet) is about THIS venue — not a
    coincidental word match and not a same-named film/song/other entity.

    The venue NAME must appear as a contiguous folded phrase (so "acoustic
    guitar tuning" does not match "Acoustic Bar"). When the name has NO
    distinctive token beyond generic/kind words (e.g. "A Star is Born", whose
    phrase collides with the 2018 film), a corroborating VENUE signal is also
    required: a venue-kind word, the district, or the city in the same snippet —
    a plain film-plot snippet carries none and is rejected."""
    hay = _fold(f"{title} {snippet}")
    if not hay:
        return False
    full = _fold(name)
    name_in = bool(full and full in hay)
    toks = _name_tokens(name)
    # Require the full name phrase, OR (for a multi-distinctive-token name) all of
    # its distinctive tokens present — but NEVER a single common token alone.
    if not name_in:
        if len(toks) >= 2 and all(t in hay for t in toks):
            name_in = True
        else:
            return False
    # The name phrase is present. If the name is distinctive (>= 1 distinctive
    # token), that is enough. If it is a common phrase (no distinctive token),
    # demand a corroborating venue signal so a same-named film/song is excluded.
    if toks:
        return True
    kind_words = set()
    if poi:
        kind_words = {w for w in _fold(poi.get("type_specialty") or "").split()}
    corroborators = set()
    corroborators |= _VENUE_KIND_SIGNAL
    corroborators |= kind_words
    # locality tokens (district / city)
    for src in (location or "", (poi or {}).get("address") or ""):
        for w in _fold(src).split():
            if len(w) >= 3:
                corroborators.add(w)
    hay_tokens = set(hay.split())
    return bool(hay_tokens & corroborators)


def _build_stop_query(name: str, poi: dict, location: str) -> str:
    """D759: '"<name>" <district or city>'. Prefer a District/Quận fragment from
    the stop's address, else the city from `location`."""
    district = ""
    addr = (poi.get("address") or "").strip()
    if addr:
        for p in (x.strip() for x in addr.split(",")):
            if re.search(r"(?i)\b(?:district|qu[ậa]n)\b", p):
                district = p
                break
    # [LOCAL-860 item 6] `location` is the whole tour title for a user-stops
    # tour ("Sophia's biking tour in Ho Chi Minh City"); the query context must be
    # the city/district, never the title.
    where = district or city_from_scope(location)
    name = (name or "").strip()
    return f'"{name}" {where}'.strip()


def retrieve_user_stop_snippets(name, poi, location, serp_fn=None, log=None,
                                max_snippets: int = 5):
    """[D759 (a)] Run ONE Serper query for a user stop and return the snippets
    that NAME the venue, plus the query string. Returns ``(snippets, query,
    n_queries)``.

    ``serp_fn(query) -> ([{title,url,snippet}], latency)`` is injected so tests
    run offline; the default uses the project's metered Serper caller
    (``work_story_searcher._serp_search`` — $0.001/query, one paid_api_calls row).
    A failure degrades to no snippets (never raises), so a stop with no retrieval
    falls to the deterministic grounded body."""
    query = _build_stop_query(name, poi, location)
    if serp_fn is None:
        try:
            from work_story_searcher import _serp_search as serp_fn
        except Exception:
            serp_fn = None
    if serp_fn is None:
        return [], query, 0
    try:
        results, _lat = serp_fn(query)
    except Exception as _e:
        if log:
            log(f"[LOCAL-855E] serper query failed for {name!r}: {_e}")
        return [], query, 1
    results = results or []
    kept = []
    for r in results:
        if not isinstance(r, dict):
            continue
        title = r.get("title", "") or ""
        snippet = r.get("snippet", "") or ""
        if _snippet_names_venue(name, title, snippet, poi=poi,
                                location=location):
            text = snippet.strip() or title.strip()
            if text and text not in kept:
                kept.append(text[:400])
        if len(kept) >= max_snippets:
            break
    if log:
        log(f"[LOCAL-855E] serper {name!r} q={query!r} -> "
            f"{len(kept)}/{len(results)} venue-naming snippet(s)")
    return kept, query, 1


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
    "  SENSORY    — a GENERIC, present-tense observation true of ANY venue of "
    "this kind, naming NO specific object, decor, smell, sound source or "
    "geography. Allowed: 'music carries from the stage', 'the room is warmly "
    "lit', 'conversation and clinking glasses fill the air'. A sentence is "
    "SENSORY ONLY if you could move it to any other venue of the same kind "
    "without it becoming false.\n"
    "  UNSUPPORTED — any factual claim the fact sheet does not support, AND any "
    "sensory-sounding sentence that invents a SPECIFIC detail the fact sheet "
    "does not list. In particular, label UNSUPPORTED:\n"
    "    * a specific OBJECT or DECOR not in the fact sheet — 'the harp from the "
    "first room', 'a corner altar', 'vintage film posters', 'a soft wooden sign "
    "carved with Vietnamese characters', 'frosted glass panels', 'bamboo "
    "accents';\n"
    "    * a specific SMELL/TASTE not in the fact sheet — 'the scent of "
    "caramelized sugar', 'brewing coffee', 'incense';\n"
    "    * any GEOGRAPHY not in the fact sheet — a sea, coast, ocean, beach, "
    "harbor, river, mountain, a named street/landmark, a direction or distance "
    "('the coastal breeze', 'meets the South China Sea', 'a hundred kilometers "
    "southeast', 'steps from Lam Sơn Square');\n"
    "    * a date or founding year, a named person or performer, a historical "
    "event, a 'first/pioneering/turning-point' claim, a legend or myth, a story "
    "'passed down' or 'among regulars', a tie to a company/artwork/figure, "
    "regional or national history, a significance/role claim ('played a "
    "critical role', 'opened doors', 'set a precedent').\n"
    "If a sentence mixes a generic sensory clause with ANY specific invented "
    "object/decor/smell/geography or any unsupported claim, label it "
    "UNSUPPORTED. A sentence that refers back to a person, group, event or past "
    "that no SUPPORTED sentence of the same stop introduces ('His playing…', "
    "'those earlier networks', 'that mythic past') is UNSUPPORTED.\n\n"
    "IMPORTANT: every UNSUPPORTED category above applies ONLY when the fact sheet "
    "does NOT state it. A date, founding year, person, event, address, rating or "
    "item that a fact-sheet line or listed source states IS SUPPORTED — e.g. "
    "'Founded in 2007' is SUPPORTED when a source says 'Founded in 2007'.\n"
    "Judge meaning, not wording. When in doubt between SENSORY and UNSUPPORTED, "
    "choose UNSUPPORTED. Return ONLY JSON of the exact shape:\n"
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
                 timeout: int = 40, max_tokens: int = 1500) -> Tuple[Optional[dict], int, int]:
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
                "max_tokens": int(max_tokens),
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
        serp_fn=None, retrieve: bool = True,
        material_by_title: Optional[Dict[str, list]] = None,
        precomposed_titles: Optional[List[str]] = None,
        ) -> Tuple[str, dict]:
    """Fact-sheet verify every USER stop in an assembled tour text with ONE cheap
    batched gpt-4.1-mini call, after ONE Serper retrieval per user stop (D759).

    For each user stop (D759): run ONE Serper query, "<name>" <district or city>,
    and keep only the snippets that NAME the venue — those become the fact
    sheet's retrieved sources. Then number its body sentences and send them all
    in a single JSON request. The model labels each SUPPORTED / SENSORY /
    UNSUPPORTED against the fact sheet; drop every UNSUPPORTED sentence. SENSORY
    is allowed only when generic to the venue kind (no specific object, decor,
    smell or geography). A stop with NO venue-naming snippet is written ONLY from
    the deterministic ``grounded_user_stop_body()`` plus a deterministic
    orientation ("Look for <name>…") — no LLM body is kept at all. If fewer than
    2 sentences survive a verified stop, it also falls to the grounded body.

    Returns ``(new_text, report)`` where report carries::
        {'ran': bool, 'model': str, 'input_tokens', 'output_tokens', 'cost_usd',
         'serper_queries', 'serper_cost_usd', 'queries': [..],
         'stops': [{'stop','kept','dropped','grounded','snippets'}],
         'dropped_total'}

    ``serp_fn(query)->([{title,url,snippet}],latency)`` is injected for offline
    tests; the default uses the project's metered Serper caller. Retrieval is
    skipped when ``retrieve=False``. The verification call is skipped (ran=False)
    when there are no user stops, no api_key, or requests is unavailable — the
    delivered text is returned unchanged and the regex scrub stands as first pass.
    """
    model = model or _MODEL_DEFAULT
    report = {"ran": False, "model": model, "input_tokens": 0,
              "output_tokens": 0, "cost_usd": 0.0, "stops": [],
              "dropped_total": 0, "serper_queries": 0, "serper_cost_usd": 0.0,
              "queries": []}
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

        # [LOCAL-862] A stop the enrichment pass already finished deterministically
        # (thin: Places data only) is final — no second retrieval, no rewrite.
        if precomposed_titles and any(_fold(title) == _fold(t)
                                      for t in precomposed_titles):
            if log:
                log(f"[LOCAL-862] verify {title} skipped (precomposed thin stop)")
            continue
        # [LOCAL-862] A stop narrated from gathered material is verified against
        # THAT material (Places record, customer voice, own site, story search):
        # it is the fact sheet, so no extra Serper query is made.
        _mat = None
        if material_by_title:
            for _k, _v in material_by_title.items():
                if _fold(_k) == _fold(title):
                    _mat = _v
                    break
        if _mat:
            facts["retrieved_sources"] = [str(x)[:400] for x in _mat][:16]
            odf = list(_mat)

        # [LOCAL-855D] A documented monument/institution (cathedral, basilica,
        # palace, museum, …) is SOURCED — skip it so its dates survive
        # (Notre-Dame "built 1863–1880"). The 855B scrub already does not
        # date-gate these kinds; the verifier must match that, or it would
        # over-scrub the exact case the ticket's run B protects.
        _kind_fold = _fold(poi.get("type_specialty") or "")
        # [LOCAL-862 item 4] Landmark detection must not hang on the generator's
        # Type label ("Historical Landmark" one run, "Historical Site" the next —
        # Independence Palace was gutted to a grounded body when it read "Site").
        # Use the shared name+type classifier as well.
        try:
            from user_stop_enrichment import classify_stop_kind as _csk862
            _is_landmark862 = _csk862(title, poi.get("type_specialty") or "") == "landmark"
        except Exception:
            _is_landmark862 = False
        if (set(_kind_fold.split()) & _DOCUMENTED_KINDS) or _is_landmark862:
            if log:
                log(f"[LOCAL-855D] verify {title} skipped (documented monument "
                    f"kind — sourced dates kept)")
            continue

        # [LOCAL-855E item 3 / D759 (a)] ONE Serper query per user stop; keep only
        # venue-naming snippets and fold them into the fact sheet so the verifier
        # has a concrete source to judge SUPPORTED against. A documented monument
        # (skipped above) never reaches here, so no Serper spend on Notre-Dame.
        _venue_snippets = []
        if retrieve and not odf:
            try:
                _venue_snippets, _q, _nq = retrieve_user_stop_snippets(
                    title, poi, location, serp_fn=serp_fn, log=log)
                report["serper_queries"] += _nq
                if _q:
                    report["queries"].append(_q)
                if _venue_snippets:
                    existing = list(facts.get("retrieved_sources", []) or [])
                    facts["retrieved_sources"] = (existing + _venue_snippets)[:8]
            except Exception as _rerr:
                if log:
                    log(f"[LOCAL-855E] retrieval skipped for {title!r}: {_rerr}")

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
                          "sentences": sentences,
                          "has_snippets": bool(_venue_snippets or odf
                                               or not retrieve)})

    # [LOCAL-855E item 3 / D759] Serper spend for this tour: one query per stop.
    try:
        from cost_rates import SERPER_COST_PER_QUERY as _spq
    except Exception:
        _spq = 0.001
    report["serper_cost_usd"] = round(report["serper_queries"] * float(_spq), 6)

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
        # The verify call did not run / failed. The regex first pass stands for
        # stops WITH snippets, but D759 (c) is deterministic and must still apply:
        # a stop with NO venue-naming snippet is rewritten to the grounded body +
        # orientation regardless of the model, so no invented SENSORY detail can
        # ship just because the model was unavailable.
        _det_applied = 0
        for meta in stop_meta:
            if meta.get("has_snippets"):
                continue
            grounded = (grounded_user_stop_body(meta["poi"], location) or "").strip()
            orientation = _deterministic_orientation(meta["poi"], location)
            if grounded or orientation:
                _apply_grounded_with_orientation(lines, meta, grounded, orientation)
                dropped_n = len(meta["sentences"])
                report["dropped_total"] += dropped_n
                report["stops"].append({"stop": meta["name"], "kept": 0,
                                        "dropped": dropped_n, "grounded": True,
                                        "snippets": 0})
                _det_applied += 1
        if log:
            log("[LOCAL-855D] verify call did not run (no key / error) — "
                "regex first pass stands; "
                f"[LOCAL-855E] {_det_applied} no-snippet stop(s) -> deterministic "
                "grounded body")
        return ("\n".join(lines) if _det_applied else tour_text), report
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

    # 4) Apply: D759 — a stop with NO venue-naming snippet is written ONLY from
    #    the deterministic grounded body + a deterministic orientation (no LLM
    #    body kept). A stop WITH snippets keeps its SUPPORTED/SENSORY sentences;
    #    drop UNSUPPORTED; if <2 survive, fall to the grounded body.
    for meta in stop_meta:
        sid = meta["id"]
        name = meta["name"]
        lab = labels_by_stop.get(sid, {})
        sentences = meta["sentences"]

        # [LOCAL-855E item 3 / D759 (c)] No retrieved source NAMES this venue:
        # take no LLM body at all. The stop is the deterministic grounded body
        # plus a deterministic orientation — nothing the model wrote survives, so
        # there is no SENSORY/atmosphere invention (no sea, harp, altar, poster).
        if not meta.get("has_snippets"):
            grounded = (grounded_user_stop_body(meta["poi"], location) or "").strip()
            orientation = _deterministic_orientation(meta["poi"], location)
            if grounded or orientation:
                _apply_grounded_with_orientation(lines, meta, grounded, orientation)
                dropped_n = len(sentences)
                report["stops"].append({"stop": name, "kept": 0,
                                        "dropped": dropped_n, "grounded": True,
                                        "snippets": 0})
                report["dropped_total"] += dropped_n
                if log:
                    log(f"[LOCAL-855E] verify {name}: no venue-naming snippet — "
                        f"deterministic grounded body + orientation (dropped "
                        f"{dropped_n} LLM sentence(s))")
                continue

        # A sentence with no returned label is KEPT (conservative — the model
        # only removes what it positively calls UNSUPPORTED).
        keep_flags = [lab.get(i, "SUPPORTED") != "UNSUPPORTED"
                      for i in range(len(sentences))]
        # [LOCAL-860 item 3] A kept sentence that opens with a back-reference
        # (This/These/It/Its/…/The contrast) right after a dropped one has lost its
        # antecedent (An Spa: "This juxtaposition…"). Drop it too; never empties.
        keep_flags, _orph = apply_orphan_rule(sentences, keep_flags)
        if _orph and log:
            log(f"[LOCAL-860] verify {name}: dropped {len(_orph)} orphaned "
                f"back-reference sentence(s)")
        kept_n = sum(1 for f in keep_flags if f)
        dropped_n = len(sentences) - kept_n

        if kept_n < 2:
            # Not enough grounded material survives — use the deterministic body.
            grounded = grounded_user_stop_body(meta["poi"], location)
            grounded = (grounded or "").strip()
            if grounded:
                _apply_grounded(lines, meta, grounded)
                report["stops"].append({"stop": name, "kept": kept_n,
                                        "dropped": dropped_n, "grounded": True,
                                        "snippets": 1})
                report["dropped_total"] += dropped_n
                if log:
                    log(f"[LOCAL-855D] verify {name} kept {kept_n} dropped "
                        f"{dropped_n} -> grounded body")
                continue
            # No grounded body possible: keep as-is (never empty).
            report["stops"].append({"stop": name, "kept": len(sentences),
                                    "dropped": 0, "grounded": False,
                                    "snippets": 1})
            if log:
                log(f"[LOCAL-855D] verify {name} kept {len(sentences)} dropped 0 "
                    f"(no grounded fallback; left unchanged)")
            continue

        # Rewrite each body paragraph keeping only its non-UNSUPPORTED sentences.
        _apply_drops(lines, meta, keep_flags)
        _lift_into_empty_orientation(lines, meta)
        # [LOCAL-855E item 3] Every user stop must NAME its venue. If dropping the
        # orientation left the surviving text without the venue name (it can read
        # as "This place…" / "this venue…"), prepend the deterministic
        # orientation ("Look for <name> at <where>") so the stop is unambiguously
        # about the venue the listener chose.
        _folded_name = _fold(name)
        _name_toks = [w for w in _folded_name.split() if len(w) >= 3]
        _surviving = _fold(" ".join(
            lines[abs_idx] for abs_idx in sorted(meta["para_sent_counts"].keys())))
        _names_venue = bool(_folded_name and _folded_name in _surviving) or (
            bool(_name_toks) and all(t in _surviving for t in _name_toks))
        if not _names_venue:
            orientation = _deterministic_orientation(meta["poi"], location)
            if orientation:
                _prepend_orientation(lines, meta, orientation)
                if log:
                    log(f"[LOCAL-855E] verify {name}: surviving text did not name "
                        f"the venue — prepended deterministic orientation")
        report["stops"].append({"stop": name, "kept": kept_n,
                                "dropped": dropped_n, "grounded": False,
                                "snippets": 1,
                                "dropped_sentences": [
                                    s for s, f in zip(sentences, keep_flags) if not f],
                                "labels": {str(i): lab.get(i, "") for i in
                                           range(len(sentences))}})
        report["dropped_total"] += dropped_n
        if log:
            log(f"[LOCAL-855D] verify {name} kept {kept_n} dropped {dropped_n}")
            for s, f in zip(sentences, keep_flags):
                if not f:
                    log(f"[LOCAL-855D]   dropped: {s[:160]}")

    return "\n".join(lines), report


def _prepend_orientation(lines: List[str], meta: dict, orientation: str):
    """Put the deterministic orientation on the stop's Orientation line (or the
    first body paragraph), keeping whatever text already survives there."""
    for abs_idx in sorted(meta["para_sent_counts"].keys()):
        is_or, _ss = meta["para_sent_counts"][abs_idx]
        cur = lines[abs_idx]
        if is_or:
            label, _, val = cur.partition(":")
            val = val.strip()
            lines[abs_idx] = f"{label}: {orientation}" + (f" {val}" if val else "")
            return
    # No Orientation line: prepend to the first body paragraph.
    for abs_idx in sorted(meta["para_sent_counts"].keys()):
        cur = lines[abs_idx].strip()
        if cur:
            lines[abs_idx] = f"{orientation} {cur}".strip()
            return
        lines[abs_idx] = orientation
        return


def _deterministic_orientation(poi: Dict, location: str = "") -> str:
    """[LOCAL-855E item 3 / D759 (c)] A deterministic orientation for a user stop
    with no retrieved source: "Look for <name> at <address/district/city>." No
    invented object, decor, smell or geography — only the listener's own name and
    a place fragment that is already on the fact sheet."""
    name = (poi.get("name") or poi.get("title") or "").strip()
    if not name:
        return ""
    addr = (poi.get("address") or "").strip().rstrip(",").strip()
    if addr:
        return f"Look for {name} at {addr}."
    # [LEAD 855E review] a city is a place you are IN, not AT.
    city = city_from_scope(location)
    if city:
        return f"Look for {name} in {city}."
    return f"Look for {name}."


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


def _lift_into_empty_orientation(lines: List[str], meta: dict) -> None:
    """[LOCAL-862] If drops emptied the Orientation line while a later body
    paragraph survives, move that paragraph's text up (never ship 'Orientation:'
    with nothing after it)."""
    keys = sorted(meta["para_sent_counts"].keys())
    or_idx = next((k for k in keys if meta["para_sent_counts"][k][0]), None)
    if or_idx is None:
        return
    label, _, val = lines[or_idx].partition(":")
    if val.strip():
        return
    for k in keys:
        if k != or_idx and lines[k].strip():
            lines[or_idx] = f"{label}: {lines[k].strip()}"
            lines[k] = ""
            return


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


def _apply_grounded_with_orientation(lines: List[str], meta: dict,
                                     grounded: str, orientation: str):
    """[LOCAL-855E item 3 / D759 (c)] Write the stop as the deterministic
    orientation + grounded body only. The orientation goes on the Orientation
    line when the block has one (else it is prepended to the grounded body on the
    first paragraph); the grounded body fills the first non-orientation
    paragraph; all other body paragraphs are blanked. No model sentence survives.
    """
    keys = sorted(meta["para_sent_counts"].keys())
    orientation_written = False
    body_written = False
    for abs_idx in keys:
        is_or, _ss = meta["para_sent_counts"][abs_idx]
        if is_or:
            label = lines[abs_idx].split(":", 1)[0]
            lines[abs_idx] = (f"{label}: {orientation}".rstrip()
                              if orientation else f"{label}:")
            orientation_written = bool(orientation)
        elif not body_written:
            if orientation and not orientation_written:
                lines[abs_idx] = f"{orientation} {grounded}".strip()
                orientation_written = True
            else:
                lines[abs_idx] = grounded
            body_written = True
        else:
            lines[abs_idx] = ""
    # If there was an Orientation line but no separate body paragraph to hold the
    # grounded body, append the grounded body to the orientation line.
    if grounded and not body_written and orientation_written:
        for abs_idx in keys:
            is_or, _ss = meta["para_sent_counts"][abs_idx]
            if is_or:
                lines[abs_idx] = f"{lines[abs_idx]} {grounded}".strip()
                break
