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
    [LOCAL-340] Also folds typographic apostrophes/quotes to ASCII.
    U+2019 (') and U+2018 (') → U+0027 (')
    U+201C (") and U+201D (") → U+0022 (")
    This is the D243 "third face": L'Armure (U+2019) must match L'Armure (U+0027).
    """
    import unicodedata
    # [LOCAL-340] Fold typographic quotes to ASCII before NFKD decomposition.
    # These survive NFKD and would otherwise cause exact-match failures.
    text = text.replace('\u2019', "'").replace('\u2018', "'")
    text = text.replace('\u201C', '"').replace('\u201D', '"')
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

    [LOCAL-339] Strategy: stop-title-first matching with venue as tie-breaker.

    The same stop_title can appear under multiple venue_name values (e.g.
    'Chez Palmyre' exists under 3 different venues). Matching by venue first
    misses stops when the tour's venue string doesn't exactly align with the
    corpus venue (e.g. 'restaurant tour in Old Nice (Vieux Nice), France' vs
    'Old Nice, Nice, France'). Matching by stop_title first — with venue as
    a preference when there are duplicates — is sounder.

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

    # [LOCAL-339] Clean the venue name using _prolog_place to strip tour-type
    # prefixes ("restaurant tour in X" → "X"). This gives a better venue
    # string for tie-breaking when multiple corpus rows match a stop_title.
    from generate_tour_text import _prolog_place
    clean_venue = _prolog_place(venue_name)

    # [LOCAL-339] Fetch ALL stop_corpus rows that could match any of our stops.
    # Strategy: query by stop_title (accent-folded) across all venues, then use
    # venue affinity as a tie-breaker.
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT venue_name, stop_title, passages_json, source_pages, passage_roles FROM stop_corpus"
    )
    all_corpus_rows = cur.fetchall()
    cur.close()

    if not all_corpus_rows:
        for name in stop_names:
            result[name] = None
        return result

    # Determine venue affinity: find which venue_name(s) best match this tour.
    # Used as tie-breaker, not as primary filter.
    preferred_venue = _find_corpus_venue_name(clean_venue, conn)

    # [LOCAL-342] Pre-fetch venue_corpus rows for venue-as-stop bridging.
    # A place can be a VENUE in one tour (museum) and a STOP in another (walking).
    # When stop_corpus has no row for such a stop, the venue's own pages (Wikipedia
    # articles about the building) are valid material about the stop-as-place.
    venue_corpus_rows = _fetch_venue_corpus_rows(conn)

    # Match each stop to its best corpus row (title-first, venue as tie-breaker)
    for stop_name in stop_names:
        matched = _match_stop_title_first(stop_name, all_corpus_rows, preferred_venue)
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

            stop_corpus_result = {
                'passages': passages,
                'sources': sources_raw or [],
                'passage_roles': roles_raw or [],
            } if passages else None

            # [LOCAL-346] Merge bridge: when a stop_corpus row exists, ALSO
            # check the venue_corpus bridge. If the bridge provides material,
            # merge it — the venue_corpus (Wikipedia tier-1 about the building)
            # complements enrichment (tier-3 travel blogs about the stop).
            #
            # Rule: merge, not choose. The bridge provides building-level
            # context (architecture, history, significance) that the enrichment
            # rarely duplicates. Three enrichment passages and sixty-three
            # venue pages are not competitors — they are complementary.
            #
            # Safety: _bridge_venue_corpus_to_stop only matches when the stop's
            # title IS the venue name (e.g. "Palais Lascaris" matches
            # "Palais Lascaris, Nice"). Museum objects inside the venue
            # (e.g. "Harpe by Naderman") will never match → museum unaffected.
            bridged = _bridge_venue_corpus_to_stop(stop_name, venue_corpus_rows)
            if bridged and stop_corpus_result:
                result[stop_name] = _merge_stop_and_bridge(
                    stop_corpus_result, bridged, stop_name
                )
            else:
                result[stop_name] = stop_corpus_result
        else:
            # [LOCAL-342] Venue-as-stop bridge: when a stop has no stop_corpus
            # row, check if its title matches a venue_corpus venue_name. If so,
            # the venue's own pages (about the building/place) are usable as
            # material for this stop — filtered for relevance.
            bridged = _bridge_venue_corpus_to_stop(stop_name, venue_corpus_rows)
            result[stop_name] = bridged

    return result


def _match_stop_title_first(
    stop_name: str,
    all_corpus_rows: List[Dict],
    preferred_venue: Optional[str],
) -> Optional[Dict]:
    """[LOCAL-339] Match a stop to corpus by title first, venue as tie-breaker.

    [LOCAL-340] Match quality tiers: an exact/accent-folded title match ALWAYS
    beats a fuzzy (containment/word-overlap) match, regardless of venue
    preference. This prevents "Chez Pipo" from being grounded against
    "Chez Palmyre" corpus when the only overlap is the word "chez".

    When the same stop_title exists under multiple venues, prefer the row
    from the preferred_venue. When no preferred venue matches, take the row
    with the most passages (richest corpus).
    """
    # [LOCAL-340] Collect candidates in quality tiers:
    #   exact_matches: case-insensitive or accent-folded exact title match
    #   fuzzy_matches: containment or word-overlap matches
    # Exact matches always take priority — fuzzy matches are only considered
    # when no exact match exists.
    exact_matches = []
    fuzzy_matches = []
    stop_folded = _accent_fold(stop_name).lower().strip()
    stop_norm = _normalize_for_match(stop_name)

    for row in all_corpus_rows:
        title = row['stop_title']
        # 1. Exact case-insensitive
        if title.lower().strip() == stop_name.lower().strip():
            exact_matches.append(row)
            continue
        # 2. Accent-folded exact
        if _accent_fold(title).lower().strip() == stop_folded:
            exact_matches.append(row)
            continue
        # 3. Containment (either direction)
        if stop_name.lower() in title.lower() or title.lower() in stop_name.lower():
            fuzzy_matches.append(row)
            continue
        # 4. Normalized word overlap
        corpus_title_norm = _normalize_for_match(title)
        corpus_words = set(w for w in corpus_title_norm.split() if len(w) >= 4)
        stop_words = set(w for w in stop_norm.split() if len(w) >= 4)
        if corpus_words and stop_words:
            overlap = corpus_words & stop_words
            threshold = max(1, min(len(corpus_words), len(stop_words)) * 0.5)
            if len(overlap) >= threshold:
                fuzzy_matches.append(row)

    # [LOCAL-340] Use exact matches when available; fall back to fuzzy only
    # when no exact match exists. This is the critical fix: a stop must be
    # grounded against ITS OWN corpus, not a similarly-named stop's corpus.
    candidates = exact_matches if exact_matches else fuzzy_matches

    if not candidates:
        # Try variant map as last resort
        variant_match = _match_via_variants(stop_name, all_corpus_rows)
        if variant_match:
            return variant_match
        return None

    if len(candidates) == 1:
        return candidates[0]

    # Multiple candidates — use venue as tie-breaker
    if preferred_venue:
        venue_matches = [r for r in candidates if r['venue_name'] == preferred_venue]
        if venue_matches:
            # Among venue matches, prefer the one with most passages
            return max(venue_matches, key=lambda r: _passage_count(r))

    # No venue match or no preferred venue — take richest corpus
    return max(candidates, key=lambda r: _passage_count(r))


def _passage_count(row: Dict) -> int:
    """Count passages in a corpus row (for tie-breaking)."""
    passages_raw = row.get('passages_json', '[]')
    if isinstance(passages_raw, str):
        try:
            return len(json.loads(passages_raw))
        except (json.JSONDecodeError, TypeError):
            return 0
    if isinstance(passages_raw, list):
        return len(passages_raw)
    return 0


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

    # [LOCAL-345] Body-usage directive: the passages must appear in the
    # DESCRIPTION BODY, not only in the orientation. Without this, the LLM
    # uses corpus words in the orientation header and then writes an entirely
    # fabricated body from training data.
    lines.append("")
    lines.append(
        "BODY USAGE RULE (LOCAL-345 — critical): Your DESCRIPTION BODY (the main narrative "
        "paragraphs after the orientation) MUST incorporate specific facts, dates, or claims "
        "from the passages above. The orientation alone is not sufficient — the body text is "
        "where the listener spends most of their time. If a passage mentions a UNESCO designation, "
        "a founding date, a named historical event, or a specific fact, that material MUST appear "
        "in the body narrative, not just be referenced in the orientation line. A body that "
        "contains zero material from the provided passages is a failure."
    )

    # [LOCAL-352] Narrative arc directive: when corpus contains a person doing
    # something — leaving, founding, refusing, recommending, returning — the
    # stop must tell what happened, not merely that the person is associated.
    # Without this, "a chef who left the Negresco to cook for twenty people"
    # collapses to "a former Michelin-starred chef" — a credential, not a story.
    lines.append("")
    lines.append(
        "NARRATIVE ARC RULE (LOCAL-352 — critical): When a passage describes a person "
        "DOING something — leaving a position, founding a place, refusing an offer, "
        "recommending a dish, returning after years away — your description MUST tell "
        "the sequence of events, not merely state the person's credential or association. "
        "A credential is an adjective (\"Michelin-starred chef\"); a narrative is a "
        "sequence (\"he left his two-star kitchen at the Negresco to cook for twenty "
        "people in a back-street bistro\"). The listener wants to experience what "
        "happened, not read a résumé. Specifically:"
    )
    lines.append(
        "  - If a passage names WHERE someone came from and WHERE they went, state both."
    )
    lines.append(
        "  - If a passage names WHAT someone gave up and WHAT they chose instead, "
        "state the contrast."
    )
    lines.append(
        "  - If a passage names a specific person recommending, reviewing, or "
        "recounting an experience at this place, tell it as an event: who did what, "
        "where, and what they said or found. This applies to visitors, critics, "
        "chefs from elsewhere, and documented incidents — not only owners."
    )
    lines.append(
        "  - Do NOT flatten a narrative into a single adjective or title. "
        "\"Former head chef of the Negresco\" is a title; \"walked away from the "
        "Negresco's two Michelin stars to serve twenty people at a place whose name "
        "means workman's snack\" is a story. Tell the story."
    )
    lines.append(
        "  - Every element of the story MUST come from the passages above. You may "
        "not infer motivation, emotion, or dates not stated in the source material."
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


# ─── LOCAL-346: Merge stop_corpus + venue_corpus bridge ──────────────────────


def _merge_stop_and_bridge(
    stop_data: Dict,
    bridge_data: Dict,
    stop_name: str,
) -> Dict:
    """[LOCAL-346] Merge stop_corpus material with venue_corpus bridge material.

    The venue_corpus bridge provides tier-1 Wikipedia content about the building
    (architecture, history, significance). The stop_corpus enrichment provides
    tier-3 supplementary web detail. They are complementary, not competing.

    Merge strategy:
      - Bridge passages go FIRST (richer, tier-1, building-level context).
      - Stop_corpus passages appended (supplementary detail).
      - Deduplication by normalized text prefix (first 100 chars).
      - Sources merged with bridge sources first.
      - Passage roles merged correspondingly.

    This ensures the generator sees the best material first without losing
    the enrichment content.
    """
    # Deduplicate: reject stop_corpus passages that substantially overlap
    # with bridge passages (same text from different acquisition paths).
    bridge_passages = bridge_data.get('passages', [])
    stop_passages = stop_data.get('passages', [])

    # Build fingerprint set from bridge passages for dedup
    bridge_fingerprints = set()
    for p in bridge_passages:
        fp = _normalize_for_match(p)[:100]
        bridge_fingerprints.add(fp)

    # Keep only non-duplicate stop_corpus passages
    unique_stop_passages = []
    for p in stop_passages:
        fp = _normalize_for_match(p)[:100]
        if fp not in bridge_fingerprints:
            unique_stop_passages.append(p)
            bridge_fingerprints.add(fp)  # prevent intra-stop duplicates too

    # Merge: bridge first (richer context), then unique enrichment passages
    merged_passages = bridge_passages + unique_stop_passages

    # Merge sources: bridge sources (tier-1) first, then stop sources
    bridge_sources = bridge_data.get('sources', [])
    stop_sources = stop_data.get('sources', [])
    seen_urls = {s.get('url', '') for s in bridge_sources if s.get('url')}
    unique_stop_sources = [s for s in stop_sources if s.get('url', '') not in seen_urls]
    merged_sources = bridge_sources + unique_stop_sources

    # Merge passage_roles: bridge roles first, then stop roles for unique passages
    bridge_roles = bridge_data.get('passage_roles', [])
    stop_roles = stop_data.get('passage_roles', [])
    # Map stop_roles to the unique passages we kept
    if stop_roles and len(stop_roles) == len(stop_passages):
        unique_stop_roles = [
            stop_roles[i] for i, p in enumerate(stop_passages)
            if _normalize_for_match(p)[:100] not in
            {_normalize_for_match(bp)[:100] for bp in bridge_passages}
        ]
    else:
        unique_stop_roles = [{'role': 'enrichment'} for _ in unique_stop_passages]
    merged_roles = bridge_roles + unique_stop_roles

    logger.info(
        "[LOCAL-346] Merged stop_corpus (%d passages) + venue bridge (%d passages) "
        "→ %d total for %r (dedup removed %d)",
        len(stop_passages), len(bridge_passages), len(merged_passages),
        stop_name, len(stop_passages) - len(unique_stop_passages),
    )

    return {
        'passages': merged_passages,
        'sources': merged_sources,
        'passage_roles': merged_roles,
    }


# ─── LOCAL-342: Venue-as-stop bridging ───────────────────────────────────────
#
# A place that is a VENUE in one tour (e.g. "Palais Lascaris, Nice" as a museum
# tour) can be a STOP in another (e.g. "Palais Lascaris" as a walking tour stop).
# The venue_corpus holds Wikipedia pages about the building itself — valid
# material for a walking-tour listener standing outside.
#
# Critical constraint: NOT all venue_corpus content is about the venue-as-place.
# The stop_corpus rows filed under that venue are about objects INSIDE it
# (instruments, paintings). Those are already handled by normal stop_corpus
# matching and must not be confused with venue-level material.
#
# The bridge:
#   1. Match stop title to venue_corpus.venue_name (accent-folded, city-suffix tolerant)
#   2. Extract pages_json text (Wikipedia articles about the building)
#   3. Split into paragraph-sized passages
#   4. Filter: reject passages that are about individual objects inside (catalogue
#      entries) — keep only content about the building, history, architecture


def _fetch_venue_corpus_rows(conn) -> List[Dict]:
    """Fetch all venue_corpus rows (venue_name + pages_json) for bridging.

    Returns list of {venue_name, pages_json} dicts.
    Only fetches rows where pages_json is an array (has page content).
    """
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT venue_name, pages_json FROM venue_corpus "
        "WHERE jsonb_typeof(pages_json) = 'array'"
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def _venue_name_matches_stop(stop_name: str, venue_name: str) -> bool:
    """Check if a stop title matches a venue_corpus venue_name.

    Handles:
      - Exact match (case-insensitive, accent-folded)
      - City-suffix stripping: "Palais Lascaris, Nice" → "Palais Lascaris"
      - Typographic apostrophe folding (D253)

    Does NOT match:
      - Partial word overlap (too loose)
      - "walking area" suffixed venue names (those are geographic areas, not buildings)
    """
    # Reject "walking area" venues — they are tour-type labels, not specific buildings
    if 'walking area' in venue_name.lower():
        return False

    stop_folded = _accent_fold(stop_name).lower().strip()
    venue_folded = _accent_fold(venue_name).lower().strip()

    # Direct match
    if stop_folded == venue_folded:
        return True

    # Strip city suffix from venue: "Palais Lascaris, Nice" → "Palais Lascaris"
    # Also handles "Musee Picasso, Antibes, France" → "Musee Picasso"
    venue_parts = venue_folded.split(',')
    venue_base = venue_parts[0].strip()
    if stop_folded == venue_base:
        return True

    # Stop might have a city suffix too: "Nice Cathedral" matching "Nice Cathedral, Nice"
    stop_parts = stop_folded.split(',')
    stop_base = stop_parts[0].strip()
    if stop_base == venue_base:
        return True

    return False


def _split_into_passages(text: str, max_passage_len: int = 800) -> List[str]:
    """Split a page text into paragraph-sized passages.

    Uses double-newlines (paragraph breaks) as the primary split.
    Merges very short paragraphs with the next one.
    Splits very long paragraphs at sentence boundaries.
    """
    # Split on section headers (== ... ==) and double newlines
    raw_paragraphs = re.split(r'\n\s*\n|\n\s*==\s*', text)
    passages = []
    buffer = ""

    for para in raw_paragraphs:
        para = para.strip()
        # Remove wiki markup header closers
        para = re.sub(r'\s*==\s*$', '', para).strip()
        if not para:
            continue

        if len(buffer) + len(para) + 1 <= max_passage_len:
            buffer = (buffer + "\n" + para).strip() if buffer else para
        else:
            if buffer:
                passages.append(buffer)
            # If this paragraph is itself too long, split at sentences
            if len(para) > max_passage_len:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                chunk = ""
                for sent in sentences:
                    if len(chunk) + len(sent) + 1 <= max_passage_len:
                        chunk = (chunk + " " + sent).strip() if chunk else sent
                    else:
                        if chunk:
                            passages.append(chunk)
                        chunk = sent
                buffer = chunk
            else:
                buffer = para

    if buffer:
        passages.append(buffer)

    return passages


def _is_object_catalogue_passage(passage: str) -> bool:
    """Detect if a passage is about a specific object inside the venue.

    Returns True for catalogue-style entries about instruments, paintings,
    sculptures — content that describes individual items, not the building.

    Conservative: only rejects passages that are clearly about a single object,
    not passages that mention objects in the context of the building's collection.
    """
    passage_lower = passage.lower()

    # Catalogue patterns: "made by X in Y", instrument/artwork descriptions
    # that are about a specific item rather than the venue
    _object_indicators = [
        # Specific maker attribution patterns
        r'\b(made|crafted|built|created|painted|sculpted)\s+by\s+[A-Z]',
        # Instrument dimensions/materials (catalogue entries)
        r'\b(length|height|width)\s*:\s*\d+\s*(cm|mm|inches)',
        # Accession/inventory numbers
        r'\b(inv\.|accession|catalogue)\s*(no\.?|number|#)\s*[\d]',
    ]

    for pattern in _object_indicators:
        if re.search(pattern, passage, re.IGNORECASE):
            # Only reject if the passage is SHORT (a pure catalogue entry).
            # Longer passages mentioning a maker in context of the building's
            # history are fine.
            if len(passage) < 200:
                return True

    return False


def _bridge_venue_corpus_to_stop(
    stop_name: str,
    venue_corpus_rows: List[Dict],
) -> Optional[Dict]:
    """[LOCAL-342] Bridge venue_corpus pages into a stop's material.

    When a stop has no stop_corpus row but its title matches a venue_corpus
    venue_name, the venue's own pages (Wikipedia articles about the building)
    are valid material for a walking-tour stop.

    Returns {passages: [...], sources: [...], passage_roles: [...]} or None.
    """
    matched_venue = None
    for vc_row in venue_corpus_rows:
        if _venue_name_matches_stop(stop_name, vc_row['venue_name']):
            matched_venue = vc_row
            break

    if not matched_venue:
        return None

    pages_json = matched_venue['pages_json']
    if isinstance(pages_json, str):
        pages_json = json.loads(pages_json)

    if not isinstance(pages_json, list) or not pages_json:
        return None

    # Extract passages from venue pages, filtering for relevance
    all_passages = []
    sources = []

    for page in pages_json:
        if not isinstance(page, dict):
            continue
        text = page.get('text', '')
        url = page.get('url', '')
        title = page.get('title', '')

        if not text or len(text) < 50:
            continue

        # Split into passage-sized chunks
        page_passages = _split_into_passages(text)

        for p in page_passages:
            # Filter: reject object catalogue entries
            if _is_object_catalogue_passage(p):
                continue
            # Reject very short fragments
            if len(p) < 40:
                continue
            all_passages.append(p)

        if url:
            sources.append({
                'url': url,
                'tier': 1,  # Wikipedia = tier 1
                'title': title or f'Venue page: {matched_venue["venue_name"]}',
                'type': 'venue_corpus_bridge',
                'tier_reason': 'LOCAL-342: venue_corpus bridge (Wikipedia about the building)',
            })

    if not all_passages:
        return None

    logger.info(
        "[LOCAL-342] Venue-as-stop bridge: %r matched venue %r — %d passages from %d pages",
        stop_name, matched_venue['venue_name'], len(all_passages), len(pages_json)
    )

    return {
        'passages': all_passages,
        'sources': sources,
        'passage_roles': [{'role': 'about_venue_as_stop'} for _ in all_passages],
    }
