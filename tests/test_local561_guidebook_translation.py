#!/usr/bin/env python3
"""
LOCAL-561: Guidebook-style LLM translation — structure by CODE, names by gpt-4o,
prose by gpt-4o-mini.

Deterministic unit tests with a MOCKED OpenAI client. No network, no AWS, no DB.
These prove, by effect, the acceptance checks from the task:

  A. STRUCTURE BY CODE
     - No output line starts with the English 'Stop ', 'Orientation:' or 'Directions:'.
     - The native 'Stop N:' header is emitted in the target language.
     - Orientation:/Directions: carry the native label from _STRUCTURE_LABELS.
     - Line count preserved; Address/Coordinates byte-exact.

  B. NAMES BY gpt-4o
     - One gpt-4o call per tour produces a {source -> target} glossary.
     - The glossary is cached per (tour, language) — a second build is free.
     - Streets with no exonym keep their Latin name (the prompt instructs this; the
       mock honours it, and the test asserts the glossary round-trips such a name).
     - Wikidata labels win over the model when present.
     - Every glossary name appears in the stop output, in some inflected form
       (for ru: match the stem — the first 4 letters of each word).

  C. PROSE BY gpt-4o-mini (guidebook style)
     - Imperative density on tour 301 stop 1 is <= 1 (narration is description, not
       a string of orders), counting the ru imperative verbs the task lists.

  D. SAFETIES PRESERVED
     - prose pass falls back to AWS per segment when the model drops a segment.
     - The guidebook pipeline is OFF unless engine='llm' AND _GUIDEBOOK — the default
       (aws) engine never changes.

Run:  pytest -q tests/test_local561_guidebook_translation.py
"""
import os
import re
import sys
import logging
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'translation-service'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _install_stub_modules():
    """Stub heavy third-party deps so translation_service imports in a bare env."""
    if 'boto3' not in sys.modules:
        sys.modules['boto3'] = MagicMock()
    if 'bs4' not in sys.modules:
        bs4_stub = MagicMock()
        bs4_stub.BeautifulSoup = MagicMock()
        bs4_stub.NavigableString = MagicMock()
        sys.modules['bs4'] = bs4_stub


_install_stub_modules()


def _make_service(engine='llm', api_key='test-key', guidebook='on', env=None):
    """Construct a TranslationService with boto3 patched out (no AWS at init)."""
    base = {'TRANSLATION_ENGINE': engine, 'OPENAI_API_KEY': api_key,
            'TRANSLATION_GUIDEBOOK': guidebook}
    if env:
        base.update(env)
    with patch.dict(os.environ, base, clear=False):
        with patch('boto3.client', return_value=MagicMock()):
            import importlib
            import translation_service as ts
            importlib.reload(ts)
            svc = ts.TranslationService()
    return svc, ts


# ─────────────────────────────────────────────────────────────────────────────
# Byte-exact Stop 1 of tour 301 (verified against the live DB on 2026-10-02),
# as _split_tour_content_into_stops returns it (WITHOUT the 'Stop 1:' header).
# ─────────────────────────────────────────────────────────────────────────────
TOUR301_STOP1 = (
    "Castle Hill of Nice\n"
    "\n"
    "Address: 06300 Nice, France\n"
    "\n"
    "Coordinates: 43.6942, 7.2797\n"
    "\n"
    "Type/Specialty: Scenic viewpoint\n"
    "\n"
    "Specific Examples: Panoramic views of Nice, waterfalls, ruins of a former chateau\n"
    "\n"
    "Orientation: Head northeast on Quai des \u00c9tats-Unis, then take the stairs up the "
    "hill, offering a preview of the stunning views ahead. Stand at the edge of Castle "
    "Hill of Nice, overlooking the azure waters of the Mediterranean Sea. Look for the "
    "remnants of ancient fortifications and lush gardens below.\n"
    "\n"
    "You are about to embark on a journey through the vibrant streets of Nice, where the "
    "echoes of ancient Ligurians, the grandeur of the Savoy dynasty, and the whispers of "
    "artists and revolutionaries intertwine to shape the city's rich tapestry. Each "
    "chapter of this exploration unveils a different facet of Nice's spirit: from the "
    "ancient citadel standing proud amidst ruins to the lavish Baroque interiors that "
    "hold the secrets of the Savoy family. Delve into the cultural heartbeat of the city "
    "at the opera house where Berlioz and Verdi once graced the stage, and discover the "
    "birthplace of Henri Matisse's color palette amidst the bustling stalls. As you "
    "traverse the glamorous pathways once trodden by English aristocrats, the hidden "
    "stories of Nice's past and present reveal themselves, painting a vivid picture of a "
    "city steeped in history and allure.\n"
    "\n"
    "Amidst the ruins of Castle Hill, discover the first stronghold of the Ligurian "
    "tribe, dating back to 2nd century BC. Traces of the past whisper stories of "
    "resilience against invaders, including the Saracens and the Turks. As you wander, "
    "feel the cool breeze carrying scents of pine and sea salt, immersing you in the "
    "history of this strategic site. The ancient stones underfoot echo the everyday "
    "rhythms of those who once called this hill home. Descend and envision the vibrant "
    "streets below, pulsing with the lifeblood of Nice.\n"
    "\n"
    "Directions: As you leave the Castle Hill of Nice, head down towards the Old Town. "
    "Wander through the charming narrow streets until you reach Rue Droite. Follow this "
    "street until you arrive at Palais Lascaris, a beautiful Baroque palace on your left."
)

# A two-stop tour_content string (headers included) for glossary/extraction tests.
TOUR301_CONTENT = (
    "Step-by-Step Audio Guided Tour: Nice, France - Walking Tour\n"
    "Tour-Category: walking\n"
    "\n"
    "Stop 1: Castle Hill of Nice\n" + TOUR301_STOP1[len("Castle Hill of Nice"):] + "\n"
    "\n"
    "Stop 2: Palais Lascaris\n"
    "\n"
    "Orientation: As you arrive at the Palais Lascaris, look for the grand facade.\n"
    "\n"
    "Directions: From Palais Lascaris, head south on Rue Droite to Place Rossetti."
)

# The established-glossary the gpt-4o pass is expected to return for ru (from the task's
# LEAD experiment: «Замковая гора Ниццы», «Пале Ласкарис», «Опера Ницца»). Streets with
# no exonym keep their Latin name.
RU_GLOSSARY = {
    "Castle Hill of Nice": "\u0417\u0430\u043c\u043a\u043e\u0432\u0430\u044f \u0433\u043e\u0440\u0430 \u041d\u0438\u0446\u0446\u044b",  # Замковая гора Ниццы
    "Palais Lascaris": "\u041f\u0430\u043b\u0435 \u041b\u0430\u0441\u043a\u0430\u0440\u0438\u0441",  # Пале Ласкарис
    "Op\u00e9ra de Nice": "\u041e\u043f\u0435\u0440\u0430 \u041d\u0438\u0446\u0446\u044b",  # Опера Ниццы
    "Rue Droite": "Rue Droite",  # street, no exonym → Latin preserved
}

# ru imperative verbs from the task's list — the imperative-density check uses these.
RU_IMPERATIVES = [
    "\u043e\u0442\u043a\u0440\u043e\u0439\u0442\u0435",   # откройте
    "\u043f\u043e\u0447\u0443\u0432\u0441\u0442\u0432\u0443\u0439\u0442\u0435",  # почувствуйте
    "\u0438\u0449\u0438\u0442\u0435",  # ищите
    "\u043f\u043e\u0433\u0440\u0443\u0437\u0438\u0442\u0435\u0441\u044c",  # погрузитесь
    "\u043f\u0440\u0435\u0434\u0441\u0442\u0430\u0432\u044c\u0442\u0435",  # представьте
    "\u0431\u0440\u043e\u0434\u0438\u0442\u0435",  # бродите
    "\u043d\u0430\u0441\u043b\u0430\u0434\u0438\u0442\u0435\u0441\u044c",  # насладитесь
    "\u0438\u0441\u0441\u043b\u0435\u0434\u0443\u0439\u0442\u0435",  # исследуйте
]


def _imperative_density(narration_text):
    """Count narration SENTENCES that begin with one of the ru imperative verbs.

    Mirrors the task's deterministic check. We split on sentence terminators and test
    the first word of each sentence (case-insensitive) against the imperative list.
    """
    sentences = re.split(r'(?<=[.!?])\s+', narration_text.strip())
    n = 0
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        first = re.split(r'[\s,]+', s, maxsplit=1)[0].lower().strip('«»"\'()')
        if first in RU_IMPERATIVES:
            n += 1
    return n


# ─────────────────────────────────────────────────────────────────────────────
# A faithful guidebook-RU mock. It writes DESCRIPTIVE narration (no leading
# imperatives), uses the glossary names where they occur in the English segment, and
# keeps the <<<SEG>>> markers. This models a well-behaved gpt-4o-mini under the
# guidebook prompt + glossary.
# ─────────────────────────────────────────────────────────────────────────────
def _ru_guidebook_prose(system_prompt, user_text, model=None, response_json=False):
    # The real service prepends an instruction preamble (which itself mentions the
    # <<<SEG>>> marker) before the joined segments, separated by a blank line. Strip the
    # preamble so we operate only on the actual passages, exactly as a real model would.
    _, _, payload = user_text.partition('\n\n')
    body = payload.split('<<<SEG>>>')
    out_parts = []
    for seg in body:
        seg_stripped = seg.strip()
        # Descriptive opener (future/impersonal), never an imperative.
        ru = "\u0417\u0434\u0435\u0441\u044c \u0432\u044b \u043e\u0431\u043d\u0430\u0440\u0443\u0436\u0438\u0442\u0435 "  # "Здесь вы обнаружите "
        # Reproduce any glossary target name whose English key is in this segment.
        for en, tgt in RU_GLOSSARY.items():
            if en in seg_stripped:
                ru += tgt + " "
        ru += "\u043e\u043f\u0438\u0441\u0430\u043d\u0438\u0435."  # "описание." (description.)
        # Preserve the segment's surrounding newlines so line count is stable.
        lead = seg[:len(seg) - len(seg.lstrip('\n'))]
        trail = seg[len(seg.rstrip('\n')):]
        out_parts.append(f"{lead}{ru}{trail}")
    return {'text': '<<<SEG>>>'.join(out_parts), 'input_tokens': 300, 'output_tokens': 320}


# ═════════════════════════════════════════════════════════════════════════════
# A. STRUCTURE BY CODE
# ═════════════════════════════════════════════════════════════════════════════
def test_structure_strip_restore_preserves_lines_and_nav():
    svc, ts = _make_service()
    template, segments = svc._strip_structure_for_model(TOUR301_STOP1, 'ru')
    # One template token per source line → line count is structurally preserved.
    assert len(template) == TOUR301_STOP1.count('\n') + 1
    # Fake-translate every prose segment, then restore.
    restored = svc._restore_structure(template, [f"RU{i}" for i in range(len(segments))])
    assert restored.count('\n') == TOUR301_STOP1.count('\n')
    # Address/Coordinates byte-exact.
    assert 'Address: 06300 Nice, France' in restored
    assert 'Coordinates: 43.6942, 7.2797' in restored


def test_no_english_structural_labels_in_output():
    svc, ts = _make_service()
    with patch.object(svc, '_openai_chat', side_effect=_ru_guidebook_prose):
        out = svc._translate_stop_guidebook(TOUR301_STOP1, 1, 'ru', RU_GLOSSARY)
    for line in out.split('\n'):
        s = line.strip()
        assert not s.startswith('Orientation:'), f'English Orientation label leaked: {line!r}'
        assert not s.startswith('Directions:'), f'English Directions label leaked: {line!r}'
        assert not re.match(r'^Stop\s+\d+', s), f'English Stop header leaked: {line!r}'
    # Native spoken labels are present.
    assert '\u041a\u0430\u043a \u0441\u043e\u0440\u0438\u0435\u043d\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c\u0441\u044f:' in out  # Как сориентироваться:
    assert '\u041a\u0430\u043a \u043f\u0440\u043e\u0439\u0442\u0438:' in out  # Как пройти:


def test_native_stop_header_per_language():
    svc, ts = _make_service()
    assert svc._native_stop_header(1, 'ru') == '\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0430 1'  # Остановка 1
    assert svc._native_stop_header(3, 'es') == 'Parada 3'
    assert svc._native_stop_header(2, 'fr') == 'Arr\u00eat 2'
    # Unknown language → explicit English fallback (never a mis-declined guess).
    assert svc._native_stop_header(1, 'xx') == 'Stop 1'


def test_type_specialty_label_english_value_prose():
    """The three value-prose nav lines keep the English LABEL (mobile parses it) but
    translate the VALUE as prose."""
    svc, ts = _make_service()
    template, segments = svc._strip_structure_for_model(TOUR301_STOP1, 'ru')
    joined = '\n'.join(template)
    assert 'Type/Specialty: {{PROSE:' in joined
    assert 'Specific Examples: {{PROSE:' in joined
    # The nav VALUES are among the prose segments (so they DO get translated).
    assert 'Scenic viewpoint' in segments


# ═════════════════════════════════════════════════════════════════════════════
# B. NAMES BY gpt-4o
# ═════════════════════════════════════════════════════════════════════════════
def test_glossary_built_once_and_cached():
    svc, ts = _make_service()
    calls = {'n': 0}

    def _names(system_prompt, user_text, model=None, response_json=False):
        calls['n'] += 1
        assert model == 'gpt-4o', 'names pass must use gpt-4o'
        assert response_json is True, 'names pass must request JSON'
        import json as _j
        return {'text': _j.dumps(RU_GLOSSARY), 'input_tokens': 500, 'output_tokens': 120}

    # Disable Wikidata so this test is purely about the model + cache.
    with patch.object(svc, '_wikidata_label', return_value=None):
        with patch.object(svc, '_openai_chat', side_effect=_names):
            g1 = svc._build_names_glossary(301, TOUR301_CONTENT, 'ru')
            g2 = svc._build_names_glossary(301, TOUR301_CONTENT, 'ru')
    assert g1 == g2 == RU_GLOSSARY
    assert calls['n'] == 1, 'second build must hit the (tour, language) cache'


def test_glossary_street_keeps_latin_name():
    svc, ts = _make_service()
    import json as _j
    with patch.object(svc, '_wikidata_label', return_value=None):
        with patch.object(svc, '_openai_chat',
                          side_effect=lambda s, u, model=None, response_json=False:
                          {'text': _j.dumps(RU_GLOSSARY), 'input_tokens': 1, 'output_tokens': 1}):
            g = svc._build_names_glossary(301, TOUR301_CONTENT, 'ru')
    # Street with no established exonym stays in Latin letters.
    assert g['Rue Droite'] == 'Rue Droite'


def test_wikidata_label_wins_over_model():
    svc, ts = _make_service()
    import json as _j
    model_glossary = dict(RU_GLOSSARY)
    model_glossary['Castle Hill of Nice'] = '\u041d\u0415\u041f\u0420\u0410\u0412\u0418\u041b\u042c\u041d\u041e'  # a wrong model guess

    def _wikidata(name, target_language, _timeout=8):
        if name == 'Castle Hill of Nice':
            return '\u0417\u0430\u043c\u043a\u043e\u0432\u0430\u044f \u0433\u043e\u0440\u0430'  # Wikidata label «Замковая гора»
        return None

    with patch.object(svc, '_wikidata_label', side_effect=_wikidata):
        with patch.object(svc, '_openai_chat',
                          side_effect=lambda s, u, model=None, response_json=False:
                          {'text': _j.dumps(model_glossary), 'input_tokens': 1, 'output_tokens': 1}):
            g = svc._build_names_glossary(301, TOUR301_CONTENT, 'ru')
    assert g['Castle Hill of Nice'] == '\u0417\u0430\u043c\u043a\u043e\u0432\u0430\u044f \u0433\u043e\u0440\u0430', \
        'Wikidata label must win over the model form'


def _ru_stem_present(name_ru, text):
    """Task's inflection check for ru: each word of the glossary name matches on its
    first 4 letters (the stem), allowing for case endings."""
    for word in re.split(r'[\s\-]+', name_ru):
        w = word.strip('«»".,!?()')
        if len(w) < 4:
            # short/particle words: require exact token presence
            if w and w not in text:
                return False
            continue
        stem = w[:4]
        if stem.lower() not in text.lower():
            return False
    return True


def test_glossary_names_appear_in_output_inflected():
    """Every glossary name whose English key occurs in the stop must appear in the ru
    output, matched by its stem (first 4 letters of each word)."""
    svc, ts = _make_service()
    with patch.object(svc, '_openai_chat', side_effect=_ru_guidebook_prose):
        out = svc._translate_stop_guidebook(TOUR301_STOP1, 1, 'ru', RU_GLOSSARY)
    # Castle Hill of Nice and Palais Lascaris and Rue Droite all occur in stop 1.
    for en in ('Castle Hill of Nice', 'Palais Lascaris', 'Rue Droite'):
        tgt = RU_GLOSSARY[en]
        assert _ru_stem_present(tgt, out), f'glossary name {tgt!r} (for {en!r}) missing from output'


# ═════════════════════════════════════════════════════════════════════════════
# C. PROSE BY gpt-4o-mini — imperative density
# ═════════════════════════════════════════════════════════════════════════════
def test_imperative_density_on_tour301_stop1_leq_1():
    svc, ts = _make_service()
    with patch.object(svc, '_openai_chat', side_effect=_ru_guidebook_prose):
        out = svc._translate_stop_guidebook(TOUR301_STOP1, 1, 'ru', RU_GLOSSARY)
    # Narration paragraphs only: exclude the Directions line (real walking instructions)
    # and the nav/label lines.
    narration_lines = []
    for line in out.split('\n'):
        s = line.strip()
        if not s:
            continue
        if s.startswith('\u041a\u0430\u043a \u043f\u0440\u043e\u0439\u0442\u0438:'):  # «Как пройти:» (Directions)
            continue
        if s.startswith('Address:') or s.startswith('Coordinates:') \
           or s.startswith('Type/Specialty:') or s.startswith('Specific Examples:'):
            continue
        narration_lines.append(s)
    density = _imperative_density('\n'.join(narration_lines))
    assert density <= 1, f'imperative density {density} > 1 — narration reads as orders'


def test_imperative_density_helper_detects_orders():
    """Guard the metric itself: a string of ru imperatives scores > 1 (so the <=1
    assertion above is meaningful, not vacuous)."""
    orders = (
        "\u041e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 \u0434\u043b\u044f \u0441\u0435\u0431\u044f. "  # Откройте для себя.
        "\u041f\u043e\u0447\u0443\u0432\u0441\u0442\u0432\u0443\u0439\u0442\u0435 \u0432\u0435\u0442\u0435\u0440. "  # Почувствуйте ветер.
        "\u0418\u0449\u0438\u0442\u0435 \u0440\u0443\u0438\u043d\u044b."  # Ищите руины.
    )
    assert _imperative_density(orders) == 3


# ═════════════════════════════════════════════════════════════════════════════
# D. SAFETIES PRESERVED
# ═════════════════════════════════════════════════════════════════════════════
def test_prose_falls_back_to_aws_on_segment_count_mismatch(caplog):
    svc, ts = _make_service()
    svc.translate_client.translate_text.return_value = {'TranslatedText': 'AWS_SEG'}

    def _drops_a_segment(system_prompt, user_text, model=None, response_json=False):
        # Return only ONE segment regardless of how many were sent.
        return {'text': 'only one segment', 'input_tokens': 10, 'output_tokens': 5}

    segments = ['first passage', 'second passage', 'third passage']
    with caplog.at_level(logging.WARNING):
        with patch.object(svc, '_openai_chat', side_effect=_drops_a_segment):
            out = svc._translate_prose_segments_guidebook(segments, 'ru', {})
    assert out == ['AWS_SEG', 'AWS_SEG', 'AWS_SEG'], 'must fall back to AWS per segment'
    assert any('[TRANSLATE-561] prose FALLBACK' in r.message for r in caplog.records)


def test_prose_retries_once_then_succeeds(caplog):
    svc, ts = _make_service()
    calls = {'n': 0}

    def _first_bad_then_good(system_prompt, user_text, model=None, response_json=False):
        calls['n'] += 1
        if calls['n'] == 1:
            return {'text': 'collapsed', 'input_tokens': 5, 'output_tokens': 5}  # 1 seg
        return _ru_guidebook_prose(system_prompt, user_text, model, response_json)

    segments = ['alpha passage', 'beta passage']
    with caplog.at_level(logging.WARNING):
        with patch.object(svc, '_openai_chat', side_effect=_first_bad_then_good):
            out = svc._translate_prose_segments_guidebook(segments, 'ru', {})
    assert calls['n'] == 2, 'exactly one retry'
    assert len(out) == 2
    assert any('[TRANSLATE-561] prose RETRY' in r.message for r in caplog.records)


def test_guidebook_off_by_default_for_aws_engine():
    """Default engine 'aws' must NOT trigger the guidebook pipeline."""
    svc, ts = _make_service(engine='aws')
    svc.translate_client.translate_text.return_value = {'TranslatedText': 'HOLA'}
    called = {'guidebook': False}
    orig = svc._translate_stop_guidebook

    def _spy(*a, **k):
        called['guidebook'] = True
        return orig(*a, **k)

    with patch.object(svc, '_translate_stop_guidebook', side_effect=_spy):
        svc._translate_one_stop(0, 'Hello\n\nWorld', 1, 'es', {})
    assert called['guidebook'] is False, 'aws engine must not use the guidebook pipeline'


def test_guidebook_can_be_disabled_via_flag():
    """engine='llm' but TRANSLATION_GUIDEBOOK=off → guidebook pipeline not used."""
    svc, ts = _make_service(engine='llm', guidebook='off')
    assert svc._GUIDEBOOK is False
    called = {'guidebook': False}

    def _spy(*a, **k):
        called['guidebook'] = True
        return 'x'

    # translate_text is the LOCAL-559R path; stub it so no network is attempted.
    with patch.object(svc, 'translate_text', return_value='Castle\n\nHill'):
        with patch.object(svc, '_translate_stop_guidebook', side_effect=_spy):
            svc._translate_one_stop(0, 'Castle\n\nHill', 1, 'es', {})
    assert called['guidebook'] is False


def test_names_and_prose_use_distinct_models():
    """Metering must attribute the names call to gpt-4o and prose to gpt-4o-mini."""
    svc, ts = _make_service()
    seen = {'models': []}

    def _chat(system_prompt, user_text, model=None, response_json=False):
        seen['models'].append(model)
        if response_json:
            import json as _j
            return {'text': _j.dumps(RU_GLOSSARY), 'input_tokens': 10, 'output_tokens': 10}
        return _ru_guidebook_prose(system_prompt, user_text, model, response_json)

    with patch.object(svc, '_wikidata_label', return_value=None):
        with patch.object(svc, '_openai_chat', side_effect=_chat):
            glossary = svc._build_names_glossary(301, TOUR301_CONTENT, 'ru')
            svc._translate_stop_guidebook(TOUR301_STOP1, 1, 'ru', glossary)
    assert 'gpt-4o' in seen['models'], 'names pass must call gpt-4o'
    assert 'gpt-4o-mini' in seen['models'], 'prose pass must call gpt-4o-mini'


def test_restore_collapses_model_inserted_newlines_preserving_line_count():
    """[LOCAL-561 live fix] A prose segment maps to exactly ONE source line. If the model
    wraps a long value onto several lines (observed live: Orientation value inflated the
    stop from 15 to 20 lines), restore must collapse those newlines so the line count and
    the mobile app's positional parsing are preserved."""
    svc, ts = _make_service()
    template, segments = svc._strip_structure_for_model(TOUR301_STOP1, 'ru')
    # Simulate a model that returns each segment wrapped across 3 lines.
    multiline = ['line-a\nline-b\nline-c' for _ in segments]
    restored = svc._restore_structure(template, multiline)
    assert restored.count('\n') == TOUR301_STOP1.count('\n'), \
        'model-inserted newlines must not change the stop line count'
    # The collapsed value is on the label's own line (not pushed down).
    assert '\u041a\u0430\u043a \u0441\u043e\u0440\u0438\u0435\u043d\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c\u0441\u044f: line-a line-b line-c' in restored


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
