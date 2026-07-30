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
    re.compile(r"vibrant\s+colou?rs?\s*(and|of|that)", re.IGNORECASE),
    re.compile(r"dreamlike\s+(imagery|quality|world|scene|composition)", re.IGNORECASE),
    re.compile(r"deep\s+connection\s+to", re.IGNORECASE),
    re.compile(r"(his|her|their)\s+Jewish\s+heritage", re.IGNORECASE),
    re.compile(r"intricate\s+details?", re.IGNORECASE),
    re.compile(r"timeless\s+themes?", re.IGNORECASE),
    re.compile(r"position\s+yourself\s+in\s+the\s+center", re.IGNORECASE),
    re.compile(r"the\s+artist['']?s?\s+(unique|remarkable|extraordinary)", re.IGNORECASE),
    re.compile(r"masterpiece\s+that", re.IGNORECASE),
    re.compile(r"a\s+testament\s+to", re.IGNORECASE),
    re.compile(r"creative\s+genius", re.IGNORECASE),
    re.compile(r"stir(s|ring)?\s+the\s+soul", re.IGNORECASE),
    re.compile(r"touch(es|ing)?\s+(the|our|your)\s+(heart|soul)", re.IGNORECASE),
    re.compile(r"pulsate\w*\s+with\s+life", re.IGNORECASE),
    re.compile(r"symphony\s+of\s+(emotions?|colou?rs?)", re.IGNORECASE),
    re.compile(r"tapestry\s+of\s+(dreams?|emotions?)", re.IGNORECASE),
    re.compile(r"weaves?\s+a\s+narrative", re.IGNORECASE),
    re.compile(r"(captivating|mesmerizing)\s+(artistry|world|vision)", re.IGNORECASE),
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
    re.compile(r"let\s+(your|the)\s+(curiosity|imagination)\s+guide", re.IGNORECASE),
    re.compile(r"beacon\s+of\s+(creativity|hope|light)", re.IGNORECASE),
    re.compile(r"gaze\s+upon\s+this", re.IGNORECASE),
    re.compile(r"power\s+of\s+art\s+to", re.IGNORECASE),
    # [LOCAL-40] Unsupported praise patterns — assertions that name without explaining
    re.compile(r"echoing\s+the\s+eternal\s+cycles", re.IGNORECASE),
    re.compile(r"fully\s+immerse\s+yourself\s+in\s+the", re.IGNORECASE),
    re.compile(r"the\s+rich\s+cultural\s+heritage\s+of", re.IGNORECASE),
    re.compile(r"each\s+(intricate\s+)?detail\s+tells\s+a\s+story", re.IGNORECASE),
    re.compile(r"to\s+fully\s+(appreciate|understand|immerse|experience)", re.IGNORECASE),
    re.compile(r"a\s+(stunning|exquisite|mesmerizing)\s+example\s+of", re.IGNORECASE),
    # [LOCAL-44] Preaching/instructive patterns — telling the listener what to feel or do
    re.compile(r"as\s+you\s+stand\s+(before|here|in\s+front)[^,]*,?\s*(consider|reflect|ponder|let)", re.IGNORECASE),
    re.compile(r"let\s+the\s+whispers?\s+of\s+the\s+past", re.IGNORECASE),
    re.compile(r"take\s+a\s+moment\s+to\s+(appreciate|reflect|consider|absorb)", re.IGNORECASE),
    re.compile(r"allow\s+(yourself|your\s+imagination)\s+to", re.IGNORECASE),
    re.compile(r"carry\s+(this|these|the)\s+\w+\s+with\s+you", re.IGNORECASE),
    re.compile(r"what\s+other\s+(tales?|stories?|secrets?|treasures?|wonders?)\s+(of|await|might)", re.IGNORECASE),
    re.compile(r"to\s+truly\s+(appreciate|understand)\s+(the\s+significance|this)", re.IGNORECASE),
    re.compile(r"it\s+is\s+(worth|important)\s+(noting|to\s+note|to\s+understand)", re.IGNORECASE),
    re.compile(r"the\s+next\s+journey\s+awaits", re.IGNORECASE),
    re.compile(r"ask\s+museum\s+staff\s+for\s+directions", re.IGNORECASE),
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


def _jaccard_similarity(words_a: set, words_b: set) -> float:
    """Word-level Jaccard similarity between two sets."""
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _split_into_sentences(text: str) -> List[str]:
    """Split text into sentences (simple regex, no external libs)."""
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if len(s.strip()) > 20]


def _tokenize(sentence: str) -> set:
    """Tokenize a sentence into lowercase word set (stopwords removed)."""
    import re
    _STOP_WORDS = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'shall', 'can', 'to', 'of', 'in', 'for',
        'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during',
        'before', 'after', 'above', 'below', 'and', 'but', 'or', 'nor', 'not',
        'so', 'yet', 'both', 'either', 'neither', 'each', 'every', 'all',
        'any', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'only',
        'own', 'same', 'than', 'too', 'very', 'just', 'because', 'this',
        'that', 'these', 'those', 'it', 'its', 'you', 'your', 'we', 'our',
        'they', 'their', 'his', 'her', 'him', 'she', 'he', 'i', 'me', 'my',
    }
    words = set(re.findall(r'[a-z]+', sentence.lower()))
    return words - _STOP_WORDS


def check_cross_stop_repetition(tour_text: str, threshold: float = 0.70) -> List[dict]:
    """Find near-duplicate sentences across different stops in a tour.

    Splits the tour text into per-stop blocks (separated by common stop markers),
    extracts sentences, and finds pairs with word-overlap Jaccard > threshold.

    Args:
        tour_text: Full tour narration text.
        threshold: Jaccard similarity threshold (default 0.85).

    Returns:
        List of dicts: {stop_a, stop_b, sentence_a, sentence_b, similarity}
        Empty list if no cross-stop repetition found.
    """
    import re

    if not tour_text or len(tour_text) < 100:
        return []

    # Split into stops — look for "Stop N:" pattern (most common in our tours)
    stop_blocks = re.split(r'\nStop\s+\d+[:.]\s*', tour_text)
    # Filter out tiny blocks (likely separators or headers)
    stop_blocks = [b.strip() for b in stop_blocks if len(b.strip()) > 50]

    if len(stop_blocks) < 2:
        # Try splitting by numbered lines "1." or double newlines
        stop_blocks = re.split(r'\n(?:\d+)\.\s+', tour_text)
        stop_blocks = [b.strip() for b in stop_blocks if len(b.strip()) > 50]

    if len(stop_blocks) < 2:
        # Last resort: paragraph breaks
        stop_blocks = [b.strip() for b in tour_text.split('\n\n') if len(b.strip()) > 50]

    if len(stop_blocks) < 2:
        return []

    # Extract sentences per stop with their tokenized forms
    stop_sentences = []
    for i, block in enumerate(stop_blocks):
        sentences = _split_into_sentences(block)
        for sent in sentences:
            tokens = _tokenize(sent)
            if len(tokens) >= 4:  # Skip very short sentences
                stop_sentences.append((i, sent, tokens))

    # Compare all pairs across different stops
    duplicates = []
    for i in range(len(stop_sentences)):
        for j in range(i + 1, len(stop_sentences)):
            stop_a, sent_a, tokens_a = stop_sentences[i]
            stop_b, sent_b, tokens_b = stop_sentences[j]

            # Only compare across different stops
            if stop_a == stop_b:
                continue

            sim = _jaccard_similarity(tokens_a, tokens_b)
            if sim >= threshold:
                duplicates.append({
                    "stop_a": stop_a + 1,
                    "stop_b": stop_b + 1,
                    "sentence_a": sent_a[:100],
                    "sentence_b": sent_b[:100],
                    "similarity": round(sim, 3),
                })

    return duplicates


def rewrite_repeated_sentence(
    sentence: str,
    stop_name: str,
    story_type: str,
    api_key: str,
) -> str:
    """Rewrite a repeated/cliché sentence in the voice of its story_type.

    Uses GPT-3.5-turbo to produce a fresh version that:
    - Preserves the factual content
    - Uses the tone appropriate to story_type
    - Avoids all forbidden phrases
    - Is 1–2 sentences

    Args:
        sentence: The flagged sentence to rewrite.
        stop_name: The POI/stop this sentence belongs to.
        story_type: One of the 6 taxonomy types (history, anecdote, etc.).
        api_key: OpenAI API key.

    Returns:
        Rewritten sentence (1–2 sentences). Original on failure.
    """
    import json as _json
    import requests as _requests
    import logging as _logging

    _log = _logging.getLogger(__name__)

    # Load forbidden phrases for this story_type from taxonomy
    try:
        taxonomy = _json.load(open("story_type_taxonomy.json"))
        type_entry = next((t for t in taxonomy["types"] if t["type"] == story_type), None)
        type_forbidden = type_entry["forbidden_phrases"] if type_entry else []
    except Exception:
        type_forbidden = []

    # Compile full ban list
    ban_list = type_forbidden + [
        "vibrant colors", "dreamlike imagery", "intricate details",
        "timeless themes", "deep connection", "truly remarkable",
        "rich tapestry", "hidden gem", "steeped in history",
    ]

    prompt = (
        f"Rewrite this sentence about '{stop_name}' in the voice of a {story_type} narrator.\n\n"
        f"Original: \"{sentence}\"\n\n"
        f"Rules:\n"
        f"- Keep the same factual content.\n"
        f"- Write 1–2 sentences maximum.\n"
        f"- DO NOT USE these phrases: {', '.join(ban_list)}\n"
        f"- Make it fresh, specific, and engaging.\n\n"
        f"Return ONLY the rewritten sentence(s), no quotes or explanation."
    )

    try:
        response = _requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "You are a creative writing editor. Return only the rewritten text."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.8,
                "max_tokens": 150,
            },
            timeout=10,
        )

        if response.status_code != 200:
            _log.error(f"Rewrite API error: {response.status_code}")
            return sentence

        result = response.json()
        rewritten = result["choices"][0]["message"]["content"].strip().strip('"')
        tokens = result.get("usage", {}).get("total_tokens", 0)
        cost = tokens / 1000 * 0.002
        _log.info(f"Rewrite: {stop_name}/{story_type} | {tokens} tokens | ${cost:.4f}")
        return rewritten

    except Exception as e:
        _log.error(f"Rewrite error: {e}")
        return sentence
