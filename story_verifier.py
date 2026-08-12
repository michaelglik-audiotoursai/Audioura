"""story_verifier.py — LOCAL-423: Verify candidate stories against retrieved sources.

Michael's algorithm Step 4: every load-bearing claim in a candidate story must trace
to a retrieved source BEFORE that candidate can win selection.

Key principles:
  - Selection rewards drama; invented claims have the most drama. Verification gates
    selection, not follows it.
  - A name match is not an identity match (entity disambiguation).
  - Self-contradictions (e.g. "15 lithographs" and "40 color lithographs" in the same
    stop) must be impossible, not merely absent.
  - A claim with no source must not ship.

This module:
  1. Extracts load-bearing claims from a candidate story (numbers, dates, named
     persons + predicates, attributions).
  2. Checks each claim against the corpus snippets for source support.
  3. Disambiguates entities (prevents wrong-person matches).
  4. Detects numeric self-contradictions within a single story.
  5. Returns a verdict: pass (all claims sourced), fail (unsourced/contradicted claims).
"""

import re
import unicodedata
from typing import Dict, List, Optional, Tuple


# ─── Text normalization ──────────────────────────────────────────────────────

def _strip_accents(text: str) -> str:
    """Remove diacritics for matching."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _normalize(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    return re.sub(r'\s+', ' ', _strip_accents(text).lower()).strip()


def _tokenize(text: str) -> List[str]:
    """Split into alpha-numeric tokens."""
    return re.findall(r'[a-z0-9]+', _normalize(text))


# ─── Claim extraction ────────────────────────────────────────────────────────

# Numeric claims: "15 lithographs", "40 color lithographs", "edition of 220"
_NUMERIC_CLAIM_RE = re.compile(
    r'\b(\d[\d,]*)\s+'
    r'((?:color\s+|colour\s+)?'
    r'(?:lithographs?|etchings?|drypoints?|woodcuts?|aquatints?|prints?|'
    r'copies|sheets?|plates?|works?|editions?|volumes?|pages?|'
    r'illustrations?|engravings?))\b',
    re.IGNORECASE
)

# Edition/set patterns: "edition of N", "set of N", "limited to N"
_EDITION_CLAIM_RE = re.compile(
    r'\b(?:edition|set|run|printing|series)\s+of\s+(\d[\d,]*)\b',
    re.IGNORECASE
)

# Year claims: "in 1971", "published in 2003"
_YEAR_CLAIM_RE = re.compile(
    r'\b(1[0-9]{3}|20[0-2][0-9])\b'
)

# Person + predicate claims: "Boris Fridman, a dedicated collector of artist books"
# Matches: ProperName + comma + article + descriptor containing a ROLE NOUN anywhere.
_PERSON_DESCRIPTOR_RE = re.compile(
    r'([A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)+)'  # multi-word proper noun
    r',?\s+'
    r'(?:a\s+|an\s+|the\s+)?'
    r'((?:[A-Za-zà-ÿ\-]+\s+){0,6}?'  # up to 6 words before the role noun
    r'(?:collector|publisher|printer|patron|donor|artist|architect|sculptor'
    r'|designer|engraver|composer|dealer|curator|founder|director'
    r'|printmaker|lithographer|poet|writer|painter|illustrator)'
    r'(?:\s+[A-Za-zà-ÿ\-]+){0,5})',  # up to 5 words after (e.g. "of artist books")
    re.MULTILINE
)

# Attribution claims: "donated this work to X", "generously donated..."
_DONATION_CLAIM_RE = re.compile(
    r'(?:\w+\s+)?'  # optional adverb like "generously"
    r'(?:donated|gave|gifted|bequeathed)\s+'
    r'(?:this\s+(?:work|piece|edition|portfolio|print|book|volume)\s+)?'
    r'(?:to\s+(?:the\s+)?(.{2,60}?))?'  # recipient (greedy-ish, up to 60 chars)
    r'(?:\.\s*$|\s+in\s+(\d{4})|(?=\s*[,.]))',  # end at period, year, or comma
    re.IGNORECASE | re.MULTILINE
)

# Commission/print attribution: "X commissioned Y", "printed by X"
_ATTRIBUTION_CLAIM_RE = re.compile(
    r'(?:'
    # Pattern 1: Subject + verb + object — "Louis Broder commissioned Miro"
    # Also handles appositive: "Louis Broder, a publisher, commissioned Miro"
    r'([A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)*)'
    r'(?:,\s*[^,]{0,80},\s*|\s+)'  # optional appositive in commas, or whitespace
    r'(?:commissioned|published|printed|produced|created|engraved|'
    r'funded|sponsored|patronized|acquired|assembled)\s+'
    r'(.{2,60}?)'
    r'|'
    # Pattern 2: "printed/published by X" — passive attribution
    r'(?:printed|published|produced|created|engraved|commissioned|lithographed)\s+'
    r'(?:by\s+(?:the\s+)?(?:renowned\s+|famous\s+|celebrated\s+)?)'
    r'([A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)*)'
    r')'
    r'(?:\s|[,.]|$)',
    re.MULTILINE
)

# Institutional claims: "enhances the museum's collection of X",
# "home to the largest collection of Y", "houses N works"
_INSTITUTIONAL_CLAIM_RE = re.compile(
    r'(?:'
    # Pattern 1: verb + possessive + "collection/holdings" + qualifier
    r'(?:enhances?|enriches?|complements?|augments?|adds?\s+to)\s+'
    r"(?:the\s+)?(?:\w+'s\s+)?"
    r'(?:extensive\s+|permanent\s+|renowned\s+|significant\s+|important\s+)?'
    r'(?:collection|holdings|archive|repository)\s+'
    r'(?:of\s+(.{2,60}?))'
    r'|'
    # Pattern 2: "one of the [largest|finest|most important] collections of X"
    r'(?:one\s+of\s+the\s+)?'
    r'(?:largest|finest|most\s+\w+|premier|leading)\s+'
    r'(?:collection|holdings|archive|repository)\s+'
    r'(?:of\s+(.{2,60}?))'
    r'|'
    # Pattern 3: "known for its/the collection of X"
    r'(?:known|renowned|famous|celebrated)\s+for\s+'
    r'(?:its|the|their)\s+'
    r'(?:collection|holdings)\s+'
    r'(?:of\s+(.{2,60}?))'
    r')'
    r'(?:\.|,|\s*$)',
    re.IGNORECASE | re.MULTILINE
)

# "Known for" descriptor applied to proper nouns: "renowned Mourlot Freres",
# "known for his dedication to X"
_KNOWN_FOR_RE = re.compile(
    r'(?:known|renowned|famous|celebrated|noted)\s+'
    r'(?:for\s+(?:his|her|its|their)\s+)?'
    r'(.{5,80}?)(?:\.|,|$)',
    re.IGNORECASE | re.MULTILINE
)

# Location descriptor: "Boston-based", "New York collector"
_LOCATION_DESCRIPTOR_RE = re.compile(
    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)-based\b|'
    r'\b(?:a|the)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+'
    r'(?:collector|dealer|publisher|patron|printer)',
    re.MULTILINE
)


class Claim:
    """A single load-bearing factual claim extracted from story text."""

    def __init__(self, claim_type: str, text: str, value: str,
                 subject: str = '', context: str = ''):
        self.claim_type = claim_type  # 'numeric', 'year', 'person_descriptor', 'donation', 'location'
        self.text = text              # verbatim text span
        self.value = value            # the key assertion (e.g. "15", "1971", "Boston-based")
        self.subject = subject        # who/what the claim is about
        self.context = context        # surrounding sentence
        self.verdict = 'UNCHECKED'    # SOURCED, UNSOURCED, CONTRADICTED
        self.source_url = ''          # URL of supporting snippet
        self.source_snippet = ''      # text of supporting snippet
        self.rejection_reason = ''    # why it failed

    def __repr__(self):
        return f"Claim({self.claim_type}, '{self.text[:50]}', verdict={self.verdict})"


def extract_claims(story_text: str) -> List[Claim]:
    """Extract all load-bearing factual claims from a candidate story.

    Load-bearing = a specific assertion that could be true or false:
      - Numbers (edition sizes, lithograph counts)
      - Years/dates
      - Person + role/descriptor ("a visionary publisher", "a dedicated collector")
      - Attribution ("X commissioned Y", "printed by X")
      - Donation/gift claims with recipients
      - Institutional claims ("enhances the museum's collection of X")
    """
    claims = []
    # Track matched text spans to avoid duplicate claims from overlapping patterns
    _seen_spans = set()
    sentences = re.split(r'(?<=[.!?])\s+', story_text.strip())

    def _add_claim(claim: Claim, span_text: str) -> None:
        """Add a claim if we haven't already captured this exact span."""
        norm_span = span_text.strip().lower()
        if norm_span not in _seen_spans:
            _seen_spans.add(norm_span)
            claims.append(claim)

    for sentence in sentences:
        # Numeric claims: "15 lithographs", "40 color lithographs"
        for match in _NUMERIC_CLAIM_RE.finditer(sentence):
            _add_claim(Claim(
                claim_type='numeric',
                text=match.group(0),
                value=match.group(1).replace(',', ''),
                subject=match.group(2),
                context=sentence,
            ), match.group(0))

        # Edition claims: "edition of 220", "set of 10"
        for match in _EDITION_CLAIM_RE.finditer(sentence):
            _add_claim(Claim(
                claim_type='numeric',
                text=match.group(0),
                value=match.group(1).replace(',', ''),
                subject='edition',
                context=sentence,
            ), match.group(0))

        # Year claims: "in 1971", "published in 2003"
        for match in _YEAR_CLAIM_RE.finditer(sentence):
            year = match.group(1)
            # Only count as a claim if it's in a factual context
            # (not just "Miró (1893-1983)" biography)
            if re.search(r'(?:in|published|printed|donated|created|produced|established|founded)\s+' + year,
                        sentence, re.IGNORECASE):
                text = f"in {year}" if f"in {year}" in sentence else year
                _add_claim(Claim(
                    claim_type='year',
                    text=text,
                    value=year,
                    subject='',
                    context=sentence,
                ), text)

        # Person + role descriptor: "Louis Broder, a visionary publisher known for..."
        for match in _PERSON_DESCRIPTOR_RE.finditer(sentence):
            person = match.group(1)
            descriptor = match.group(2).strip()
            if descriptor:
                _add_claim(Claim(
                    claim_type='person_descriptor',
                    text=match.group(0).strip(),
                    value=descriptor,
                    subject=person,
                    context=sentence,
                ), match.group(0))

        # Attribution claims: "X commissioned Y", "printed by X"
        for match in _ATTRIBUTION_CLAIM_RE.finditer(sentence):
            # Group 1+2 = active voice (Subject commissioned Object)
            # Group 3 = passive voice (printed by Subject)
            if match.group(1) and match.group(2):
                subject = match.group(1).strip()
                obj = match.group(2).strip().rstrip(',.')
                _add_claim(Claim(
                    claim_type='attribution',
                    text=match.group(0).strip(),
                    value=f"{subject} → {obj}",
                    subject=subject,
                    context=sentence,
                ), match.group(0))
            elif match.group(3):
                agent = match.group(3).strip()
                # Extract the verb for context
                verb_match = re.search(
                    r'(printed|published|produced|created|engraved|commissioned|lithographed)',
                    match.group(0), re.IGNORECASE
                )
                verb = verb_match.group(1) if verb_match else 'attributed'
                _add_claim(Claim(
                    claim_type='attribution',
                    text=match.group(0).strip(),
                    value=f"{verb} by {agent}",
                    subject=agent,
                    context=sentence,
                ), match.group(0))

        # Donation/gift claims: "generously donated this work to the Museum of Fine Arts"
        for match in _DONATION_CLAIM_RE.finditer(sentence):
            recipient = match.group(1)
            year = match.group(2)
            if recipient or year:
                value = recipient.strip().rstrip(',.') if recipient else ''
                if year:
                    value = f"{value} in {year}" if value else year
                _add_claim(Claim(
                    claim_type='donation',
                    text=match.group(0).strip(),
                    value=value,
                    subject=recipient.strip().rstrip(',.') if recipient else '',
                    context=sentence,
                ), match.group(0))

        # Institutional claims: "enhances the museum's extensive collection of X"
        for match in _INSTITUTIONAL_CLAIM_RE.finditer(sentence):
            # Any of the three groups could be the collection descriptor
            descriptor = match.group(1) or match.group(2) or match.group(3)
            if descriptor:
                descriptor = descriptor.strip().rstrip(',.')
                _add_claim(Claim(
                    claim_type='institutional',
                    text=match.group(0).strip(),
                    value=descriptor,
                    subject='institution',
                    context=sentence,
                ), match.group(0))

        # Location descriptor claims: "Boston-based", "a New York collector"
        for match in _LOCATION_DESCRIPTOR_RE.finditer(sentence):
            location = match.group(1) or match.group(2)
            if location:
                _add_claim(Claim(
                    claim_type='location_descriptor',
                    text=match.group(0),
                    value=location,
                    subject='',
                    context=sentence,
                ), match.group(0))

    return claims


# ─── Entity disambiguation ───────────────────────────────────────────────────

# Known disambiguation cases — entities whose name substring matches but are
# different people/things entirely.
_DISAMBIGUATION_RULES = [
    {
        'surname': 'fridman',
        'exclude_patterns': [
            r'fridman[- ]?mintz',           # Boris Fridman-Mintz, linguist in Mexico
            r'linguist',
            r'deaf\s+(?:community|studies|education)',
            r'sign\s+language',
            r'mexico\s+city',
            r'unam',                         # Universidad Nacional Autónoma de México
        ],
        'exclude_reason': 'Wrong person: Boris Fridman-Mintz is a Mexican linguist, not the collector',
    },
    {
        'surname': 'fridman',
        'exclude_patterns': [
            r'fridman\s+gallery',
            r'founded\s+in\s+2013',
            r'new\s+york\s+gallery',
            r'contemporary\s+art\s+gallery',
        ],
        'exclude_reason': 'Wrong entity: Fridman Gallery (NYC, 2013) is unrelated to collector Boris Fridman',
    },
]


def disambiguate_snippet(snippet_text: str, snippet_title: str = '',
                         target_surname: str = '') -> Tuple[bool, str]:
    """Check if a snippet is about the RIGHT entity (not a namesake).

    Returns (is_valid, reason). If is_valid=False, the snippet must be excluded.
    """
    if not target_surname:
        return True, ''

    combined = f"{snippet_title} {snippet_text}".lower()
    target_lower = target_surname.lower()

    # Only check disambiguation if the surname appears in the snippet
    if target_lower not in combined:
        return True, ''  # Surname not in snippet — no confusion possible

    for rule in _DISAMBIGUATION_RULES:
        if rule['surname'] != target_lower:
            continue
        for pattern in rule['exclude_patterns']:
            if re.search(pattern, combined, re.IGNORECASE):
                return False, rule['exclude_reason']

    return True, ''


def disambiguate_snippets(snippets: List[Dict], target_surname: str) -> Tuple[List[Dict], List[Dict]]:
    """Filter snippets, removing those about wrong entities.

    Returns (valid_snippets, excluded_snippets).
    """
    valid = []
    excluded = []

    for snip in snippets:
        text = snip.get('snippet', '')
        title = snip.get('title', '')
        is_valid, reason = disambiguate_snippet(text, title, target_surname)
        if is_valid:
            valid.append(snip)
        else:
            excluded.append({**snip, 'exclusion_reason': reason})

    return valid, excluded


# ─── Self-contradiction detection ────────────────────────────────────────────

def detect_self_contradictions(claims: List[Claim]) -> List[Tuple[Claim, Claim, str]]:
    """Detect numeric self-contradictions within a single story.

    The lithograph-count bug: "15 lithographs" and "40 color lithographs" in one stop
    must be impossible. This catches any case where the same SUBJECT (e.g. lithographs)
    gets two DIFFERENT numeric values in the same text.

    Returns list of (claim1, claim2, explanation) tuples.
    """
    contradictions = []

    # Group numeric claims by normalized subject
    subject_claims: Dict[str, List[Claim]] = {}
    for claim in claims:
        if claim.claim_type != 'numeric':
            continue
        # Normalize subject: "lithographs" == "color lithographs" == "lithograph"
        subj = _normalize(claim.subject)
        # Strip adjectives to group: "color lithographs" → "lithographs"
        subj_core = re.sub(r'^(color|colour|original|hand|full)\s+', '', subj)
        # Singularize
        subj_core = re.sub(r's$', '', subj_core)
        if subj_core not in subject_claims:
            subject_claims[subj_core] = []
        subject_claims[subj_core].append(claim)

    # Check for conflicting values within same subject
    for subj, group in subject_claims.items():
        if len(group) < 2:
            continue
        values = set(c.value for c in group)
        if len(values) > 1:
            # Multiple different numbers for the same subject = contradiction
            for i in range(len(group)):
                for j in range(i+1, len(group)):
                    if group[i].value != group[j].value:
                        contradictions.append((
                            group[i], group[j],
                            f"Contradictory {subj} count: "
                            f"{group[i].value} vs {group[j].value} in same story"
                        ))

    return contradictions


# ─── Claim verification against corpus ───────────────────────────────────────

def _snippet_supports_claim(claim: Claim, snippet_text: str) -> bool:
    """Check if a single snippet text supports a claim.

    For numeric claims: the exact number must appear in the snippet.
    For year claims: the year must appear in a relevant context.
    For location descriptors: the location must appear near the person.
    For donation claims: recipient or year must appear with donation context.
    For attribution claims: the subject must appear with the attributed action.
    For person_descriptor claims: the person and a role-related word must co-occur.
    For institutional claims: the collection/holdings descriptor must appear.
    """
    snip_lower = snippet_text.lower()
    snip_norm = _normalize(snippet_text)

    if claim.claim_type == 'numeric':
        # The exact number must appear
        if claim.value not in snippet_text and claim.value not in snip_norm:
            return False
        # AND the subject (or a synonym) must appear nearby
        subj_core = re.sub(r's$', '', _normalize(claim.subject))
        if subj_core in snip_norm:
            return True
        # Check synonyms: "lithograph" ≈ "print", "copy" ≈ "edition"
        _SYNONYMS = {
            'lithograph': ['lithograph', 'print', 'plate'],
            'copy': ['copy', 'copies', 'edition', 'exemplaire'],
            'plate': ['plate', 'planche'],
            'sheet': ['sheet', 'feuille', 'leaf'],
        }
        for syn_list in _SYNONYMS.values():
            if subj_core in syn_list:
                if any(s in snip_norm for s in syn_list):
                    return True
        return False

    elif claim.claim_type == 'year':
        # Year must appear in snippet
        return claim.value in snippet_text

    elif claim.claim_type == 'location_descriptor':
        # The location must appear AS A DESCRIPTOR of a person, not just anywhere.
        location_lower = _normalize(claim.value)
        descriptor_patterns = [
            rf'{location_lower}[- ]based',
            rf'(?:a|the)\s+{location_lower}\s+(?:collector|dealer|publisher|patron|printer)',
            rf'from\s+{location_lower}',
            rf'{location_lower}\s+(?:native|resident|based)',
        ]
        for pat in descriptor_patterns:
            if re.search(pat, snip_norm):
                return True
        return False

    elif claim.claim_type == 'donation_date':
        # Legacy type — year must appear AND donation/gift context must exist
        if claim.value not in snippet_text:
            return False
        return bool(re.search(r'donat|gift|gave|bequeath', snip_lower))

    elif claim.claim_type == 'donation':
        # New broader donation type: recipient or year must appear with donation context
        has_donation_context = bool(re.search(r'donat|gift|gave|bequeath|present', snip_lower))
        if not has_donation_context:
            return False
        # If we have a recipient, it must appear in the snippet
        if claim.subject:
            subject_norm = _normalize(claim.subject)
            # Allow partial match — "Museum of Fine Arts" matches "Museum of Fine Arts, Boston"
            subject_words = subject_norm.split()
            if len(subject_words) >= 2:
                # Check if at least the key content words appear together
                return subject_norm in snip_norm or all(
                    w in snip_norm for w in subject_words if len(w) > 3
                )
            return subject_norm in snip_norm
        return True  # Generic donation claim, context alone suffices

    elif claim.claim_type == 'attribution':
        # The subject (person/house) must appear in the snippet, AND
        # the action verb or relationship must be present
        subject_norm = _normalize(claim.subject)
        if subject_norm not in snip_norm:
            # Try surname only (last word of subject)
            surname = subject_norm.split()[-1] if subject_norm.split() else ''
            if not surname or surname not in snip_norm:
                return False
        # Check for the attribution verb
        attribution_verbs = r'commission|publish|print|produc|creat|engrav|lithograph'
        return bool(re.search(attribution_verbs, snip_lower))

    elif claim.claim_type == 'person_descriptor':
        # The person must appear AND a role-related word from the descriptor must appear
        subject_norm = _normalize(claim.subject)
        # Try full name or surname
        if subject_norm not in snip_norm:
            surname = subject_norm.split()[-1] if subject_norm.split() else ''
            if not surname or surname not in snip_norm:
                return False
        # Check if the role word from the descriptor appears
        role_words = re.findall(
            r'collector|publisher|printer|patron|donor|artist|architect|sculptor'
            r'|designer|engraver|composer|dealer|curator|founder|director'
            r'|printmaker|lithographer|poet|writer|painter|illustrator',
            claim.value.lower()
        )
        if role_words:
            return any(role in snip_lower for role in role_words)
        # Fallback: check if at least 2 content words from the descriptor appear
        desc_words = [w for w in _normalize(claim.value).split() if len(w) > 3]
        if desc_words:
            matches = sum(1 for w in desc_words if w in snip_norm)
            return matches >= min(2, len(desc_words))
        return False

    elif claim.claim_type == 'institutional':
        # The collection descriptor must appear (or key content words from it)
        desc_norm = _normalize(claim.value)
        if desc_norm in snip_norm:
            return True
        # Partial match: key words from the descriptor
        desc_words = [w for w in desc_norm.split() if len(w) > 3]
        if desc_words:
            matches = sum(1 for w in desc_words if w in snip_norm)
            return matches >= min(2, len(desc_words))
        return False

    return False


def verify_claims_against_corpus(
    claims: List[Claim],
    snippets: List[Dict],
    strict: bool = True,
) -> Dict:
    """Verify all claims against the available corpus snippets.

    For each claim, search all snippets for support. A claim is SOURCED if at least
    one snippet contains the asserted fact. A claim is UNSOURCED if no snippet supports it.

    Parameters:
        claims: extracted claims from the candidate story
        snippets: list of {'title', 'snippet', 'url'} dicts
        strict: if True, ANY unsourced claim fails the candidate

    Returns:
        {
            'all_sourced': bool,
            'sourced_claims': list of Claim,
            'unsourced_claims': list of Claim,
            'contradicted_claims': list of Claim,
            'evidence': list of {claim_text, source_url, source_snippet},
        }
    """
    sourced = []
    unsourced = []
    evidence = []

    for claim in claims:
        found_support = False
        for snip in snippets:
            snip_text = snip.get('snippet', '')
            snip_title = snip.get('title', '')
            combined_text = f"{snip_title} {snip_text}"

            if _snippet_supports_claim(claim, combined_text):
                claim.verdict = 'SOURCED'
                claim.source_url = snip.get('url', '')
                claim.source_snippet = snip_text[:200]
                found_support = True
                sourced.append(claim)
                evidence.append({
                    'claim_text': claim.text,
                    'claim_type': claim.claim_type,
                    'source_url': claim.source_url,
                    'source_snippet': claim.source_snippet,
                })
                break

        if not found_support:
            claim.verdict = 'UNSOURCED'
            claim.rejection_reason = f"No snippet supports: '{claim.text}'"
            unsourced.append(claim)

    # Check for self-contradictions
    contradictions = detect_self_contradictions(claims)
    contradicted = []
    for c1, c2, explanation in contradictions:
        c1.verdict = 'CONTRADICTED'
        c1.rejection_reason = explanation
        c2.verdict = 'CONTRADICTED'
        c2.rejection_reason = explanation
        contradicted.extend([c1, c2])

    all_sourced = len(unsourced) == 0 and len(contradicted) == 0

    return {
        'all_sourced': all_sourced,
        'sourced_claims': sourced,
        'unsourced_claims': unsourced,
        'contradicted_claims': contradicted,
        'contradictions': [(c1.text, c2.text, expl) for c1, c2, expl in contradictions],
        'evidence': evidence,
    }


# ─── Main verification function (Michael's Step 4) ──────────────────────────

def verify_story_candidate(
    story_text: str,
    snippets: List[Dict],
    credit_line: str = '',
    stop_name: str = '',
) -> Dict:
    """Verify a candidate story against its retrieved sources.

    Michael's Step 4: verification gates selection. A candidate with unsourced
    claims or self-contradictions is rejected BEFORE selection can reward its drama.

    Parameters:
        story_text: the candidate story text to verify
        snippets: the retrieved corpus snippets that sourced this story
        credit_line: the work's credit line (for entity disambiguation)
        stop_name: name of the stop (for logging)

    Returns:
        {
            'passed': bool — True if all claims are sourced
            'claims_extracted': int — total claims found
            'claims_sourced': int — claims with source support
            'claims_unsourced': int — claims without support
            'claims_contradicted': int — self-contradicting claims
            'unsourced_details': list of {text, type, reason}
            'contradictions': list of (text1, text2, explanation)
            'evidence': list of {claim_text, source_url, source_snippet}
            'disambiguation_excluded': list of excluded snippets
            'rejection_reasons': list of human-readable failure reasons
        }
    """
    if not story_text or not story_text.strip():
        return {
            'passed': False,
            'claims_extracted': 0,
            'claims_sourced': 0,
            'claims_unsourced': 0,
            'claims_contradicted': 0,
            'unsourced_details': [],
            'contradictions': [],
            'evidence': [],
            'disambiguation_excluded': [],
            'rejection_reasons': ['Empty story text'],
        }

    # Step 1: Entity disambiguation — filter snippets
    # Extract donor surname from credit line for disambiguation
    donor_surname = ''
    donor_match = re.search(
        r'(?:Gift|Bequest|Donation)\s+of\s+\w+\s+(\w+)',
        credit_line, re.IGNORECASE
    )
    if donor_match:
        donor_surname = donor_match.group(1)

    valid_snippets = snippets
    excluded_snippets = []
    if donor_surname:
        valid_snippets, excluded_snippets = disambiguate_snippets(snippets, donor_surname)
        if excluded_snippets:
            print(f"    [LOCAL-423] Entity disambiguation: excluded {len(excluded_snippets)} "
                  f"snippets for '{donor_surname}' (wrong entity)")
            for ex in excluded_snippets:
                print(f"      • {ex.get('title', '')[:60]}: {ex.get('exclusion_reason', '')}")

    # Step 2: Extract claims
    claims = extract_claims(story_text)

    # Step 3: Verify each claim against valid (disambiguated) snippets
    verification = verify_claims_against_corpus(claims, valid_snippets)

    # Step 4: Build rejection reasons
    rejection_reasons = []
    if verification['unsourced_claims']:
        for claim in verification['unsourced_claims']:
            rejection_reasons.append(
                f"UNSOURCED: '{claim.text}' ({claim.claim_type}) — "
                f"no snippet contains this assertion"
            )
    if verification['contradictions']:
        for t1, t2, expl in verification['contradictions']:
            rejection_reasons.append(f"CONTRADICTED: {expl}")

    passed = verification['all_sourced']

    return {
        'passed': passed,
        'claims_extracted': len(claims),
        'claims_sourced': len(verification['sourced_claims']),
        'claims_unsourced': len(verification['unsourced_claims']),
        'claims_contradicted': len(verification['contradicted_claims']),
        'unsourced_details': [
            {'text': c.text, 'type': c.claim_type, 'reason': c.rejection_reason}
            for c in verification['unsourced_claims']
        ],
        'contradictions': verification['contradictions'],
        'evidence': verification['evidence'],
        'disambiguation_excluded': [
            {'title': ex.get('title', ''), 'reason': ex.get('exclusion_reason', '')}
            for ex in excluded_snippets
        ],
        'rejection_reasons': rejection_reasons,
    }


# ─── Selection with verification (Michael's Step 3 + 4 combined) ─────────────

def select_verified_story(
    candidates: List[str],
    snippets: List[Dict],
    credit_line: str = '',
    stop_name: str = '',
) -> Dict:
    """Select the best story candidate that passes verification.

    Michael's rubric (Step 3):
      - Prefer information the listener cannot see with their own eyes
      - Require both informational AND emotional content
      - Reject anything that tells visitors what they should want or feel

    Step 4 gates Step 3: verification runs BEFORE selection. Only candidates
    where ALL claims are sourced can win.

    Parameters:
        candidates: list of candidate story texts
        snippets: retrieved corpus snippets
        credit_line: work's credit line
        stop_name: stop name for logging

    Returns:
        {
            'selected': str or None — the winning story text
            'selected_index': int or -1
            'selected_evidence': list — evidence for the winner
            'rejected': list of {index, text_preview, reasons}
            'all_failed': bool — True if no candidate passed
        }
    """
    rejected = []

    for i, candidate in enumerate(candidates):
        result = verify_story_candidate(
            story_text=candidate,
            snippets=snippets,
            credit_line=credit_line,
            stop_name=stop_name,
        )

        if not result['passed']:
            rejected.append({
                'index': i,
                'text_preview': candidate[:150] + '...' if len(candidate) > 150 else candidate,
                'reasons': result['rejection_reasons'],
                'claims_extracted': result['claims_extracted'],
                'claims_unsourced': result['claims_unsourced'],
            })
            print(f"    [LOCAL-423] Candidate {i+1} REJECTED: "
                  f"{result['claims_unsourced']} unsourced, "
                  f"{result['claims_contradicted']} contradicted")
            for reason in result['rejection_reasons'][:3]:
                print(f"      → {reason}")
            continue

        # Candidate passed verification — apply Michael's selection rubric
        # (Step 3: prefer invisible info, require info+emotion, reject directive)
        if _is_directive_text(candidate):
            rejected.append({
                'index': i,
                'text_preview': candidate[:150] + '...',
                'reasons': ['Directive: tells visitor what to feel/want'],
                'claims_extracted': result['claims_extracted'],
                'claims_unsourced': 0,
            })
            continue

        # Winner found
        return {
            'selected': candidate,
            'selected_index': i,
            'selected_evidence': result['evidence'],
            'rejected': rejected,
            'all_failed': False,
        }

    # All candidates failed
    return {
        'selected': None,
        'selected_index': -1,
        'selected_evidence': [],
        'rejected': rejected,
        'all_failed': True,
    }


def _is_directive_text(text: str) -> bool:
    """Michael's rubric rule 3: reject text that tells visitors what to feel/want.

    Returns True if the text contains directive language.
    """
    _DIRECTIVE_PATTERNS = [
        r'\binvites?\s+(?:you|us|the\s+(?:viewer|visitor|listener))\s+to\b',
        r'\b(?:take\s+a\s+moment|pause\s+to|consider\s+how|imagine\s+yourself)\b',
        r'\byou\s+(?:cannot\s+help|are\s+struck|find\s+yourself|should|must\s+(?:see|feel|experience))\b',
        r'\b(?:let|allow)\s+(?:yourself|us|the\s+work)\b',
    ]
    for pattern in _DIRECTIVE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False
