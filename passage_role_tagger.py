#!/usr/bin/env python3
"""passage_role_tagger.py — LOCAL-203

Assign a role to every passage in stop_corpus:
  - about_subject: this object, artwork, exhibition, or place
  - about_creator: its artist, maker, or architect
  - about_venue: the institution or place that houses it

The role determines what the generation prompt may say:
  - about_subject → full narration of the object
  - about_creator → discuss the maker; must not describe the object
  - about_venue → orientation / institutional context only

Storage: stop_corpus.passage_roles JSONB — an array parallel to passages_json,
each element is {"role": "about_subject"|"about_creator"|"about_venue",
"source_url": str, "tier": int}.

A passage that fits NONE of the three roles is tagged null and excluded from
generation (it does not belong in the row). This script does not delete such
passages from passages_json — it marks them, so downstream can filter.

Rules (D75):
- Roles are a claim about content, not about the URL.
- Decide per passage by reading it.
- A Wikipedia article about an artist can contain a paragraph about the
  specific work — that paragraph is about_subject.
- Do not delete sources to improve a metric.
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
# Known artist attributions for work-level stops
# ===========================================================================

KNOWN_ARTISTS = {
    # MAMAC Nice
    "Le Déjeuner sur l'herbe": "Alain Jacquet",
    "Le Village de grand-mère": "Arman",
    "Le Mur de Feu d'Yves Klein": "Yves Klein",
    "She-Bam Pow POP Wizz": "Niki de Saint Phalle",
    "Richard Long ou la sculpture en marchant": "Richard Long",
    "Tir, séance 26 juin 1961": "Niki de Saint Phalle",
    "La mariée sous l'arbre": "Niki de Saint Phalle",
    # Chagall Museum
    "Abraham et les trois anges": "Marc Chagall",
    "L'Arche de Noé": "Marc Chagall",
    "La Bible : Abraham et Isaac en route": "Marc Chagall",
    "Le Cirque bleu": "Marc Chagall",
    # Matisse Museum
    "Nature morte aux grenades": "Henri Matisse",
    "Lectrice à la table jaune": "Henri Matisse",
    "Nymphe dans la forêt": "Henri Matisse",
    "Odalisque au coffret rouge": "Henri Matisse",
    "Papeete-Tahiti": "Henri Matisse",
    "Tempête à Nice": "Henri Matisse",
    # Palais Lascaris
    "Harpe by Naderman (Paris, 1780)": "Naderman",
    "Guitar by Antonio de Torres (Almeria, 1884)": "Antonio de Torres",
    "Basse de violon by Paolo Antonio Testore (Milan, 1696)": "Paolo Antonio Testore",
}


def _lookup_known_artist(stop_title: str) -> Optional[str]:
    """Look up known artist, normalizing curly quotes to straight ones."""
    # Direct lookup first
    artist = KNOWN_ARTISTS.get(stop_title)
    if artist:
        return artist
    # Try with curly quotes normalized to straight
    normalized_title = stop_title.replace('\u2019', "'").replace('\u2018', "'")
    artist = KNOWN_ARTISTS.get(normalized_title)
    if artist:
        return artist
    # Try the other direction (straight to curly)
    for key, val in KNOWN_ARTISTS.items():
        if key.replace("'", '\u2019') == stop_title or key.replace("'", '\u2018') == stop_title:
            return val
    return None


# Venue-level signals per venue (for about_venue detection)
VENUE_SIGNALS = {
    'mamac': ['mamac', 'musee d art moderne', 'art contemporain', 'nouveau realisme',
              'donations and deposits', 'donations et depots', 'permanent collection',
              'collection permanente', 'ouverture du musee', 'museum opening'],
    'chagall': ['musee chagall', 'musee national marc chagall', 'message biblique',
                'biblical message', 'cimiez'],
    'matisse': ['musee matisse', 'cimiez', 'musee de matisse'],
    'lascaris': ['palais lascaris', 'lascaris', 'baroque palace', 'instrument collection',
                 'collection d instruments'],
    'boston': ['boston common', 'freedom trail', 'public garden'],
    'riviera': [],  # Walking areas — no single venue
}


def _detect_venue_key(venue_name: str) -> Optional[str]:
    """Identify the venue category from venue_name."""
    v = venue_name.lower()
    if 'mamac' in v or 'art moderne' in v or 'art contemporain' in v:
        return 'mamac'
    if 'chagall' in v:
        return 'chagall'
    if 'matisse' in v:
        return 'matisse'
    if 'lascaris' in v:
        return 'lascaris'
    if 'boston' in v:
        return 'boston'
    if 'riviera' in v or ('nice' in v and 'walking' in v):
        return 'riviera'
    return None


def classify_passage_role(
    passage_text: str,
    stop_title: str,
    venue_name: str,
    source_url: str = "",
    source_title: str = "",
) -> str:
    """Classify a single passage's role.

    Returns: 'about_subject', 'about_creator', 'about_venue', or None
    (None means the passage doesn't belong).
    """
    if not passage_text or len(passage_text.strip()) < 20:
        return None

    text_norm = normalize(passage_text)
    text_lower = passage_text.lower()
    venue_key = _detect_venue_key(venue_name)

    # --- Check 1: Is this about the venue itself? ---
    if _is_about_venue(text_norm, text_lower, venue_key, stop_title):
        return 'about_venue'

    # --- Check 2: Is this about the creator? ---
    # Check creator BEFORE subject because a maker's biography is not about the object.
    # A passage about Naderman the harpist describes THE MAKER, not the harp at Lascaris.
    known_artist = _lookup_known_artist(stop_title)
    if known_artist and _is_about_creator(text_norm, text_lower, known_artist, stop_title):
        # But: if the passage ALSO directly references the specific work (not just
        # the artist), it's about_subject. E.g. "Klein's Mur de Feu at MAMAC" is
        # about the work even though it names the artist.
        if _is_about_subject(text_norm, text_lower, stop_title, venue_name):
            return 'about_subject'
        return 'about_creator'

    # For instrument stops at Lascaris, maker bios are about_creator
    if venue_key == 'lascaris' and _is_maker_bio(text_norm, text_lower, stop_title):
        return 'about_creator'

    # --- Check 3: Is this about the specific subject (object/place)? ---
    if _is_about_subject(text_norm, text_lower, stop_title, venue_name):
        return 'about_subject'

    # --- Check 3b: Collection-listing passages that name this instrument ---
    # Palais Lascaris passages from the Wikipedia article list instruments;
    # if the passage names this specific instrument, it's about_subject.
    if venue_key == 'lascaris' and _passage_names_this_instrument(text_norm, stop_title):
        return 'about_subject'

    # --- Check 4: For place-type stops (walking tours), the passage IS the subject ---
    if _is_place_stop(stop_title, venue_name):
        # Any passage with geographic/descriptive content about this place
        # is about_subject by definition
        if _passage_mentions_place(text_norm, stop_title):
            return 'about_subject'

    # --- Fallback: if the source is about the artist and we have a known artist ---
    if known_artist:
        artist_norm = normalize(known_artist)
        artist_surname = artist_norm.split()[-1]
        # If passage prominently features the artist, it's about_creator
        pattern = r'\b' + re.escape(artist_surname) + r'\b'
        if len(re.findall(pattern, text_norm)) >= 2:
            return 'about_creator'

    # If we can't classify it, check if it at least relates to the stop at all
    # For walking tour stops, be generous — geographic content is about_subject
    if venue_key == 'riviera' or 'walking' in venue_name.lower():
        return 'about_subject'  # Walking tour passages are inherently about the place

    return None


def _is_about_venue(text_norm: str, text_lower: str, venue_key: Optional[str], stop_title: str) -> bool:
    """Check if a passage is primarily about the venue/institution."""
    if not venue_key:
        return False

    signals = VENUE_SIGNALS.get(venue_key, [])
    if not signals:
        return False

    # The passage must be PRIMARILY about the venue (not just mention it in passing)
    # Check: multiple venue signals + content about the institution rather than a work
    venue_signal_count = sum(1 for s in signals if normalize(s) in text_norm)

    # Strong venue indicators: museum history, collection descriptions, opening info
    venue_content_patterns = [
        r'\bmuseum\b.*\bopen', r'\bmusee\b.*\bouvert',
        r'\bcollection\b.*\bwork', r'\bcollection\b.*\boeuvre',
        r'\bdonations?\b', r'\bdeposit', r'\bpermanent collection',
        r'\bexposition.+temporaire', r'\btemporary exhibition',
        r'\binaugur', r'\bfound.*\d{4}',
    ]
    venue_content_hits = sum(1 for p in venue_content_patterns if re.search(p, text_lower))

    # If the passage is about institutional donations/deposits, it's venue-level
    if 'donations and deposits' in text_lower or 'donations et' in text_lower:
        return True

    # Strong venue signal: many venue markers + institutional content
    if venue_signal_count >= 2 and venue_content_hits >= 1:
        return True

    # For MAMAC specifically: paragraphs listing multiple artists are venue-level
    if venue_key == 'mamac':
        # Count distinct artist names mentioned
        artist_names = ['klein', 'arman', 'saint phalle', 'niki', 'cesar',
                        'vautier', 'ben', 'raysse', 'christo', 'hains']
        artists_mentioned = sum(1 for a in artist_names if a in text_lower)
        if artists_mentioned >= 3:
            return True

    return False


def _is_about_subject(text_norm: str, text_lower: str, stop_title: str, venue_name: str) -> bool:
    """Check if a passage is about the specific object/artwork/place at the stop."""
    title_norm = normalize(stop_title)

    # Extract the key subject identifiers from the title
    # For artworks: the artwork name/title
    # For places: the place name
    # For instruments: the instrument type + maker provenance

    # Check for direct mentions of the artwork title or its key parts
    # (excluding common words and the artist name)
    title_words = [w for w in title_norm.split() if len(w) >= 4]
    noise = {'art', 'les', 'des', 'une', 'par', 'sur', 'sous', 'dans', 'avec',
             'pour', 'the', 'and', 'for', 'from', 'with', 'village', 'grand',
             'mere', 'sculpture', 'marchant'}

    # For specific artwork references (e.g. "Mur de Feu" in a passage about the work)
    stop_specific_phrases = _extract_subject_phrases(stop_title)
    for phrase in stop_specific_phrases:
        if normalize(phrase) in text_norm:
            return True

    # For instrument stops: if the passage describes the PHYSICAL instrument
    # (not the maker's biography — that's about_creator)
    # Indicators: physical attributes of an instrument, playing technique, sound
    instrument_physical_indicators = ['string', 'cordes', 'touche', 'manche',
                                       'soundboard', 'table d harmonie',
                                       'pedal', 'pedale', 'fret', 'bridge',
                                       'chevalet', 'tuning', 'accord',
                                       'resonance', 'tone', 'timbre',
                                       'collection', 'specimen', 'preserved']
    if any(ind in text_lower for ind in instrument_physical_indicators):
        # And it's an instrument stop
        if any(w in title_norm for w in ['harpe', 'guitar', 'guitare', 'violon',
                                          'basse', 'sacqueboute', 'luth']):
            return True

    # For collection-metadata passages that name this specific work
    # e.g. "Arman, Le Village de grand-mère, 1962, Collection MAMAC"
    known_artist = _lookup_known_artist(stop_title)
    if known_artist:
        artist_norm = normalize(known_artist)
        artist_surname = artist_norm.split()[-1]
        # If the passage contains BOTH the artist and a specific artwork reference
        if re.search(r'\b' + re.escape(artist_surname) + r'\b', text_norm):
            for phrase in stop_specific_phrases:
                phrase_norm = normalize(phrase)
                if phrase_norm in text_norm:
                    return True

    return False


def _extract_subject_phrases(stop_title: str) -> List[str]:
    """Extract phrases that identify the specific subject/artwork.

    For "X by Y" patterns, the subject is X (the object), not Y (the maker).
    """
    phrases = []

    # Strip "by Maker (City, Date)" attribution — the maker is NOT the subject
    cleaned = re.sub(r'\s*by\s+.+$', '', stop_title)
    cleaned = re.sub(r'\s*\(.+\)$', '', cleaned)  # Remove parenthetical

    # For "X ou la Y" pattern, the Y part is the description
    m = re.match(r'^(.+?)\s+ou\s+la\s+(.+)$', stop_title, re.IGNORECASE)
    if m:
        phrases.append(m.group(1))  # artist name
        phrases.append(m.group(2))  # description

    # For "Le/La X" patterns
    m = re.match(r"^(?:Le|La|Les|L['\u2019])\s*(.+?)(?:\s+d['\u2019].+)?$", stop_title, re.IGNORECASE)
    if m:
        phrases.append(stop_title)  # Full title
        inner = m.group(1)
        if len(inner) > 3:
            phrases.append(inner)

    # For "X, date" patterns
    m = re.match(r'^(.+?),\s+(?:séance\s+)?\d', stop_title)
    if m:
        phrases.append(m.group(1))

    # Key multi-word phrases from the CLEANED title (3+ char words, consecutive pairs)
    # Use cleaned (no maker attribution) to avoid treating maker name as subject
    words = [w for w in cleaned.split() if len(w) >= 3]
    for i in range(len(words) - 1):
        phrase = f"{words[i]} {words[i+1]}"
        if len(phrase) >= 8:
            phrases.append(phrase)

    # Always include the full title itself
    if stop_title not in phrases:
        phrases.append(stop_title)

    # For specific known works, add their distinctive elements
    specific_map = {
        "Le Mur de Feu d'Yves Klein": ["Mur de Feu", "mur de feu", "Peinture de feu",
                                         "peinture de feu", "becs Bunsen"],
        "Le Village de grand-mère": ["Village de grand-mère", "village de grand"],
        "Le Déjeuner sur l'herbe": ["Déjeuner sur l'herbe"],
        "She-Bam Pow POP Wizz": ["She-Bam", "Pow POP"],
        "Tir, séance 26 juin 1961": ["Tir", "shooting", "tirs"],
        "La mariée sous l'arbre": ["mariée sous l'arbre", "mariee"],
        "Richard Long ou la sculpture en marchant": ["sculpture en marchant"],
    }
    phrases.extend(specific_map.get(stop_title, []))

    return [p for p in phrases if len(p) >= 3]


def _is_about_creator(text_norm: str, text_lower: str, artist: str, stop_title: str) -> bool:
    """Check if a passage is biographical content about the creator."""
    artist_norm = normalize(artist)
    artist_surname = artist_norm.split()[-1]

    # The passage must prominently feature the artist
    pattern = r'\b' + re.escape(artist_surname) + r'\b'
    surname_count = len(re.findall(pattern, text_norm))
    if surname_count < 1:
        return False

    # Biographical indicators
    bio_signals = [
        r'\bborn\b', r'\bne\s+le\b', r'\bne\s+en\b', r'\b\d{4}\b.*\b\d{4}\b',
        r'\bpractice\b', r'\bcareer\b', r'\bwork(?:ed|s)\b.*\b(?:art|sculpt|paint)',
        r'\bstyle\b', r'\binfluence', r'\bearly life\b', r'\beducation\b',
        r'\bstudied\b', r'\bcommission', r'\bexhibit',
        r'\bartist\b', r'\bsculptor\b', r'\bpainter\b', r'\bpeintre\b',
        r'\bsculpteur\b', r'\bartiste\b', r'\bluthier\b', r'\bmaker\b',
        r'\bharpist\b', r'\bcomposer\b',
    ]
    bio_hits = sum(1 for s in bio_signals if re.search(s, text_lower))

    # Strong bio: artist name prominent + biographical language
    if surname_count >= 2 and bio_hits >= 2:
        return True
    if surname_count >= 1 and bio_hits >= 3:
        return True

    # Lead-paragraph pattern: "X (born...) is a Y"
    if re.search(r'\b' + re.escape(artist_surname) + r'\b.*\b(is|was|est)\s+(a|an|un|une)\b', text_norm):
        return True

    return False


def _is_place_stop(stop_title: str, venue_name: str) -> bool:
    """Check if this is a geographic/place stop (walking tour)."""
    venue_lower = venue_name.lower()
    if 'walking' in venue_lower or 'riviera' in venue_lower:
        return True
    # Place indicators in title
    place_words = ['beach', 'plage', 'village', 'cap', 'port', 'harbour',
                   'castle', 'chateau', 'garden', 'jardin', 'square', 'place',
                   'hill', 'colline', 'bay', 'baie', 'island', 'ile']
    title_lower = stop_title.lower()
    return any(w in title_lower for w in place_words)


def _passage_mentions_place(text_norm: str, stop_title: str) -> bool:
    """Check if a passage mentions the place referenced in the stop title."""
    # Extract place name words
    title_norm = normalize(stop_title)
    words = [w for w in title_norm.split() if len(w) >= 3]
    noise = {'the', 'les', 'des', 'beach', 'plage', 'village', 'cap',
             'port', 'old', 'town'}
    content = [w for w in words if w not in noise]

    if not content:
        return True  # Can't check, assume valid

    # At least one distinguishing word from the place name
    for w in content:
        pattern = r'\b' + re.escape(w) + r'\b'
        if re.search(pattern, text_norm):
            return True
    return False


def _is_maker_bio(text_norm: str, text_lower: str, stop_title: str) -> bool:
    """Check if a passage is a maker/luthier biography for an instrument stop."""
    maker_signals = ['luthier', 'harpist', 'composer', 'maker', 'builder',
                     'craftsman', 'workshop', 'atelier', 'facteur',
                     'born', 'died', 'né', 'mort']
    return sum(1 for s in maker_signals if s in text_lower) >= 2


def _passage_names_this_instrument(text_norm: str, stop_title: str) -> bool:
    """Check if a collection-listing passage explicitly names this instrument.

    For Palais Lascaris instruments with titles like
    "Guitare baroque by René Voboam (Paris, 1650)",
    check if the passage mentions the maker's surname AND the instrument type.
    """
    # Extract maker surname from "X by Maker (City, Date)" pattern
    m = re.match(r'.+\s+by\s+(.+?)(?:\s*\(.+\))?$', stop_title)
    if not m:
        return False

    maker_name = m.group(1).strip()
    # Get surname (last word that's not a city in parens)
    maker_words = maker_name.split()
    if not maker_words:
        return False
    maker_surname = normalize(maker_words[-1])

    # Also extract the instrument type from the title
    instrument_part = re.match(r'^(.+?)\s+by\s+', stop_title)
    instrument_type = normalize(instrument_part.group(1)) if instrument_part else ''

    # Check if the passage mentions this maker
    if maker_surname and len(maker_surname) >= 4:
        pattern = r'\b' + re.escape(maker_surname) + r'\b'
        if re.search(pattern, text_norm):
            return True

    # Also check for the instrument type words
    if instrument_type:
        type_words = [w for w in instrument_type.split() if len(w) >= 4]
        if type_words:
            for w in type_words:
                if re.search(r'\b' + re.escape(w) + r'\b', text_norm):
                    return True

    return False


# ===========================================================================
# Main: tag all passages in stop_corpus
# ===========================================================================

def tag_all_passages(verbose: bool = True) -> Dict:
    """Tag every passage in stop_corpus with a role.

    Updates the passage_roles column (JSONB array parallel to passages_json).
    Returns a report dict.
    """
    conn = get_connection()
    cur = conn.cursor()

    # Ensure the passage_roles column exists
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'stop_corpus' AND column_name = 'passage_roles'
    """)
    if not cur.fetchone():
        cur.execute("""
            ALTER TABLE stop_corpus
            ADD COLUMN passage_roles JSONB
        """)
        conn.commit()
        if verbose:
            print("Added passage_roles column to stop_corpus")

    # Fetch all rows
    cur.execute("""
        SELECT id, venue_name, stop_title, passages_json, source_pages
        FROM stop_corpus
        ORDER BY id
    """)
    rows = cur.fetchall()

    report = {
        'rows_tagged': 0,
        'total_passages': 0,
        'roles': {'about_subject': 0, 'about_creator': 0, 'about_venue': 0, 'unclassified': 0},
        'per_stop': [],
    }

    for row in rows:
        stop_id, venue_name, stop_title, passages_json, source_pages = row

        if not passages_json:
            # Empty row — store empty roles array
            cur.execute(
                "UPDATE stop_corpus SET passage_roles = %s::jsonb WHERE id = %s",
                (json.dumps([]), stop_id)
            )
            continue

        passages = passages_json if isinstance(passages_json, list) else json.loads(passages_json)
        sources = source_pages if isinstance(source_pages, list) else (
            json.loads(source_pages) if source_pages else []
        )

        roles = []
        stop_roles_summary = {'about_subject': 0, 'about_creator': 0, 'about_venue': 0, 'unclassified': 0}

        for i, p in enumerate(passages):
            p_text = p.get('text', p) if isinstance(p, dict) else str(p)

            # Determine source for this passage (best effort)
            source_url = ""
            source_tier = None
            source_title_str = ""
            if sources:
                # Try to identify which source this passage belongs to
                for s in sources:
                    if isinstance(s, dict) and s.get('url'):
                        source_url = s.get('url', '')
                        source_tier = s.get('tier')
                        source_title_str = s.get('title', '')
                        break  # Use first enrichment source as default

            role = classify_passage_role(
                passage_text=p_text,
                stop_title=stop_title,
                venue_name=venue_name,
                source_url=source_url,
                source_title=source_title_str,
            )

            role_entry = {
                'role': role,
                'source_url': source_url,
                'tier': source_tier,
            }
            roles.append(role_entry)

            if role:
                stop_roles_summary[role] += 1
                report['roles'][role] += 1
            else:
                stop_roles_summary['unclassified'] += 1
                report['roles']['unclassified'] += 1
            report['total_passages'] += 1

        # Write roles
        cur.execute(
            "UPDATE stop_corpus SET passage_roles = %s::jsonb WHERE id = %s",
            (json.dumps(roles), stop_id)
        )
        report['rows_tagged'] += 1

        if verbose:
            print(f"  id={stop_id:3d} | {stop_title[:45]:45s} | "
                  f"subj={stop_roles_summary['about_subject']} "
                  f"creator={stop_roles_summary['about_creator']} "
                  f"venue={stop_roles_summary['about_venue']} "
                  f"unk={stop_roles_summary['unclassified']}")

        report['per_stop'].append({
            'id': stop_id,
            'stop_title': stop_title,
            'venue': venue_name,
            **stop_roles_summary,
        })

    conn.commit()
    conn.close()
    return report


if __name__ == '__main__':
    print("=" * 70)
    print("LOCAL-203: Passage Role Tagging")
    print("=" * 70)
    print()

    report = tag_all_passages(verbose=True)

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Rows tagged: {report['rows_tagged']}")
    print(f"  Total passages: {report['total_passages']}")
    print(f"  about_subject: {report['roles']['about_subject']}")
    print(f"  about_creator: {report['roles']['about_creator']}")
    print(f"  about_venue: {report['roles']['about_venue']}")
    print(f"  unclassified: {report['roles']['unclassified']}")
