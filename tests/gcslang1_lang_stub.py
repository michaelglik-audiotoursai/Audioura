#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GCS-LANG1 language-detection stand-in (deterministic, no AWS).

Reproduces the reported Comprehend behaviour without calling AWS, so the local
container verification is deterministic. Accepts Comprehend's request shape via
a tiny JSON contract used by the tour_editing_phase2 test seam
(LOCAL_LANGUAGE_STUB_URL): POST {"text": "..."} -> {"Languages":[{...}]}.

Verdict by script mix of the text it is GIVEN:
  * no Cyrillic                       -> 'en'   (Latin)
  * Cyrillic present, no Latin        -> 'ru'   (clean Cyrillic body)
  * Cyrillic + a substantial Latin    -> 'cv'   (Chuvash: the mixed-script wander
                                                 that the whole-blob call hits)

So the RAW stop blob (Latin header + Latin place name + English Orientation
diluting the Russian body) is judged 'cv' -> LANGUAGE_MISMATCH, while the
stripped narration is judged 'ru' -> accepted. An all-English narration is 'en'.

Windows-safe: utf-8 on every write.
"""
import os
import json
from flask import Flask, request, jsonify

app = Flask(__name__)
LOG = os.getenv('LANG_STUB_LOG', 'gcslang1_lang_stub.jsonl')


def _classify(text):
    t = text or ""
    cyr = sum(1 for ch in t if '\u0400' <= ch <= '\u04FF')
    lat = sum(1 for ch in t if 'a' <= ch.lower() <= 'z')
    if cyr == 0:
        return 'en'
    if lat == 0:
        return 'ru'
    ratio = lat / float(cyr + lat)
    # A meaningful Latin fraction drags detection to a neighbouring Cyrillic
    # language (the reported 'cv'); a stray Latin word or two does not.
    return 'cv' if ratio >= 0.25 else 'ru'


@app.route('/detect', methods=['POST'])
def detect():
    data = request.get_json(silent=True) or {}
    text = data.get('text') or ''
    code = _classify(text)
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'code': code, 'len': len(text),
                                'prefix': text[:40]}, ensure_ascii=False) + '\n')
    except Exception:
        pass
    return jsonify({'Languages': [{'LanguageCode': code, 'Score': 0.99}]})


@app.route('/health')
def health():
    return {'status': 'ok'}


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.getenv('PORT', '5599')), debug=False)
