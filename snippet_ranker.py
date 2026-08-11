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


# ─── LOCAL-419: Production-fact detection ─────────────────────────────────────
# These patterns identify snippets that contain the concrete production facts
# about a livre d'artiste or printed work: publisher, printer, edition size,
# paper type, technique. These are exactly what the tour text needs to deliver.
_PRODUCTION_FACT_PATTERNS = [
    re.compile(r'\b(?:publish(?:ed|er|ing)\s+by|publisher:?)\s+', re.IGNORECASE),
    re.compile(r'\b(?:print(?:ed|er|ing)\s+by|printer:?)\s+', re.IGNORECASE),
    re.compile(r'\b(?:edition\s+(?:of|size)|one\s+of\s+(?:only\s+)?\d+\s+copies|'
               r'numbered\s+\d+[/]\d+|limited\s+to\s+\d+)\b', re.IGNORECASE),
    re.compile(r'\b(?:drypoint|etching|aquatint|lithograph|woodcut|engraving)s?\s+'
               r'(?:on|in\s+colou?rs?\s+on)\s+', re.IGNORECASE),
    re.compile(r'\b(?:set\s+of\s+\d+|suite\s+of\s+\d+|\d+\s+(?:full\s+sheet\s+)?'
               r'(?:lithographs?|etchings?|plates?|drypoints?))\b', re.IGNORECASE),
    re.compile(r'\b(?:Arches|Japan(?:\s+paper)?|vellum|wove\s+paper|'
               r'Rives|sheepskin|parchment)\b', re.IGNORECASE),
    re.compile(r'\b(?:Tériade|Mourlot|Broder|Crommelynck|Lacourière|'
               r'Atelier|Imprimerie)\b', re.IGNORECASE),
]


def _has_production_fact_content(text: str) -> bool:
    """[LOCAL-419] Detect snippets with concrete production facts.

    Returns True if the text mentions at least 2 production-fact signals:
    publisher, printer, edition details, paper type, or named print workshop.
    A single signal (e.g. just 'lithograph') is not enough — that's too common.
    """
    matches = sum(1 for pat in _PRODUCTION_FACT_PATTERNS if pat.search(text))
    return matches >= 2


def score_snippet(snippet: Dict, artist: str = '') -> int:
    """Score a single snippet for story quality.

    Returns:
      Positive score for good snippets, -999 for biography-only rejects.

    LOCAL-412: Score *event* snippets (person + verb + date in narrative context)
    above *catalogue* snippets (auction listings, dimensions, lot numbers, prices).
    A filter that rejects nothing is not filtering — the previous scoring treated
    "Sotheby's Lot 34, Joan Miró, published 1971, $30,000" identically to
    "Picasso met Fernand Mourlot in October 1945 at his workshop."
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

    # ─── LOCAL-412: Catalogue/auction penalty ───────────────────────────────
    # Auction listings, catalogue entries, and price-sheet snippets are data,
    # not stories. They inflate scores by having person+verb+date in metadata
    # form. Penalize them so event/narrative snippets rank above.
    # [LOCAL-419] BUT: catalogue entries that name publisher/printer/edition
    # are the PRIMARY source of production facts. These are exactly what the
    # prompt needs. A catalogue snippet with "Publisher: Tériade; Printer:
    # Mourlot Frères" is more valuable than an event narrative about a
    # different exhibition. Apply penalty ONLY if no production facts present.
    _is_catalogue = _is_catalogue_snippet(text)
    _has_production_facts = _has_production_fact_content(text)
    if _is_catalogue and not _has_production_facts:
        score -= 4
    elif _is_catalogue and _has_production_facts:
        # [LOCAL-419] Production-fact catalogue entries get a BONUS — these
        # are the snippets that contain publisher, printer, edition size, medium.
        score += 3

    # ─── LOCAL-412: Event/narrative bonus ───────────────────────────────────
    # A snippet that describes a specific historical event (person did X in Y)
    # in narrative prose gets a bonus. This is what the model needs to write
    # a story — not dimensions and lot numbers.
    # [LOCAL-419] BUT: only if the event is ABOUT THE WORK, not about a
    # different exhibition or unrelated topic. Snippets about "Dalí: Disruption
    # and Devotion" (a different MFA exhibition) were outscoring actual facts
    # about "Moses and Monotheism".
    if _is_event_snippet(text):
        score += 5

    # [LOCAL-419] Production-fact bonus (non-catalogue snippets too)
    # Snippets that name the publisher, printer, edition, or medium of the work
    # get a bonus even if they aren't catalogue entries.
    if _has_production_facts and not _is_catalogue:
        score += 3

    return score


# ─── LOCAL-412: Catalogue/auction detection ───────────────────────────────────
_CATALOGUE_SIGNALS = re.compile(
    r'\b(?:lot\s+\d+|estimate[ds]?\s*[:$€£]|'
    r'(?:USD|GBP|EUR)\s*[\d,]+|'
    r'\$\s*[\d,]+|'
    r'(?:cm|mm|inches?|in\.)\s*[×x]\s*\d|'
    r'\d+\s*[×x]\s*\d+\s*(?:cm|mm|inches?|in\.)|'
    r'(?:provenance|literature|exhibited|bibliography)\s*:|'
    r'(?:Christie[\'\u2019]?s|Sotheby[\'\u2019]?s|Phillips|Bonhams|'
    r'Artcurial|Drouot|Ketterer)\b)',
    re.IGNORECASE
)

_PRICE_PATTERN = re.compile(
    r'(?:\$|€|£|USD|GBP|EUR)\s*[\d,.]+(?:\s*[-–—]\s*[\d,.]+)?',
    re.IGNORECASE
)


def _is_catalogue_snippet(text: str) -> bool:
    """Detect auction/catalogue snippets: dimensions, lot numbers, prices."""
    signals = 0
    if _CATALOGUE_SIGNALS.search(text):
        signals += 1
    if _PRICE_PATTERN.search(text):
        signals += 1
    # Multiple dimensions pattern (e.g. "38.1 × 28.2 cm")
    if re.search(r'\d+[.,]?\d*\s*[×x]\s*\d+[.,]?\d*', text):
        signals += 1
    return signals >= 1


# ─── LOCAL-412: Event/narrative detection ─────────────────────────────────────
# An event snippet has a person DOING something specific — not just being listed
# as metadata. Look for: [Person] [verb-of-action] ... [date/place] in a sentence
# that reads as prose (has connecting words, not just comma-separated fields).

_EVENT_VERBS = re.compile(
    r'\b(?:met|visited|arrived|invited|persuaded|encouraged|introduced|'
    r'began|started|opened|moved|returned|joined|left|founded|'
    r'convinced|asked|brought|took|went|came|worked|walked|'
    r'discovered|experimented|transformed|decided|agreed|'
    r'commissioned|collaborated|printed|published|created|'
    r'donated|assembled|acquired|collected|bequeathed|gifted|'
    r'wrote|illustrated|designed|produced|established)\b',
    re.IGNORECASE
)

_NARRATIVE_CONNECTORS = re.compile(
    r'\b(?:when|after|before|during|because|while|until|'
    r'who|which|that|where|then|later|finally|'
    r'in\s+(?:january|february|march|april|may|june|july|'
    r'august|september|october|november|december)|'
    r'at\s+(?:his|her|their|the)|'
    r'in\s+\d{4})\b',
    re.IGNORECASE
)


def _is_event_snippet(text: str) -> bool:
    """Detect narrative/event snippets: person + action + temporal/spatial context.

    An event snippet reads like a story: "Picasso met Mourlot in October 1945
    at his lithography workshop." A catalogue entry reads like: "Published by
    Mourlot, Paris, 1945. 40 lithographs."

    Key difference: event snippets have narrative connectors (when, after, at his,
    in October) that indicate prose flow, not just comma-separated metadata.
    """
    has_person = bool(_NAMED_PERSON.search(text))
    has_event_verb = bool(_EVENT_VERBS.search(text))
    has_narrative_flow = bool(_NARRATIVE_CONNECTORS.search(text))
    has_date = bool(_YEAR_PATTERN.search(text))

    # Strong event: person + event verb + narrative connector + date
    if has_person and has_event_verb and has_narrative_flow and has_date:
        return True

    # Moderate event: person + event verb + narrative connector (no date ok)
    if has_person and has_event_verb and has_narrative_flow:
        # But only if NOT a catalogue snippet (avoid false positives)
        if not _is_catalogue_snippet(text):
            return True

    return False


def _snippet_is_title_relevant(snippet: Dict, work_title: str) -> bool:
    """[LOCAL-415] Check if a snippet is plausibly about the given work.

    A snippet is "usable" for a stop if its text relates to the work title.
    Tier1/tier2 snippets about completely unrelated topics (Korean hanboks,
    Homeric epics) count as survivors but produce starved stops because the
    LLM cannot write about the work from irrelevant material.

    This is a lightweight heuristic, not a semantic classifier:
    - Any word from the work title (3+ chars) appearing in snippet text
    - Or snippet URL/domain matching the venue (mfa.org, etc.)
    """
    if not work_title or not snippet:
        return True  # Can't assess — assume relevant

    text = f"{snippet.get('title', '')} {snippet.get('snippet', '')}".lower()
    title_lower = work_title.lower()

    # Extract significant words from the work title (3+ chars, not stopwords)
    _stopwords = {'the', 'and', 'for', 'from', 'with', 'that', 'this', 'are', 'was', 'now'}
    title_words = [w for w in re.findall(r'\b[a-z]{3,}\b', title_lower) if w not in _stopwords]

    if not title_words:
        return True  # Title too short to assess

    # If ANY significant title word appears in snippet text, it's relevant
    for word in title_words:
        if word in text:
            return True

    return False


def rank_and_cap_snippets(
    snippets: List[Dict],
    artist: str = '',
    cap: int = None,
    work_title: str = '',
) -> Tuple[List[Dict], Dict]:
    """Rank snippets by story quality and cap at top N.

    Parameters:
      snippets: list of {'title', 'snippet', 'url', 'tier'?, ...}
      artist: artist name for bonus scoring
      cap: max snippets to return (default: SNIPPET_CAP_PER_STOP)
      work_title: the canonical title of the work this stop is about
                  (LOCAL-419 relevance scoring; LOCAL-415 usability check)

    Returns:
      (ranked_snippets, ranking_report)
      ranking_report: {
        'input_count': int,
        'rejected_biography_only': int,
        'cap_applied': int,
        'output_count': int,
        'usable_count': int,           # [LOCAL-415] how many are title-relevant
        'starvation_rescued': bool,    # [LOCAL-415] whether tier3 was let through
        'scores': [(snippet_title_prefix, score, tier), ...]  # for tracing
      }
    """
    if cap is None:
        cap = SNIPPET_CAP_PER_STOP

    scored = []
    rejected_bio = 0
    tier3_demoted = 0

    # [LOCAL-419] Normalize work title for relevance check
    _work_title_lower = work_title.lower().strip() if work_title else ''
    # Extract key words from title (4+ chars) for partial matching
    _title_words = {w.lower() for w in re.findall(r'\b\w{4,}\b', _work_title_lower)} if _work_title_lower else set()

    for snip in snippets:
        s = score_snippet(snip, artist)
        if s == -999:
            rejected_bio += 1
        else:
            # [LOCAL-419] Title relevance adjustment: snippets that don't mention
            # the work title at all are likely about a different topic (e.g. a
            # different exhibition at the same venue). Penalize them.
            if _title_words:
                snip_text = f"{snip.get('title', '')} {snip.get('snippet', '')}".lower()
                _title_word_hits = sum(1 for w in _title_words if w in snip_text)
                if _title_word_hits == 0:
                    # No title words at all → likely irrelevant
                    s -= 5
                elif _title_word_hits >= 2 or _work_title_lower in snip_text:
                    # Strong title match → small bonus
                    s += 1
            # [LOCAL-415] Count tier3 demotions for the usability metric. Independent
            # of the relevance adjustment above — both apply. (LEAD merge, D363)
            if snip.get('tier') == 'tier3':
                tier3_demoted += 1
            scored.append((s, snip))

    # Sort descending by score, with tier1/tier2 winning ties over tier3
    scored.sort(key=lambda x: (x[0], 0 if x[1].get('tier') == 'tier3' else 1), reverse=True)

    # Cap
    capped = scored[:cap]

    # [LOCAL-415] Usability check: how many surviving snippets are title-relevant?
    starvation_rescued = False
    usable_count = 0
    if work_title:
        usable_count = sum(
            1 for _, snip in capped
            if _snippet_is_title_relevant(snip, work_title)
        )

        # STARVATION RESCUE: if NO surviving snippet is title-relevant but there
        # ARE tier3 snippets that ARE relevant, let the best one through.
        # This prevents the tier gate from starving stops into LLM refusals.
        if usable_count == 0 and capped:
            # Find tier3 snippets that were scored (including penalized ones beyond cap)
            _all_tier3_relevant = [
                (s, snip) for s, snip in scored
                if snip.get('tier') == 'tier3' and _snippet_is_title_relevant(snip, work_title)
            ]
            if _all_tier3_relevant:
                # Re-score without the tier3 penalty to find the truly best one
                _best_tier3 = max(_all_tier3_relevant, key=lambda x: x[0] - TIER3_PENALTY + TIER3_PENALTY)
                # Actually we need the original score + penalty removed:
                # The score already has the penalty applied, so add it back to get raw score
                _best_snip = _best_tier3[1]
                _raw_score = _best_tier3[0] - TIER3_PENALTY  # remove penalty to get base score
                # Replace the worst snippet in capped with this relevant tier3
                # (or append if under cap)
                if len(capped) >= cap:
                    # Replace the last (lowest-scoring) entry
                    capped[-1] = (_raw_score, _best_snip)
                else:
                    capped.append((_raw_score, _best_snip))
                starvation_rescued = True
                usable_count = 1  # At least the rescued one
                print(f"    [LOCAL-415] STARVATION RESCUE: tier3 snippet '{_best_snip.get('title', '')[:50]}' "
                      f"let through (score {_raw_score}) — only title-relevant material for this stop")
    else:
        usable_count = len(capped)  # Can't assess without title

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
        'usable_count': usable_count,
        'starvation_rescued': starvation_rescued,
        'scores': [
            (s[1].get('title', '')[:50], s[0], s[1].get('tier', '')) for s in capped
        ],
    }

    return [s[1] for s in capped], report
