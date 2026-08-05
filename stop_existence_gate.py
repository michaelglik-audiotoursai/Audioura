"""stop_existence_gate.py — verify stops actually exist at the claimed venue.

LOCAL-236: D127 established that stops can be invented by the model.
26 of 29 real tours had no venue_corpus when generated, so stop titles
were fabricated. This gate checks whether a stop is a real object the
venue actually holds, BEFORE narration.

A stop is VERIFIED if:
  1. venue_corpus canonical title or SPARQL work for the venue matches, OR
  2. stop_corpus passage names the stop AND the venue in the same source
     (D74's same-source rule), OR
  3. The venue's own catalogue page lists it (future: not implemented yet).

If none holds, the stop is UNVERIFIED and must not be narrated.

Feature flag (default OFF pending LEAD review of blast-radius numbers):
  ENABLE_STOP_EXISTENCE_GATE=1   → gate active, UNVERIFIED stops dropped
  DISABLE_STOP_EXISTENCE_GATE=1  → gate disabled even if previously enabled

When OFF, the gate still LOGS verdicts (measurement mode) but does not
drop stops. This allows assessment without affecting output.
"""

import json
import logging
import os
import re
import unicodedata
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


def _strip_accents(text: str) -> str:
    """Remove accents for matching (é→e, ô→o, etc.)."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _normalize_title(title: str) -> str:
    """Normalize a title for comparison: lowercase, strip accents, collapse whitespace."""
    t = _strip_accents(title).lower().strip()
    t = re.sub(r'[^\w\s]', ' ', t)
    return ' '.join(t.split())


def _content_words(title: str) -> List[str]:
    """Extract meaningful words (>=4 chars, no stopwords) from a title."""
    STOP = {
        'the', 'and', 'for', 'with', 'from', 'that', 'this', 'are', 'was',
        'des', 'les', 'une', 'dans', 'sur', 'par', 'aux', 'son', 'ses',
        'qui', 'que', 'est', 'sont', 'art', 'arts', 'musee', 'museum',
        'stop', 'tour', 'nice', 'france',
    }
    words = _normalize_title(title).split()
    return [w for w in words if len(w) >= 4 and w not in STOP]


def _title_match(stop_title: str, canonical_title: str) -> bool:
    """Check if a stop title matches a canonical title.

    Uses normalized token overlap: >=60% of the shorter title's content words
    must appear in the longer. Also checks substring containment for short titles.
    """
    norm_stop = _normalize_title(stop_title)
    norm_canon = _normalize_title(canonical_title)

    # Exact match
    if norm_stop == norm_canon:
        return True

    # Substring containment (either direction)
    if len(norm_stop) > 5 and len(norm_canon) > 5:
        if norm_stop in norm_canon or norm_canon in norm_stop:
            return True

    # Token overlap
    stop_words = set(_content_words(stop_title))
    canon_words = set(_content_words(canonical_title))

    if not stop_words or not canon_words:
        return False

    # Check overlap against the shorter set
    shorter = stop_words if len(stop_words) <= len(canon_words) else canon_words
    longer = canon_words if len(stop_words) <= len(canon_words) else stop_words

    overlap = len(shorter & longer)
    if len(shorter) > 0 and overlap / len(shorter) >= 0.60:
        return True

    return False


def _find_venue_corpus_rows(venue_name: str, db_conn) -> list:
    """Find venue_corpus rows that match a venue name.

    Uses progressive relaxation:
    1. All significant words match (strict)
    2. Any 2 significant words match (relaxed)
    3. Single most specific word matches (last resort)

    Returns list of (venue_name, canonical_titles_json, sparql_works_json) tuples.
    """
    cur = db_conn.cursor()
    venue_words = [w for w in _content_words(venue_name) if len(w) >= 4]

    # Remove generic tour-type words that aren't venue identifiers
    TOUR_WORDS = {'tour', 'walking', 'biking', 'cycling', 'museum', 'visite',
                  'restaurant', 'экскурсия', 'тур', 'музей', 'musee'}
    venue_words = [w for w in venue_words if w not in TOUR_WORDS]

    if not venue_words:
        return []

    # Try strict: all words
    conditions = []
    params = []
    for w in venue_words[:4]:
        conditions.append("LOWER(venue_name) LIKE %s")
        params.append(f"%{w}%")

    query = f"""
        SELECT venue_name, canonical_titles_json, sparql_works_json
        FROM venue_corpus WHERE {' AND '.join(conditions)}
    """
    cur.execute(query, params)
    rows = cur.fetchall()
    if rows:
        return rows

    # Try relaxed: any 2 words (for multi-word venue names)
    if len(venue_words) >= 2:
        conditions = []
        params = []
        for w in venue_words[:4]:
            conditions.append("LOWER(venue_name) LIKE %s")
            params.append(f"%{w}%")

        query = f"""
            SELECT venue_name, canonical_titles_json, sparql_works_json
            FROM venue_corpus WHERE {' OR '.join(
                f"({c1} AND {c2})"
                for i, c1 in enumerate(conditions)
                for c2 in conditions[i+1:]
            )}
        """
        # Flatten params for OR pairs
        pair_params = []
        for i in range(len(params)):
            for j in range(i + 1, len(params)):
                pair_params.extend([params[i], params[j]])
        if pair_params:
            cur.execute(query, pair_params)
            rows = cur.fetchall()
            if rows:
                return rows

    # Last resort: single most specific word (longest, not a city name)
    CITIES = {'nice', 'paris', 'france', 'monaco', 'antibes', 'boston',
              'philadelphia', 'ницца', 'франция'}
    specific_words = [w for w in venue_words if w not in CITIES]
    if not specific_words:
        specific_words = venue_words

    # Sort by length descending (longer words are more specific)
    specific_words.sort(key=len, reverse=True)
    for w in specific_words[:2]:
        cur.execute(
            "SELECT venue_name, canonical_titles_json, sparql_works_json "
            "FROM venue_corpus WHERE LOWER(venue_name) LIKE %s",
            (f"%{w}%",)
        )
        rows = cur.fetchall()
        if rows:
            return rows

    return []


def _check_venue_corpus(
    stop_title: str, venue_name: str, db_conn
) -> Tuple[bool, str]:
    """Check venue_corpus for canonical_titles_json or sparql_works_json match.

    Returns (verified: bool, evidence: str).
    """
    try:
        rows = _find_venue_corpus_rows(venue_name, db_conn)

        for vc_name, ct_json, sw_json in rows:
            # Check canonical_titles_json
            if ct_json:
                titles = ct_json if isinstance(ct_json, list) else []
                for ct in titles:
                    if isinstance(ct, str) and _title_match(stop_title, ct):
                        return True, f"venue_corpus canonical_title: {ct!r} at {vc_name!r}"
                    elif isinstance(ct, dict):
                        # Geographic POI format: {name: ..., qid: ..., lat: ..., lng: ...}
                        name = ct.get('name', '')
                        if name and _title_match(stop_title, name):
                            return True, f"venue_corpus canonical_title(geo): {name!r} at {vc_name!r}"

            # Check sparql_works_json
            if sw_json:
                works = sw_json if isinstance(sw_json, list) else []
                for w in works:
                    if isinstance(w, dict):
                        for key in ('label_en', 'label_local'):
                            label = w.get(key, '')
                            if label and _title_match(stop_title, label):
                                return True, f"venue_corpus sparql_work: {label!r} (QID:{w.get('qid','?')}) at {vc_name!r}"

        return False, ""
    except Exception as e:
        logger.warning(f"[EXISTENCE-GATE] venue_corpus check failed: {e}")
        return False, ""


def _find_stop_corpus_rows(venue_name: str, db_conn) -> list:
    """Find stop_corpus rows that match a venue name.

    Similar to _find_venue_corpus_rows but for the stop_corpus table.
    Returns list of (venue_name, stop_title, passages_json, source_pages) tuples.
    """
    cur = db_conn.cursor()
    venue_words = [w for w in _content_words(venue_name) if len(w) >= 4]

    TOUR_WORDS = {'tour', 'walking', 'biking', 'cycling', 'museum', 'visite',
                  'restaurant', 'экскурсия', 'тур', 'музей', 'musee'}
    venue_words = [w for w in venue_words if w not in TOUR_WORDS]

    if not venue_words:
        return []

    # Try strict: all words
    conditions = []
    params = []
    for w in venue_words[:4]:
        conditions.append("LOWER(venue_name) LIKE %s")
        params.append(f"%{w}%")

    query = f"""
        SELECT venue_name, stop_title, passages_json, source_pages
        FROM stop_corpus
        WHERE {' AND '.join(conditions)} AND passage_count > 0
    """
    cur.execute(query, params)
    rows = cur.fetchall()
    if rows:
        return rows

    # Relaxed: any 2 words
    if len(venue_words) >= 2:
        or_conditions = []
        or_params = []
        for i in range(len(venue_words[:4])):
            for j in range(i + 1, len(venue_words[:4])):
                or_conditions.append(f"(LOWER(venue_name) LIKE %s AND LOWER(venue_name) LIKE %s)")
                or_params.extend([f"%{venue_words[i]}%", f"%{venue_words[j]}%"])

        if or_conditions:
            query = f"""
                SELECT venue_name, stop_title, passages_json, source_pages
                FROM stop_corpus
                WHERE ({' OR '.join(or_conditions)}) AND passage_count > 0
            """
            cur.execute(query, or_params)
            rows = cur.fetchall()
            if rows:
                return rows

    # Last resort: single most specific word
    CITIES = {'nice', 'paris', 'france', 'monaco', 'antibes', 'boston',
              'philadelphia', 'ницца', 'франция'}
    specific_words = [w for w in venue_words if w not in CITIES]
    if not specific_words:
        specific_words = venue_words
    specific_words.sort(key=len, reverse=True)

    for w in specific_words[:2]:
        cur.execute(
            "SELECT venue_name, stop_title, passages_json, source_pages "
            "FROM stop_corpus WHERE LOWER(venue_name) LIKE %s AND passage_count > 0",
            (f"%{w}%",)
        )
        rows = cur.fetchall()
        if rows:
            return rows

    return []


def _check_stop_corpus(
    stop_title: str, venue_name: str, db_conn
) -> Tuple[bool, str]:
    """Check stop_corpus for a passage that names BOTH the stop and the venue.

    D74 rule: venue confirmation must come from the same source as the subject claim.
    A stop_corpus row matching the stop title is not enough — the passages must
    mention both the stop subject and the venue in the same source.
    """
    try:
        rows = _find_stop_corpus_rows(venue_name, db_conn)

        for sc_venue, sc_stop, passages_json, source_pages in rows:
            # Check if this stop_corpus row matches our stop title
            if not _title_match(stop_title, sc_stop):
                continue

            # D74: passages must mention BOTH stop and venue in the same source
            # Check that at least one passage contains venue context
            if not passages_json:
                continue

            passages = passages_json if isinstance(passages_json, list) else []
            # Extract venue-identifying words (city name, museum name fragments)
            venue_signals = set()
            for part in re.split(r'[,\s]+', venue_name):
                part_clean = _strip_accents(part).lower()
                if len(part_clean) >= 4 and part_clean not in ('france', 'museum', 'musee'):
                    venue_signals.add(part_clean)

            for p in passages:
                p_text = p if isinstance(p, str) else (p.get('text', '') if isinstance(p, dict) else str(p))
                p_lower = _strip_accents(p_text).lower()

                # Check if passage has BOTH stop content and venue signal
                stop_words = _content_words(stop_title)
                has_stop = any(w in p_lower for w in stop_words) if stop_words else False
                has_venue = any(v in p_lower for v in venue_signals)

                if has_stop and has_venue:
                    return True, f"stop_corpus: {sc_stop!r} at {sc_venue!r} (same-source confirmed)"

            # If passages exist but none has both signals, it fails D74
            # (the passage might be about the subject in general but not at THIS venue)

        return False, ""
    except Exception as e:
        logger.warning(f"[EXISTENCE-GATE] stop_corpus check failed: {e}")
        return False, ""


def _classify_venue_kind(venue_name: str, db_conn) -> Tuple[str, str]:
    """Classify a venue as 'institution' or 'geographic_area'.

    LOCAL-239: An institution (museum, palace, named building) and a geographic
    area (walking route, region, coastal path) need different confirmation logic.

    Classification signal: venue_corpus.sparql_works_json presence.
      - Institution: has sparql_works_json (a list of held works from Wikidata)
      - Geographic area: no sparql_works_json (canonical_titles are POIs/sections)

    Returns:
        (kind: 'institution' | 'geographic_area' | 'unknown', evidence: str)
    """
    try:
        rows = _find_venue_corpus_rows(venue_name, db_conn)
        if not rows:
            return 'unknown', 'no venue_corpus row found'

        # Check if ANY matched row has sparql_works_json
        for vc_name, ct_json, sw_json in rows:
            if sw_json:
                return 'institution', f'sparql_works_json present at {vc_name!r}'

        # No sparql — geographic area
        vc_name = rows[0][0]
        return 'geographic_area', f'no sparql_works_json at {vc_name!r}'
    except Exception as e:
        logger.warning(f"[EXISTENCE-GATE] venue kind classification failed: {e}")
        return 'unknown', f'classification error: {e}'


def _check_stop_corpus_geographic(
    stop_title: str, venue_name: str, db_conn
) -> Tuple[bool, str]:
    """Check stop_corpus for a geographic area — relaxed confirmation.

    LOCAL-239: For geographic areas, the stop does NOT need to mention the
    venue name in its passage. A stop_corpus row matching the stop title under
    this venue, with at least one passage, is sufficient evidence that it is a
    real place in the region.

    This is fundamentally different from institutions: a museum stop must prove
    the object is AT that museum (same-source rule, D74). But Eze Village's
    Wikipedia article will never say "French Riviera walking area" — it just
    needs to be a real place that is geographically within the Riviera.
    """
    try:
        rows = _find_stop_corpus_rows(venue_name, db_conn)

        for sc_venue, sc_stop, passages_json, source_pages in rows:
            # Check if this stop_corpus row matches our stop title
            if not _title_match(stop_title, sc_stop):
                continue

            # For geographic areas: having a passage at all is sufficient
            if passages_json:
                passages = passages_json if isinstance(passages_json, list) else []
                if passages:
                    return True, f"stop_corpus(geographic): {sc_stop!r} at {sc_venue!r} ({len(passages)} passages)"

        return False, ""
    except Exception as e:
        logger.warning(f"[EXISTENCE-GATE] stop_corpus geographic check failed: {e}")
        return False, ""


def verify_stop_existence(
    stop_title: str,
    venue_name: str,
    db_conn,
) -> Dict:
    """Verify whether a stop actually exists at the claimed venue.

    LOCAL-239: Uses venue kind to determine verification strictness:
      - institution: source must tie the object to THAT institution (D74, D127)
      - geographic_area: stop must be a real place in the region (relaxed)

    Returns:
        {
            'stop_title': str,
            'venue_name': str,
            'venue_kind': 'institution' | 'geographic_area' | 'unknown',
            'verified': bool,
            'evidence': str (what confirmed it, or '' if unverified),
            'source': 'venue_corpus' | 'stop_corpus' | 'stop_corpus_geographic' | '',
        }
    """
    # Classify venue kind first
    venue_kind, kind_evidence = _classify_venue_kind(venue_name, db_conn)

    result = {
        'stop_title': stop_title,
        'venue_name': venue_name,
        'venue_kind': venue_kind,
        'verified': False,
        'evidence': '',
        'source': '',
    }

    # Check 1: venue_corpus (canonical titles, SPARQL works)
    # This works for BOTH kinds — a canonical title match is always valid
    verified, evidence = _check_venue_corpus(stop_title, venue_name, db_conn)
    if verified:
        result['verified'] = True
        result['evidence'] = evidence
        result['source'] = 'venue_corpus'
        return result

    # Check 2: stop_corpus — logic depends on venue kind
    if venue_kind == 'geographic_area':
        # Relaxed: stop_corpus row with passages is sufficient (no same-source
        # venue mention required). A real place doesn't need to name our
        # internal label "French Riviera walking area" in its Wikipedia article.
        verified, evidence = _check_stop_corpus_geographic(stop_title, venue_name, db_conn)
        if verified:
            result['verified'] = True
            result['evidence'] = evidence
            result['source'] = 'stop_corpus_geographic'
            return result
    else:
        # Institution or unknown: strict same-source rule (D74, D127).
        # The passage must mention BOTH the stop and the venue.
        verified, evidence = _check_stop_corpus(stop_title, venue_name, db_conn)
        if verified:
            result['verified'] = True
            result['evidence'] = evidence
            result['source'] = 'stop_corpus'
            return result

    # Check 3: venue catalogue page — not implemented yet
    # (would require fetching venue's official collection page and checking)

    return result


def run_existence_gate(
    poi_list: List[str],
    venue_name: str,
    db_conn,
) -> Dict:
    """Run the stop-existence gate over a list of candidate stops.

    Feature flags:
        ENABLE_STOP_EXISTENCE_GATE=1  → gate enforced (unverified stops dropped)
        DISABLE_STOP_EXISTENCE_GATE=1 → gate completely off (no logging either)

    When gate is NOT enabled, verdicts are still logged for measurement but
    stops are NOT dropped.

    Returns:
        {
            'gate_enabled': bool,
            'gate_enforced': bool,
            'total_stops': int,
            'verified_stops': list of stop titles,
            'unverified_stops': list of stop titles,
            'verdicts': list of verify_stop_existence results,
            'action': 'ENFORCED' | 'LOG_ONLY' | 'DISABLED',
        }
    """
    # Feature flag logic
    disabled = os.environ.get('DISABLE_STOP_EXISTENCE_GATE', '').strip() == '1'
    enabled = os.environ.get('ENABLE_STOP_EXISTENCE_GATE', '').strip() == '1'

    if disabled:
        return {
            'gate_enabled': False,
            'gate_enforced': False,
            'total_stops': len(poi_list),
            'verified_stops': list(poi_list),
            'unverified_stops': [],
            'verdicts': [],
            'action': 'DISABLED',
        }

    # Run verification on all stops regardless of enforcement
    verdicts = []
    verified_stops = []
    unverified_stops = []

    for stop_title in poi_list:
        verdict = verify_stop_existence(stop_title, venue_name, db_conn)
        verdicts.append(verdict)
        if verdict['verified']:
            verified_stops.append(stop_title)
        else:
            unverified_stops.append(stop_title)

    # Log results
    n_ver = len(verified_stops)
    n_unver = len(unverified_stops)
    pct_ver = n_ver / len(poi_list) * 100 if poi_list else 0

    if enabled:
        action = 'ENFORCED'
        print(f"  [EXISTENCE-GATE] ENFORCED — {n_ver}/{len(poi_list)} stops verified "
              f"({pct_ver:.0f}%), dropping {n_unver} unverified")
    else:
        action = 'LOG_ONLY'
        print(f"  [EXISTENCE-GATE] LOG_ONLY — {n_ver}/{len(poi_list)} stops verified "
              f"({pct_ver:.0f}%), {n_unver} would be dropped if enforced")

    # Log individual verdicts
    for v in verdicts:
        status = "VERIFIED" if v['verified'] else "UNVERIFIED"
        ev = v['evidence'][:80] if v['evidence'] else "no evidence"
        print(f"    [{status}] {v['stop_title']!r:.50s} — {ev}")

    return {
        'gate_enabled': True,
        'gate_enforced': enabled,
        'total_stops': len(poi_list),
        'verified_stops': verified_stops,
        'unverified_stops': unverified_stops,
        'verdicts': verdicts,
        'action': action,
    }
