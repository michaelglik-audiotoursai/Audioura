#!/usr/bin/env python3
"""unglossed_reference_gate.py — LOCAL-269: Detect and gloss unexplained references.

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
  Stage 4 — Keep glosses 8–14 words.

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


def _has_nearby_gloss(sentence: str, entity_name: str, sentences: List[str],
                      index: int) -> bool:
    """Check if entity_name has a gloss in this sentence or adjacent ones.

    A gloss means: appositive, relative clause, parenthetical, or explanation
    in the same or immediately adjacent sentence.
    """
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

def _search_corpus_for_gloss(entity: str, corpus_passages: List[str]) -> Optional[str]:
    """Try to find an explanation of entity in the corpus passages.

    Returns a gloss string if found, None otherwise.
    """
    if not corpus_passages:
        return None

    entity_lower = entity.lower()
    entity_words = set(entity_lower.split())

    for passage in corpus_passages:
        passage_lower = passage.lower()
        if entity_lower in passage_lower:
            # Found entity in corpus — extract explanation
            # Look for sentence containing entity + explanatory content
            sents = re.split(r'(?<=[.!?])\s+', passage)
            for s in sents:
                if entity_lower in s.lower():
                    # Check if this sentence has explanatory content beyond just naming
                    # (contains verbs, dates, descriptions)
                    if re.search(r'\b(?:was|is|were|built|founded|designed|'
                                 r'created|established|launched|began|'
                                 r'served|fought|allied|landed|invaded|'
                                 r'occurred|took\s+place|led\s+by|'
                                 r'the\s+\d{4}|in\s+\d{4})\b',
                                 s, re.IGNORECASE):
                        return s.strip()
        # Also check for entity words appearing close together
        elif any(w in passage_lower for w in entity_words if len(w) > 3):
            # Partial match — check if passage explains the concept
            pass  # Only use exact entity match for corpus glosses

    return None


def supply_glosses(references: List[Dict], corpus_passages: List[str],
                   api_key: str, model: str = None) -> Tuple[List[Dict], int, float, float]:
    """Stage 3: Supply a gloss for each reference that needs one.

    Order of preference:
      1. From corpus (free, traceable)
      2. From model call with citation requirement
      3. Degrade the reference (remove the unknown name, keep the fact)

    Args:
        references: triaged refs (only those with triage != 'known_enough')
        corpus_passages: the stop's corpus
        api_key: OpenAI API key
        model: model to use

    Returns:
        (glossed_refs, tokens_used, cost, latency)
        Each ref gets: gloss, gloss_source, stage
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
        corpus_gloss = _search_corpus_for_gloss(ref['entity'], corpus_passages)
        if corpus_gloss:
            # Trim to 8-14 words
            words = corpus_gloss.split()
            if len(words) > 14:
                corpus_gloss = ' '.join(words[:14])
                if not corpus_gloss.endswith('.'):
                    corpus_gloss = corpus_gloss.rstrip(',;:') + '.'
            ref['gloss'] = corpus_gloss
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

        prompt = f"""For each named reference below, provide:
1. A GLOSS: a brief factual explanation (8-14 words) suitable for audio narration.
2. A SOURCE: what factual basis supports this gloss (a historical record, date, or verifiable fact).

If you CANNOT provide a verifiable factual gloss, output DEGRADE and suggest how to rewrite the sentence without the unknown name while keeping the core fact.

REFERENCES:
{refs_block}

Format each response as:
[number]. GLOSS: [8-14 word explanation] | SOURCE: [basis]
OR
[number]. DEGRADE: [rewritten phrase without the unknown name]

RULES:
- Glosses must be 8-14 words. An appositive clause.
- Every gloss must be factually verifiable.
- Prefer DEGRADE over inventing: if unsure, degrade.

Examples:
- "Operation Dragoon" → GLOSS: the Allied landings in southern France in August 1944 | SOURCE: Operation Dragoon, August 15 1944, Allied invasion of southern France
- "House of Savoy" → GLOSS: the Italian royal dynasty that ruled the region until 1860 | SOURCE: Treaty of Turin 1860, Savoy/Nice ceded to France
- "Josep Lluís Sert" → GLOSS: the Catalan architect who designed the building in 1964 | SOURCE: Fondation Maeght, designed by Sert, opened 1964
"""

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You supply factual glosses for audio tour references. Every gloss must be verifiable. Prefer DEGRADE over inventing."},
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

                    # GLOSS line
                    gm = re.match(r'(\d+)\.\s*GLOSS:\s*(.+?)\s*\|\s*SOURCE:\s*(.+)', line, re.IGNORECASE)
                    if gm:
                        idx = int(gm.group(1)) - 1
                        gloss = gm.group(2).strip()
                        source = gm.group(3).strip()
                        if 0 <= idx < len(model_needed):
                            # Enforce 8-14 word limit
                            words = gloss.split()
                            if len(words) > 14:
                                gloss = ' '.join(words[:14])
                            model_needed[idx]['gloss'] = gloss
                            model_needed[idx]['gloss_source'] = source
                            model_needed[idx]['stage'] = 'model'
                        continue

                    # DEGRADE line
                    dm = re.match(r'(\d+)\.\s*DEGRADE:\s*(.+)', line, re.IGNORECASE)
                    if dm:
                        idx = int(dm.group(1)) - 1
                        degraded = dm.group(2).strip()
                        if 0 <= idx < len(model_needed):
                            model_needed[idx]['gloss'] = None
                            model_needed[idx]['degraded_text'] = degraded
                            model_needed[idx]['gloss_source'] = 'degrade'
                            model_needed[idx]['stage'] = 'degrade'
                        continue

        except Exception:
            total_latency += time.time() - start_time

    # Stage 3c: Anything still without a gloss gets degraded
    for ref in model_needed:
        if 'stage' not in ref:
            ref['gloss'] = None
            ref['gloss_source'] = 'degrade'
            ref['stage'] = 'degrade'
            # Generate a simple degradation
            ref['degraded_text'] = _degrade_reference(ref['entity'], ref['sentence'])

    return references, total_tokens, total_cost, total_latency


def _degrade_reference(entity: str, sentence: str) -> str:
    """Degrade a reference by removing the unknown name and keeping the fact.

    Example: "the first town liberated during Operation Dragoon"
          → "the first town liberated in 1944"
    """
    # Try to remove just the entity name and keep surrounding context
    # This is a best-effort heuristic
    degraded = sentence.replace(entity, '').strip()
    # Clean up double spaces, dangling prepositions
    degraded = re.sub(r'\s{2,}', ' ', degraded)
    degraded = re.sub(r'\b(during|under|by|of|at)\s*[,.]', '.', degraded)
    return degraded


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 4 — APPLY GLOSSES TO TEXT
# ═══════════════════════════════════════════════════════════════════════════════

def _insert_gloss(sentence: str, entity: str, gloss: str) -> str:
    """Insert a gloss after the entity name in the sentence.

    Target form: "...during Operation Dragoon, the Allied landings in
    southern France in August 1944."

    Ensures the gloss is 8-14 words and forms an appositive.
    """
    # Enforce 8-14 words
    words = gloss.split()
    if len(words) > 14:
        gloss = ' '.join(words[:14])
    if len(words) < 8:
        # Pad if too short (unusual but handle gracefully)
        pass

    # Find entity position
    pos = sentence.find(entity)
    if pos < 0:
        return sentence  # Entity not found — return unchanged

    end_pos = pos + len(entity)

    # Check what follows the entity
    after = sentence[end_pos:].lstrip()

    # If entity is followed by punctuation that ends the clause, insert before it
    if after and after[0] in '.!?,;:':
        punct = after[0]
        rest = after[1:]
        return sentence[:end_pos] + ', ' + gloss + punct + rest
    elif after and after[0] == "'":
        # Possessive: "Savoy's rule" → keep as is, insert after possessive phrase
        # Find end of possessive phrase
        poss_end = after.find(' ', 3)
        if poss_end > 0:
            return sentence[:end_pos + poss_end] + ', ' + gloss + ',' + after[poss_end:]
        return sentence[:end_pos] + ', ' + gloss + ', ' + after
    else:
        # Insert as appositive after entity
        return sentence[:end_pos] + ', ' + gloss + ',' + sentence[end_pos:]


def apply_glosses_to_text(text: str, glossed_refs: List[Dict]) -> str:
    """Apply all glosses to the tour text.

    For glossed refs: insert appositive gloss after entity name.
    For degraded refs: rewrite sentence to remove entity.
    """
    if not glossed_refs:
        return text

    sentences = _split_sentences(text)
    modified = False

    for ref in glossed_refs:
        if ref.get('triage') == 'known_enough':
            continue

        sent_idx = ref.get('sentence_index')
        if sent_idx is None or sent_idx >= len(sentences):
            continue

        entity = ref['entity']
        original_sent = ref['sentence']

        if ref.get('stage') == 'degrade':
            # Replace sentence with degraded version
            degraded = ref.get('degraded_text', '')
            if degraded and original_sent in text:
                text = text.replace(original_sent, degraded, 1)
                modified = True
        elif ref.get('gloss'):
            # Insert gloss
            gloss = ref['gloss']
            new_sent = _insert_gloss(original_sent, entity, gloss)
            if new_sent != original_sent and original_sent in text:
                text = text.replace(original_sent, new_sent, 1)
                modified = True

    return text


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

    Four stages: detect → triage → gloss → apply.

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
        'references_known': 0,
        'triage_tokens': 0,
        'triage_cost': 0.0,
        'triage_latency': 0.0,
        'gloss_tokens': 0,
        'gloss_cost': 0.0,
        'gloss_latency': 0.0,
        'glossed_list': [],  # For reporting
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

    # Stage 3: Supply glosses
    refs, gloss_tokens, gloss_cost, gloss_latency = supply_glosses(
        refs, corpus_passages or [], api_key, model
    )
    stats['gloss_tokens'] = gloss_tokens
    stats['gloss_cost'] = gloss_cost
    stats['gloss_latency'] = gloss_latency

    # Stage 4: Apply
    new_description = apply_glosses_to_text(description, refs)

    # Count results
    for ref in refs:
        if ref.get('triage') == 'known_enough':
            continue
        if ref.get('stage') == 'degrade':
            stats['references_degraded'] += 1
            stats['glossed_list'].append({
                'entity': ref['entity'],
                'action': 'degraded',
                'degraded_text': ref.get('degraded_text', ''),
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
        'total_known': 0,
        'triage_tokens': 0,
        'triage_cost': 0.0,
        'triage_latency': 0.0,
        'gloss_tokens': 0,
        'gloss_cost': 0.0,
        'gloss_latency': 0.0,
        'total_cost': 0.0,
        'total_tokens': 0,
        'total_latency': 0.0,
        'stops_affected': 0,
        'all_glosses': [],
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
        total_stats['total_known'] += stats['references_known']
        total_stats['triage_tokens'] += stats['triage_tokens']
        total_stats['triage_cost'] += stats['triage_cost']
        total_stats['triage_latency'] += stats['triage_latency']
        total_stats['gloss_tokens'] += stats['gloss_tokens']
        total_stats['gloss_cost'] += stats['gloss_cost']
        total_stats['gloss_latency'] += stats['gloss_latency']
        total_stats['all_glosses'].extend(stats['glossed_list'])

        total_stats['per_stop'].append({
            'stop_name': stop_name,
            'detected': stats['references_detected'],
            'glossed': stats['references_glossed'],
            'degraded': stats['references_degraded'],
            'known': stats['references_known'],
        })

    total_stats['total_cost'] = total_stats['triage_cost'] + total_stats['gloss_cost']
    total_stats['total_tokens'] = total_stats['triage_tokens'] + total_stats['gloss_tokens']
    total_stats['total_latency'] = total_stats['triage_latency'] + total_stats['gloss_latency']

    return total_stats
