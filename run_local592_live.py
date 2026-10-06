#!/usr/bin/env python3
"""run_local592_live.py — LOCAL-592 isolated live run (Athenaeum + Griffin).

Runs INSIDE a disposable container (see run_local592_live.sh) so it never touches
the audioura-* services. Drives the REAL generation path (generate_tour_text) for
the two field cases and AUDITS the LOCAL-592 contract from the delivered text:

  Michael's rule (2026-10-06, binding): a request for N stops delivers EXACTLY N
  stops. The museum "About" content and the practical facts (opening hours,
  admission, closed days) are the OPENING SECTION of Stop 1 — like the walking-tour
  Overall section — never a standalone "About <museum>" stop.

  CASE ATHENAEUM  "Art and Architectual tour in Boston Athenaeum, boston, ma" (5)
      → EXACTLY 5 stops; Stop 1 opens with the About + building/architecture +
        practical facts, then the first artwork's own narration. No stop titled
        "About …".
  CASE GRIFFIN    "Griffin museum of photography, Winchester, MA"  (museum, 7)
      → EXACTLY 7 stops; Stop 1 opens with the About (Arthur Griffin, est. 1992,
        non-profit) + practical facts, then the first exhibition. No "About …" stop.

OpenAI hard cap $1.00 (well under the $2 ticket cap). Tour cache OFF so the new
code runs. audio_tours is only COUNTED, never written or deleted.
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
os.environ["COST_HARD_LIMIT_USD"] = "1.00"   # OpenAI hard cap $1 (< $2 ticket cap)

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
    out = os.path.join("/app/tours", f"LOCAL592_{tag}.txt")
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
    print(f"\nCASE {tag}: delivered {len(parsed)} stop(s) (requested {stops}):")
    for n, (name, _seg) in enumerate(parsed, 1):
        print(f"   Stop {n}: {name[:70]}")

    # ── LOCAL-592 contract audit ──
    exactly_n = (len(parsed) == stops)
    any_about_stop = any(name.lower().startswith("about ") for name, _ in parsed)
    stop1_name, stop1_body = parsed[0] if parsed else ("", "")
    stop1_full = f"{stop1_name}\n{stop1_body}"
    low = stop1_full.lower()
    non_artwork = not am.looks_like_artwork_framing(stop1_full)
    has_about_content = bool(re.search(
        r"found|establish|est\.?\s*\d{4}|since\s+\d{4}|non-?profit|history|mission|designed", low))
    has_practical = bool(re.search(
        r"\b(open|hours?|admission|closed|free|\$\d|\d+\s*(?:am|pm)|noon)\b", low))
    covers_arch = bool(re.search(
        r"architect|building|designed|style|facade|fa\u00e7ade|granite|revival|neoclassical", low))

    print(f"\nCASE {tag} LOCAL-592 AUDIT:")
    print(f"   EXACTLY N stops ({stops})             : {exactly_n}  (delivered {len(parsed)})")
    print(f"   NO stop titled 'About …'              : {not any_about_stop}")
    print(f"   Stop 1 carries About content          : {has_about_content}")
    print(f"   Stop 1 carries practical facts        : {has_practical}")
    print(f"   Stop 1 NOT framed as an artwork        : {non_artwork}")
    if expect_architecture:
        print(f"   Stop 1 covers architecture/building   : {covers_arch}")

    print(f"\nCASE {tag} STOP 1 — FIRST 15 LINES >>>>>>>>>>")
    stop1_render = (f"Stop 1: {stop1_name}\n" + stop1_body.strip())
    for ln in stop1_render.splitlines()[:15]:
        print(ln)
    print(f"<<<<<<<<<< CASE {tag} STOP 1 END")

    # ── [r4] VISITING SENTENCES: the spoken hours+admission with the day range
    # bound and the source + month signal. Pull the sentence(s) that state the
    # venue being open / closed / admission so the LEAD can read them directly.
    visiting = _extract_visiting_sentences(stop1_full)
    print(f"\nCASE {tag} r4 VISITING SENTENCES >>>>>>>>>>")
    print(visiting or "(none found in Stop 1)")
    print(f"<<<<<<<<<< CASE {tag} VISITING END")

    # r4 audits: the day range must travel WITH the hours; the source+month signal
    # must be present when any facts are stated.
    low_v = (visiting or "").lower()
    states_hours = bool(re.search(r"\bis open\b|\bopens\b|\bclosed\b", low_v))
    day_bound = bool(re.search(
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|daily)", low_v))
    has_time = bool(re.search(r"\d\s*(?:am|pm)|noon|midnight", low_v))
    source_month = bool(re.search(r"as listed on .+ in [a-z]+ \d{4}", low_v))
    reads_as_note = "a few practical notes" in low
    print(f"\nCASE {tag} r4 AUDIT:")
    print(f"   visiting reads as a sentence (is open/closed) : {states_hours}")
    print(f"   day range bound to the hours                  : {day_bound if has_time else 'n/a (no times)'}")
    print(f"   source + month honesty signal present         : {source_month}")
    print(f"   r3 note lead GONE ('a few practical notes')   : {not reads_as_note}")

    return {
        "tag": tag, "ok": True, "n": len(parsed), "requested": stops,
        "exactly_n": exactly_n, "no_about_stop": not any_about_stop,
        "has_about_content": has_about_content, "has_practical": has_practical,
        "non_artwork": non_artwork,
        "covers_arch": covers_arch if expect_architecture else None,
        "visiting": visiting,
        "r4_states_hours": states_hours,
        "r4_day_bound": (day_bound if has_time else None),
        "r4_source_month": source_month,
        "r4_no_note_lead": not reads_as_note,
        "total_cost": cost.get("total_cost"),
    }


def _extract_visiting_sentences(stop1_full: str) -> str:
    """Return the spoken visiting sentence(s) from Stop 1 — the ones that state the
    venue's hours/closed-day/admission (r4). Matches the composer's voice ('… is
    open …', 'Admission is …', 'Check … before you go', '… are listed on …')."""
    sents = re.split(r"(?<=[.!?])\s+", stop1_full)
    keep = []
    for s in sents:
        sl = s.lower().strip()
        # Anchor on the composer's visiting voice. 'opens' alone is too loose (an
        # exhibition sentence may say 'it opens a window…'), so require the venue
        # being open on a day/time, a closed-day clause, an admission clause, or a
        # website pointer.
        if (re.search(r"\bis open\b", sl)
                or re.search(r"\bclosed on\b", sl)
                or re.search(r"\badmission is\b", sl)
                or re.search(r"admission prices? (?:are|is) listed", sl)
                or re.search(r"opening hours (?:are|is) listed", sl)
                or re.search(r"check (?:opening )?hours|check opening hours and admission", sl)
                or re.search(r"\bas listed on\b.+\bin [a-z]+ \d{4}", sl)):
            keep.append(s.strip())
    return " ".join(keep).strip()


def main():
    print("=== LOCAL-592 ISOLATED LIVE RUN ===")
    print(f"model={os.environ['TOUR_LLM_MODEL']} cap=${os.environ['COST_HARD_LIMIT_USD']} "
          f"cache=OFF storied={os.environ['STORIED_MODE']}")
    git_sha = open("/app/.git_sha").read().strip() if os.path.exists("/app/.git_sha") else "?"
    print(f"git_sha={git_sha}")

    results = []
    results.append(run_case(
        "ATHENAEUM", "Art and Architectual tour in Boston Athenaeum, boston, ma", "", 5,
        expect_architecture=True))
    results.append(run_case(
        "GRIFFIN", "Griffin museum of photography, Winchester, MA", "museum", 7,
        expect_architecture=False))

    print(f"\n{'#'*72}\nLOCAL-592 SUMMARY\n{'#'*72}")
    for r in results:
        print(f"  {r}")


if __name__ == "__main__":
    main()
