#!/usr/bin/env python3
"""test_local228_glue_falsification.py — LOCAL-228: Falsify the glue, not the detectors.

LOCAL-227 proved every detector notices being broken. But this week's four real
failures (D83, D91, D97, D103, D110) were all in the CODE THAT CALLS detectors,
reads their output, and interprets it. This test falsifies that glue layer.

Four categories:
  1. KEY-NAME CONTRACTS — assert the key a consumer reads EXISTS in what the
     producer returns. A .get('violations') against a producer emitting
     'findings' must fail loudly.
  2. SWALLOWED EXCEPTIONS — make underlying operations fail and assert the
     caller can DISTINGUISH failure from absence.
  3. UNCONSUMED OUTPUTS — for each verdict/field a detector can emit, find
     whether ANYTHING reads it. Report every one nothing consumes.
  4. CROSS-COMPONENT FORMAT AGREEMENT — where one component's output feeds
     another's input, assert the shapes match on real data.

IMPORTANT: This test is READ-ONLY against `audio_tours`. It never writes to
the database. All mutations are in-memory (monkeypatching) or in temp files.
133 tours, Nice list [1,12,14,17,21,24,27,28,29,152].
"""
import os
import sys
import json
import copy
import importlib.util
import traceback
from typing import Dict, List, Any, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, 'tests'))

from db_connection import get_connection, check_db_available


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def _import_module(name, path):
    """Import a module by file path."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _check_audio_tours_count():
    """Return (count, nice_list) from audiotours database."""
    if not check_db_available():
        return None, None
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM audio_tours")
        count = cur.fetchone()[0]
        cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,21,24,27,28,29,152) ORDER BY id")
        nice_list = [row[0] for row in cur.fetchall()]
        return count, nice_list
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 1: KEY-NAME CONTRACTS
# ═══════════════════════════════════════════════════════════════════════════════

def test_key_contract_style_validator_findings_vs_violations():
    """D83 reproducer: local205_analyze reads 'violations' but producer returns 'findings'.

    The style_validator_detector.validate_paragraph() returns a dict with key
    'findings'. But tests/local205_analyze.py reads style_result.get('violations', []).
    This means the analysis harness always gets [] regardless of what the
    detector found — the measurement was always zero.
    """
    sv = _import_module('style_validator_detector',
                        os.path.join(REPO_ROOT, 'style_validator_detector.py'))

    # Get actual output from validate_paragraph on known-firing text
    test_para = "Stand at the entrance and admire the facade. Look up and note the frescoes."
    result = sv.validate_paragraph(test_para)

    # What the producer ACTUALLY returns
    producer_keys = set(result.keys())
    assert 'findings' in producer_keys, (
        f"Producer changed! Expected 'findings' in keys, got: {producer_keys}"
    )

    # What local205_analyze.py reads:
    consumer_key = 'violations'
    consumer_gets = result.get(consumer_key, [])

    # THE FINDING: consumer reads a key that does not exist in producer output
    key_exists_in_producer = consumer_key in producer_keys
    actual_data = result.get('findings', [])

    return {
        'glue_point': 'tests/local205_analyze.py → style_validator_detector.validate_paragraph()',
        'producer_key': 'findings',
        'consumer_key': 'violations',
        'key_exists_in_producer': key_exists_in_producer,
        'consumer_gets': consumer_gets,
        'actual_data_length': len(actual_data),
        'notices_breakage': key_exists_in_producer,  # False = DOES NOT NOTICE
        'impact': 'All style A/B cells report 0.000 — the harness measures nothing',
    }


def test_key_contract_style_validator_rule_key():
    """local205_analyze reads v['rule'] but findings have 'rule_id'.

    Even if 'violations' were fixed to 'findings', the code then accesses
    v['rule'] on each item — but the actual findings dict uses 'rule_id'.
    """
    sv = _import_module('style_validator_detector',
                        os.path.join(REPO_ROOT, 'style_validator_detector.py'))

    # Get a finding from a known-firing sentence
    findings = sv.check_r1_imperatives("Stand at the entrance and admire the facade.")
    if not findings:
        # Try another
        findings = sv.check_r4_prescribed_feeling("You feel a sense of awe pressing down upon you.")
    
    assert findings, "PRECONDITION: need at least one finding to check key names"
    
    finding = findings[0]
    finding_keys = set(finding.keys())
    
    # local205_analyze.py line 174: [v['rule'] for v in style_result.get('violations', [])]
    consumer_reads_key = 'rule'
    producer_has_key = 'rule_id'
    
    return {
        'glue_point': "tests/local205_analyze.py line 174 → individual finding dict",
        'producer_key': producer_has_key,
        'consumer_key': consumer_reads_key,
        'key_exists_in_producer': consumer_reads_key in finding_keys,
        'finding_actual_keys': sorted(finding_keys),
        'notices_breakage': consumer_reads_key in finding_keys,
        'impact': 'Would raise KeyError if violations key were fixed (double fault)',
    }


def test_key_contract_corpus_coverage_verdict():
    """Verify generate_tour_text reads the correct key from corpus_coverage output."""
    cov = _import_module('corpus_coverage',
                         os.path.join(REPO_ROOT, 'corpus_coverage.py'))

    # Call with minimal data to get a result
    # Signature: assess_stop_coverage(stop_title, venue_name, passages, passage_roles=None)
    result = cov.assess_stop_coverage(
        "Test Stop",
        "Test Venue",
        ["This is a passage about Test Stop in the Test Venue."],
    )

    # generate_tour_text.py reads result['verdict']
    consumer_key = 'verdict'
    key_exists = consumer_key in result

    return {
        'glue_point': "generate_tour_text.py → corpus_coverage.assess_stop_coverage()",
        'producer_keys': sorted(result.keys()),
        'consumer_key': consumer_key,
        'key_exists_in_producer': key_exists,
        'notices_breakage': key_exists,  # True = contract holds
        'value': result.get(consumer_key),
    }


def test_key_contract_claim_check_verdict_counts():
    """Verify sentence_group_scorer reads correct keys from claim_check output."""
    cc = _import_module('claim_check', os.path.join(REPO_ROOT, 'claim_check.py'))

    # Minimal call
    result = cc.check_paragraph(
        text="The museum opened in 1990.",
        stop_title="Test Museum",
        venue_name="Test City",
        passages=["The museum was inaugurated on 21 June 1990 in Nice, France."],
    )

    # sentence_group_scorer reads: result['verdict_counts'].get('contradicted', 0)
    has_verdict_counts = 'verdict_counts' in result
    if has_verdict_counts:
        vc = result['verdict_counts']
        has_contradicted = 'contradicted' in vc
        has_supported = 'supported' in vc
        has_unsupported = 'unsupported' in vc
    else:
        has_contradicted = has_supported = has_unsupported = False

    return {
        'glue_point': "sentence_group_scorer.py → claim_check.check_paragraph()['verdict_counts']",
        'producer_keys': sorted(result.keys()),
        'has_verdict_counts': has_verdict_counts,
        'verdict_counts_keys': sorted(vc.keys()) if has_verdict_counts else [],
        'has_contradicted_key': has_contradicted,
        'notices_breakage': has_verdict_counts and has_contradicted,
    }


def test_key_contract_anchor_detector_classification():
    """Verify local205_analyze reads correct key from stop_anchor_detector_v2."""
    sad = _import_module('stop_anchor_detector_v2',
                         os.path.join(REPO_ROOT, 'tests', 'stop_anchor_detector_v2.py'))

    # build_corpus_anchors(venue_corpus: Dict, stop_title: str, tour_name: str)
    venue_corpus = {
        'passages': ["Henri Matisse was born in 1869.", "The museum houses his paper cutouts."]
    }
    corpus_anchors = sad.build_corpus_anchors(
        venue_corpus, "Musée Matisse", "Nice Art Museums"
    )
    
    result = sad.classify_paragraph(
        "Henri Matisse created his famous paper cutouts here.",
        corpus_anchors,
        "Musée Matisse",
        "Nice Art Museums"
    )

    # local205_analyze reads result['classification'] and result.get('anchor')
    has_classification = 'classification' in result
    
    return {
        'glue_point': "tests/local205_analyze.py → stop_anchor_detector_v2.classify_paragraph()",
        'producer_keys': sorted(result.keys()),
        'consumer_reads': ['classification', 'anchor'],
        'has_classification': has_classification,
        'classification_value': result.get('classification'),
        'notices_breakage': has_classification,
    }



# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 2: SWALLOWED EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def test_swallowed_exception_venue_resolver_get_instance_of():
    """D91 pattern: venue_resolver._get_instance_of swallows all exceptions.

    Line 473: `except Exception: return None`
    A network failure is indistinguishable from 'not a museum type'.
    """
    vr = _import_module('venue_resolver', os.path.join(REPO_ROOT, 'venue_resolver.py'))
    import requests

    # Healthy: call with a known museum QID (if network available)
    # We monkeypatch requests.get to simulate failure
    original_get = requests.get
    failure_detected_by_caller = False

    try:
        def failing_get(*args, **kwargs):
            raise ConnectionError("Simulated network failure")

        requests.get = failing_get

        # Call _get_instance_of — it should fail, but what does caller see?
        result = vr._get_instance_of("Q123456")

        # The function returns None on exception — same as "not a museum"
        # A caller cannot distinguish network failure from genuinely-not-a-museum
        failure_detected_by_caller = (result is not None)  # Always False here
    finally:
        requests.get = original_get

    return {
        'glue_point': "venue_resolver._get_instance_of() except block (line ~473)",
        'what_was_broken': "requests.get raises ConnectionError",
        'what_caller_sees': f"return value = {repr(result)}",
        'can_distinguish_failure_from_absence': failure_detected_by_caller,
        'notices_breakage': failure_detected_by_caller,
        'impact': "A museum is classified as 'not a museum' during network outage — silent data loss",
    }


def test_swallowed_exception_venue_resolver_get_coordinates():
    """venue_resolver._get_coordinates swallows exceptions, returns (0.0, 0.0).

    Line ~580: `except Exception: return 0.0, 0.0`
    A network failure is indistinguishable from 'entity has no coordinates'.
    """
    vr = _import_module('venue_resolver', os.path.join(REPO_ROOT, 'venue_resolver.py'))
    import requests

    original_get = requests.get
    try:
        def failing_get(*args, **kwargs):
            raise ConnectionError("Simulated network failure")
        requests.get = failing_get

        lat, lng = vr._get_coordinates("Q123456")
        
        # Returns (0.0, 0.0) on exception — same as "no coordinates in Wikidata"
        can_distinguish = not (lat == 0.0 and lng == 0.0)
    finally:
        requests.get = original_get

    return {
        'glue_point': "venue_resolver._get_coordinates() except block (line ~580)",
        'what_was_broken': "requests.get raises ConnectionError",
        'what_caller_sees': f"({lat}, {lng})",
        'can_distinguish_failure_from_absence': can_distinguish,
        'notices_breakage': can_distinguish,
        'impact': "Geo-disambiguation uses (0,0) during network issues — wrong candidate selected silently",
    }


def test_swallowed_exception_venue_resolver_geocode_city():
    """venue_resolver._geocode_city swallows exceptions, returns (0.0, 0.0)."""
    vr = _import_module('venue_resolver', os.path.join(REPO_ROOT, 'venue_resolver.py'))
    import requests

    original_get = requests.get
    try:
        def failing_get(*args, **kwargs):
            raise ConnectionError("Simulated network failure")
        requests.get = failing_get

        lat, lng = vr._geocode_city("Paris")
        can_distinguish = not (lat == 0.0 and lng == 0.0)
    finally:
        requests.get = original_get

    return {
        'glue_point': "venue_resolver._geocode_city() except block",
        'what_was_broken': "requests.get raises ConnectionError",
        'what_caller_sees': f"({lat}, {lng})",
        'can_distinguish_failure_from_absence': can_distinguish,
        'notices_breakage': can_distinguish,
        'impact': "City geocoding silently returns null island — all distance comparisons wrong",
    }


def test_swallowed_exception_venue_resolver_sparql():
    """venue_resolver SPARQL query handler: returns [] on exception.

    Line ~235: `except Exception as e: logger.warning(...); return []`
    A caller cannot distinguish 'no results found' from 'query failed'.
    """
    vr = _import_module('venue_resolver', os.path.join(REPO_ROOT, 'venue_resolver.py'))
    import requests

    original_get = requests.get
    try:
        def failing_get(*args, **kwargs):
            raise ConnectionError("Simulated SPARQL endpoint failure")
        requests.get = failing_get

        # Call a function that uses SPARQL internally
        # _search_entities is the entry point for wikidata search
        if hasattr(vr, '_search_entities'):
            result = vr._search_entities("Musée Matisse Nice")
            can_distinguish = result is not None and result != []
        else:
            result = "function not found"
            can_distinguish = False
    finally:
        requests.get = original_get

    return {
        'glue_point': "venue_resolver._search_entities() SPARQL except block (line ~235/439)",
        'what_was_broken': "requests.get raises ConnectionError on Wikidata API",
        'what_caller_sees': f"result = {repr(result)[:100]}",
        'can_distinguish_failure_from_absence': can_distinguish,
        'notices_breakage': can_distinguish,
        'impact': "Venue not found during API outage — tour generation proceeds without venue data",
    }


def test_swallowed_exception_coverage_selection_db():
    """generate_tour_text coverage selection: DB failure silently skips selection.

    Lines ~4057-4064: Two nested `except Exception: pass` blocks around DB connect.
    If the database is down, coverage selection is silently skipped and stops
    are selected in position order. No log distinguishes 'DB down' from
    'feature disabled'.
    """
    # This is a static analysis finding — the except blocks at lines 4057 and 4064
    # both do `pass`, making DB failure indistinguishable from "no DB needed".
    # We verify by reading the source.
    
    gen_path = os.path.join(REPO_ROOT, 'generate_tour_text.py')
    with open(gen_path, 'r') as f:
        content = f.read()

    # Find the coverage selection DB connection pattern
    # Pattern: try: ... _cs_conn = ... except Exception: pass
    import re
    # Look for the double-except pattern around _cs_conn
    pattern = r'_cs_conn.*?except\s+Exception.*?pass'
    matches = re.findall(pattern, content, re.DOTALL)

    return {
        'glue_point': "generate_tour_text.py coverage selection DB connect (lines ~4057-4064)",
        'what_was_broken': "DB unreachable",
        'what_caller_sees': "_cs_conn remains None → selection skipped",
        'can_distinguish_failure_from_absence': False,
        'notices_breakage': False,
        'except_pass_count': len(matches),
        'impact': "Coverage selection silently degrades to position-order when DB is down — no error logged in the first try block",
    }



# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 3: UNCONSUMED OUTPUTS
# ═══════════════════════════════════════════════════════════════════════════════

def test_unconsumed_outputs_survey():
    """Survey all detector outputs and which are consumed in production code.

    For each verdict or field a detector can emit, check whether anything in
    the production pipeline (generate_tour_text.py, tour_orchestrator_service.py,
    sentence_group_scorer.py) reads it.
    
    D97 sat unnoticed because nothing consumed CONTRADICTED in production.
    """
    import re
    
    # Read production files
    prod_files = [
        'generate_tour_text.py',
        'generate_tour_text_service.py',
        'tour_orchestrator_service.py',
        'tour_generation_service.py',
    ]
    
    prod_content = ""
    for f in prod_files:
        path = os.path.join(REPO_ROOT, f)
        if os.path.exists(path):
            with open(path, 'r') as fh:
                prod_content += fh.read() + "\n"

    # Also check sentence_group_scorer (integration layer, but not in production pipeline)
    scorer_path = os.path.join(REPO_ROOT, 'sentence_group_scorer.py')
    scorer_content = ""
    if os.path.exists(scorer_path):
        with open(scorer_path, 'r') as fh:
            scorer_content = fh.read()

    # All verdicts/fields that detectors can emit
    detector_outputs = {
        # claim_check verdicts
        'CONTRADICTED': {
            'producer': 'claim_check.check_paragraph() → verdict_counts["contradicted"]',
            'in_production': 'CONTRADICTED' in prod_content,
            'in_scorer': 'contradicted' in scorer_content,
        },
        'SUPPORTED_PARAPHRASE': {
            'producer': 'claim_check.check_paragraph() → claim["verdict"]',
            'in_production': 'SUPPORTED_PARAPHRASE' in prod_content,
            'in_scorer': 'SUPPORTED_PARAPHRASE' in scorer_content,
        },
        'SUPPORTED_ELSEWHERE': {
            'producer': 'claim_check.check_paragraph() → claim["verdict"]',
            'in_production': 'SUPPORTED_ELSEWHERE' in prod_content,
            'in_scorer': 'SUPPORTED_ELSEWHERE' in scorer_content,
        },
        'UNSUPPORTED (verdict)': {
            'producer': 'claim_check.check_paragraph() → claim["verdict"]',
            'in_production': 'unsupported_count' in prod_content or 'UNSUPPORTED' in prod_content,
            'in_scorer': 'unsupported_count' in scorer_content or 'UNSUPPORTED' in scorer_content,
        },
        'NOT_CHECKABLE': {
            'producer': 'claim_check.check_paragraph() → claim["verdict"]',
            'in_production': 'NOT_CHECKABLE' in prod_content,
            'in_scorer': 'NOT_CHECKABLE' in scorer_content or 'not_checkable' in scorer_content,
        },
        'SUPPORTED_EXTERNAL': {
            'producer': 'external_claim_verify.evaluate_evidence() → verdict',
            'in_production': 'SUPPORTED_EXTERNAL' in prod_content,
            'in_scorer': 'SUPPORTED_EXTERNAL' in scorer_content,
        },
        # corpus_coverage verdicts
        'COVERED': {
            'producer': 'corpus_coverage.assess_stop_coverage() → verdict',
            'in_production': "'COVERED'" in prod_content or '"COVERED"' in prod_content,
            'in_scorer': 'COVERED' in scorer_content,
        },
        'CREATOR_ONLY': {
            'producer': 'corpus_coverage.assess_stop_coverage() → verdict',
            'in_production': 'CREATOR_ONLY' in prod_content,
            'in_scorer': 'CREATOR_ONLY' in scorer_content,
        },
        'VENUE_ONLY': {
            'producer': 'corpus_coverage.assess_stop_coverage() → verdict',
            'in_production': 'VENUE_ONLY' in prod_content,
            'in_scorer': 'VENUE_ONLY' in scorer_content,
        },
        # style_validator outputs
        'R7 warnings (hallucinated_sensory)': {
            'producer': 'style_validator_detector.validate_paragraph() → findings with rule_id=R7',
            'in_production': 'R7' in prod_content or 'hallucinated_sensory' in prod_content,
            'in_scorer': 'R7' in scorer_content or 'check_r7' in scorer_content,
        },
        # stop_anchor verdicts  
        'NO_ANCHOR': {
            'producer': 'stop_anchor_detector_v2.classify_paragraph() → classification',
            'in_production': 'NO_ANCHOR' in prod_content,
            'in_scorer': 'NO_ANCHOR' in scorer_content,
        },
        'UNLINKED_ENTITY': {
            'producer': 'stop_anchor_detector_v2.classify_paragraph() → classification',
            'in_production': 'UNLINKED_ENTITY' in prod_content,
            'in_scorer': 'UNLINKED_ENTITY' in scorer_content,
        },
        # claim_check sub-fields
        'unsupported_claims (from scorer)': {
            'producer': 'sentence_group_scorer.score_group() → unsupported_claims',
            'in_production': 'unsupported_claims' in prod_content,
            'in_scorer': 'unsupported_claims' in scorer_content,
        },
    }

    unconsumed = []
    consumed_in_prod = []
    consumed_only_in_scorer = []

    for output_name, info in detector_outputs.items():
        if info['in_production']:
            consumed_in_prod.append(output_name)
        elif info['in_scorer']:
            consumed_only_in_scorer.append(output_name)
        else:
            unconsumed.append(output_name)

    return {
        'glue_point': "All detector outputs → production pipeline consumption",
        'consumed_in_production': consumed_in_prod,
        'consumed_only_in_scorer_not_production': consumed_only_in_scorer,
        'unconsumed_by_anything': unconsumed,
        'notices_breakage': len(unconsumed) == 0,
        'impact': (
            f"{len(consumed_only_in_scorer)} outputs consumed only by "
            f"sentence_group_scorer (offline scoring, not in production generation pipeline). "
            f"{len(unconsumed)} outputs consumed by nothing at all."
        ),
    }


def test_unconsumed_contradicted_in_generation():
    """D97 reproducer: CONTRADICTED verdict is not consumed in the tour generation pipeline.

    claim_check can emit CONTRADICTED. sentence_group_scorer blocks on it.
    But sentence_group_scorer is NOT imported by generate_tour_text.py or any
    production service. The block logic exists but is never reached in production.
    """
    # Verify claim_check is NOT imported in generate_tour_text.py
    gen_path = os.path.join(REPO_ROOT, 'generate_tour_text.py')
    with open(gen_path, 'r') as f:
        gen_content = f.read()
    
    imports_claim_check = ('import claim_check' in gen_content or
                          'from claim_check' in gen_content)
    imports_scorer = ('import sentence_group_scorer' in gen_content or
                     'from sentence_group_scorer' in gen_content)

    # Check all service files
    service_files = [
        'generate_tour_text_service.py',
        'tour_orchestrator_service.py',
        'tour_generation_service.py',
    ]
    service_imports_scorer = False
    for sf in service_files:
        path = os.path.join(REPO_ROOT, sf)
        if os.path.exists(path):
            with open(path, 'r') as f:
                content = f.read()
            if 'sentence_group_scorer' in content:
                service_imports_scorer = True

    return {
        'glue_point': "claim_check CONTRADICTED verdict → production generation pipeline",
        'generate_tour_text_imports_claim_check': imports_claim_check,
        'generate_tour_text_imports_scorer': imports_scorer,
        'any_service_imports_scorer': service_imports_scorer,
        'notices_breakage': imports_claim_check or imports_scorer or service_imports_scorer,
        'impact': (
            "A tour with CONTRADICTED claims is generated and delivered to users. "
            "The block logic exists in sentence_group_scorer but is only exercised "
            "in offline evaluation scripts (run_local220), never in the production path."
        ),
    }



# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 4: CROSS-COMPONENT FORMAT AGREEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def test_format_agreement_claim_check_to_external_verify():
    """D103 reproducer: claim_check emits bare text, evaluate_evidence needs context.

    claim_check.check_paragraph() extracts claims and sets claim['text'] to the
    bare value (e.g. '320 feet'). external_claim_verify.evaluate_evidence()
    needs surrounding context to bind the claim to a subject.

    When claim_text is just '320 feet', evaluate_evidence cannot determine
    WHAT is 320 feet, and refuses the claim.
    """
    cc = _import_module('claim_check', os.path.join(REPO_ROOT, 'claim_check.py'))

    # Use a sentence with a numeric claim
    test_text = "The deep bay of Villefranche reaches depths of approximately 320 feet at its outer mouth."
    
    result = cc.check_paragraph(
        text=test_text,
        stop_title="Bay of Villefranche",
        venue_name="French Riviera",
        passages=[],  # No passages → claims are UNSUPPORTED
    )

    # Find a NUMBER-type claim
    number_claims = [c for c in result.get('claims', []) if c.get('type') == 'NUMBER']
    date_claims = [c for c in result.get('claims', []) if c.get('type') == 'DATE']
    
    # Check what text the claim carries
    bare_claims = []
    contextual_claims = []
    for claim in result.get('claims', []):
        text = claim.get('text', '')
        # "Bare" means just the value without subject context
        # A bare claim like "320 feet" has no subject; "reaches 320 feet" is slightly better;
        # "Bay of Villefranche reaches 320 feet" carries full context
        words = text.split()
        if len(words) <= 3:  # Very short = likely bare
            bare_claims.append(claim)
        else:
            contextual_claims.append(claim)

    # Also check: does claim dict include 'sentence' field for context recovery?
    has_sentence_field = all('sentence' in c for c in result.get('claims', []))

    return {
        'glue_point': "claim_check.check_paragraph()['claims'][n]['text'] → external_claim_verify.evaluate_evidence(claim_text=...)",
        'total_claims_found': len(result.get('claims', [])),
        'number_claims': len(number_claims),
        'date_claims': len(date_claims),
        'bare_claims_count': len(bare_claims),
        'bare_claim_examples': [c.get('text', '') for c in bare_claims[:3]],
        'contextual_claims_count': len(contextual_claims),
        'has_sentence_field_for_recovery': has_sentence_field,
        'notices_breakage': len(bare_claims) == 0,  # False if any bare claims exist
        'impact': (
            "NUMBER and DATE claims get bare text like '320 feet' or '1990'. "
            "evaluate_evidence() cannot bind these to a subject without the sentence field. "
            "D103: every date and number was refused because the handoff strips context."
        ),
    }


def test_format_agreement_style_findings_structure():
    """Verify findings from individual checkers match what sentence_group_scorer expects.

    sentence_group_scorer reads f['rule_id'] from individual checker results.
    Verify that's actually what the checkers return.
    """
    sv = _import_module('style_validator_detector',
                        os.path.join(REPO_ROOT, 'style_validator_detector.py'))

    # Get findings from multiple checkers
    checkers = {
        'check_r1_imperatives': "Stand at the entrance and admire the facade.",
        'check_r3_suggestive_exploration': "As you walk through the gallery, the paintings seem to follow you.",
        'check_r4_prescribed_feeling': "You feel a sense of awe pressing down upon you.",
        'check_r7_hallucinated_sensory': "You can almost hear the echo of his brushstrokes on the canvas.",
    }

    mismatches = []
    for checker_name, test_sentence in checkers.items():
        checker_fn = getattr(sv, checker_name, None)
        if not checker_fn:
            mismatches.append(f"{checker_name}: function not found")
            continue
        findings = checker_fn(test_sentence)
        if not findings:
            continue
        for f in findings:
            if 'rule_id' not in f:
                mismatches.append(f"{checker_name}: finding missing 'rule_id', has keys: {sorted(f.keys())}")

    return {
        'glue_point': "style_validator_detector.check_r*() → sentence_group_scorer reads f['rule_id']",
        'mismatches': mismatches,
        'notices_breakage': len(mismatches) == 0,
        'impact': "If any checker returned findings without 'rule_id', scorer would crash on access",
    }


def test_format_agreement_scorer_output_for_downstream():
    """Verify sentence_group_scorer.score_group() output matches what run_local220 reads.
    
    run_local220 reads:
      record['style_verdicts']['rules_violated']
      record['style_verdicts']['findings']
      record['claim_verdicts']['verdict_counts']
      record['publishable']
      record['block_reasons']
    """
    try:
        scorer = _import_module('sentence_group_scorer',
                               os.path.join(REPO_ROOT, 'sentence_group_scorer.py'))
    except Exception as e:
        return {
            'glue_point': "sentence_group_scorer.score_group() → run_local220 consumers",
            'error': f"Could not import: {e}",
            'notices_breakage': False,
        }

    # We need passages for a real call, but can check expected output structure
    # by examining the function's documented return pattern
    scorer_path = os.path.join(REPO_ROOT, 'sentence_group_scorer.py')
    with open(scorer_path, 'r') as f:
        content = f.read()

    # Check the return dict construction has the expected keys
    consumer_keys = ['style_verdicts', 'claim_verdicts', 'publishable', 'block_reasons', 'unsupported_claims']
    missing_in_source = [k for k in consumer_keys if k not in content]

    return {
        'glue_point': "sentence_group_scorer.score_group() → run_local220 consumers",
        'consumer_expected_keys': consumer_keys,
        'missing_from_producer_source': missing_in_source,
        'notices_breakage': len(missing_in_source) == 0,
    }



# ═══════════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

ALL_TESTS = [
    # Category 1: Key-name contracts
    test_key_contract_style_validator_findings_vs_violations,
    test_key_contract_style_validator_rule_key,
    test_key_contract_corpus_coverage_verdict,
    test_key_contract_claim_check_verdict_counts,
    test_key_contract_anchor_detector_classification,
    # Category 2: Swallowed exceptions
    test_swallowed_exception_venue_resolver_get_instance_of,
    test_swallowed_exception_venue_resolver_get_coordinates,
    test_swallowed_exception_venue_resolver_geocode_city,
    test_swallowed_exception_venue_resolver_sparql,
    test_swallowed_exception_coverage_selection_db,
    # Category 3: Unconsumed outputs
    test_unconsumed_outputs_survey,
    test_unconsumed_contradicted_in_generation,
    # Category 4: Cross-component format agreement
    test_format_agreement_claim_check_to_external_verify,
    test_format_agreement_style_findings_structure,
    test_format_agreement_scorer_output_for_downstream,
]


def main():
    print("=" * 70)
    print("LOCAL-228: GLUE FALSIFICATION REPORT")
    print("=" * 70)
    print()

    # Baseline
    count, nice_list = _check_audio_tours_count()
    if count is not None:
        print(f"BASELINE: audio_tours = {count}, Nice list = {nice_list}")
    else:
        print("BASELINE: DB not available (skipping count check)")
    print()

    results = []
    notices_breakage = 0
    does_not_notice = 0
    errors = 0

    for test_fn in ALL_TESTS:
        test_name = test_fn.__name__
        try:
            result = test_fn()
            results.append((test_name, result))
            if result.get('notices_breakage'):
                notices_breakage += 1
                status = "✓ CONTRACT HOLDS"
            else:
                does_not_notice += 1
                status = "✗ DOES NOT NOTICE"
            print(f"  {test_name}... {status}")
            if not result.get('notices_breakage'):
                # Print details for failures
                impact = result.get('impact', '')
                if impact:
                    print(f"    └─ {impact[:120]}")
        except Exception as e:
            errors += 1
            print(f"  {test_name}... ⚠ ERROR: {e}")
            traceback.print_exc()
            results.append((test_name, {'error': str(e), 'notices_breakage': None}))

    # Post-check
    print()
    count_after, nice_list_after = _check_audio_tours_count()
    if count_after is not None:
        print(f"POST-CHECK: audio_tours = {count_after}, Nice list = {nice_list_after}")
        if count == count_after and nice_list == nice_list_after:
            print("  ✓ Database unchanged.")
        else:
            print("  ✗ DATABASE CHANGED! This should not happen!")
    else:
        print("POST-CHECK: DB not available (count check skipped)")

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Glue points where contract HOLDS:        {notices_breakage}")
    print(f"  Glue points that DO NOT NOTICE breakage: {does_not_notice}")
    print(f"  Tests with errors:                       {errors}")
    print()

    # Detailed findings
    print("=" * 70)
    print("DETAILED FINDINGS — Glue points that cannot detect their own breakage")
    print("=" * 70)
    print()

    for test_name, result in results:
        if result.get('notices_breakage') == False:
            print(f"─── {test_name} ───")
            print(f"  Glue point: {result.get('glue_point', '?')}")
            if 'what_was_broken' in result:
                print(f"  What was broken: {result['what_was_broken']}")
            if 'what_caller_sees' in result:
                print(f"  What caller sees: {result['what_caller_sees']}")
            if 'producer_key' in result and 'consumer_key' in result:
                print(f"  Producer emits key: '{result['producer_key']}'")
                print(f"  Consumer reads key: '{result['consumer_key']}'")
            if 'can_distinguish_failure_from_absence' in result:
                print(f"  Can distinguish failure from absence: {result['can_distinguish_failure_from_absence']}")
            if 'impact' in result:
                print(f"  Impact: {result['impact']}")
            if 'consumed_only_in_scorer_not_production' in result:
                print(f"  Outputs in scorer only (not production): {result['consumed_only_in_scorer_not_production']}")
            if 'unconsumed_by_anything' in result:
                print(f"  Outputs consumed by nothing: {result['unconsumed_by_anything']}")
            print()

    # Return exit code
    return 0 if errors == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
