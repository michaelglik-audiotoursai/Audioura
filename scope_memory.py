"""[D557] Scope rejections must stick — a stop's location is a fact, not an opinion.

D556 found the defect: PHASE 5.6 removed Villa Leopolda from a Cimiez tour at
`conf=high` because it is in Villefranche-sur-Mer, and the very next run for the
same district kept it. The scope check is a per-stop LLM judgement with no memory
between runs, so a correctly-deleted stop can walk straight back in.

Which town a building stands in does not change between two API calls. This module
gives that judgement a memory, in the same shape as `known_closed_venues.json` —
the one piece of the closure machinery that proved reliable, precisely because it
is a deterministic lookup rather than a model answering the same question twice.

Two halves:

  `known_out_of_scope(name, scope)` — consulted BEFORE the LLM call. A hit drops
  the stop with no token spend and no chance of a different answer.

  `record_out_of_scope(...)` — called when the LLM rejects at high confidence.
  It can only ever record a removal the machinery had already decided to make, so
  it cannot make the guard more destructive than it is today; it only makes it
  consistent. Entries are keyed on the (name, scope) PAIR, so a wrong entry is
  contained to the one request that produced it.

Durability is honest about its limits: the write lands in the repo checkout on a
host run, and in the container's own filesystem otherwise — which is lost at the
next rebuild but covers the case that actually bit us, two runs minutes apart
against one running container. Every write also prints `[SCOPE-MEMORY] NEW ENTRY`
with the exact JSON, so LEAD can commit it permanently.
"""

import json
import os
import re
import threading
import unicodedata
from datetime import datetime, timezone

_CORPUS_BASENAME = os.path.join('tests', 'known_out_of_scope.json')

_CACHE = None
_CACHE_PATH = None
_LOAD_LOCK = threading.Lock()


def _fold(s):
    """Accent-fold and punctuation-strip for matching (D243).

    Exact match on French titles silently reports absence — 'Musee' must find
    'Musée', and 'Villefranche-sur-Mer' must find 'Villefranche sur Mer'.
    """
    n = unicodedata.normalize('NFKD', (s or '').lower())
    n = ''.join(c for c in n if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r"[^\w\s]", ' ', n)).strip()


def _candidate_paths():
    here = os.path.dirname(os.path.abspath(__file__))
    return [os.path.join(here, _CORPUS_BASENAME), '/app/' + _CORPUS_BASENAME]


def _load():
    """Load the corpus once, remembering which path it came from so writes go back there.

    [D558] Publish the list only when it is fully built. The first version assigned
    `_CACHE = []` and *then* filled it, so a second thread arriving in between saw a
    non-None empty cache and reported "not on record". `_validate_stops_within_scope`
    checks stops on a ThreadPoolExecutor, so this was not theoretical: with Villa
    Leopolda and the Chapelle du Rosaire vetted in the same batch, one hit the corpus
    and the other fell through to the LLM. Caught by
    test_a_candidate_batch_can_be_rejected_entirely.
    """
    global _CACHE, _CACHE_PATH
    if _CACHE is not None:
        return _CACHE
    with _LOAD_LOCK:
        if _CACHE is not None:          # another thread finished while we waited
            return _CACHE
        loaded, path = [], None
        for cand in _candidate_paths():
            try:
                with open(cand, encoding='utf-8') as fh:
                    loaded = json.load(fh).get('venues', [])
                path = cand
                break
            except Exception:
                continue
        _CACHE_PATH = path
        _CACHE = loaded                 # single assignment, fully populated
    return _CACHE


def reset_cache():
    """Drop the in-process cache. Tests use this after writing a fixture."""
    global _CACHE, _CACHE_PATH
    _CACHE = None
    _CACHE_PATH = None


def _scopes_match(entry_scope, asked_scope):
    """Containment both ways, folded (D542).

    The caller passes the tour's scope string, which is derived from the user's
    request — 'Cimiez District, Nice' against a stored 'Cimiez'. Exact comparison
    is what made the closure lookup skip every entry inside a real tour while
    working perfectly when called directly.
    """
    e, a = _fold(entry_scope), _fold(asked_scope)
    if not e or not a:
        return False
    return e == a or e in a or a in e


def _names_match(entry, asked_name):
    """Exact fold-match, or containment when the shorter side is distinctive.

    The closure lookup accepts any substring, which would let a stop called
    'Villa' collide with 'Villa Leopolda'. Requiring the shorter string to be
    >= 6 folded characters keeps 'Chapelle du Rosaire' matching 'Chapelle du
    Rosaire (Matisse Chapel)' while refusing one-word collisions.
    """
    n = _fold(asked_name)
    if not n:
        return False
    for cand in [entry.get('name', '')] + list(entry.get('aliases', [])):
        f = _fold(cand)
        if not f:
            continue
        if f == n:
            return True
        if (f in n or n in f) and min(len(f), len(n)) >= 6:
            return True
    return False


def known_out_of_scope(name, scope):
    """Has this stop already been ruled outside this scope?

    Returns (True, reason) only for `expect: "outside"` entries. `verify` entries
    are suspicions on the record and must never remove a stop — the same split
    `known_closed_venues.json` uses.
    """
    for v in _load():
        if v.get('expect') != 'outside':
            continue
        if not _scopes_match(v.get('scope', ''), scope):
            continue
        if _names_match(v, name):
            return True, (f"recorded in known_out_of_scope.json: "
                          f"{v.get('ground_truth', '')[:150]}")
    return False, ''


def record_out_of_scope(name, scope, reason='', actual_location='', source='phase_5_6_high_conf'):
    """Persist one high-confidence rejection. Returns (written, entry).

    `written` is False when the pair is already on record — a repeat rejection is
    the corpus working, not new information.
    """
    if not name or not scope:
        return False, None
    already, _ = known_out_of_scope(name, scope)
    if already:
        return False, None

    entry = {
        'name': name,
        'aliases': [],
        'scope': scope,
        'expect': 'outside',
        'actual_location': actual_location,
        'ground_truth': reason or f"ruled outside '{scope}' by the PHASE 5.6 containment check",
        'source': source,
        'recorded': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    }

    # Always print it, whether or not the write lands. In the container the file
    # is baked into the image and any write dies at the next rebuild; this line is
    # what lets LEAD commit the entry for good.
    print(f"   [SCOPE-MEMORY] NEW ENTRY {json.dumps(entry, ensure_ascii=False)}")

    _load()  # settles _CACHE_PATH
    path = _CACHE_PATH or _candidate_paths()[0]
    try:
        try:
            with open(path, encoding='utf-8') as fh:
                doc = json.load(fh)
        except Exception:
            doc = {'venues': []}
        doc.setdefault('venues', []).append(entry)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
        os.replace(tmp, path)
        _CACHE.append(entry)
        return True, entry
    except Exception as e:
        print(f"   [SCOPE-MEMORY] could not persist ({e}) — entry is in the log above only")
        _CACHE.append(entry)   # still binds the rest of this container's life
        return False, entry
