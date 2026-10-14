#!/usr/bin/env python3
"""
LOCAL-586 repair — strip the FORCED STOPS — VERIFICATION HARNESS banner that the
LOCAL-357 harness path stamped into real listener-chosen-stops tours.

WHAT IT DOES
    Scans every `audio_tours` row whose `tour_content` column OR whose stored ZIP
    (`audio_tour` BYTEA) member `tour_content.txt` contains the banner. For each:

      --dry-run (default):
          Prints id, user (best-effort from cost_ledger by time), created_at,
          stops_count, where the banner lives (column / zip / both) and how many
          banner blocks were found. Changes NOTHING.

      --apply:
          1. Backs up the row's `tour_content` and `audio_tour` bytes to
                 /Volumes/AudiouraSSD/backup_local586/<id>.json   (metadata + text)
                 /Volumes/AudiouraSSD/backup_local586/<id>.zip    (raw audio_tour)
             BEFORE touching anything.
          2. Removes ONLY the contiguous banner region from `tour_content` and from
             the ZIP's `tour_content.txt`. Every OTHER member of the ZIP (audio
             mp3, audio_N.txt, index.html, manifest.json, service-worker.js) is
             copied through BYTE-IDENTICAL (same bytes, same compression type).
          3. UPDATEs the row's `tour_content` and `audio_tour`.
          4. Reports before/after sizes and the md5 of every audio_*.mp3 before and
             after (must be unchanged).

    NEVER deletes a row. NEVER touches lat/lng. NEVER regenerates a tour. The audio
    is never re-encoded — only the text member of the ZIP is rewritten.

USAGE
    python3 repair_local586_harness_banner.py --dry-run
    python3 repair_local586_harness_banner.py --apply

    Database: $DATABASE_URL, else postgresql://admin:password123@localhost:5433/audiotours
    (the local development-postgres-2-1 container, host port 5433).
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime

import psycopg2

BACKUP_DIR = "/Volumes/AudiouraSSD/backup_local586"
BANNER_MARK = "FORCED STOPS — VERIFICATION HARNESS"
ZIP_TEXT_MEMBER = "tour_content.txt"

DEFAULT_DB_URL = "postgresql://admin:password123@localhost:5433/audiotours"


# ──────────────────────────── Banner stripping ────────────────────────────
# The banner region is one-or-more HARNESS blocks, optionally preceded by a full
# "=" rule, each block closed by a separator line that is EITHER a full 70-"="
# rule or a lone "=" (the implicit-concat *70 bug left lone "=" closers). The
# region is anchored to the start of the text and ends at the first blank line
# that precedes the real tour body. We match the full region in one pass so we
# strip the banner and ONLY the banner.
#
# Block body (fixed wording from _build_harness_banner / the original literal):
_BLOCK_BODY = (
    r"⚠️  FORCED STOPS — VERIFICATION HARNESS \(LOCAL-357\)\n"
    r"    This tour was generated with a forced stop list\.\n"
    r"    It is NOT a naturally-selected tour and must not be\n"
    r"    scored as evidence of selection quality\.\n"
    r"    Forced: .*?\n"
)
# A separator line: a run of "=" (1..N) on its own line.
_SEP = r"=+\n"

# Full banner region: optional leading bar, then 1+ (body + separator), then any
# trailing blank lines. Anchored at the start (the banner is always stamped at the
# very top of the content, before "Step-by-Step Audio Guided Tour:").
_BANNER_REGION = re.compile(
    r"\A(?:=+\n)?(?:" + _BLOCK_BODY + _SEP + r")+\n*",
    re.DOTALL,
)


def strip_banner(text):
    """Remove the leading harness banner region. Returns (clean_text, n_blocks).

    n_blocks is the number of HARNESS block bodies removed (0 if none). Only the
    anchored leading region is touched; the tour body is left exactly as-is.
    """
    if text is None:
        return None, 0
    if BANNER_MARK not in text:
        return text, 0
    m = _BANNER_REGION.match(text)
    if not m:
        # Banner present but not in the exact anchored shape — do NOT guess.
        return text, -1
    region = m.group(0)
    n_blocks = region.count(BANNER_MARK)
    clean = text[m.end():]
    return clean, n_blocks


# ──────────────────────────── ZIP handling ────────────────────────────
def zip_member_banner_count(zip_bytes):
    """Return the HARNESS count in the ZIP's tour_content.txt (0 if absent)."""
    if not zip_bytes:
        return 0
    try:
        zf = zipfile.ZipFile(io.BytesIO(bytes(zip_bytes)))
    except zipfile.BadZipFile:
        return 0
    if ZIP_TEXT_MEMBER not in zf.namelist():
        return 0
    try:
        return zf.read(ZIP_TEXT_MEMBER).decode("utf-8", "replace").count(BANNER_MARK)
    except Exception:
        return 0


def audio_md5_map(zip_bytes):
    """md5 of every audio_*.mp3 member, keyed by member name."""
    out = {}
    if not zip_bytes:
        return out
    zf = zipfile.ZipFile(io.BytesIO(bytes(zip_bytes)))
    for n in zf.namelist():
        if re.fullmatch(r"audio_\d+\.mp3", n):
            out[n] = hashlib.md5(zf.read(n)).hexdigest()
    return out


def rewrite_zip_strip_banner(zip_bytes):
    """Return (new_zip_bytes, n_blocks_removed, before_len, after_len).

    Rewrites the ZIP so tour_content.txt has the banner stripped. EVERY other
    member is copied through byte-identical (raw bytes, original compression
    type and metadata preserved). If tour_content.txt is absent or clean, the
    ZIP bytes are returned unchanged.
    """
    src = zipfile.ZipFile(io.BytesIO(bytes(zip_bytes)))
    if ZIP_TEXT_MEMBER not in src.namelist():
        return bytes(zip_bytes), 0, None, None

    before = src.read(ZIP_TEXT_MEMBER).decode("utf-8")
    clean, n_blocks = strip_banner(before)
    if n_blocks <= 0:
        # Nothing to strip (0) or unrecognised shape (-1): leave ZIP untouched.
        return bytes(zip_bytes), n_blocks, len(before), len(before)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == ZIP_TEXT_MEMBER:
                data = clean.encode("utf-8")
            # Preserve the member's original ZipInfo (name, date, compression,
            # external attrs) so every other file stays byte-for-byte identical
            # and only the text member's payload changes.
            dst.writestr(info, data)
    return out.getvalue(), n_blocks, len(before), len(clean)


# ──────────────────────────── DB helpers ────────────────────────────
def get_db_url():
    return os.environ.get("DATABASE_URL", DEFAULT_DB_URL)


def best_effort_user(cur, created_at):
    """Best-effort user attribution: the cost_ledger tour_generate/spine_generate
    row nearest at or before this tour's created_at (within 10 minutes). The
    audio_tours table has no user_id column and no FK to cost_ledger, so this is
    a heuristic for reporting only — it never drives the repair."""
    if created_at is None:
        return "unknown"
    try:
        cur.execute(
            """
            SELECT user_id FROM cost_ledger
            WHERE operation_type IN ('tour_generate', 'spine_generate')
              AND created_at <= %s
              AND created_at >= %s - interval '10 minutes'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (created_at, created_at),
        )
        row = cur.fetchone()
        return row[0] if row and row[0] else "unknown"
    except Exception:
        return "unknown"


def find_affected(cur):
    """Return a list of affected row dicts (banner in column and/or ZIP)."""
    cur.execute(
        "SELECT id, tour_name, created_at, stops_count, tour_content, audio_tour "
        "FROM audio_tours ORDER BY id"
    )
    rows = cur.fetchall()
    affected = []
    for rid, name, created_at, stops_count, content, audio in rows:
        col_count = content.count(BANNER_MARK) if content else 0
        zip_count = zip_member_banner_count(audio)
        if col_count == 0 and zip_count == 0:
            continue
        affected.append({
            "id": rid,
            "tour_name": name,
            "created_at": created_at,
            "stops_count": stops_count,
            "col_count": col_count,
            "zip_count": zip_count,
            "content": content,
            "audio": bytes(audio) if audio is not None else None,
        })
    return affected


# ──────────────────────────── Backup ────────────────────────────
def write_backup(row):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    rid = row["id"]
    meta = {
        "id": rid,
        "tour_name": row["tour_name"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "stops_count": row["stops_count"],
        "backed_up_at": datetime.utcnow().isoformat() + "Z",
        "tour_content": row["content"],
        "audio_tour_md5": hashlib.md5(row["audio"]).hexdigest() if row["audio"] else None,
        "audio_tour_bytes": len(row["audio"]) if row["audio"] else 0,
        "audio_md5_by_member": audio_md5_map(row["audio"]),
    }
    json_path = os.path.join(BACKUP_DIR, f"{rid}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    zip_path = None
    if row["audio"]:
        zip_path = os.path.join(BACKUP_DIR, f"{rid}.zip")
        with open(zip_path, "wb") as f:
            f.write(row["audio"])
    return json_path, zip_path


# ──────────────────────────── Main ────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="LOCAL-586 harness-banner repair")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true",
                   help="list affected rows, change nothing (default)")
    g.add_argument("--apply", action="store_true",
                   help="back up, strip banner from column + ZIP, UPDATE rows")
    args = ap.parse_args()
    apply = args.apply
    mode = "APPLY" if apply else "DRY-RUN"

    conn = psycopg2.connect(get_db_url())
    conn.autocommit = False
    cur = conn.cursor()

    affected = find_affected(cur)
    print(f"[LOCAL-586] mode={mode}  db={get_db_url().rsplit('@', 1)[-1]}")
    print(f"[LOCAL-586] affected rows: {len(affected)}")
    print("-" * 78)
    if not affected:
        print("No rows contain the harness banner. Nothing to do.")
        conn.close()
        return

    for row in affected:
        rid = row["id"]
        user = best_effort_user(cur, row["created_at"])
        where = []
        if row["col_count"]:
            where.append(f"column×{row['col_count']}")
        if row["zip_count"]:
            where.append(f"zip×{row['zip_count']}")
        print(f"id={rid}  user={user}  created_at={row['created_at']}  "
              f"stops_count={row['stops_count']}  banner_in={', '.join(where)}")
        print(f"    tour_name: {row['tour_name']}")

        if not apply:
            # Preview the strip result without writing.
            clean, n = strip_banner(row["content"])
            if row["content"] is not None:
                print(f"    tour_content: {len(row['content'])} → "
                      f"{len(clean) if clean is not None else '?'} chars "
                      f"({n if n >= 0 else 'UNRECOGNISED SHAPE — would skip'} blocks)")
            continue

        # ---- APPLY ----
        json_path, zip_path = write_backup(row)
        print(f"    backup: {json_path}" + (f" , {zip_path}" if zip_path else ""))

        # Strip column.
        new_content, col_blocks = strip_banner(row["content"]) if row["content"] else (row["content"], 0)
        if col_blocks == -1:
            print("    SKIP: tour_content banner did not match the expected shape "
                  "— leaving row untouched to avoid damaging real content.")
            continue

        # Strip ZIP member (and verify audio md5 unchanged).
        new_audio = row["audio"]
        zip_blocks = 0
        before_md5 = audio_md5_map(row["audio"]) if row["audio"] else {}
        if row["audio"] and row["zip_count"]:
            new_audio, zip_blocks, zlen_before, zlen_after = rewrite_zip_strip_banner(row["audio"])
            if zip_blocks == -1:
                print("    SKIP: ZIP tour_content.txt banner did not match the "
                      "expected shape — leaving row untouched.")
                continue
            after_md5 = audio_md5_map(new_audio)
            if before_md5 != after_md5:
                print("    ABORT: audio md5 changed — refusing to write. "
                      f"before={before_md5} after={after_md5}")
                conn.rollback()
                continue
            print(f"    zip tour_content.txt: {zlen_before} → {zlen_after} chars "
                  f"({zip_blocks} blocks removed)")
            print(f"    audio md5 unchanged: {after_md5}")

        cur.execute(
            "UPDATE audio_tours SET tour_content = %s, audio_tour = %s WHERE id = %s",
            (new_content, psycopg2.Binary(new_audio) if new_audio is not None else None, rid),
        )
        print(f"    tour_content: {len(row['content']) if row['content'] else 0} → "
              f"{len(new_content) if new_content else 0} chars ({col_blocks} blocks removed)")
        print(f"    UPDATED row {rid} (no DELETE, lat/lng untouched)")

    if apply:
        conn.commit()
        print("-" * 78)
        print("[LOCAL-586] committed.")
    else:
        print("-" * 78)
        print("[LOCAL-586] dry-run only — no changes written. Re-run with --apply.")
    conn.close()


if __name__ == "__main__":
    main()
