#!/usr/bin/env python3
"""subject_validate_expand.py — LOCAL-237: Gather, Validate, Expand, Remove.

Michael's instruction (2026-08-05):
  "create a routine with or without AI API call to gather a subject matter in
   the sentence or paragraph and then validate, expand, and if cannot expand
   [remove]."

Four stages:
  1. GATHER  — per sentence: what is it about, and does it make a promise?
  2. VALIDATE — is the subject true and sourceable?
  3. EXPAND  — replace the promise with delivered story, using only the source.
  4. REMOVE  — only if expansion fails.

Design constraints:
  - Expansion MUST quote the source sentence it drew from (D127).
  - No expansion on stops failing LOCAL-236's existence check.
  - Deterministic where possible; LLM permitted for subject extraction only.
  - Reuses external_claim_verify for search (do not build a second search path).
  - Behind DISABLE_SUBJECT_ROUTINE=1.
  - Cost ceiling $0.45 total.

Does NOT modify:
  - claim_check.py, external_claim_verify.py, style_validator_detector.py (D55)
  - DECISIONS.md, CLAUDE.md, .continuous_dev/* (D48)
"""

import os
import re
import sys
import json
import logging
import unicodedata
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
from db_connection import get_connection

logger = logging.getLogger("subject_validate_expand")

# ─── Feature flag ────────────────────────────────────────────────────────────

def is_subject_routine_enabled() -> bool:
    """Check if subject routine is enabled (default: enabled).
    Set DISABLE_SUBJECT_ROUTINE=1 to disable."""
    return os.environ.get('DISABLE_SUBJECT_ROUTINE', '').strip() != '1'


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 1: GATHER — Promise detection
# ═══════════════════════════════════════════════════════════════════════════════

# Promise signal words: a sentence that names a story/tale/history/legacy/
# connection/testament without delivering it.
_PROMISE_NOUNS = {
    'story', 'stories', 'tale', 'tales', 'history', 'legacy', 'legacies',
    'connection', 'connections', 'testament', 'secret', 'secrets',
    'mystery', 'mysteries', 'wonder', 'wonders', 'chapter', 'chapters',
    'narrative', 'narratives', 'saga', 'tradition', 'traditions',
    'tapestry', 'allure', 'charm', 'spirit', 'essence',
}

# Phrases that signal a promise without delivery
_PROMISE_PATTERNS = [
    # "holding a story" / "each crack holding a story"
    re.compile(r'\bholding\s+a\s+(?:' + '|'.join(_PROMISE_NOUNS) + r')\b', re.I),
    # "tales from a bygone era" / "tales of X"
    re.compile(r'\b(?:tales?|stories?)\s+(?:from|of)\s+(?:a\s+)?(?:bygone|ancient|forgotten|rich|'
               r'past|lost|old|historic)', re.I),
    # "whisper tales" / "whispers tales"
    re.compile(r'\bwhispers?\s+(?:tales?|stories?|secrets?)\b', re.I),
    # "a testament to" without following specifics
    re.compile(r'\ba\s+testament\s+to\s+(?:the\s+)?(?:enduring|timeless|rich|lasting)', re.I),
    # "steeped in history" / "rich tapestry of history"
    re.compile(r'\b(?:steeped|bathed|drenched|soaked)\s+in\s+(?:history|tradition|legend)', re.I),
    re.compile(r'\b(?:rich|vivid|intricate)\s+tapestry\s+of\s+(?:history|culture|tradition)', re.I),
    # "inviting you to ponder the enduring legacy"
    re.compile(r'\b(?:inviting|beckoning|urging)\s+(?:you|us|visitors?)\s+to\s+(?:ponder|consider|'
               r'contemplate|explore|discover|uncover)\s+(?:the\s+)?(?:enduring|timeless|rich|'
               r'hidden|forgotten)', re.I),
    # "multitude of tales" / "hold(s) X tales/stories"
    re.compile(r'\b(?:multitude|wealth|treasure|trove)\s+of\s+(?:' + '|'.join(_PROMISE_NOUNS) + r')\b', re.I),
    re.compile(r'\bholds?\s+(?:a\s+)?(?:multitude|wealth|many|countless)\s+(?:of\s+)?(?:'
               + '|'.join(_PROMISE_NOUNS) + r')\b', re.I),
    # "remember X, a testament to"
    re.compile(r'\bremember\s+\w+.*?\ba\s+testament\s+to\b', re.I),
    # "serves as a bridge between" (metaphorical without evidence)
    re.compile(r'\bserves?\s+as\s+a\s+(?:bridge|gateway|window|portal)\s+between\b', re.I),
    # "the connection between past and present becomes tangible"
    re.compile(r'\bconnection\s+between\s+(?:past|ancient|old)\s+and\s+(?:present|modern|'
               r'contemporary|new)\s+(?:becomes?|is)\s+(?:tangible|real|palpable)', re.I),
    # "symphony of past and present"
    re.compile(r'\b(?:symphony|harmony|blend|fusion)\s+of\s+(?:past|old|ancient)\s+and\s+'
               r'(?:present|modern|new)', re.I),
]

# Delivery indicators: if a sentence has these, it IS delivering (not just promising)
_DELIVERY_SIGNALS = [
    # Specific dates/years
    re.compile(r'\b(?:1[0-9]{3}|20[0-2][0-9])\b'),
    # Named people (proper noun + verb of creation/action)
    re.compile(r'\b[A-Z][a-z]+\s+(?:built|designed|created|founded|painted|wrote|composed|'
               r'established|constructed|commissioned|completed|opened)\b'),
    # Quoted titles
    re.compile(r'[""\u201c].{3,50}[""\u201d]'),
    # Measurements with units
    re.compile(r'\b\d+(?:\.\d+)?\s*(?:km|meters?|metres?|feet|ft|miles?|hectares?)\b', re.I),
]


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences. Handles abbreviations and common patterns."""
    # Simple sentence splitter that handles Mr./Mrs./Dr./etc.
    text = re.sub(r'([.!?])\s+', r'\1\n', text)
    sentences = [s.strip() for s in text.split('\n') if s.strip()]
    return sentences


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', _strip_accents(text).lower()).strip()


def _sentence_is_delivering(sentence: str) -> bool:
    """Check if a sentence is actually delivering content (dates, names, facts)."""
    for pattern in _DELIVERY_SIGNALS:
        if pattern.search(sentence):
            return True
    return False


def gather_promises(paragraph: str) -> List[Dict]:
    """Stage 1: Identify sentences that make promises without delivering.

    Returns list of {sentence, promise_type, subject_span, index}.
    A "promise" is a sentence that names a story/tale/history/legacy/connection
    without giving the actual content.
    """
    sentences = _split_sentences(paragraph)
    promises = []

    for idx, sentence in enumerate(sentences):
        # Skip sentences that ARE delivering (have dates, proper nouns with predicates, etc.)
        if _sentence_is_delivering(sentence):
            continue

        # Check each promise pattern
        for pattern in _PROMISE_PATTERNS:
            match = pattern.search(sentence)
            if match:
                # Extract what subject is being promised about
                subject = _extract_promise_subject(sentence)
                promises.append({
                    'sentence': sentence,
                    'promise_type': _classify_promise_type(match.group()),
                    'subject_span': match.group(),
                    'subject': subject,
                    'index': idx,
                })
                break  # One match per sentence is enough

    return promises


def _classify_promise_type(matched_text: str) -> str:
    """Classify the type of promise being made."""
    lower = matched_text.lower()
    if any(w in lower for w in ('tale', 'story', 'narrative', 'saga')):
        return 'UNNAMED_STORY'
    if any(w in lower for w in ('testament', 'legacy', 'spirit')):
        return 'VAGUE_LEGACY'
    if any(w in lower for w in ('tapestry', 'history', 'steeped')):
        return 'ABSTRACT_HISTORY'
    if any(w in lower for w in ('bridge', 'connection', 'symphony')):
        return 'METAPHORICAL_LINK'
    if any(w in lower for w in ('inviting', 'beckoning', 'ponder')):
        return 'INVITATION_TO_DISCOVER'
    return 'GENERIC_PROMISE'


def _extract_promise_subject(sentence: str) -> str:
    """Extract the subject being promised about from the sentence.

    Looks for proper nouns, named entities, or the grammatical subject.
    Filters out common false positives (sentence-initial capitalization,
    pronouns like "Here", "This").
    """
    _NOT_SUBJECTS = {'Here', 'There', 'This', 'That', 'These', 'Those',
                     'The', 'As', 'It', 'Its', 'In', 'On', 'At', 'From',
                     'With', 'You', 'Your', 'We', 'They'}

    # Try to find proper nouns (multi-word first, then single)
    # Multi-word proper nouns: "Eze Village", "French Riviera", "Cap d'Antibes"
    multi_pn = re.findall(r'\b[A-Z][a-z]+(?:[\s\'-]+[A-Zd][a-z]+)+\b', sentence)
    candidates = [pn for pn in multi_pn if pn.split()[0] not in _NOT_SUBJECTS]
    if candidates:
        return candidates[0]

    # Single proper nouns
    single_pn = re.findall(r'\b[A-Z][a-z]{2,}\b', sentence)
    candidates = [pn for pn in single_pn if pn not in _NOT_SUBJECTS]
    if candidates:
        return candidates[0]

    # Try to find "of X" or "the X" near promise words
    of_match = re.search(r'\bof\s+(?:the\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', sentence)
    if of_match and of_match.group(1) not in _NOT_SUBJECTS:
        return of_match.group(1)

    # Look for the grammatical subject: "The [noun]" patterns
    the_match = re.match(r'^(?:The|This|That)\s+(\w{3,}(?:\s+\w{3,})?)', sentence)
    if the_match:
        subj = the_match.group(1)
        # Avoid generic subjects like "timeless allure" or "aged stone"
        if not any(w in subj.lower() for w in ('timeless', 'enduring', 'mystical',
                                                 'gentle', 'aged', 'ancient')):
            return subj
        # Still return it but mark as weak
        return subj

    return "(unresolved)"


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 2: VALIDATE — Check subject against corpus, then external sources
# ═══════════════════════════════════════════════════════════════════════════════

def validate_subject(subject: str, stop_title: str, venue_name: str = "",
                     conn=None) -> Dict:
    """Stage 2: Validate whether the subject can be sourced.

    Search order:
      1. stop_corpus — passages for this specific stop
      2. venue_corpus — broader venue material
      3. external sources via external_claim_verify's search path

    Returns: {
        found: bool,
        source: 'stop_corpus' | 'venue_corpus' | 'external' | None,
        passage: str (the supporting sentence),
        url: str | None,
        tier: int | None,
    }
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        result = _check_stop_corpus(subject, stop_title, conn)
        if result['found']:
            return result

        result = _check_venue_corpus(subject, venue_name, conn)
        if result['found']:
            return result

        result = _check_external(subject, stop_title, venue_name)
        return result
    finally:
        if close_conn:
            conn.close()


def _check_stop_corpus(subject: str, stop_title: str, conn) -> Dict:
    """Check stop_corpus for passages mentioning the subject."""
    cur = conn.cursor()
    cur.execute(
        "SELECT passages_json FROM stop_corpus WHERE stop_title = %s",
        (stop_title,)
    )
    row = cur.fetchone()
    cur.close()

    if not row or not row[0]:
        return {'found': False, 'source': None, 'passage': None, 'url': None, 'tier': None}

    passages = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    subject_norm = _normalize(subject)
    subject_tokens = set(re.findall(r'[a-z0-9]+', subject_norm))

    for passage in passages:
        text = passage if isinstance(passage, str) else passage.get('text', '')
        passage_norm = _normalize(text)
        # Check if subject tokens appear in passage
        passage_tokens = set(re.findall(r'[a-z0-9]+', passage_norm))
        overlap = subject_tokens & passage_tokens
        # Need at least 60% of subject tokens present
        if len(subject_tokens) > 0 and len(overlap) / len(subject_tokens) >= 0.6:
            return {
                'found': True,
                'source': 'stop_corpus',
                'passage': text,
                'url': None,
                'tier': 1,  # Corpus is tier 1
            }

    return {'found': False, 'source': None, 'passage': None, 'url': None, 'tier': None}


def _check_venue_corpus(subject: str, venue_name: str, conn) -> Dict:
    """Check venue_corpus for material mentioning the subject."""
    if not venue_name:
        return {'found': False, 'source': None, 'passage': None, 'url': None, 'tier': None}

    cur = conn.cursor()
    cur.execute(
        "SELECT pages_json FROM venue_corpus WHERE venue_name = %s",
        (venue_name,)
    )
    row = cur.fetchone()
    cur.close()

    if not row or not row[0]:
        return {'found': False, 'source': None, 'passage': None, 'url': None, 'tier': None}

    pages = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    subject_norm = _normalize(subject)
    subject_tokens = set(re.findall(r'[a-z0-9]+', subject_norm))

    for page in pages:
        text = page if isinstance(page, str) else page.get('text', page.get('content', ''))
        if not text:
            continue
        # Split into sentences and check each
        page_sentences = re.split(r'[.!?]\s+', text)
        for sent in page_sentences:
            sent_norm = _normalize(sent)
            sent_tokens = set(re.findall(r'[a-z0-9]+', sent_norm))
            overlap = subject_tokens & sent_tokens
            if len(subject_tokens) > 0 and len(overlap) / len(subject_tokens) >= 0.6:
                url = page.get('url', None) if isinstance(page, dict) else None
                return {
                    'found': True,
                    'source': 'venue_corpus',
                    'passage': sent.strip(),
                    'url': url,
                    'tier': 2,
                }

    return {'found': False, 'source': None, 'passage': None, 'url': None, 'tier': None}


def _check_external(subject: str, stop_title: str, venue_name: str) -> Dict:
    """Check external sources via the existing external_claim_verify search path.

    Reuses work_story_searcher._serp_search() and story_miner._fetch_page_text().
    """
    from work_story_searcher import _serp_search
    from story_miner import _fetch_page_text
    from external_claim_verify import classify_source_tier
    from cost_rates import SERPER_COST_PER_QUERY

    # Build a targeted query
    city = ""
    if venue_name:
        parts = venue_name.split(',')
        if len(parts) > 1:
            city = parts[1].strip()

    query = f'"{subject}" {stop_title} {city}'.strip()
    if len(query) > 200:
        query = query[:200]

    serp_results, _latency = _serp_search(query)
    if not serp_results:
        return {'found': False, 'source': None, 'passage': None, 'url': None, 'tier': None,
                'cost': SERPER_COST_PER_QUERY}

    # Check top results
    for sr in serp_results[:3]:
        url = sr.get('url', '')
        tier = classify_source_tier(url)
        if tier == 0:
            continue

        # First check snippet
        snippet = sr.get('snippet', '')
        if snippet and _normalize(subject) in _normalize(snippet):
            return {
                'found': True,
                'source': 'external',
                'passage': snippet,
                'url': url,
                'tier': tier,
                'cost': SERPER_COST_PER_QUERY,
            }

        # Fetch page for deeper search
        page_text, _ = _fetch_page_text(url, max_chars=15000)
        if not page_text:
            continue

        # Find sentences mentioning the subject
        subject_tokens = set(re.findall(r'[a-z0-9]+', _normalize(subject)))
        page_sentences = re.split(r'[.!?]\s+', page_text)
        for sent in page_sentences[:100]:
            sent_norm = _normalize(sent)
            sent_tokens = set(re.findall(r'[a-z0-9]+', sent_norm))
            overlap = subject_tokens & sent_tokens
            if len(subject_tokens) > 0 and len(overlap) / len(subject_tokens) >= 0.6:
                return {
                    'found': True,
                    'source': 'external',
                    'passage': sent.strip(),
                    'url': url,
                    'tier': tier,
                    'cost': SERPER_COST_PER_QUERY,
                }

    return {'found': False, 'source': None, 'passage': None, 'url': None, 'tier': None,
            'cost': SERPER_COST_PER_QUERY}


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 3: EXPAND — Rewrite promise using ONLY the sourced passage
# ═══════════════════════════════════════════════════════════════════════════════

def _source_relates_to_promise(source_passage: str, promise_sentence: str) -> bool:
    """Check if the source passage actually relates to what the promise is about.

    Prevents replacing a promise about history/legacy with source material
    about transport schedules or restaurant recommendations.
    """
    # Extract the semantic domain of the promise
    promise_lower = promise_sentence.lower()
    promise_domains = set()
    if any(w in promise_lower for w in ('history', 'historical', 'past', 'ancient',
                                         'bygone', 'era', 'century', 'centuries')):
        promise_domains.add('history')
    if any(w in promise_lower for w in ('story', 'stories', 'tale', 'tales',
                                         'narrative', 'saga')):
        promise_domains.add('narrative')
    if any(w in promise_lower for w in ('legacy', 'testament', 'spirit', 'charm')):
        promise_domains.add('heritage')
    if any(w in promise_lower for w in ('culture', 'cultural', 'art', 'artist')):
        promise_domains.add('culture')

    # Check if source has material in the same domain
    source_lower = source_passage.lower()
    source_domains = set()
    if any(w in source_lower for w in ('history', 'historical', 'founded', 'established',
                                        'built', 'century', '1800', '1900', 'ancient',
                                        'medieval', 'roman')):
        source_domains.add('history')
    if any(w in source_lower for w in ('story', 'tale', 'legend', 'famous',
                                        'known for', 'notable')):
        source_domains.add('narrative')
    if any(w in source_lower for w in ('heritage', 'monument', 'listed', 'preserved',
                                        'tradition', 'cultural')):
        source_domains.add('heritage')
    if any(w in source_lower for w in ('art', 'artist', 'museum', 'paint', 'sculpt',
                                        'gallery', 'exhibition')):
        source_domains.add('culture')

    # If promise has a domain and source has NO overlap, reject
    if promise_domains and not (promise_domains & source_domains):
        return False
    return True


def expand_promise(promise_sentence: str, source_passage: str, subject: str,
                   stop_title: str, source_url: Optional[str] = None,
                   source_tier: Optional[int] = None) -> Dict:
    """Stage 3: Expand a promise sentence into delivered content.

    Uses ONLY the source passage — never parametric memory.
    The expansion must quote the source sentence it drew from.

    If the source passage does not contain enough material to deliver
    a meaningful replacement, returns {expanded: False} → triggers removal.

    Args:
        promise_sentence: The original sentence making the promise.
        source_passage: The validated source text to expand from.
        subject: The subject being promised about.
        stop_title: The stop name for context.
        source_url: URL of the source (for attribution).
        source_tier: Trust tier of the source.

    Returns: {
        expanded: bool,
        new_sentence: str | None,
        source_quoted: str,  # The specific clause drawn from source
        url: str | None,
        tier: int | None,
        method: 'deterministic' | 'llm',
    }
    """
    # Try deterministic expansion first: extract a factual sentence from
    # the source that relates to the subject and can replace the promise.
    deterministic = _try_deterministic_expansion(promise_sentence, source_passage, subject)
    if deterministic:
        return {
            'expanded': True,
            'new_sentence': deterministic['replacement'],
            'source_quoted': deterministic['quoted_from'],
            'url': source_url,
            'tier': source_tier,
            'method': 'deterministic',
        }

    # If the source passage is too short or too generic to extract a meaningful
    # replacement, try LLM-based rewrite (bounded by source only).
    # But ONLY if the source actually relates to the promise's subject matter.
    # A source about transport/access does not deliver a promise about legacy/history.
    if _source_relates_to_promise(source_passage, promise_sentence):
        llm_result = _try_llm_expansion(promise_sentence, source_passage, subject, stop_title)
        if llm_result:
            return {
                'expanded': True,
                'new_sentence': llm_result['replacement'],
                'source_quoted': llm_result['quoted_from'],
                'url': source_url,
                'tier': source_tier,
                'method': 'llm',
            }

    # Cannot expand — will trigger removal (Stage 4)
    return {
        'expanded': False,
        'new_sentence': None,
        'source_quoted': None,
        'url': source_url,
        'tier': source_tier,
        'method': None,
    }


def _try_deterministic_expansion(promise_sentence: str, source_passage: str,
                                  subject: str) -> Optional[Dict]:
    """Try to expand deterministically by extracting a factual statement
    from the source passage.

    Works when the source contains a clear factual sentence about the subject
    that can directly replace the promise.
    """
    # Split source into sentences
    source_sentences = re.split(r'(?<=[.!?])\s+', source_passage)

    subject_norm = _normalize(subject)
    subject_tokens = set(re.findall(r'[a-z0-9]+', subject_norm))

    best_sentence = None
    best_score = 0

    for sent in source_sentences:
        sent_norm = _normalize(sent)
        sent_tokens = set(re.findall(r'[a-z0-9]+', sent_norm))

        # Must mention the subject
        overlap = subject_tokens & sent_tokens
        if len(subject_tokens) == 0 or len(overlap) / len(subject_tokens) < 0.5:
            continue

        # Must have factual content (dates, numbers, proper nouns with predicates)
        has_date = bool(re.search(r'\b(?:1[0-9]{3}|20[0-2][0-9])\b', sent))
        has_number = bool(re.search(r'\b\d+(?:\.\d+)?\s*(?:km|m|meters?|feet|'
                                    r'hectares?|years?|centuries?)\b', sent, re.I))
        has_predicate = bool(re.search(r'\b(?:built|designed|created|founded|'
                                       r'established|constructed|opened|painted|'
                                       r'wrote|completed|named|commissioned)\b', sent, re.I))

        factual_score = int(has_date) + int(has_number) + int(has_predicate)
        if factual_score == 0:
            continue

        # Score: factual density + subject relevance
        score = factual_score + (len(overlap) / len(subject_tokens))
        if score > best_score:
            best_score = score
            best_sentence = sent.strip()

    if best_sentence and best_score >= 1.5:
        return {
            'replacement': best_sentence,
            'quoted_from': best_sentence,
        }
    return None


def _try_llm_expansion(promise_sentence: str, source_passage: str,
                        subject: str, stop_title: str) -> Optional[Dict]:
    """Try LLM-based expansion, strictly bounded to the source passage.

    The LLM is instructed to rewrite the promise sentence using ONLY
    information from the provided source passage. If it cannot do so
    without adding information not in the source, it returns null.

    Cost: ~$0.001 per call (gpt-4o-mini, ~200 input + ~100 output tokens).
    """
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return None

    import urllib.request

    prompt = f"""You are rewriting a single sentence from an audio tour.

ORIGINAL SENTENCE (makes a promise without delivering):
"{promise_sentence}"

SOURCE PASSAGE (the ONLY material you may use):
"{source_passage}"

SUBJECT: {subject}
STOP: {stop_title}

TASK: Rewrite the original sentence to deliver what it promised, using ONLY
facts from the source passage. The rewritten sentence must:
1. Be a single sentence (or at most two short sentences)
2. Contain ONLY information present in the source passage
3. Be suitable for spoken audio (conversational, not academic)
4. NOT add any dates, names, or facts not explicitly in the source

If the source passage does not contain enough information to deliver what the
original sentence promised, respond with exactly: CANNOT_EXPAND

Respond with ONLY the rewritten sentence (or CANNOT_EXPAND). No explanation."""

    try:
        data = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 150,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
            reply = body['choices'][0]['message']['content'].strip()

            if reply == 'CANNOT_EXPAND' or 'CANNOT_EXPAND' in reply:
                return None

            # Verify the expansion doesn't introduce content not in source
            # (basic check: key tokens in expansion should appear in source)
            expansion_tokens = set(re.findall(r'[a-z0-9]+', _normalize(reply)))
            source_tokens = set(re.findall(r'[a-z0-9]+', _normalize(source_passage)))
            # Allow common English words not in source
            _common = {'the', 'a', 'an', 'is', 'was', 'were', 'are', 'has', 'had',
                      'this', 'that', 'its', 'with', 'from', 'for', 'and', 'but',
                      'not', 'of', 'in', 'on', 'at', 'to', 'by', 'as', 'or'}
            novel_tokens = expansion_tokens - source_tokens - _common
            # If more than 30% of expansion tokens are novel, reject
            content_tokens = expansion_tokens - _common
            if content_tokens and len(novel_tokens) / len(content_tokens) > 0.3:
                logger.warning(f"LLM expansion introduced too many novel tokens, rejecting")
                return None

            # Find the source sentence that most closely matches what was used
            source_sentences = re.split(r'(?<=[.!?])\s+', source_passage)
            best_quote = source_passage[:200]  # Default: first 200 chars
            best_overlap = 0
            for ssent in source_sentences:
                ssent_tokens = set(re.findall(r'[a-z0-9]+', _normalize(ssent)))
                overlap = len(expansion_tokens & ssent_tokens)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_quote = ssent.strip()

            return {
                'replacement': reply,
                'quoted_from': best_quote,
            }
    except Exception as e:
        logger.error(f"LLM expansion failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 4: REMOVE — Delete sentence if expansion fails
# ═══════════════════════════════════════════════════════════════════════════════

def remove_promise(paragraph: str, sentence_to_remove: str) -> str:
    """Stage 4: Remove a sentence from a paragraph.

    Only removes the exact sentence — does not touch surrounding material
    (LOCAL-192 lesson: do not rewrite good material alongside bad).
    """
    # Remove the sentence and clean up whitespace
    cleaned = paragraph.replace(sentence_to_remove, '')
    # Clean up double spaces and leading/trailing whitespace
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
    return cleaned


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE: Process a paragraph through all four stages
# ═══════════════════════════════════════════════════════════════════════════════

def process_paragraph(paragraph: str, stop_title: str, venue_name: str = "",
                      conn=None, existence_verified: bool = True) -> Dict:
    """Run the full gather→validate→expand→remove pipeline on a paragraph.

    Args:
        paragraph: The text to process.
        stop_title: The stop/POI name.
        venue_name: The broader venue/tour name.
        conn: Optional database connection (reused across calls).
        existence_verified: Whether this stop passed LOCAL-236's existence check.
            If False, NO expansion is attempted (D127: a beautifully sourced
            story about an object the venue does not hold is still false).

    Returns: {
        original: str,
        processed: str,
        promises_found: [{sentence, subject, promise_type, outcome, ...}],
        expanded_count: int,
        deleted_count: int,
        unchanged_count: int,
        cost: float,
    }
    """
    if not is_subject_routine_enabled():
        return {
            'original': paragraph,
            'processed': paragraph,
            'promises_found': [],
            'expanded_count': 0,
            'deleted_count': 0,
            'unchanged_count': 0,
            'cost': 0.0,
        }

    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        # Stage 1: Gather
        promises = gather_promises(paragraph)

        if not promises:
            return {
                'original': paragraph,
                'processed': paragraph,
                'promises_found': [],
                'expanded_count': 0,
                'deleted_count': 0,
                'unchanged_count': 0,
                'cost': 0.0,
            }

        processed_text = paragraph
        results = []
        total_cost = 0.0
        expanded_count = 0
        deleted_count = 0
        unchanged_count = 0

        for promise in promises:
            sentence = promise['sentence']
            subject = promise['subject']

            # If stop fails existence check, skip expansion → delete
            if not existence_verified:
                processed_text = remove_promise(processed_text, sentence)
                results.append({
                    **promise,
                    'outcome': 'DELETED_NO_EXISTENCE',
                    'reason': 'Stop failed existence check (D127)',
                })
                deleted_count += 1
                continue

            # Stage 2: Validate
            validation = validate_subject(subject, stop_title, venue_name, conn)
            total_cost += validation.get('cost', 0.0)

            if not validation['found']:
                # Stage 4: Remove (no source found)
                processed_text = remove_promise(processed_text, sentence)
                results.append({
                    **promise,
                    'outcome': 'DELETED',
                    'reason': 'No source found for subject',
                    'validation': validation,
                })
                deleted_count += 1
                continue

            # Stage 3: Expand
            expansion = expand_promise(
                promise_sentence=sentence,
                source_passage=validation['passage'],
                subject=subject,
                stop_title=stop_title,
                source_url=validation.get('url'),
                source_tier=validation.get('tier'),
            )

            if expansion['expanded']:
                # Replace promise with expansion
                processed_text = processed_text.replace(sentence, expansion['new_sentence'])
                results.append({
                    **promise,
                    'outcome': 'EXPANDED',
                    'expansion': expansion,
                    'validation': validation,
                })
                expanded_count += 1
            else:
                # Expansion failed — remove
                processed_text = remove_promise(processed_text, sentence)
                results.append({
                    **promise,
                    'outcome': 'DELETED_EXPANSION_FAILED',
                    'reason': 'Source found but expansion could not deliver',
                    'validation': validation,
                })
                deleted_count += 1

        return {
            'original': paragraph,
            'processed': processed_text,
            'promises_found': results,
            'expanded_count': expanded_count,
            'deleted_count': deleted_count,
            'unchanged_count': unchanged_count,
            'cost': total_cost,
        }
    finally:
        if close_conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# CORPUS-WIDE RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

def run_on_tour(tour_id: int, conn=None) -> Dict:
    """Run the subject routine on all paragraphs of a stored tour.

    Returns aggregate stats: promises found, expanded, deleted per stop.
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        cur = conn.cursor()
        cur.execute("SELECT tour_name, tour_content FROM audio_tours WHERE id = %s", (tour_id,))
        row = cur.fetchone()
        cur.close()

        if not row or not row[1]:
            return {'tour_id': tour_id, 'error': 'No tour_content', 'paragraphs': []}

        tour_name = row[0]
        content = row[1]

        # Parse tour_content into stops and paragraphs
        stops = _parse_tour_content(content)

        results = []
        total_cost = 0.0
        total_promises = 0
        total_expanded = 0
        total_deleted = 0

        for stop in stops:
            stop_title = stop['title']
            paragraphs = stop['paragraphs']

            for para in paragraphs:
                para_result = process_paragraph(
                    paragraph=para,
                    stop_title=stop_title,
                    venue_name=tour_name,
                    conn=conn,
                    existence_verified=True,  # Assume verified for corpus-wide run
                )
                results.append({
                    'stop': stop_title,
                    'paragraph': para[:100] + '...' if len(para) > 100 else para,
                    **para_result,
                })
                total_cost += para_result['cost']
                total_promises += len(para_result['promises_found'])
                total_expanded += para_result['expanded_count']
                total_deleted += para_result['deleted_count']

        return {
            'tour_id': tour_id,
            'tour_name': tour_name,
            'stops_processed': len(stops),
            'paragraphs_processed': len(results),
            'total_promises': total_promises,
            'total_expanded': total_expanded,
            'total_deleted': total_deleted,
            'total_cost': total_cost,
            'results': results,
        }
    finally:
        if close_conn:
            conn.close()


def _parse_tour_content(content: str) -> List[Dict]:
    """Parse the stored tour_content text into a list of stops with paragraphs."""
    stops = []
    current_stop = None
    current_paragraphs = []

    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Detect stop boundaries
        if line.startswith('Stop ') and ':' in line:
            # Save previous stop
            if current_stop and current_paragraphs:
                stops.append({'title': current_stop, 'paragraphs': current_paragraphs})
            # Parse new stop title
            current_stop = line.split(':', 1)[1].strip()
            current_paragraphs = []
        elif line.startswith('Description:'):
            # The description section contains the main narrative paragraphs
            i += 1
            # Collect subsequent non-empty lines until the next section
            para_text = []
            while i < len(lines):
                next_line = lines[i].strip()
                if next_line.startswith(('Directions:', 'Stop ', 'Address:', 'Coordinates:',
                                        'Type/Specialty:', 'Specific Examples:', 'Orientation:')):
                    break
                if next_line:
                    para_text.append(next_line)
                elif para_text:
                    # Empty line = paragraph boundary
                    current_paragraphs.append(' '.join(para_text))
                    para_text = []
                i += 1
            if para_text:
                current_paragraphs.append(' '.join(para_text))
            continue
        elif line.startswith('Orientation:'):
            # Orientation is also narrative text
            text = line[len('Orientation:'):].strip()
            i += 1
            while i < len(lines):
                next_line = lines[i].strip()
                if next_line.startswith(('Description:', 'Directions:', 'Stop ', 'Address:',
                                        'Coordinates:', 'Type/Specialty:', 'Specific Examples:')):
                    break
                if next_line:
                    text += ' ' + next_line
                elif text:
                    current_paragraphs.append(text)
                    text = ''
                i += 1
            if text:
                current_paragraphs.append(text)
            continue

        i += 1

    # Save last stop
    if current_stop and current_paragraphs:
        stops.append({'title': current_stop, 'paragraphs': current_paragraphs})

    return stops


# ═══════════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Subject Validate Expand routine (LOCAL-237)')
    parser.add_argument('--paragraph', type=str, help='Single paragraph to process')
    parser.add_argument('--stop', type=str, default='', help='Stop title')
    parser.add_argument('--venue', type=str, default='', help='Venue/tour name')
    parser.add_argument('--tour-id', type=int, help='Process a stored tour by ID')
    parser.add_argument('--all-tours', action='store_true', help='Process all stored tours')
    parser.add_argument('--riviera', action='store_true',
                        help='Run on the 5 paragraphs from RIVIERA_2STOP_ROUND2')

    args = parser.parse_args()

    if args.riviera:
        # Run on Michael's reviewed paragraphs
        from run_subject_routine_riviera import run_riviera_analysis
        run_riviera_analysis()
    elif args.tour_id:
        result = run_on_tour(args.tour_id)
        print(json.dumps(result, indent=2, default=str))
    elif args.paragraph:
        result = process_paragraph(args.paragraph, args.stop, args.venue)
        print(json.dumps(result, indent=2, default=str))
    else:
        parser.print_help()
