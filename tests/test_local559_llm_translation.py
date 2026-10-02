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


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
