#!/usr/bin/env python3
"""Minimal Polly TTS stand-in for GCS-5 local verification.

Returns deterministic MP3-like bytes for /synthesize so the editing service's
generate_audio_for_stop() path succeeds without real AWS Polly. The bytes start
with an ID3 header so any downstream format sniffing sees 'mp3'.
"""
import os
from flask import Flask, request, Response

app = Flask(__name__)


@app.route('/synthesize', methods=['POST'])
def synthesize():
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').encode('utf-8', 'replace')
    # ID3 header + a marker + a slice of the text so different text -> different bytes
    body = b'ID3\x03\x00\x00\x00\x00\x00\x00' + b'STUBMP3:' + text[:64]
    return Response(body, mimetype='audio/mpeg')


@app.route('/health')
def health():
    return {'status': 'ok'}


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.getenv('PORT', '5599')), debug=False)
