#!/usr/bin/env python3
"""
beta_image_drift_check.py — reusable Beta-drift check for the shared Cloud Run image.

WHY THIS EXISTS
---------------
The Cloud Run image is built with `COPY *.py /app/` (Dockerfile.cloudrun), so every
service image carries EVERY root .py file and the CMD only selects which one runs.
That means "I diffed the one file I edited, nothing drifted" is NOT sufficient evidence
that Beta behaviour is unchanged: dozens of sibling modules can differ between two image
builds. Whether that matters depends entirely on whether any drifted module is on the
RUNTIME IMPORT PATH of the entrypoint the service actually runs.

The GCS-REVIEW-1 review established this the hard way (30 modules drifted in the news
image, 49 in the map image; none on the import path, so behaviourally inert — but that
is incidental, not structural, and must be re-checked on EVERY shared-image deploy).

This script writes that procedure down so nobody has to rediscover it.

WHAT IT DOES
------------
Given two image references (e.g. the newly built image and the currently-deployed image)
and the entrypoint module a service runs, it:
  1. extracts every root .py from both images,
  2. computes the transitive LOCAL-import closure of the entrypoint (best-effort static
     analysis of `import X` / `from X import ...` limited to modules present in the image),
  3. diffs the two images file-by-file (SHA-256), and
  4. classifies each drifted file as ON the import path (BEHAVIOURAL RISK) or OFF it
     (behaviourally inert for this entrypoint).

Exit code is non-zero iff any drift lands on the import path — so it is CI-usable.

USAGE
-----
  # Compare a freshly built local image against the live deployed digest:
  python beta_image_drift_check.py \
      --new  gcs4-verify:latest \
      --old  us-docker.pkg.dev/audioura/.../audioura@sha256:068f6fea... \
      --entrypoint news_orchestrator_service.py

  # Map-delivery:
  python beta_image_drift_check.py \
      --new  gcs4-verify:latest \
      --old  ...audioura@sha256:24f0ceaa... \
      --entrypoint map_delivery_service.py

Discover the live digest first:
  gcloud run services describe news-orchestrator --region <r> \
      --format='value(spec.template.spec.containers[0].image)'

Requires: docker CLI on PATH. Does NOT deploy, does NOT touch the DB, read-only.
"""

import argparse
import ast
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path


def _run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def extract_py(image, dest):
    """Create a container from `image` and copy every /app/*.py into `dest`."""
    dest.mkdir(parents=True, exist_ok=True)
    cid = _run(["docker", "create", image]).stdout.strip()
    try:
        # Copy the whole /app then keep only *.py at top level.
        tmp = dest.parent / (dest.name + "_app")
        _run(["docker", "cp", f"{cid}:/app/.", str(tmp)])
    finally:
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True, text=True)
    files = {}
    for p in Path(tmp).glob("*.py"):
        files[p.name] = p.read_bytes()
        (dest / p.name).write_bytes(p.read_bytes())
    return files


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def import_closure(entrypoint, files):
    """Best-effort transitive closure of local imports starting at `entrypoint`.

    `files` maps module_filename -> source bytes. Only imports that resolve to a
    module actually present in the image are followed (stdlib / pip deps are ignored
    for the purpose of 'did a SIBLING FILE change').
    """
    present = {name[:-3] for name in files if name.endswith(".py")}
    closure = set()
    stack = [entrypoint]
    while stack:
        cur = stack.pop()
        if cur in closure:
            continue
        closure.add(cur)
        src = files.get(cur)
        if src is None:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                mods = [node.module.split(".")[0]]
            for m in mods:
                if m in present:
                    dep = m + ".py"
                    if dep not in closure:
                        stack.append(dep)
    return closure


def main():
    ap = argparse.ArgumentParser(description="Beta shared-image drift check")
    ap.add_argument("--new", required=True, help="new/candidate image ref")
    ap.add_argument("--old", required=True, help="old/deployed image ref")
    ap.add_argument("--entrypoint", required=True,
                    help="entrypoint .py the service CMDs (e.g. news_orchestrator_service.py)")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        print(f"Extracting {args.new} ...")
        new_files = extract_py(args.new, td / "new")
        print(f"Extracting {args.old} ...")
        old_files = extract_py(args.old, td / "old")

    all_names = sorted(set(new_files) | set(old_files))
    added = [n for n in all_names if n not in old_files]
    removed = [n for n in all_names if n not in new_files]
    changed = [n for n in all_names
               if n in new_files and n in old_files
               and sha(new_files[n]) != sha(old_files[n])]

    closure = import_closure(args.entrypoint, new_files)

    print("\n=== IMAGE DRIFT SUMMARY ===")
    print(f"entrypoint       : {args.entrypoint}")
    print(f"import closure   : {len(closure)} modules -> {sorted(closure)}")
    print(f"added files      : {len(added)} {added}")
    print(f"removed files    : {len(removed)} {removed}")
    print(f"changed files    : {len(changed)}")

    on_path_changed = sorted(set(changed) & closure)
    off_path_changed = sorted(set(changed) - closure)
    # Removals of a module that IS on the import path are also a runtime risk.
    on_path_removed = sorted(set(removed) & closure)

    print("\n--- changed ON import path (BEHAVIOURAL RISK) ---")
    for n in on_path_changed:
        print(f"  ! {n}")
    print("\n--- changed OFF import path (behaviourally inert for this entrypoint) ---")
    for n in off_path_changed:
        print(f"    {n}")
    if on_path_removed:
        print("\n--- REMOVED but on import path (WOULD FAIL TO START) ---")
        for n in on_path_removed:
            print(f"  !! {n}")

    risk = on_path_changed or on_path_removed
    print("\n=== VERDICT ===")
    if risk:
        print("DRIFT ON IMPORT PATH — Beta behaviour may have changed. Investigate before deploy.")
        return 2
    print("No drift on the import path. Any drift is behaviourally inert for this "
          "entrypoint (re-verify on the NEXT shared-image deploy — this is incidental, "
          "not structural).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
