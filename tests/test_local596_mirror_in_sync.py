"""LEAD (2026-10-06): user-tracking/ is the user-api's build context and cannot import
repo-root modules, so l2_seats.py exists twice. They must stay byte-identical."""
import pathlib, sys
root = pathlib.Path(__file__).resolve().parents[1]
a, b = (root / "l2_seats.py").read_bytes(), (root / "user-tracking" / "l2_seats.py").read_bytes()
if a != b:
    print("FAIL: l2_seats.py and user-tracking/l2_seats.py differ — edit both"); sys.exit(1)
print("PASS: l2_seats.py mirror in sync")
