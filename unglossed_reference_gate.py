#!/usr/bin/env python3
"""unglossed_reference_gate.py — LOCAL-269/LOCAL-287: Detect and gloss unexplained references.

The inverse of LOCAL-263's unsupported-claim gate. LOCAL-263 catches claims with
no fact behind them. This gate catches facts that assume knowledge the listener
lacks — a named person, operation, event, or structure that carries no explanation.

Michael's two triggers for glossing:
  1. A general audience likely does not know it.
  2. The tour has made it load-bearing (sentence meaning depends on it).

Four stages:
  Stage 1 — Deterministic detection of unglossed named entities.
  Stage 2 — LLM triage: general_audience_knows? load_bearing?
  Stage 3 — Supply a gloss (corpus first, model+citation second, degrade third).
  Stage 4 — COMPOSE the gloss into the host sentence (D194 fix: never splice).

LOCAL-287 fix: Glosses are composed clauses, never spliced sentences.
  - The host sentence is checked first: if it already explains the reference,
    the gate does not fire.
  - Glosses are composed via an LLM call that rephrases the supplied fact as a
    short appositive clause (never adds a fact).
  - Five mechanical guards validate the final text and force a fallback (drop
    the name) if any guard fails.

A reference IS glossed if a nearby span explains it — appositive, relative
clause, or explanation in adjacent sentence.

D164: navigation sentences are exempt from modification.
"""
import os
import re
import sys
import json
import time
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))

from style_validator_detector import (
    _is_style_navigation_sentence,
    _split_sentences,
)


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 1 — DETERMINISTIC DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

# Well-known references a general audience DOES know — skip these
_WELL_KNOWN = {
    # Wars/events
    'world war i', 'world war ii', 'wwi', 'wwii', 'the renaissance',
    'the french revolution', 'the industrial revolution', 'the cold war',
    'the great depression', 'world war 2', 'world war 1',
    # People broadly known
    'picasso', 'pablo picasso', 'monet', 'claude monet', 'van gogh',
    'vincent van gogh', 'napoleon', 'napoleon bonaparte', 'shakespeare',
    'william shakespeare', 'da vinci', 'leonardo da vinci', 'michelangelo',
    'einstein', 'albert einstein', 'mozart', 'beethoven', 'bach',
    'rembrandt', 'matisse', 'henri matisse', 'cézanne', 'paul cézanne',
    'renoir', 'auguste renoir', 'hemingway', 'ernest hemingway',
    'fitzgerald', 'f. scott fitzgerald', 'nietzsche', 'walt disney',
    'louis xiv', 'queen victoria', 'julius caesar', 'cleopatra',
    'alexander the great', 'genghis khan', 'jesus', 'muhammad', 'buddha',
    'socrates', 'plato', 'aristotle', 'galileo', 'newton', 'darwin',
    'marx', 'freud', 'gandhi', 'martin luther king',
    # Religions/movements
    'christianity', 'islam', 'buddhism', 'hinduism', 'judaism',
    # Modern broadly known
    'the beatles', 'elvis', 'michael jackson',
    # Geography well-known
    'mediterranean', 'mediterranean sea', 'atlantic', 'atlantic ocean',
    'pacific', 'pacific ocean', 'alps', 'the alps', 'french riviera',
    'riviera', 'côte d\'azur',
}

# Patterns that indicate an entity is already glossed (has an explanation)
_GLOSS_PATTERNS = [
    # Appositive: "X, a/an/the [word]" (word can start with letter or digit)
    re.compile(r',\s+(?:a|an|the)\s+[a-z0-9]', re.IGNORECASE),
    # Relative clause: "X, who/which/where/that [verb]"
    re.compile(r',\s+(?:who|which|where|that|whose)\s+', re.IGNORECASE),
    # Parenthetical: "X (explanation)"
    re.compile(r'\([^)]{5,}\)'),
    # Dash appositive: "X — explanation" or "X – explanation"
    re.compile(r'\s[—–]\s'),
    # "known as", "called", "named after"
    re.compile(r'\b(?:known\s+as|called|named\s+after|also\s+called)\b', re.IGNORECASE),
]

# Descriptor words that, when preceding a name, already explain it
_DESCRIPTOR_WORDS = re.compile(
    r'\b(?:architect|painter|sculptor|artist|composer|writer|author|poet|'
    r'playwright|philosopher|politician|statesman|general|admiral|'
    r'king|queen|emperor|prince|duke|count|baron|saint|pope|'
    r'director|actor|actress|singer|musician|designer|engineer|'
    r'scientist|mathematician|physician|surgeon|explorer|navigator|'
    r'merchant|banker|industrialist|philanthropist|collector|patron|'
    r'French|Italian|Spanish|German|British|American|Dutch|Swiss|'
    r'Catalan|Provençal|Genoese|Flemish|Austrian|Russian|Greek|'
    r'Roman|Byzantine|medieval|Renaissance|Baroque|Impressionist|'
    r'Modernist|Art\s+Deco|Romanesque|Gothic|Neoclassical)\b',
    re.IGNORECASE,
)

# Named entity patterns — people, operations, institutions, works, structures
_PERSON_PATTERN = re.compile(
    r'\b([A-Z][a-zà-ÿ]+(?:\s+(?:de|du|von|van|di|del|la|le|les|des|d\'|l\')?'
    r'\s*[A-Z][a-zà-ÿ]+)+)\b'
)

# Titled people (King X, Queen X, etc.)
_TITLED_PERSON = re.compile(
    r'\b((?:King|Queen|Emperor|Empress|Prince|Princess|Duke|Duchess|'
    r'Count|Countess|Baron|Baroness|Pope|Saint|St\.?)\s+'
    r'[A-Z][a-zà-ÿ]+(?:\s+[IVX]+|\s+[a-zà-ÿ]+)*(?:\s+of\s+[A-Z][a-zà-ÿ]+)?)\b'
)

# Operations/events: "Operation X", "Battle of X", "Treaty of X", etc.
_EVENT_PATTERN = re.compile(
    r'\b((?:Operation|Battle|Siege|Treaty|Accord|Convention|Congress|'
    r'Council|Crusade|Revolt|Revolution|Uprising|War)\s+(?:of\s+)?'
    r'[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)*)\b'
)

# Named structures/institutions: "Villa X", "Château X", "Palais X", etc.
_STRUCTURE_PATTERN = re.compile(
    r'\b((?:Villa|Château|Palais|Chapelle|Église|Cathédrale|Basilique|'
    r'Musée|Hôtel|Fort|Forte|Porta|Casa|Palazzo|Abbey|Priory|'
    r'Monastery|Convent|Rue|Place|Pont|Tour|Porte)\s+'
    r'(?:de\s+la\s+|du\s+|de\s+|des\s+|d\')?'
    r'[A-Z][a-zà-ÿ]+(?:\s+(?:de|du|d\'|la|le)?\s*[A-Za-zà-ÿ]+)*)\b'
)

# "House of X" pattern
_HOUSE_OF_PATTERN = re.compile(
    r'\b((?:House|Order|Brotherhood|Society|Guild)\s+of\s+'
    r'[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)*)\b'
)

# Named works: "Tender Is the Night", quoted titles
_WORK_TITLE_PATTERN = re.compile(
    r'["""]([^"""]{3,50})["""]'
)


def _is_well_known(name: str) -> bool:
    """Check if a reference is well-known to a general audience."""
    lower = name.lower().strip()
    if lower in _WELL_KNOWN:
        return True
    # Check if any well-known name is a substring
    for known in _WELL_KNOWN:
        if known in lower or lower in known:
            return True
    return False


def _host_sentence_already_explains(sentence: str, entity_name: str) -> bool:
    """LOCAL-287: Check if the host sentence already explains the entity.

    Catches cases like "Spanish architect Josep Lluís Sert" where the descriptor
    before the name already tells the listener who/what this is. In such cases
    the reference is NOT unglossed and the gate must not fire.

    Also catches patterns like:
      - "designed by architect X" (role before name)
      - "the French philosopher X" (nationality + role before name)
      - "X, the renowned painter" (appositive after name)
    """
    entity_pos = sentence.find(entity_name)
    if entity_pos < 0:
        entity_pos = sentence.lower().find(entity_name.lower())
    if entity_pos < 0:
        return False

    # Check text BEFORE the entity for descriptor words (within 40 chars)
    prefix_start = max(0, entity_pos - 40)
    prefix = sentence[prefix_start:entity_pos]
    if _DESCRIPTOR_WORDS.search(prefix):
        return True

    # Check text AFTER the entity for appositive descriptor (within 60 chars)
    after = sentence[entity_pos + len(entity_name):entity_pos + len(entity_name) + 60]
    # Pattern: ", the/a [descriptor]"
    if re.match(r',\s+(?:the|a|an)\s+', after):
        remaining = re.sub(r'^,\s+(?:the|a|an)\s+', '', after)
        if _DESCRIPTOR_WORDS.match(remaining):
            return True

    return False


def _has_nearby_gloss(sentence: str, entity_name: str, sentences: List[str],
                      index: int) -> bool:
    """Check if entity_name has a gloss in this sentence or adjacent ones.

    A gloss means: appositive, relative clause, parenthetical, or explanation
    in the same or immediately adjacent sentence.
    """
    # LOCAL-287: First check if host sentence already explains via descriptor
    if _host_sentence_already_explains(sentence, entity_name):
        return True

    # Check within the same sentence
    entity_pos = sentence.find(entity_name)
    if entity_pos < 0:
        entity_pos = sentence.lower().find(entity_name.lower())

    if entity_pos >= 0:
        # Text after the entity in this sentence
        after_entity = sentence[entity_pos + len(entity_name):]
        for pat in _GLOSS_PATTERNS:
            if pat.search(after_entity[:80]):
                return True

    # Check adjacent sentences for explanation of same entity
    for offset in [-1, 1]:
        adj_idx = index + offset
        if 0 <= adj_idx < len(sentences):
            adj = sentences[adj_idx]
            # If adjacent sentence contains entity name and has explanatory content
            if entity_name.lower() in adj.lower() or entity_name.split()[-1].lower() in adj.lower():
                for pat in _GLOSS_PATTERNS:
                    if pat.search(adj):
                        return True
                # Check if adjacent sentence has explanatory verbs about the entity
                if re.search(r'\b(?:was|is|were|are|built|founded|designed|created|'
                             r'constructed|established|commissioned|named|known|'
                             r'served|used|became|transformed)\b', adj, re.IGNORECASE):
                    # Check it's actually explaining THIS entity
                    entity_last_word = entity_name.split()[-1].lower()
                    if entity_last_word in adj.lower():
                        return True

    return False


def detect_unglossed_references(text: str, stop_names: List[str] = None) -> List[Dict]:
    """Stage 1: Deterministic detection of named entities lacking explanation.

    Returns list of dicts with:
      - entity: the entity name
      - sentence: the sentence containing it
      - sentence_index: index in the sentence list
      - category: person | event | structure | house | work

    Args:
        text: the tour text to analyze
        stop_names: list of stop names in this tour (excluded from flagging)
    """
    sentences = _split_sentences(text)
    results = []
    seen_entities = set()  # Avoid duplicates

    # Build set of stop name fragments to exclude
    _stop_fragments = set()
    if stop_names:
        for sn in stop_names:
            _stop_fragments.add(sn.lower())
            # Also add individual words > 3 chars
            for w in sn.split():
                if len(w) > 3:
                    _stop_fragments.add(w.lower())

    for i, sent in enumerate(sentences):
        if len(sent) < 15:
            continue
        # D164: skip navigation
        if _is_style_navigation_sentence(sent):
            continue

        # Find named entities in this sentence
        entities_found = []

        # People
        for m in _PERSON_PATTERN.finditer(sent):
            name = m.group(1)
            # Skip names that start with articles or are structure/place names
            if name.split()[0].lower() in ('the', 'this', 'that', 'a', 'an', 'its'):
                continue
            if len(name) > 3 and not _is_well_known(name):
                entities_found.append((name, 'person'))

        # Titled people
        for m in _TITLED_PERSON.finditer(sent):
            name = m.group(1)
            if not _is_well_known(name):
                entities_found.append((name, 'person'))

        # Events/Operations
        for m in _EVENT_PATTERN.finditer(sent):
            name = m.group(1)
            if not _is_well_known(name):
                entities_found.append((name, 'event'))

        # Structures
        for m in _STRUCTURE_PATTERN.finditer(sent):
            name = m.group(1)
            entities_found.append((name, 'structure'))

        # House of X
        for m in _HOUSE_OF_PATTERN.finditer(sent):
            name = m.group(1)
            if not _is_well_known(name):
                entities_found.append((name, 'house'))

        # Check each entity for existing gloss
        for entity_name, category in entities_found:
            if entity_name.lower() in seen_entities:
                continue
            # Skip if entity is a stop name or fragment thereof
            if _stop_fragments and entity_name.lower() in _stop_fragments:
                continue
            if _stop_fragments and any(entity_name.lower() in sf or sf in entity_name.lower()
                                       for sf in _stop_fragments if len(sf) > 3):
                continue
            if not _has_nearby_gloss(sent, entity_name, sentences, i):
                seen_entities.add(entity_name.lower())
                results.append({
                    'entity': entity_name,
                    'sentence': sent,
                    'sentence_index': i,
                    'category': category,
                })

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 2 — TRIAGE (model call, batched per stop)
# ═══════════════════════════════════════════════════════════════════════════════

def triage_references(references: List[Dict], api_key: str,
                      model: str = None) -> Tuple[List[Dict], int, float, float]:
    """Stage 2: For each unglossed reference, determine if gloss is needed.

    Batches all references for a stop into one call. Returns per reference:
      gloss_needed / known_enough / load_bearing

    Args:
        references: list from detect_unglossed_references
        api_key: OpenAI API key
        model: model to use (default: gpt-4o-mini)

    Returns:
        (triaged_refs, tokens_used, cost, latency)
        Each ref in triaged_refs gets a 'triage' field.
    """
    import requests as _req

    if not references:
        return [], 0, 0.0, 0.0

    if not model:
        model = os.environ.get('GLOSS_TRIAGE_MODEL', 'gpt-4o-mini')

    # Build the batch prompt
    refs_block = "\n".join(
        f"{i+1}. \"{ref['entity']}\" in: \"{ref['sentence'][:150]}\""
        for i, ref in enumerate(references)
    )

    prompt = f"""You are triaging named references in an audio tour for a general audience.

For each reference below, determine:
1. Would a GENERAL AUDIENCE (tourists, not historians) know what this is without explanation?
2. Is the sentence's meaning DEPENDENT on knowing what this reference is (load-bearing)?

REFERENCES:
{refs_block}

For EACH reference, output exactly one line:
[number]. [verdict]: [brief reason]

Verdicts:
- GLOSS_NEEDED — general audience would not know this
- LOAD_BEARING — even if somewhat known, the sentence depends on understanding it
- KNOWN_ENOUGH — general audience knows this well enough (e.g., "World War II", "Monet")

Be strict about KNOWN_ENOUGH — only common-knowledge items qualify.
"Operation Dragoon" → GLOSS_NEEDED (few non-historians know this)
"World War II" → KNOWN_ENOUGH
"House of Savoy" → GLOSS_NEEDED
"Monet" → KNOWN_ENOUGH
"Josep Lluís Sert" → GLOSS_NEEDED
"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You triage named references for audio tours. Be strict: only truly common knowledge is KNOWN_ENOUGH."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 300,
    }

    start_time = time.time()
    try:
        resp = _req.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            data=json.dumps(data),
            timeout=30,
        )
        latency = time.time() - start_time

        if resp.status_code != 200:
            # API error — default to GLOSS_NEEDED (safe)
            for ref in references:
                ref['triage'] = 'gloss_needed'
            return references, 0, 0.0, latency

        result = resp.json()
        text = result["choices"][0]["message"]["content"].strip()
        tokens_used = result.get("usage", {}).get("total_tokens", 0)

        # gpt-4o-mini pricing: $0.15/1M input, $0.60/1M output
        input_tokens = result.get("usage", {}).get("prompt_tokens", 0)
        output_tokens = result.get("usage", {}).get("completion_tokens", 0)
        cost = (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000

        # Parse response
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            m = re.match(r'(\d+)\.\s*(GLOSS_NEEDED|LOAD_BEARING|KNOWN_ENOUGH)', line, re.IGNORECASE)
            if m:
                idx = int(m.group(1)) - 1
                verdict = m.group(2).upper()
                if 0 <= idx < len(references):
                    references[idx]['triage'] = verdict.lower()

        # Default unmatched to gloss_needed
        for ref in references:
            if 'triage' not in ref:
                ref['triage'] = 'gloss_needed'

        return references, tokens_used, cost, latency

    except Exception:
        latency = time.time() - start_time
        for ref in references:
            ref['triage'] = 'gloss_needed'
        return references, 0, 0.0, latency


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 3 — SUPPLY THE GLOSS (corpus → model+citation → degrade)
# ═══════════════════════════════════════════════════════════════════════════════

def _search_corpus_for_fact(entity: str, corpus_passages: List[str]) -> Optional[str]:
    """Try to find a factual statement about entity in the corpus passages.

    Returns a raw fact string if found (will be composed into a clause later),
    or None if no corpus fact is available.
    """
    if not corpus_passages:
        return None

    entity_lower = entity.lower()

    for passage in corpus_passages:
        passage_lower = passage.lower()
        if entity_lower in passage_lower:
            # Found entity in corpus — extract the sentence containing it
            sents = re.split(r'(?<=[.!?])\s+', passage)
            for s in sents:
                if entity_lower in s.lower():
                    # Check if this sentence has factual content beyond just naming
                    if re.search(r'\b(?:was|is|were|built|founded|designed|'
                                 r'created|established|launched|began|'
                                 r'served|fought|allied|landed|invaded|'
                                 r'occurred|took\s+place|led\s+by|'
                                 r'the\s+\d{4}|in\s+\d{4})\b',
                                 s, re.IGNORECASE):
                        return s.strip()

    return None


def supply_glosses(references: List[Dict], corpus_passages: List[str],
                   api_key: str, model: str = None) -> Tuple[List[Dict], int, float, float]:
    """Stage 3: Supply a fact for each reference that needs glossing.

    LOCAL-287: This stage now only gathers the RAW FACT. Composition into a
    proper appositive clause happens in Stage 4 via the compose_glosses() call.

    Order of preference:
      1. From corpus (free, traceable)
      2. From model call with citation requirement
      3. Degrade the reference (remove the unknown name, keep the fact)

    Returns:
        (glossed_refs, tokens_used, cost, latency)
        Each ref gets: raw_fact, gloss_source, stage
    """
    import requests as _req

    if not model:
        model = os.environ.get('GLOSS_MODEL', 'gpt-4o-mini')

    needs_gloss = [r for r in references if r.get('triage') in ('gloss_needed', 'load_bearing')]
    if not needs_gloss:
        return references, 0, 0.0, 0.0

    total_tokens = 0
    total_cost = 0.0
    total_latency = 0.0

    # Stage 3a: Try corpus first (free)
    model_needed = []
    for ref in needs_gloss:
        corpus_fact = _search_corpus_for_fact(ref['entity'], corpus_passages)
        if corpus_fact:
            ref['raw_fact'] = corpus_fact
            ref['gloss_source'] = 'corpus'
            ref['stage'] = 'corpus'
        else:
            model_needed.append(ref)

    # Stage 3b: Model call for remaining (batched)
    if model_needed and api_key:
        refs_block = "\n".join(
            f"{i+1}. Entity: \"{ref['entity']}\" | Category: {ref['category']} | "
            f"Sentence: \"{ref['sentence'][:120]}\""
            for i, ref in enumerate(model_needed)
        )

        prompt = f"""For each named reference below, provide a single FACTUAL statement
about the entity that would help a listener understand who/what it is.

If you CANNOT provide a verifiable factual statement, output DEGRADE.

REFERENCES:
{refs_block}

Format each response as:
[number]. FACT: [one factual statement about the entity]
OR
[number]. DEGRADE

RULES:
- Only verifiable facts. Do not invent or speculate.
- One concise sentence per entity.
- Prefer DEGRADE over inventing.
"""

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You supply factual information for audio tour references. Every fact must be verifiable. Prefer DEGRADE over inventing."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 500,
        }

        start_time = time.time()
        try:
            resp = _req.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                data=json.dumps(data),
                timeout=30,
            )
            latency = time.time() - start_time
            total_latency += latency

            if resp.status_code == 200:
                result = resp.json()
                text = result["choices"][0]["message"]["content"].strip()
                input_tokens = result.get("usage", {}).get("prompt_tokens", 0)
                output_tokens = result.get("usage", {}).get("completion_tokens", 0)
                tokens_used = input_tokens + output_tokens
                total_tokens += tokens_used
                cost = (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000
                total_cost += cost

                # Parse responses
                for line in text.strip().split('\n'):
                    line = line.strip()
                    if not line:
                        continue

                    # FACT line
                    fm = re.match(r'(\d+)\.\s*FACT:\s*(.+)', line, re.IGNORECASE)
                    if fm:
                        idx = int(fm.group(1)) - 1
                        fact = fm.group(2).strip()
                        if 0 <= idx < len(model_needed):
                            model_needed[idx]['raw_fact'] = fact
                            model_needed[idx]['gloss_source'] = 'model'
                            model_needed[idx]['stage'] = 'model'
                        continue

                    # DEGRADE line
                    dm = re.match(r'(\d+)\.\s*DEGRADE', line, re.IGNORECASE)
                    if dm:
                        idx = int(dm.group(1)) - 1
                        if 0 <= idx < len(model_needed):
                            model_needed[idx]['raw_fact'] = None
                            model_needed[idx]['gloss_source'] = 'degrade'
                            model_needed[idx]['stage'] = 'degrade'
                        continue

        except Exception:
            total_latency += time.time() - start_time

    # Stage 3c: Anything still without a fact gets degraded
    for ref in model_needed:
        if 'stage' not in ref:
            ref['raw_fact'] = None
            ref['gloss_source'] = 'degrade'
            ref['stage'] = 'degrade'

    return references, total_tokens, total_cost, total_latency


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 4 — COMPOSE GLOSSES INTO HOST SENTENCES (D194 fix)
# ═══════════════════════════════════════════════════════════════════════════════

# ─── Mechanical guards (LOCAL-287) ─────────────────────────────────────────────
# These validate a composed gloss and force a fallback (drop the name) if any
# guard fails. A silent fallback is a good outcome; spliced garbage is not.

def _guard_spliced_sentence(gloss: str) -> bool:
    """Guard 1: ., produced by an inserted gloss (capital-letter sentence mid-sentence).

    Also catches glosses that ARE complete sentences (start with capital, contain
    a main verb, and are longer than a few words) — these should be appositive
    clauses starting lowercase.
    """
    if re.search(r'\.\s*,', gloss):
        return False
    # A gloss that starts with a capital letter and is > 5 words is likely a
    # spliced sentence rather than a composed appositive clause
    gloss_stripped = gloss.strip().rstrip('.,;:')
    if gloss_stripped and gloss_stripped[0].isupper() and len(gloss_stripped.split()) > 5:
        # Check if it contains a main verb (indicator of full sentence)
        if re.search(r'\b(?:was|is|were|are|has|had|have|did|does|will|would|'
                     r'could|should|shall|may|might|built|founded|designed|'
                     r'created|established|became|served|occurred|landed|'
                     r'attracted|frequented|visited)\b', gloss_stripped, re.IGNORECASE):
            return False
    # Capital letter after comma (except proper nouns at start) indicates a spliced sentence
    if re.search(r',\s+[A-Z][a-z]+\s+[a-z]+\s+[a-z]+\s+[a-z]+', gloss):
        # More than 4 words after a comma starting with capital = likely a sentence
        words_after_comma = re.findall(r',\s+([A-Z][^,]*)', gloss)
        for segment in words_after_comma:
            if len(segment.split()) > 6:
                return False
    return True


def _guard_doubled_name(full_sentence: str, entity_name: str) -> bool:
    """Guard 2: the glossed name appearing twice within 120 characters."""
    entity_lower = entity_name.lower()
    first_pos = full_sentence.lower().find(entity_lower)
    if first_pos < 0:
        return True
    second_pos = full_sentence.lower().find(entity_lower, first_pos + len(entity_lower))
    if second_pos < 0:
        return True
    if second_pos - first_pos <= 120:
        return False
    return True


def _guard_trailing_preposition(gloss: str) -> bool:
    """Guard 3: a gloss ending in a preposition or article — 'on the.', 'of the.', 'in.'."""
    # Check if the gloss clause ends with prep/article before punctuation
    if re.search(r'\b(?:on|of|in|at|by|for|to|from|with|the|a|an)\s*[.,;:!?]?\s*$', gloss.strip()):
        return False
    return True


def _guard_length(gloss: str) -> bool:
    """Guard 4: a gloss longer than ~12 words."""
    words = gloss.split()
    return len(words) <= 12


def _guard_host_duplication(gloss: str, host_sentence: str) -> bool:
    """Guard 5: a gloss whose text duplicates ≥6 consecutive words of its host sentence."""
    gloss_words = gloss.lower().split()
    host_words = host_sentence.lower().split()
    if len(gloss_words) < 6:
        return True
    for i in range(len(gloss_words) - 5):
        seq = gloss_words[i:i+6]
        # Check if this 6-word sequence appears in the host
        for j in range(len(host_words) - 5):
            if host_words[j:j+6] == seq:
                return False
    return True


def validate_gloss(gloss: str, host_sentence: str, entity_name: str) -> Tuple[bool, str]:
    """Run all five mechanical guards on a composed gloss.

    Returns (passed, failure_reason).
    """
    if not _guard_spliced_sentence(gloss):
        return False, "spliced_sentence"
    if not _guard_doubled_name(host_sentence, entity_name):
        return False, "doubled_name"
    if not _guard_trailing_preposition(gloss):
        return False, "trailing_preposition"
    if not _guard_length(gloss):
        return False, "too_long"
    if not _guard_host_duplication(gloss, host_sentence):
        return False, "host_duplication"
    return True, ""


def compose_glosses(references: List[Dict], api_key: str,
                    model: str = None) -> Tuple[List[Dict], int, float, float]:
    """Stage 4: Compose glosses as proper appositive clauses via LLM.

    LOCAL-287 (D194 fix): This is the critical difference from the old gate.
    Instead of pasting raw source text after a name, we ask the model to compose
    a short appositive clause that reads naturally in the host sentence.

    The model may only REPHRASE the supplied fact, never add one.

    All glosses for a stop are batched into a single call.

    Returns:
        (refs_with_composed_glosses, tokens_used, cost, latency)
    """
    import requests as _req

    if not model:
        model = os.environ.get('GLOSS_MODEL', 'gpt-4o-mini')

    # Filter to refs that have a raw_fact and need composition
    composable = [r for r in references
                  if r.get('raw_fact') and r.get('stage') != 'degrade'
                  and r.get('triage') in ('gloss_needed', 'load_bearing')]

    if not composable or not api_key:
        return references, 0, 0.0, 0.0

    # Build composition prompt — batched
    items_block = "\n".join(
        f"{i+1}. ENTITY: \"{ref['entity']}\"\n"
        f"   HOST SENTENCE: \"{ref['sentence'][:200]}\"\n"
        f"   FACT: \"{ref['raw_fact'][:200]}\""
        for i, ref in enumerate(composable)
    )

    prompt = f"""You are composing SHORT APPOSITIVE CLAUSES for an audio tour.

For each entity below, compose a gloss that:
- Is a lowercase appositive phrase (3-10 words, ideally 4-7)
- Reads naturally when inserted after the entity name in the host sentence
- Only rephrases the supplied FACT — never adds new information
- Does NOT repeat the entity name
- Does NOT repeat words already in the host sentence
- Starts lowercase (it will follow a comma)
- Does NOT end with a period (it will be followed by a comma)

If the host sentence ALREADY explains the entity (e.g., "Spanish architect X"),
output SUPPRESS — no gloss is needed.

If no short clause can be formed from the fact without distortion, output DROP.

ITEMS:
{items_block}

For EACH item, output exactly one line:
[number]. GLOSS: [the appositive clause, lowercase, no period]
OR
[number]. SUPPRESS
OR
[number]. DROP

EXAMPLES:
- Entity "Operation Dragoon", Fact "Operation Dragoon was the Allied invasion of southern France on August 15, 1944"
  → GLOSS: the 1944 Allied landings in southern France
- Entity "Josep Lluís Sert", Host "designed by Spanish architect Josep Lluís Sert"
  → SUPPRESS
- Entity "House of Savoy", Fact "The House of Savoy was the royal dynasty that ruled the region"
  → GLOSS: the royal dynasty that once ruled here
- Entity "Marguerite and Aimé Maeght", Fact "The Fondation Maeght was established by Marguerite and Aimé Maeght in 1964"
  → GLOSS: the gallerists who founded it in 1964
"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You compose short appositive clauses for audio tours. Output only lowercase phrases of 3-10 words. Never add facts not in the supplied material."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 400,
    }

    start_time = time.time()
    total_tokens = 0
    total_cost = 0.0

    try:
        resp = _req.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            data=json.dumps(data),
            timeout=30,
        )
        latency = time.time() - start_time

        if resp.status_code != 200:
            # API error — degrade all composable refs
            for ref in composable:
                ref['stage'] = 'degrade'
                ref['gloss'] = None
            return references, 0, 0.0, latency

        result = resp.json()
        text = result["choices"][0]["message"]["content"].strip()
        input_tokens = result.get("usage", {}).get("prompt_tokens", 0)
        output_tokens = result.get("usage", {}).get("completion_tokens", 0)
        total_tokens = input_tokens + output_tokens
        total_cost = (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000

        # Parse responses
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue

            # GLOSS line
            gm = re.match(r'(\d+)\.\s*GLOSS:\s*(.+)', line, re.IGNORECASE)
            if gm:
                idx = int(gm.group(1)) - 1
                gloss = gm.group(2).strip().rstrip('.')
                # Ensure lowercase start
                if gloss and gloss[0].isupper():
                    gloss = gloss[0].lower() + gloss[1:]
                if 0 <= idx < len(composable):
                    composable[idx]['gloss'] = gloss
                continue

            # SUPPRESS line
            sm = re.match(r'(\d+)\.\s*SUPPRESS', line, re.IGNORECASE)
            if sm:
                idx = int(sm.group(1)) - 1
                if 0 <= idx < len(composable):
                    composable[idx]['stage'] = 'suppressed'
                    composable[idx]['gloss'] = None
                continue

            # DROP line
            dm = re.match(r'(\d+)\.\s*DROP', line, re.IGNORECASE)
            if dm:
                idx = int(dm.group(1)) - 1
                if 0 <= idx < len(composable):
                    composable[idx]['stage'] = 'degrade'
                    composable[idx]['gloss'] = None
                continue

        # Anything not parsed → degrade
        for ref in composable:
            if 'gloss' not in ref:
                ref['stage'] = 'degrade'
                ref['gloss'] = None

        return references, total_tokens, total_cost, latency

    except Exception:
        latency = time.time() - start_time
        for ref in composable:
            ref['stage'] = 'degrade'
            ref['gloss'] = None
        return references, 0, 0.0, latency


# ═══════════════════════════════════════════════════════════════════════════════
# APPLY — Insert composed glosses into text, with guard validation
# ═══════════════════════════════════════════════════════════════════════════════

def _insert_gloss(sentence: str, entity: str, gloss: str) -> str:
    """Backwards-compatible alias for _insert_composed_gloss.

    Also enforces max 12-word truncation for direct callers (tests).
    """
    # Enforce 12-word max (mechanical guard 4)
    words = gloss.split()
    if len(words) > 12:
        gloss = ' '.join(words[:12])
    return _insert_composed_gloss(sentence, entity, gloss)


def _insert_composed_gloss(sentence: str, entity: str, gloss: str) -> str:
    """Insert a composed gloss after the entity name as an appositive.

    The gloss is already a lowercase clause without period. We insert it as:
      "...Entity, gloss, remainder..."

    Handles possessive ('s) by wrapping: "Entity's X" → "Entity, gloss, whose X"
    or by placing the gloss after the possessive phrase when short.

    Returns the modified sentence, or the original if insertion fails.
    """
    pos = sentence.find(entity)
    if pos < 0:
        return sentence

    end_pos = pos + len(entity)
    after = sentence[end_pos:]

    # Handle possessive: "Entity's ..."
    if after.startswith("'s ") or after.startswith("'s "):
        # Drop the gloss rather than produce "Entity, gloss,'s X"
        # Possessive constructions can't cleanly take an appositive
        return sentence

    # Insert appositive: "Entity, gloss, rest"
    # Handle case where entity is already followed by a comma
    if after.lstrip().startswith(','):
        # Already has comma — insert gloss after existing comma
        comma_pos = after.index(',')
        rest = after[comma_pos + 1:]
        return sentence[:end_pos] + ', ' + gloss + ',' + rest
    elif after.lstrip().startswith('.'):
        # End of sentence — insert before period
        dot_pos = after.index('.')
        return sentence[:end_pos] + ', ' + gloss + after[dot_pos:]
    else:
        # Normal case: insert comma-gloss-comma
        return sentence[:end_pos] + ', ' + gloss + ',' + after


def _degrade_reference_in_text(text: str, entity: str, sentence: str) -> str:
    """Remove entity name from its sentence in the text (fallback).

    Tries to gracefully remove just the name while preserving sentence flow.
    If the entity is the subject and removal would break the sentence,
    the sentence is left unchanged (the gloss is simply not applied).
    """
    # Try removing "entity, " or ", entity" patterns
    # Pattern: "by Entity" or "Entity," in a list
    patterns_to_try = [
        # "by Entity" → "by" removed too if it leaves orphan
        (f'{entity}, ', ''),
        (f', {entity}', ''),
        (f'{entity} ', ''),
    ]

    new_sentence = sentence
    for old, new in patterns_to_try:
        if old in new_sentence:
            candidate = new_sentence.replace(old, new, 1)
            # Don't produce empty or broken results
            if len(candidate.strip()) > 20:
                new_sentence = candidate
                break

    if new_sentence != sentence and sentence in text:
        return text.replace(sentence, new_sentence, 1)

    return text  # No change — leave as-is rather than damage


def apply_glosses_to_text(text: str, glossed_refs: List[Dict]) -> Tuple[str, List[Dict]]:
    """Apply composed glosses to the tour text with mechanical guard validation.

    LOCAL-287: Every gloss is validated against the 5 mechanical guards AFTER
    insertion. If any guard fails, the gloss is rejected and the name is dropped
    (or left unchanged if dropping would damage the sentence).

    Returns:
        (modified_text, guard_failures_log)
    """
    if not glossed_refs:
        return text, []

    guard_failures = []

    for ref in glossed_refs:
        if ref.get('triage') == 'known_enough':
            continue
        if ref.get('stage') == 'suppressed':
            continue

        entity = ref['entity']
        original_sent = ref['sentence']

        if ref.get('stage') == 'degrade' or not ref.get('gloss'):
            # Degrade: remove the name
            text = _degrade_reference_in_text(text, entity, original_sent)
            continue

        gloss = ref['gloss']

        # Compose the new sentence
        new_sent = _insert_composed_gloss(original_sent, entity, gloss)

        # Validate with mechanical guards
        # Guard 2 (doubled name) uses new_sent to check the result
        # Guard 5 (host_duplication) uses original_sent to avoid circular match
        passed, failure_reason = validate_gloss(gloss, original_sent, entity)
        if passed:
            # Also check guard 2 on the composed result
            if not _guard_doubled_name(new_sent, entity):
                passed = False
                failure_reason = "doubled_name"

        if not passed:
            # Guard failed — fall back to dropping the name
            guard_failures.append({
                'entity': entity,
                'gloss': gloss,
                'reason': failure_reason,
            })
            text = _degrade_reference_in_text(text, entity, original_sent)
            ref['stage'] = 'guard_failed'
            ref['guard_failure'] = failure_reason
        else:
            # Guard passed — apply the gloss
            if original_sent in text:
                text = text.replace(original_sent, new_sent, 1)

    return text, guard_failures


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN GATE — apply to a stop description
# ═══════════════════════════════════════════════════════════════════════════════

def apply_unglossed_reference_gate(
    description: str,
    corpus_passages: List[str] = None,
    api_key: str = None,
    model: str = None,
    stop_names: List[str] = None,
) -> Tuple[str, Dict]:
    """Apply the unglossed-reference gate to a stop description.

    Four stages: detect → triage → supply fact → compose gloss → apply.

    LOCAL-287: Stage 4 now COMPOSES glosses via LLM rather than splicing raw text.
    Mechanical guards validate the output and fall back to dropping the name.

    Args:
        description: the stop's description text
        corpus_passages: the stop's corpus passages
        api_key: OpenAI API key (required for triage + gloss)
        model: LLM model
        stop_names: names of all stops in this tour (excluded from flagging)

    Returns:
        (new_description, stats_dict)
    """
    stats = {
        'references_detected': 0,
        'references_glossed': 0,
        'references_degraded': 0,
        'references_suppressed': 0,
        'references_known': 0,
        'references_guard_failed': 0,
        'triage_tokens': 0,
        'triage_cost': 0.0,
        'triage_latency': 0.0,
        'gloss_tokens': 0,
        'gloss_cost': 0.0,
        'gloss_latency': 0.0,
        'compose_tokens': 0,
        'compose_cost': 0.0,
        'compose_latency': 0.0,
        'glossed_list': [],  # For reporting
        'guard_failures': [],
    }

    if not description or not description.strip():
        return description, stats

    # Stage 1: Detect
    refs = detect_unglossed_references(description, stop_names=stop_names)
    stats['references_detected'] = len(refs)

    if not refs:
        return description, stats

    if not api_key:
        # No API key — cannot triage or gloss, return as-is
        return description, stats

    # Stage 2: Triage
    refs, triage_tokens, triage_cost, triage_latency = triage_references(
        refs, api_key, model
    )
    stats['triage_tokens'] = triage_tokens
    stats['triage_cost'] = triage_cost
    stats['triage_latency'] = triage_latency

    # Filter to only those needing gloss
    needs_gloss = [r for r in refs if r.get('triage') in ('gloss_needed', 'load_bearing')]
    known = [r for r in refs if r.get('triage') == 'known_enough']
    stats['references_known'] = len(known)

    if not needs_gloss:
        return description, stats

    # Stage 3: Supply facts (corpus or model)
    refs, gloss_tokens, gloss_cost, gloss_latency = supply_glosses(
        refs, corpus_passages or [], api_key, model
    )
    stats['gloss_tokens'] = gloss_tokens
    stats['gloss_cost'] = gloss_cost
    stats['gloss_latency'] = gloss_latency

    # Stage 4: Compose glosses as proper appositive clauses (D194 fix)
    refs, compose_tokens, compose_cost, compose_latency = compose_glosses(
        refs, api_key, model
    )
    stats['compose_tokens'] = compose_tokens
    stats['compose_cost'] = compose_cost
    stats['compose_latency'] = compose_latency

    # Apply composed glosses with guard validation
    new_description, guard_failures = apply_glosses_to_text(description, refs)
    stats['guard_failures'] = guard_failures

    # Count results
    for ref in refs:
        if ref.get('triage') == 'known_enough':
            continue
        if ref.get('stage') == 'suppressed':
            stats['references_suppressed'] += 1
            stats['glossed_list'].append({
                'entity': ref['entity'],
                'action': 'suppressed',
                'reason': 'host sentence already explains',
            })
        elif ref.get('stage') == 'guard_failed':
            stats['references_guard_failed'] += 1
            stats['references_degraded'] += 1
            stats['glossed_list'].append({
                'entity': ref['entity'],
                'action': 'guard_failed',
                'gloss_attempted': ref.get('gloss', ''),
                'reason': ref.get('guard_failure', ''),
            })
        elif ref.get('stage') == 'degrade':
            stats['references_degraded'] += 1
            stats['glossed_list'].append({
                'entity': ref['entity'],
                'action': 'degraded',
                'source': 'degrade',
            })
        elif ref.get('gloss'):
            stats['references_glossed'] += 1
            stats['glossed_list'].append({
                'entity': ref['entity'],
                'gloss': ref['gloss'],
                'source': ref.get('gloss_source', 'unknown'),
                'stage': ref.get('stage', 'unknown'),
            })

    return new_description, stats


def apply_gate_to_stop_descriptions(
    poi_list: List[Dict],
    stop_corpus_data: Dict = None,
    api_key: str = None,
    model: str = None,
) -> Dict:
    """Apply the unglossed-reference gate to all stops in a tour.

    Args:
        poi_list: list of POI dicts with 'description' and 'name' keys
        stop_corpus_data: dict mapping stop_name → {passages: [...]}
        api_key: OpenAI API key
        model: LLM model

    Returns:
        Summary dict with per-stop and total stats.
    """
    total_stats = {
        'total_detected': 0,
        'total_glossed': 0,
        'total_degraded': 0,
        'total_suppressed': 0,
        'total_known': 0,
        'total_guard_failed': 0,
        'triage_tokens': 0,
        'triage_cost': 0.0,
        'triage_latency': 0.0,
        'gloss_tokens': 0,
        'gloss_cost': 0.0,
        'gloss_latency': 0.0,
        'compose_tokens': 0,
        'compose_cost': 0.0,
        'compose_latency': 0.0,
        'total_cost': 0.0,
        'total_tokens': 0,
        'total_latency': 0.0,
        'stops_affected': 0,
        'all_glosses': [],
        'guard_failures': [],
        'per_stop': [],
    }

    # Collect all stop names for exclusion
    all_stop_names = [poi.get('name', '') for poi in poi_list if poi.get('name')]

    for si, poi in enumerate(poi_list):
        desc = poi.get('description', '')
        if not desc or desc.startswith('['):
            continue

        stop_name = poi.get('name', f'Stop {si + 1}')

        # Get corpus passages
        passages = []
        if stop_corpus_data and stop_name in stop_corpus_data:
            sc_entry = stop_corpus_data[stop_name]
            if sc_entry and sc_entry.get('passages'):
                passages = sc_entry['passages']

        new_desc, stats = apply_unglossed_reference_gate(
            desc, corpus_passages=passages, api_key=api_key, model=model,
            stop_names=all_stop_names,
        )

        if stats['references_glossed'] > 0 or stats['references_degraded'] > 0:
            poi_list[si]['description'] = new_desc
            total_stats['stops_affected'] += 1

        total_stats['total_detected'] += stats['references_detected']
        total_stats['total_glossed'] += stats['references_glossed']
        total_stats['total_degraded'] += stats['references_degraded']
        total_stats['total_suppressed'] += stats['references_suppressed']
        total_stats['total_known'] += stats['references_known']
        total_stats['total_guard_failed'] += stats['references_guard_failed']
        total_stats['triage_tokens'] += stats['triage_tokens']
        total_stats['triage_cost'] += stats['triage_cost']
        total_stats['triage_latency'] += stats['triage_latency']
        total_stats['gloss_tokens'] += stats['gloss_tokens']
        total_stats['gloss_cost'] += stats['gloss_cost']
        total_stats['gloss_latency'] += stats['gloss_latency']
        total_stats['compose_tokens'] += stats['compose_tokens']
        total_stats['compose_cost'] += stats['compose_cost']
        total_stats['compose_latency'] += stats['compose_latency']
        total_stats['all_glosses'].extend(stats['glossed_list'])
        total_stats['guard_failures'].extend(stats['guard_failures'])

        total_stats['per_stop'].append({
            'stop_name': stop_name,
            'detected': stats['references_detected'],
            'glossed': stats['references_glossed'],
            'degraded': stats['references_degraded'],
            'suppressed': stats['references_suppressed'],
            'known': stats['references_known'],
            'guard_failed': stats['references_guard_failed'],
        })

    total_stats['total_cost'] = (total_stats['triage_cost'] +
                                  total_stats['gloss_cost'] +
                                  total_stats['compose_cost'])
    total_stats['total_tokens'] = (total_stats['triage_tokens'] +
                                    total_stats['gloss_tokens'] +
                                    total_stats['compose_tokens'])
    total_stats['total_latency'] = (total_stats['triage_latency'] +
                                     total_stats['gloss_latency'] +
                                     total_stats['compose_latency'])

    return total_stats
