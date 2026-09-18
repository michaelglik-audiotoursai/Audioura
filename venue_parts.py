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
