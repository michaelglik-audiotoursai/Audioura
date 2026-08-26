"""
Derepetition Guard — catches overused/cliché phrases in tour narration.
========================================================================
Compiled from analysis of chagall_current_tour.txt and common GPT-isms.
Use scan_for_repetition() to check generated text before committing it.
"""
import re
from typing import List
from cost_rates import llm_cost as _llm_cost

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
        cost = _llm_cost(total_tokens=tokens)
        _log.info(f"Rewrite: {stop_name}/{story_type} | {tokens} tokens | ${cost:.4f}")
        return rewritten

    except Exception as e:
        _log.error(f"Rewrite error: {e}")
        return sentence


# ──────────────────────────────────────────────────────────────────────────────
# [LOCAL-47] Tour-title / location-name repetition cap
# ──────────────────────────────────────────────────────────────────────────────

def cap_location_repetition(tour_text: str, location_phrase: str, max_occurrences: int = 2) -> str:
    """Remove excess occurrences of the tour location phrase from generated text.
    
    When GPT over-references the tour title/location (e.g., "French Riviera biking tour"
    appears 6 times), this removes occurrences beyond max_occurrences while preserving
    sentence structure.
    
    Strategy: keep the first `max_occurrences`, for subsequent ones:
    - If the phrase is within a larger noun-phrase ("this French Riviera biking tour stop"),
      remove just the location phrase leaving the rest intact.
    - If it's a standalone clause ("on this French Riviera biking tour"), remove the
      entire clause-fragment.
    
    Args:
        tour_text: Full tour text.
        location_phrase: The phrase to cap (e.g., "French Riviera biking tour").
        max_occurrences: Maximum allowed occurrences (default 2).
        
    Returns:
        Modified tour text with excess occurrences removed or replaced.
    """
    if not tour_text or not location_phrase or len(location_phrase) < 5:
        return tour_text
    
    # Build case-insensitive pattern that captures surrounding context
    escaped = re.escape(location_phrase)
    # Match with optional surrounding articles/prepositions
    pattern = re.compile(
        r'(?:(?:this|the|our|your|a)\s+)?' + escaped + r'(?:\s+(?:stop|experience|adventure|journey))?',
        re.IGNORECASE
    )
    
    matches = list(pattern.finditer(tour_text))
    if len(matches) <= max_occurrences:
        return tour_text  # Within cap, nothing to do
    
    # Keep first N, replace rest
    result = tour_text
    # Process from end to preserve character offsets
    for match in reversed(matches[max_occurrences:]):
        start, end = match.start(), match.end()
        matched_text = match.group(0)
        
        # Check if removing would leave a broken sentence
        # Look for surrounding sentence context
        before = result[max(0, start - 20):start].rstrip()
        after = result[end:min(len(result), end + 20)].lstrip()
        
        # If preceded by "on/of/along/during" and followed by comma or period,
        # remove the whole prepositional phrase fragment
        if re.search(r'\b(on|of|along|during|in|across)\s*$', before):
            # Find the preposition start
            prep_match = re.search(r'\b(on|of|along|during|in|across)\s*$', before)
            if prep_match:
                prep_start = start - (len(before) - prep_match.start())
                # Also consume trailing comma if present
                if after.startswith(','):
                    result = result[:prep_start] + result[end + 1:]
                else:
                    result = result[:prep_start] + result[end:]
        else:
            # Simple removal — just strip the location phrase, keep surrounding words
            result = result[:start] + result[end:]
        
        # Clean up double spaces
        result = re.sub(r'  +', ' ', result)
        # Clean up orphaned punctuation from removals
        result = re.sub(r'\s+,', ',', result)
        result = re.sub(r',\s*,', ',', result)
    
    return result


def count_phrase_occurrences(text: str, phrase: str) -> int:
    """Count case-insensitive occurrences of a phrase in text."""
    if not text or not phrase:
        return 0
    return len(re.findall(re.escape(phrase), text, re.IGNORECASE))


# ---------------------------------------------------------------------------
# [D533] Cross-stop FACT repetition — Michael, 2026-08-26:
#   "make sure the same facts are not repeated not only in the same sentence and
#    in the same stop, but across all stops: listener should not listen the same
#    story many times."
#
# Why the existing check was not enough. `check_cross_stop_repetition` compares
# SENTENCES by Jaccard word overlap. On the Palais Lascaris run the two tellings
# of the museum's founding scored **0.692** against a 0.70 threshold and passed:
#
#   stop 1  "In 1942, the city of Nice purchased the Palais Lascaris, a
#            seventeenth-century aristocratic building, with the goal of
#            transforming it into a museum."
#   stop 3  "In 1942, the city of Nice purchased the seventeenth-century Palais
#            Lascaris with the intention of transforming it into a museum."
#
# Lowering the threshold would have caught that pair and would still miss the
# real target, because **the same fact can be told in words that barely overlap.**
# The listener does not hear word overlap; they hear the same thing twice.
#
# So this works on FACTS, not sentences. A fact signature is the pair
# (year, subject-entity) — the unit a listener actually remembers. The same
# (1942, palais lascaris) asserted in two stops is one story told twice however
# it is phrased.
# ---------------------------------------------------------------------------

_FACT_YEAR_RE = re.compile(r'\b(1[0-9]{3}|20[0-9]{2})\b')
_FACT_NAME_RE = re.compile(
    r'\b([A-ZÀ-Þ][\w\'’\-]+(?:\s+(?:de|du|van|von|della|di|le|la)?\s*[A-ZÀ-Þ][\w\'’\-]+)*)\b')

# Words that look like names at a sentence start but carry no fact.
_FACT_NAME_STOPWORDS = {
    'the', 'this', 'that', 'these', 'those', 'stand', 'pause', 'notice', 'look',
    'your', 'you', 'from', 'here', 'now', 'then', 'while', 'when', 'as', 'in',
    'at', 'on', 'it', 'its', 'a', 'an', 'and', 'but', 'orientation', 'directions',
    'stop', 'unlike', 'because', 'although', 'today', 'originally', 'following',
    'such', 'each', 'both', 'after', 'before', 'during',
}


# [D534] Content words that carry a fact when paired with a year. Proper nouns
# alone were not enough: the v2 tour told the 1946 monument classification twice
# as "its classification as a historical monument in 1946" (stop 1) and "the
# building was declared a historical monument by 1946" (stop 3). NEITHER has a
# capitalised subject — "this decision", "the building" — so a proper-noun
# signature is blind to both, and the sentences are worded differently enough
# that embeddings score them below any usable threshold once stop 3's extra
# clauses dilute the vector.
#
# A shared YEAR plus a shared uncommon noun is a strong joint signal: the year
# constrains it hard enough that "monument" alone cannot false-positive across
# unrelated facts.
_FACT_GENERIC_WORDS = {
    'museum', 'collection', 'collections', 'instrument', 'instruments', 'visitor',
    'visitors', 'listener', 'history', 'historical', 'century', 'centuries',
    'building', 'palace', 'city', 'public', 'cultural', 'culture', 'heritage',
    'important', 'significant', 'remarkable', 'crafted', 'created', 'housing',
    'featuring', 'including', 'showcasing', 'preserving', 'transformation',
    'transforming', 'stands', 'standing', 'placed', 'display', 'displayed',
}


def _fact_content_words(sentence, window=None):
    """Uncommon content words in a sentence — the noun half of a (year, X) fact."""
    words = re.findall(r"[a-zA-Zà-þ']{6,}", sentence or '')
    out = set()
    for w in words:
        import unicodedata
        f = unicodedata.normalize('NFKD', w.lower())
        f = ''.join(c for c in f if not unicodedata.combining(c))
        if f in _FACT_GENERIC_WORDS or f in _FACT_NAME_STOPWORDS:
            continue
        out.add(f)
    return out


def _fact_entities(sentence: str):
    """Capitalised entities in a sentence, folded, minus sentence-start noise."""
    import unicodedata
    ents = set()
    for m in _FACT_NAME_RE.findall(sentence or ''):
        f = unicodedata.normalize('NFKD', m.lower())
        f = ''.join(c for c in f if not unicodedata.combining(c)).strip()
        if not f or f in _FACT_NAME_STOPWORDS:
            continue
        if len(f) < 4:
            continue
        ents.add(f)
        # Also index the last token, so 'Palais Lascaris' and 'the Lascaris
        # palace' meet on 'lascaris'.
        parts = f.split()
        if len(parts) > 1 and parts[-1] not in _FACT_NAME_STOPWORDS and len(parts[-1]) >= 4:
            ents.add(parts[-1])
    return ents


# Lines that are not narration and must never contribute facts: the machine-
# readable scaffolding, and the closing recap whose whole JOB is to mention
# earlier stops again.
_FACT_SKIP_LINE = re.compile(
    r'^\s*(Stop\s+\d+:|Coordinates:|Directions:|Sources:|Tour-Category:|Orientation:\s*$)',
    re.IGNORECASE)
_FACT_RECAP = re.compile(r"That'?s\s+\d+\s+stops?\b|If you would like another", re.IGNORECASE)

# A year and an entity belong to the same fact only if they are near each other.
# Without this, one sentence listing three works with three dates yields nine
# cross-product "facts", and every later stop then looks like a repeat. That is
# exactly what stop 1's front-loaded orientation produced on the Palais run.
_FACT_PROXIMITY_CHARS = 120


def fact_signatures(sentence: str):
    """(year, entity) pairs asserted by a sentence — its atomic facts.

    Pairs are formed only within `_FACT_PROXIMITY_CHARS`, and list-shaped
    sentences (three or more years, or a recap) assert nothing and are skipped.
    """
    s = sentence or ''
    if _FACT_RECAP.search(s):
        return set()
    years = [(m.group(1), m.start()) for m in _FACT_YEAR_RE.finditer(s)]
    if not years or len(set(y for y, _ in years)) >= 3:
        return set()
    # [D534] Proper nouns AND uncommon content words. See the note above
    # `_FACT_GENERIC_WORDS`: the 1946 case has no proper noun at all.
    ents = _fact_entities(s) | _fact_content_words(s)
    if not ents:
        return set()
    sigs = set()
    low = s.lower()
    for ent in ents:
        # Position of the entity as it appears (accent-folded compare is done in
        # _fact_entities; here we locate the first plausible occurrence).
        pos = low.find(ent.split()[0])
        if pos < 0:
            pos = 0
        for year, ypos in years:
            if abs(ypos - pos) <= _FACT_PROXIMITY_CHARS:
                sigs.add((year, ent))
    return sigs


def _stop_blocks(tour_text: str):
    """Split a tour into (stop_number, block_text). Stop 1 is the first block."""
    parts = re.split(r'\n(Stop\s+\d+:)', tour_text or '')
    blocks = []
    for i in range(1, len(parts), 2):
        num = int(re.search(r'\d+', parts[i]).group())
        blocks.append((num, parts[i + 1] if i + 1 < len(parts) else ''))
    return blocks


def check_cross_stop_fact_repetition(tour_text: str, min_stops: int = 2):
    """Facts asserted in more than one stop.

    Returns [{signature, first_stop, repeat_stop, sentence}] — one entry per
    REPEAT (the first telling is never reported; it is the one to keep).
    """
    blocks = _stop_blocks(tour_text)
    if len(blocks) < min_stops:
        return []
    seen = {}          # signature -> (stop_number, sentence)
    repeats = []
    for num, block in blocks:
        # A stop repeating itself is a different problem; dedupe within the stop
        # first so one stop's two mentions do not both count against the next.
        local = set()
        # Drop the block's FIRST line: _stop_blocks splits on "Stop N:", so each
        # block opens with the stop TITLE, which _FACT_SKIP_LINE cannot match and
        # which otherwise reads as a fact ("... (Nuremberg, 1581)").
        _lines = block.split('\n')[1:]
        # [D534] Stop 1's ORIENTATION previews the whole tour, and Michael asked
        # for that to stay: "Stop 1's orientation: stop previewing later stops.
        # -- I actually like it." (2026-08-26). It must therefore never count as
        # the FIRST telling of anything, or every stop that describes its own
        # object gets flagged for repeating the preview — measured, it produced
        # four false positives on the v2 tour (1581/schnitzer and friends) and
        # would have had stop 2 regenerated for saying what it is there to say.
        if num == 1:
            _lines = [ln for ln in _lines
                      if not ln.strip().lower().startswith('orientation:')]
        narration = '\n'.join(ln for ln in _lines if not _FACT_SKIP_LINE.match(ln))
        for sent in _split_into_sentences(narration):
            for sig in fact_signatures(sent):
                if sig in local:
                    continue
                local.add(sig)
                if sig in seen and seen[sig][0] != num:
                    repeats.append({
                        'signature': f"{sig[0]}/{sig[1]}",
                        'first_stop': seen[sig][0],
                        'repeat_stop': num,
                        'sentence': sent,
                        'first_sentence': seen[sig][1],
                    })
                elif sig not in seen:
                    seen[sig] = (num, sent)
    return repeats


# A sentence opening with one of these points BACKWARDS. Delete the sentence it
# points at and the listener hears "This action set in motion a series of
# restorations" with no action ever named — which is exactly what happened on the
# 2026-08-26 re-run, at stops 2 and 3, caused by this guard's own removals.
#
# Deletion is safe for TRUTH (it cannot add a falsehood) but not for COHERENCE.
# So a removal that would orphan a back-reference is refused, and the repetition
# is kept instead: hearing a fact twice is a smaller harm than hearing a sentence
# that refers to nothing. Repairing the anaphor instead would mean generating
# replacement prose, which is the door this guard exists to keep shut.
_ANAPHORIC_OPENER = re.compile(
    r'^\s*(This|That|These|Those|Such|Its|His|Her|Their|It|They|As a result|'
    r'Consequently|Therefore|Thus|Following this|After this|Because of this|'
    r'In turn|Under their|Under his|Under her)\b',
    re.IGNORECASE)


def strip_repeated_facts(tour_text: str, min_remaining_words: int = 60):
    """Delete later re-tellings of a fact already told at an earlier stop.

    **Deletion, not rewriting** — the same reasoning as `story_fact_guard`: a
    rewrite has to assert something, and all we know is that this sentence is
    redundant. Removing it cannot introduce a falsehood.

    A stop is never stripped below `min_remaining_words`; a thin stop keeps its
    repeated sentence and the caller is told, because an empty stop is worse for
    the listener than a repeated one.

    Returns (new_text, actions) where actions have 'removed': bool.
    """
    repeats = check_cross_stop_fact_repetition(tour_text)
    if not repeats:
        return tour_text, []
    out, actions = tour_text, []
    # One sentence can carry several repeated signatures; remove it once.
    handled = set()
    for r in repeats:
        sent = r['sentence']
        if sent in handled:
            continue
        handled.add(sent)
        blocks = dict(_stop_blocks(out))
        block = blocks.get(r['repeat_stop'], '')
        if sent not in block:
            actions.append(dict(r, removed=False, reason='sentence not in stop block'))
            continue
        if len(block.split()) - len(sent.split()) < min_remaining_words:
            actions.append(dict(r, removed=False, reason='stop would fall below minimum'))
            continue
        # Would removing this sentence orphan the one after it?
        _tail = block.split(sent, 1)[1] if sent in block else ''
        _next = next((s for s in _split_into_sentences(_tail) if s.strip()), '')
        if _next and _ANAPHORIC_OPENER.match(_next):
            actions.append(dict(r, removed=False,
                                reason=f'next sentence refers back to it ("{_next[:40]}...")'))
            continue
        new_block = block.replace(sent, '', 1)
        new_block = re.sub(r'[ \t]{2,}', ' ', new_block)
        out = out.replace(block, new_block, 1)
        actions.append(dict(r, removed=True, reason=''))
    return out, actions


# ---------------------------------------------------------------------------
# [D534] GENERIC cross-stop repetition — Michael, 2026-08-26:
#   "error identification should have triggered in this generic case, try it and
#    try a more generous solution: ANY information should not be repeated among
#    stops of the tour."
#
# He is right and the case he found proves it. The v2 tour told the 1946 monument
# classification at stop 1 AND stop 3:
#
#   stop 1  "This pivotal decision set the stage for its classification as a
#            historical monument in 1946."
#   stop 3  "The building was declared a historical monument by 1946..."
#
# Both carry the year. The (year, entity) signature STILL missed them, because
# neither sentence contains a capitalised entity — "this decision", "the
# building". A signature keyed on proper nouns cannot see a fact whose subject is
# a pronoun or a definite description, and that is most sentences in running
# prose.
#
# Word overlap misses it too: Jaccard here is ~0.35.
#
# So the generic instrument is MEANING, which means embeddings. Two sentences
# that say the same thing land near each other in embedding space however they
# are worded, whatever their subjects are called, dated or not.
#
# EXEMPT, deliberately: stop 1's Orientation and the closing recap. Michael,
# 2026-08-26: "Stop 1's orientation: stop previewing later stops. -- I actually
# like it." The preview and the recap are SUPPOSED to restate other stops; a
# generic no-repetition rule would strip exactly the thing he asked to keep.
# ---------------------------------------------------------------------------

_EMBED_MODEL = 'text-embedding-3-small'


def _embed(texts, api_key, model=None, timeout=60):
    """Batch-embed. Returns list of vectors, or None if the call did not run."""
    if not texts or not api_key:
        return None
    import json
    import requests
    try:
        resp = requests.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            data=json.dumps({"model": model or _EMBED_MODEL, "input": texts}),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        return [d['embedding'] for d in resp.json()['data']]
    except Exception:
        return None


def _cosine(a, b):
    num = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return num / (na * nb) if na and nb else 0.0


def narration_sentences_by_stop(tour_text, skip_first_orientation=True):
    """[(stop_number, sentence)] for real narration only.

    Scaffolding, the closing recap, and — by Michael's instruction — stop 1's
    orientation preview are excluded.
    """
    out = []
    for num, block in _stop_blocks(tour_text or ''):
        # First line is the stop TITLE (see the note in
        # check_cross_stop_fact_repetition) — never narration.
        for line in block.split('\n')[1:]:
            if _FACT_SKIP_LINE.match(line) or not line.strip():
                continue
            body = line
            if line.strip().lower().startswith('orientation:'):
                if num == 1 and skip_first_orientation:
                    continue
                body = line.split(':', 1)[1]
            for sent in _split_into_sentences(body):
                s = sent.strip()
                if len(s.split()) >= 6 and not _FACT_RECAP.search(s):
                    out.append((num, s))
    return out


def check_cross_stop_semantic_repetition(tour_text, api_key, threshold=0.82):
    """ANY information restated at a later stop, however worded.

    Returns [{first_stop, repeat_stop, first_sentence, sentence, similarity}],
    one per repeat, later telling second. Empty list if the check could not run —
    and the caller must treat that as UNKNOWN, not as clean.
    """
    pairs = narration_sentences_by_stop(tour_text)
    if len(pairs) < 2:
        return []
    vecs = _embed([s for _, s in pairs], api_key)
    if vecs is None:
        return []
    out = []
    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            (sa, ta), (sb, tb) = pairs[i], pairs[j]
            if sa == sb:
                continue
            sim = _cosine(vecs[i], vecs[j])
            if sim >= threshold:
                first, second = (sa, ta), (sb, tb)
                if sb < sa:
                    first, second = (sb, tb), (sa, ta)
                out.append({
                    'first_stop': first[0], 'first_sentence': first[1],
                    'repeat_stop': second[0], 'sentence': second[1],
                    'similarity': round(sim, 3),
                })
    # Strongest first, so a capped repair fixes the worst offenders.
    return sorted(out, key=lambda d: -d['similarity'])


def repeated_assertions_by_stop(tour_text, api_key, threshold=0.82):
    """{stop_number: [assertion, ...]} — what each stop restates from earlier.

    Feeds the PHASE 5.17 regeneration ban list. The ASSERTION handed over is the
    EARLIER telling, not the later one: LOCAL-476 established that naming the
    sentence teaches the model which words to avoid, while naming the underlying
    claim is the only form a paraphrase cannot satisfy.
    """
    by_stop = {}
    for r in check_cross_stop_semantic_repetition(tour_text, api_key, threshold):
        by_stop.setdefault(r['repeat_stop'], [])
        if r['first_sentence'] not in by_stop[r['repeat_stop']]:
            by_stop[r['repeat_stop']].append(r['first_sentence'])
    return by_stop
