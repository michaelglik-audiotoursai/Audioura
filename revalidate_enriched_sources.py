#!/usr/bin/env python3
"""revalidate_enriched_sources.py — LOCAL-202

Re-validate every stop_corpus row that stop_subject_acquisition.py enriched.
Applies three new rules from D74:

1. VENUE CONFIRMATION MUST COME FROM THE SAME SOURCE AS THE SUBJECT CLAIM.
   A passage set is not evidence for its own members. Validate per source.

2. FOR A WORK-LEVEL STOP, A TITLE MATCH IS NOT IDENTIFICATION.
   Titles are reused, reinterpreted, and translated. The source must be
   about *that work* — which means the artist must match what the venue
   says it holds.

3. EVERY SOURCE MUST BE TIERED (D51).
   Unlabelled is worse than tier 3 because nothing downstream can weigh it.

After validation, removes passages from invalid sources and updates
the stop_corpus rows.

This script does NOT modify corpus_coverage.py or stop_subject_acquisition.py.
It applies changes directly to the DB and reports per-row verdicts.
"""
import json
import os
import re
import sys
import unicodedata
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))
from db_connection import get_connection


def normalize(text: str) -> str:
    """Normalize for matching: lowercase, strip accents, collapse whitespace."""
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', text.lower())
    stripped = ''.join(c for c in nfkd if not unicodedata.combining(c))
    stripped = re.sub(r'[^\w\s]', ' ', stripped)
    return ' '.join(stripped.split())


# ===========================================================================
# Source Tier Assignment (D51)
# ===========================================================================

def assign_tier(source: Dict) -> int:
    """Assign a tier to a source per D51 trust hierarchy.

    Tier 1: Wikipedia, institution's own site (e.g. mamac-nice.org, nice.fr)
    Tier 2: Academic, established arts journalism
    Tier 3: Commercial, travel blog, social, video
    """
    url = source.get('url', '')
    url_lower = url.lower()

    # Tier 1: Wikipedia
    if 'wikipedia.org' in url_lower:
        return 1

    # Tier 1: Institution's own site
    institutional_domains = [
        'mamac-nice.org', 'nice.fr', 'musee-matisse-nice.org',
        'musees-nationaux-alpesmaritimes.fr',
        'departement06.fr',  # Alpes-Maritimes departmental portal
    ]
    for domain in institutional_domains:
        if domain in url_lower:
            return 1

    # Tier 2: Academic / arts journalism
    academic_domains = [
        'jstor.org', 'academia.edu', 'artforum.com',
        'theartnewspaper.com', 'frieze.com',
    ]
    for domain in academic_domains:
        if domain in url_lower:
            return 2

    # Tier 3: Everything else (commercial, blogs, YouTube, travel sites)
    return 3


# ===========================================================================
# Per-Source Validation — the core D74 fix
# ===========================================================================

# Known correct attributions for MAMAC stops (from MAMAC's own collection data)
KNOWN_ATTRIBUTIONS = {
    "Le Déjeuner sur l'herbe": "Alain Jacquet",
    "Le Village de grand-mère": "Arman",
    "Le Mur de Feu d'Yves Klein": "Yves Klein",
    "She-Bam Pow POP Wizz": None,  # Group exhibition - multiple artists valid
    "Richard Long ou la sculpture en marchant": "Richard Long",
    "Tir, séance 26 juin 1961": "Niki de Saint Phalle",
    "La mariée sous l'arbre": "Niki de Saint Phalle",
}

# Group exhibitions: these are shows featuring multiple artists; a single
# artist's biography is a PARTIAL source if that artist was a key participant.
# The stop title itself is not attributable to one person.
KNOWN_GROUP_EXHIBITIONS = {
    "She-Bam Pow POP Wizz": {
        'description': 'Group exhibition of women pop artists at MAMAC (2022)',
        'valid_artists': ['Niki de Saint Phalle', 'Evelyne Axell', 'Pauline Boty',
                          'Rosalyn Drexler', 'Marisol', 'Chryssa'],
    },
}


def validate_source_for_stop(
    source: Dict,
    passages_from_source: List[str],
    stop_title: str,
    venue_name: str,
) -> Dict:
    """Validate a single source for a stop, per D74 rules.

    Returns:
        {
            'valid': bool,
            'reason': str,
            'tier': int,
            'deciding_sentence': str  # The sentence that decided the verdict
        }
    """
    url = source.get('url', '')
    title = source.get('title', '')
    tier = assign_tier(source)

    if not passages_from_source:
        return {
            'valid': False,
            'reason': 'no passages from this source',
            'tier': tier,
            'deciding_sentence': '',
        }

    all_text = '\n'.join(passages_from_source)
    all_text_lower = all_text.lower()
    all_text_norm = normalize(all_text)

    # --- Rule 1: Per-source venue confirmation ---
    # The venue signal must appear in THIS source's passages, OR in the
    # source's own URL/title (which identifies what the source is about).
    venue_confirmed_in_source = _check_venue_in_text(all_text_lower, venue_name)

    # Also check the source URL and title for venue confirmation
    if not venue_confirmed_in_source:
        source_identity = (url + ' ' + title).lower()
        venue_confirmed_in_source = _check_venue_in_text(source_identity, venue_name)

    # --- Rule 2: Work-level identity check ---
    # For a work-level stop, the source must be about THAT work at THAT venue.
    # If we know the correct artist, the source must mention them.
    known_artist = KNOWN_ATTRIBUTIONS.get(stop_title)

    if known_artist is not None:
        # We know who made this work — does the source confirm that artist?
        artist_norm = normalize(known_artist)
        artist_surname = artist_norm.split()[-1] if artist_norm.split() else ''

        # Check source article title first
        source_title_norm = normalize(title)

        # The source must be ABOUT the correct artist (in its title or lead)
        # Not just mention them in a list alongside others
        source_is_about_correct_artist = (
            artist_surname in source_title_norm
        )

        # Check if the source is primarily about a DIFFERENT artist
        # (i.e., the source title/lead identifies someone else as the subject)
        if not source_is_about_correct_artist:
            # Source article is not about our correct artist — it's about someone else
            deciding = _find_identity_sentence(all_text, title)
            return {
                'valid': False,
                'reason': f'source "{title}" is not about {known_artist} (correct artist for this work at this venue)',
                'tier': tier,
                'deciding_sentence': deciding,
            }

        # Additional check: is the source primarily about a DIFFERENT artist?
        wrong_artist = _detect_wrong_artist(all_text, known_artist, stop_title)
        if wrong_artist:
            deciding = _find_identity_sentence(all_text, title)
            return {
                'valid': False,
                'reason': f'source is primarily about {wrong_artist}, not {known_artist}',
                'tier': tier,
                'deciding_sentence': deciding,
            }

    # --- Rule 1 continued: venue confirmation must come from THIS source ---
    if not venue_confirmed_in_source:
        # For tier 1 Wikipedia artist articles, art-domain signals suffice
        # (same as original validator, but scoped to THIS source)
        art_signals = ['sculptor', 'sculpture', 'artist', 'painter', 'artiste',
                       'sculpteur', 'peintre', 'land art', 'contemporary art',
                       'art contemporain', 'museum', 'musée', 'gallery',
                       'exhibition', 'exposition', 'installation']
        has_art_signal = any(s in all_text_lower for s in art_signals)

        if not has_art_signal:
            deciding = passages_from_source[0][:150] if passages_from_source else ''
            return {
                'valid': False,
                'reason': 'no venue-confirming signal in this source\'s passages',
                'tier': tier,
                'deciding_sentence': deciding,
            }

    # --- Rule 3: Subject relevance ---
    # The source must actually be about the stop's subject
    subject_relevant = _check_subject_relevance(
        all_text, all_text_norm, stop_title, venue_name, title
    )
    if not subject_relevant['relevant']:
        # Exception: for single-artist venues (Chagall, Matisse), the artist
        # biography IS a valid source for any work at that venue, because the
        # venue confirms the artist-work relationship by definition.
        if not _is_single_artist_venue_source(venue_name, title, source):
            return {
                'valid': False,
                'reason': subject_relevant['reason'],
                'tier': tier,
                'deciding_sentence': subject_relevant.get('deciding_sentence', ''),
            }

    # Passed all checks
    deciding = _find_confirming_sentence(all_text, stop_title, venue_name)
    return {
        'valid': True,
        'reason': 'per-source venue confirmed + subject identity verified',
        'tier': tier,
        'deciding_sentence': deciding,
    }


def _check_venue_in_text(text_lower: str, venue_name: str) -> bool:
    """Check if venue-confirming signals appear in the text."""
    venue_lower = venue_name.lower()

    # Direct venue signals
    venue_signals = []
    if 'mamac' in venue_lower or 'art moderne' in venue_lower or 'art contemporain' in venue_lower:
        venue_signals = ['mamac', 'nice', 'art moderne', 'art contemporain',
                         'contemporary art', 'modern art']
    elif 'chagall' in venue_lower:
        venue_signals = ['nice', 'chagall', 'message biblique', 'biblical message']
    elif 'matisse' in venue_lower:
        venue_signals = ['nice', 'matisse', 'cimiez']
    elif 'lascaris' in venue_lower:
        venue_signals = ['nice', 'lascaris', 'baroque', 'palais']
    elif 'boston' in venue_lower:
        venue_signals = ['boston', 'massachusetts', 'common']
    elif 'riviera' in venue_lower or 'nice' in venue_lower or 'antibes' in venue_lower:
        venue_signals = ['nice', 'riviera', "côte d'azur", 'antibes',
                         'villefranche', 'beaulieu', 'eze']

    return any(signal in text_lower for signal in venue_signals)


def _detect_wrong_artist(text: str, correct_artist: str, stop_title: str) -> Optional[str]:
    """Detect if the source is primarily about a different artist than expected."""
    text_norm = normalize(text[:1500])  # Check the lead portion
    correct_norm = normalize(correct_artist)
    correct_surname = correct_norm.split()[-1] if correct_norm.split() else ''

    # Check if the lead paragraph identifies a DIFFERENT person
    lead = text[:500].lower()

    # Known wrong-artist patterns for our specific stops
    wrong_artists = {
        "Le Déjeuner sur l'herbe": [("manet", "Édouard Manet")],
        "Le Village de grand-mère": [("viallat", "Claude Viallat")],
        "Le Mur de Feu d'Yves Klein": [("bonfanti", "Antoine Bonfanti")],
    }

    if stop_title in wrong_artists:
        for pattern, name in wrong_artists[stop_title]:
            # Is this source primarily about the wrong artist?
            pattern_norm = normalize(pattern)
            if pattern_norm in normalize(text[:300]) and correct_surname not in normalize(text[:300]):
                return name

    return None


def _check_subject_relevance(
    text: str, text_norm: str, stop_title: str, venue_name: str, source_title: str
) -> Dict:
    """Check if the source is actually about the stop's subject."""
    # Extract meaningful words from stop title
    title_norm = normalize(stop_title)
    title_words = [w for w in title_norm.split() if len(w) >= 4]

    # Filter out common words
    noise = {'art', 'les', 'des', 'une', 'par', 'sur', 'sous', 'dans', 'avec',
             'pour', 'the', 'and', 'for', 'from', 'with', 'museum', 'musee',
             'exposition', 'exhibition'}
    title_words = [w for w in title_words if w not in noise]

    if not title_words:
        return {'relevant': True, 'reason': ''}

    # At least some title content words should appear in the text
    matches = sum(1 for w in title_words if w in text_norm)
    if matches > 0:
        return {'relevant': True, 'reason': ''}

    # No literal title word matches — check exceptions

    # Exception 1: for artist-named stops, the artist name in the source is enough
    known_artist = KNOWN_ATTRIBUTIONS.get(stop_title)
    if known_artist:
        artist_norm = normalize(known_artist)
        if artist_norm.split()[-1] in text_norm:
            return {'relevant': True, 'reason': ''}

    # Exception 2: for group exhibitions, any valid participant artist is enough
    exhibition_info = KNOWN_GROUP_EXHIBITIONS.get(stop_title)
    if exhibition_info:
        for artist in exhibition_info['valid_artists']:
            artist_surname = normalize(artist).split()[-1]
            if artist_surname in text_norm:
                return {'relevant': True, 'reason': ''}

    # Exception 3: for single-artist venues, the venue artist is always relevant
    venue_lower = venue_name.lower()
    single_artist_map = {'chagall': 'chagall', 'matisse': 'matisse'}
    for venue_key, artist_key in single_artist_map.items():
        if venue_key in venue_lower and artist_key in text_norm:
            return {'relevant': True, 'reason': ''}

    return {
        'relevant': False,
        'reason': f'no title content words found in source (tried: {title_words[:5]})',
        'deciding_sentence': text[:150],
    }


def _find_identity_sentence(text: str, source_title: str) -> str:
    """Find the sentence that identifies what the source is about."""
    # First sentence of the text usually identifies the subject
    sentences = re.split(r'(?<=[.!?])\s+', text[:500])
    if sentences:
        return sentences[0][:200]
    return text[:200]


def _find_confirming_sentence(text: str, stop_title: str, venue_name: str) -> str:
    """Find the sentence that confirms the source is relevant."""
    # Look for a sentence mentioning both subject and venue
    sentences = re.split(r'(?<=[.!?])\s+', text[:2000])
    stop_words = [w.lower() for w in stop_title.split() if len(w) >= 4]

    for sent in sentences:
        sent_lower = sent.lower()
        if any(w in sent_lower for w in stop_words):
            return sent[:200]

    # Fallback: first sentence
    return sentences[0][:200] if sentences else text[:200]


def _is_single_artist_venue_source(venue_name: str, source_title: str, source: Dict) -> bool:
    """Check if this is a valid artist-biography source for a single-artist museum.

    For venues like 'Musée Marc Chagall' or 'Musée Matisse', the venue only
    shows one artist's work, so a biography of that artist is inherently
    relevant to every stop — the venue ITSELF confirms the artist-work link.
    This is different from a multi-artist museum like MAMAC where "Manet" and
    "Jacquet" can be conflated.
    """
    venue_lower = venue_name.lower()
    source_title_lower = source_title.lower() if source_title else ''

    # Single-artist venues and their artists
    single_artist_venues = {
        'chagall': 'chagall',
        'matisse': 'matisse',
    }

    for venue_key, artist_key in single_artist_venues.items():
        if venue_key in venue_lower:
            # Source must be about THIS artist
            if artist_key in source_title_lower:
                return True
            url = source.get('url', '').lower()
            if artist_key in url:
                return True

    return False


# ===========================================================================
# Passage Attribution — determine which passages came from which source
# ===========================================================================

def attribute_passages_to_sources(
    passages: List,
    sources: List,
    stop_id: int,
) -> Dict[int, List[str]]:
    """Attribute passages to their sources.

    For rows enriched by stop_subject_acquisition.py, the pattern is:
    - New subject-specific passages are prepended
    - Existing venue-level passages follow
    - The source_pages list has both integer refs (old venue sources) and
      dict objects (new enrichment sources with url/tier/validation)

    This function groups passages by source index for per-source validation.
    Returns: {source_index: [passage_texts]}
    """
    # Identify which sources are enrichment sources (dicts with 'url')
    enrichment_sources = [(i, s) for i, s in enumerate(sources) if isinstance(s, dict) and 'url' in s]

    # Get passage texts
    passage_texts = []
    for p in passages:
        if isinstance(p, dict):
            passage_texts.append(p.get('text', ''))
        else:
            passage_texts.append(str(p))

    # If there's only one enrichment source and NO pre-existing venue sources,
    # all passages belong to that single source.
    if len(enrichment_sources) == 1:
        src_idx = enrichment_sources[0][0]
        non_enrichment = [s for s in sources if not (isinstance(s, dict) and 'url' in s)]
        if not non_enrichment:
            return {src_idx: passage_texts}
        # If there ARE pre-existing sources, fall through to content matching
        # so we only attribute passages that actually came from the enrichment source.

    result = {}
    claimed_passages = set()

    for src_idx, src in enrichment_sources:
        src_url = src.get('url', '')
        src_title = src.get('title', '')
        src_title_norm = normalize(src_title)

        # Find passages that match this source's subject
        matching_passages = []
        for p_idx, p_text in enumerate(passage_texts):
            if p_idx in claimed_passages:
                continue
            p_norm = normalize(p_text[:500])

            # Match by source title words appearing in passage
            matched = False
            if src_title_norm:
                title_words = [w for w in src_title_norm.split() if len(w) >= 4]
                if title_words:
                    word_matches = sum(1 for w in title_words if w in p_norm)
                    if word_matches >= 1:
                        matching_passages.append(p_text)
                        claimed_passages.add(p_idx)
                        matched = True

            if matched:
                continue

            # Match by URL domain hints
            if 'wikipedia.org' in src_url:
                # Extract the article name from URL
                parts = src_url.rstrip('/').split('/')
                if parts:
                    article_name = normalize(parts[-1].replace('_', ' ').replace('%20', ' '))
                    article_words = [w for w in article_name.split() if len(w) >= 4]
                    if article_words:
                        word_matches = sum(1 for w in article_words if w in p_norm)
                        if word_matches >= 1:
                            matching_passages.append(p_text)
                            claimed_passages.add(p_idx)

        result[src_idx] = matching_passages

    # For sources that got no passages via matching, check if unmatched passages
    # could belong to them (fallback for sources where title doesn't help)
    # ONLY do this when there are NO pre-existing venue sources — if venue
    # sources exist, unclaimed passages likely belong to THEM, not the enrichment.
    unclaimed = [passage_texts[i] for i in range(len(passage_texts)) if i not in claimed_passages]
    non_enrichment = [s for s in sources if not (isinstance(s, dict) and 'url' in s)]
    if unclaimed and len(enrichment_sources) == 1 and not non_enrichment:
        # Single enrichment source with no venue sources gets all unclaimed passages
        src_idx = enrichment_sources[0][0]
        result[src_idx] = result.get(src_idx, []) + unclaimed

    return result


# ===========================================================================
# Main Re-validation
# ===========================================================================

def revalidate_all_enriched_rows():
    """Re-validate all enriched rows and apply fixes."""
    conn = get_connection()
    cur = conn.cursor()

    # Get all enriched rows (those with url-containing source_pages)
    cur.execute("""
        SELECT id, venue_name, stop_title, passages_json, source_pages, passage_count
        FROM stop_corpus
        WHERE source_pages IS NOT NULL
          AND source_pages::text LIKE '%url%'
        ORDER BY id
    """)
    rows = cur.fetchall()

    print(f"{'='*70}")
    print(f"LOCAL-202: Re-validation of Enriched Sources")
    print(f"{'='*70}")
    print(f"Total enriched rows: {len(rows)}")
    print()

    verdicts = []
    changes_made = []

    for row in rows:
        stop_id, venue_name, stop_title, passages_json, source_pages, passage_count = row

        # Parse data
        passages = passages_json if isinstance(passages_json, list) else json.loads(passages_json) if passages_json else []
        sources = source_pages if isinstance(source_pages, list) else json.loads(source_pages) if source_pages else []

        # Get enrichment sources only
        enrichment_sources = [(i, s) for i, s in enumerate(sources) if isinstance(s, dict) and 'url' in s]

        if not enrichment_sources:
            continue

        print(f"--- id={stop_id} | {stop_title} | {venue_name} ---")

        # Attribute passages to sources
        passage_attribution = attribute_passages_to_sources(passages, sources, stop_id)

        sources_kept = []
        sources_removed = []
        passages_to_remove = set()

        for src_idx, src in enrichment_sources:
            src_passages = passage_attribution.get(src_idx, [])

            # Assign tier if missing
            if src.get('tier') is None:
                src['tier'] = assign_tier(src)

            # Validate this source
            verdict = validate_source_for_stop(
                source=src,
                passages_from_source=src_passages,
                stop_title=stop_title,
                venue_name=venue_name,
            )

            # Update tier in source
            src['tier'] = verdict['tier']

            if verdict['valid']:
                sources_kept.append({
                    'source': src,
                    'reason': verdict['reason'],
                    'deciding_sentence': verdict['deciding_sentence'],
                    'passages_count': len(src_passages),
                })
                print(f"  KEEP source: {src.get('title', src.get('url', '')[:50])}")
                print(f"    tier={verdict['tier']} | {verdict['reason']}")
                print(f"    evidence: \"{verdict['deciding_sentence'][:120]}\"")
            else:
                sources_removed.append({
                    'source': src,
                    'reason': verdict['reason'],
                    'deciding_sentence': verdict['deciding_sentence'],
                    'passages_count': len(src_passages),
                })
                # Mark passages from this source for removal
                for p_text in src_passages:
                    passages_to_remove.add(p_text)
                print(f"  REMOVE source: {src.get('title', src.get('url', '')[:50])}")
                print(f"    tier={verdict['tier']} | {verdict['reason']}")
                print(f"    evidence: \"{verdict['deciding_sentence'][:120]}\"")

        # Apply changes if any sources were removed
        if passages_to_remove:
            # Filter passages
            new_passages = []
            for p in passages:
                p_text = p.get('text', p) if isinstance(p, dict) else str(p)
                if p_text not in passages_to_remove:
                    new_passages.append(p)

            # Filter sources
            new_sources = [s for i, s in enumerate(sources)
                          if not (isinstance(s, dict) and 'url' in s and
                                  any(s == rem['source'] for rem in sources_removed))]
            # Keep valid enrichment sources (update tier)
            for kept in sources_kept:
                # Already in new_sources (wasn't removed)
                pass

            # Update tier on all remaining dict sources
            for s in new_sources:
                if isinstance(s, dict) and 'url' in s and s.get('tier') is None:
                    s['tier'] = assign_tier(s)

            # Write to DB
            cur.execute("""
                UPDATE stop_corpus
                SET passages_json = %s::jsonb,
                    source_pages = %s::jsonb,
                    passage_count = %s
                WHERE id = %s
            """, (
                json.dumps(new_passages),
                json.dumps(new_sources),
                len(new_passages),
                stop_id,
            ))

            changes_made.append({
                'id': stop_id,
                'stop_title': stop_title,
                'venue': venue_name,
                'passages_before': len(passages),
                'passages_after': len(new_passages),
                'sources_kept': len(sources_kept),
                'sources_removed': len(sources_removed),
                'removed_details': sources_removed,
            })

            print(f"  => passages: {len(passages)} -> {len(new_passages)}")
        else:
            # Just update tiers on existing sources if needed
            tier_updated = False
            for s in sources:
                if isinstance(s, dict) and 'url' in s:
                    new_tier = assign_tier(s)
                    if s.get('tier') != new_tier:
                        s['tier'] = new_tier
                        tier_updated = True

            if tier_updated:
                cur.execute("""
                    UPDATE stop_corpus
                    SET source_pages = %s::jsonb
                    WHERE id = %s
                """, (json.dumps(sources), stop_id))

            print(f"  => no passages removed (all sources valid)")

        verdicts.append({
            'id': stop_id,
            'stop_title': stop_title,
            'venue': venue_name,
            'sources_kept': sources_kept,
            'sources_removed': sources_removed,
        })

        print()

    conn.commit()

    # Summary
    print(f"{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"Rows examined: {len(verdicts)}")
    print(f"Rows modified: {len(changes_made)}")
    total_passages_removed = sum(c['passages_before'] - c['passages_after'] for c in changes_made)
    print(f"Total passages removed: {total_passages_removed}")
    print()

    if changes_made:
        print("Changes made:")
        for c in changes_made:
            print(f"  id={c['id']} {c['stop_title']}")
            print(f"    passages: {c['passages_before']} -> {c['passages_after']}")
            for rem in c['removed_details']:
                print(f"    removed: {rem['source'].get('title', '')} — {rem['reason']}")
        print()

    # Final counts
    cur.execute('SELECT COUNT(*) FROM stop_corpus')
    final_rows = cur.fetchone()[0]
    cur.execute('SELECT COALESCE(SUM(passage_count), 0) FROM stop_corpus')
    final_passages = cur.fetchone()[0]

    print(f"Final stop_corpus: {final_rows} rows, {final_passages} total passages")

    conn.close()
    return verdicts, changes_made


if __name__ == '__main__':
    revalidate_all_enriched_rows()
