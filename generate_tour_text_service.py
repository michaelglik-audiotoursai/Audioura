"""
Modified version of generate_tour_text_service.py that includes geo coordinates
"""
import os
import sys
import json
import time
import uuid
import tempfile
from datetime import datetime
import flask
from flask import Flask, request, jsonify, send_file as _send_file
from flask_cors import CORS


def _compat_send_file(path_or_file, **kwargs):
    """Version-tolerant send_file wrapper.

    Flask <2.0 uses ``attachment_filename``; Flask >=2.0 renamed it to
    ``download_name``.  This helper accepts either and maps to whichever the
    installed Flask supports, so the same code runs on both.
    """
    import inspect
    sig = inspect.signature(_send_file)
    params = sig.parameters

    # Normalise: caller may pass either name
    download_name = kwargs.pop("download_name", None)
    attachment_filename = kwargs.pop("attachment_filename", None)
    name = download_name or attachment_filename

    if name:
        if "download_name" in params:
            kwargs["download_name"] = name
        else:
            kwargs["attachment_filename"] = name

    return _send_file(path_or_file, **kwargs)


# Override module-level name so all call sites use the compat wrapper
send_file = _compat_send_file
import threading
import re

# Import the tour text generator
from generate_tour_text import generate_tour_text
import api_call_logger
from job_store import get_job_store
from storied_version_constants import STORIED_SERVICE_VERSION

SERVICE_VERSION = STORIED_SERVICE_VERSION

app = Flask(__name__)
CORS(app)

# Register sharing blueprint (LOCAL-110: POST /tour/share + GET /tour/<id>)
from sharing_endpoints import sharing_bp
app.register_blueprint(sharing_bp)

# Global variables
TOURS_DIR = "/app/tours"
ACTIVE_JOBS = get_job_store('tour-generator')

# TODO(S94): remove in-code password fallback; prod must use DATABASE_URL/DB_PASSWORD env only
def _persist_icon_metrics(icon_result, job_id):
    """Persist I-CON results to stop_metrics table (non-blocking)."""
    import json as _json
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST", "postgres-2"),
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ.get("DB_NAME", "audiotours"),
            user=os.environ.get("DB_USER", "admin"),
            password=os.environ.get("DB_PASSWORD", "password123"),
        )
        cur = conn.cursor()
        
        for stop in icon_result.get("stops", []):
            # [PALAIS-FIX B1] Propagate verified flag to stop_metrics
            _verified = stop.get("verified", True)
            cur.execute(
                """INSERT INTO stop_metrics 
                   (job_id, stop_index, stop_title, i_con, class_details, class_historic, class_social, 
                    paragraphs, evaluator_version, prompt_hash, verified)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (job_id, stop["stop_index"], stop["stop_title"], stop["i_con"],
                 stop["class_dist"].get("details", 0), stop["class_dist"].get("historic", 0),
                 stop["class_dist"].get("social", 0),
                 _json.dumps(stop["paragraphs"]),
                 icon_result.get("evaluator_version", "1.0.0"),
                 icon_result.get("prompt_hash", ""),
                 _verified)
            )
        
        conn.commit()
        cur.close()
        conn.close()
        print(f"[I-CON] Persisted {len(icon_result.get('stops', []))} stop metrics for job {job_id}")
    except Exception as e:
        print(f"[I-CON] Persistence failed: {e}")


def ensure_tours_directory():
    """Ensure the tours directory exists."""
    if not os.path.exists(TOURS_DIR):
        os.makedirs(TOURS_DIR)

def generate_tour_async(job_id, location, tour_type, total_stops=10, user_id=None):
    """Generate tour text asynchronously."""
    try:
        api_call_logger.log("GENERATOR_SERVICE_ASYNC_START", {
            "job_id": job_id,
            "location": location,
            "tour_type": tour_type,
            "total_stops": total_stops,
            "user_id": user_id,
        })
        
        ACTIVE_JOBS.update(job_id, status="processing", progress="Starting tour text generation...")

        # [S46] Persona lookup — graceful degradation if unavailable
        _persona_value = None
        if user_id:
            try:
                from persona_preference_store import get_persona
                from onboarding_preference import UserPersona
                _db_url = os.getenv('DATABASE_URL', 'postgresql://admin:password123@postgres-2:5432/audiotours')
                _persona_result = get_persona(user_id, _db_url)
                if _persona_result is not None:
                    _persona_value = _persona_result.value
                    print(f"  [S46] Persona for user '{user_id}': {_persona_value}")
                else:
                    print(f"  [S46] No persona stored for user '{user_id}' — using default")
            except Exception as e:
                print(f"  [S46] Persona lookup failed (graceful degradation): {e}")
                _persona_value = None
        
        # Create a temporary file for the output
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as temp_file:
            temp_path = temp_file.name
        
        api_call_logger.log("CALLING_GENERATE_TOUR_TEXT_FUNCTION", {
            "function": "generate_tour_text",
            "location": location,
            "tour_type": tour_type,
            "total_stops": total_stops,
            "persona": _persona_value,
            "log_file": api_call_logger.get_log_path(),
        })
        
        # Generate the tour text - PASS total_stops, persona, and user_id parameters
        tour_text, _, coordinates = generate_tour_text(location, tour_type, temp_path, total_stops, persona=_persona_value, user_id=user_id)
        
        if tour_text is None:
            # Check for structured evidence from degradation ladder
            _error_msg = f"Tour generation failed for '{location}' — no stops could be generated (all filtered or knowledge insufficient)."
            _error_extra = {}
            try:
                from generate_tour_text import _LAST_CLEAN_FAIL_EVIDENCE
                if _LAST_CLEAN_FAIL_EVIDENCE:
                    _error_extra = {
                        "error_type": _LAST_CLEAN_FAIL_EVIDENCE.get("error_type", "generation_failed"),
                        "evidence_summary": _LAST_CLEAN_FAIL_EVIDENCE,
                    }
                    _error_msg = "This venue could not be verified with enough works to generate a quality tour."
                    import generate_tour_text as _gtt
                    _gtt._LAST_CLEAN_FAIL_EVIDENCE = {}  # Reset for next request
            except (ImportError, AttributeError):
                pass
            ACTIVE_JOBS.update(job_id, status="error", error=_error_msg, **_error_extra)
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return
        
        # [LOCAL-60] Record operation cost immediately after generation (before QA gate)
        # This ensures cache hits are always metered even if QA subsequently rejects.
        _our_cost = 0.0
        try:
            from cost_meter import record_operation
            from generate_tour_text import _LAST_GENERATION_COST
            _cost_info = _LAST_GENERATION_COST
            _is_cache_hit = _cost_info.get("cache_hit", False)
            _op_type = "tour_cache_hit" if _is_cache_hit else "tour_generate"
            _our_cost = _cost_info.get("total_cost", 0.0)
            _breakdown = _cost_info.get("breakdown", {})
            record_operation(
                operation_type=_op_type,
                our_cost_usd=_our_cost,
                cache_hit=_is_cache_hit,
                user_id=user_id,
                job_id=job_id,
                breakdown=_breakdown,
            )
            print(f"[LOCAL-60] Cost metered: {_op_type} | ${_our_cost:.6f} | cache_hit={_is_cache_hit}")
        except Exception as _meter_err:
            print(f"[LOCAL-60] Cost metering failed (non-fatal): {_meter_err}")

        # [LOCAL-64] Enforce cost ceiling — SEPARATE try block, FAILS CLOSED.
        # A safety control must not share an exception handler with instrumentation.
        # If this check cannot run (DB down, import error, bad config), we abort
        # delivery — a tour we cannot price is a tour we must not ship.
        try:
            from cost_ceiling_monitor import enforce_cost_ceiling
            _ceiling_result = enforce_cost_ceiling(
                total_cost=_our_cost,
                job_id=job_id,
                user_id=user_id,
                tour_category=tour_type,
            )
            if _ceiling_result["abort"]:
                # Hard limit exceeded — do NOT deliver this tour
                ACTIVE_JOBS.update(job_id, status="error",
                    error=_ceiling_result["message"],
                    error_type="cost_hard_limit_exceeded")
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                return
        except Exception as _ceiling_err:
            # FAIL CLOSED: ceiling check itself failed — abort delivery.
            import logging as _ceil_logging
            _ceil_logging.getLogger("generate_tour_text_service").error(
                f"[LOCAL-64] COST CEILING CHECK FAILED — aborting delivery (fail-closed): {_ceiling_err}"
            )
            print(f"[LOCAL-64] ERROR: Cost ceiling check failed — aborting delivery: {_ceiling_err}")
            ACTIVE_JOBS.update(job_id, status="error",
                error=f"Cost ceiling check unavailable ({type(_ceiling_err).__name__}: {_ceiling_err}). "
                      f"Tour not delivered — fail-closed safety policy.",
                error_type="cost_ceiling_check_failed")
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return

        # [LOCAL-83] Charge the user's wallet — SEPARATE try block, FAILS CLOSED.
        # This is a billing control (D14): if charging fails, do NOT deliver.
        # Do NOT share an exception handler with cost metering above.
        # Idempotency: use job_id as the key — a retried generation charges once (LOCAL-66).
        if user_id and _our_cost > 0:
            try:
                from pricing import compute_user_charge as _compute_charge
                from wallet_ledger import charge as _wallet_charge, record_unlimited_cost as _record_unlimited
                from entitlements import _get_subscription_tier

                _user_tier = _get_subscription_tier(user_id)
                _charge_result = _compute_charge(
                    our_cost_usd=_our_cost,
                    cache_hit=_is_cache_hit,
                    operation_type=_op_type,
                    description=f"Tour: {location[:200]}",
                )

                if _user_tier == 'ppu' and _charge_result['user_charge_cents'] > 0:
                    _charge_idem_key = f"charge:{user_id}:{job_id}"
                    _row_id, _new_bal, _was_stopped = _wallet_charge(
                        user_id=user_id,
                        charge_usd=_charge_result['user_charge_usd'],
                        idempotency_key=_charge_idem_key,
                        description=f"Tour: {location[:200]} — ${_charge_result['user_charge_usd']:.2f}",
                        job_id=job_id,
                    )
                    if _was_stopped:
                        # Balance insufficient — should not happen if entitlements passed,
                        # but fail closed anyway.
                        import logging as _charge_logging
                        _charge_logging.getLogger("generate_tour_text_service").error(
                            f"[LOCAL-83] CHARGE BLOCKED (zero balance) for {user_id} job={job_id}"
                        )
                        ACTIVE_JOBS.update(job_id, status="error",
                            error="Insufficient balance to complete this tour. Please top up your credits.",
                            error_type="charge_blocked_zero_balance")
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)
                        return
                    print(f"[LOCAL-83] PPU charged: ${_charge_result['user_charge_usd']:.2f} | "
                          f"balance={_new_bal}¢ | user={user_id} | job={job_id}")

                elif _user_tier == 'unlimited':
                    from decimal import Decimal as _Dec
                    _record_unlimited(user_id, _Dec(str(_our_cost)))
                    print(f"[LOCAL-83] Unlimited cost recorded: ${_our_cost:.6f} | user={user_id} | job={job_id}")

                # free tier or cache hit ($0 charge): no wallet action needed
            except Exception as _charge_err:
                # FAIL CLOSED (D14): charging failed — do NOT deliver unbilled tour.
                import logging as _charge_logging
                _charge_logging.getLogger("generate_tour_text_service").error(
                    f"[LOCAL-83] CHARGING FAILED — aborting delivery (fail-closed): {_charge_err}"
                )
                print(f"[LOCAL-83] ERROR: Charging failed — aborting delivery: {_charge_err}")
                ACTIVE_JOBS.update(job_id, status="error",
                    error=f"Billing unavailable ({type(_charge_err).__name__}: {_charge_err}). "
                          f"Tour not delivered — fail-closed billing policy.",
                    error_type="charge_failed")
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                return

        # [BLOCKER4c] QA gate — corrections on structured data, never deliver on exit 1
        if os.getenv('STORIED_MODE', 'false').lower() == 'true' and tour_text:
            import content_qa_runner
            import re as _qa_re
            
            # Load story elements for G4 check (persisted during generate_tour_text)
            _serving_story_elements = None
            try:
                import json as _json
                _elem_path = temp_path.replace('.txt', '_story_elements.json')
                if os.path.exists(_elem_path):
                    with open(_elem_path, 'r') as _ef:
                        _serving_story_elements = _json.load(_ef)
                    print(f"[BLOCKER4c] Loaded {len(_serving_story_elements)} story elements for G4 check")
                else:
                    print(f"[BLOCKER4c] No story_elements file at {_elem_path} — G4 will use fail-closed")
            except Exception as _elem_err:
                print(f"[BLOCKER4c] story_elements load error: {_elem_err}")
            
            _QA_MAX_ROUNDS = 3
            _qa_passed = False
            
            for _qa_round in range(1, _QA_MAX_ROUNDS + 1):
                # Run QA with story_elements passed in-memory
                content_qa_runner.PASS_COUNT = 0
                content_qa_runner.FAIL_COUNT = 0
                content_qa_runner.FACTUAL_FAIL_COUNT = 0
                try:
                    # B7: Build venue_context from location for G4 proper-noun exclusion
                    _venue_ctx = None
                    try:
                        _loc_parts = location.split(',')
                        _venue_name_raw = _loc_parts[0].strip() if _loc_parts else location
                        _city_raw = _loc_parts[1].strip() if len(_loc_parts) > 1 else ''
                        _region_raw = _loc_parts[2].strip() if len(_loc_parts) > 2 else ''
                        _venue_tokens = set(w.lower() for w in re.split(r'[\s\-]+', _venue_name_raw) if len(w) >= 3)
                        # Get tier from generation module (exposed via module-level var)
                        _gen_tier = ''
                        try:
                            from generate_tour_text import _LAST_VERIFICATION_TIER
                            _gen_tier = _LAST_VERIFICATION_TIER or ''
                        except (ImportError, AttributeError):
                            pass
                        _venue_ctx = {
                            'venue_tokens': _venue_tokens,
                            'city': _city_raw,
                            'region': _region_raw,
                            'artist': '',  # Will be populated if venue_resolver provides it
                            'tier': _gen_tier,
                        }
                    except Exception:
                        pass
                    # [LOCAL-22] Print all Stop N: headings BEFORE QA for verification
                    _debug_headers = re.findall(r'^(Stop\s+\d+:.+)$', tour_text, re.MULTILINE)
                    print(f"  Rendered Stop headings ({len(_debug_headers)}):")
                    for _dh in _debug_headers:
                        print(f"    {_dh[:120]}")
                    content_qa_runner.run_qa(tour_text, story_elements=_serving_story_elements, venue_context=_venue_ctx)
                except SystemExit:
                    pass  # run_qa calls sys.exit() — catch it
                except Exception as _qa_err:
                    print(f"[BLOCKER4c] QA error: {_qa_err}")
                    # [F1] QA infrastructure error → reject (fail closed). Never deliver unverified.
                    ACTIVE_JOBS.update(job_id, status="error",
                                      error=f"Tour quality check failed (infrastructure error). Please try again.")
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    return
                
                # Check result
                if content_qa_runner.FACTUAL_FAIL_COUNT == 0 and content_qa_runner.FAIL_COUNT == 0:
                    _qa_passed = True
                    print(f"[BLOCKER4c] QA PASSED (round {_qa_round}): all checks clean")
                    break
                elif content_qa_runner.FACTUAL_FAIL_COUNT > 0:
                    # Factual failure — reject entirely (upstream pipeline bug, not fixable here)
                    print(f"[BLOCKER4c] FACTUAL QA FAILED (round {_qa_round}): {content_qa_runner.FACTUAL_FAIL_COUNT} factual failure(s)")
                    ACTIVE_JOBS.update(job_id, status="error",
                                      error=f"Tour failed factual integrity check ({content_qa_runner.FACTUAL_FAIL_COUNT} factual failures). Please try again.")
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    return
                else:
                    # Style failures only — apply algorithmic corrections, then re-check
                    print(f"[BLOCKER4c] Style issues (round {_qa_round}): {content_qa_runner.FAIL_COUNT} style failure(s) — correcting")
                    try:
                        from derepetition_guard import FORBIDDEN_PHRASES
                        for pattern in FORBIDDEN_PHRASES:
                            tour_text = pattern.sub('', tour_text)
                        tour_text = _qa_re.sub(r'  +', ' ', tour_text)
                        tour_text = _qa_re.sub(r'\n\n\n+', '\n\n', tour_text)
                    except ImportError:
                        import logging as _svc_logging
                        _svc_logging.getLogger("generate_tour_text_service").error(
                            "[BLOCKER4c] MISSING: derepetition_guard (FORBIDDEN_PHRASES) — style correction DISABLED"
                        )
                    # Loop continues — will re-run QA on corrected text
            
            if not _qa_passed:
                # After max rounds, style issues remain — but QA DID complete successfully
                # (factual gates passed, only style checks failed). Deliver with warning.
                if content_qa_runner.FACTUAL_FAIL_COUNT == 0:
                    _style_warning = f"Delivered with {content_qa_runner.FAIL_COUNT} style issue(s) after {_QA_MAX_ROUNDS} correction rounds"
                    print(f"[BLOCKER4c] {_style_warning}")
                    # [G1/W1] Set qa_style_warning on the job for auditability
                    ACTIVE_JOBS.update(job_id, qa_style_warning=_style_warning)
                else:
                    # Should not reach here (factual failures reject above), but fail-closed safety
                    ACTIVE_JOBS.update(job_id, status="error",
                                      error=f"Tour failed quality checks. Please try again.")
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    return

        # Create a safe filename for the output
        safe_location = ''.join(c if c.isalnum() else '_' for c in location)
        safe_tour_type = ''.join(c if c.isalnum() else '_' for c in tour_type)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{safe_location}_{safe_tour_type}_tour_{timestamp}.txt"
        output_path = os.path.join(TOURS_DIR, output_filename)
        
        # Copy the temporary file to the output path
        import shutil
        shutil.copy2(temp_path, output_path)
        
        # Clean up the temporary file
        os.unlink(temp_path)
        
        # --- I-CON EVALUATION (STORIED_MODE only, AFTER QA loop) ---
        # Evaluates the DELIVERED text (what the customer actually hears)
        _icon_result = None
        if os.environ.get("STORIED_MODE") == "true":
            try:
                from icon_evaluator import evaluate_tour_icon, report_icon_gate
                with open(output_path, 'r', encoding='utf-8') as _f:
                    _delivered_text = _f.read()
                _icon_result = evaluate_tour_icon(_delivered_text)
                report_icon_gate(_icon_result)
                
                # [B1b] Map poi_list verified flags to i-con stops for stop_metrics
                if _icon_result and _icon_result.get("stops"):
                    try:
                        from generate_tour_text import _LAST_POI_LIST as poi_list
                        if poi_list:
                            for i, stop_result in enumerate(_icon_result["stops"]):
                                if i < len(poi_list):
                                    stop_result["verified"] = poi_list[i].get("verified", True)
                    except (ImportError, AttributeError):
                        pass

                # Persist to stop_metrics (non-blocking)
                try:
                    _persist_icon_metrics(_icon_result, job_id)
                except Exception as _pe:
                    print(f"[I-CON] Persistence error (non-fatal): {_pe}")
            except ImportError:
                import logging as _svc_logging
                _svc_logging.getLogger("generate_tour_text_service").error(
                    "[I-CON] MISSING: icon_evaluator (evaluate_tour_icon, report_icon_gate) — I-CON evaluation DISABLED"
                )
                print("[I-CON] icon_evaluator not available — skipped")
            except Exception as _ie:
                print(f"[I-CON] Evaluation error (non-fatal): {_ie}")
        
        # Update job status — use .update() for database-mode compatibility
        tour_content_str = None
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                tour_content_str = f.read()
        except Exception as content_err:
            print(f"Warning: Could not read tour_content: {content_err}")
        
        ACTIVE_JOBS.update(job_id, status="completed",
                          progress="Tour text generation completed successfully!",
                          output_file=output_filename,
                          coordinates=coordinates,
                          **({"tour_content": tour_content_str} if tour_content_str else {}),
                          **({"i_con_avg": _icon_result["tour_avg"]} if _icon_result else {}))
        
    except Exception as e:
        ACTIVE_JOBS.update(job_id, status="error", error=str(e))

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint with code integrity info."""
    try:
        import manifest_check
        _manifest_info = manifest_check.get_health_info()
    except ImportError:
        _manifest_info = {
            "code_sha": "manifest_check_unavailable",
            "build_time": "unknown",
            "manifest_ok": False,
            "drift_files": ["manifest_check.py not found in image"],
        }

    # [LOCAL-64] Include cost ceiling stats for monitoring/alerting
    try:
        from cost_ceiling_monitor import get_ceiling_stats
        _ceiling_stats = get_ceiling_stats()
    except ImportError:
        _ceiling_stats = {}

    return jsonify({
        "status": "healthy",
        "service": "tour_text_generator",
        "version": SERVICE_VERSION,
        "mode": os.getenv("STORIED_MODE", "false"),
        "code_sha": _manifest_info.get("code_sha", "unknown"),
        "build_time": _manifest_info.get("build_time", "unknown"),
        "manifest_ok": _manifest_info.get("manifest_ok", False),
        **({
            "drift_files": _manifest_info["drift_files"]
        } if not _manifest_info.get("manifest_ok", False) else {}),
        "cost_ceiling": _ceiling_stats,
    })

@app.route('/generate', methods=['POST'])
def generate_tour():
    """Generate tour text."""
    data = request.json
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    # Get parameters
    location = data.get('location')
    tour_type = data.get('tour_type')
    total_stops = data.get('total_stops', 10)
    user_id = data.get('user_id')  # [S46] Extract user_id for persona lookup
    
    api_call_logger.log("GENERATOR_SERVICE_RECEIVED_REQUEST", {
        "raw_request_body": data,
        "location": location,
        "tour_type": tour_type,
        "total_stops_raw": data.get('total_stops', '(not provided - will default to 10)'),
        "total_stops_resolved": total_stops,
    })
    
    if not location or not tour_type:
        return jsonify({"error": "location and tour_type are required"}), 400
    
    try:
        total_stops = int(total_stops)
        if total_stops < 1 or total_stops > 50:
            return jsonify({"error": "total_stops must be between 1 and 50"}), 400
    except ValueError:
        return jsonify({"error": "total_stops must be a valid integer"}), 400
    
    # Generate job ID
    job_id = str(uuid.uuid4())
    
    # Initialize job tracking
    ACTIVE_JOBS[job_id] = {
        "status": "queued",
        "progress": "Job queued for processing",
        "location": location,
        "tour_type": tour_type,
        "total_stops": total_stops,
        "created_at": datetime.now().isoformat()
    }
    
    # Start generation in background thread
    thread = threading.Thread(
        target=generate_tour_async,
        args=(job_id, location, tour_type, total_stops, user_id)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({"job_id": job_id, "status": "queued"})

@app.route('/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get job status."""
    if job_id not in ACTIVE_JOBS:
        return jsonify({"error": "Job not found"}), 404
    
    job = ACTIVE_JOBS[job_id]
    response = {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "location": job["location"],
        "tour_type": job["tour_type"],
        "total_stops": job["total_stops"],
        "created_at": job["created_at"]
    }
    
    if job["status"] == "completed":
        response["output_file"] = job["output_file"]
        if "coordinates" in job:
            response["coordinates"] = job["coordinates"]
        if "tour_content" in job:
            response["tour_content"] = job["tour_content"]
    elif job["status"] == "error":
        response["error"] = job["error"]
        # Phase 2: structured clean-fail fields (if present)
        if "error_type" in job:
            response["error_type"] = job["error_type"]
        if "evidence_summary" in job:
            response["evidence_summary"] = job["evidence_summary"]
    
    return jsonify(response)

@app.route('/download/<job_id>', methods=['GET'])
def download_tour(job_id):
    """Download the generated tour text."""
    if job_id not in ACTIVE_JOBS:
        return jsonify({"error": "Job not found"}), 404
    
    job = ACTIVE_JOBS[job_id]
    if job["status"] != "completed":
        return jsonify({"error": "Job not completed"}), 400
    
    output_path = os.path.join(TOURS_DIR, job["output_file"])
    if not os.path.exists(output_path):
        return jsonify({"error": "File not found"}), 404
    
    return send_file(output_path, as_attachment=True, download_name=job["output_file"])

@app.route('/jobs', methods=['GET'])
def list_jobs():
    """List all generation jobs."""
    jobs = []
    for job_id, job_data in ACTIVE_JOBS.items():
        job_info = {
            "job_id": job_id,
            "status": job_data["status"],
            "location": job_data["location"],
            "tour_type": job_data["tour_type"],
            "total_stops": job_data["total_stops"],
            "created_at": job_data["created_at"],
            "progress": job_data.get("progress", "")
        }
        
        # Add coordinates if available
        if "coordinates" in job_data:
            job_info["coordinates"] = job_data["coordinates"]
        
        jobs.append(job_info)
    
    return jsonify({"jobs": jobs})

if __name__ == '__main__':
    # Ensure tours directory exists
    ensure_tours_directory()
    
    print(f"Starting Modified Tour Text Generator Service...")
    print(f"Tours directory: {TOURS_DIR}")
    
    # Run Flask app
    port = int(os.getenv('PORT', '5000'))
    app.run(host='0.0.0.0', port=port, debug=False)