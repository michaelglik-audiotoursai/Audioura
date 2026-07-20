"""PALAIS-FIX B4: Pilot run for Palais Lascaris via containerized tour-generator.

Calls the Docker tour-generator service, saves output as pilot artifact
with code_sha, code_dirty, and regression suite results.
"""
import json
import os
import subprocess
import sys
import time
import requests

GENERATOR_URL = "http://localhost:5000"
LOCATION = "Palais Lascaris, Nice"
TOUR_TYPE = "art and historical instruments"
TOTAL_STOPS = 6
OUTPUT_FILE = "tours/palais_lascaris_pilot.json"


def get_code_sha():
    """Get current git commit SHA."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__))
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def get_code_dirty():
    """Check if working tree is dirty — report honestly with reason."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__))
        )
        lines = [l for l in result.stdout.strip().split('\n') if l.strip()]
        if not lines:
            return False, "clean"
        # Check if changes are only CRLF / untracked files
        modified = [l for l in lines if l.startswith(' M') or l.startswith('M ')]
        untracked = [l for l in lines if l.startswith('??')]
        if modified or untracked:
            reasons = []
            if modified:
                reasons.append(f"{len(modified)} modified (CRLF/content changes)")
            if untracked:
                reasons.append(f"{len(untracked)} untracked files")
            return True, "; ".join(reasons)
        return True, "uncommitted changes"
    except Exception:
        return True, "git status failed"


def run_regression_suites():
    """Run ALL regression suites and capture verbatim output."""
    suites = [
        ("palais_lead_fixture", "test_palais_fix_lead_fixture.py"),
        ("b6_generation_wiring", "test_b6_generation_wiring.py"),
        ("f4_cache_roundtrip", "test_f4_cache_roundtrip.py"),
        ("g4_false_positives", "test_g4_false_positives.py"),
        ("sq2_fixtures", "test_sq2_fixtures.py"),
        ("sq3_fixtures", "test_sq3_fixtures.py"),
        ("sq4_merge", "test_sq4_merge.py"),
        ("w4_matcher", "test_w4_matcher.py"),
        ("w7_wiring", "test_w7_wiring.py"),
        ("w9_collection_anchor", "test_w9_collection_anchor.py"),
        ("tier_computation", "test_tier_computation.py"),
    ]
    results = {}
    for name, script in suites:
        try:
            result = subprocess.run(
                [sys.executable, script],
                capture_output=True, text=True, timeout=60,
                cwd=os.path.dirname(os.path.abspath(__file__)),
                env={**os.environ, "PYTHONIOENCODING": "utf-8"}
            )
            stdout_lines = result.stdout.strip().split('\n') if result.stdout else []
            results[name] = {
                "exit_code": result.returncode,
                "passed": result.returncode == 0,
                "stdout": result.stdout.strip()[-2000:] if result.stdout else "",
                "stderr_tail": result.stderr.strip()[-500:] if result.stderr else "",
            }
        except subprocess.TimeoutExpired:
            results[name] = {"exit_code": -1, "passed": False, "error": "timeout"}
        except Exception as e:
            results[name] = {"exit_code": -1, "passed": False, "error": str(e)}
        status = "PASS" if results[name]["passed"] else "FAIL"
        print(f"  {status}: {name} (exit {results[name]['exit_code']})")
    return results


def wait_for_service(url, timeout=60):
    """Wait for service to be healthy."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{url}/health", timeout=5)
            if r.status_code == 200:
                return True
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(2)
    return False


def submit_tour_job():
    """Submit generation job and poll for completion."""
    payload = {
        "location": LOCATION,
        "tour_type": TOUR_TYPE,
        "total_stops": TOTAL_STOPS,
    }
    print(f"Submitting tour generation: {LOCATION} ({TOUR_TYPE}, {TOTAL_STOPS} stops)")
    r = requests.post(f"{GENERATOR_URL}/generate", json=payload, timeout=30)
    if r.status_code != 200:
        return None, f"Submit failed: {r.status_code} {r.text[:200]}"

    data = r.json()
    job_id = data.get("job_id")
    if not job_id:
        return None, f"No job_id in response: {data}"

    print(f"Job submitted: {job_id}")

    # Poll for completion
    max_wait = 300  # 5 minutes
    start = time.time()
    while time.time() - start < max_wait:
        time.sleep(10)
        try:
            status_r = requests.get(f"{GENERATOR_URL}/status/{job_id}", timeout=10)
            if status_r.status_code == 200:
                status_data = status_r.json()
                status = status_data.get("status", "")
                print(f"  [{int(time.time()-start)}s] Status: {status}")
                if status == "complete" or status == "completed":
                    return status_data, None
                elif status == "error" or status == "failed":
                    return status_data, f"Job failed: {status_data.get('error', 'unknown')}"
        except Exception as e:
            print(f"  Poll error: {e}")

    return None, "Timeout waiting for job completion"


def main():
    print("=" * 60)
    print("PALAIS-FIX B4 PILOT: Palais Lascaris")
    print("=" * 60)

    # Run ALL regression suites
    print("\n--- Running regression suites ---")
    regression_results = run_regression_suites()
    all_passed = all(r["passed"] for r in regression_results.values())
    print(f"\nOverall: {'ALL PASS' if all_passed else 'SOME FAILURES'}")

    # Get code metadata
    code_sha = get_code_sha()
    code_dirty, dirty_reason = get_code_dirty()
    print(f"\nCode SHA: {code_sha}")
    print(f"Code dirty: {code_dirty}")
    print(f"Dirty reason: {dirty_reason}")

    # Wait for service
    print(f"\n--- Waiting for tour-generator at {GENERATOR_URL} ---")
    if not wait_for_service(GENERATOR_URL):
        print("ERROR: Service not healthy after 60s")
        # Save partial artifact
        artifact = {
            "pilot": "palais_lascaris",
            "code_sha": code_sha,
            "code_dirty": code_dirty,
            "dirty_reason": dirty_reason,
            "regression_suites": regression_results,
            "generation": {"status": "service_unavailable"},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        os.makedirs("tours", exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2, ensure_ascii=False)
        print(f"Partial artifact saved: {OUTPUT_FILE}")
        sys.exit(1)

    print("Service healthy!")

    # Submit and wait for tour
    print("\n--- Generating Palais Lascaris tour ---")
    result, error = submit_tour_job()

    # Build artifact
    artifact = {
        "pilot": "palais_lascaris",
        "code_sha": code_sha,
        "code_dirty": code_dirty,
        "dirty_reason": dirty_reason,
        "regression_suites": regression_results,
        "generation": {
            "location": LOCATION,
            "tour_type": TOUR_TYPE,
            "total_stops_requested": TOTAL_STOPS,
            "status": "complete" if result and not error else "error",
            "error": error,
            "result": result,
        },
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    os.makedirs("tours", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"ARTIFACT SAVED: {OUTPUT_FILE}")
    print(f"Generation: {'SUCCESS' if not error else f'FAILED: {error}'}")
    print(f"Regression: {'ALL PASS' if all_passed else 'SOME FAILURES'}")
    print(f"{'=' * 60}")

    sys.exit(0 if not error and all_passed else 1)


if __name__ == "__main__":
    main()
