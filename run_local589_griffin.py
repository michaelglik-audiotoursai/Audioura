#!/usr/bin/env python3
"""run_local589_griffin.py — LOCAL-589 D6 one-shot live driver (isolated).

Generates ONE Griffin 7-stop tour by calling generate_tour_text directly (no
HTTP service, no port binding), so it can run in an isolated container that never
touches the audioura-* services. Prints a clear banner before/after so the stop
list, the [D536] requested/delivered line, the [LOCAL-589][fetch] log lines and
the [TIMING] TOTAL line are easy to extract from the captured log.

Usage (inside the container):
    python run_local589_griffin.py <run_label>
"""
import sys
import os

LOCATION = "Griffin museum of photography, Winchester, MA"
TOUR_TYPE = "museum"
STOPS = 7


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    out_path = f"/app/tours/local589_griffin_{label}.txt"
    print(f"\n==================== LOCAL-589 LIVE {label} ====================")
    print(f"[driver] location={LOCATION!r} tour_type={TOUR_TYPE!r} stops={STOPS}")
    print(f"[driver] git_sha={open('/app/.git_sha').read().strip() if os.path.exists('/app/.git_sha') else '?'}")

    import generate_tour_text as g

    tour_text, output_file, _coords = g.generate_tour_text(
        LOCATION, TOUR_TYPE, out_path, STOPS)

    print(f"\n-------------------- LOCAL-589 RESULT {label} --------------------")
    notice = getattr(g, "_LAST_STOP_COUNT_NOTICE", {}) or {}
    kind = getattr(g, "_LAST_TOUR_KIND", "full")
    print(f"[driver] tour_kind={kind}")
    print(f"[driver] stop_count_notice={notice}")

    # Parse the delivered stop list from the output file's "Stop N:" headers.
    stops = []
    if output_file and os.path.exists(output_file):
        import re
        with open(output_file, encoding="utf-8") as fh:
            text = fh.read()
        for m in re.finditer(r'^\s*Stop\s+(\d+)\s*[:\-]\s*(.+)$', text, re.MULTILINE):
            stops.append((int(m.group(1)), m.group(2).strip()))
    print(f"[driver] DELIVERED STOP LIST ({len(stops)} stop(s)):")
    for n, name in stops:
        print(f"   Stop {n}: {name}")
    if tour_text is None:
        print("[driver] generate_tour_text returned None (clean-fail / overview path)")
        print(f"[driver] clean_fail_evidence={getattr(g, '_LAST_CLEAN_FAIL_EVIDENCE', {})}")
    print(f"==================== LOCAL-589 END {label} ====================\n")


if __name__ == "__main__":
    main()
