"""LOCAL-411: Rank and cap search snippets before prompt injection.

A snippet earns its place by containing a *story*: a named person plus a verb
of consequence plus ideally a date. Biography-only snippets (LOCAL-406 Part B)
are rejected outright. The remaining snippets are scored and capped at
SNIPPET_CAP_PER_STOP (default 5).

Scoring:
  - Named person (proper noun pattern): +3
  - Verb of consequence (created, published, printed, commissioned, donated,
    founded, established, collaborated, met, visited, exhibited, produced,
    acquired, wrote, illustrated): +3
  - Date (4-digit year): +2
  - Named place or institution: +1
  - Tier1/Tier2 domain: +1
  - Contains artist name: +1
  - Biography-only (LOCAL-406): hard reject (score = -999)
  - [LOCAL-414] Tier3 penalty: -5 (unverified domains cannot outrank tier1/tier2
    on story quality alone; prevents doctrinal/apologetics sites from displacing
    institutional sources). Not a hard exclusion: tier3 material still available
    when no tier1/tier2 exists for a stop.

Returns at most SNIPPET_CAP_PER_STOP snippets, sorted by descending score.
"""

import re
import os
from typing import List, Dict, Tuple

# Configurable cap — default 5
SNIPPET_CAP_PER_STOP = int(os.environ.get('SNIPPET_CAP_PER_STOP', '5'))

# [LOCAL-414] Tier3 penalty: unverified domains score -5 so they cannot outrank
# tier1/tier2 material with comparable story quality. A tier1/tier2 snippet with
# person+verb+date = 9; a tier3 snippet with the same = 3 (9-6 is too harsh,
# 9-4 still allows a tier3 with ALL signals to tie). -5 means tier3 needs
# *more* story signals than tier1/tier2 to win — practically impossible when
# both have the same content, but still possible when tier3 is the ONLY source.
TIER3_PENALTY = int(os.environ.get('SNIPPET_TIER3_PENALTY', '-5'))

# Verbs of consequence — actions that indicate a story, not a description
_VERBS_OF_CONSEQUENCE = re.compile(
    r'\b(?:creat(?:ed|ing)|publish(?:ed|ing)|print(?:ed|ing)|commission(?:ed|ing)|'
    r'donat(?:ed|ing)|found(?:ed|ing)|establish(?:ed|ing)|collaborat(?:ed|ing)|'
    r'met|visit(?:ed|ing)|exhibit(?:ed|ing)|produc(?:ed|ing)|acquir(?:ed|ing)|'
    r'wrote|illustrat(?:ed|ing)|engrav(?:ed|ing)|etch(?:ed|ing)|sign(?:ed|ing)|'
    r'introduc(?:ed|ing)|assembl(?:ed|ing)|curated?|assist(?:ed|ing)|'
    r'encouraged|arrang(?:ed|ing)|dedicat(?:ed|ing)|initiat(?:ed|ing)|'
    r'design(?:ed|ing)|organiz(?:ed|ing)|invit(?:ed|ing)|persuad(?:ed|ing))\b',
    re.IGNORECASE
)

# Named person pattern: Capitalized first + last name (simple heuristic)
_NAMED_PERSON = re.compile(
    r'\b[A-Z][a-zà-ÿ]+\s+(?:de\s+|van\s+|von\s+|di\s+|le\s+|la\s+)?[A-Z][a-zà-ÿ]+\b'
)

# 4-digit year
_YEAR_PATTERN = re.compile(r'\b(1[4-9]\d{2}|20[0-2]\d)\b')

# Named place/institution indicators
_PLACE_PATTERN = re.compile(
    r'\b(?:Museum|Gallery|Atelier|Workshop|Foundation|Institute|Press|'
    r'Bibliothèque|Musée|University|Collection|Studio|École)\b',
    re.IGNORECASE
)

# Biography-only detection (imported from work_story_searcher for consistency)
_BIO_SIGNALS = [
    re.compile(r'\bborn\b.*\d{4}', re.IGNORECASE),
    re.compile(r'\(\d{4}\s*[-–—]\s*\d{4}\)', re.IGNORECASE),
    re.compile(
        r'\bwas\s+(?:a|an)\s+(?:spanish|catalan|french|italian|german|american|dutch|'
        r'belgian|swiss|austrian|russian|mexican|brazilian|british|'
        r'painter|sculptor|printmaker|artist|lithographer|ceramicist|'
        r'surrealist|cubist|abstract)\b', re.IGNORECASE
    ),
    re.compile(r'\bnationality\b', re.IGNORECASE),
    re.compile(r'\bgrew\s+up\b', re.IGNORECASE),
    re.compile(r'\bfamily\s+of\b', re.IGNORECASE),
    re.compile(r'\bchildhood\b', re.IGNORECASE),
    re.compile(r'\bearly\s+(?:life|years|career)\b', re.IGNORECASE),
]

_WORK_RESCUE_SIGNALS = [
    re.compile(r'\blivre[s]?\s+d[\'\u2019]artiste\b', re.IGNORECASE),
    re.compile(r'\blithograph(?:s|y|ie)?\b', re.IGNORECASE),
    re.compile(r'\bpublish(?:ed|er|ing)\b', re.IGNORECASE),
    re.compile(r'\bprint(?:ed|er|ing|s)\b', re.IGNORECASE),
    re.compile(r'\bedition\b', re.IGNORECASE),
    re.compile(r'\bworkshop\b', re.IGNORECASE),
    re.compile(r'\batelier\b', re.IGNORECASE),
    re.compile(r'\bcollection\b', re.IGNORECASE),
    re.compile(r'\bdonat(?:ed|ion|or)\b', re.IGNORECASE),
    re.compile(r'\bcommission(?:ed)?\b', re.IGNORECASE),
    re.compile(r'\bcollaborat(?:ed|ion|or)\b', re.IGNORECASE),
    re.compile(r'\bpatron(?:age)?\b', re.IGNORECASE),
    re.compile(r'\bexhibit(?:ed|ion)\b', re.IGNORECASE),
]


def _is_biography_only(text: str) -> bool:
    """LOCAL-406 Part B: reject biography-only snippets."""
    bio_count = sum(1 for pat in _BIO_SIGNALS if pat.search(text))
    work_count = sum(1 for pat in _WORK_RESCUE_SIGNALS if pat.search(text))
    return bio_count >= 2 and work_count == 0


def score_snippet(snippet: Dict, artist: str = '') -> int:
    """Score a single snippet for story quality.

    Returns:
      Positive score for good snippets, -999 for biography-only rejects.
    """
    text = f"{snippet.get('title', '')} {snippet.get('snippet', '')}".strip()
    if not text:
        return -999

    # Hard reject: biography-only
    if _is_biography_only(text):
        return -999

    score = 0

    # Named person: +3
    if _NAMED_PERSON.search(text):
        score += 3

    # Verb of consequence: +3
    if _VERBS_OF_CONSEQUENCE.search(text):
        score += 3

    # Date: +2
    if _YEAR_PATTERN.search(text):
        score += 2

    # Named place/institution: +1
    if _PLACE_PATTERN.search(text):
        score += 1

    # Domain tier bonus: +1
    tier = snippet.get('tier', '')
    if tier in ('tier1', 'tier2'):
        score += 1
    # [LOCAL-414] Tier3 penalty: unverified domains are demoted so they cannot
    # outrank tier1/tier2 on story quality alone. This prevents doctrinal and
    # apologetics sites from being injected as reference material.
    elif tier == 'tier3':
        score += TIER3_PENALTY

    # Contains artist surname: +1
    if artist:
        artist_surname = artist.split()[-1].lower()
        if artist_surname in text.lower():
            score += 1

    return score


def rank_and_cap_snippets(
    snippets: List[Dict],
    artist: str = '',
    cap: int = None,
) -> Tuple[List[Dict], Dict]:
    """Rank snippets by story quality and cap at top N.

    Parameters:
      snippets: list of {'title', 'snippet', 'url', 'tier'?, ...}
      artist: artist name for bonus scoring
      cap: max snippets to return (default: SNIPPET_CAP_PER_STOP)

    Returns:
      (ranked_snippets, ranking_report)
      ranking_report: {
        'input_count': int,
        'rejected_biography_only': int,
        'cap_applied': int,
        'output_count': int,
        'scores': [(snippet_title_prefix, score), ...]  # for tracing
      }
    """
    if cap is None:
        cap = SNIPPET_CAP_PER_STOP

    scored = []
    rejected_bio = 0
    tier3_demoted = 0

    for snip in snippets:
        s = score_snippet(snip, artist)
        if s == -999:
            rejected_bio += 1
        else:
            if snip.get('tier') == 'tier3':
                tier3_demoted += 1
            scored.append((s, snip))

    # Sort descending by score
    scored.sort(key=lambda x: x[0], reverse=True)

    # Cap
    capped = scored[:cap]

    # [LOCAL-414] Report how many tier3 snippets survived into the final output
    tier3_in_output = sum(1 for _, snip in capped if snip.get('tier') == 'tier3')
    tier1_tier2_in_output = sum(1 for _, snip in capped if snip.get('tier') in ('tier1', 'tier2'))

    report = {
        'input_count': len(snippets),
        'rejected_biography_only': rejected_bio,
        'tier3_demoted': tier3_demoted,
        'tier3_in_output': tier3_in_output,
        'tier1_tier2_in_output': tier1_tier2_in_output,
        'cap_applied': cap,
        'output_count': len(capped),
        'scores': [
            (s[1].get('title', '')[:50], s[0], s[1].get('tier', '')) for s in capped
        ],
    }

    return [s[1] for s in capped], report
