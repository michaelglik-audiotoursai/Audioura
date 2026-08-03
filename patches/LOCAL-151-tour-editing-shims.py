#!/usr/bin/env python3
"""LOCAL-151: Patch tour_editing_phase2.py to add update-stop and job-status shims.

Usage:
    # Extract current file from container:
    docker cp tour-editing-phase2-1:/app/tour_editing_phase2.py /tmp/phase2_current.py
    
    # Apply patch:
    python3 patches/LOCAL-151-tour-editing-shims.py /tmp/phase2_current.py /tmp/phase2_patched.py
    
    # Deploy:
    docker cp /tmp/phase2_patched.py tour-editing-phase2-1:/app/tour_editing_phase2.py
    docker restart tour-editing-phase2-1

Why: The app (tour_editing_service.dart) calls six routes on port 5022.
Four exist in tour_editing_phase2.py. Two are missing:
  - POST /tour/<id>/update-stop   (single-stop edit from edit_stop_screen.dart)
  - GET  /tour/<id>/job-status/<job_id>  (async polling — never implemented server-side)

This script adds both as shims:
  - update-stop delegates to bulk-save via test_client
  - job-status always returns "completed" (all ops are synchronous)
"""
import sys

SHIM_ROUTES = '''

@app.route('/tour/<tour_id>/update-stop', methods=['POST'])
def update_single_stop(tour_id):
    """Shim: single-stop update delegated to bulk-save via internal request.

    The app's edit_stop_screen calls this for individual stop text edits.
    Translates the single-stop format into bulk-save format.
    Returns synchronously (no job_id), so the app skips job polling.
    """
    data = request.json or {}
    stop_number = data.get('stop_number')
    new_text = data.get('new_text')

    if not stop_number or not new_text:
        return jsonify({
            "status": "error",
            "message": "stop_number and new_text are required",
            "error_code": "VALIDATION_FAILED",
            "recoverable": True,
            "suggested_action": "Please provide stop_number and new_text fields"
        }), 400

    # Delegate to bulk-save using internal test client
    import json as _json
    bulk_payload = _json.dumps({
        "stops": [{
            "stop_number": stop_number,
            "text": new_text,
            "original_text": "",
            "action": "modify",
            "generate_audio_from_text": True,
            "has_custom_audio": False,
            "audio_source": "tts_generated"
        }]
    })

    with app.test_client() as client:
        resp = client.post(
            f"/tour/{tour_id}/bulk-save",
            data=bulk_payload,
            content_type="application/json"
        )

    # Return the bulk-save response directly
    return app.response_class(
        response=resp.data,
        status=resp.status_code,
        mimetype="application/json"
    )


@app.route('/tour/<tour_id>/job-status/<job_id>', methods=['GET'])
def get_job_status(tour_id, job_id):
    """Shim: job status endpoint.

    Phase2 bulk-save is synchronous - no background jobs exist.
    The app only reaches this if update-stop returns a job_id (it does not).
    Registered so the route returns structured JSON instead of generic 404.
    Always returns 'completed' since all operations finish synchronously.
    """
    return jsonify({
        "status": "completed",
        "tour_id": tour_id,
        "job_id": job_id,
        "message": "Operation completed synchronously"
    })

'''


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.py> <output.py>")
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]

    with open(input_path, 'r') as f:
        content = f.read()

    # Insert before the /health route
    target = "\n\n@app.route('/health', methods=['GET'])"
    if target not in content:
        target = "\n@app.route('/health', methods=['GET'])"

    if target not in content:
        print("ERROR: Could not find @app.route('/health') insertion point")
        sys.exit(1)

    if "update-stop" in content:
        print("WARNING: update-stop already present — skipping patch")
        with open(output_path, 'w') as f:
            f.write(content)
        return

    patched = content.replace(target, SHIM_ROUTES + target, 1)

    with open(output_path, 'w') as f:
        f.write(patched)

    print(f"Patched: {len(content.splitlines())} → {len(patched.splitlines())} lines")
    print(f"Added: /tour/<id>/update-stop, /tour/<id>/job-status/<job_id>")


if __name__ == '__main__':
    main()
