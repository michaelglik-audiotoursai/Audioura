#!/usr/bin/env python3
"""
LOCAL-559: Translate with a small LLM instead of AWS Translate (behind a flag).

Unit tests with a MOCKED OpenAI client. No network, no AWS, no DB.

Acceptance (by effect) proven here:
  1. Line count is preserved by the llm engine.
  2. Nav lines (Address:/Coordinates:/Type-Specialty:/Specific Examples:/
     Operational Details:) pass through unchanged.
  3. Fallback to AWS fires on LLM error, empty output, and bad length ratio,
     and emits a '[TRANSLATE-LLM] FALLBACK <reason>' log line.
  4. A 12,000-char input is translated in full — nothing is truncated
     (red on the old code, which sent Text=text[:5000]).
  5. Default engine is 'aws' (nothing deployed changes until the flag is set).
  6. The in-process memo returns a cached result without a second LLM call.
  7. Cost is metered: '[TRANSLATE-LLM] tokens_in=.. tokens_out=.. cost=$..'.
  8. Voice-command phrases survive the llm engine.

Run:  pytest -q tests/test_local559_llm_translation.py
"""
import os
import sys
import logging
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'translation-service'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _install_stub_modules():
    """Stub heavy third-party deps so translation_service imports in a bare env.

    This is a UNIT test: AWS, BeautifulSoup and Flask are not exercised. We only
    need the module to import so TranslationService.translate_text can be tested
    with a mocked OpenAI client. 'requests' and 'cost_rates' are real.
    """
    if 'boto3' not in sys.modules:
        boto3_stub = MagicMock()
        sys.modules['boto3'] = boto3_stub
    if 'bs4' not in sys.modules:
        bs4_stub = MagicMock()
        # BeautifulSoup and NavigableString are imported by name.
        bs4_stub.BeautifulSoup = MagicMock()
        bs4_stub.NavigableString = MagicMock()
        sys.modules['bs4'] = bs4_stub


_install_stub_modules()


def _make_service(engine='aws', api_key='test-key'):
    """Construct a TranslationService with boto3 patched out (no AWS at init)."""
    env = {'TRANSLATION_ENGINE': engine, 'OPENAI_API_KEY': api_key}
    with patch.dict(os.environ, env, clear=False):
        with patch('boto3.client', return_value=MagicMock()):
            import importlib
            import translation_service as ts
            importlib.reload(ts)
            svc = ts.TranslationService()
    return svc, ts


# ─────────────────────────────────────────────────────────────────────────────
# 5. Default engine is 'aws'
# ─────────────────────────────────────────────────────────────────────────────
def test_default_engine_is_aws():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop('TRANSLATION_ENGINE', None)
        with patch('boto3.client', return_value=MagicMock()):
            import importlib
            import translation_service as ts
            importlib.reload(ts)
            svc = ts.TranslationService()
    assert svc.translation_engine == 'aws'


def test_aws_engine_does_not_call_openai():
    svc, ts = _make_service(engine='aws')
    svc.translate_client.translate_text.return_value = {'TranslatedText': 'HOLA'}
    with patch.object(svc, '_openai_chat', side_effect=AssertionError('must not call LLM')):
        out = svc.translate_text('Hello', 'es')
    assert out == 'HOLA'


# ─────────────────────────────────────────────────────────────────────────────
# 1 & 2. Line count preserved; nav lines unchanged
# ─────────────────────────────────────────────────────────────────────────────
NAV_STOP = (
    "The Old Lighthouse\n"
    "\n"
    "Address: 12 Harbour Road\n"
    "Coordinates: 43.1234, -5.6789\n"
    "Type/Specialty: Historic landmark\n"
    "\n"
    "This lighthouse has guided ships for two centuries.\n"
    "Specific Examples: the great storm of 1897\n"
    "Operational Details: open 9am-5pm"
)


def _fake_llm_line_preserving(system_prompt, user_text):
    """A faithful mock: translate each non-nav line to 'TR<i>', keep nav lines verbatim,
    and KEEP THE SAME NUMBER OF LINES. Models a well-behaved gpt-4o-mini."""
    nav_prefixes = ('Address:', 'Coordinates:', 'Type/Specialty:',
                    'Specific Examples:', 'Operational Details:')
    out_lines = []
    for i, line in enumerate(user_text.split('\n')):
        s = line.strip()
        if s == '':
            out_lines.append('')
        elif s.startswith(nav_prefixes):
            out_lines.append(line)  # unchanged
        else:
            out_lines.append(f'TR{i}')
    return {'text': '\n'.join(out_lines), 'input_tokens': 100, 'output_tokens': 90}


def test_llm_preserves_line_count_and_nav_lines():
    svc, ts = _make_service(engine='llm')
    with patch.object(svc, '_openai_chat', side_effect=_fake_llm_line_preserving):
        out = svc.translate_text(NAV_STOP, 'ru')
    assert out.count('\n') == NAV_STOP.count('\n'), 'line count must be preserved'
    for nav in ('Address: 12 Harbour Road',
                'Coordinates: 43.1234, -5.6789',
                'Type/Specialty: Historic landmark',
                'Specific Examples: the great storm of 1897',
                'Operational Details: open 9am-5pm'):
        assert nav in out, f'nav line changed/dropped: {nav}'


# ─────────────────────────────────────────────────────────────────────────────
# 3. Fallback fires on error / empty / bad ratio, with the log line
# ─────────────────────────────────────────────────────────────────────────────
def test_fallback_on_llm_error(caplog):
    svc, ts = _make_service(engine='llm')
    svc.translate_client.translate_text.return_value = {'TranslatedText': 'AWS_RESULT'}
    with caplog.at_level(logging.WARNING):
        with patch.object(svc, '_openai_chat', side_effect=RuntimeError('boom')):
            out = svc.translate_text('Hello world', 'es')
    assert out == 'AWS_RESULT'
    assert any('[TRANSLATE-LLM] FALLBACK' in r.message for r in caplog.records)


def test_fallback_on_empty_output(caplog):
    svc, ts = _make_service(engine='llm')
    svc.translate_client.translate_text.return_value = {'TranslatedText': 'AWS_RESULT'}
    with caplog.at_level(logging.WARNING):
        with patch.object(svc, '_openai_chat',
                          return_value={'text': '   ', 'input_tokens': 1, 'output_tokens': 0}):
            out = svc.translate_text('Hello world', 'es')
    assert out == 'AWS_RESULT'
    assert any('FALLBACK empty' in r.message for r in caplog.records)


def test_fallback_on_bad_ratio(caplog):
    svc, ts = _make_service(engine='llm')
    svc.translate_client.translate_text.return_value = {'TranslatedText': 'AWS_RESULT'}
    long_out = 'x' * 500  # single line, ~100x too long → ratio > 2.5
    with caplog.at_level(logging.WARNING):
        with patch.object(svc, '_openai_chat',
                          return_value={'text': long_out, 'input_tokens': 5, 'output_tokens': 5}):
            out = svc.translate_text('short', 'es')
    assert out == 'AWS_RESULT'
    assert any('FALLBACK ratio' in r.message for r in caplog.records)


def test_fallback_on_line_count_mismatch(caplog):
    svc, ts = _make_service(engine='llm')
    svc.translate_client.translate_text.return_value = {'TranslatedText': 'AWS_RESULT'}
    with caplog.at_level(logging.WARNING):
        with patch.object(svc, '_openai_chat',
                          return_value={'text': 'onlyoneline', 'input_tokens': 5, 'output_tokens': 5}):
            out = svc.translate_text('line one\nline two', 'es')
    assert out == 'AWS_RESULT'
    assert any('FALLBACK line_count' in r.message for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# 4. 12,000-char input is translated in full (no truncation)
# ─────────────────────────────────────────────────────────────────────────────
def test_12000_char_input_not_truncated():
    svc, ts = _make_service(engine='llm')
    paras = [('Sentence number %d. ' % i) * 10 for i in range(60)]
    big_text = '\n\n'.join(p.strip() for p in paras)
    if len(big_text) < 12000:
        big_text = big_text + '\n\n' + ('z' * (12000 - len(big_text)))
    assert len(big_text) >= 12000

    seen_chunks = []

    def _echo_chunk(system_prompt, user_text):
        seen_chunks.append(user_text)
        lines = ['[T]' + ln for ln in user_text.split('\n')]
        return {'text': '\n'.join(lines),
                'input_tokens': len(user_text) // 4,
                'output_tokens': len(user_text) // 4}

    with patch.object(svc, '_openai_chat', side_effect=_echo_chunk):
        out = svc.translate_text(big_text, 'es')

    assert len(seen_chunks) > 1, 'a 12k input must be split into multiple chunks'
    total_in = sum(len(c) for c in seen_chunks)
    assert total_in >= len(big_text) - 10, 'input characters were lost (truncation!)'
    assert len(out) > 5000, 'output far exceeds the old 5,000-char cap'


def test_aws_engine_also_untruncated_over_5000():
    """The AWS path must no longer send Text=text[:5000]."""
    svc, ts = _make_service(engine='aws')
    calls = []

    def _aws(Text, SourceLanguageCode, TargetLanguageCode):
        calls.append(Text)
        return {'TranslatedText': 'T:' + Text[:3]}

    svc.translate_client.translate_text.side_effect = _aws
    big = '\n\n'.join('para %d body text here' % i for i in range(400))  # > 4500 chars
    assert len(big) > 4500
    svc.translate_text(big, 'es')
    total_sent = sum(len(c) for c in calls)
    assert total_sent >= len(big) - 10


# ─────────────────────────────────────────────────────────────────────────────
# 6. Memoisation
# ─────────────────────────────────────────────────────────────────────────────
def test_memo_avoids_second_llm_call():
    svc, ts = _make_service(engine='llm')
    mock = MagicMock(return_value={'text': 'HOLA', 'input_tokens': 10, 'output_tokens': 5})
    with patch.object(svc, '_openai_chat', mock):
        a = svc.translate_text('Hello', 'es')
        b = svc.translate_text('Hello', 'es')
    assert a == b == 'HOLA'
    assert mock.call_count == 1, 'second identical call must hit the memo'


# ─────────────────────────────────────────────────────────────────────────────
# 7. Cost metering
# ─────────────────────────────────────────────────────────────────────────────
def test_cost_metered_and_logged(caplog):
    svc, ts = _make_service(engine='llm')
    with caplog.at_level(logging.INFO):
        with patch.object(svc, '_openai_chat',
                          return_value={'text': 'HOLA', 'input_tokens': 1000, 'output_tokens': 500}):
            svc.translate_text('Hello', 'es')
    assert svc._llm_cost_total > 0.0
    assert any('tokens_in=1000' in r.message and 'tokens_out=500' in r.message
               and 'cost=$' in r.message for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Voice-command preservation under the llm engine
# ─────────────────────────────────────────────────────────────────────────────
def test_voice_commands_preserved_under_llm():
    svc, ts = _make_service(engine='llm')

    def _keep_play(system_prompt, user_text):
        assert 'Play' in system_prompt  # prompt instructs keeping voice commands
        return {'text': user_text.replace('Say', 'Diga'),
                'input_tokens': 20, 'output_tokens': 20}

    with patch.object(svc, '_openai_chat', side_effect=_keep_play):
        out = svc.translate_text('Say Play to begin', 'es', preserve_voice_commands=True)
    assert 'Play' in out


# ═════════════════════════════════════════════════════════════════════════════
# LOCAL-559R. Bounce fix: the llm engine left SPOKEN 'Orientation:' and
# 'Directions:' lines in English (a Russian listener heard English directions).
#
# This fixture is a REAL stop of tour 301 — Stop 2, Palais Lascaris — copied
# byte-for-byte from the live audio_tours.tour_content row (the same stop LEAD
# quoted: "373 (ru, llm): Directions: From Palais Lascaris, head south ..."). It
# carries the five nav lines AND the two spoken label lines Orientation:/Directions:.
#
# RED on e406c8f: the old code had no untranslated-line check and no retry, so a
# model that leaves 'Directions:' / 'Orientation:' verbatim (exactly what the old
# prompt induced) is returned unchanged — the Directions line stays English.
# GREEN after the fix: the deterministic check flags those lines, one retry is
# issued, and the retried (translated) output is returned.
# ═════════════════════════════════════════════════════════════════════════════

# Byte-exact Stop 2 body of tour 301 (verified against the live DB on 2026-10-02).
TOUR301_STOP2 = (
    "Palais Lascaris\n"
    "\n"
    "Address: 06300 \n"
    "\n"
    "Coordinates: 43.6963, 7.2767\n"
    "\n"
    "Type/Specialty: Historic palace\n"
    "\n"
    "Specific Examples: Baroque architecture, musical instrument collection, ornate decorations\n"
    "\n"
    "Orientation: As you arrive at the Palais Lascaris in the heart of Old Town, look for the grand facade of this seventeenth-century aristocratic building. Once the residence of the influential Vintimille-Lascaris family, it now stands as a museum housing over 500 musical instruments, a treasure trove of sound and history waiting to be discovered.\n"
    "\n"
    "Built in the early seventeenth century and later modified in the eighteenth century, the Palais Lascaris was a symbol of power and prestige for the Vintimille-Lascaris family until the early 19th century. In 1942, the city of Nice acquired the palace to transform it into a museum, a decision that would preserve its rich heritage and offer visitors a glimpse into its opulent past. Step inside the palace, and you are immediately enveloped in a sensory journey through time. The creaking of the wooden floors beneath your feet echoes the footsteps of the aristocrats who once roamed these halls. The faint scent of aged wood and history lingers in the air, inviting you to explore further. The lavish Baroque interiors of the Palais Lascaris hide stories of a once-powerful Savoy family whose influence shaped the destiny of the region. As you wander through the rooms adorned with intricate tapestries and ornate furnishings, imagine the grandeur and elegance that once filled these spaces. This stop on our walking tour of Nice connects to our theme by showcasing the intersection of art, history, and culture. The Palais Lascaris serves as a window into the past, offering a glimpse of a bygone era when music and luxury intertwined to create a world of beauty and refinement. Just beyond this rich historical site, the echoes of an operatic past await, hinting at the grandeur and drama that once graced this vibrant city.\n"
    "\n"
    "Directions: From Palais Lascaris, head south on Rue Droite until you reach Place Rossetti with its bustling cafes. Continue straight on Rue de la Pr\u00e9fecture until you arrive at Op\u00e9ra de Nice, a grand building with a beautiful fa\u00e7ade. Enjoy the walk through the charming streets of Old Town Nice!"
)

# The five nav-line prefixes that are the ONLY lines allowed to stay in English.
_NAV_PREFIXES = ('Address:', 'Coordinates:', 'Type/Specialty:',
                 'Specific Examples:', 'Operational Details:')


def _ru_translate_line(line):
    """Fake-but-faithful per-line RU translation: prefix a Cyrillic marker to the
    non-label text so the line is byte-DIFFERENT from English (i.e. 'translated'),
    while preserving line structure and a sane length ratio. Label words on
    Orientation:/Directions: are themselves translated (label + value)."""
    s = line.strip()
    if s == '':
        return ''
    if s.startswith('Orientation:'):
        return 'Ориентация: \u041f\u0435\u0440\u0435\u0432\u043e\u0434 ' + s[len('Orientation:'):].strip()
    if s.startswith('Directions:'):
        return 'Как добраться: \u041f\u0435\u0440\u0435\u0432\u043e\u0434 ' + s[len('Directions:'):].strip()
    return '\u041f\u0435\u0440\u0435\u0432\u043e\u0434 ' + s  # "Перевод " (translation) + text


def _nav_passthrough(line):
    """Nav lines: keep label English; translate value except Address/Coordinates."""
    s = line.strip()
    for p in _NAV_PREFIXES:
        if s.startswith(p):
            if p in ('Address:', 'Coordinates:'):
                return line  # value unchanged
            label, _, val = s.partition(':')
            return f"{label}: \u041f\u0435\u0440\u0435\u0432\u043e\u0434 {val.strip()}"
    return None


class _Tour301Mock:
    """Models the live gpt-4o-mini defect, then a correct retry.

    Call 1 (buggy): translate narrative, keep the five nav lines English, but ALSO
    leave the 'Orientation:' and 'Directions:' lines verbatim English — exactly the
    over-generalisation the old prompt caused.
    Call 2 (retry): translate everything correctly (Orientation/Directions included).
    Line count is always preserved; ratio stays well within bounds.
    """
    def __init__(self):
        self.calls = 0

    def __call__(self, system_prompt, user_text):
        self.calls += 1
        buggy = self.calls == 1
        out = []
        for line in user_text.split('\n'):
            s = line.strip()
            nav = _nav_passthrough(line)
            if nav is not None:
                out.append(nav)
            elif buggy and (s.startswith('Orientation:') or s.startswith('Directions:')):
                out.append(line)  # BUG: left in English
            else:
                out.append(_ru_translate_line(line))
        return {'text': '\n'.join(out), 'input_tokens': 400, 'output_tokens': 420}


def _directions_line(text):
    for ln in text.split('\n'):
        if ln.strip().startswith('Directions:') or ln.strip().startswith('Как добраться:'):
            return ln
    return None


def test_local559r_directions_line_is_translated_tour301_stop2(caplog):
    """RED on e406c8f, GREEN after the fix: the spoken Directions line must not
    survive in English. Mirrors `grep -cE '^Directions: [A-Za-z]' == 0` on live rows."""
    svc, ts = _make_service(engine='llm')
    mock = _Tour301Mock()
    with caplog.at_level(logging.WARNING):
        with patch.object(svc, '_openai_chat', side_effect=mock):
            out = svc.translate_text(TOUR301_STOP2, 'ru')

    # Line count preserved (acceptance for the llm engine).
    assert out.count('\n') == TOUR301_STOP2.count('\n')

    # The Directions line must be translated — NOT the English source line.
    dline = _directions_line(out)
    assert dline is not None, 'Directions line vanished'
    assert not dline.startswith('Directions: From Palais Lascaris'), \
        'Directions line left in English (the LOCAL-559R defect)'
    # And it carries Cyrillic (actually translated).
    assert any('\u0400' <= ch <= '\u04FF' for ch in dline), 'Directions line not in Russian'

    # The spoken Orientation line is likewise translated.
    assert 'Orientation: As you arrive' not in out

    # The five nav lines are preserved per spec: Address/Coordinates values byte-exact.
    assert 'Coordinates: 43.6963, 7.2767' in out
    assert 'Address: 06300' in out

    # The deterministic check fired and a single retry resolved it (no AWS fallback).
    assert mock.calls == 2, 'expected exactly one LLM retry'
    assert any('[TRANSLATE-LLM] RETRY untranslated_lines=' in r.message for r in caplog.records)
    assert not any('[TRANSLATE-LLM] FALLBACK' in r.message for r in caplog.records)


def test_local559r_fallback_when_retry_still_untranslated(caplog):
    """If the retry ALSO leaves spoken lines in English, fall back to AWS and log
    '[TRANSLATE-LLM] FALLBACK untranslated_lines=N'."""
    svc, ts = _make_service(engine='llm')
    svc.translate_client.translate_text.return_value = {'TranslatedText': 'AWS_RESULT'}

    def _always_buggy(system_prompt, user_text):
        # Keep Orientation/Directions English on EVERY call; translate the rest.
        out = []
        for line in user_text.split('\n'):
            s = line.strip()
            nav = _nav_passthrough(line)
            if nav is not None:
                out.append(nav)
            elif s.startswith('Orientation:') or s.startswith('Directions:'):
                out.append(line)
            else:
                out.append(_ru_translate_line(line))
        return {'text': '\n'.join(out), 'input_tokens': 400, 'output_tokens': 420}

    attempts = {'n': 0}
    def _counting(system_prompt, user_text):
        attempts['n'] += 1
        return _always_buggy(system_prompt, user_text)

    with caplog.at_level(logging.WARNING):
        with patch.object(svc, '_openai_chat', side_effect=_counting):
            out = svc.translate_text(TOUR301_STOP2, 'ru')

    assert out == 'AWS_RESULT'
    assert attempts['n'] == 2, 'must try once, retry once, then fall back'
    assert any('[TRANSLATE-LLM] FALLBACK untranslated_lines=' in r.message
               for r in caplog.records)


def test_local559r_untranslated_counter_ignores_names_and_nav():
    """The deterministic counter must NOT flag the five nav lines nor short/proper-noun
    lines that are legitimately identical across languages."""
    svc, ts = _make_service(engine='llm')
    source = (
        "Palais Lascaris\n"              # proper noun, 2 words → not flagged
        "Address: 06300 \n"               # nav line → not flagged
        "Coordinates: 43.6963, 7.2767\n"  # nav line → not flagged
        "This is a long English prose sentence that was left untranslated entirely."
    )
    # Identical output on the one prose line only.
    n = svc._count_untranslated_lines(source, source)
    assert n == 1, f'exactly the prose line should be flagged, got {n}'


def test_local559r_english_spoken_label_with_translated_value_is_flagged():
    """A spoken label line whose VALUE is translated but whose LABEL stays English
    (e.g. 'Directions: Dirígete hacia el sur ...' in Spanish) must be flagged — the
    app speaks the label aloud. This is the es-row defect from the live run."""
    svc, ts = _make_service(engine='llm')
    source = (
        "Orientation: Head north and look for the tower.\n"
        "\n"
        "Directions: From here, walk south until you reach the square."
    )
    # Value translated to Spanish, label left English on both spoken lines.
    out = (
        "Orientation: Dirígete al norte y busca la torre.\n"
        "\n"
        "Directions: Desde aquí, camina hacia el sur hasta llegar a la plaza."
    )
    n = svc._count_untranslated_lines(source, out)
    assert n == 2, f'both spoken labels left in English should be flagged, got {n}'

    # Fully translated labels (Spanish) must NOT be flagged.
    out_ok = (
        "Orientación: Dirígete al norte y busca la torre.\n"
        "\n"
        "Cómo llegar: Desde aquí, camina hacia el sur hasta llegar a la plaza."
    )
    assert svc._count_untranslated_lines(source, out_ok) == 0


def test_local559r_label_normalized_without_fallback(caplog):
    """When the model translates the VALUE but keeps the English spoken label, the
    label is repaired DETERMINISTICALLY (via a cheap AWS label lookup) with NO retry
    and NO full-text AWS fallback — this is the wall-time fix for the live run."""
    svc, ts = _make_service(engine='llm')

    # AWS label lookups: 'Directions' -> 'Cómo llegar', 'Orientation' -> 'Orientación'.
    def _aws_label(Text, SourceLanguageCode, TargetLanguageCode):
        mapping = {'Directions': 'Cómo llegar', 'Orientation': 'Orientación'}
        return {'TranslatedText': mapping.get(Text, Text)}
    svc.translate_client.translate_text.side_effect = _aws_label

    source = (
        "Orientation: Head north and look for the tower.\n"
        "\n"
        "Directions: From here, walk south until you reach the square."
    )
    # Model translated the VALUE to Spanish but kept the English labels.
    llm_out = (
        "Orientation: Dirígete al norte y busca la torre.\n"
        "\n"
        "Directions: Desde aquí, camina hacia el sur hasta llegar a la plaza."
    )
    calls = {'n': 0}
    def _one_shot(system_prompt, user_text):
        calls['n'] += 1
        return {'text': llm_out, 'input_tokens': 50, 'output_tokens': 55}

    with caplog.at_level(logging.WARNING):
        with patch.object(svc, '_openai_chat', side_effect=_one_shot):
            out = svc.translate_text(source, 'es')

    # Exactly one LLM call — no retry, no fallback.
    assert calls['n'] == 1
    assert not any('[TRANSLATE-LLM] RETRY' in r.message for r in caplog.records)
    assert not any('[TRANSLATE-LLM] FALLBACK' in r.message for r in caplog.records)
    # Labels repaired, values preserved.
    assert 'Cómo llegar: Desde aquí' in out
    assert 'Orientación: Dirígete al norte' in out
    assert '\nDirections:' not in out and not out.startswith('Directions:')
    assert 'Orientation:' not in out


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
