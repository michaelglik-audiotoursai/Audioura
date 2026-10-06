#!/usr/bin/env python3
"""run_local585_live.py — LOCAL-585 isolated live run (Griffin + Athenaeum).

Runs INSIDE a disposable container (see run_local585_live.sh) so it never touches
the audioura-* services. Drives the REAL generation path (generate_tour_text) for
the two field cases and AUDITS the LOCAL-585 contract from the delivered text:

  CASE GRIFFIN  "Griffin museum of photography, Winchester, MA"  (museum, 7 stops)
      → Stop 1 is an "About <Griffin>" STORY stop: the founder (Arthur Griffin),
        the founding (est. 1992 / 1987), non-profit — NEVER framed as an artwork
        ("consists of a series of frames", "this work", "oil on canvas").
      → Stops 2..N are current exhibitions.

  CASE ATHENAEUM  "Art and Architectual tour in Boston Athenaeum, boston, ma"  (5)
      → Stop 1 is an "About <Boston Athenaeum>" stop that ALSO covers the building
        / architecture (the request names architecture), sourced.

OpenAI hard cap $2.00 (ticket). Tour cache OFF so the new code runs. audio_tours
is only COUNTED, never written or deleted (generate_tour_text does not insert tour
rows). Prints, per case: tour_kind, delivered stop list, the Stop-1 audit
(is-About? is-non-artwork? covers-architecture?), and the generation cost.
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["STORIED_MODE"] = "true"
os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ.setdefault("TOUR_LLM_MODEL", "gpt-4o")
os.environ["COST_HARD_LIMIT_USD"] = "2.00"   # OpenAI hard cap $2 (ticket)

import about_museum_stop as am
import generate_tour_text as g
from generate_tour_text import generate_tour_text


def _audio_tours_count():
    try:
        import psycopg2
        url = os.environ.get("DATABASE_URL") or (
            f"postgresql://{os.environ.get('DB_USER','admin')}:"
            f"{os.environ.get('DB_PASSWORD','password123')}@"
            f"{os.environ.get('DB_HOST','localhost')}:{os.environ.get('DB_PORT','5432')}/"
            f"{os.environ.get('DB_NAME','audiotours')}")
        c = psycopg2.connect(url, connect_timeout=5)
        cur = c.cursor(); cur.execute("SELECT COUNT(*) FROM audio_tours")
        n = cur.fetchone()[0]; cur.close(); c.close()
        return n
    except Exception as e:
        return f"(count unavailable: {type(e).__name__}: {e})"


def _parse_stops(text):
    stops = []
    headers = list(re.finditer(r"(?mi)^\s*Stop\s+(\d+)\s*[:\-]\s*(.+?)\s*$", text))
    for i, m in enumerate(headers):
        name = m.group(2).strip()
        seg = text[m.end(): headers[i + 1].start() if i + 1 < len(headers) else len(text)]
        stops.append((name, seg))
    return stops


def run_case(tag, location, tour_type, stops, expect_architecture):
    out = os.path.join("/app/tours", f"LOCAL585_{tag}.txt")
    print(f"\n{'='*72}\nCASE {tag}: {location!r}  ({stops} stops requested)\n{'='*72}")
    before = _audio_tours_count()
    t0 = time.time()
    text, out_file, _coords = generate_tour_text(location, tour_type, out, stops)
    elapsed = time.time() - t0
    after = _audio_tours_count()

    kind = getattr(g, "_LAST_TOUR_KIND", None)
    cost = getattr(g, "_LAST_GENERATION_COST", {}) or {}
    bd = cost.get("breakdown", {}) or {}
    print(f"\n--- CASE {tag} RESULT ({elapsed:.1f}s) ---")
    print(f"tour_kind              : {kind}")
    print(f"generation cost        : total={cost.get('total_cost')} "
          f"about_stops={bd.get('about_stops')} reused={bd.get('reused_stops')} "
          f"new={bd.get('new_stops')}")
    print(f"audio_tours BEFORE/AFTER (never DELETE): {before} / {after}")

    if not text:
        print(f"CASE {tag}: NO TEXT — clean fail. evidence="
              f"{getattr(g, '_LAST_CLEAN_FAIL_EVIDENCE', {})}")
        return {"tag": tag, "ok": False}

    parsed = _parse_stops(text)
    print(f"CASE {tag}: delivered {len(parsed)} stop(s):")
    for n, (name, _seg) in enumerate(parsed, 1):
        print(f"   Stop {n}: {name[:70]}")

    # ── Stop-1 audit (the LOCAL-585 contract) ──
    stop1_name, stop1_body = parsed[0] if parsed else ("", "")
    is_about = stop1_name.lower().startswith("about ")
    stop1_full = f"{stop1_name}\n{stop1_body}"
    non_artwork = not am.looks_like_artwork_framing(stop1_full)
    low = stop1_full.lower()
    has_founder_or_history = bool(re.search(
        r"found|establish|est\.?\s*\d{4}|since\s+\d{4}|non-?profit|history|mission|designed", low))
    covers_arch = bool(re.search(
        r"architect|building|designed|style|facade|fa\u00e7ade|granite|revival|neoclassical", low))

    print(f"\nCASE {tag} STOP-1 AUDIT:")
    print(f"   is 'About <museum>' stop      : {is_about}  ({stop1_name!r})")
    print(f"   NOT framed as an artwork      : {non_artwork}")
    print(f"   carries founder/history/mission: {has_founder_or_history}")
    if expect_architecture:
        print(f"   covers architecture/building  : {covers_arch}")
    # Hard guard: the About stop must NEVER contain the exact tour-391 phrase.
    leaked = "consists of a series of frames" in text.lower()
    print(f"   NO 'consists of a series of frames' anywhere: {not leaked}")

    return {
        "tag": tag, "ok": True, "n": len(parsed), "kind": kind,
        "stop1": stop1_name, "is_about": is_about, "non_artwork": non_artwork,
        "has_history": has_founder_or_history,
        "covers_arch": covers_arch if expect_architecture else None,
        "no_frames_leak": not leaked,
        "total_cost": cost.get("total_cost"),
    }


def main():
    print("=== LOCAL-585 ISOLATED LIVE RUN ===")
    print(f"model={os.environ['TOUR_LLM_MODEL']} cap=${os.environ['COST_HARD_LIMIT_USD']} "
          f"cache=OFF storied={os.environ['STORIED_MODE']}")
    git_sha = open("/app/.git_sha").read().strip() if os.path.exists("/app/.git_sha") else "?"
    print(f"git_sha={git_sha}")

    results = []
    results.append(run_case(
        "GRIFFIN", "Griffin museum of photography, Winchester, MA", "museum", 7,
        expect_architecture=False))
    results.append(run_case(
        "ATHENAEUM", "Art and Architectual tour in Boston Athenaeum, boston, ma", "", 5,
        expect_architecture=True))

    print(f"\n{'#'*72}\nLOCAL-585 SUMMARY\n{'#'*72}")
    for r in results:
        print(f"  {r}")


if __name__ == "__main__":
    main()
