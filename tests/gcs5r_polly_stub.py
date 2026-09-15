#!/usr/bin/env python3
"""Polly TTS stand-in for GCS-5R verification that RECORDS the requested voice.

The editing service calls POST /synthesize with {text, voice_id, format}. For
B3 we must prove which Polly voice the service asked for: Russian text on a
Russian tour must synth with the Russian voice (Tatyana), not the English one
(Joanna). Every request's voice_id is appended to POLLY_VOICE_LOG (JSON lines).

Returns ID3-prefixed bytes so downstream format sniffing sees 'mp3'.
Windows-safe: utf-8 on every write.
"""
import os
import json
from flask import Flask, request, Response

app = Flask(__name__)
VOICE_LOG = os.getenv('POLLY_VOICE_LOG', 'polly_voice_log.jsonl')


@app.route('/synthesize', methods=['POST'])
def synthesize():
    data = request.get_json(silent=True) or {}
    voice_id = data.get('voice_id')
    text = (data.get('text') or '')
    with open(VOICE_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'voice_id': voice_id, 'text_prefix': text[:40]},
                           ensure_ascii=False) + '\n')
    body = b'ID3\x03\x00\x00\x00\x00\x00\x00' + b'STUBMP3:' + text[:64].encode('utf-8', 'replace')
    return Response(body, mimetype='audio/mpeg')


@app.route('/health')
def health():
    return {'status': 'ok'}


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.getenv('PORT', '5599')), debug=False)
