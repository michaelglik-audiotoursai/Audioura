#!/usr/bin/env python3
"""stop_dedup_collision_guard.py — LOCAL-801.

Two defect families found by the Oct-28 P1 blind scoring on the DEFAULT
(gpt-4.1) narration arm — the opposite arm from the Oct-9 LOCAL-654 work, which
fixed the same *shapes* on the cheap (gpt-4.1-mini) arm:

  (1) DUPLICATE STOPS / STOP OVERCOUNT.  A "next-stop preview" written by the
      model (or spliced by an assembly pass) landed in the PREVIOUS stop's
      tail, and the real stop was then re-emitted, so a stop appeared twice and
      the tour reported one more stop than requested:

        w1 Freedom Trail (5 requested): Park Street Church delivered twice,
           closing line said "That's 6 stops in all."
        w3 Salem (4 requested): The Witch House twice, "5 stops in all."
        w4 Old Saigon (5 requested): Independence Palace body spliced into
           Stop 1's Directions AND emitted as Stop 2.

      The exact on-the-wire shape (verbatim, w1):

        Directions: … When you reach … Park Street Church … Continue to Park Street Church
        Address: 1 Park St, Boston, MA 02108          ┐  headerless duplicate
        Coordinates: 42.3577, -71.0621                │  of the NEXT stop —
        …Orientation: … story continues to unfold.    ┘  no "Stop N:" header
        Stop 3: Boston Common — it is roughly 1.1 km … away.   ← stray preview header
        Continue to Park Street Church.
        Stop 2: Park Street Church                     ← the real stop
        Address: 1 Park St, Boston, MA 02108
        …

      Three artifacts repaired here, deterministically and offline:
        • a STRAY PREVIEW HEADER — a "Stop N: <title> — it is roughly … away."
          line whose value carries a distance/hand-off tail (a preview, not a
          stop). Dropped.
        • a HEADERLESS SPLICED BODY — a run of house field lines
          (Address/Coordinates/Type/Specialty/Specific Examples/Orientation)
          that sits after a Directions line with NO "Stop N:" header of its own
          and duplicates a FOLLOWING real stop. Dropped, keeping the Directions
          hand-off sentence.
        • TRUE DUPLICATE STOPS — two real "Stop N:" blocks with the same
          normalised title, or coordinates within 60 m. The later copy is
          dropped.
      Stops are then renumbered 1..k and the delivered count can only ever be
      ≤ requested (never more).

  (2) MID-CLAUSE TEXT COLLISION.  d1 (JP coffee), Stop 1 opened:

        "This route takes you from J.P. These stops reflect … essence of
         Jamaica Plain. Licks in June 2021 demanding significant back rent at
         J.P. Your first stop is J.P. Licks.P. Licks.P. Licks."

      A sentence pass that split on a naive "period + space" boundary cut
      "J.P. Licks" at the abbreviation dot, dropped/re-ordered fragments, and
      re-joined mid-clause — leaving a dangling fragment ("…from J.P.") and a
      repeated, welded phrase ("Licks.P. Licks.P. Licks."). The garble guard
      detects such a sentence (a dangling abbreviation hand-off, a repeated
      welded token, or two finite clauses glued with no punctuation) and
      repairs it — removing the welded repetition and the dangling fragment —
      or drops the sentence when it cannot be made whole. Every repair logs
      ``[LOCAL-801] collision repaired <stop>``.

Pure, deterministic, offline, idempotent. Museum/building/venue tours keep the
same dedup (a duplicated painting stop is just as wrong) but the collision
guard is conservative everywhere.
"""
import re
from math import radians, sin, cos, asin, sqrt
from typing import List, Optional, Tuple, Dict

_STOP_HEADER = re.compile(r'(?m)^Stop (\d+):[ \t]*(.+?)[ \t]*$')
_SOURCES_LINE = re.compile(r'(?ms)^\s*Sources:\s.*\Z')
_COORDS_LINE = re.compile(r'(?im)^Coordinates:\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$')

# House field labels that make up a stop BODY. A run of these with no "Stop N:"
# header is an orphan (headerless) body.
_FIELD_LABEL = re.compile(
    r'(?im)^[ \t]*(?:Address|Coordinates|Type/Specialty|Specific Examples|'
    r'Orientation|Directions|Operational Details|Museum Information):')

# A "Stop N:" header whose VALUE ends with a hand-off / distance preview tail —
# "Stop 3: Boston Common — it is roughly 1.1 km … away." — is a preview the
# model mis-rendered as a header, never a real stop.
_PREVIEW_HEADER_TAIL = re.compile(
    r'(?i)(?:(?:\u2014|--|-)\s*it is (?:roughly|about|approximately|around)\b'
    r'|\bit is (?:roughly|about|approximately|around)\b.*\b(?:away|walk)\b)')

# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Geometry (mirrors walking_directions_guard / stop_route_sequencer)
# ─────────────────────────────────────────────────────────────────────────────

def _haversine_m(a, b) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6371000.0 * asin(sqrt(h))


def _norm_title(raw: str) -> str:
    t = (raw or "").strip()
    # Drop a distance/hand-off preview tail so the comparison keys on the title.
    t = re.split(r'\s*(?:\u2014|--| - )\s*it is\b', t, maxsplit=1, flags=re.I)[0]
    t = re.sub(r',\s*\d{3,4}\s*$', '', t)           # trailing year
    t = re.sub(r'\s+by\s+.+$', '', t, flags=re.I)   # " by Artist"
    t = re.sub(r'[\s.,:;"\'\u2019()]+$', '', t)
    t = re.sub(r'\s+', ' ', t).strip().lower()
    return t


def _titles_equivalent(a: str, b: str) -> bool:
    """True when two normalised titles name the SAME place for the coord-assisted
    dedup: exact equality, or one is wholly contained in the other as a whole-
    word prefix/suffix ("regina" ⊂ "pizzeria regina", "independence palace" ⊂
    "the independence palace"). Deliberately conservative: it must NOT treat two
    different places that merely share a theme word as equivalent — "salem witch
    museum" and "salem witch trials memorial" share tokens but neither contains
    the other, so they stay distinct even when their approximate coordinates sit
    within 60 m."""
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    # whole-word containment
    return bool(re.search(r'(?:^|\s)' + re.escape(shorter) + r'(?:\s|$)', longer))


def _coord_of(segment: str) -> Optional[Tuple[float, float]]:
    m = _COORDS_LINE.search(segment)
    if not m:
        return None
    try:
        lat, lng = float(m.group(1)), float(m.group(2))
        if lat == 0.0 and lng == 0.0:
            return None
        return (lat, lng)
    except ValueError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Segment model
# ─────────────────────────────────────────────────────────────────────────────

def _body_end(text: str) -> int:
    src = _SOURCES_LINE.search(text)
    return src.start() if src else len(text)


def _segments(text: str) -> List[Dict]:
    """Return a list of real "Stop N:" segments: {num,title,start,end,coord,seg}.
    ``end`` runs to the next header or to the Sources/conclusion region.
    """
    end_body = _body_end(text)
    headers = [h for h in _STOP_HEADER.finditer(text) if h.start() < end_body]
    out = []
    for i, h in enumerate(headers):
        start = h.start()
        end = headers[i + 1].start() if i + 1 < len(headers) else end_body
        seg = text[start:end]
        out.append({
            'num': int(h.group(1)),
            'title_raw': h.group(2).strip(),
            'title': _norm_title(h.group(2)),
            'start': start,
            'end': end,
            'coord': _coord_of(seg),
            'seg': seg,
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# (1) De-splice: remove a headerless body glued after a Directions line
# ─────────────────────────────────────────────────────────────────────────────

# The "<cue> <Name>" hand-off a Directions line ends with. The <Name> is the
# stop the orphan body belongs to (w1: "Continue to Park Street Church"; Rijks:
# "Proceed to A Militiaman Holding a Berkemeyer, Known as the 'Merry Drinker'
# (Een schutter …)"). Used to re-title an orphan body that is a UNIQUE stop whose
# header was lost, so it is promoted (not dropped). Cue list mirrors the
# deterministic museum/outdoor hand-offs.
_HANDOFF_NAME = re.compile(
    r'(?i)(?:Continue through|Continue to|Proceed to|Next:|'
    r'Head towards|Your final stop(?:\s+in\s+[^:]+)?:)\s*(.+?)\s*$')


def _handoff_title(directions_line: str) -> str:
    """Return the next-stop NAME a Directions hand-off line announces, or ''.

    "Directions: Proceed to A Militiaman … ('De vrolijke drinker')." →
    "A Militiaman … ('De vrolijke drinker')". The trailing sentence period and a
    "next is "/"next:" lead-in are trimmed."""
    m = _HANDOFF_NAME.search(directions_line or "")
    if not m:
        return ""
    name = m.group(1).strip()
    name = re.sub(r'(?i)^next\s+is\s+', '', name).strip()
    name = name.rstrip('.').strip()
    # Strip surrounding single quotes a hand-off sometimes wraps the name in.
    if len(name) >= 2 and name[0] in "'\u2018\u2019" and name[-1] in "'\u2018\u2019":
        name = name[1:-1].strip()
    return name


def _desplice_segment(seg: str) -> Tuple[str, str, bool]:
    """Within a single stop segment, split off a headerless body that was spliced
    after the Directions line.

    The segment legitimately ends with ONE ``Directions:`` hand-off line and no
    house field labels after it. A SPLICE re-opens house field labels
    (Address/Coordinates/Type/Specialty/Specific Examples/Orientation) AFTER a
    Directions line with no "Stop N:" header of its own — that is a copy of the
    next stop glued into this one's tail (w1: Park Street Church's body after
    Stop 1's Directions; w4: Independence Palace's body after Stop 1's; Rijks
    866: the Merry Drinker's whole narrated body after Stop 3's Directions). Find
    the FIRST Directions line that is followed by such a field block and separate
    the kept hand-off from the orphan tail.

    Returns ``(kept_seg, orphan_tail, changed)``. The CALLER decides the orphan's
    fate: drop it when it only duplicates a FOLLOWING real stop (the w1/w4
    symptom), or PROMOTE it to its own "Stop N:" block when it is a unique
    narrated stop whose header a late pass lost (Rijks 866) — deleting a real,
    paid, narrated stop is never acceptable.
    """
    for d in re.finditer(r'(?im)^[ \t]*Directions:[^\n]*$', seg):
        tail = seg[d.end():]
        if _FIELD_LABEL.search(tail):
            kept = seg[:d.end()].rstrip() + "\n\n"
            return kept, tail, True
    return seg, "", False


# ─────────────────────────────────────────────────────────────────────────────
# (1) Drop stray preview headers + de-splice + dedupe real stops + renumber
# ─────────────────────────────────────────────────────────────────────────────

def _orphan_body_text(orphan_tail: str) -> str:
    """Comparable text of an orphan/stop body: the field-label PREFIX is dropped
    but the field VALUE is kept (museum narration lives inside the Orientation
    value), and bare narration paragraphs are kept, normalised for a duplicate
    comparison. Address/Coordinates/Directions carry no narration and are dropped
    entirely so an address string cannot dominate the overlap."""
    kept = []
    for ln in (orphan_tail or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if re.match(r'(?i)^(?:Address|Coordinates|Directions):', s):
            continue
        # Keep the value of a narration-bearing field label; keep bare prose.
        m = re.match(r'(?i)^(?:Orientation|Type/Specialty|Specific Examples|'
                     r'Operational Details|Museum Information):\s*(.*)$', s)
        kept.append(m.group(1) if m else s)
    return re.sub(r'\s+', ' ', " ".join(kept)).strip().lower()


def _orphan_duplicates_following(orphan_tail: str,
                                 handoff_title: str,
                                 following_segs: List[Dict]) -> bool:
    """True when the orphan body spliced after a Directions line merely DUPLICATES
    a FOLLOWING real stop — the w1/w4 symptom, where the next stop is also emitted
    with its own "Stop N:" header, so dropping the orphan loses nothing.

    False when the orphan is a UNIQUE narrated stop whose header a late pass lost
    (Rijks 866: the Merry Drinker body, with no matching "Stop N:" elsewhere) — the
    caller must PROMOTE it, never drop it.

    A match is by the hand-off title naming a following real stop, or by heavy
    narration overlap with a following segment's body (title lost on both sides)."""
    _ht = _norm_title(handoff_title)
    for fs in following_segs:
        if _ht and (_ht == fs['title'] or _titles_equivalent(_ht, fs['title'])):
            return True
    _ob = _orphan_body_text(orphan_tail)
    if len(_ob) >= 40:
        _ob_tokens = set(_ob.split())
        for fs in following_segs:
            _fb = _orphan_body_text(fs['seg'])
            if not _fb:
                continue
            if _ob in _fb or _fb in _ob:
                return True
            # Heavy token overlap (same narration re-emitted with minor edits):
            # Jaccard over the shorter side ≥ 0.6 means the orphan is that stop.
            _fb_tokens = set(_fb.split())
            _inter = len(_ob_tokens & _fb_tokens)
            _denom = max(1, min(len(_ob_tokens), len(_fb_tokens)))
            if _inter / _denom >= 0.6:
                return True
    return False


def _promote_orphan_to_stop(orphan_tail: str, handoff_title: str) -> str:
    """Build a self-contained "Stop:" block from an orphan body whose header was
    lost, titled by the Directions hand-off that announced it. The number is a
    placeholder (0); the caller renumbers every survivor 1..k afterwards."""
    body = orphan_tail.lstrip("\n")
    title = (handoff_title or "").strip() or "This stop"
    return f"Stop 0: {title}\n\n" + body


def _orphan_has_narration_body(orphan_tail: str) -> bool:
    """True when the orphan carries a REAL narration body — a bare prose
    paragraph (not a field label) of some substance — so it is a lost-header
    stop worth PROMOTING (Rijks 866: the Merry Drinker's two-sentence body).

    False for a glued FIELD-PREVIEW fragment that has no prose of its own: the
    tour-716 case where only "Type/Specialty: …" / "Specific Examples: … — it is
    about a minute's walk away." follow a Directions line. Those carry no
    narration, only a distance preview of the NEXT stop, and must be dropped.
    """
    for ln in (orphan_tail or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if _FIELD_LABEL.match(s):
            continue          # a house field label line — structure, not prose
        # A bare prose paragraph. Require a couple of real sentences' worth of
        # text so a one-line fragment / distance preview never reads as a body.
        if len(s) >= 80 and _PREVIEW_HEADER_TAIL.search(s) is None:
            return True
    return False


def dedupe_and_fix_stop_count(text: str,
                              requested_stops: Optional[int] = None,
                              dedupe_real_stops: bool = True
                              ) -> Tuple[str, Dict]:
    """Remove duplicate/preview/spliced stop artifacts and renumber.

    Steps (all deterministic, offline, idempotent):
      1. Drop STRAY PREVIEW HEADERS — "Stop N: <title> — it is roughly … away."
      2. DE-SPLICE each surviving segment — separate a headerless field block
         glued after its Directions line. The orphan is DROPPED only when it
         duplicates a following real stop (w1/w4); when it is a UNIQUE narrated
         stop whose header was lost (Rijks 866), it is PROMOTED to its own
         "Stop N:" block so the real, paid stop is never silently deleted.
      3. DEDUPE real stops by normalised title OR (contained title + coordinates
         within 60 m) — keep the first occurrence, drop later copies. Skipped
         when ``dedupe_real_stops`` is False (used by the universal
         ``normalise_stop_headers`` choke point, which must only strip the
         artifacts — preview headers and spliced bodies — and must NOT drop a
         legitimately repeated real title such as a museum's two views of the
         same wall; same-title real dedup stays in the delivery path, where
         stop_title_dedup/LOCAL-722 already owns it).
      4. RENUMBER the survivors 1..k and (when ``requested_stops`` is given)
         never keep more than requested.

    Returns ``(new_text, report)`` with ``report`` =
      {dropped_preview, despliced, dropped_duplicate, renumbered, count}.
    """
    if not text:
        return text or "", {'dropped_preview': 0, 'despliced': 0,
                            'dropped_duplicate': 0, 'renumbered': False, 'count': 0}

    segs = _segments(text)
    if not segs:
        return text, {'dropped_preview': 0, 'despliced': 0,
                      'dropped_duplicate': 0, 'renumbered': False, 'count': 0}

    head = text[:segs[0]['start']]
    tail = text[_body_end(text):]

    dropped_preview = 0
    despliced = 0
    dropped_duplicate = 0

    kept: List[Dict] = []
    seen_titles: Dict[str, Optional[Tuple[float, float]]] = {}
    promoted = 0

    for _si, s in enumerate(segs):
        # (1) Stray preview header? Its value carries a distance/hand-off tail
        #     and it is NOT a self-contained stop (no real body of its own, or a
        #     real stop of the same title follows). Drop it.
        if _PREVIEW_HEADER_TAIL.search(s['title_raw']):
            dropped_preview += 1
            print(f"  [LOCAL-801] dropped stray preview header: "
                  f"{s['title_raw'][:60]!r}")
            continue

        # (2) De-splice a headerless body glued after Directions. The orphan is
        #     DROPPED only when it duplicates a following real stop (w1/w4); a
        #     UNIQUE narrated stop whose header was lost is PROMOTED to its own
        #     "Stop N:" block (Rijks 866) — a real, paid stop is never deleted.
        _promoted_seg = None
        while True:
            new_seg, orphan_tail, changed = _desplice_segment(s['seg'])
            if not changed:
                break
            despliced += 1
            s = dict(s, seg=new_seg)
            # The Directions hand-off that the orphan was glued after names the
            # orphan stop; recover it from the kept segment's LAST Directions line.
            _dirs = re.findall(r'(?im)^[ \t]*Directions:[^\n]*$', new_seg)
            _ht = _handoff_title(_dirs[-1]) if _dirs else ""
            if _orphan_duplicates_following(orphan_tail, _ht, segs[_si + 1:]):
                print(f"  [LOCAL-801] de-spliced duplicate body after Directions "
                      f"in stop {s['title_raw'][:40]!r}")
            elif _orphan_has_narration_body(orphan_tail):
                _promoted_seg = _promote_orphan_to_stop(orphan_tail, _ht)
                promoted += 1
                print(f"  [LOCAL-801] promoted lost-header stop from spliced body "
                      f"after Directions in {s['title_raw'][:30]!r}: "
                      f"{(_ht or 'This stop')[:40]!r}")
                break  # one orphan promoted per splice; it becomes its own seg

        # (3) Duplicate of an already-kept stop?
        #
        #     The PRIMARY key is the normalised title: two "Stop N:" blocks with
        #     the same title are the same stop. Coordinates are only a SECONDARY,
        #     corroborating signal — and they are used ONLY together with a title
        #     match (containment), never alone. LLM-approximated coordinates in a
        #     dense district cluster (Old Saigon w4: five distinct places all
        #     within ~50 m of each other; Salem w3: the Witch Museum is ~57 m
        #     from the Trials Memorial) would otherwise collapse genuinely
        #     different stops. "normalized title + location (<=60 m)" is an AND.
        title = s['title']
        coord = s['coord']
        is_dup = False
        if dedupe_real_stops:
            if title and title in seen_titles:
                is_dup = True
            else:
                for kept_title, kc in seen_titles.items():
                    if _titles_equivalent(title, kept_title) and coord is not None \
                            and kc is not None and _haversine_m(coord, kc) <= 60.0:
                        is_dup = True
                        break
        if is_dup:
            dropped_duplicate += 1
            print(f"  [LOCAL-801] dropped duplicate stop: {s['title_raw'][:40]!r}")
            continue

        kept.append(s)
        if title:
            seen_titles[title] = coord

        # A promoted orphan becomes its own segment, inserted right after its
        # parent so order and numbering stay correct.
        if _promoted_seg is not None:
            _pseg = _segments(_promoted_seg)
            if _pseg:
                _ps = _pseg[0]
                if not (_ps['title'] and _ps['title'] in seen_titles):
                    kept.append(_ps)
                    if _ps['title']:
                        seen_titles[_ps['title']] = _ps['coord']

    # (4) Cap to requested (never more) — keep the FIRST ``requested`` stops.
    trimmed = 0
    if requested_stops is not None and requested_stops > 0 and len(kept) > requested_stops:
        for extra in kept[requested_stops:]:
            print(f"  [LOCAL-801] trimmed over-count stop beyond requested "
                  f"{requested_stops}: {extra['title_raw'][:40]!r}")
        trimmed = len(kept) - requested_stops
        kept = kept[:requested_stops]

    # No artifact found and no trim needed → return the input byte-for-byte so
    # this stays a strict no-op on clean text (required: count_delivered_stops
    # and the service's _header_formatting_defect both key on
    # normalise_stop_headers(text) == text for a clean tour).
    if not (dropped_preview or despliced or dropped_duplicate or trimmed or promoted):
        return text, {
            'dropped_preview': 0, 'despliced': 0, 'dropped_duplicate': 0,
            'promoted': 0, 'renumbered': False, 'count': len(kept),
        }

    # Rebuild with renumbered headers (only when something was removed).
    renumbered = False
    pieces = [head.rstrip("\n")]
    for i, s in enumerate(kept, start=1):
        seg = s['seg']
        # Replace the leading "Stop N:" header number with the new index.
        new_seg = _STOP_HEADER.sub(
            lambda m, _i=i: f"Stop {_i}: {m.group(2).strip()}", seg, count=1)
        if new_seg != seg:
            renumbered = True
        pieces.append(new_seg.rstrip("\n"))
    body = "\n\n".join(p for p in pieces if p != "")
    out = body
    if tail.strip():
        out = body.rstrip("\n") + "\n\n" + tail.lstrip("\n")
    out = re.sub(r'\n{3,}', '\n\n', out).rstrip() + "\n"

    return out, {
        'dropped_preview': dropped_preview,
        'despliced': despliced,
        'dropped_duplicate': dropped_duplicate,
        'promoted': promoted,
        'renumbered': renumbered,
        'count': len(kept),
    }


# ─────────────────────────────────────────────────────────────────────────────
# (2) Garble guard — mid-clause text collisions
# ─────────────────────────────────────────────────────────────────────────────

# A welded, repeated abbreviation-fragment run such as "Licks.P. Licks.P. Licks"
# — the dead giveaway of a sentence pass that cut on "J.P." and re-welded. Match
# a word immediately followed by ".<Cap>." repeated.
_WELD_REPEAT = re.compile(
    r'\b(\w+)\.(?:[A-Z]\.)(?:\s+\1\.(?:[A-Z]\.)?)+')

# A dangling hand-off fragment: a sentence that ENDS on a bare abbreviation that
# the splitter should have kept attached ("This route takes you from J.P.").

try:
    from sentence_split import split_sentences as _split_sentences
except Exception:  # pragma: no cover
    def _split_sentences(t):
        return [s.strip() for s in re.split(r'(?<=[.!?])\s+', t or "") if s.strip()]


# A COLLISION GLUE: a dotted abbreviation ("J.P.") immediately followed by a
# word that can only open a NEW sentence (a determiner/pronoun/connective), not
# the abbreviation's proper-noun completion. In correct prose "J.P." is followed
# by its completion ("J.P. Licks", "against J.P. Licks, demanding …") or by
# lowercase — NEVER by "These"/"Your"/"This". So "… from J.P. These stops …" and
# "… at J.P. Your first stop …" are two unrelated clauses welded at the dot.
_SENTENCE_STARTER = (
    r'These|This|That|Those|Your|Their|Our|His|Her|Its|It|He|She|They|We|You|'
    r'The|A|An|In|On|At|When|While|Here|There|Today|Later|Long|Since')
_COLLISION_GLUE = re.compile(
    r'(?:[A-Z]\.){2,}(?=\s+(?:' + _SENTENCE_STARTER + r')\b)')

# A dangling fragment: a clause that ENDS on a bare preposition + dotted
# abbreviation ("This route takes you from J.P.", "… back rent at J.P.") with no
# proper-noun completion — the debris left on the LEFT of a collision glue.
_DANGLING_FRAGMENT = re.compile(
    r'(?i)\b(?:from|at|to|by|near|against|through|of|with)\s+(?:[A-Za-z]\.){1,3}\s*$')

# An orphan opener: a fragment that BEGINS with a capitalised noun directly
# followed by a bare participle/number with no subject ("Licks in June 2021
# demanding …") — the debris left when a proper noun was split and its tail ran
# into unrelated text. Only used together with a dangling-abbreviation end.
_ORPHAN_OPENER = re.compile(r'^[A-Z][a-z]+\s+(?:in|on|at)\s+\w')


def _repair_welded_repeat(text: str) -> Tuple[str, int]:
    """Collapse a welded repeat ("Licks.P. Licks.P. Licks" → "Licks") and clean
    the leftover dangling abbreviation hand-off."""
    n = 0

    def _sub(m):
        nonlocal n
        n += 1
        return m.group(1)  # keep a single clean token

    out = _WELD_REPEAT.sub(_sub, text)
    return out, n


def repair_collisions(text: str) -> Tuple[str, Dict]:
    """Detect and repair mid-clause text collisions in each stop's narration.

    For each stop body, find a welded/repeated abbreviation run (the d1 shape)
    and collapse it; remove the orphaned dangling-abbreviation hand-off fragment
    it leaves. When a sentence is a collision that cannot be made whole, it is
    dropped. Every change logs ``[LOCAL-801] collision repaired <stop>``.

    Returns ``(new_text, report)`` with ``report`` = {repaired, dropped,
    stops: [titles]}.
    """
    if not text:
        return text or "", {'repaired': 0, 'dropped': 0, 'stops': []}

    segs = _segments(text)
    if not segs:
        # No stop structure — still try a whole-text welded-repeat collapse.
        fixed, n = _repair_welded_repeat(text)
        return fixed, {'repaired': n, 'dropped': 0, 'stops': []}

    repaired = 0
    dropped = 0
    stops_touched: List[str] = []

    head = text[:segs[0]['start']]
    tail = text[_body_end(text):]
    pieces = [head.rstrip("\n")]

    for s in segs:
        seg = s['seg']
        before = seg

        # (a) Collapse welded repeats anywhere in the segment first
        #     ("Licks.P. Licks.P. Licks" → "Licks").
        seg, n_weld = _repair_welded_repeat(seg)

        # (b) Drop irreparable mid-clause debris fragments, paragraph by
        #     paragraph. A paragraph that opens with a house field label keeps
        #     the label; the value/narration after it is cleaned. The header and
        #     the structural hand-off lines (Address/Coordinates/Directions) are
        #     never touched. We rebuild a paragraph ONLY when a fragment was
        #     actually dropped, so clean prose is preserved byte-for-byte.
        seg_dropped = 0
        paras = re.split(r'(\n{2,})', seg)  # keep separators to preserve spacing
        rebuilt = []
        for part in paras:
            if not part or part.startswith("\n"):
                rebuilt.append(part)
                continue
            stripped = part.strip()
            if stripped.startswith("Stop "):
                rebuilt.append(part)
                continue
            label_m = re.match(r'(?is)^([ \t]*(?:Type/Specialty|Specific Examples|'
                               r'Orientation|Operational Details|'
                               r'Museum Information):[ \t]*)(.*)$', part)
            if label_m:
                label, rest = label_m.group(1), label_m.group(2)
                rest2, dn = _clean_sentences(rest)
                seg_dropped += dn
                rebuilt.append(label + rest2 if dn else part)
                continue
            # A structural field line (Address/Coordinates/Directions) or a bare
            # narration paragraph.
            if re.match(r'(?i)^[ \t]*(?:Address|Coordinates|Directions):', part):
                rebuilt.append(part)
                continue
            rest2, dn = _clean_sentences(part)
            seg_dropped += dn
            rebuilt.append(rest2 if dn else part)
        if seg_dropped:
            seg = "".join(rebuilt)

        if n_weld or seg_dropped:
            repaired += 1
            dropped += seg_dropped
            stops_touched.append(s['title_raw'])
            print(f"  [LOCAL-801] collision repaired {s['title_raw'][:50]!r}")
        pieces.append(seg.rstrip("\n"))

    # Strict no-op on clean text: when no collision was repaired, return the
    # input byte-for-byte (normalise_stop_headers idempotency contract).
    if repaired == 0:
        return text, {'repaired': 0, 'dropped': 0, 'stops': []}

    body = "\n\n".join(p for p in pieces if p != "")
    out = body
    if tail.strip():
        out = body.rstrip("\n") + "\n\n" + tail.lstrip("\n")
    out = re.sub(r'\n{3,}', '\n\n', out).rstrip() + "\n"
    return out, {'repaired': repaired, 'dropped': dropped, 'stops': stops_touched}


def _clean_sentences(prose: str) -> Tuple[str, int]:
    """Drop the irreparable mid-clause debris fragments from a narration body.

    Split with the abbreviation-aware splitter (so "J.P. Licks" stays whole),
    then split each sentence further at any COLLISION GLUE — a dotted
    abbreviation welded directly to a sentence-starter ("J.P. These", "J.P.
    Your") — which only ever appears when two unrelated clauses were fused at the
    abbreviation dot. Of the resulting pieces, DROP a piece that is a dangling
    abbreviation fragment ("… from J.P.") or an orphan opener that also dangles
    ("Licks in June 2021 … at J.P."); KEEP whole, self-standing clauses. A clean
    body has no glue and is returned unchanged. Returns (clean_prose, dropped)."""
    if not prose.strip():
        return prose, 0
    dropped = 0
    out_pieces: List[str] = []
    for sent in _split_sentences(prose):
        st = sent.strip()
        if not st:
            continue
        # Split this sentence at each collision glue.
        parts = []
        last = 0
        for m in _COLLISION_GLUE.finditer(st):
            parts.append(st[last:m.end()])
            last = m.end()
        parts.append(st[last:])
        if len(parts) == 1:
            out_pieces.append(st)        # no glue — keep verbatim
            continue
        for p in parts:
            pt = p.strip()
            if not pt:
                continue
            if _DANGLING_FRAGMENT.search(pt) or _ORPHAN_OPENER.match(pt):
                dropped += 1
                continue
            out_pieces.append(pt)
    if not dropped:
        return prose, 0
    return " ".join(out_pieces), dropped


# ─────────────────────────────────────────────────────────────────────────────
# One-shot convenience: run both guards (dedup first, then collisions)
# ─────────────────────────────────────────────────────────────────────────────

def guard(text: str, requested_stops: Optional[int] = None) -> Tuple[str, Dict]:
    """Apply the dedup/count fix then the collision guard. Returns
    ``(new_text, {'dedup': {...}, 'collision': {...}})``."""
    t1, r1 = dedupe_and_fix_stop_count(text, requested_stops=requested_stops)
    t2, r2 = repair_collisions(t1)
    return t2, {'dedup': r1, 'collision': r2}


if __name__ == "__main__":  # pragma: no cover
    import sys
    with open(sys.argv[1], encoding="utf-8") as f:
        t = f.read()
    req = int(sys.argv[2]) if len(sys.argv) > 2 else None
    out, rep = guard(t, requested_stops=req)
    print("report:", rep)
    print("=" * 60)
    print(out)
