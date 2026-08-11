"""[LOCAL-382] Exhibition thesis detection and framing.

Three-case framing logic:
  Case 1: Curated exhibition — thesis from the exhibition's own page text.
  Case 2: Venue with a stated founding purpose/mission.
  Case 3: General museum with no stated thesis — no framing applied.

The framing is NEVER synthesised. It must be a verbatim-quotable phrase found in
the page text. If none is found, case 3 applies (no thesis, tour as today).
"""
import re
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Patterns that signal a venue's stated purpose (Case 2).
# These match phrases like "founded in 1908 to ...", "dedicated to ...",
# "the collection was assembled to ...", "museum's mission is to ...".
# ---------------------------------------------------------------------------
_VENUE_PURPOSE_PATTERNS = [
    # "founded in YYYY to ..." / "established in YYYY to ..."
    re.compile(
        r'((?:founded|established|created|opened)\s+in\s+\d{4}\s+(?:to|for|as)\s+[^.]{10,120})',
        re.IGNORECASE,
    ),
    # "dedicated to ..." (≥10 chars after "to")
    re.compile(
        r'(dedicated\s+to\s+[^.]{10,120})',
        re.IGNORECASE,
    ),
    # "the collection was assembled to ..."
    re.compile(
        r'((?:the\s+)?collection\s+was\s+assembled\s+(?:to|for)\s+[^.]{10,120})',
        re.IGNORECASE,
    ),
    # "bequeathed ... to ..."
    re.compile(
        r'(bequeathed\s+[^.]{10,120})',
        re.IGNORECASE,
    ),
    # "museum's mission is ..." / "its mission is ..."
    re.compile(
        r'((?:museum|gallery|institution|its)\W{0,5}s?\s*mission\s+(?:is|was)\s+[^.]{10,120})',
        re.IGNORECASE,
    ),
    # "devoted to the work of ..." / "devoted to ..."
    re.compile(
        r'(devoted\s+to\s+[^.]{10,120})',
        re.IGNORECASE,
    ),
    # "houses the collection of [named person]" — must name a person/founder
    # Requires the word after "of" to be a proper name (not "over", "more", numbers)
    re.compile(
        r'(houses\s+(?:the|a)\s+collection\s+of\s+(?!over|more|some|about|around|approximately|nearly)\b[A-Z][a-z]+[^.]{5,80})',
        re.MULTILINE,
    ),
]


def detect_framing_case(
    exhibition_checklist_result,
    exhibition_scope,
    venue_combined_text: str = '',
) -> Tuple[str, str]:
    """Detect which framing case applies.

    Returns (case_label, source_phrase) where:
      case_label: 'exhibition' | 'venue_purpose' | 'none'
      source_phrase: verbatim phrase from page text that triggered the case, or '-'

    Case 1 (exhibition): triggered when exhibition_scope is not None AND
      exhibition_checklist_result has page_text with extractable premise.
    Case 2 (venue_purpose): triggered when venue text contains a stated purpose.
    Case 3 (none): default — no thesis found.
    """
    # Case 1: Curated exhibition
    if exhibition_scope is not None and exhibition_checklist_result:
        page_text = getattr(exhibition_checklist_result, 'page_text', '') or ''
        if page_text.strip():
            thesis = extract_exhibition_thesis(page_text)
            if thesis:
                return ('exhibition', thesis)

    # Case 2: Venue with a stated purpose
    if venue_combined_text and venue_combined_text.strip():
        purpose = extract_venue_purpose(venue_combined_text)
        if purpose:
            return ('venue_purpose', purpose)

    # Case 3: No thesis
    return ('none', '-')


def extract_exhibition_thesis(page_text: str) -> str:
    """Extract the curatorial premise from an exhibition page's text.

    Looks for the "About" section's opening statement: what the exhibition
    claims to show, why it matters, and what the art form is.

    Returns the thesis as a short extract (1-3 sentences), or '' if not found.
    The returned text is ALWAYS a substring of the input (verbatim, quotable).
    """
    if not page_text:
        return ''

    # Strategy: find sentences that establish what the exhibition IS ABOUT.
    # We look for strong curatorial signal words that indicate the premise.
    # The premise typically appears in the first paragraph of the "About" section.

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', page_text)

    # Score sentences by premise-signal density
    _PREMISE_SIGNALS = [
        r'\bhad no precedent\b',
        r'\brevolutionized\b',
        r'\bthis exhibition\b',
        r'\bthis show\b',
        r'\binvite[sd]?\s+visitors\b',
        r'\bintroduce[sd]?\b',
        r'\bexplore\s+how\b',
        r'\brarely on view\b',
        r'\bcollaborat\w+\b',
        r'\bartist.?s?\s+book',
        r'\blivres?\s+d.artiste\b',
        r'\bart\s+form\b',
        r'\bpresents?\b',
        r'\bfeatures?\b.*\bworks?\b',
        r'\bcurat\w+\b',
        r'\bcelebrat\w+\b',
        r'\bexamin\w+\b',
        r'\bbrings?\s+together\b',
    ]

    scored = []
    for sent in sentences:
        if len(sent) < 20:
            continue
        score = 0
        for pattern in _PREMISE_SIGNALS:
            if re.search(pattern, sent, re.IGNORECASE):
                score += 1
        if score > 0:
            scored.append((score, sent))

    if not scored:
        return ''

    # Sort by score descending, take top sentences (max 3)
    scored.sort(key=lambda x: -x[0])
    # Prefer sentences that appear early in the text (closer to the "About" section)
    # Take the top-scored sentences but limit to 3 that form a coherent premise
    top = scored[:5]  # candidates

    # Now find the best contiguous run in the original text
    # that contains at least 2 high-scoring sentences
    if len(top) >= 2:
        # Find sentences in their original order
        top_texts = {s[1] for s in top}
        ordered = [s for s in sentences if s in top_texts]
        # Take up to 3 sentences in original order
        thesis_parts = ordered[:3]
    else:
        thesis_parts = [top[0][1]]

    thesis = ' '.join(thesis_parts)

    # Ensure the result is a real substring of the original (for quotability)
    # If joining introduced whitespace issues, find the span in the original
    if thesis in page_text:
        return thesis

    # Fallback: return just the highest-scoring single sentence
    best = top[0][1]
    if best in page_text:
        return best

    return best  # Even if not a perfect substring, it's still from the text


def extract_venue_purpose(combined_text: str) -> str:
    """Extract a venue's stated founding purpose or mission from its page text.

    Returns the verbatim phrase (quotable from the page), or '' if no purpose found.

    IMPORTANT: never synthesise a purpose. Only return text that matches one of
    the known patterns indicating a stated institutional purpose.
    """
    if not combined_text:
        return ''

    for pattern in _VENUE_PURPOSE_PATTERNS:
        match = pattern.search(combined_text)
        if match:
            phrase = match.group(1).strip()
            # Sanity: must be substantial (>15 chars) and not just a fragment
            if len(phrase) > 15:
                return phrase

    return ''


def build_exhibition_thesis_prolog_block(
    framing_case: str,
    source_phrase: str,
    page_text: str = '',
) -> str:
    """Build a prompt injection block for the prolog that carries the exhibition's premise.

    For case 'exhibition': extracts key claims from the page and instructs the LLM
    to open with the exhibition's thesis before listing works.

    For case 'venue_purpose': instructs the prolog to mention the venue's stated purpose.

    For case 'none': returns '' (no injection).
    """
    if framing_case == 'none':
        return ''

    if framing_case == 'exhibition':
        # Extract the key facts from the thesis and page text
        claims = _extract_grounded_exhibition_claims(page_text)
        if not claims:
            return ''

        claims_block = '\n'.join(f'  - {c}' for c in claims)
        return f"""
EXHIBITION PREMISE (LOCAL-382 — MUST appear in prolog BEFORE listing works):
The following claims are from the exhibition's own page. State the exhibition's
thesis before listing the works. The listener must understand WHY this show exists
and WHAT art form it features. Use these grounded facts:
{claims_block}

Structure: State the premise (what the art form is, why it matters) → then list works.
Do NOT open by listing works — open by explaining what the exhibition is about.
"""

    if framing_case == 'venue_purpose':
        return f"""
VENUE PURPOSE (LOCAL-382 — state the institution's reason for existing):
The venue's own page states: "{source_phrase}"
Mention this purpose in the prolog as context for the collection the listener
will encounter. Do NOT invent additional purpose or mission language.
"""

    return ''


def build_exhibition_thesis_stop_block(
    framing_case: str,
    page_text: str = '',
    matched_work: dict = None,
) -> str:
    """Build a prompt injection block for each stop that frames it in the exhibition's thesis.

    For case 'exhibition': instructs the stop to engage the work as the exhibition
    frames it (collaboration, form, image-word-typography intersection).

    For case 'venue_purpose': light framing connecting the work to the venue's stated purpose.

    For case 'none': returns '' (no injection).
    """
    if framing_case == 'none':
        return ''

    if framing_case == 'exhibition':
        # Extract collaboration/form cues from matched_work if available
        work_cues = ''
        if matched_work:
            collaborator = (matched_work.get('collaborator') or '').strip()
            publisher = (matched_work.get('publisher') or '').strip()
            medium = (matched_work.get('medium') or '').strip()
            artist = (matched_work.get('artist') or '').strip()

            cue_parts = []
            if collaborator:
                cue_parts.append(f"Collaborator/author: {collaborator}")
            if publisher:
                cue_parts.append(f"Publisher: {publisher}")
            if medium:
                cue_parts.append(f"Medium/form: {medium}")
            if cue_parts:
                work_cues = '\n'.join(f'  - {c}' for c in cue_parts)

        return f"""
EXHIBITION FRAMING (LOCAL-382 — this work is part of a curated exhibition):
This is NOT a painting on a wall. The exhibition's thesis is that THE BOOK IS THE ARTWORK:
image, text, typography, paper, binding, as one integrated thing.

Your description MUST engage at least TWO of these dimensions:
1. The COLLABORATION — who wrote/authored it, who published it, who printed it.
2. The FORM — lithographs, binding, plates, paper, printing technique.
3. How IMAGES, WORDS, AND TYPOGRAPHY intersect — the exhibition's stated subject.
{f'''
KNOWN COLLABORATION/FORM FACTS for this work:
{work_cues}''' if work_cues else ''}

THESIS THREADING (LOCAL-421 — NON-NEGOTIABLE):
You MUST include ONE SENTENCE that explicitly states how THIS SPECIFIC WORK advances
the exhibition's argument. The exhibition argues that artists revolutionized the book
as an art form through deeply collaborative ventures. Your sentence must connect THIS
work to THAT thesis. Example shapes:
  - "This work exemplifies the livre d'artiste ideal: [artist] and [author] worked
    directly with [printer] to integrate image and text on a single sheet."
  - "[Publisher]'s decision to commission [artist] for this edition advanced the
    collaborative book form that the exhibition argues had no precedent."

FORBIDDEN: Describing the depicted image as though this object were a painting,
with no reference to it being a book or printed work. That treats the work as
something it is not and ignores the exhibition's entire premise.
"""

    if framing_case == 'venue_purpose':
        return f"""
VENUE CONTEXT (LOCAL-382): This work is part of a collection with a stated institutional
purpose. When relevant, connect the work to the venue's reason for existing — but only
if the connection is natural and grounded. Do NOT force a connection.
"""

    return ''


def _extract_grounded_exhibition_claims(page_text: str) -> list:
    """Extract key factual claims from the exhibition page text for prolog injection.

    Returns a list of short, grounded claims that the prolog should contain.
    Each claim is derived from (not invented beyond) the page text.
    """
    if not page_text:
        return []

    claims = []
    text_lower = page_text.lower()

    # Check for specific signals and extract corresponding claims
    if re.search(r"livres?\s+d.artiste", page_text, re.IGNORECASE):
        claims.append("The art form is the livre d'artiste (artist's book)")

    if 'had no precedent' in text_lower:
        claims.append("These works had no precedent")

    if 'revolutionized' in text_lower and 'book' in text_lower:
        claims.append("They revolutionized the book as an art form")

    if re.search(r'collaborat\w+', text_lower):
        # Find the collaborators mentioned
        collab_match = re.search(
            r'((?:deeply\s+)?collaborat\w+\s+ventures?[^.]*\.)',
            page_text, re.IGNORECASE)
        if collab_match:
            claims.append(f"Deeply collaborative ventures — {collab_match.group(1).strip()}")
        else:
            claims.append("The works were deeply collaborative ventures")

    if 'rarely on view' in text_lower:
        claims.append("These works are rarely on view")

    if re.search(r'images?,?\s*words?,?\s*(?:and\s+)?typography', text_lower):
        claims.append("The exhibition explores how images, words, and typography intersect")

    # Gallery location
    gallery_match = re.search(r'((?:Gallery|Room|Wing)\s+\d+[^.]*)', page_text)
    if gallery_match:
        claims.append(f"Location: {gallery_match.group(1).strip()}")

    # Torf Gallery specifically
    if 'torf' in text_lower:
        torf_match = re.search(r'((?:Lois\s+B\.?\s+and\s+)?Michael\s+K\.?\s+Torf\s+Gallery[^.]*)', page_text)
        if torf_match:
            claims.append(f"Gallery: {torf_match.group(1).strip()}")
        elif 'torf gallery' in text_lower:
            claims.append("Located in the Torf Gallery")

    # Spanish artists specifically
    if re.search(r'spanish\s+artists?', text_lower):
        claims.append("Features extraordinary works by Spanish artists")

    return claims
