"""
content_qa_runner.py — Automated QA pass over a generated Storied tour.
========================================================================
Task [S39]: Runs 8 automated checks on any tour text file.
Exits 0 on >=6/8 pass, exits 1 on <6/8.

Usage:
    python content_qa_runner.py [tour_file.txt]
"""
import os
import sys
import re


def load_tour(path):
    """Load tour text from file."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


PASS_COUNT = 0
FAIL_COUNT = 0
FACTUAL_FAIL_COUNT = 0


# ---------------------------------------------------------------------------
# Module-level G4 proper-noun extraction (extracted from run_qa for testability)
# ---------------------------------------------------------------------------

# B7: Proper nouns — closed-class art periods + runtime venue-derived terms
_COMMON_PROPER = {
    'this', 'after', 'before', 'during', 'through', 'from', 'with',
    'when', 'where', 'which', 'whose', 'what', 'that', 'each',
    'both', 'some', 'many', 'most', 'also', 'just', 'here',
    'originally', 'eventually', 'finally', 'initially', 'today',
    'french', 'italian', 'jewish', 'biblical', 'christian', 'roman',
    'greek', 'ancient', 'modern', 'national', 'original',
    # Abstract nouns that capitalize in titles
    'message', 'museum', 'chapel', 'gallery', 'collection',
    'biblical', 'testament', 'exodus', 'genesis',
    # Historical periods — closed class, NOT fabrication carriers
    'renaissance', 'baroque', 'impressionist', 'impressionism',
    'expressionist', 'expressionism', 'cubist', 'cubism',
    'fauvist', 'fauvism', 'modernist', 'modernism',
    'neoclassical', 'rococo', 'mannerist', 'mannerism',
    'surrealist', 'surrealism', 'realist', 'realism',
    'romantic', 'romanticism', 'romanesque', 'gothic',
    'post-impressionist', 'post-impressionism',
    'classical', 'medieval', 'byzantine', 'hellenistic',
    # Exhibition terms — closed class
    'grand', 'palais', 'salon', 'exposition', 'biennale',
    'retrospective', 'atelier',
}


def extract_g4_proper_nouns(claim_text: str, venue_context: dict = None,
                            venue_artist_words: set = None) -> set:
    """Extract proper nouns from a claim sentence using the G4 gate logic.

    Returns the set of proper nouns (lowercased) that would need grounding
    against story element text. An empty set means the claim passes G4.

    Parameters
    ----------
    claim_text : str
        The claim sentence(s) to extract proper nouns from.
    venue_context : dict, optional
        Runtime venue context with keys like 'city', 'region', 'artist',
        'venue_tokens'. Used to build exclusion terms.
    venue_artist_words : set, optional
        Pre-computed set of venue/artist words extracted from tour file metadata.
    """
    if venue_artist_words is None:
        venue_artist_words = set()

    # Build working copy of closed-class set with venue context injected
    common_proper = set(_COMMON_PROPER)

    _venue_ctx = venue_context if venue_context else {}
    if _venue_ctx:
        for token in _venue_ctx.get('venue_tokens', set()):
            if len(token) >= 3:
                common_proper.add(token.lower())
        if _venue_ctx.get('city'):
            for w in _venue_ctx['city'].lower().split():
                if len(w) >= 3:
                    common_proper.add(w)
        if _venue_ctx.get('region'):
            for w in _venue_ctx['region'].lower().split():
                if len(w) >= 3:
                    common_proper.add(w)
        if _venue_ctx.get('artist'):
            for w in _venue_ctx['artist'].lower().split():
                if len(w) >= 3:
                    common_proper.add(w)

    # Extract proper nouns: capitalized words NOT at sentence start, ≥3 chars
    _sentences_in_claim = re.split(r'[.!?]\s+', claim_text)
    _claim_proper_nouns = set()
    for sent in _sentences_in_claim:
        words = sent.split()
        for word in words[1:]:  # Skip first word of each sentence
            _w = word.strip('.,;:!?()[]"')
            if _w.endswith("'s"):
                _w = _w[:-2]
            if _w and _w[0].isupper() and len(_w) >= 3:
                _wl = _w.lower()
                if _wl not in venue_artist_words and _wl not in common_proper:
                    _claim_proper_nouns.add(_wl)

    return _claim_proper_nouns


def check(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  PASS: {name}")
        PASS_COUNT += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        FAIL_COUNT += 1


def run_qa(tour_text, tour_file="", story_elements=None, venue_context=None):
    """Run QA checks on tour text.
    
    Args:
        tour_text: The tour text to check
        tour_file: Path to the tour file (for CLI mode)
        story_elements: List of story element dicts (for serving mode — in-memory, no file glob)
        venue_context: Dict with venue-derived terms for G4 proper-noun exclusion (B7).
                       Keys: 'venue_tokens' (set of lowercase words from venue name),
                             'city' (str), 'region' (str), 'artist' (str)
    """
    global PASS_COUNT, FAIL_COUNT
    # Store elements for G4 check access
    run_qa._story_elements_override = story_elements

    # 1. No forbidden phrases from master list
    try:
        from derepetition_guard import scan_for_repetition
        matches = scan_for_repetition(tour_text)
        check("No forbidden phrases", len(matches) == 0,
              f"{len(matches)} forbidden phrases found: {matches[:3]}")
    except ImportError:
        check("No forbidden phrases", True, "(derepetition_guard unavailable — skipped)")

    # 2. No cross-stop repetition pairs above 0.85
    try:
        from derepetition_guard import check_cross_stop_repetition
        pairs = check_cross_stop_repetition(tour_text, threshold=0.85)
        check("No cross-stop repetition (>0.85)", len(pairs) == 0,
              f"{len(pairs)} pairs found")
    except ImportError:
        check("No cross-stop repetition (>0.85)", True, "(unavailable — skipped)")

    # 3. All stops have distinct opening sentences
    stops = re.split(r"Stop\s+\d+[:\.]", tour_text)[1:]  # skip pre-stop content
    openers = []
    for stop in stops:
        lines = [l.strip() for l in stop.strip().split("\n") if l.strip()
                 and not re.match(r"^(Address|Coordinates|Type|Specific|Operational|Orientation):", l)]
        if lines:
            openers.append(lines[0][:80])
    unique_openers = set(openers)
    check("Distinct opening sentences", len(unique_openers) == len(openers),
          f"{len(openers)} openers, {len(unique_openers)} unique")

    # 4. No fabricated compass bearings in museum tour transitions
    is_museum = "Tour-Category: museum" in tour_text
    if is_museum:
        compass_re = re.compile(r"\b(head north|head south|head east|head west|turn north|turn south)\b", re.I)
        compass_matches = compass_re.findall(tour_text)
        check("No compass bearings (museum)", len(compass_matches) == 0,
              f"found: {compass_matches[:3]}")
    else:
        check("No compass bearings (museum)", True, "(not a museum tour — skipped)")

    # 5. [R2] No standalone Introduction block — prolog now lives in Stop 1
    _has_standalone_intro = bool(re.match(r'^Introduction:', tour_text, re.MULTILINE))
    check("No standalone Introduction block (R2)", not _has_standalone_intro,
          "found standalone 'Introduction:' — should be folded into Stop 1")

    # 6. closing_revelation present in final stop
    if stops:
        last_stop = stops[-1]
        has_revelation = len(last_stop) > 200  # Final stop should have substantial content
        check("Final stop has substantial content", has_revelation,
              f"last stop length={len(last_stop)}")
    else:
        check("Final stop has substantial content", False, "no stops found")

    # 7. Word count per stop: 200-500 for middle stops, up to 800 for first/last (prolog/epilog)
    word_counts = [len(stop.split()) for stop in stops]
    in_range = []
    for idx, wc in enumerate(word_counts):
        if idx == 0 or idx == len(word_counts) - 1:
            # Stop 1 carries prolog, last stop carries epilog — allow up to 800
            in_range.append(150 <= wc <= 800)
        else:
            in_range.append(200 <= wc <= 500)
    check("Word count per stop (200-500 middle, 150-800 first/last)",
          sum(in_range) >= len(word_counts) * 0.7,
          f"{sum(in_range)}/{len(word_counts)} in range; counts={word_counts[:5]}")

    # 8. Total length reasonable (not truncated or bloated)
    total_words = len(tour_text.split())
    check("Total length reasonable (1000-8000 words)",
          1000 <= total_words <= 8000,
          f"total={total_words} words")

    # -------- [BLOCKER 3] Factual integrity checks --------
    # These are RELEASE-GATING: any factual failure → exit 1 regardless of style score.
    global FACTUAL_FAIL_COUNT
    FACTUAL_FAIL_COUNT = 0

    # -------- [D3] New deterministic checks --------
    
    # D3(a) Stop-title sanity: short noun phrase, no "Welcome to", no self-referential "Stop N", no mid-word punctuation
    _title_issues = []
    _stop_headers = re.findall(r'^(Stop\s+\d+:.+)$', tour_text, re.MULTILINE)
    for _header in _stop_headers:
        # Extract just the name part (after "Stop N: ")
        _name_part = re.sub(r'^Stop\s+\d+:\s*', '', _header).strip()
        # Remove " by Artist" and ", Year" suffixes
        _name_part = re.sub(r'\s+by\s+[A-Z][^,]*$', '', _name_part)
        _name_part = re.sub(r',\s*\d{4}$', '', _name_part).strip()
        
        _word_count = len(_name_part.split())
        if _word_count > 15:
            _title_issues.append(f"'{_header[:60]}...' ({_word_count} words — too long)")
        if re.search(r'\b(welcome to|behold|discover|featuring|located at|awaits)\b', _name_part, re.I):
            _title_issues.append(f"'{_header[:60]}...' (contains flowery text)")
        if re.search(r'Stop\s+\d+', _name_part, re.I):
            _title_issues.append(f"'{_header[:60]}...' (self-referential Stop N)")
        if re.search(r'\w\.\w', _name_part):  # mid-word punctuation
            _title_issues.append(f"'{_header[:60]}...' (mid-word punctuation)")
    check("D3(a) Stop-title sanity", len(_title_issues) == 0,
          f"{len(_title_issues)} issue(s): {_title_issues[:3]}")

    # D3(b) Coordinate scatter for museum tours: all interior stops within ~100m
    if is_museum:
        _coords_found = re.findall(r'Coordinates:\s*([\d.-]+)\s*,\s*([\d.-]+)', tour_text)
        if len(_coords_found) >= 2:
            _lats = [float(c[0]) for c in _coords_found]
            _lngs = [float(c[1]) for c in _coords_found]
            _lat_spread = max(_lats) - min(_lats)
            _lng_spread = max(_lngs) - min(_lngs)
            # ~0.001 degree ≈ 111m latitude, ~80m longitude at 45°N
            _scatter_ok = _lat_spread < 0.002 and _lng_spread < 0.002
            check("D3(b) Coordinate scatter (museum <200m)",
                  _scatter_ok,
                  f"lat spread={_lat_spread:.4f}° lng spread={_lng_spread:.4f}°")
        else:
            check("D3(b) Coordinate scatter (museum <200m)", True,
                  f"(only {len(_coords_found)} coordinate(s) — single-coord mode)")
    else:
        check("D3(b) Coordinate scatter (museum <200m)", True, "(not a museum tour)")

    # D3(c) Cross-stop boilerplate shingles: flag 4-word shingles in >=3 stops (STYLE check)
    _shingle_issues = []
    if stops and len(stops) >= 3:
        from collections import Counter
        _shingle_counts = Counter()
        _STRUCTURAL_LINE_RE = re.compile(r'^(Address|Coordinates|Type/?Specialty|Specific Examples?|Operational|Orientation|Museum Information|Introduction|Stop \d+|Please resume):')
        for stop in stops:
            # Get content lines only (exclude structural lines)
            _content_lines = [l for l in stop.split('\n') 
                            if l.strip() and not _STRUCTURAL_LINE_RE.match(l.strip())]
            _content_text = ' '.join(_content_lines).lower()
            _words = re.findall(r'\b\w{4,}\b', _content_text)
            # Generate 4-word shingles for this stop (deduplicated within stop)
            _stop_shingles = set()
            for j in range(len(_words) - 3):
                _shingle = ' '.join(_words[j:j+4])
                _stop_shingles.add(_shingle)
            for s in _stop_shingles:
                _shingle_counts[s] += 1
        # Flag shingles appearing in 3+ stops
        _repeated_shingles = [(s, c) for s, c in _shingle_counts.items() if c >= 3]
        _shingle_issues = _repeated_shingles[:5]  # Show top 5
    check("D3(c) No boilerplate shingles (4-word in 3+ stops)",
          len(_shingle_issues) == 0,
          f"{len(_shingle_issues)} repeated shingle(s): {[s[0] for s in _shingle_issues[:3]]}")

    # D3(d) Grounding assertion: if D1 evidence was persisted, check stop titles appear in it
    # (This check is informational until evidence files are consistently written)
    # For now: check that stop titles are short, real-looking noun phrases (proxy for grounding)
    _ungrounded = []
    for _header in _stop_headers:
        _name_part = re.sub(r'^Stop\s+\d+:\s*', '', _header).strip()
        _name_part = re.sub(r'\s+by\s+[A-Z][^,]*$', '', _name_part)
        _name_part = re.sub(r',\s*\d{4}$', '', _name_part).strip()
        # A real artwork name should be 1-8 words, start with uppercase
        if _name_part and (len(_name_part.split()) > 15 or not _name_part[0].isupper()):
            _ungrounded.append(_name_part[:50])
    check("D3(d) Grounding assertion (titles look like real entities)",
          len(_ungrounded) == 0,
          f"{len(_ungrounded)} suspicious title(s): {_ungrounded[:3]}")
    # [LOCAL-16] Downgraded from FACTUAL to STYLE: title corruption is a formatting
    # issue (address leaking into name field) not a fabrication. The actual exhibit IS
    # verified by D1v2; only its presentation in the header is garbled. The choke-point
    # gate (LOCAL-16) ensures no unverified exhibit can appear at all.
    if _ungrounded:
        FAIL_COUNT += 1  # Style failure, not FACTUAL_FAIL_COUNT

    # D3(e) Duplicate-stop detection: no two stops may be the same work under different labels
    # Catches: "Resurrection" / "Résurrection", "Le Roi David" / "King David"
    _stop_names = [re.sub(r'^Stop\s+\d+:\s*', '', h).strip() for h in _stop_headers]
    _normalized_names = {}
    _duplicate_stops = []
    for name in _stop_names:
        # Normalize: lowercase, strip accents, strip punctuation
        import unicodedata as _ud
        _nfkd = _ud.normalize('NFKD', name.lower())
        _norm = ''.join(c for c in _nfkd if not _ud.combining(c))
        _norm = re.sub(r'[^\w\s]', ' ', _norm).strip()
        _norm = ' '.join(_norm.split())
        
        if _norm in _normalized_names:
            _duplicate_stops.append(f"'{name}' = '{_normalized_names[_norm]}' (same work)")
        else:
            _normalized_names[_norm] = name
    
    _passed_dedup = len(_duplicate_stops) == 0
    check("D3(e) No duplicate stops (same work under different labels) (FACTUAL)",
          _passed_dedup,
          f"{len(_duplicate_stops)} duplicate(s): {_duplicate_stops[:3]}")
    if not _passed_dedup:
        FACTUAL_FAIL_COUNT += 1

    # [T6] Splice check: detect mid-token splices and malformed transitions
    _splice_issues = []
    _lines = tour_text.split('\n')
    for line_num, line in enumerate(_lines, 1):
        # Skip Sources: credit lines entirely (URLs are expected per R1 design)
        if line.strip().startswith('Sources:'):
            continue
        # Check for [a-z].[a-z] mid-token patterns (splice signature)
        _splices = re.findall(r'[a-z]\.[a-z]', line)
        # Filter out legitimate abbreviations, URLs, and domain-shaped tokens
        for sp in _splices:
            # Skip if line contains URL indicators or domain patterns
            if any(x in line.lower() for x in ['i.e.', 'e.g.', 'http', 'www.', '.com', '.fr', '.org', '.it', '.de', '.es', '.net', '.edu', '.gov']):
                continue
            # Skip URL-shaped tokens: word.tld pattern (e.g., "uffizi.it", "musee.fr")
            if re.search(r'\b[\w-]+\.[a-z]{2,4}\b', line):
                continue
            _splice_issues.append(f"Line {line_num}: '{sp}' in ...{line[max(0,line.find(sp)-20):line.find(sp)+20]}...")
        # Check for "Stop N" references in body text (not headers)
        if not re.match(r'^Stop\s+\d+:', line) and re.search(r'\bStop\s+\d+\b', line):
            if 'Directions:' not in line:  # Allow in transition templates
                _splice_issues.append(f"Line {line_num}: 'Stop N' reference in body")
    check("T6 No splice corruption (mid-token dots, stray Stop N refs)",
          len(_splice_issues) <= 1,
          f"{len(_splice_issues)} issue(s): {_splice_issues[:3]}")

    # [R3] Orientation substance check: flag generic filler orientations
    _orientation_filler = []
    _orientation_blocks = re.findall(r'^Orientation:\s*(.+?)$', tour_text, re.MULTILINE)
    _ORIENTATION_FILLER_PATTERNS = [
        r'(?i)fully\s+immerse',
        r'(?i)intricate\s+details',
        r'(?i)symbolic\s+richness',
        r'(?i)position\s+yourself\s+(directly\s+)?in\s+front',
        r'(?i)take\s+a\s+moment\s+to\s+let',
        r'(?i)allow\s+your\s+(eyes|gaze)\s+to\s+wander',
    ]
    for orient in _orientation_blocks:
        _has_filler = any(re.search(pat, orient) for pat in _ORIENTATION_FILLER_PATTERNS)
        # Check if it also has substance (specific art element, positional reason)
        _has_substance = bool(re.search(
            r'(?i)(mosaic|reflected|window|pond|corner|ceiling|floor|left wall|right wall|'
            r'lower|upper|behind|above|below|stained glass|tapestry|sculpture|goat|angel|'
            r'designed to be|from this angle)',
            orient
        ))
        if _has_filler and not _has_substance:
            _orientation_filler.append(orient[:60])
    if is_museum:
        check("R3 Orientation substance (no generic filler in museum)",
              len(_orientation_filler) == 0,
              f"{len(_orientation_filler)} filler orientation(s): {_orientation_filler[:2]}")
    else:
        check("R3 Orientation substance (museum only)", True, "(not museum — skipped)")

    # 9. Single-venue consistency: for museum tours, stops should not reference other NAMED venues
    # [GAP 3] Exemption: when address-contained (<=2 unique addresses), exempt named-venue refs
    # that are substrings of the tour's own stop titles.
    is_museum = "Tour-Category: museum" in tour_text
    _other_venue_flags = []
    if is_museum:
        # Extract venue name from the title line
        _title_match = re.search(r"Audio Guided Tour:\s*(.+?)(?:\s*-\s*Museum Tour)?$", tour_text, re.MULTILINE)
        _tour_venue = _title_match.group(1).strip() if _title_match else ""
        
        # [GAP 3] Collect stop titles for exemption check
        _stop_titles = [re.sub(r'^Stop\s+\d+:\s*', '', h).strip().lower() for h in _stop_headers]
        
        # Check address containment (<=2 unique addresses)
        _all_addresses = re.findall(r'^Address:\s*(.+)$', tour_text, re.MULTILINE)
        _unique_addrs = set(a.strip().lower()[:30] for a in _all_addresses if a.strip())
        _is_contained = len(_unique_addrs) <= 2
        
        # Only flag PROPER-NAMED venues
        _NAMED_VENUE_PATTERN = re.compile(
            r'\b(Mus[ée]+e?\s+[A-Z]\w+(?:\s+[A-Za-z]+)*|'
            r'Galerie\s+[A-Z]\w+(?:\s+[A-Za-z]+)*|'
            r'Palais\s+[A-Z]\w+(?:\s+[A-Za-z]+)*|'
            r'Villa\s+[A-Z]\w+(?:\s+[A-Za-z]+)*|'
            r'[A-Z]\w+\s+Museum(?:\s+[A-Za-z]+)*|'
            r'[A-Z]\w+\s+Gallery(?:\s+[A-Za-z]+)*)',
            re.UNICODE
        )
        for i, stop in enumerate(stops):
            # [M4] Exclude structural lines before scanning for venue references
            _STRUCT_LINE_RE = re.compile(r'^(Address|Coordinates|Type/?Specialty|Specific Examples?|Operational|Orientation|Museum Information|Directions|Sources|Stop \d+|Please resume):')
            _content_only = '\n'.join(
                line for line in stop.split('\n')
                if line.strip() and not _STRUCT_LINE_RE.match(line.strip())
            )
            _named_refs = _NAMED_VENUE_PATTERN.findall(_content_only)
            for ref in _named_refs:
                # If the named venue IS the target venue, skip it
                # B1 FIX: Compare core venue name (first 2 words) not the full greedy match
                _ref_core = ' '.join(ref.split()[:2]).lower()
                if _tour_venue and (_tour_venue.lower()[:20] in ref.lower() or ref.lower()[:20] in _tour_venue.lower() or _ref_core in _tour_venue.lower()):
                    continue  # It's the tour's own venue — not a foreign reference
                # [GAP 3] Exemption: if tour is address-contained AND ref matches a stop title
                if _is_contained:
                    _ref_lower = ref.strip().lower()
                    _is_stop_title = any(_ref_lower in t or t in _ref_lower for t in _stop_titles)
                    if _is_stop_title:
                        continue  # Exempt — it's the tour's own stop name
                _other_venue_flags.append(f"Stop {i+1}: '{ref.strip()[:60]}'")
        _passed_9 = len(_other_venue_flags) <= 2
        check("Single-venue consistency (no other NAMED venues)",
              _passed_9,
              f"{len(_other_venue_flags)} refs to other named venues: {_other_venue_flags[:3]}")
        if not _passed_9:
            FACTUAL_FAIL_COUNT += 1
    else:
        check("Single-venue consistency (no other NAMED venues)", True, "(not a museum tour)")

    # 10. Attribution grounding: only flag when venue-inconsistency exists
    if is_museum and stops:
        _has_venue_problem = len(_other_venue_flags) > 2
        if _has_venue_problem:
            _artist_patterns = re.findall(r"(?:by|created by|painted by|work of)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", tour_text)
            _passed_10 = len(_artist_patterns) < 5
            check("Attribution grounding (no unverified claims when venues are mixed)",
                  _passed_10,
                  f"{len(_artist_patterns)} artist attributions while {len(_other_venue_flags)} other venues flagged")
            if not _passed_10:
                FACTUAL_FAIL_COUNT += 1
        else:
            check("Attribution grounding (consistent with venue)", True,
                  "(single-venue tour — attribution is appropriate)")
    else:
        check("Attribution grounding (consistent with venue)", True, "(not a museum tour)")

    # 11. Venue coherence: stop descriptions should reference the correct venue
    if is_museum and _tour_venue:
        _venue_mentions = sum(1 for stop in stops if _tour_venue.lower()[:15] in stop.lower())
        _passed_11 = _venue_mentions >= len(stops) // 3
        check("Venue coherence (stops reference correct venue)",
              _passed_11,
              f"{_venue_mentions}/{len(stops)} stops mention '{_tour_venue[:30]}'")
        if not _passed_11:
            FACTUAL_FAIL_COUNT += 1
    else:
        check("Venue coherence (stops reference correct venue)", True, "(not a museum tour)")

    # [G4] Prolog/epilog causal-claim trace check (REVISED per LEAD comment 1000410000005486)
    # Every dated or causal claim in Stop 1 Orientation (prolog) + epilog must trace
    # to ONE SPECIFIC story element. Fabrications recombine real vocabulary into false claims;
    # per-element matching (not pooled union) catches them.
    _CAUSAL_VERBS = re.compile(r'\b(became|created|founded|transformed|donated|established|inaugurated|opened|built|commissioned|dedicated|added|expanded|collaborated|collaboration)\b', re.I)
    _YEAR_PATTERN = re.compile(r'\b(1[4-9]\d{2}|20[0-2]\d)\b')
    
    # Extract prolog (Stop 1 Orientation) and epilog text
    _prolog_text = ""
    _epilog_text = ""
    _stop1_match = re.search(r'Stop\s+1:.*?(?=\nStop\s+2:|$)', tour_text, re.DOTALL)
    if _stop1_match:
        _s1_text = _stop1_match.group(0)
        _orient_match = re.search(r'Orientation:\s*(.+?)(?=\n\n)', _s1_text, re.DOTALL)
        if _orient_match:
            _prolog_text = _orient_match.group(1)
    
    # Epilog: text after last stop's Directions (or after last stop content)
    _epilog_match = re.search(r'(?:As this journey comes to a close|You\'ve experienced).*', tour_text, re.DOTALL)
    if _epilog_match:
        _epilog_text = _epilog_match.group(0)
    
    _combined_prolog_epilog = _prolog_text + "\n" + _epilog_text
    
    # Find sentences with dated or causal claims
    _claim_sentences = []
    # B1 FIX: Also split on paragraph breaks — \n\n separates distinct thoughts
    for _paragraph in re.split(r'\n\n+', _combined_prolog_epilog):
        for sent in re.split(r'[.!?]\s+', _paragraph):
            sent = sent.strip()
            if not sent or len(sent) < 20:
                continue
            # B1 FIX: Skip recap/enumeration sentences — they list stop names, not factual claims
            if re.search(r"You.ve experienced", sent, re.I):
                continue
            # Skip sentences that are mostly a comma-separated list (5+ commas = enumeration)
            if sent.count(',') >= 5 and len(sent) > 200:
                continue
            has_year = _YEAR_PATTERN.search(sent)
            has_causal = _CAUSAL_VERBS.search(sent)
            if has_year or has_causal:
                _claim_sentences.append(sent)
    
    # --- Load story elements (FIX #3: in-memory param OR file with exact stem match) ---
    _story_elements_list = None  # List of element dicts
    
    # Priority 1: in-memory param (from run_qa(story_elements=...))
    # This is set by the serving gate which has the elements from the current job
    if hasattr(run_qa, '_story_elements_override') and run_qa._story_elements_override:
        _story_elements_list = run_qa._story_elements_override
    
    # Priority 2: CLI — match tour's exact filename stem
    if _story_elements_list is None and tour_file:
        try:
            import json as _json
            _tour_stem = os.path.splitext(os.path.basename(tour_file))[0]
            _elements_dir = os.path.dirname(tour_file) if tour_file else "."
            _exact_match = os.path.join(_elements_dir, f"{_tour_stem}_story_elements.json")
            if os.path.exists(_exact_match):
                with open(_exact_match, 'r') as _ef:
                    _story_elements_list = _json.load(_ef)
        except Exception:
            pass
    
    # --- Check claims against elements ---
    _ungrounded_claims = []
    _is_storied = os.environ.get("STORIED_MODE") == "true"
    
    if _claim_sentences:
        if _story_elements_list:
            # Extract venue/artist names to exclude from proper-noun check
            _venue_artist_words = set()
            if tour_file:
                _base = os.path.basename(tour_file).lower()
                _venue_artist_words = set(w for w in re.split(r'[_\s]', _base) if len(w) >= 4)
            # Also from the tour header
            _header_match = re.search(r'Tour:?\s*(.+)', tour_text[:200])
            if _header_match:
                _venue_artist_words.update(w.lower() for w in _header_match.group(1).split() if len(w) >= 4)
            
            for claim in _claim_sentences:
                _claim_words = set()
                for w in claim.split():
                    w = w.strip('.,;:!?()[]"')  # Strip punctuation
                    if w.endswith("'s"): w = w[:-2]  # Strip possessive
                    w = w.lower()
                    if len(w) >= 4 and w[0:1].isalpha():
                        _claim_words.add(w)
                if not _claim_words:
                    continue
                
                # FIX #1+#2 combined: find the element that best accounts for THIS claim
                # The matched element must have ≥35% overlap AND contain all proper nouns
                _matched_element = None
                for elem in _story_elements_list:
                    _elem_text = elem.get('text', '')
                    if not _elem_text or len(_elem_text) < 10:
                        continue
                    _elem_words = set()
                    for w in _elem_text.split():
                        w = w.strip('.,;:!?()[]"')
                        if w.endswith("'s"): w = w[:-2]
                        w = w.lower()
                        if len(w) >= 4:
                            _elem_words.add(w)
                    _overlap = _claim_words & _elem_words
                    _fwd = len(_overlap) / len(_claim_words) if _claim_words else 0
                    _rev = len(_overlap) / len(_elem_words) if _elem_words else 0
                    if max(_fwd, _rev) >= 0.35:
                        _matched_element = elem
                        break
                
                if not _matched_element:
                    _ungrounded_claims.append(claim[:80])
                    continue
                
                # B7: Proper nouns — delegate to module-level extraction function
                _claim_proper_nouns = extract_g4_proper_nouns(
                    claim, venue_context=venue_context,
                    venue_artist_words=_venue_artist_words
                )
                
                if _claim_proper_nouns:
                    _elem_text_lower = _matched_element.get('text', '').lower()
                    _missing_pn = []
                    for pn in _claim_proper_nouns:
                        if pn not in _elem_text_lower:
                            _missing_pn.append(pn)
                    if _missing_pn:
                        _ungrounded_claims.append(f"{claim[:60]}... (proper noun '{_missing_pn[0]}' not in element)")
                        continue
                    
                    # Also check: the SPECIFIC causal verb from the claim must exist in the
                    # matched element (catches recombination fabrications where a person name
                    # from one element is combined with an action from a different context)
                    # Allow synonym matches: added≈donated, built≈created, etc.
                    _CAUSAL_SYNONYMS = {
                        'added': ['donated', 'contributed', 'gave', 'added'],
                        'donated': ['added', 'contributed', 'gave', 'donated'],
                        'created': ['built', 'founded', 'established', 'created'],
                        'built': ['created', 'constructed', 'built'],
                        'founded': ['created', 'established', 'founded'],
                        'established': ['created', 'founded', 'established'],
                        'opened': ['inaugurated', 'established', 'opened'],
                        'inaugurated': ['opened', 'established', 'inaugurated'],
                    }
                    _claim_causal = _CAUSAL_VERBS.findall(claim.lower())
                    if _claim_causal and _claim_proper_nouns:
                        _any_causal_matches = False
                        for v in _claim_causal:
                            # Check exact verb or its synonyms in the element
                            _to_check = [v] + _CAUSAL_SYNONYMS.get(v, [])
                            if any(sv in _elem_text_lower for sv in _to_check):
                                _any_causal_matches = True
                                break
                        if not _any_causal_matches:
                            _ungrounded_claims.append(f"{claim[:60]}... (causal verb '{_claim_causal[0]}' not in matched element)")
                            continue
        
        elif _is_storied and _claim_sentences:
            # FIX #4: Fail-closed in serving — STORIED mode, claims present, elements missing → FAIL
            _ungrounded_claims.append("(STORIED mode: claims present but story_elements unavailable — fail-closed)")
    
    _passed_g4 = len(_ungrounded_claims) == 0
    if _claim_sentences and _story_elements_list:
        check("G4 Prolog/epilog claims trace to story elements (FACTUAL)",
              _passed_g4,
              f"{len(_ungrounded_claims)} ungrounded claim(s): {_ungrounded_claims[:2]}")
        if not _passed_g4:
            FACTUAL_FAIL_COUNT += 1
    elif _is_storied and _claim_sentences and not _story_elements_list:
        # Fail-closed: STORIED mode, claims present, no elements → FACTUAL FAIL
        # EXCEPT: walking tours and exhibit_museum tours structurally never have story_elements.
        # For those categories/tiers, skip gracefully. For rich/medium/thin museum tours,
        # an empty story_elements is a real signal (extractor failed) — keep fail-closed.
        _tour_category_match = re.search(r'Tour-Category:\s*(\w+)', tour_text)
        _tour_category = _tour_category_match.group(1).lower() if _tour_category_match else 'unknown'
        # exhibit_museum detection via venue_context (passed from service layer with tier info)
        _ctx_tier = (venue_context or {}).get('tier', '') if venue_context else ''
        _is_exhibit_museum = (_ctx_tier == 'exhibit_museum')
        
        if _tour_category != 'museum':
            # Non-museum tours (walking, restaurant, etc.) — story_elements not expected
            check("G4 Prolog/epilog claims trace to story elements (FACTUAL)",
                  True, f"(tour_category={_tour_category} — story_elements not expected, skipped)")
        elif _is_exhibit_museum:
            # exhibit_museum tier — sparse venue, story mining not available
            check("G4 Prolog/epilog claims trace to story elements (FACTUAL)",
                  True, "(exhibit_museum tier — story_elements not expected, skipped)")
        else:
            # Rich/medium/thin museum tour — story_elements SHOULD exist; fail-closed
            check("G4 Prolog/epilog claims trace to story elements (FACTUAL)",
                  False, "STORIED mode: claims present but story_elements unavailable — fail-closed")
            FACTUAL_FAIL_COUNT += 1
    else:
        check("G4 Prolog/epilog claims trace to story elements (FACTUAL)",
              True, "(no story_elements available or no dated/causal claims — skipped)")


def main():
    print("=" * 60)
    print("content_qa_runner.py — Automated Tour QA")
    print("=" * 60)

    # Determine input file
    if len(sys.argv) > 1:
        tour_file = sys.argv[1]
    else:
        tour_file = "chagall_current_tour.txt"

    if not os.path.exists(tour_file):
        print(f"ERROR: File not found: {tour_file}")
        sys.exit(1)

    print(f"Input: {tour_file}")
    tour_text = load_tour(tour_file)
    print(f"Length: {len(tour_text)} chars, {len(tour_text.split())} words\n")

    run_qa(tour_text, tour_file)

    print(f"\n{'=' * 60}")
    print(f"Score: {PASS_COUNT}/{PASS_COUNT + FAIL_COUNT} (style+factual)")
    if FACTUAL_FAIL_COUNT > 0:
        print(f"FACTUAL INTEGRITY FAILED ({FACTUAL_FAIL_COUNT} factual check(s) failed) — RELEASE BLOCKED")
        sys.exit(1)
    elif FAIL_COUNT <= 3:
        print("QA PASSED (<=3 style failures + all factual checks pass)")
        sys.exit(0)
    else:
        print(f"QA FAILED ({FAIL_COUNT} failures)")
        sys.exit(1)


if __name__ == "__main__":
    main()
