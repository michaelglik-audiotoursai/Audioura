"""[D571/D576] What does this venue CONSIST OF? — the two-question stop source.

Michael's method, 2026-09-17. A named building is a building tour (D571), and its
stops are not "whatever is famous nearby" and not "catalogued artworks". They are
the parts the building is made of.

**Question 1 — what IS this?**   "Our Lady Help of Christians" -> a Catholic parish church
**Question 2 — what does that KIND of place consist of, for a tour?**
    narthex, baptismal font, nave, stained glass, pulpit, Stations of the Cross,
    rood screen, chancel, altar, tabernacle, transepts, side chapels, sacristy, crypt
**Question 3 — which of those does THIS one have?**  (grounded, per-venue, verifiable)

**Why this is safe where the museum path was not.** Q2 is knowledge about the CLASS.
"A church has a nave" cannot be a falsehood about Newton. Only Q3 is venue-specific,
and it asks a closed yes/no about a named part rather than inviting a model to name
objects — which is what produced the Sistine Chapel Ceiling in a Newton parish (D564).

D548 already recorded the failure this avoids: *"The strongest source in the system
was being asked the wrong question."* Same fix, one level up — ask what the building
is made of, not what is famous in it.

Every model call is injected, so the module is deterministic and offline in tests.
"""

import json
import os
import re
import threading

MAX_PARTS = 24

# ── Q2 cache ────────────────────────────────────────────────────────────────
# What a KIND of building consists of does not change, so the answer is cacheable
# forever. Michael, 2026-09-17: *"let's keep it in cache but do not assume that we
# will get cache so large that it will encapsulate all such questions: what if it
# is not catholic church, but Jewish synagogue, or Indian temple, or industrial
# port, or zoo."*
#
# THE POLICY: cache every kind, expire nothing, and always work on a miss. A rare
# kind simply never gets a second hit — it costs one ask, exactly as if there were
# no cache. Caching is a saving on repeats, never a precondition. There is no
# "cacheable kinds" list to maintain and nothing to fall off the end of.
#
# Normalisation is deliberately CONSERVATIVE. "Russian Orthodox church" and
# "Catholic parish church" must NOT collapse together — one has an iconostasis and
# a royal door, the other a rood screen and Stations of the Cross. Only casing,
# punctuation, articles and whitespace are normalised; never a denominational,
# national or functional word.
_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           '.venue_parts_cache.json')
_CACHE_LOCK = threading.Lock()
_ARTICLES = ('a ', 'an ', 'the ')


def normalise_kind(kind):
    k = re.sub(r'[^\w\s-]', ' ', (kind or '').lower())
    k = re.sub(r'\s+', ' ', k).strip()
    for art in _ARTICLES:
        if k.startswith(art):
            k = k[len(art):]
    return k.strip()


def _cache_load():
    try:
        with open(_CACHE_PATH) as fh:
            d = json.load(fh)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def cache_get(kind):
    return _cache_load().get(normalise_kind(kind))


def cache_put(kind, parts):
    key = normalise_kind(kind)
    if not key or not parts:
        return
    with _CACHE_LOCK:
        d = _cache_load()
        d[key] = list(parts)
        try:
            tmp = _CACHE_PATH + '.tmp'
            with open(tmp, 'w') as fh:
                json.dump(d, fh, indent=1, sort_keys=True)
            os.replace(tmp, _CACHE_PATH)
        except Exception:
            pass


def _coerce_list(raw):
    """Pull a clean list of short names out of whatever the model returned."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        text = str(raw).strip()
        items = None
        m = re.search(r'\[.*\]', text, re.S)
        if m:
            try:
                items = json.loads(m.group(0))
            except Exception:
                items = None
        if items is None:
            items = [ln for ln in text.splitlines()]
    out, seen = [], set()
    for it in items:
        s = re.sub(r'^\s*(?:[-*•]|\d+[.)])\s*', '', str(it)).strip()
        s = s.strip(' .;:"\'')
        s = re.sub(r'\s*[—:-]\s.*$', '', s).strip()      # drop trailing explanations
        if 1 < len(s) <= 60 and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
        if len(out) >= MAX_PARTS:
            break
    return out


def identify_venue_kind(venue_name, location, ask):
    """Q1: what kind of place is this? Returns a short noun phrase, or ''.

    `ask(prompt) -> str` is injected.
    """
    if not venue_name:
        return ''
    prompt = (
        f'What kind of place is "{venue_name}"{" in " + location if location else ""}?\n'
        'Answer with ONE short noun phrase naming the category of building or site — '
        'for example: "Catholic parish church", "international airport", "art museum", '
        '"royal palace", "railway station". No sentence, no explanation.'
    )
    try:
        raw = ask(prompt)
    except Exception:
        return ''
    kind = (str(raw or '')).strip().strip('."\'')
    kind = kind.splitlines()[0].strip() if kind else ''
    return kind[:60]


def parts_for_kind(kind, ask, use_cache=True):
    """Q2: what does that KIND of place consist of, for a tour?

    Knowledge about the CLASS — cannot be a falsehood about any particular venue.
    Returns an ordered list, roughly the order a visitor meets them.

    Cached by normalised kind (see the policy note at the top of this module): a
    repeat kind costs nothing, a novel kind costs one ask and then joins the cache.
    """
    if not kind:
        return []
    if use_cache:
        hit = cache_get(kind)
        if hit:
            return list(hit)
    prompt = (
        f'When people take a tour inside a {kind}, what are the parts, spaces and '
        f'fixtures they want to see and learn about?\n'
        'List them in the order a visitor naturally encounters them, from the entrance '
        'inward. Each item must be a PART OF THE BUILDING or a fixture in it — not an '
        'activity, not a format, not a nearby attraction.\n'
        'Answer as a JSON array of short names only.'
    )
    try:
        parts = _coerce_list(ask(prompt))
    except Exception:
        return []
    if use_cache and parts:
        cache_put(kind, parts)
    return parts


def parts_present(venue_name, location, parts, ask_grounded):
    """Q3: which of those parts does THIS venue actually have?

    `ask_grounded(prompt) -> (text, sources)` — the grounded client, because this is
    the only venue-specific step and it is the one that can be wrong.

    Returns {"present": [...], "absent": [...], "unknown": [...], "sources": [...]}.
    A part we cannot confirm lands in `unknown`, NOT `absent` — D577: unverified
    material still ships, hedged. Only a part positively contradicted is dropped.
    """
    rec = {"present": [], "absent": [], "unknown": list(parts or []), "sources": []}
    if not venue_name or not parts:
        return rec
    listing = "\n".join(f"- {p}" for p in parts)
    prompt = (
        f'For "{venue_name}"{" in " + location if location else ""}, which of the '
        f'following does it actually have? Use only what your sources support.\n\n'
        f'{listing}\n\n'
        'Answer as JSON: {"present": [...], "absent": [...], "unknown": [...]}. '
        'Put an item in "unknown" if the sources do not say — do not guess.'
    )
    try:
        text, sources = ask_grounded(prompt)
    except Exception:
        return rec
    rec["sources"] = list(sources or [])
    data = None
    m = re.search(r'\{.*\}', str(text or ''), re.S)
    if m:
        try:
            data = json.loads(m.group(0))
        except Exception:
            data = None
    if not isinstance(data, dict):
        return rec
    known = {p.lower(): p for p in parts}
    claimed = set()
    for bucket in ("present", "absent", "unknown"):
        vals = []
        for item in _coerce_list(data.get(bucket)):
            canon = known.get(item.lower())
            if canon and canon.lower() not in claimed:
                claimed.add(canon.lower())
                vals.append(canon)
        rec[bucket] = vals
    # Anything the model did not place at all stays unknown, never absent.
    rec["unknown"] += [p for p in parts if p.lower() not in claimed]
    return rec


def venue_parts_stops(venue_name, location, ask, ask_grounded, want=None,
                      use_cache=True):
    """The whole three-question chain -> an ordered stop-name list.

    Present parts first, in class order; then unknown parts (D577 — unverified
    ships, hedged). Absent parts are dropped. Returns (stops, evidence).
    """
    kind = identify_venue_kind(venue_name, location, ask)
    parts = parts_for_kind(kind, ask, use_cache=use_cache)
    pres = parts_present(venue_name, location, parts, ask_grounded)
    ordered = [p for p in parts if p in pres["present"]] + \
              [p for p in parts if p in pres["unknown"]]
    if want:
        ordered = ordered[:want]
    evidence = {"kind": kind, "class_parts": parts, "present": pres["present"],
                "unknown": pres["unknown"], "absent": pres["absent"],
                "sources": pres["sources"]}
    return ordered, evidence


# ── Q1 validation, via Q2's answer ──────────────────────────────────────────
# Michael, 2026-09-17: *"we do need a sanity check, but also we need to learn how
# to ask the second question… so the answer on the second question is more
# important sanity check than just sanity check on the first question alone."*
#
# Exactly right, and it costs nothing extra. If Q1 misfires — "Our Lady Help of
# Christians" -> "a Marian devotional title" — then Q2 ("what does a tour inside a
# Marian devotional title consist of") cannot return physical parts, because there
# is no building. **A Q2 answer that is not a list of places is the evidence that
# Q1 was wrong.** Checking Q1 on its own could never see this.
#
# His own transcript is the proof: asking "what is the church consists of?" returned
# theology — *"The church consists of people, not buildings… believers, the Head,
# the Spirit."* Those are not parts of a building, and that is detectable.

_NON_PHYSICAL = (
    'people', 'believers', 'community', 'congregation', 'faith', 'spirit',
    'fellowship', 'worship', 'belief', 'doctrine', 'theology', 'tradition',
    'history', 'culture', 'experience', 'atmosphere', 'symbolism', 'meaning',
)
MIN_PHYSICAL_PARTS = 3


def looks_physical(part):
    """A tour stop is somewhere you can stand. 'The Holy Spirit' is not."""
    p = (part or '').strip().lower()
    if not p:
        return False
    return not any(w == p or p.startswith(w + ' ') or p.endswith(' ' + w)
                   for w in _NON_PHYSICAL)


def validate_kind_via_parts(parts):
    """Return (ok, physical_parts, reason). Q2's answer judges Q1."""
    physical = [p for p in (parts or []) if looks_physical(p)]
    if len(physical) < MIN_PHYSICAL_PARTS:
        return False, physical, (
            f'only {len(physical)} of {len(parts or [])} answers name something you '
            f'can stand next to — the venue kind is probably wrong')
    return True, physical, 'ok'


# ── The story questions ─────────────────────────────────────────────────────
# Michael, 2026-09-17, on why a parts list alone would be dull:
#
#   *"description of an altar may be boring, but who came to this altar and what
#   did they do and were hoping to achieve is not boring. In St Nicholas church in
#   Nice France I was fascinated to learn that it was built because of the death of
#   the Russian Tsar heir; and all inside of the church was paid by Russians, had
#   icons that invoke the heavenly patronage of the Romanov family's patron saints…
#   who the painters were, who the architect, who gave the money… the fact that this
#   is the largest Russian Orthodox church in France."*
#
# Two questions, because his example contains two KINDS of story:
#   * **venue-level** — why this building exists at all, who willed it, who paid,
#     who made it, what it is the largest/first/only of. Asked ONCE per tour.
#   * **part-level** — his formulation, applied to a specific part: who came here,
#     what did they do, what were they hoping to achieve.
#
# Both are grounded (sources required). Neither asks "what is an altar" — that is
# the encyclopaedia question that produces the glossary tour.

def venue_story_prompt(venue_name, location, kind=''):
    """Why does this place exist, and who made it happen?"""
    where = f' in {location}' if location else ''
    what = f' ({kind})' if kind else ''
    return (
        f'Tell me what is singular and surprising about "{venue_name}"{where}{what}.\n'
        'Specifically:\n'
        '  - Why was it built, and what event or person caused it to exist?\n'
        '  - Who paid for it, who designed it, who made the art in it — by name?\n'
        '  - What is it the largest, first, only or last of?\n'
        '  - What happened here that people still argue about or remember?\n'
        'Give concrete, checkable facts with names and dates. Cite your sources. '
        'If you do not know something, say so rather than guessing.'
    )


def part_story_prompt(part, venue_name, location=''):
    """Michael's formulation: who came to this part, and what were they after?"""
    where = f' in {location}' if location else ''
    return (
        f'About the {part} of "{venue_name}"{where}:\n'
        f'  - Who came to this {part}, and what did they do there?\n'
        f'  - What were they hoping to achieve?\n'
        f'  - Who made it or paid for it, and why that person?\n'
        f'  - What does it show or contain that it would not have if it stood '
        f'somewhere else?\n'
        'Concrete people, dates and events — not a description of what a '
        f'{part} is in general. Cite your sources; say so if you do not know.'
    )


# ── Production adapters ─────────────────────────────────────────────────────
# The module keeps every model call injected so tests stay offline. These are the
# two callables production passes in.

def default_ask(prompt, timeout=60):
    """Ungrounded asker for Q1/Q2 — class knowledge, no sources needed."""
    try:
        from story_leads import gemini_with_sources
    except Exception:
        return ''
    out = gemini_with_sources(prompt, resolve=False, timeout=timeout) or {}
    return out.get('text', '') or ''


def default_ask_grounded(prompt, timeout=90):
    """Grounded asker for Q3 and the story questions — returns (text, sources)."""
    try:
        from story_leads import gemini_with_sources
    except Exception:
        return '', []
    out = gemini_with_sources(prompt, resolve=True, timeout=timeout) or {}
    srcs = [s.get('url') or s.get('domain') for s in (out.get('sources') or [])]
    return out.get('text', '') or '', [s for s in srcs if s]


def build_tour_stops(venue_name, location, want, ask=None, ask_grounded=None,
                     use_cache=True):
    """The whole chain, production-shaped. Returns (stop_names, evidence).

    Falls back to an empty list on any failure, so the caller keeps its existing
    path — D577: never turn a working tour into no tour.
    """
    ask = ask or default_ask
    ask_grounded = ask_grounded or default_ask_grounded
    try:
        kind = identify_venue_kind(venue_name, location, ask)
        parts = parts_for_kind(kind, ask, use_cache=use_cache)
        ok, physical, why = validate_kind_via_parts(parts)
        if not ok:
            # Q2's answer says Q1 was wrong. Do not build a tour on it.
            return [], {"kind": kind, "rejected": why, "class_parts": parts}
        pres = parts_present(venue_name, location, physical, ask_grounded)
        candidates = [p for p in physical if p in pres["present"]] + \
                     [p for p in physical if p in pres["unknown"]]

        # [Michael, 2026-09-18] STORY FIRST, PARTS SECOND. Run the causal chain —
        # why does this exist / who created it / who paid / who came / what is it
        # the only one of — then place those stories in the parts of the building
        # they happened in. Ranking parts by "which is most interesting" (the
        # previous approach, kept below as the fallback) asks an airport what is
        # interesting about a control tower and gets machinery; the causal chain
        # asks why the airport exists and gets Wood Island Park, Neptune Road and
        # the families Massport displaced.
        chain = venue_story_chain(venue_name, location, ask_grounded)
        placed = place_stories_in_building(venue_name, location, chain,
                                           candidates, ask_grounded)
        if placed:
            by_story = [r["part"] for r in placed]
            by_story += [p for p in candidates if p not in by_story]
        else:
            by_story = rank_parts_by_story(venue_name, location, candidates, ask_grounded)
        chosen = by_story[:want] if want else by_story
        ordered = [p for p in physical if p in chosen]
        return ordered, {"kind": kind, "class_parts": parts, "physical": physical,
                         "story_rank": by_story[:8],
                         "story_chain": {k: {"chars": len(v.get("text") or ""),
                                             "sources": len(v.get("sources") or [])}
                                         for k, v in (chain or {}).items()},
                         "placed": placed,
                         "lore": distribute_lore(ordered, placed, chain),
                         "present": pres["present"], "unknown": pres["unknown"],
                         "absent": pres["absent"], "sources": pres["sources"]}
    except Exception as e:
        return [], {"error": str(e)}


def rank_parts_by_story(venue_name, location, parts, ask_grounded):
    """Rank parts by how much REMARKABLE, venue-specific history attaches to each.

    Michael, 2026-09-17: *"description of an altar may be boring, but who came to
    this altar and what did they do and were hoping to achieve is not boring."*

    Q2 returns parts in walking order — entrance inward — so taking the first N
    gives Porch, Narthex, Nave: architecturally correct and dull. At St Nicholas in
    Nice the interesting part is the **iconostasis**, whose icons invoke the patron
    saints matching the Romanov family's baptismal names. Walking order buries it.

    **So: select by story, then order by walk.** One grounded call, not one per part.
    Returns the part names ordered best-story-first; parts the model does not rank
    keep their class order at the end (D577 — unranked is not rejected).
    """
    if not parts:
        return []
    listing = "\n".join(f"- {p}" for p in parts)
    where = f' in {location}' if location else ''
    prompt = (
        f'For "{venue_name}"{where}, which of these parts has the most remarkable, '
        f'specific history attached to it — real people, events, donors, makers, '
        f'disputes, or things found nowhere else?\n\n{listing}\n\n'
        'Rank them most interesting first. Judge by what actually happened AT that '
        'part of THIS building, not by how important the part is in general. '
        'Answer as a JSON array of the names, best first. Cite your sources.'
    )
    try:
        text, _sources = ask_grounded(prompt)
    except Exception:
        return list(parts)
    ranked = _coerce_list(text)
    known = {p.lower(): p for p in parts}
    out, seen = [], set()
    for r in ranked:
        canon = known.get(r.lower())
        if canon and canon.lower() not in seen:
            seen.add(canon.lower())
            out.append(canon)
    out += [p for p in parts if p.lower() not in seen]
    return out


# ── Michael's causal chain (2026-09-18) — STORY FIRST, PARTS SECOND ─────────
# *"if you fix the selection for this particular cathedral -- it is useless… We need
# to fix it so there is a path to the items humans consider interesting. Maybe an
# algorithm such as --> Building tour --> What was the reason/cause for this building
# to exist --> who created it --> Who paid for it -- who visited it, etc."*
#
# This replaces ranking parts by "which is most interesting", which was one opaque
# judgement with no reasoning path. His ordering is a CAUSAL chain, and it is what
# actually produces people:
#
#   why does it exist   -> the event or person that caused it (a Tsarevich's death;
#                          an airport expansion that swallowed a neighbourhood)
#   who created it      -> architect, builder, artists, by name
#   who paid for it     -> donors and patrons, and what they wanted in return
#   who came / happened -> visitors, protests, disasters, arguments
#
# Each link is a separate grounded question, so the chain is INSPECTABLE — you can
# see which link produced a fact and which link came back empty. Parts are then
# matched to the stories, not the other way round.

STORY_CHAIN = (
    ('cause',    'What event, person or decision caused "{venue}"{where} to be built at all? '
                 'Name the event and the people, with dates. What existed on the site before, '
                 'and what happened to it?'),
    ('creators', 'Who created "{venue}"{where} — the architect, the builder, the artists and '
                 'craftsmen — by name? What else are they known for, and what did they do '
                 'differently here?'),
    ('patrons',  'Who paid for "{venue}"{where}? Name the donors, patrons or public bodies, '
                 'what it cost, and what they wanted in return or wanted remembered.'),
    ('visitors', 'Who came to "{venue}"{where} and what happened here? Name visitors, '
                 'congregants, workers, protesters, victims — real people and real events, '
                 'with dates. What are people still arguing about?'),
    ('singular', 'What is "{venue}"{where} the largest, first, only, oldest or last of? '
                 'What does it hold or show that exists nowhere else?'),
)


def venue_story_chain(venue_name, location, ask_grounded, links=None):
    """Run the causal chain. Returns {link: {"text":…, "sources":[…]}}.

    Inspectable by design: every link is recorded separately, including the empty
    ones, so it is visible WHICH question produced the material and which failed.
    A failed link never aborts the chain (D577).
    """
    where = f' in {location}' if location else ''
    out = {}
    for key, template in (links or STORY_CHAIN):
        prompt = template.format(venue=venue_name, where=where) + \
                 '\nGive concrete, checkable facts with names and dates. Cite your sources. ' \
                 'If you do not know, say so rather than guessing.'
        try:
            text, sources = ask_grounded(prompt)
        except Exception as e:
            out[key] = {"text": "", "sources": [], "error": str(e)}
            continue
        out[key] = {"text": text or "", "sources": list(sources or [])}
    return out


def place_stories_in_building(venue_name, location, chain, parts, ask_grounded):
    """Match the stories the chain found to the parts of the building they happened in.

    This is the join that makes a story-first tour into a walkable one: the sit-in
    happened in the nave, the donor's name is on the window, the architect's signature
    is on the porch. A story with no home is still worth telling — it is attached to
    the most relevant part rather than dropped (D577).

    Returns [{"part":…, "why":…}] ordered best-story-first.
    """
    material = "\n\n".join(f"[{k}] {v.get('text','')[:1200]}"
                           for k, v in (chain or {}).items() if v.get('text'))
    if not material or not parts:
        return []
    listing = "\n".join(f"- {p}" for p in parts)
    where = f' in {location}' if location else ''
    prompt = (
        f'Here is what is known about "{venue_name}"{where}:\n\n{material}\n\n'
        f'These are the parts of the building a visitor can stand in:\n{listing}\n\n'
        'For each story above, say WHICH PART of the building it belongs to — where the '
        'visitor should be standing to hear it. Then list the parts that carry the best '
        'stories, best first.\n'
        'Answer as a JSON array of objects: [{"part": "...", "why": "one line naming the '
        'people or event"}]. Use only parts from the list. Omit parts with no story.'
    )
    try:
        text, _ = ask_grounded(prompt)
    except Exception:
        return []
    m = re.search(r'\[.*\]', str(text or ''), re.S)
    if not m:
        return []
    try:
        rows = json.loads(m.group(0))
    except Exception:
        return []
    known = {p.lower(): p for p in parts}
    out, seen = [], set()
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        canon = known.get(str(r.get('part', '')).strip().lower())
        if canon and canon.lower() not in seen:
            seen.add(canon.lower())
            out.append({"part": canon, "why": str(r.get('why', ''))[:200]})
    return out


# ── The handoff: chain material -> per-stop lore ────────────────────────────
# The chain was computing ~25k characters of sourced story material, using it to
# order the stops, and then discarding it: `poi_list = [_new_poi(_n) for _n in
# _vp_stops]` kept only the NAMES. The writer then re-researched each stop from its
# name alone, which is why "Control Tower" came back as 2,384 acres and six runways
# while the chain had Wood Island Park and the Neptune Road displacements.
#
# `poi['_lore']` is the writer's own input channel (consumed by
# `stop_knowledge_fallback.story_prompt_block`, which states the facts as a
# REQUIREMENT rather than offering them as context — D548). Pre-seeding it also
# suppresses the generic per-stop fetch, which skips any stop that already has lore.

_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"“])')
_FACTY = re.compile(r'\b(1[5-9]\d\d|20\d\d)\b|\b[A-Z][a-z]+\s+[A-Z][a-z]+\b')


def chain_to_facts(chain, per_link=6):
    """Turn the causal chain's prose into fact lines the writer will be given.

    Keeps only sentences that carry a date or a proper name — the ones that can
    actually anchor a story. A link that returned sources marks its facts `high`.
    """
    out = []
    for link, payload in (chain or {}).items():
        text = (payload or {}).get('text') or ''
        has_src = bool((payload or {}).get('sources'))
        kept = 0
        for raw in _SENT_SPLIT.split(re.sub(r'[*#`]+', '', text)):
            s = ' '.join(raw.split()).strip(' -–—')
            if not (40 <= len(s) <= 400) or not _FACTY.search(s):
                continue
            out.append({'fact': s, 'confidence': 'high' if has_src else 'low',
                        'link': link})
            kept += 1
            if kept >= per_link:
                break
    return out


def distribute_lore(stops, placed, chain, per_stop=6):
    """Give every stop its own slice of the chain, so stops do not repeat each other.

    Each stop gets: the one-line reason it was chosen (its `placed` entry, stated
    first and high-confidence), then a non-overlapping share of the venue-level
    facts dealt round-robin.
    """
    facts = chain_to_facts(chain)
    why_by_part = {r['part']: r.get('why', '') for r in (placed or []) if r.get('part')}
    lore = {s: [] for s in stops}
    for s in stops:
        why = why_by_part.get(s)
        if why:
            lore[s].append({'fact': why, 'confidence': 'high', 'link': 'placed'})
    for i, f in enumerate(facts):
        if not stops:
            break
        s = stops[i % len(stops)]
        if len(lore[s]) < per_stop:
            lore[s].append(f)
    return lore
