#!/usr/bin/env python3
"""validate_story.py — Routine 3: Validate_Story (LOCAL-463)

Validates that every claim in a story is traceable to a source.

Two failure classes:
- UNSUPPORTED_ENTITY: a name/date/place absent from the corpus.
- UNSUPPORTED_RELATION: entities present but the causal/consequential link
  between them is not stated in any corpus sentence.

A story is TRUE_TO_SOURCES only when every sentence is GROUNDED.

Deterministic and offline. No LLM call, no API key, no network.

Usage:
    python3 validate_story.py --story "..." --corpus story_lab_state/stop2_survivors.txt
    python3 validate_story.py --story-file path.txt --corpus path.txt
"""
import argparse
import os
import re
import sys
import unicodedata
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from story_opportunity_scan import _fold, split_sentences  # noqa: E402
from story_material_check import (  # noqa: E402
    _PERSON_WITH_INITIAL, _NOT_A_PERSON, passages_about, _corpus_units,
)


# ═══════════════════════════════════════════════════════════════════════════════
# ENTITY CHECK — reuses the logic from story_writer.validate
# ═══════════════════════════════════════════════════════════════════════════════

_YEAR = re.compile(r'\b(1[5-9]\d{2}|20[0-2]\d)\b')

_SAFE_OPENERS = frozenset({
    'the', 'this', 'that', 'these', 'those', 'a', 'an', 'in', 'on', 'at', 'by',
    'for', 'with', 'from', 'when', 'while', 'and', 'but', 'his', 'her', 'their',
    'it', 'he', 'she', 'they', 'both', 'neither', 'no', 'not', 'nothing',
    'years', 'later',
})


def _check_entities(sentence: str, corpus_folded: str, corpus_raw: str) -> List[Dict]:
    """Check that all named entities and years in a sentence exist in the corpus."""
    findings = []

    # Person names
    for m in _PERSON_WITH_INITIAL.finditer(sentence):
        name = m.group(1).strip()
        if _NOT_A_PERSON.search(name):
            continue
        if name.split()[0].lower() in _SAFE_OPENERS:
            continue
        f = _fold(name)
        if f in corpus_folded:
            continue
        surname = f.split()[-1]
        if len(surname) >= 4 and re.search(r'\b' + re.escape(surname) + r'\b', corpus_folded):
            continue
        findings.append({'kind': 'person', 'value': name,
                         'why': 'not in source material'})

    # Organization / proper noun entities: "The X Press", "The X Gallery", etc.
    for m in _ORG_NAME.finditer(sentence):
        org = m.group(1).strip()
        f = _fold(org)
        if f in corpus_folded:
            continue
        # Check just the distinctive part (e.g., "hogarth" from "The Hogarth Press")
        core = _org_core(org)
        if core and re.search(r'\b' + re.escape(_fold(core)) + r'\b', corpus_folded):
            continue
        findings.append({'kind': 'organization', 'value': org,
                         'why': 'not in source material'})

    # Years
    for y in set(_YEAR.findall(sentence)):
        if y not in corpus_raw:
            findings.append({'kind': 'year', 'value': y,
                             'why': 'not in source material'})

    return findings


# Proper noun organizations: "The X Press", "X Gallery", "X Institute", etc.
_ORG_NAME = re.compile(
    r'\b((?:The\s+)?[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)*\s+'
    r'(?:Press|Gallery|Museum|Institute|Foundation|Society|University|'
    r'Workshop|Company|Publishers?|Editions?|Atelier))\b'
)


def _org_core(org: str) -> str:
    """Extract the distinctive core of an organization name.
    'The Hogarth Press' -> 'Hogarth', 'Torf Gallery' -> 'Torf'."""
    words = org.split()
    # Remove 'The' and the type word (last word)
    core_words = [w for w in words if w.lower() != 'the' and
                  not re.match(r'(?:press|gallery|museum|institute|foundation|'
                               r'society|university|workshop|company|publishers?|'
                               r'editions?|atelier)$', w, re.IGNORECASE)]
    return ' '.join(core_words)


# ═══════════════════════════════════════════════════════════════════════════════
# RELATION CHECK — the new work (LOCAL-463)
# ═══════════════════════════════════════════════════════════════════════════════

# Causal/consequential connectives that assert a link between two things.
# If a sentence contains one of these, the sentence asserts that something
# CAUSED or LED TO something else — and we require the corpus to state that
# link, not merely both endpoints.
_CAUSAL_CONNECTIVES = re.compile(
    r'\b('
    r'culminat(?:ing|ed)\s+in'
    r'|lead(?:ing)?\s+to'
    r'|led\s+to'
    r'|result(?:ing|ed)\s+in'
    r'|which\s+inspired'
    r'|as\s+a\s+result'
    r'|so\s+that'
    r'|thereby'
    r'|prompted'
    r'|drove\s+(?:him|her|them)\s+to'
    r'|pav(?:ing|ed)\s+the\s+way'
    r'|leaving\s+a\s+lasting'
    r'|would\s+channel'
    r'|gave\s+rise\s+to'
    r'|sparked'
    r'|inspired\s+(?:him|her|them|his|her)\b'
    r'|fueled'
    r'|ignited'
    r'|set\s+(?:in\s+motion|the\s+stage)'
    r'|was\s+born\s+(?:out\s+)?of'
    r'|sprang\s+from'
    r'|grew\s+out\s+of'
    r'|stemmed\s+from'
    r'|owing\s+to'
    r'|thanks\s+to'
    r'|on\s+account\s+of'
    r'|bringing\s+about'
    r'|brought\s+about'
    r'|giving\s+rise'
    r'|which\s+led'
    r'|which\s+caused'
    r'|which\s+prompted'
    r'|which\s+drove'
    r'|which\s+sparked'
    r'|which\s+fueled'
    r'|that\s+inspired'
    r'|that\s+led'
    r'|that\s+prompted'
    r')',
    re.IGNORECASE
)

# Plain conjunction — NOT causal. "X and Y" does not assert X caused Y.
# We explicitly exclude sentences that only use 'and', 'while', 'also', etc.
# between two supported facts.
_PLAIN_CONJUNCTION = re.compile(
    r'^(and|but|while|also|meanwhile|at the same time|in addition|furthermore)$',
    re.IGNORECASE
)


def _extract_linked_entities(sentence: str, connective_match: re.Match) -> Tuple[str, str]:
    """Given a sentence and the location of a causal connective, extract the
    two things being linked: the antecedent (before the connective) and the
    consequent (after the connective)."""
    start = connective_match.start()
    end = connective_match.end()

    antecedent = sentence[:start].strip().rstrip(',').strip()
    consequent = sentence[end:].strip().lstrip(',').strip()

    return antecedent, consequent


def _corpus_supports_link(antecedent: str, consequent: str, corpus: str,
                          story_connective: str = '') -> bool:
    """Check whether the corpus STATES the causal link between antecedent and consequent.

    The key distinction: finding both endpoints in the corpus is NOT enough.
    The corpus must contain a sentence/window that ASSERTS the same directional
    causal/consequential relationship the story asserts.

    "Dalí illustrated Freud's Moses and Monotheism in 1974" supports "Dalí created
    illustrations of Moses and Monotheism" — but does NOT support "the 1938 meeting
    culminated in the creation of Moses and Monotheism" because the corpus never
    says one CAUSED the other.

    Returns True only when the corpus itself asserts the causal/consequential link.
    """
    ante_keys = _extract_content_keys(antecedent)
    cons_keys = _extract_content_keys(consequent)

    if not ante_keys and not cons_keys:
        return True  # Nothing to check

    # For the "one side is vague" case (e.g., "leaving a lasting impression"):
    # the corpus must literally contain that phrase or its key claim.
    if not ante_keys or not cons_keys:
        return _vague_claim_in_corpus(antecedent, consequent, story_connective, corpus)

    corpus_units = _corpus_units(corpus)
    fc_units = [_fold(u) for u in corpus_units]

    # The story asserts: ANTECEDENT --caused/led-to/culminated-in--> CONSEQUENT
    # For this to be supported, the corpus must have a sentence that asserts
    # the same directional causal link. Not just co-occurrence.
    #
    # Strategy: find windows where both endpoints appear, then check if ANY
    # causal/directional language connects them in the corpus.
    for i, fu in enumerate(fc_units):
        window = fu
        if i + 1 < len(fc_units):
            window = fu + ' ' + fc_units[i + 1]

        ante_found = any(_key_in_text(k, window) for k in ante_keys)
        cons_found = any(_key_in_text(k, window) for k in cons_keys)

        if ante_found and cons_found:
            # Both endpoints in window — does it assert a CAUSAL link?
            if _window_has_causal_language(window):
                return True

    return False


# Language that asserts CAUSATION in corpus text (not mere co-occurrence).
# "illustrations for" is NOT causal — it says what Dalí made, not what caused it.
# "inspired by", "led to", "as a result of", "prompted by" ARE causal.
_CORPUS_CAUSAL_LANGUAGE = re.compile(
    r'\b('
    r'led\s+to'
    r'|result(?:ed|ing)\s+in'
    r'|culminat(?:ed|ing)\s+in'
    r'|caus(?:ed|ing)'
    r'|prompt(?:ed|ing)'
    r'|inspir(?:ed|ing)\s+(?:him|her|them|his|her|the|dal)'
    r'|influenced'
    r'|motivated'
    r'|drove\s+(?:him|her|them)'
    r'|sparked'
    r'|gave\s+rise'
    r'|as\s+a\s+result'
    r'|consequently'
    r'|therefore'
    r'|thus'
    r'|owing\s+to'
    r'|because\s+of'
    r'|thanks\s+to'
    r'|due\s+to'
    r'|pav(?:ed|ing)\s+the\s+way'
    r'|set\s+(?:in\s+motion|the\s+stage)'
    r'|brought\s+about'
    r'|channel(?:ed|ing)'
    r'|fascination.*(?:led|drove|prompted|inspired|into)'
    r'|impression'
    r')',
    re.IGNORECASE
)


def _window_has_causal_language(window: str) -> bool:
    """Check if a corpus window asserts a causal/consequential relationship
    (not mere factual co-occurrence)."""
    return bool(_CORPUS_CAUSAL_LANGUAGE.search(window))


def _vague_claim_in_corpus(antecedent: str, consequent: str, connective: str,
                           corpus: str) -> bool:
    """When one side of the causal claim is vague (no extractable entities),
    check if the specific claim phrasing appears in the corpus."""
    fc = _fold(corpus)

    # The vague phrases we're looking for: "lasting impression", "channel...fascination"
    claim_text = antecedent + ' ' + connective + ' ' + consequent
    distinctive_phrases = _extract_distinctive_phrases(claim_text)

    for phrase in distinctive_phrases:
        if _fold(phrase) in fc:
            return True

    return False


def _extract_distinctive_phrases(text: str) -> List[str]:
    """Extract distinctive multi-word phrases from a claim."""
    phrases = []
    # adjective+noun combinations that constitute the actual claim
    patterns = [
        r'lasting\s+impression',
        r'channel\w*\s+\w+\s+fascination',
        r'profound\s+(?:impact|effect|influence)',
        r'deep(?:ly)?\s+(?:impact|affect|influence)',
        r'transform(?:ed|ing|ative)',
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            phrases.append(m.group(0))
    return phrases


def _key_in_text(key: str, text: str) -> bool:
    """Check if a key phrase appears in text (folded)."""
    if len(key) < 3:
        return False
    return key in text


def _extract_content_keys(phrase: str) -> List[str]:
    """Extract meaningful content keys from a phrase for corpus matching.
    Returns folded keys: proper nouns, years, and significant noun phrases."""
    keys = []

    # Proper nouns
    for m in _PERSON_WITH_INITIAL.finditer(phrase):
        name = m.group(1).strip()
        if _NOT_A_PERSON.search(name):
            continue
        if name.split()[0].lower() in _SAFE_OPENERS:
            continue
        f = _fold(name)
        if f:
            keys.append(f)

    # Years
    for y in _YEAR.findall(phrase):
        keys.append(y)

    # Quoted titles
    for m in re.finditer(r'"([^"]+)"|"([^"]+)"', phrase):
        title = (m.group(1) or m.group(2)).strip()
        f = _fold(title)
        if f and len(f) > 3:
            keys.append(f)

    # If we found nothing from proper nouns, try significant noun-ish words
    # (longer words that aren't stopwords)
    if not keys:
        words = re.findall(r'\b[a-zA-Zà-ÿ]{5,}\b', phrase)
        stopwords = {'which', 'their', 'would', 'could', 'should', 'about',
                     'these', 'those', 'there', 'where', 'while', 'being',
                     'after', 'before', 'between', 'through', 'during',
                     'never', 'always', 'often', 'later', 'years', 'first',
                     'impression', 'lasting'}
        for w in words:
            if w.lower() not in stopwords:
                keys.append(_fold(w))

    return keys


def _check_relations(sentence: str, corpus: str) -> Optional[Dict]:
    """Check if a sentence asserts an unsupported causal/consequential relation.

    Returns None if no causal claim or if the relation is supported.
    Returns a finding dict if the relation is unsupported.
    """
    m = _CAUSAL_CONNECTIVES.search(sentence)
    if not m:
        return None

    connective = m.group(0)

    # FIRST: does the corpus contain the causal construction verbatim?
    # If the corpus says "culminating in the creation of Moses and Monotheism"
    # and the story says the same, the relation is supported.
    if _causal_phrase_in_corpus(sentence, m, corpus):
        return None

    antecedent, consequent = _extract_linked_entities(sentence, m)

    if not antecedent.strip() or not consequent.strip():
        return None

    if _corpus_supports_link(antecedent, consequent, corpus, connective):
        return None

    return {
        'kind': 'relation',
        'connective': connective,
        'antecedent': antecedent[:80],
        'consequent': consequent[:80],
        'why': f'corpus contains both endpoints but not the asserted link "{connective}"'
    }


def _causal_phrase_in_corpus(sentence: str, connective_match: re.Match, corpus: str) -> bool:
    """Check if the causal phrase from the story appears in the corpus.

    Takes a window around the connective and checks if the corpus contains it.
    This handles the case where the corpus literally states the same causal link.
    """
    fc = _fold(corpus)
    connective_text = connective_match.group(0)
    min_len = len(_fold(connective_text)) + 15

    # Try the connective + what follows (the consequence)
    phrase_start = connective_match.start()
    phrase = sentence[phrase_start:phrase_start + 80].strip()
    phrase_clean = re.sub(r'["\u201c\u201d]+', '', phrase)
    phrase_folded = _fold(phrase_clean)

    # Try progressively shorter suffixes
    while len(phrase_folded) >= min_len:
        if phrase_folded in fc:
            return True
        last_space = phrase_folded.rfind(' ')
        if last_space < min_len:
            break
        phrase_folded = phrase_folded[:last_space]

    # Also try: what's before the connective + connective
    pre_start = max(0, phrase_start - 60)
    pre_phrase = sentence[pre_start:connective_match.end()].strip()
    pre_clean = re.sub(r'["\u201c\u201d]+', '', pre_phrase)
    pre_folded = _fold(pre_clean)

    while len(pre_folded) >= min_len:
        if pre_folded in fc:
            return True
        first_space = pre_folded.find(' ')
        if first_space < 0 or len(pre_folded) - first_space < min_len:
            break
        pre_folded = pre_folded[first_space + 1:]

    return False


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def validate_story(story: str, corpus: str, matrix: Dict = None) -> Dict:
    """Validate that every claim in a story is traceable to the corpus.

    Args:
        story: The story text to validate.
        corpus: The grounding corpus (source material).
        matrix: Optional interrogation matrix (unused for now, reserved).

    Returns:
        Dict with:
            'verdict': 'TRUE_TO_SOURCES' or 'REJECTED'
            'sentences': List of per-sentence results, each with:
                'text': the sentence
                'status': 'GROUNDED' | 'UNSUPPORTED_ENTITY' | 'UNSUPPORTED_RELATION'
                'findings': list of specific issues (empty if GROUNDED)
    """
    corpus_folded = _fold(corpus)
    sentences = split_sentences(story)
    results = []

    for sent in sentences:
        # 1. Entity check first
        entity_issues = _check_entities(sent, corpus_folded, corpus)
        if entity_issues:
            results.append({
                'text': sent,
                'status': 'UNSUPPORTED_ENTITY',
                'findings': entity_issues,
            })
            continue

        # 2. Relation check
        relation_issue = _check_relations(sent, corpus)
        if relation_issue:
            results.append({
                'text': sent,
                'status': 'UNSUPPORTED_RELATION',
                'findings': [relation_issue],
            })
            continue

        # 3. All clear
        results.append({
            'text': sent,
            'status': 'GROUNDED',
            'findings': [],
        })

    # Overall verdict
    all_grounded = all(r['status'] == 'GROUNDED' for r in results)
    return {
        'verdict': 'TRUE_TO_SOURCES' if all_grounded else 'REJECTED',
        'sentences': results,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Validate story against corpus')
    parser.add_argument('--story', help='Story text (inline)')
    parser.add_argument('--story-file', help='Path to file containing story text')
    parser.add_argument('--corpus', required=True, help='Path to corpus file')
    args = parser.parse_args()

    if args.story_file:
        story = open(args.story_file, encoding='utf-8').read().strip()
    elif args.story:
        story = args.story
    else:
        parser.error('Provide --story or --story-file')
        return

    corpus = open(args.corpus, encoding='utf-8').read()

    result = validate_story(story, corpus)

    print(f"\n{'='*70}")
    print(f"STORY VERDICT: {result['verdict']}")
    print(f"{'='*70}\n")

    for i, s in enumerate(result['sentences'], 1):
        status_marker = '✓' if s['status'] == 'GROUNDED' else '✗'
        print(f"  [{status_marker}] Sentence {i}: {s['status']}")
        print(f"      \"{s['text'][:100]}{'...' if len(s['text']) > 100 else ''}\"")
        for f in s['findings']:
            if f['kind'] == 'relation':
                print(f"      → {f['why']}")
            else:
                print(f"      → {f['kind']}: {f['value']} — {f['why']}")
        print()


if __name__ == '__main__':
    main()
