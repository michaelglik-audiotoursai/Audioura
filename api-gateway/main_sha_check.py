#!/usr/bin/env python3
"""main_sha_check.py — prove byte-identity of two gateway main.py files.

GCS-5R2: the new gateway image must ship v35's EXACT main.py, not storied's
(storied's main.py diverges: attestation rewrite, sys.path hack, extra /health
fields — 54/29 lines). Before building the image we stage main.py from
`git show origin/main:api-gateway/main.py` (LEAD-verified identical to the
running services/api-gateway:v35 image's /app/main.py apart from a line-1 BOM
their export added) and compare it against the /app/main.py extracted from the
v35 image itself.

We normalise ONLY line endings (CRLF/CR -> LF) and a leading UTF-8 BOM, because
those are the only differences an image export / Windows checkout can introduce
and they do not change the code the interpreter runs. ANY other byte difference
must fail the deploy.

Usage:
    python api-gateway/main_sha_check.py <staged_main.py> <image_main.py>

Prints the normalised SHA256 of each file and exits 0 iff they match, non-zero
otherwise. utf-8 on every read (Windows-safe).
"""
import hashlib
import sys


def normalised_bytes(path):
    with open(path, "rb") as f:
        raw = f.read()
    # Strip a single leading UTF-8 BOM if present.
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    # Normalise CRLF and lone CR to LF.
    raw = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return raw


def sha256_of(path):
    return hashlib.sha256(normalised_bytes(path)).hexdigest()


def main():
    if len(sys.argv) != 3:
        print("usage: main_sha_check.py <staged_main.py> <image_main.py>")
        return 2
    staged, image = sys.argv[1], sys.argv[2]
    staged_sha = sha256_of(staged)
    image_sha = sha256_of(image)
    print(f"staged main.py : {staged}")
    print(f"  sha256 (norm CRLF/BOM) = {staged_sha}")
    print(f"image  main.py : {image}")
    print(f"  sha256 (norm CRLF/BOM) = {image_sha}")
    print("=" * 60)
    if staged_sha == image_sha:
        print("PASS: staged gateway main.py is byte-identical to the v35 image "
              "main.py (CRLF/BOM-normalised).")
        return 0
    print("FAIL: staged main.py differs from the v35 image main.py. The gateway "
          "image would NOT ship v35's code. Aborting.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
