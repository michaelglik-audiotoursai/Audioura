#!/usr/bin/env python3
"""GCS-5E Polly stand-in that REQUIRES a Google identity token AND records voice.

Mirrors the real private polly-tts: POST /synthesize returns 403 unless an
`Authorization: Bearer <token>` header is present (any non-empty token is
accepted — the point is to prove tour-editing actually attaches one). Every
accepted request's voice_id is appended to POLLY_VOICE_LOG so the harness can
prove the Russian tour synthesised with Tatyana, not Joanna.

Returns ID3-prefixed bytes so downstream mp3 sniffing sees 'mp3'.
Windows-safe: utf-8 on every write.
"""
import os
import json
from flask import Flask, request, Response

app = Flask(__name__)
VOICE_LOG = os.getenv('POLLY_VOICE_LOG', 'polly_voice_log.jsonl')
UNAUTH_LOG = os.getenv('POLLY_UNAUTH_LOG', 'polly_unauth_log.jsonl')


def _has_bearer():
    auth = request.headers.get('Authorization', '')
    return auth.startswith('Bearer ') and len(auth) > len('Bearer ')


@app.route('/synthesize', methods=['POST'])
def synthesize():
    if not _has_bearer():
        # Record the unauthenticated hit so a regression (no token) is visible.
        with open(UNAUTH_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'path': '/synthesize', 'authorized': False}) + '\n')
        return Response('{"error":"missing identity token"}', status=403,
                        mimetype='application/json')
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
    # Health is unauthenticated so the harness can wait on readiness.
    return {'status': 'ok'}


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.getenv('PORT', '5598')), debug=False)
