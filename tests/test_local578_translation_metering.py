#!/usr/bin/env python3
"""
LOCAL-578: Meter translations — translation LLM + its direct-boto3 Polly audio
write cost_ledger rows.

Why (D605): Russian translations left NO cost_ledger rows. The translation service
logged '[TRANSLATE-LLM] … cost=$…' per LLM call but never wrote the ledger, and its
audio went through its OWN boto3 Polly client (not polly-tts), also unmetered. So
per-tour price reports undercounted every translation.

Acceptance proven here (boto3 + the LLM fully stubbed, no network, no real DB):
  A 4-stop Russian translation writes EXACTLY:
    * 1 translation_generate row — our_cost_usd = summed LLM cost + summed TTS cost,
      breakdown carries {llm, models:{...}, tts, tts_engine, chars} + source tour id,
      target language and the job id the orchestrator gave.
    * 4 tts_generate rows — one per synthesized stop, each with
      breakdown={chars, engine, voice_id} and the Polly price from cost_rates.
  And the sums line up: sum(tts rows) == translation_generate.breakdown['tts'];
  translation_generate.our_cost_usd == llm (tts is charged by the tts_generate rows).

Also:
  * job_id/user_id are threaded through onto every row.
  * The /translate-with-audio endpoint reads job_id/user_id from the request body.

Run:  pytest -q tests/test_local578_translation_metering.py
"""
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# translation_service lives in translation-service/ (hyphen → not importable as a
# package); put that dir and the repo root (cost_rates/cost_meter) on the path.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'translation-service'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _install_stub_modules():
    """Stub heavy third-party deps so translation_service imports in a bare env.

    AWS (boto3) and BeautifulSoup are not exercised: boto3 is replaced wholesale and
    the Polly client is a MagicMock whose synthesize_speech returns canned audio bytes.
    'requests', 'cost_rates' and 'cost_meter' are the real modules.
    """
    if 'boto3' not in sys.modules:
        sys.modules['boto3'] = MagicMock()
    # Stub bs4 ONLY when it is genuinely not installed. Stubbing it when it is importable leaked a
    # MagicMock BeautifulSoup into every later test in the run (LEAD 2026-10-05: LOCAL-580's
    # site-first tests then parsed nothing and failed when run after this file).
    try:
        import bs4  # noqa: F401
    except ImportError:
        bs4_stub = MagicMock()
        bs4_stub.BeautifulSoup = MagicMock()
        bs4_stub.NavigableString = MagicMock()
        sys.modules['bs4'] = bs4_stub


_install_stub_modules()


# ── A fake DB cursor that scripts just the queries translate_tour_with_audio runs ──
class _FakeCursor:
    def __init__(self, tour_row):
        self._tour_row = tour_row
        self._last = None

    def execute(self, sql, params=None):
        s = ' '.join(sql.split())
        if s.startswith("SELECT id, tour_name"):
            self._last = ('tour_row',)
        elif "information_schema.columns" in s and "'track'" in s:
            self._last = ('track_check',)      # → fetchone() returns None (no track col)
        elif s.startswith("SELECT id FROM audio_tours WHERE original_tour_id"):
            self._last = ('existing_check',)    # → None (no existing translation)
        elif s.startswith("INSERT INTO audio_tours"):
            self._last = ('insert',)            # → RETURNING id
        else:
            self._last = ('other',)

    def fetchone(self):
        if self._last == ('tour_row',):
            return self._tour_row
        if self._last == ('insert',):
            return (999,)                       # new_tour_id
        return None                             # track check / existing check → None

    def close(self):
        pass


class _FakeConn:
    def __init__(self, tour_row):
        self._tour_row = tour_row

    def cursor(self):
        return _FakeCursor(self._tour_row)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _make_llm_service():
    """Construct a TranslationService on the LLM engine with boto3 patched out."""
    env = {'TRANSLATION_ENGINE': 'llm', 'TRANSLATION_GUIDEBOOK': 'off',
           'OPENAI_API_KEY': 'test-key'}
    with patch.dict(os.environ, env, clear=False):
        with patch('boto3.client', return_value=MagicMock()):
            import importlib
            import translation_service as ts
            importlib.reload(ts)
            svc = ts.TranslationService()
    return svc, ts


def _four_stop_tour_content():
    """A tour_content string with four stops, in the 'Stop N:' format the splitter
    expects. Each stop has a title + a prose line long enough to pass the LLM output
    sanity checks."""
    stops = ["Walking Tour of Test City"]
    for n in range(1, 5):
        stops.append(
            f"Stop {n}: Landmark Number {n}\n"
            f"This is the narration paragraph for landmark number {n} on the walking tour."
        )
    return "\n\n".join(stops)


def test_four_stop_russian_translation_writes_one_translation_and_four_tts_rows():
    svc, ts = _make_llm_service()

    # Deterministic LLM: return a non-identical "translation" that preserves the line
    # count (so the output passes the acceptance checks and is metered — an echo would be
    # byte-identical and trip the untranslated-lines check → AWS fallback). We prepend a
    # Cyrillic marker to each line so no prose line equals its source.
    def _fake_openai_chat(system_prompt, user_text, model=None, response_json=False):
        translated = '\n'.join('пер ' + ln if ln.strip() else ln
                               for ln in user_text.split('\n'))
        return {'text': translated, 'input_tokens': 100, 'output_tokens': 50}

    # Polly returns canned bytes; the real _meter_tts_cost runs on the result.
    svc.polly_client.synthesize_speech.return_value = {
        'AudioStream': MagicMock(read=lambda: b'FAKEMP3')
    }
    # Backstop: if any short string (tour name / request) trips the LLM sanity checks and
    # falls back to AWS Translate, return a plain string (not a MagicMock) so the join/strip
    # logic still works. The stops themselves are translated by the stubbed LLM above.
    svc.translate_client.translate_text.return_value = {'TranslatedText': 'перевод'}

    tour_content = _four_stop_tour_content()
    # audio_tours row layout the code reads (11 columns):
    # id, tour_name, request_string, audio_tour, number_requested, lat, lng,
    # tour_content, content_language, tour_blob_uri, stops_count
    tour_row = (
        388, 'Test Tour', 'test request', b'ZIPBYTES', 1,
        42.0, -71.0, tour_content, 'en', None, 4,
    )

    recorded = []

    def _recorder(**kwargs):
        recorded.append(kwargs)
        return 'row-' + kwargs['operation_type']

    with patch.object(svc, '_openai_chat', side_effect=_fake_openai_chat), \
         patch.object(svc, 'get_db_connection', return_value=_FakeConn(tour_row)), \
         patch.object(svc, '_create_mobile_compatible_zip', return_value=b'TRANSLATED_ZIP'), \
         patch.object(ts, '_record_operation', side_effect=_recorder):
        new_id, cache_hit = svc.translate_tour_with_audio(
            388, 'ru', job_id='job-local578', user_id='user-xyz'
        )

    assert new_id == 999
    assert cache_hit is False

    tts_rows = [r for r in recorded if r['operation_type'] == 'tts_generate']
    trans_rows = [r for r in recorded if r['operation_type'] == 'translation_generate']

    # Exactly 4 tts rows (one per synthesized stop) and exactly 1 translation row.
    assert len(tts_rows) == 4, f"expected 4 tts_generate rows, got {len(tts_rows)}"
    assert len(trans_rows) == 1, f"expected 1 translation_generate row, got {len(trans_rows)}"

    # ── tts_generate rows: shape + Polly price from cost_rates ──
    from cost_rates import tts_cost
    tts_sum = 0.0
    for r in tts_rows:
        assert r['job_id'] == 'job-local578'
        assert r['user_id'] == 'user-xyz'
        assert r['cache_hit'] is False
        b = r['breakdown']
        assert b['voice_id'] == 'Tatyana'       # Russian voice
        assert b['engine'] == 'standard'        # Tatyana is a standard voice
        assert b['chars'] > 0
        # Price must equal cost_rates.tts_cost(chars, standard)
        assert r['our_cost_usd'] == pytest.approx(tts_cost(b['chars'], engine='standard'))
        tts_sum += r['our_cost_usd']

    # ── translation_generate row: shape + sums ──
    tr = trans_rows[0]
    assert tr['job_id'] == 'job-local578'
    assert tr['user_id'] == 'user-xyz'
    assert tr['cache_hit'] is False
    tb = tr['breakdown']
    # Required breakdown keys from the ticket (D605).
    for key in ('llm', 'models', 'tts', 'tts_engine', 'chars'):
        assert key in tb, f"translation_generate breakdown missing {key!r}"
    assert tb['source_tour_id'] == 388
    assert tb['target_language'] == 'ru'
    assert tb['tts_engine'] == 'standard'

    # LLM cost summed by model: the non-guidebook llm engine uses gpt-4o-mini only.
    from cost_rates import llm_cost
    assert 'gpt-4o-mini' in tb['models']
    # 8 accepted stop calls? No — one translate_text per stop (4) + name + request = 6
    # accepted LLM calls, each 100 in / 50 out tokens. We don't hardcode the count; we
    # assert the by-model total equals llm and is a positive multiple of one call's cost.
    one_call = llm_cost(input_tokens=100, output_tokens=50, model='gpt-4o-mini')
    assert tb['models']['gpt-4o-mini'] == pytest.approx(tb['llm'])
    assert tb['llm'] > 0
    assert tb['llm'] == pytest.approx(round(tb['models']['gpt-4o-mini'], 6))
    # llm must be a whole number of identical calls (sanity on the accumulation).
    n_calls = round(tb['llm'] / one_call)
    assert n_calls >= 4
    assert tb['llm'] == pytest.approx(n_calls * one_call, rel=1e-6)

    # TTS totals: the row's tts equals the sum of the four tts_generate rows, and chars
    # equals the sum of their chars.
    assert tb['tts'] == pytest.approx(round(tts_sum, 6))
    assert tb['chars'] == sum(r['breakdown']['chars'] for r in tts_rows)

    # our_cost_usd on the translation row == llm ONLY: the tts_generate rows charge the audio,
    # so a per-job ledger sum counts every cent exactly once (LEAD review, no double billing).
    assert tr['our_cost_usd'] == pytest.approx(tb['llm'])
    assert tb.get('tts_metered_separately') is True
    job_total = tr['our_cost_usd'] + sum(r['our_cost_usd'] for r in tts_rows)
    assert job_total == pytest.approx(tb['llm'] + tts_sum)

    print(
        f"PASS: 1 translation_generate (llm=${tb['llm']:.6f} over {n_calls} calls, "
        f"tts=${tb['tts']:.6f} over {len(tts_rows)} stops, total=${tr['our_cost_usd']:.6f}) "
        f"+ {len(tts_rows)} tts_generate rows"
    )


def test_endpoint_reads_job_id_and_user_id_from_body():
    """The /translate-with-audio handler must read job_id and user_id from the request
    JSON and pass them into translate_tour_with_audio."""
    svc, ts = _make_llm_service()

    captured = {}

    def _fake_translate(content_id, lang, job_id=None, user_id=None):
        captured['content_id'] = content_id
        captured['lang'] = lang
        captured['job_id'] = job_id
        captured['user_id'] = user_id
        return 123, False

    ts.app.config['TESTING'] = True
    client = ts.app.test_client()
    with patch.object(ts.translation_service, 'translate_tour_with_audio',
                      side_effect=_fake_translate), \
         patch.object(ts.translation_service, 'get_db_connection',
                      return_value=_FakeConn(None)):
        resp = client.post('/translate-with-audio', json={
            'content_id': 388,
            'content_type': 'tour',
            'languages': ['ru'],
            'job_id': 'job-endpoint',
            'user_id': 'user-endpoint',
        })

    assert resp.status_code == 200
    assert captured['job_id'] == 'job-endpoint'
    assert captured['user_id'] == 'user-endpoint'
    assert captured['content_id'] == 388
    assert captured['lang'] == 'ru'
    print("PASS: endpoint threads job_id/user_id into translate_tour_with_audio")


if __name__ == '__main__':
    test_four_stop_russian_translation_writes_one_translation_and_four_tts_rows()
    test_endpoint_reads_job_id_and_user_id_from_body()
    print("ALL LOCAL-578 TESTS PASSED")
