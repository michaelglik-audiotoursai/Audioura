#!/usr/bin/env python3
"""test_local219_corpus_wide.py — Corpus-wide CONTRADICTED measurement.

Methodology:
1. For each tour with content, match it to a venue corpus by name.
2. Split tour content into paragraphs (skip metadata lines).
3. For each paragraph, gather the venue's stop_corpus passages (all stops)
   as the corpus pool.
4. Run check_paragraph and collect all CONTRADICTED verdicts.
5. Report per-verdict counts and quote every CONTRADICTED with evidence.

This is the measurement LEAD ran: stored tours against their venue corpora.
"""

import sys
import os
import json
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

import claim_check
from db_connection import get_connection


# ─── Tour-to-venue matching ──────────────────────────────────────────────────
# Manual mapping based on known tour names → venue_corpus names.
# This is explicit rather than fuzzy to avoid wrong matches.

TOUR_VENUE_MAP = {
    # Museum tours
    'Palais Lascaris': 'Palais Lascaris, Nice',
    'Musée Matisse': 'Musee Matisse, Nice, France',
    'Matisse': 'Musee Matisse, Nice, France',
    'MAMAC': 'Musee d Art Moderne et d Art Contemporain, Nice, France',
    'Art Moderne': 'Musee d Art Moderne et d Art Contemporain, Nice, France',
    'Chagall': 'Musee National Marc Chagall, Nice, France',
    'Marc Chagall': 'Musee National Marc Chagall, Nice, France',
    'Naïf': 'Musée International d\'Art Naïf Anatole Jakovsky, Nice',
    'Naif': 'Musée International d\'Art Naïf Anatole Jakovsky, Nice',
    'Naïve': 'Musée International d\'Art Naïf Anatole Jakovsky, Nice',
    'Beaux-Arts': 'Musee des Beaux-Arts Jules Cheret, Nice, France',
    'Jules Cheret': 'Musee des Beaux-Arts Jules Cheret, Nice, France',
    'Picasso': 'Musee Picasso, Antibes, France',
    'Massena': 'Musee Massena, Nice, France',
    'Oceanographique': 'Musee Oceanographique de Monaco, Monaco',
    # Walking/cycling tours
    'French Riviera': 'French Riviera walking area',
    'Riviera': 'French Riviera walking area',
    'Nice France walking': 'Nice walking area',
    'Nice walking': 'Nice walking area',
    'Boston Common': 'Boston Common walking area',
    'Jamaica Pond': 'Jamaica Pond walking area',
    'Arnold Arboretum': 'Arnold Arboretum walking area',
    'Fort du Mont Alban': 'Fort du Mont Alban walking area',
    'Cathédrale Saint-Nicolas': 'Cathédrale Saint-Nicolas walking area',
    'Saint-Nicolas': 'Cathédrale Saint-Nicolas walking area',
}


def match_tour_to_venue(tour_name):
    """Match a tour name to a venue corpus name."""
    for key, venue in TOUR_VENUE_MAP.items():
        if key.lower() in tour_name.lower():
            return venue
    return None


def split_paragraphs(tour_text):
    """Split tour text into meaningful paragraphs."""
    lines = tour_text.split('\n')
    paragraphs = []
    current = []

    skip_prefixes = [
        'Step-by-Step', 'Tour-Category:', 'Stop ', 'Address:',
        'Coordinates:', 'Museum Information:', 'Directions:',
        'Type/Specialty:', 'Specific Examples:', 'Orientation:',
        'Sources:', 'Description:',
    ]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                para = ' '.join(current)
                if len(para) > 50:
                    paragraphs.append(para)
                current = []
        elif any(stripped.startswith(p) for p in skip_prefixes):
            # Include content after the prefix
            after_prefix = stripped
            for p in skip_prefixes:
                if stripped.startswith(p):
                    after_prefix = stripped[len(p):].strip()
                    if after_prefix.startswith(':'):
                        after_prefix = after_prefix[1:].strip()
                    break
            if after_prefix and len(after_prefix) > 50:
                if current:
                    para = ' '.join(current)
                    if len(para) > 50:
                        paragraphs.append(para)
                    current = []
                paragraphs.append(after_prefix)
            elif current:
                para = ' '.join(current)
                if len(para) > 50:
                    paragraphs.append(para)
                current = []
        else:
            current.append(stripped)

    if current:
        para = ' '.join(current)
        if len(para) > 50:
            paragraphs.append(para)

    return paragraphs


def get_venue_passages(conn, venue_name):
    """Get all passages for a venue from stop_corpus + venue_corpus."""
    cur = conn.cursor()
    passages = []

    # Stop corpus passages
    cur.execute(
        "SELECT passages_json FROM stop_corpus WHERE venue_name = %s",
        (venue_name,)
    )
    for row in cur.fetchall():
        data = row[0]
        if isinstance(data, str):
            data = json.loads(data)
        for p in data:
            text = p.get('text', '') if isinstance(p, dict) else str(p)
            if text and len(text) > 20:
                passages.append(text)

    # Venue corpus (pages_json) — only if it has real text passages
    cur.execute(
        "SELECT pages_json FROM venue_corpus WHERE venue_name = %s",
        (venue_name,)
    )
    row = cur.fetchone()
    if row:
        data = row[0]
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, list):
            for p in data:
                text = p.get('text', '') if isinstance(p, dict) else str(p)
                if text and len(text) > 20:
                    passages.append(text)

    cur.close()
    return passages


def main():
    conn = get_connection()
    cur = conn.cursor()

    # Get all tours with content
    cur.execute(
        "SELECT id, tour_name, tour_content FROM audio_tours "
        "WHERE tour_content IS NOT NULL ORDER BY id"
    )
    tours = cur.fetchall()

    print("=" * 70)
    print("LOCAL-219 CORPUS-WIDE CONTRADICTED MEASUREMENT")
    print("=" * 70)
    print()
    print(f"Tours with content: {len(tours)}")

    # Match tours to venues
    matched_tours = []
    for tid, tname, tcontent in tours:
        venue = match_tour_to_venue(tname)
        if venue:
            matched_tours.append((tid, tname, venue, tcontent))

    print(f"Tours matched to venue corpus: {len(matched_tours)}")
    print()

    # Run check_paragraph on all paragraphs
    total_paragraphs = 0
    total_claims = 0
    verdict_totals = {
        'SUPPORTED_PARAPHRASE': 0,
        'SUPPORTED_ELSEWHERE': 0,
        'UNSUPPORTED': 0,
        'CONTRADICTED': 0,
        'NOT_CHECKABLE': 0,
    }
    contradictions = []  # (tour_id, tour_name, claim_text, evidence)

    for tid, tname, venue, tcontent in matched_tours:
        passages = get_venue_passages(conn, venue)
        if not passages:
            continue

        paragraphs = split_paragraphs(tcontent)
        total_paragraphs += len(paragraphs)

        for para in paragraphs:
            result = claim_check.check_paragraph(
                para, '', venue, passages
            )
            total_claims += len(result['claims'])
            for c in result['claims']:
                v = c['verdict']
                if v in verdict_totals:
                    verdict_totals[v] += 1
                if v == 'CONTRADICTED':
                    contradictions.append((
                        tid, tname, c['text'], c['evidence']
                    ))

    print(f"Paragraphs checked: {total_paragraphs}")
    print(f"Total claims extracted: {total_claims}")
    print()
    print("Per-verdict counts:")
    for v, count in verdict_totals.items():
        print(f"  {v}: {count}")
    print()
    print(f"CONTRADICTED rate: {verdict_totals['CONTRADICTED']} of {total_claims} claims")
    print()

    if contradictions:
        print("=" * 70)
        print("EVERY CONTRADICTED VERDICT (quoted with evidence):")
        print("=" * 70)
        for tid, tname, claim_text, evidence in contradictions:
            print(f"\n  Tour {tid}: {tname[:50]}")
            print(f"  CLAIM: {claim_text[:100]}")
            print(f"  EVIDENCE: {evidence[:150]}")
        print()
    else:
        print("  No CONTRADICTED verdicts across corpus. ✓")
        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Corpus-wide CONTRADICTED: {verdict_totals['CONTRADICTED']}")
    print(f"  Total paragraphs: {total_paragraphs}")
    print(f"  Total claims: {total_claims}")
    print()

    conn.close()
    return verdict_totals['CONTRADICTED']


if __name__ == '__main__':
    sys.exit(0 if main() == 0 else 1)
