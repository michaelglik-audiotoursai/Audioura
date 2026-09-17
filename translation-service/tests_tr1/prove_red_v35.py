"""
GCS-TR1 RED proof against the deployed v35 baseline (byte-identical to commit 73d8eb5).

This demonstrates the failures the fix addresses, using the SAME local Postgres + MinIO
stack as the green suite. It imports the v35 file under an alias so it can run side by
side with the fixed module.

Expected: these checks FAIL on v35 (that is the point — D242 "break it, see red").
Run via tests_tr1/prove_red.sh, which loads the v35 copy into place first.

Behavioral checks (no TranslationArtifactError exists in v35, so we assert on outcomes):
  * AC1/AC5: v35 inserts a row whose audio_tour is NULL and tour_blob_uri is NULL
             -> not servable by map-delivery -> the historic 404.
  * AC3:     v35 returns an existing artifact-less row as a cache hit.
"""
import io
import os
import sys
import zipfile

import psycopg2

# The v35 baseline copy and blobstorage.py live in the service dir (parent of tests_tr1/).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# import the v35 baseline copied next to this file as _v35_translation_service.py
import _v35_translation_service as ts  # noqa: E402

RUS = "\u041f\u0435\u0440\u0435\u0432\u043e\u0434"


def _fake_translate_text(self, text, target_language, preserve_voice_commands=False):
    if target_language == "en" or not text:
        return text
    return f"[{target_language}] {RUS}: {text}"


def _fake_generate_audio(self, text, target_language):
    return b"ID3FAKEMP3" + text.encode("utf-8")[:16]


def _make_source_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("tour.html", "<html><head><title>t</title></head><body>"
                                "<h1>Stop 1</h1><p>Welcome to the first stop of this tour.</p>"
                                "</body></html>")
        for i in (1, 2, 3):
            z.writestr(f"audio_{i}.mp3", b"ID3ORIG" + str(i).encode())
            z.writestr(f"audio_{i}.txt", f"English narration for stop {i}.")
    return buf.getvalue()


SRC_CONTENT = ("Stop 1: Welcome to the first stop of this tour.\n\n"
               "Stop 2: Here is the second stop.\n\n"
               "Stop 3: The final stop.")


def _conn():
    return psycopg2.connect(host=os.environ["DB_HOST"], database=os.environ["DB_NAME"],
                            user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
                            port=os.environ["DB_PORT"])


def _reset_table():
    c = _conn(); c.autocommit = True; cur = c.cursor()
    cur.execute("DROP TABLE IF EXISTS audio_tours")
    cur.execute("""CREATE TABLE audio_tours (
        id SERIAL PRIMARY KEY, tour_name TEXT, request_string TEXT, audio_tour BYTEA,
        number_requested INTEGER DEFAULT 0, lat DOUBLE PRECISION, lng DOUBLE PRECISION,
        content_language TEXT, original_tour_id INTEGER, tour_content TEXT,
        tour_blob_uri TEXT, track TEXT)""")
    cur.close(); c.close()


def _seed(track="beta", key="tours/107.zip", upload=True):
    if upload:
        from blobstorage import R2BlobStorage
        R2BlobStorage().upload(key, _make_source_zip())
    c = _conn(); c.autocommit = True; cur = c.cursor()
    cur.execute("""INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested,
                   lat, lng, content_language, original_tour_id, tour_content, tour_blob_uri, track)
                   VALUES (%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                ("Original Tour", "walking tour", 1, 40.0, -73.0, "en", None, SRC_CONTENT, key, track))
    sid = cur.fetchone()[0]; cur.close(); c.close()
    return sid


def _fetch(rid):
    c = _conn(); cur = c.cursor()
    cur.execute("SELECT id, audio_tour, tour_blob_uri FROM audio_tours WHERE id=%s", (rid,))
    r = cur.fetchone(); cur.close(); c.close()
    return r


def _servable(audio_tour, blob_uri):
    return audio_tour is not None or blob_uri is not None


def main():
    ts.TranslationService.translate_text = _fake_translate_text
    ts.TranslationService.generate_audio = _fake_generate_audio
    svc = ts.TranslationService()

    failures = []

    # RED 1: R2-migrated source (tour_content set, audio_tour NULL) -> v35 inserts artifact-less row.
    _reset_table()
    sid = _seed(key="tours/107.zip")
    new_id = svc.translate_tour_with_audio(sid, "ru")
    row = _fetch(new_id) if new_id else None
    if row and _servable(row[1], row[2]):
        print("UNEXPECTED: v35 produced a servable artifact (should have been NULL)")
    else:
        print(f"RED CONFIRMED (AC1/AC5): v35 created tour {new_id} with NO artifact "
              f"(audio_tour NULL, tour_blob_uri NULL) -> map-delivery 404")
        failures.append("v35 inserts artifact-less row")

    # RED 3: artifact-less cache row is returned as a hit.
    _reset_table()
    sid = _seed(key="tours/107c.zip")
    c = _conn(); c.autocommit = True; cur = c.cursor()
    cur.execute("""INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested,
                   lat, lng, content_language, original_tour_id, tour_content, tour_blob_uri, track)
                   VALUES (%s,%s,NULL,%s,%s,%s,%s,%s,%s,NULL,%s) RETURNING id""",
                ("broken ru", "walking tour", 0, 40.0, -73.0, "ru", sid, "x", "beta"))
    broken_id = cur.fetchone()[0]; cur.close(); c.close()
    ret = svc.translate_tour_with_audio(sid, "ru")
    if ret == broken_id:
        print(f"RED CONFIRMED (AC3): v35 returned artifact-less cached row {broken_id} as a hit")
        failures.append("v35 cache trap returns broken row")
    else:
        print(f"UNEXPECTED: v35 did not return the broken cache row (got {ret})")

    print()
    if failures:
        print(f"RED PROOF: {len(failures)} historic failure(s) reproduced on v35:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)  # non-zero: the baseline is broken, as expected
    print("No failures reproduced (unexpected for v35).")
    sys.exit(0)


if __name__ == "__main__":
    main()
