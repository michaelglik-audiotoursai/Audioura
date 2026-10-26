"""[wdvrdaz5yt] translation-service/_meter must stay byte-identical to _meter/,
and the translation image must bake it in at /opt/meter with PYTHONPATH."""
import filecmp
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_meter_copy_identical():
    src = os.path.join(ROOT, "_meter")
    dst = os.path.join(ROOT, "translation-service", "_meter")
    names = sorted(n for n in os.listdir(src) if n.endswith(".py"))
    assert names, "no meter modules found"
    match, mismatch, errors = filecmp.cmpfiles(src, dst, names, shallow=False)
    assert not mismatch and not errors, (
        "translation-service/_meter is stale; run: cp _meter/*.py translation-service/_meter/ "
        f"(mismatch={mismatch}, missing={errors})")


def test_translation_dockerfile_bakes_meter():
    df = open(os.path.join(ROOT, "translation-service", "Dockerfile")).read()
    assert "COPY _meter/ /opt/meter/" in df
    assert "ENV PYTHONPATH=/opt/meter" in df
