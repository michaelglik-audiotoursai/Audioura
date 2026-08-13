#!/usr/bin/env python3
"""story_claim_lab.py — audit a delivered stop's prose against its stop record.

RENAMED 2026-08-13. LOCAL-458 shipped a PRODUCTION gate under the name
`stop_claim_audit.py` — it rebuilt this from the task description because LEAD
never committed this file, so the worktree branched from storied could not see it.
That is LEAD's process error, not the task's. Both files are worth keeping and they
are different things: `stop_claim_audit.py` is the gate that runs in generation,
this is the hand-driven lab instrument used with story_lab.

Michael's ask, 2026-08-13: run a routine on the delivered Stop 2 description and
tie every claim in it back to the starting point the system actually had.

The question this answers is not "is the prose true" — we have no oracle for that.
It is the narrower, checkable one:

    for each factual claim in the delivered text, WHERE DID IT COME FROM?

Three sources are possible, and only three:

    RECORD    the stop record carried it   (canonical_title, artist, publisher, …)
    EVIDENCE  the retrieved corpus carried it   (page_text, ranked snippets)
    NEITHER   the model asserted it from parametric memory

A NEITHER verdict is not proof the claim is false. It is proof the system had no
reason to say it — which is the only thing a validator can ever establish, and is
exactly the state "Commissioned by The Hogarth Press" was in.

The audit is deterministic and free. No API calls.

    python3 story_claim_lab.py --state story_lab_state/stop2_prod.json --text-from-tour
    python3 story_claim_lab.py --text-file some_stop.txt --record-json rec.json
"""
import argparse
import json
import os
import re
import sys
import textwrap
import unicodedata
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


# ═══════════════════════════════════════════════════════════════════════════════
# ROLE CLAIMS — "X was published by Y"
# ═══════════════════════════════════════════════════════════════════════════════
#
# These are the claims that assign an AGENT to a ROLE. They are the highest-value
# class to audit because they are the ones a listener will repeat as fact, and
# because the stop record has a named slot for most of them — so when the record's
# slot is empty and the prose fills it anyway, the invention is unambiguous.
#
# Deliberately NOT a person-name detector. The failure this was built for involved
# an organisation, which every person-oriented gate is structurally blind to.

ROLE_PATTERNS: List[Tuple[str, str, str]] = [
    # (role, record field it maps to, regex — agent in group 'agent')
    ('publisher',    'publisher',   r'\bpublished\s+by\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
    ('publisher',    'publisher',   r'\bcommissioned\s+by\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
    ('publisher',    'publisher',   r'\bpublishers?\s+such\s+as\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
    ('publisher',    'publisher',   r'\bfor\s+(?:the\s+)?publisher\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
    ('printer',      'printer',     r'\bprinted\s+by\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
    ('printer',      'printer',     r'\bat\s+the\s+(?P<agent>[A-Z][^.,;:]{2,60})\s+workshop'),
    ('illustrator',  'artist',      r'\billustrated\s+by\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
    ('illustrator',  'artist',      r'\betchings?\s+by\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
    ('writer',       'collaborator', r'\bwritten\s+by\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
    ('writer',       'collaborator', r'\btext\s+by\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
    ('designer',     'artist',      r'\bdesigned\s+by\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
    ('donor',        'credit_line', r'\b(?:gift|bequest)\s+of\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
    ('donor',        'credit_line', r'\bdonated\s+by\s+(?P<agent>[A-Z][^.,;:]{2,60})'),
]

# "X illustrating Y's work" / "X embarked on ... illustrating" — active-voice
# attributions that carry the same weight as the passive ones above.
ACTIVE_ROLE_PATTERNS: List[Tuple[str, str, str]] = [
    ('illustrator', 'artist',
     r'(?P<agent>[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)+)[^.]{0,80}?\billustrat(?:ing|ed)\b'),
    ('writer', 'collaborator',
     r'(?P<agent>[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)+)[^.]{0,40}?\bwrote\b'),
]


# ═══════════════════════════════════════════════════════════════════════════════
# NAMED ENTITIES — every proper-noun span, articles included
# ═══════════════════════════════════════════════════════════════════════════════
#
# prose_entity_grounding_gate._PERSON_MULTI_WORD matches leftmost-longest and then
# rejects anything opening with an article. "The Hogarth Press" is therefore
# consumed as one candidate and discarded, and the bare "Hogarth Press" inside it
# is never offered separately. The article shields the entity from the gate.
# This extractor keeps BOTH forms so nothing can hide behind a determiner.

_ENTITY_SPAN = re.compile(
    r'\b((?:The\s+|Le\s+|La\s+|Les\s+)?'
    r'[A-Z][a-zà-ÿ]+(?:\s+(?:de|du|von|van|di|del|des|et)\s+|\s+)'
    r'[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)*)\b'
)

_LEADING_ARTICLE = re.compile(r'^(?:The|Le|La|Les)\s+', re.IGNORECASE)

# Spans that are descriptive rather than referential — not worth auditing.
_ENTITY_STOPWORDS = frozenset({
    'moses and monotheism',
})


def _fold(text: str) -> str:
    """Accent-fold and lowercase. D243: exact match on French titles reports
    absence that is not there."""
    if not text:
        return ''
    nfd = unicodedata.normalize('NFD', text)
    stripped = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', stripped.lower()).strip()


def extract_entities(text: str) -> List[str]:
    """Every proper-noun span, with and without a leading article."""
    out, seen = [], set()
    for m in _ENTITY_SPAN.finditer(text):
        span = m.group(1).strip()
        for variant in (span, _LEADING_ARTICLE.sub('', span)):
            key = _fold(variant)
            if not key or key in seen or key in _ENTITY_STOPWORDS:
                continue
            if len(variant.split()) < 2:
                continue
            seen.add(key)
            out.append(variant)
    return out


def extract_role_claims(text: str) -> List[Dict]:
    """Every ROLE→AGENT assignment the prose makes."""
    claims, seen = [], set()
    for patterns in (ROLE_PATTERNS, ACTIVE_ROLE_PATTERNS):
        for role, field, pattern in patterns:
            for m in re.finditer(pattern, text, re.IGNORECASE if patterns is ROLE_PATTERNS else 0):
                agent = re.sub(r'\s+', ' ', m.group('agent').strip())
                agent = re.sub(r'\s+(?:and|in|to|for|with|transformed|this)$', '', agent, flags=re.I)
                key = (role, _fold(agent))
                if not agent or key in seen:
                    continue
                seen.add(key)
                claims.append({
                    'role': role,
                    'field': field,
                    'agent': agent,
                    'sentence': _sentence_containing(text, m.start()),
                })
    return claims


def _sentence_containing(text: str, pos: int) -> str:
    start = max(text.rfind('.', 0, pos), text.rfind('\n', 0, pos)) + 1
    end = text.find('.', pos)
    end = len(text) if end == -1 else end + 1
    return text[start:end].strip()


# ═══════════════════════════════════════════════════════════════════════════════
# GROUNDING
# ═══════════════════════════════════════════════════════════════════════════════

def _in_corpus(needle: str, corpus: str) -> bool:
    """Accent-folded substring, plus a surname/last-token fallback for people."""
    if not needle or not corpus:
        return False
    n, c = _fold(needle), _fold(corpus)
    if n in c:
        return True
    tokens = [t for t in n.split() if len(t) >= 4 and t not in ('the', 'press')]
    return bool(tokens) and all(re.search(r'\b' + re.escape(t) + r'\b', c) for t in tokens)


def audit(text: str, record: Dict, evidence: str = '') -> Dict:
    """Classify every claim in `text` by where it could have come from."""
    record_blob = ' | '.join(str(v) for v in record.values() if v)

    findings = []

    for claim in extract_role_claims(text):
        field = claim['field']
        slot = (record.get(field) or '').strip()
        agent = claim['agent']

        if slot and _in_corpus(agent, slot):
            verdict, why = 'RECORD', f"stop record {field}={slot!r}"
        elif slot:
            verdict, why = 'CONTRADICTS', f"stop record {field}={slot!r} — prose says {agent!r}"
        elif _in_corpus(agent, record_blob):
            verdict, why = 'RECORD', 'appears elsewhere in the stop record'
        elif evidence and _in_corpus(agent, evidence):
            verdict, why = 'EVIDENCE', 'present in retrieved corpus'
        elif not slot:
            verdict, why = 'INVENTED', f"stop record {field} is EMPTY — nothing supplied this"
        else:
            verdict, why = 'UNSUPPORTED', 'not in record, not in corpus'

        findings.append({**claim, 'verdict': verdict, 'why': why})

    entity_findings = []
    claimed = {_fold(f['agent']) for f in findings}
    for ent in extract_entities(text):
        if _fold(ent) in claimed:
            continue
        if _in_corpus(ent, record_blob):
            v, why = 'RECORD', 'in the stop record'
        elif evidence and _in_corpus(ent, evidence):
            v, why = 'EVIDENCE', 'in retrieved corpus'
        else:
            v, why = 'INVENTED', 'not in record, not in corpus'
        entity_findings.append({'entity': ent, 'verdict': v, 'why': why})

    return {
        'role_claims': findings,
        'entities': entity_findings,
        'evidence_chars': len(evidence or ''),
        'record_fields_filled': sum(1 for v in record.values() if v),
        'record_fields_total': len(record),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════════════════════

_MARK = {'RECORD': '  OK  ', 'EVIDENCE': '  OK  ',
         'INVENTED': ' !!!! ', 'CONTRADICTS': ' !!!! ', 'UNSUPPORTED': '  ??  '}


def report(result: Dict, record: Dict) -> None:
    print(f"\n{'=' * 78}\nSTOP CLAIM AUDIT\n{'=' * 78}")
    print(f"\n  STARTING POINT — {result['record_fields_filled']} of "
          f"{result['record_fields_total']} fields carry a value\n")
    for k, v in record.items():
        print(f"   {' ' if v else '!'} {k:18} {v!r}")
    print(f"\n   evidence corpus: {result['evidence_chars']} chars"
          f"{'  <- EMPTY: nothing can be grounded in evidence' if not result['evidence_chars'] else ''}")

    print(f"\n{'-' * 78}\n  ROLE CLAIMS — who the prose says did what\n{'-' * 78}\n")
    if not result['role_claims']:
        print("   (none detected)")
    for f in result['role_claims']:
        print(f"  [{_MARK[f['verdict']]}] {f['role']:12} = {f['agent']}")
        print(f"           {f['verdict']}: {f['why']}")
        print(textwrap.fill(f['sentence'], width=76,
                            initial_indent='           " ', subsequent_indent='             '))
        print()

    print(f"{'-' * 78}\n  OTHER NAMED ENTITIES\n{'-' * 78}\n")
    for e in result['entities']:
        print(f"  [{_MARK[e['verdict']]}] {e['entity']:38} {e['why']}")

    bad = [f for f in result['role_claims'] if f['verdict'] in ('INVENTED', 'CONTRADICTS')]
    bad_e = [e for e in result['entities'] if e['verdict'] == 'INVENTED']
    print(f"\n{'=' * 78}")
    print(f"  {len(bad)} unsupported role claim(s), {len(bad_e)} unsupported entity mention(s)")
    if bad:
        print("\n  Each of these assigns a role the system had no value for. The prose is")
        print("  not embellishing a known fact — it is supplying the fact itself.")
    print('=' * 78)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--state', help='story_lab state json (reads stop + tour_prose)')
    p.add_argument('--text-from-tour', action='store_true',
                   help='audit the tour_prose held in the state file')
    p.add_argument('--text-file', help='audit this file instead')
    p.add_argument('--record-json', help='stop record json (with --text-file)')
    p.add_argument('--evidence-file', help='grounding corpus (page_text / snippets)')
    p.add_argument('--json', dest='as_json', action='store_true')
    a = p.parse_args()

    record, text = {}, ''
    if a.state:
        st = json.load(open(a.state))
        record = st.get('stop', {})
        if a.text_from_tour:
            text = st.get('tour_orientation', '') + '\n' + st.get('tour_prose', '')
        evidence = '\n'.join(s.get('snippet', '') for s in st.get('ranked_snippets', []) or [])
    else:
        evidence = ''
    if a.text_file:
        text = open(a.text_file, encoding='utf-8').read()
    if a.record_json:
        record = json.load(open(a.record_json))
    if a.evidence_file:
        evidence = open(a.evidence_file, encoding='utf-8').read()

    if not text.strip():
        sys.exit('story_claim_lab: no text to audit (pass --text-from-tour or --text-file)')

    result = audit(text, record, evidence)
    if a.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        report(result, record)


if __name__ == '__main__':
    main()
