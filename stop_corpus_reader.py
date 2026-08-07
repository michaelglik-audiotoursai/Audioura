"""stop_corpus_reader.py — LOCAL-183

Read per-stop source material from the stop_corpus table and format it
for injection into tour generation prompts.

This module is the production counterpart of the logic in
tests/stop_anchor_detector_v2_with_stop_corpus.py — same table, same
lookup strategy, but formatted for the generator rather than the detector.

Design constraints (D50, D54, D57):
- Passages carry source URLs so the model can ground on real text.
- The generator prompt must instruct the model to substantiate only
  from the provided passages, never from its own memory.
- Falls back to venue_corpus when a stop has no per-stop corpus.
"""
import json
import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("stop_corpus_reader")


def _normalize_for_match(text: str) -> str:
    """Normalize text for fuzzy matching (mirrors detector logic)."""
    return re.sub(r'[^a-z0-9\s]', '', text.lower()).strip()


def _accent_fold(text: str) -> str:
    """Fold accented characters to ASCII equivalents for matching.

    LOCAL-277: Île/Ile, Èze/Eze, Château/Chateau, Carré/Carre etc.
    """
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


# LOCAL-277: Name variant groups — these drawn names refer to the same place.
# Each tuple is (canonical_corpus_title, [variant_names_the_selector_may_use]).
# Only equivalent places; distinct places (e.g. Cap Ferrat Lighthouse vs Cap Ferrat) stay separate.
_NAME_VARIANT_MAP = {
    # Port/Harbor forms for the same place
    'saint-tropez harbor': ['port de saint-tropez', 'port of saint-tropez', 'saint-tropez port',
                            'saint-tropez harbour', 'vieux port de saint-tropez'],
    'port de nice': ['port lympia', 'port of nice', 'nice harbor', 'nice harbour',
                     'old port of nice', 'vieux port de nice'],
    'port grimaud': ['port de grimaud', 'port of grimaud'],
    # Accent/article variants
    'ile sainte-marguerite': ['ile sainte marguerite', 'ile ste-marguerite',
                              'ile ste marguerite', 'saint margaret island'],
    # "Old Town" with/without "of"
    'old town of antibes': ['old town antibes', 'vieil antibes', 'vieille ville d\'antibes'],
    # Croisette variants
    'la croisette': ['cannes croisette', 'boulevard de la croisette',
                     'promenade de la croisette', 'the croisette'],
    # Chateau variants
    'chateau de la chevre d\'or': ['la chevre d\'or', 'chevre d\'or',
                                    'chateau chevre d\'or'],
    # Saint-Paul hyphen variants
    'saint-paul-de-vence': ['saint-paul de vence', 'saint paul de vence',
                            'st-paul-de-vence', 'st paul de vence'],
    # Cap Ferrat variants (note: Cap Ferrat Lighthouse IS arguably different — kept separate)
    'cap ferrat': ['saint-jean-cap-ferrat', 'st-jean-cap-ferrat'],
    # Fort variants
    'fort carre d\'antibes': ['fort carre', 'fort carre antibes'],
    # Eze
    'eze village': ['village d\'eze', 'eze'],
    # Mougins
    'vieux village de mougins': ['mougins village', 'old village of mougins',
                                  'mougins old village', 'mougins'],
}


def _match_via_variants(stop_name: str, corpus_rows: List[Dict]) -> Optional[Dict]:
    """LOCAL-277: Match a drawn stop name to corpus via known variant groups.

    Accent-folded, case-insensitive comparison. Returns the best matching row
    or None if no variant match found.
    """
    stop_folded = _accent_fold(stop_name).lower().strip()

    for row in corpus_rows:
        corpus_folded = _accent_fold(row['stop_title']).lower().strip()

        # Direct accent-folded match
        if stop_folded == corpus_folded:
            return row

    # Check variant map: is the drawn name a known variant of a corpus title?
    for canonical, variants in _NAME_VARIANT_MAP.items():
        all_forms = [canonical] + variants
        all_folded = [_accent_fold(f).lower().strip() for f in all_forms]

        if stop_folded in all_folded:
            # Find corpus row matching canonical or any variant
            for row in corpus_rows:
                row_folded = _accent_fold(row['stop_title']).lower().strip()
                if row_folded in all_folded:
                    return row

    return None


def get_stop_corpus_for_tour(
    venue_name: str,
    stop_names: List[str],
    conn,
) -> Dict[str, Optional[Dict]]:
    """Fetch per-stop corpus passages for all stops in a tour.

    Args:
        venue_name: The venue name used in generation (e.g. tour location).
        stop_names: List of stop/POI names in the tour.
        conn: psycopg2 connection.

    Returns:
        Dict mapping stop_name → {passages: [...], sources: [...]} or None.
        Each passage is the raw text string.
        Each source is {url, tier, title, ...} from source_pages.
    """
    import psycopg2.extras

    result = {}

    # First, find which venue_name(s) in stop_corpus match this tour
    corpus_venue_name = _find_corpus_venue_name(venue_name, conn)
    if not corpus_venue_name:
        # No stop_corpus rows for this venue at all
        for name in stop_names:
            result[name] = None
        return result

    # Fetch all rows for this venue in one query
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT stop_title, passages_json, source_pages, passage_roles FROM stop_corpus WHERE venue_name = %s",
        (corpus_venue_name,)
    )
    corpus_rows = cur.fetchall()
    cur.close()

    if not corpus_rows:
        for name in stop_names:
            result[name] = None
        return result

    # Build lookup index
    corpus_by_title = {}
    for row in corpus_rows:
        corpus_by_title[row['stop_title']] = row

    # Match each stop to its corpus row
    for stop_name in stop_names:
        matched = _match_stop_to_corpus(stop_name, corpus_rows)
        if matched:
            passages_raw = matched['passages_json']
            if isinstance(passages_raw, str):
                passages_raw = json.loads(passages_raw)

            sources_raw = matched.get('source_pages', [])
            if isinstance(sources_raw, str):
                sources_raw = json.loads(sources_raw)

            # [LOCAL-328] Filter sludge passages at read time.
            # This removes directory listings, keyword blobs, and search-result
            # collages that inflate passage_count without carrying facts.
            from corpus_source_quality import filter_passages_for_generation
            passages_filtered = filter_passages_for_generation(passages_raw)

            # Extract passage texts
            passages = []
            for p in (passages_filtered or []):
                if isinstance(p, dict):
                    text = p.get('text', '')
                elif isinstance(p, str):
                    text = p
                else:
                    text = str(p)
                if text:
                    passages.append(text)

            # [LOCAL-203] Include passage_roles for role-aware coverage
            roles_raw = matched.get('passage_roles')
            if isinstance(roles_raw, str):
                roles_raw = json.loads(roles_raw)

            result[stop_name] = {
                'passages': passages,
                'sources': sources_raw or [],
                'passage_roles': roles_raw or [],
            } if passages else None
        else:
            result[stop_name] = None

    return result


def _find_corpus_venue_name(venue_name: str, conn) -> Optional[str]:
    """Find the matching venue_name in stop_corpus for this tour's venue.

    Uses the same strategy as the detector: exact match first, then
    significant-word matching with stop-word exclusion.
    """
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Try various forms of the venue name
    candidates = [venue_name]
    # Strip " - Biking Tour" etc. suffixes
    if ' - ' in venue_name:
        candidates.append(venue_name.split(' - ')[0].strip())
    # Strip trailing ", Country"
    parts = venue_name.split(',')
    if len(parts) > 1:
        candidates.append(parts[0].strip())
        candidates.append(', '.join(parts[:-1]).strip())

    for candidate in candidates:
        cur.execute(
            "SELECT DISTINCT venue_name FROM stop_corpus WHERE venue_name ILIKE %s",
            (f'%{candidate}%',)
        )
        row = cur.fetchone()
        if row:
            cur.close()
            return row['venue_name']

    # Significant-word fallback
    _stop_words = {'tour', 'france', 'museum', 'musee', 'musée', 'nice',
                   'walking', 'biking', 'cycling', 'historical', 'boston',
                   'common', 'park', 'street', 'avenue', 'area'}
    raw_words = re.findall(r'[A-Za-zÀ-ÿ]+', venue_name)
    words = [w for w in raw_words if len(w) >= 5 and w.lower() not in _stop_words]

    for w in words:
        cur.execute(
            "SELECT DISTINCT venue_name FROM stop_corpus WHERE venue_name ILIKE %s",
            (f'%{w}%',)
        )
        rows = cur.fetchall()
        if len(rows) == 1:
            cur.close()
            return rows[0]['venue_name']

    cur.close()
    return None


def _match_stop_to_corpus(stop_name: str, corpus_rows: List[Dict]) -> Optional[Dict]:
    """Match a stop name to its corpus row using multi-strategy matching.

    Strategy: exact → accent-folded → variant map → containment → fuzzy word overlap.
    LOCAL-277: Added accent folding (step 2) and variant map (step 3) to resolve
    name fragmentation that caused 11/23 drawn stops to find zero corpus.
    """
    stop_norm = _normalize_for_match(stop_name)

    # 1. Exact match (case-insensitive)
    for row in corpus_rows:
        if row['stop_title'].lower().strip() == stop_name.lower().strip():
            return row

    # 2. LOCAL-277: Accent-folded exact match (Île→Ile, Château→Chateau, etc.)
    stop_folded = _accent_fold(stop_name).lower().strip()
    for row in corpus_rows:
        if _accent_fold(row['stop_title']).lower().strip() == stop_folded:
            return row

    # 3. LOCAL-277: Known variant groups (Port de/Port of/Harbor, Old Town/Old Town of, etc.)
    variant_match = _match_via_variants(stop_name, corpus_rows)
    if variant_match:
        return variant_match

    # 4. Containment match (either direction)
    for row in corpus_rows:
        title_lower = row['stop_title'].lower()
        name_lower = stop_name.lower()
        if name_lower in title_lower or title_lower in name_lower:
            return row

    # 5. Normalized word overlap (significant words)
    for row in corpus_rows:
        corpus_title_norm = _normalize_for_match(row['stop_title'])
        corpus_words = set(w for w in corpus_title_norm.split() if len(w) >= 4)
        stop_words = set(w for w in stop_norm.split() if len(w) >= 4)
        if corpus_words and stop_words:
            overlap = corpus_words & stop_words
            threshold = max(1, min(len(corpus_words), len(stop_words)) * 0.5)
            if len(overlap) >= threshold:
                return row

    return None


def format_passages_for_prompt(
    stop_corpus_data: Optional[Dict],
    stop_name: str,
    max_chars: int = 2000,
) -> str:
    """Format stop_corpus passages into a prompt injection block.

    Returns a ready-to-inject string with passages and source URLs,
    plus the grounding instruction (D50). Returns empty string if no data.

    [LOCAL-203] When passage_roles are available, annotates each passage
    with its role so the model knows what content it may use for what purpose.
    """
    if not stop_corpus_data or not stop_corpus_data.get('passages'):
        return ""

    passages = stop_corpus_data['passages']
    sources = stop_corpus_data.get('sources', [])
    roles = stop_corpus_data.get('passage_roles', [])

    # Truncate passages to fit budget
    passage_block = []
    passage_roles_for_prompt = []
    total_chars = 0
    for i, p in enumerate(passages):
        if total_chars + len(p) > max_chars:
            # Include partial if room
            remaining = max_chars - total_chars
            if remaining > 100:
                passage_block.append(p[:remaining] + "…")
                passage_roles_for_prompt.append(roles[i] if i < len(roles) else None)
            break
        passage_block.append(p)
        passage_roles_for_prompt.append(roles[i] if i < len(roles) else None)
        total_chars += len(p)

    if not passage_block:
        return ""

    # Format source URLs
    source_urls = []
    for s in sources:
        if isinstance(s, dict) and s.get('url'):
            tier = s.get('tier', '?')
            title = s.get('title', '')
            source_urls.append(f"  [{title}] {s['url']} (tier {tier})")
        elif isinstance(s, str):
            source_urls.append(f"  {s}")

    # Build the injection block
    lines = [
        f"\nPER-STOP SOURCE MATERIAL for \"{stop_name}\" (from verified sources — use this as your primary factual basis):",
    ]
    for i, p in enumerate(passage_block, 0):
        role_info = ""
        if i < len(passage_roles_for_prompt) and passage_roles_for_prompt[i]:
            r = passage_roles_for_prompt[i]
            role_val = r.get('role') if isinstance(r, dict) else r
            if role_val:
                role_info = f" [ROLE: {role_val}]"
        lines.append(f"  Passage {i+1}{role_info}: {p}")

    if source_urls:
        lines.append("  Sources:")
        lines.extend(source_urls)

    lines.append("")
    lines.append(
        "GROUNDING RULE (D50 — critical): Substantiate claims ONLY from the passages above. "
        "Do NOT supplement with facts from your own training data that are not in these passages. "
        "If the passages do not mention something, do not assert it as fact. "
        "You may describe what is physically visible at the stop and provide general orientation, "
        "but specific historical claims, dates, people, and events MUST come from the passages above. "
        "If a passage names a person or event, you may include it; if it does not, leave it out."
    )

    # [LOCAL-203] Add role-specific guidance when roles are present
    if roles:
        has_creator = any(
            (r.get('role') if isinstance(r, dict) else r) == 'about_creator'
            for r in passage_roles_for_prompt if r
        )
        has_subject = any(
            (r.get('role') if isinstance(r, dict) else r) == 'about_subject'
            for r in passage_roles_for_prompt if r
        )
        if has_creator and not has_subject:
            lines.append(
                "ROLE NOTE: All passages above are about the CREATOR/MAKER. You may discuss "
                "the maker's biography and significance, but do NOT describe the physical object "
                "at this stop — no appearance, materials, dimensions, or condition claims."
            )
        elif has_creator and has_subject:
            lines.append(
                "ROLE NOTE: Passages marked [ROLE: about_creator] describe the maker; those marked "
                "[ROLE: about_subject] describe the specific work. Use both appropriately."
            )

    return "\n".join(lines) + "\n"
