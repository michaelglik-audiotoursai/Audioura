"""Service images must ship the shared modules their code imports.

2026-10-26: LOCAL-781/785 merged code that imports blobstorage / failure_log /
safe_headers, but four Dockerfiles with explicit COPY lists (or sub-directory
build contexts) did not package them. The imports are guarded, so the features
were silently OFF in the cloud images (and LOCAL-781's R2 resolve would fail).
GCloud_Storied caught it before deploy. This test keeps it from slipping again.
"""
import filecmp
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(p):
    with open(os.path.join(ROOT, p)) as f:
        return f.read()


def _copied(dockerfile):
    names = set()
    for line in _read(dockerfile).splitlines():
        if line.strip().startswith("COPY"):
            names.update(re.findall(r"([\w./-]+\.py)", line))
    return {os.path.basename(n) for n in names}


def test_tour_id_resolution_image_ships_blob_and_failure_log():
    c = _copied("Dockerfile.tour-id-resolution")
    assert {"blobstorage.py", "failure_log.py", "tour_id_resolution_service.py"} <= c
    assert "boto3" in _read("requirements-tour-id-resolution.txt")


def test_orchestrator_image_ships_failure_log_and_safe_headers():
    c = _copied("Dockerfile.orchestrator")
    assert {"failure_log.py", "safe_headers.py"} <= c


def test_translation_image_ships_failure_log():
    assert "failure_log.py" in _copied("translation-service/Dockerfile")


def test_subdir_copies_identical_to_root():
    for sub in ("map_delivery/failure_log.py", "translation-service/failure_log.py",
                "user-tracking/failure_log.py"):
        assert filecmp.cmp(os.path.join(ROOT, "failure_log.py"),
                           os.path.join(ROOT, sub), shallow=False), sub
    assert filecmp.cmp(os.path.join(ROOT, "safe_headers.py"),
                       os.path.join(ROOT, "map_delivery/safe_headers.py"), shallow=False)
