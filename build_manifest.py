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


def _read_build_arg_file(path):
    """Return the stripped contents of a build-arg-injected file, or None.

    The build args are written to files by Dockerfile.cloudrun (see
    `RUN echo "${GIT_SHA}" > /app/.git_sha`). We read a file rather than an env
    var because build_manifest.py runs at build time; env vars promoted via ENV
    are only reliably visible at run time, and the file gives a single, explicit
    contract for both this generator and any debugging.
    """
    if os.path.exists(path):
        with open(path) as f:
            val = f.read().strip()
            return val if val else None
    return None


def get_git_sha():
    """Try to read git SHA from build arg or .git_sha file.

    Baked in at build time via --build-arg GIT_SHA (never computed inside the
    container: the .git directory is NOT in the build context, so `git rev-parse`
    here would silently fail and report a wrong or empty value).
    """
    val = _read_build_arg_file("/app/.git_sha")
    if val:
        return val
    # Fallback: try git directly. This only works in a host/dev checkout, NEVER
    # in the Cloud Run image (COPY *.py leaves no .git). We keep it for local
    # `python build_manifest.py .` runs, but the build-arg file is authoritative.
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def get_build_number():
    """Return the display build number (the vNNN the app shows).

    Baked in at build time via --build-arg BUILD_NUMBER (git rev-list --count HEAD).
    Returns the sentinel "unknown" when the build arg was omitted, so a build
    made without the plumbing degrades to a CLEARLY missing value rather than
    silently carrying a stale or wrong number. A wrong build_number is worse
    than none: it mislabels which engine produced a tour.
    """
    val = _read_build_arg_file("/app/.build_number")
    if val:
        return val
    return "unknown"


def get_git_branch():
    """Return the branch the image was built from (baked via --build-arg GIT_BRANCH)."""
    val = _read_build_arg_file("/app/.git_branch")
    if val:
        return val
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
        "build_number": get_build_number(),
        "git_branch": get_git_branch(),
        "build_time": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }

    with open(output_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(
        f"[build_manifest] Wrote {output_path}: {len(files)} files, "
        f"sha={manifest['git_sha']}, build_number={manifest['build_number']}, "
        f"branch={manifest['git_branch']}"
    )
    return manifest


if __name__ == "__main__":
    app_dir = sys.argv[1] if len(sys.argv) > 1 else "/app"
    output = sys.argv[2] if len(sys.argv) > 2 else os.path.join(app_dir, ".build_manifest.json")
    generate_manifest(app_dir, output)
