"""corpus_source_quality.py — LOCAL-328: Corpus source quality measurement and sludge detection.

Measures passage yield by source type, scores corpus by source quality,
and structurally detects sludge passages (directory listings, keyword blobs,
signage fragments) without relying on phrase blocklists.

Design constraints:
- No rows deleted from stop_corpus (mark/score only).
- No phrase blocklist (D236: structural signals only).
- passage_count as quality signal must be replaced by source-weighted scoring.
"""
import json
import re
import sys
import os

# Add parent dir so tests/db_connection.py resolves
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))
from db_connection import get_connection


# ─── Structural sludge detection ─────────────────────────────────────────────
#
# A "sludge" passage is one that carries zero extractable facts despite being
# counted toward passage_count.  We detect these structurally:
#
# Signal 1: FRAGMENT DENSITY — directory listings and keyword blobs have many
#   sentence fragments separated by punctuation (·, |, ..., •) but few
#   complete sentences (subject-verb-object).  We measure the ratio of
#   delimiter characters to word count.
#
# Signal 2: ELLIPSIS DENSITY — scraped snippets from search-engine result pages
#   are stitched fragments joined by "..." — three or more ellipses in under
#   200 chars is a search result page artifact, not authored text.
#
# Signal 3: CURLY BRACE / STRUCTURED DATA — passages containing { } are
#   metadata blobs from scraped JSON-LD or template markup that leaked
#   through extraction.  No authored prose contains bare curly braces.
#
# Signal 4: LOW INFORMATION DENSITY — very short passages (< 60 chars after
#   trimming whitespace) that also lack a verb are signage ("Restaurant Name ·
#   City · $$") rather than factual text.
#
# These four signals combined identify sludge without needing to enumerate
# specific phrases like "restaurants near me" — that phrase triggers because
# it is a directory listing (Signal 1), not because we hardcoded it.


def _count_delimiters(text: str) -> int:
    """Count fragment-separator characters: · | • … and isolated ... """
    count = 0
    count += text.count('·')
    count += text.count('|')
    count += text.count('•')
    count += text.count('…')
    # Count runs of 3+ dots (search snippet joins)
    count += len(re.findall(r'\.{3,}', text))
    # Count " ... " (space-padded ellipsis, common in scraped snippets)
    count += len(re.findall(r'\s\.\.\.[\s]', text))
    return count


def _count_complete_sentences(text: str) -> int:
    """Count sentences that end with proper punctuation and have 4+ words."""
    # Split on sentence-ending punctuation
    sentences = re.split(r'[.!?]+', text)
    complete = 0
    for s in sentences:
        words = s.strip().split()
        if len(words) >= 4:
            complete += 1
    return complete


def is_sludge(text: str) -> tuple:
    """Determine if a passage is sludge based on structural signals.

    Returns (is_sludge: bool, reason: str).
    """
    if not text or not text.strip():
        return (True, "empty")

    text = text.strip()
    word_count = len(text.split())

    # Signal 3: Curly braces (structured data / template leak)
    if '{' in text and '}' in text:
        # Must be actual template data, not a quote containing braces
        brace_content = re.findall(r'\{[^}]+\}', text)
        if brace_content:
            # Check if it looks like metadata: comma-separated keywords
            for bc in brace_content:
                if ',' in bc and len(bc.split(',')) >= 3:
                    return (True, "structured_data_leak")

    # Signal 4: Very short + fragment markers + low word count
    # These are category tags from directories: "Nice · Restaurants · $$$"
    if len(text) < 60:
        has_fragment_markers = _count_delimiters(text) >= 1
        word_count_local = len(text.split())
        if has_fragment_markers and word_count_local <= 6:
            return (True, "fragment_too_short")

    # Signal 1: Fragment density — many delimiters relative to words
    delimiters = _count_delimiters(text)
    if word_count > 0:
        delimiter_ratio = delimiters / word_count
        # Threshold: > 1 delimiter per 8 words with at least 3 delimiters
        if delimiters >= 3 and delimiter_ratio > 0.12:
            return (True, "directory_listing")

    # Signal 2: Ellipsis density — many "..." joins in short text
    ellipsis_count = len(re.findall(r'\.\.\.', text))
    if ellipsis_count >= 3 and len(text) < 250:
        return (True, "search_snippet_collage")

    # Signal 2b: Leading ellipsis (truncated snippet start)
    if text.startswith('...') or text.startswith('…'):
        # Only flag if also has other snippet markers
        if ellipsis_count >= 2 or delimiters >= 2:
            return (True, "truncated_snippet")

    # Signal 5: ENUMERATION INDEX — directory/listing pages contain bare
    # enumeration indices (digits followed by a period or parenthesis) in the
    # middle of what should be prose.  "11. La ..." or "(3)" within a passage
    # whose first segment is a dash-separated breadcrumb trail is a listing.
    #
    # The structural pattern is: Name - [words] - Place[, Region]. \d+\.
    # This catches venue directory pages regardless of what category words
    # they use ("Restaurants near me", "Hotels", "Things to do").
    if ' - ' in text:
        dash_segments = text.split(' - ')
        if len(dash_segments) >= 3:
            # 3+ dash-separated segments = breadcrumb navigation pattern
            # Check for enumeration index anywhere in the text
            has_enum_index = bool(re.search(r'\b\d{1,3}\.\s', text))
            if has_enum_index:
                return (True, "directory_breadcrumb_listing")

        # Even with 2 dash segments, if there's an enumeration index AND the
        # text is relatively short, it's a listing entry
        if len(dash_segments) >= 2:
            has_enum_index = bool(re.search(r'\b\d{1,3}\.\s', text))
            # Also check for trailing "..." (truncated listing entry)
            ends_truncated = text.rstrip().endswith('...')
            if has_enum_index and ends_truncated and len(text) < 200:
                return (True, "directory_breadcrumb_listing")

    return (False, "")


def classify_passage(passage) -> dict:
    """Classify a single passage element from passages_json.

    Returns dict with: source_type, text, is_sludge, sludge_reason, char_len
    """
    if isinstance(passage, str):
        text = passage
        source_type = "bare_string"
    elif isinstance(passage, dict):
        text = passage.get('text', '')
        source_type = passage.get('type') or passage.get('source') or 'object_no_type'
    else:
        text = str(passage)
        source_type = "unknown"

    sludge, reason = is_sludge(text)

    return {
        'source_type': source_type,
        'text': text,
        'is_sludge': sludge,
        'sludge_reason': reason,
        'char_len': len(text),
    }


def compute_quality_score(passages_classified: list) -> float:
    """Compute a quality score for a stop based on classified passages.

    Score = weighted sum of non-sludge passages by source type.
    This replaces raw passage_count as a quality signal.

    Weights reflect measured fact yield per passage type:
    - museum_official: 3.0 (dense catalogue facts)
    - wikipedia: 2.5 (reliable, structured)
    - external_verified: 2.0 (URL-verified claims)
    - bare_string / object_no_type: 1.5 (museum page scrapes, untyped)
    - web_search: 0.5 (only useful if non-sludge, and even then low-density)
    - heritage / museum_site / museum_partner: 2.0
    """
    SOURCE_WEIGHTS = {
        'museum_official': 3.0,
        'wikipedia': 2.5,
        'external_verified': 2.0,
        'bare_string': 1.5,
        'object_no_type': 1.5,
        'heritage': 2.0,
        'museum_site': 2.0,
        'museum_partner': 2.0,
        'web_search': 0.5,
    }

    score = 0.0
    for p in passages_classified:
        if p['is_sludge']:
            continue  # sludge contributes nothing
        weight = SOURCE_WEIGHTS.get(p['source_type'], 1.0)
        score += weight
    return round(score, 2)


def measure_corpus(conn) -> dict:
    """Measure the full stop_corpus: yield per type, sludge rate, quality scores.

    Returns a comprehensive measurement dict.
    """
    cur = conn.cursor()
    cur.execute("SELECT id, venue_name, stop_title, passages_json, passage_count FROM stop_corpus")
    rows = cur.fetchall()
    cur.close()

    # Per-type aggregations
    type_stats = {}  # source_type -> {total, sludge, useful, total_chars}
    # Per-stop quality
    stop_scores = []

    for row in rows:
        row_id, venue_name, stop_title, passages_json_raw, passage_count = row
        if isinstance(passages_json_raw, str):
            passages = json.loads(passages_json_raw)
        else:
            passages = passages_json_raw

        classified = [classify_passage(p) for p in (passages or [])]
        quality_score = compute_quality_score(classified)

        stop_scores.append({
            'id': row_id,
            'venue_name': venue_name,
            'stop_title': stop_title,
            'passage_count': passage_count,
            'quality_score': quality_score,
            'total_passages': len(classified),
            'sludge_count': sum(1 for p in classified if p['is_sludge']),
            'useful_count': sum(1 for p in classified if not p['is_sludge']),
        })

        for p in classified:
            st = p['source_type']
            if st not in type_stats:
                type_stats[st] = {'total': 0, 'sludge': 0, 'useful': 0, 'total_chars': 0}
            type_stats[st]['total'] += 1
            if p['is_sludge']:
                type_stats[st]['sludge'] += 1
            else:
                type_stats[st]['useful'] += 1
                type_stats[st]['total_chars'] += p['char_len']

    return {
        'type_stats': type_stats,
        'stop_scores': stop_scores,
        'total_rows': len(rows),
    }


def print_yield_table(measurement: dict):
    """Print the yield-per-source-type table."""
    print("\n" + "=" * 78)
    print("PASSAGE YIELD BY SOURCE TYPE (BEFORE filtering)")
    print("=" * 78)
    print(f"{'Source Type':<20} {'Total':>6} {'Sludge':>7} {'Useful':>7} {'Sludge%':>8} {'Avg Len':>8}")
    print("-" * 78)

    type_stats = measurement['type_stats']
    for st in sorted(type_stats.keys(), key=lambda k: type_stats[k]['total'], reverse=True):
        s = type_stats[st]
        sludge_pct = (s['sludge'] / s['total'] * 100) if s['total'] > 0 else 0
        avg_len = (s['total_chars'] / s['useful']) if s['useful'] > 0 else 0
        print(f"{st:<20} {s['total']:>6} {s['sludge']:>7} {s['useful']:>7} {sludge_pct:>7.1f}% {avg_len:>8.0f}")

    total_passages = sum(s['total'] for s in type_stats.values())
    total_sludge = sum(s['sludge'] for s in type_stats.values())
    print("-" * 78)
    print(f"{'TOTAL':<20} {total_passages:>6} {total_sludge:>7} {total_passages - total_sludge:>7} "
          f"{(total_sludge/total_passages*100) if total_passages > 0 else 0:>7.1f}%")


def print_rossettisserie_detail(conn):
    """Show La Rossettisserie specifically: what survives filtering."""
    print("\n" + "=" * 78)
    print("LA ROSSETTISSERIE — PASSAGE DETAIL")
    print("=" * 78)

    cur = conn.cursor()
    cur.execute(
        "SELECT venue_name, stop_title, passages_json FROM stop_corpus WHERE stop_title ILIKE %s",
        ('%Rossettisserie%',)
    )
    rows = cur.fetchall()
    cur.close()

    for venue_name, stop_title, passages_json_raw in rows:
        if isinstance(passages_json_raw, str):
            passages = json.loads(passages_json_raw)
        else:
            passages = passages_json_raw

        print(f"\n  Venue: {venue_name}")
        print(f"  Stop:  {stop_title}")
        print(f"  Passages ({len(passages)}):")

        for i, p in enumerate(passages, 1):
            classified = classify_passage(p)
            status = "SLUDGE" if classified['is_sludge'] else "KEEP"
            reason = f" ({classified['sludge_reason']})" if classified['is_sludge'] else ""
            text_preview = classified['text'][:100]
            print(f"    [{status}{reason}] #{i}: {text_preview}...")

        classified_all = [classify_passage(p) for p in passages]
        survivors = [c for c in classified_all if not c['is_sludge']]
        print(f"\n  Survives filtering: {len(survivors)}/{len(passages)} passages")
        if survivors:
            print("  Surviving text:")
            for s in survivors:
                print(f"    → {s['text'][:150]}")
        else:
            print("  ⚠ ZERO passages survive — this stop genuinely lacks documentation.")


def get_quality_score_for_stop(stop_title: str, venue_name: str, conn) -> float:
    """Get the quality score for a specific stop (for use in selection/extraction)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT passages_json FROM stop_corpus WHERE stop_title = %s AND venue_name = %s",
        (stop_title, venue_name)
    )
    row = cur.fetchone()
    cur.close()

    if not row:
        return 0.0

    passages_json_raw = row[0]
    if isinstance(passages_json_raw, str):
        passages = json.loads(passages_json_raw)
    else:
        passages = passages_json_raw

    classified = [classify_passage(p) for p in (passages or [])]
    return compute_quality_score(classified)


def get_bulk_quality_scores(stop_names: list, conn) -> dict:
    """[LOCAL-349] Compute quality scores for multiple stops in one DB pass.

    Returns {stop_name: quality_score} for all stops that have corpus rows.
    Stops not found in the corpus get score 0.0.

    Uses accent-folded title matching (same as stop_corpus_reader) to handle
    accented venue names like "Acchiardo" vs "Acchiardo".

    This is the efficient path for coverage selection: one query fetches all
    rows, then we match each candidate stop to its best corpus row and score it.
    """
    import unicodedata

    def _fold(text):
        """Accent-fold + typographic quote normalization (D253, LOCAL-340)."""
        text = text.replace('\u2019', "'").replace('\u2018', "'")
        text = text.replace('\u201C', '"').replace('\u201D', '"')
        nfkd = unicodedata.normalize('NFKD', text)
        return ''.join(c for c in nfkd if not unicodedata.combining(c))

    # Fetch all corpus rows (same approach as stop_corpus_reader)
    cur = conn.cursor()
    cur.execute("SELECT stop_title, passages_json FROM stop_corpus")
    all_rows = cur.fetchall()
    cur.close()

    # Build a lookup: folded_title → best passages_json (richest)
    # When multiple rows match a title, keep the one with most passages
    title_to_passages = {}  # folded_lower_title → passages_json (raw)
    for stop_title, passages_json_raw in all_rows:
        folded = _fold(stop_title).lower().strip()
        if isinstance(passages_json_raw, str):
            try:
                passages = json.loads(passages_json_raw)
            except (json.JSONDecodeError, TypeError):
                passages = []
        else:
            passages = passages_json_raw or []

        # Keep the row with the HIGHEST quality score (LOCAL-349: passage count
        # is anti-correlated with quality per D241 — more passages ≠ better).
        if folded not in title_to_passages:
            title_to_passages[folded] = passages
        else:
            # Compare quality scores to pick the better row
            existing_classified = [classify_passage(p) for p in title_to_passages[folded]]
            existing_score = compute_quality_score(existing_classified)
            new_classified = [classify_passage(p) for p in passages]
            new_score = compute_quality_score(new_classified)
            if new_score > existing_score:
                title_to_passages[folded] = passages

    # Score each candidate stop
    scores = {}
    for name in stop_names:
        folded = _fold(name).lower().strip()
        passages = title_to_passages.get(folded)
        if passages:
            classified = [classify_passage(p) for p in passages]
            scores[name] = compute_quality_score(classified)
        else:
            scores[name] = 0.0

    return scores


def filter_passages_for_generation(passages_json: list) -> list:
    """Filter passages_json for generation: remove sludge, keep useful.

    Returns a new list with sludge passages removed. Does NOT modify the
    database — this is applied at read time (stop_corpus_reader.py).
    """
    result = []
    for p in (passages_json or []):
        classified = classify_passage(p)
        if not classified['is_sludge']:
            result.append(p)
    return result


if __name__ == '__main__':
    conn = get_connection()
    measurement = measure_corpus(conn)

    print(f"\nstop_corpus row count: {measurement['total_rows']}")
    print_yield_table(measurement)
    print_rossettisserie_detail(conn)

    # Print worst stops (highest sludge ratio)
    print("\n" + "=" * 78)
    print("STOPS WITH HIGHEST SLUDGE RATIO")
    print("=" * 78)
    stops_with_sludge = [s for s in measurement['stop_scores'] if s['sludge_count'] > 0]
    stops_with_sludge.sort(key=lambda s: s['sludge_count'] / max(s['total_passages'], 1), reverse=True)
    print(f"{'Stop Title':<30} {'Venue':<35} {'Total':>5} {'Sludge':>6} {'Score':>6}")
    print("-" * 78)
    for s in stops_with_sludge[:20]:
        venue_short = s['venue_name'][:33]
        title_short = s['stop_title'][:28]
        print(f"{title_short:<30} {venue_short:<35} {s['total_passages']:>5} {s['sludge_count']:>6} {s['quality_score']:>6.1f}")

    # Comparison: quality_score vs passage_count correlation
    print("\n" + "=" * 78)
    print("QUALITY SCORE vs PASSAGE COUNT — should now be POSITIVELY correlated")
    print("=" * 78)
    for s in sorted(measurement['stop_scores'], key=lambda x: x['quality_score'], reverse=True)[:15]:
        print(f"  {s['stop_title']:<40} passages={s['passage_count']:>2}  quality_score={s['quality_score']:>5.1f}  "
              f"(useful={s['useful_count']}, sludge={s['sludge_count']})")

    conn.close()
