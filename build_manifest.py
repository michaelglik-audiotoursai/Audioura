#!/usr/bin/env python3
"""
Build-time manifest generator.

Run during `docker build` to record the checksums and git SHA of the Python
sources copied into the image.  Writes /app/.build_manifest.json.

Usage (in Dockerfile):
    RUN python build_manifest.py
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone


def md5_file(path):
    """Return hex MD5 of a file."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def get_git_sha():
    """Try to read git SHA from build arg or .git_sha file."""
    # Prefer build-arg injected file (see Dockerfile ARG GIT_SHA)
    sha_file = "/app/.git_sha"
    if os.path.exists(sha_file):
        with open(sha_file) as f:
            return f.read().strip()
    # Fallback: try git directly (won't work in most Docker builds)
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def generate_manifest(app_dir="/app", output_path="/app/.build_manifest.json"):
    """Scan all .py files in app_dir and write the manifest."""
    files = {}
    for entry in sorted(os.listdir(app_dir)):
        if entry.endswith(".py"):
            full_path = os.path.join(app_dir, entry)
            if os.path.isfile(full_path):
                files[entry] = {
                    "md5": md5_file(full_path),
                    "size": os.path.getsize(full_path),
                }

    manifest = {
        "git_sha": get_git_sha(),
        "build_time": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }

    with open(output_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"[build_manifest] Wrote {output_path}: {len(files)} files, sha={manifest['git_sha']}")
    return manifest


if __name__ == "__main__":
    app_dir = sys.argv[1] if len(sys.argv) > 1 else "/app"
    output = sys.argv[2] if len(sys.argv) > 2 else os.path.join(app_dir, ".build_manifest.json")
    generate_manifest(app_dir, output)
