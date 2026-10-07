#!/usr/bin/env python3
"""
tour_cost_report.py — Per-tour cost breakdown by provider.
===========================================================
[LOCAL-609]  Michael: "let's get all broken into each part."

Prints, for ONE tour, a table of every provider × ($, units), the delivery
total, the reused-research total, and the wall time (orchestrator start →
completed). Includes the translation and TTS rows of any translation of that
tour.

Usage
-----
    python3 tour_cost_report.py <audio_tour_id | job_id>

The argument is resolved as follows:
  * If it is an integer, it is first tried as an `audio_tours.id`; the report
    links that tour to its cost_ledger rows via the stored job_id (when the
    column exists) or, failing that, by matching the ledger `description` to the
    tour name. If no audio_tour row matches, the same value is tried as a job_id.
  * Otherwise it is treated as a job_id and matched directly against
    cost_ledger.job_id (this is the reliable key the generator writes).

The cost figures come straight from `cost_ledger.breakdown` (the JSONB written
by LOCAL-609), so this report is a READER — it never re-prices anything. Every
dollar it prints was counted at a real call site.

Reads the database with the same connection logic as cost_meter. Needs
DATABASE_URL (or DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD) in the environment.
"""

import argparse
import json
import os
import sys
from typing import Optional


# ─── DB helpers (mirror cost_meter's connection logic) ───────────────────────
def _get_db_url() -> Optional[str]:
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        return db_url
    host = os.environ.get("DB_HOST", "postgres-2")
    port = os.environ.get("DB_PORT", "5432")
    dbname = os.environ.get("DB_NAME", "audiotours")
    user = os.environ.get("DB_USER", "admin")
    password = os.environ.get("DB_PASSWORD", "password123")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def _connect():
    import psycopg2
    url = _get_db_url()
    if not url:
        raise RuntimeError("No database URL available (set DATABASE_URL).")
    return psycopg2.connect(url)


# ─── Ledger row loading ──────────────────────────────────────────────────────
def _rows_for_job(conn, job_id: str):
    """Every cost_ledger row for a job_id, oldest first."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT operation_type, our_cost_usd, cache_hit, job_id, breakdown,
                   description, created_at
            FROM cost_ledger
            WHERE job_id = %s
            ORDER BY created_at ASC
            """,
            (job_id,),
        )
        return [_row_dict(r) for r in cur.fetchall()]


def _row_dict(r) -> dict:
    bd = r[4]
    if bd is not None and not isinstance(bd, dict):
        try:
            bd = json.loads(bd)
        except Exception:
            bd = {}
    return {
        "operation_type": r[0],
        "our_cost_usd": float(r[1]) if r[1] is not None else 0.0,
        "cache_hit": bool(r[2]),
        "job_id": r[3],
        "breakdown": bd or {},
        "description": r[5] or "",
        "created_at": r[6],
    }


def _resolve_target(conn, arg: str):
    """Resolve the CLI argument to (job_id, audio_tour_meta).

    Returns (job_id or None, meta dict). meta may carry 'audio_tour_id',
    'tour_name', 'created_at' when an audio_tours row was found.
    """
    meta = {}
    # Try audio_tours.id when the argument is an integer.
    if arg.isdigit():
        at = _lookup_audio_tour(conn, int(arg))
        if at:
            meta = at
            if at.get("job_id"):
                return at["job_id"], meta
            # No job_id column/value — fall back to matching the ledger by name.
            jid = _job_id_by_description(conn, at.get("tour_name", ""))
            if jid:
                return jid, meta
            # Last resort: treat the integer itself as a job_id.
            return arg, meta
    # Not an integer, or no audio_tours row — treat as a job_id directly.
    return arg, meta


def _lookup_audio_tour(conn, audio_tour_id: int) -> Optional[dict]:
    """Best-effort audio_tours lookup. Tolerates a missing job_id column."""
    # Does audio_tours have a job_id column?
    has_job_id = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'audio_tours' AND column_name = 'job_id'
                LIMIT 1
                """
            )
            has_job_id = cur.fetchone() is not None
    except Exception:
        has_job_id = False

    cols = "id, tour_name, created_at" + (", job_id" if has_job_id else "")
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {cols} FROM audio_tours WHERE id = %s", (audio_tour_id,))
            row = cur.fetchone()
    except Exception:
        return None
    if not row:
        return None
    meta = {
        "audio_tour_id": row[0],
        "tour_name": row[1] or "",
        "created_at": row[2],
    }
    if has_job_id and len(row) > 3:
        meta["job_id"] = row[3]
    return meta


def _job_id_by_description(conn, tour_name: str) -> Optional[str]:
    """Find a tour_generate/tour_cache_hit ledger row whose description mentions
    the tour name, and return its job_id. Best-effort link when no job_id column
    exists on audio_tours."""
    if not tour_name:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT job_id FROM cost_ledger
                WHERE operation_type IN ('tour_generate', 'tour_cache_hit')
                  AND description ILIKE %s
                  AND job_id IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (f"%{tour_name}%",),
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:
        return None


def _translation_rows_for_tour(conn, audio_tour_id):
    """[LOCAL-609] Translation + translation-TTS ledger rows for a source tour.

    A translation runs as its OWN job, so its rows are not on the tour's job_id.
    They are linked by breakdown->source_tour_id. Returns [] when none / no id.
    """
    if audio_tour_id is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT operation_type, our_cost_usd, cache_hit, job_id, breakdown,
                       description, created_at
                FROM cost_ledger
                WHERE operation_type IN ('translation_generate', 'translation_cache_hit', 'tts_generate')
                  AND breakdown ->> 'source_tour_id' = %s
                ORDER BY created_at ASC
                """,
                (str(audio_tour_id),),
            )
            return [_row_dict(r) for r in cur.fetchall()]
    except Exception:
        return []


# ─── Formatting ──────────────────────────────────────────────────────────────
def _usd(x) -> str:
    return f"${float(x or 0.0):.6f}"


def _provider_rows(breakdown: dict):
    """Yield (provider_label, usd, units_str) for the 7 provider keys present in a
    tour row's breakdown. Tolerates the legacy 4-key shape (llm/grounding/search/
    tts) by mapping it onto the provider labels."""
    b = breakdown or {}

    def _num(d, *keys):
        for k in keys:
            if isinstance(d, dict) and k in d and d[k] is not None:
                return d[k]
        return None

    # New 7-key shape?
    if any(k in b for k in ("openai", "gemini_grounding", "gemini_tokens",
                            "serper", "preflight", "tts")):
        oa = b.get("openai", {}) or {}
        yield ("OpenAI", _num(oa, "usd") or 0.0,
               f"{_num(oa, 'input_tokens') or 0}+{_num(oa, 'output_tokens') or 0} tok, "
               f"{_num(oa, 'calls') or 0} calls")
        gg = b.get("gemini_grounding", {}) or {}
        yield ("Gemini grounding", _num(gg, "usd") or 0.0,
               f"{_num(gg, 'queries') or 0} queries, {_num(gg, 'requests') or 0} req")
        gt = b.get("gemini_tokens", {}) or {}
        yield ("Gemini Flash tokens", _num(gt, "usd") or 0.0,
               f"{_num(gt, 'input_tokens') or 0}+{_num(gt, 'output_tokens') or 0} tok, "
               f"{_num(gt, 'calls') or 0} calls")
        sp = b.get("serper", {}) or {}
        yield ("Serper", _num(sp, "usd") or 0.0, f"{_num(sp, 'queries') or 0} queries")
        pf = b.get("preflight", {}) or {}
        _pf_calls = _num(pf, "calls") or 0
        _pf_units = (f"{_num(pf, 'queries') or 0} queries, "
                     f"{_num(pf, 'input_tokens') or 0}+{_num(pf, 'output_tokens') or 0} tok"
                     if _pf_calls else "did not run")
        yield ("Preflight", _num(pf, "usd") or 0.0, _pf_units)
        tts = b.get("tts", {}) or {}
        _eng = _num(tts, "engine") or "—"
        yield ("TTS", _num(tts, "usd") or 0.0,
               f"{_eng}, {_num(tts, 'characters') or 0} chars, {_num(tts, 'calls') or 0} calls")
        return

    # Legacy 4-key shape fallback.
    yield ("OpenAI", b.get("llm", 0.0) or 0.0, "—")
    yield ("Gemini grounding", b.get("grounding", 0.0) or 0.0, "—")
    yield ("Serper", b.get("search", 0.0) or 0.0, "—")
    yield ("TTS", b.get("tts", 0.0) or 0.0, "—")


def _translation_rows(breakdown: dict):
    """Yield (label, usd, units) for a translation row's breakdown."""
    b = breakdown or {}
    if "translation" in b and isinstance(b["translation"], dict):
        t = b["translation"]
        yield ("Translation (AWS Translate+Polly)", t.get("usd", 0.0) or 0.0,
               f"{t.get('engine', '—')}, {t.get('characters', t.get('source_chars', 0))} chars")
        return
    # Legacy translation breakdown keys.
    if "translate_and_tts" in b:
        yield ("Translation (AWS Translate+Polly)", b.get("translate_and_tts", 0.0) or 0.0,
               f"{b.get('source_chars', 0)} source chars, "
               f"{b.get('translation_passes', 1)} pass(es)")
    elif "translate" in b or "tts" in b:
        yield ("Translation", (b.get("translate", 0.0) or 0.0) + (b.get("tts", 0.0) or 0.0),
               "cache hit" if (b.get("translate", 0) == 0 and b.get("tts", 0) == 0) else "")


def _fmt_duration(seconds: float) -> str:
    if seconds is None:
        return "—"
    seconds = int(round(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


# ─── Report ──────────────────────────────────────────────────────────────────
def build_report(rows, meta=None, extra_translation_rows=None) -> str:
    """Render the report text from the ledger rows (and optional audio_tour meta).

    Pure w.r.t. the rows — no DB — so it is unit-testable. ``rows`` is the list of
    cost_ledger row dicts for one job (as returned by _rows_for_job).
    ``extra_translation_rows`` are translation/tts rows of this tour that live on
    their own job (linked by source_tour_id) — [LOCAL-609] merged into the
    translation section so the report covers any translation of the tour."""
    meta = meta or {}
    extra_translation_rows = extra_translation_rows or []
    lines = []
    W = 64
    lines.append("=" * W)
    lines.append("LOCAL-609 — Per-tour cost breakdown by provider")
    if meta.get("tour_name"):
        lines.append(f"Tour:      {meta['tour_name']}")
    if meta.get("audio_tour_id") is not None:
        lines.append(f"audio_tour_id: {meta['audio_tour_id']}")
    if rows:
        lines.append(f"job_id:    {rows[0]['job_id']}")
    lines.append("=" * W)

    if not rows and not extra_translation_rows:
        lines.append("")
        lines.append("No cost_ledger rows found for this tour / job.")
        lines.append("(Nothing was metered under this id, or the id is wrong.)")
        lines.append("=" * W)
        return "\n".join(lines)

    # The tour-generation row (fresh, cache hit, or pool/by-reference delivery).
    tour_rows = [r for r in rows if r["operation_type"] in ("tour_generate", "tour_cache_hit")]
    translation_rows = [r for r in rows
                        if r["operation_type"] in ("translation_generate", "translation_cache_hit")]
    tts_rows = [r for r in rows if r["operation_type"] in ("tts_generate", "tts_cache_hit")]
    other_rows = [r for r in rows if r not in tour_rows and r not in translation_rows
                  and r not in tts_rows]
    # [LOCAL-609] fold in translation/tts rows that live on their own job.
    _seen = {(r["job_id"], r["operation_type"], r["created_at"]) for r in rows}
    for xr in extra_translation_rows:
        _key = (xr["job_id"], xr["operation_type"], xr["created_at"])
        if _key in _seen:
            continue
        if xr["operation_type"] in ("tts_generate", "tts_cache_hit"):
            tts_rows.append(xr)
        else:
            translation_rows.append(xr)

    delivery_total = 0.0
    reused_research_total = 0.0

    for tr in tour_rows:
        bd = tr["breakdown"]
        _kind = "CACHE HIT" if tr["cache_hit"] else "FRESH"
        if bd.get("pool_reuse"):
            _kind = "POOL REUSE"
        if bd.get("by_reference"):
            _kind = "BY-REFERENCE"
        lines.append("")
        lines.append(f"DELIVERY ({tr['operation_type']}, {_kind})")
        lines.append("-" * W)
        lines.append(f"{'Provider':<24}{'Cost':>14}  {'Units'}")
        lines.append("-" * W)
        _row_sum = 0.0
        for label, usd, units in _provider_rows(bd):
            _row_sum += float(usd or 0.0)
            lines.append(f"{label:<24}{_usd(usd):>14}  {units}")
        lines.append("-" * W)
        lines.append(f"{'Delivery total':<24}{_usd(tr['our_cost_usd']):>14}")
        delivery_total += float(tr["our_cost_usd"] or 0.0)
        _rr = bd.get("research_cost_reused")
        if _rr is not None:
            reused_research_total += float(_rr or 0.0)
            lines.append(f"{'Reused research':<24}{_usd(_rr):>14}  "
                         f"(reused {bd.get('reused_stops', 0)} pooled stop(s))")
        if bd.get("new_stops") is not None or bd.get("reused_stops") is not None:
            lines.append(f"{'Composition':<24}{'':>14}  "
                         f"new={bd.get('new_stops', 0)}, reused={bd.get('reused_stops', 0)}")

    # Translation rows (if any translation of this tour was metered on the same job).
    for xr in translation_rows:
        lines.append("")
        _kind = "CACHE HIT" if xr["cache_hit"] else "FRESH"
        lines.append(f"TRANSLATION ({xr['operation_type']}, {_kind})")
        lines.append("-" * W)
        for label, usd, units in _translation_rows(xr["breakdown"]):
            lines.append(f"{label:<24}{_usd(usd):>14}  {units}")
        lines.append(f"{'Translation total':<24}{_usd(xr['our_cost_usd']):>14}")
        delivery_total += float(xr["our_cost_usd"] or 0.0)

    # Translation TTS rows (per-stop audio of a translation).
    if tts_rows:
        lines.append("")
        lines.append("TRANSLATION TTS (per-stop audio)")
        lines.append("-" * W)
        _tts_total = 0.0
        _tts_chars = 0
        _tts_engine = ""
        for tr in tts_rows:
            b = tr["breakdown"] or {}
            _tts_total += float(tr["our_cost_usd"] or 0.0)
            _tts_chars += int(b.get("chars", 0) or 0)
            _tts_engine = b.get("engine", _tts_engine) or _tts_engine
        lines.append(f"{'TTS (Polly)':<24}{_usd(_tts_total):>14}  "
                     f"{_tts_engine or '—'}, {_tts_chars} chars, {len(tts_rows)} stop(s)")
        delivery_total += _tts_total

    # Any other metered ops on this job (spine, tts, etc.) — list them plainly.
    for orow in other_rows:
        lines.append("")
        lines.append(f"OTHER ({orow['operation_type']}): {_usd(orow['our_cost_usd'])}")
        delivery_total += float(orow["our_cost_usd"] or 0.0)

    # Wall time: orchestrator start → completed. Best proxy from the data we have:
    # the span of this job's ledger rows; prefer audio_tours.created_at as start
    # when present.
    wall = None
    try:
        times = [r["created_at"] for r in rows if r["created_at"] is not None]
        if times:
            start = min(times)
            if meta.get("created_at") is not None:
                start = min(start, meta["created_at"])
            wall = (max(times) - start).total_seconds()
    except Exception:
        wall = None

    lines.append("")
    lines.append("=" * W)
    lines.append(f"{'DELIVERY TOTAL (all rows this job)':<40}{_usd(delivery_total):>24}")
    lines.append(f"{'REUSED-RESEARCH TOTAL':<40}{_usd(reused_research_total):>24}")
    lines.append(f"{'WALL TIME (ledger span)':<40}{_fmt_duration(wall):>24}")
    lines.append("=" * W)
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="LOCAL-609 per-tour cost breakdown by provider.")
    parser.add_argument("id", help="audio_tour_id (integer) or job_id")
    args = parser.parse_args(argv)

    try:
        conn = _connect()
    except Exception as e:
        print(f"ERROR: could not connect to the database: {e}", file=sys.stderr)
        return 2

    try:
        job_id, meta = _resolve_target(conn, args.id)
        if not job_id:
            print(build_report([], meta))
            return 1
        rows = _rows_for_job(conn, job_id)
        extra = _translation_rows_for_tour(conn, meta.get("audio_tour_id"))
        print(build_report(rows, meta, extra_translation_rows=extra))
        return 0 if (rows or extra) else 1
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
