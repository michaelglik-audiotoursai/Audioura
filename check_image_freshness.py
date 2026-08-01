#!/usr/bin/env python3
"""
check_image_freshness.py — compare running containers against host working tree.

For every running audioura/development container, compare the Python source
files inside the container against the host's working tree.  Print a table
showing which containers are fresh and which have drifted.

Three states:
  FRESH   — manifest present and all files match, OR no manifest but direct
            file comparison shows all files identical.
  STALE   — manifest present and mismatched, OR direct comparison shows drift.
  UNKNOWN — no manifest AND cannot determine file state (container unreachable, etc.)

Usage:
    python check_image_freshness.py              # check all running containers
    python check_image_freshness.py --verbose    # show per-file diffs

Requires: docker CLI available on PATH.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime


# Containers to check — maps container name prefix to the directory in the
# image where .py files live.
CONTAINER_APP_DIR = "/app"

# Host working tree root (override with --host-dir)
DEFAULT_HOST_DIR = os.path.dirname(os.path.abspath(__file__))

# Map of service names (as they appear in docker-compose) to their build
# context subdirectory relative to the host root.  Services not listed here
# use the root directory as their build context.
SERVICE_BUILD_CONTEXT = {
    "map-delivery": "map_delivery",
    "user-api-2": "user-tracking",
    "tour-update": "tour-update-service",
    "coordinates-fromai": "coordinates_fromAI",
    "voice-control": "voice_control",
    "translation-service": "translation-service",
}

# Map of (service_key, container_filename) → host_filename for services that
# rename files during COPY (e.g., `COPY treats_service.py app.py`).
SERVICE_FILE_RENAMES = {
    ("treats", "app.py"): "treats_service.py",
    ("tour-processor", "build_mp3.py"): "build_mp3_simple.py",
}


def resolve_host_dir_for_container(container_name, base_host_dir):
    """
    Given a container name, determine the host directory that was used as the
    build context.  Subdirectory services (map-delivery, user-api-2, etc.)
    have their source in a subfolder; root-context services use the repo root.
    """
    for service_key, subdir in SERVICE_BUILD_CONTEXT.items():
        if service_key in container_name:
            candidate = os.path.join(base_host_dir, subdir)
            if os.path.isdir(candidate):
                return candidate
    return base_host_dir


def resolve_host_filename(container_name, container_filename):
    """
    Some services rename files during COPY (e.g., treats: COPY treats_service.py app.py).
    Return the host-side filename for a given container filename.
    """
    for (service_key, cfile), host_file in SERVICE_FILE_RENAMES.items():
        if service_key in container_name and cfile == container_filename:
            return host_file
    return container_filename


def md5_file(path):
    """Return hex MD5 of a local file."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def get_running_containers():
    """Return list of (container_id, container_name, image) for running containers."""
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.CreatedAt}}"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"ERROR: docker ps failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    containers = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            containers.append({
                "id": parts[0],
                "name": parts[1],
                "image": parts[2],
                "created": parts[3] if len(parts) > 3 else "unknown",
            })
    return containers


def get_container_manifest(container_name):
    """Try to read .build_manifest.json from inside a container."""
    result = subprocess.run(
        ["docker", "exec", container_name, "cat", f"{CONTAINER_APP_DIR}/.build_manifest.json"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return None
    return None


def get_container_file_md5(container_name, filepath):
    """Get the md5 of a file inside a container."""
    result = subprocess.run(
        ["docker", "exec", container_name, "md5sum", filepath],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout.split()[0]
    # Fallback for containers without md5sum (e.g., alpine)
    result = subprocess.run(
        ["docker", "exec", container_name, "python3", "-c",
         f"import hashlib; print(hashlib.md5(open('{filepath}','rb').read()).hexdigest())"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def list_container_py_files(container_name):
    """List .py files in the container's /app directory."""
    result = subprocess.run(
        ["docker", "exec", container_name, "python3", "-c",
         f"import os; print('\\n'.join(f for f in sorted(os.listdir('{CONTAINER_APP_DIR}')) "
         f"if f.endswith('.py') and os.path.isfile(os.path.join('{CONTAINER_APP_DIR}', f))))"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return [f for f in result.stdout.strip().split("\n") if f]
    return []


def check_container(container_name, host_dir, verbose=False):
    """
    Compare a container's Python files against the host working tree.
    Returns (status, details) where status is 'FRESH', 'STALE', or 'UNKNOWN'.
    """
    manifest = get_container_manifest(container_name)

    # Resolve the correct host directory for this container
    effective_host_dir = resolve_host_dir_for_container(container_name, host_dir)

    # Get list of .py files in container
    container_files = list_container_py_files(container_name)
    if not container_files:
        return "UNKNOWN", {"reason": "Could not list files in container",
                           "manifest_present": manifest is not None,
                           "code_sha": manifest.get("git_sha", "unknown") if manifest else "no_manifest",
                           "build_time": manifest.get("build_time", "unknown") if manifest else "no_manifest",
                           "host_dir": effective_host_dir}

    diffs = []
    checked = 0
    files_compared = []

    for filename in container_files:
        # Resolve potential file renames (e.g., treats_service.py → app.py)
        host_filename = resolve_host_filename(container_name, filename)
        host_path = os.path.join(effective_host_dir, host_filename)
        if not os.path.exists(host_path):
            # File exists in container but not on host — might be fine (generated)
            continue

        host_md5 = md5_file(host_path)

        # Get container md5 — prefer manifest, fall back to live check
        container_md5 = None
        if manifest and filename in manifest.get("files", {}):
            container_md5 = manifest["files"][filename]["md5"]
        else:
            container_path = f"{CONTAINER_APP_DIR}/{filename}"
            container_md5 = get_container_file_md5(container_name, container_path)

        if container_md5 is None:
            diffs.append({"file": filename, "reason": "could not read md5 from container"})
            continue

        checked += 1
        files_compared.append(filename)
        if host_md5 != container_md5:
            host_size = os.path.getsize(host_path)
            diffs.append({
                "file": filename,
                "host_md5": host_md5,
                "container_md5": container_md5,
                "host_size": host_size,
            })

    details = {
        "files_checked": checked,
        "files_drifted": len(diffs),
        "manifest_present": manifest is not None,
        "code_sha": manifest.get("git_sha", "unknown") if manifest else "no_manifest",
        "build_time": manifest.get("build_time", "unknown") if manifest else "no_manifest",
        "host_dir": effective_host_dir,
        "files_compared": files_compared,
    }
    if diffs:
        details["drifted_files"] = diffs

    if checked == 0:
        status = "UNKNOWN"
    elif len(diffs) == 0:
        status = "FRESH"
    else:
        status = "STALE"

    return status, details


def main():
    parser = argparse.ArgumentParser(
        description="Check running containers against host working tree for code drift"
    )
    parser.add_argument("--host-dir", default=DEFAULT_HOST_DIR,
                        help="Host directory containing the source tree")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show per-file differences")
    parser.add_argument("--container", "-c", default=None,
                        help="Check only this container (by name or ID)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    args = parser.parse_args()

    containers = get_running_containers()
    if not containers:
        print("No running containers found.")
        sys.exit(0)

    # Filter to our project containers (audioura/development/news/tour/etc.)
    project_prefixes = (
        "development-", "audioura-", "tour-", "news-", "newsletter-",
        "polly-", "translation-", "simple-news-"
    )
    project_containers = [
        c for c in containers
        if any(c["name"].startswith(p) for p in project_prefixes)
        or (args.container and (args.container in c["name"] or args.container == c["id"]))
    ]

    if args.container:
        # Also try exact match
        project_containers = [
            c for c in containers
            if args.container in c["name"] or args.container == c["id"]
        ]

    if not project_containers:
        print("No project containers found running.")
        if args.container:
            print(f"  (looked for: {args.container})")
        sys.exit(0)

    results = []
    for container in project_containers:
        status, details = check_container(container["name"], args.host_dir, args.verbose)
        results.append({
            "container": container["name"],
            "image": container["image"],
            "created": container["created"],
            "status": status,
            **details,
        })

    if args.json:
        print(json.dumps(results, indent=2))
        sys.exit(0 if all(r["status"] in ("FRESH", "UNKNOWN") for r in results) else 1)

    # Print table
    print(f"\n{'='*80}")
    print(f"IMAGE FRESHNESS CHECK — {datetime.now().isoformat()}")
    print(f"Host dir: {args.host_dir}")
    print(f"{'='*80}\n")

    any_stale = False
    for r in results:
        if r["status"] == "FRESH":
            status_icon = "✅"
        elif r["status"] == "STALE":
            status_icon = "❌"
        elif r["status"] == "UNKNOWN":
            status_icon = "⚠️"
        else:
            status_icon = "❓"

        manifest_tag = ""
        if not r.get("manifest_present", False) and r["status"] != "UNKNOWN":
            manifest_tag = " (no manifest — compared live)"

        print(f"{status_icon} {r['container']:<40} {r['status']}{manifest_tag}")
        print(f"   Image: {r['image']}")
        print(f"   Created: {r['created']}")
        print(f"   SHA: {r.get('code_sha', 'unknown')}")
        print(f"   Built: {r.get('build_time', 'unknown')}")
        print(f"   Files checked: {r.get('files_checked', 0)}, drifted: {r.get('files_drifted', 0)}")
        if r.get("host_dir") and r["host_dir"] != args.host_dir:
            print(f"   Source dir: {r['host_dir']}")

        if r["status"] == "STALE":
            any_stale = True
            if args.verbose and "drifted_files" in r:
                for df in r["drifted_files"]:
                    print(f"      ⚠ {df['file']}: host={df.get('host_md5', '?')[:8]}… "
                          f"container={df.get('container_md5', '?')[:8]}…"
                          f" (host size: {df.get('host_size', '?')})")

        if r["status"] == "UNKNOWN" and r.get("reason"):
            print(f"   Reason: {r['reason']}")

        if args.verbose and r["status"] == "FRESH" and r.get("files_compared"):
            print(f"   Verified: {', '.join(r['files_compared'][:5])}"
                  + (f" (+{len(r['files_compared'])-5} more)" if len(r['files_compared']) > 5 else ""))

        print()

    print(f"{'='*80}")
    summary_parts = []
    fresh_count = sum(1 for r in results if r["status"] == "FRESH")
    stale_count = sum(1 for r in results if r["status"] == "STALE")
    unknown_count = sum(1 for r in results if r["status"] == "UNKNOWN")
    if fresh_count:
        summary_parts.append(f"✅ {fresh_count} FRESH")
    if stale_count:
        summary_parts.append(f"❌ {stale_count} STALE")
    if unknown_count:
        summary_parts.append(f"⚠️  {unknown_count} UNKNOWN")
    print(f"Summary: {' | '.join(summary_parts)}")

    if any_stale:
        print("\n⚠️  STALE CONTAINERS DETECTED — rebuild required:")
        print("   docker-compose -f docker-compose-master.yml build --build-arg GIT_SHA=$(git rev-parse HEAD) <service>")
        print("   docker-compose -f docker-compose-master.yml up -d <service>")
        sys.exit(1)
    else:
        print("\n✅ All containers are fresh (or UNKNOWN — no manifest to compare).")
        sys.exit(0)


if __name__ == "__main__":
    main()
