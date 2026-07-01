"""
Derepetition Guard — catches overused/cliché phrases in tour narration.
========================================================================
Compiled from analysis of chagall_current_tour.txt and common GPT-isms.
Use scan_for_repetition() to check generated text before committing it.
"""
import re
from typing import List

# 25+ forbidden/overused phrases compiled as case-insensitive regexes.
# Each pattern matches the phrase (or close variants) wherever it appears.
FORBIDDEN_PHRASES: List[re.Pattern] = [
    # Chagall-specific repetition (from current tour analysis)
    re.compile(r"vibrant\s+colou?rs?\s*(and|of)", re.IGNORECASE),
    re.compile(r"dreamlike\s+(imagery|quality|world|scene)", re.IGNORECASE),
    re.compile(r"deep\s+connection\s+to", re.IGNORECASE),
    re.compile(r"(his|her|their)\s+Jewish\s+heritage", re.IGNORECASE),
    re.compile(r"intricate\s+details?", re.IGNORECASE),
    re.compile(r"timeless\s+themes?", re.IGNORECASE),
    re.compile(r"position\s+yourself\s+in\s+the\s+center", re.IGNORECASE),
    re.compile(r"the\s+artist['']?s?\s+(unique|remarkable|extraordinary)", re.IGNORECASE),
    re.compile(r"masterpiece\s+that", re.IGNORECASE),
    re.compile(r"a\s+testament\s+to", re.IGNORECASE),
    # Generic GPT-ism clichés
    re.compile(r"truly\s+remarkable", re.IGNORECASE),
    re.compile(r"can['']t\s+help\s+but", re.IGNORECASE),
    re.compile(r"feast\s+for\s+the\s+(eyes|senses)", re.IGNORECASE),
    re.compile(r"invites\s+you\s+to\s+(explore|discover|reflect)", re.IGNORECASE),
    re.compile(r"step\s+into\s+a\s+world", re.IGNORECASE),
    re.compile(r"rich\s+tapestry\s+of", re.IGNORECASE),
    re.compile(r"journey\s+through\s+(time|history)", re.IGNORECASE),
    re.compile(r"stands?\s+as\s+a\s+testament", re.IGNORECASE),
    re.compile(r"explore\s+the\s+(rich|fascinating|incredible)", re.IGNORECASE),
    re.compile(r"immerse\s+yourself\s+in", re.IGNORECASE),
    re.compile(r"a\s+hidden\s+gem", re.IGNORECASE),
    re.compile(r"steeped\s+in\s+history", re.IGNORECASE),
    re.compile(r"transcends?\s+(time|boundaries)", re.IGNORECASE),
    re.compile(r"a\s+window\s+into", re.IGNORECASE),
    re.compile(r"breathtaking\s+(view|beauty|display)", re.IGNORECASE),
]


def scan_for_repetition(text: str) -> List[str]:
    """Scan text for forbidden/overused phrases.

    Args:
        text: The narration text to check.

    Returns:
        List of matched phrase strings found in the text.
        Empty list means text is clean.
    """
    if not text:
        return []

    matches = []
    for pattern in FORBIDDEN_PHRASES:
        found = pattern.findall(text)
        if found:
            # Get the full match context for reporting
            for m in pattern.finditer(text):
                matches.append(m.group(0))

    return matches
