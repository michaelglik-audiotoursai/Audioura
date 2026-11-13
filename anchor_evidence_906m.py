"""[LOCAL-906M] A user stop with a GENERIC title is anchored to the tour's place; later-stop Directions sentences go.

Pure, free, never raises. Generic names only (D769).

* ``is_generic_title``   -- "The cable car ascent", "The summit views", "Dragon fruit country": no proper name.
* ``anchors_for``        -- the tour's place (request destination / area), else the previous / next NAMED stop.
* ``anchored_queries``   -- a search query for a generic stop carries the anchor.
* ``mentions``           -- the folded text names the anchor (diacritics, case, a trailing kind word, spacing).
* ``reject_evidence``    -- ``[LOCAL-906M] Stop N evidence rejected: no '<anchor>' in <url>`` (None = accepted).
* ``drop_other_site_landmarks`` -- delivery: a body sentence of a generic-title stop that names a landmark found in
  neither the tour nor the stop's anchored evidence is dropped (906K ``other_landmark``, every body sentence).
* ``trim_directions``    -- a Directions block belongs to the leg it starts: a sentence naming Stop N+2 or later goes.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Sequence

import route_content_896 as rc

TAG = "[LOCAL-906M]"

_KIND = re.compile(r"(?i)\s+(?:mountain|mount|mt\.?|hill|peak|lake|beach|temple|pagoda|park|island|river|falls?|"
                   r"village|town|city|province|district|national\s+park)$")
_LEAD = re.compile(r"(?i)^(?:arriving\s+(?:at|in)|leaving|departing|approaching|welcome\s+to|from|to|at|in|the)\s+")


def _emit(log: Optional[Callable]) -> Callable:
    return log or (lambda _m: None)


def _fold(x: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", rc.fold(x or ""))).strip()


# ══ 1. generic title ═════════════════════════════════════════════════════════════════════════════════════
def _head(title: str) -> str:
    """The part of a title before a subtitle dash / colon (\"Arriving at X – the mountain\" -> \"Arriving at X\")."""
    return re.split(r"\s+[–—-]\s+|\s*:\s+", title or "", maxsplit=1)[0].strip()


def is_generic_title(title: str) -> bool:
    """True when the title carries no proper name: after the first word, no capitalised word, digit-led name or
    ``<placeholder>``. \"The cable car ascent\", \"The summit views and the drive home\", \"Dragon fruit country\"."""
    t = re.sub(r"https?\S+", " ", title or "").strip()
    if not t or "<" in t:
        return False
    head = _head(t)
    words = re.findall(r"[^\W\d_][\w'’\-]*|\d[\w\-]*", head)
    if not words:
        return False
    for w in words[1:]:
        if w[:1].isupper():
            return False
    # a 1-word title is a single proper name unless it is an article-led phrase
    if len(words) == 1:
        return False
    return True


# ══ 2. anchors ═══════════════════════════════════════════════════════════════════════════════════════════
def _named(title: str) -> bool:
    return bool((title or "").strip()) and not is_generic_title(title)


def _core(title: str) -> str:
    """The searchable core of a named stop title (subtitle and leading verb dropped)."""
    t = _LEAD.sub("", _head(re.sub(r"https?\S+", " ", title or "")).strip()).strip()
    return t


_CONN = frozenset("of the de la le du des del della da do dos das di van von".split())
# a title naming a kind of PLACE / structure: its facts belong to the destination's site
_LANDMARK_NOUN = re.compile(r"(?i)\b(?:ascent|cable\s*car|ropeway|gondola|summit|peak|view(?:s|point)?|temple|pagoda|shrine|"
                            r"church|cathedral|mosque|museum|gallery|castle|palace|fort(?:ress)?|tower|bridge|beach|"
                            r"lake|river|falls?|waterfall|cave|island|garden|park|statue|buddha|monument|gate|market|"
                            r"harbou?r|port|dune|dunes|trail|climb|hike|drive\s+home|road)\b")


def is_topic_like(title: str) -> bool:
    """[LOCAL-906O] A generic title that is a TOPIC of the region, not a site: a crop, a dish, a craft (\"Dragon fruit
    country\"): no landmark noun. Its facts are the province's / the country's."""
    return is_generic_title(title) and not _LANDMARK_NOUN.search(_head(title or ""))


def name_cores(title: str) -> List[str]:
    """[LOCAL-906O] The proper-name cores of a NAMED stop title, never the whole title: \"Phan Thiet and the Ca Ty River\" ->
    [\"Phan Thiet\", \"Ca Ty River\"]; \"Leaving Mui Ne – the fishing coast\" -> [\"Mui Ne\"]. Runs of capitalised words (small
    linking words allowed inside a run)."""
    head = _LEAD.sub("", _head(re.sub(r"https?\S+", " ", title or "")).strip()).strip()
    out: List[str] = []
    for piece in re.split(r"\s+(?:and|&)\s+|,|;|/", head):
        run: List[str] = []
        runs: List[List[str]] = []
        for w in re.findall(r"[^\W\d_][\w'’\-]*|\d[\w\-]*", piece):
            if w[:1].isupper() or w[:1].isdigit():
                run.append(w)
            elif w.lower() in _CONN and run:
                run.append(w)
            else:
                if run:
                    runs.append(run)
                run = []
        if run:
            runs.append(run)
        for r in runs:
            while r and r[-1].lower() in _CONN:
                r = r[:-1]
            name = " ".join(r).strip()
            if name and _fold(name) and name not in out:
                out.append(name)
    return out


def region_names(region: str) -> Dict[str, str]:
    """``{"province": ..., "country": ...}`` of a request region (\"Binh Thuan, Vietnam\", \"Binh Thuan province\")."""
    parts = [x.strip() for x in re.split(r"[,;]", region or "") if x.strip()]
    country = ""
    try:
        from city_scope import is_country_name
        if parts and is_country_name(parts[-1]):
            country = parts.pop()
    except Exception:
        if len(parts) >= 2:
            country = parts.pop()
    province = parts[0] if parts else ""
    return {"province": province, "country": country}


def anchors_for(title: str, titles: Sequence[str] = (), destination: str = "", area: str = "",
                region: str = "") -> List[str]:
    """[LOCAL-906O] Anchors of a generic-title stop, best first. PLACE NAMES only, never a whole user title: the
    request's destination, its province / region and country, and the proper-name cores of the previous / next NAMED
    stop. A page naming ANY of them is accepted. A TOPIC-like title (a crop, a dish, a craft) is anchored by the
    province, then the country (then the destination and the neighbours' names). [] for a stop that names itself."""
    if not is_generic_title(title):
        return []
    out: List[str] = []

    def add(x: str) -> None:
        x = (x or "").strip(" ,.;")
        if x and _fold(x) and _fold(x) not in {_fold(o) for o in out}:
            out.append(x)

    rn = region_names(region)
    province = rn["province"] or (area or "")
    country = rn["country"]
    neigh: List[str] = []
    ts = [str(t) for t in titles or []]
    try:
        i = next(k for k, t in enumerate(ts) if _fold(t) == _fold(title))
    except StopIteration:
        i = None
    if i is not None:
        for rng in (range(i - 1, -1, -1), range(i + 1, len(ts))):
            for j in rng:
                if _named(ts[j]):
                    neigh.extend(name_cores(ts[j]))
                    break
    if is_topic_like(title):
        add(province)
        add(country)
        add(destination)
        for n in neigh:
            add(n)
    else:
        add(destination)
        add(area)
        for n in neigh:
            add(n)
        if not out:
            add(province)
    return out


def anchored_queries(queries: Sequence[str], anchors: Sequence[str]) -> List[str]:
    """Every query carries the primary anchor (appended when its folded text does not already hold it)."""
    if not anchors:
        return list(queries)
    a = anchors[0]
    out: List[str] = []
    for q in queries:
        q2 = q if mentions(q, [a]) else f"{q} {a}".strip()
        if q2 not in out:
            out.append(q2)
    return out


# ══ 3. does the evidence name the anchor ═════════════════════════════════════════════════════════════════
def _variants(anchor: str) -> List[str]:
    """Folded spellings of an anchor: full, without a trailing kind word, with and without spaces."""
    full = _fold(anchor)
    if not full:
        return []
    short = _fold(_KIND.sub("", anchor.strip()))
    vs = [full]
    if short and short != full:
        vs.append(short)
    vs += [v.replace(" ", "") for v in list(vs) if " " in v]
    return [v for v in dict.fromkeys(vs) if len(v) >= 3]


def mentions(text: str, anchors: Sequence[str]) -> bool:
    """True when the folded ``text`` names any anchor (whole-word, any spelling). No anchor = nothing to test = True."""
    if not [a for a in anchors if _fold(a)]:
        return True
    hay = " " + _fold(text) + " "
    glued = hay.replace(" ", "")
    for a in anchors:
        for v in _variants(a):
            if " " in v:
                if (" " + v + " ") in hay:
                    return True
            elif (" " + v + " ") in hay or (len(v) >= 6 and v in glued):
                return True
    return False


def reject_evidence(num: object, anchors: Sequence[str], text: str, url: str = "",
                    log: Optional[Callable] = None) -> bool:
    """True = the page / snippet does not name the anchor (logged); False = accepted (or no anchor to test)."""
    if mentions(text, anchors):
        return False
    _emit(log)(f"  {TAG} Stop {num} evidence rejected: no '{anchors[0]}' in {url or '(snippet)'}")
    return True


# ══ 4. delivery: other-site landmarks in a generic stop's body ═══════════════════════════════════════════
def drop_other_site_landmarks(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                              log: Optional[Callable] = None) -> str:
    """A body sentence of a generic-title stop that names a landmark found in no title, no other stop and not in this
    stop's own evidence is dropped (906K ``other_landmark`` applied to every body sentence)."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        import leftovers_906c as c
        import leftovers_906f as f
        import refill_quality_906k as k
        ev_map = c._ev_map(evidence_by_title)
        infos = c._stops_info(tour_text)
        if not infos:
            return tour_text
        titles = " ".join(i["title"] for i in infos)

        def fn(st: Dict, _all: List[Dict]):
            if not is_generic_title(st["title"]):
                return {}
            ev = rc._ev_for(ev_map, st["title"]) or ""
            # the tour as the OTHER stops and the stop's own keyed lines see it (never the stop's own body)
            own_keyed = " ".join(ln for ln in st["lines"] if rc._KEYED.match(ln or "") or ln is st["lines"][0])
            known = " ".join([tour_text[:st["s"]], tour_text[st["e"]:], titles, ev, own_keyed])
            edits = {}
            for i, j, x in st["flat"]:
                other = k.other_landmark(x, st["title"], known)
                if other:
                    emit(f'  {TAG} Stop {st["num"]}: names {other[:40]!r}, in neither the tour nor the stop\'s '
                         f'anchored evidence -> dropped: "{x[:80]}"')
                    edits[(i, j)] = []
            return edits
        return f._each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} other-site landmark guard skipped (non-fatal): {err}")
        return tour_text


# ══ 5. Directions name only the leg's own end ════════════════════════════════════════════════════════════
def _name_forms(title: str) -> List[str]:
    """Folded forms of a named title that identify it in prose: the core, and the core without its kind word."""
    if not _named(title):
        return []
    core = _core(title)
    forms = [_fold(core)]
    short = _fold(_KIND.sub("", core))
    if short and short != forms[0] and len(short.split()) >= 1 and len(short) >= 4:
        forms.append(short)
    return [f for f in dict.fromkeys(forms) if len(f) >= 4]


def _names_in(sentence: str, forms: Sequence[str]) -> bool:
    hay = " " + _fold(sentence) + " "
    return any((" " + f + " ") in hay for f in forms)


def trim_directions(tour_text: str, log: Optional[Callable] = None) -> str:
    """Drop the sentences of Stop N's ``Directions:`` that name Stop N+2 or a later stop (unless that name is also part
    of Stop N's or Stop N+1's own title). A block keeps at least its first sentence."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        blocks = rc._stop_blocks(tour_text)
        if len(blocks) < 3:
            return tour_text
        titles = [b[3] for b in blocks]
        out, pos, changed = [], 0, False
        for k, (s, e, num, title) in enumerate(blocks):
            out.append(tour_text[pos:s])
            pos = e
            block = tour_text[s:e]
            later: List[str] = []
            near = _fold(titles[k]) + " " + (_fold(titles[k + 1]) if k + 1 < len(titles) else "")
            for t in titles[k + 2:]:
                for f in _name_forms(t):
                    if (" " + f + " ") not in (" " + near + " "):
                        later.append(f)
            if not later:
                out.append(block)
                continue
            lines = block.split("\n")
            for li, ln in enumerate(lines):
                m = re.match(r"(?i)^(\s*directions\s*:\s*)(.*)$", ln)
                if not m:
                    continue
                sents = rc.split_sentences(m.group(2))
                keep = [x for x in sents if not _names_in(x, later)]
                if len(keep) != len(sents) and keep:
                    for x in sents:
                        if x not in keep:
                            emit(f'  {TAG} Stop {num}: Directions sentence names a later stop (not the next one) '
                                 f'-> dropped: "{x[:90]}"')
                    lines[li] = m.group(1) + " ".join(keep)
                    changed = True
            out.append("\n".join(lines))
        out.append(tour_text[pos:])
        return "".join(out) if changed else tour_text
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} directions guard skipped (non-fatal): {err}")
        return tour_text
