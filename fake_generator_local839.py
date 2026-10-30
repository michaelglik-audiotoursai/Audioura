#!/usr/bin/env python3
"""fake_generator_local839.py — a zero-cost stand-in for the tour-generator,
used ONLY by the LOCAL-839 end-to-end orchestrator proof.

It speaks the exact slice of the generator's HTTP contract the orchestrator
consumes (tour_orchestrator_service.orchestrate_tour_async):

  POST /generate  {location, tour_type, total_stops, ...}
      -> {"job_id": "<uuid>"}
  GET  /status/<job_id>
      -> {"status":"completed", "output_file": "...",
          "coordinates":[lat,lng], "tour_content":"<3-stop walking tour>",
          "tour_kind":"full"}
  GET  /health -> {"status":"healthy"}

It returns a fixed 3-stop walking tour immediately and makes NO paid API calls,
so the end-to-end proof exercises the REAL orchestrator → REAL two modernized
instances (voice/ZIP, kokoro TTS) → REAL store path at ~$0, without the paid
tour-generator. The multi-instance behaviour under test lives entirely in the
modernized service and the orchestrator's handoff, which are the real code here.
"""
import os
import uuid
from flask import Flask, request, jsonify

app = Flask(__name__)

_JOBS = {}

TOUR_TEXT = """Step-by-Step Audio Guided Tour: Salem Common Public Art Walk - Walking Tour
Tour-Category: walking

Stop 1: Salem Common Bandstand
Orientation: Begin at the historic bandstand at the center of Salem Common.
This 1920s structure has hosted concerts and civic gatherings for a century.

Stop 2: Roger Conant Statue
Orientation: Walk to the northwest corner to the bronze figure of Salem's founder.
The brooding statue is one of the city's most photographed landmarks.

Stop 3: Salem Witch Museum Facade
Orientation: Cross Washington Square to the Romanesque former church.
Its red sandstone arches frame the north edge of the Common.
"""


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "fake-generator-local839"})


@app.route('/generate', methods=['POST'])
def generate():
    job_id = str(uuid.uuid4())
    _JOBS[job_id] = request.get_json(silent=True) or {}
    return jsonify({"job_id": job_id})


@app.route('/status/<job_id>', methods=['GET'])
def status(job_id):
    if job_id not in _JOBS:
        return jsonify({"error": "Job not found"}), 404
    # Completed immediately with canned content + real coordinates (Salem Common).
    return jsonify({
        "status": "completed",
        "output_file": "fake_local839_tour.txt",
        "coordinates": [42.5223, -70.8938],
        "tour_content": TOUR_TEXT,
        "tour_kind": "full",
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')), debug=False)
