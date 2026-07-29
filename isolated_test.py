#!/usr/bin/env python3
"""
Runs one live tour-generation call inside a disposable, resource-capped
Docker container -- for LEAD's live-verification step during review,
without touching the shared long-running audioura-tour-generator-1
container and without racing another concurrent review's test.

Concurrency is bounded (continuous_dev_lib.Semaphore, default 3 slots) so
this can't pile up and exhaust the Mac Mini's Docker budget. Every test
image is removed immediately after use. The request signature is
auto-suffixed with the task ID so two concurrent tests can never collide
on tour_cache_layer1's (location, tour_type, total_stops) cache key --
the exact bug class found reviewing LOCAL-8.

Usage:
  python3 isolated_test.py --task-id LOCAL-9 \
      --location "Restaurants tour in old city of Nice, France" \
      --tour-type restaurant --stops 6 --output /tmp/local9_test.txt
"""
import argparse
import subprocess
import sys
import time
import uuid
from pathlib import Path

import continuous_dev_lib as cdl

WATCH_DIR = cdl.WATCH_DIR
DOCKERFILE = "Dockerfile.generator"
ENV_FILE = WATCH_DIR / ".env"
COMPOSE_NETWORK = "development_default"  # so DATABASE_URL's postgres-2 host resolves
MAX_CONCURRENT_TESTS = 3
DEFAULT_TIMEOUT_SECONDS = 15 * 60
MEMORY_LIMIT = "512m"
CPU_LIMIT = "2"


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--location", required=True)
    ap.add_argument("--tour-type", required=True)
    ap.add_argument("--stops", type=int, required=True)
    ap.add_argument("--context", default=str(WATCH_DIR), help="build context (worktree path)")
    ap.add_argument("--output", help="path (on host) to save the generated tour text")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    ap.add_argument(
        "--no-suffix", action="store_true",
        help="skip auto-appending [test:<task-id>] to the location (only if you already guarantee uniqueness)",
    )
    args = ap.parse_args()

    location = args.location if args.no_suffix else f"{args.location} [test:{args.task_id}]"
    image_tag = f"audioura-test-{args.task_id.lower()}"
    container_name = f"{image_tag}-{uuid.uuid4().hex[:8]}"

    host_out_dir = Path(args.output).resolve().parent if args.output else None
    if host_out_dir:
        host_out_dir.mkdir(parents=True, exist_ok=True)
    container_output = f"/host_out/{Path(args.output).name}" if args.output else "/tmp/isolated_test_output.txt"

    sem = cdl.Semaphore("isolated_test", MAX_CONCURRENT_TESTS)
    print(f"Waiting for a test slot (max {MAX_CONCURRENT_TESTS} concurrent)...")
    sem.acquire()
    print("Slot acquired. Building image...")
    try:
        build = run(
            ["docker", "build", "-f", DOCKERFILE, "-t", image_tag, args.context],
            timeout=600,
        )
        if build.returncode != 0:
            print("BUILD FAILED:\n" + build.stdout[-4000:] + build.stderr[-4000:])
            sys.exit(1)

        script = (
            "import sys, os\n"
            "sys.path.insert(0, '/app')\n"
            "os.environ['STORIED_MODE'] = 'true'\n"
            "from generate_tour_text import generate_tour_text\n"
            f"text, _, _ = generate_tour_text({location!r}, {args.tour_type!r}, {container_output!r}, {args.stops})\n"
            "print(f'SUCCESS: {len(text)} chars' if text else 'FAILED')\n"
        )

        docker_cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--memory", MEMORY_LIMIT,
            "--cpus", CPU_LIMIT,
            "--network", COMPOSE_NETWORK,
            "-e", "DATABASE_URL=postgresql://admin:password123@postgres-2:5432/audiotours",
            "-e", "STORIED_MODE=true",
        ]
        if ENV_FILE.exists():
            docker_cmd += ["--env-file", str(ENV_FILE)]
        if host_out_dir:
            docker_cmd += ["-v", f"{host_out_dir}:/host_out"]
        docker_cmd += [image_tag, "python", "-c", script]

        start = time.monotonic()
        try:
            result = run(docker_cmd, timeout=args.timeout)
            status = "SUCCESS" if result.returncode == 0 and "SUCCESS" in result.stdout else "FAILED"
            output_text = result.stdout + result.stderr
        except subprocess.TimeoutExpired as e:
            run(["docker", "kill", container_name], timeout=30)
            status = "TIMEOUT"
            output_text = (e.stdout or "") + (e.stderr or "")

        duration = int(time.monotonic() - start)
        print(f"{status} in {duration}s")
        print(output_text[-3000:])
        if args.output and status == "SUCCESS":
            print(f"Output written to: {args.output}")
    finally:
        run(["docker", "rmi", "-f", image_tag], timeout=120)
        sem.release()


if __name__ == "__main__":
    main()
