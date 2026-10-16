"""[GCS-C1] A tour with no usable coordinates must never be stored silently.

WHY THIS EXISTS
`tours-near` filters on audio_tours.lat/lng. A row with NULL coordinates, or with
0,0, can never be returned to any listener -- while the app is told the tour
generated successfully. Two holes produced exactly that, both observed on live
Preview job 36b13113 on 2026-10-16 (ClickUp wdvrdaz109):

    19:13:02  ==== COORDINATES CHECK IN ORCHESTRATE_TOUR_ASYNC ====
    19:13:02  Coordinates from modernized service: [None, None]

and no "No coordinates received" line after it. `[None, None]` is a list of
length 2, so the old guard

    if not coordinates or not isinstance(coordinates, list) or len(coordinates) < 2:

was False, the fallback never ran, and the row was written with NULL lat/lng.

The second hole: every failure branch of get_coordinates_direct() returns
(0, 0) and that was stored verbatim. 0,0 is in the Gulf of Guinea.

THE RED TEST
test_old_guard_let_none_none_through reproduces the ORIGINAL predicate and
asserts it accepted [None, None]. If someone ever reverts to a length check,
that test still passes while the others fail -- which is the point: it pins the
defect, not the fix.

Run: python tests/test_gcs_c1_coordinate_guard.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tour_orchestrator_service import _usable_coordinates as orch_guard
from tour_worker_service import _usable_coordinates as worker_guard

FAILURES = []


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {label}")


def old_guard_accepts(coordinates):
    """The predicate as it stood before GCS-C1. True == 'these are fine'."""
    return not (not coordinates
                or not isinstance(coordinates, list)
                or len(coordinates) < 2)


def test_old_guard_let_none_none_through():
    print("[RED] the original guard accepted the value that broke production")
    check("old guard accepts [None, None]", old_guard_accepts([None, None]), True)
    check("old guard accepts [0, 0]", old_guard_accepts([0, 0]), True)
    # ...and it was right about the genuinely good case, which is why it survived.
    check("old guard accepts [42.36, -71.05]",
          old_guard_accepts([42.36, -71.05]), True)


def test_rejects_the_production_failure():
    print("[GREEN] the new guard rejects both silent-failure shapes")
    for name, guard in (("orchestrator", orch_guard), ("worker", worker_guard)):
        check(f"{name}: [None, None]", guard([None, None]), False)
        check(f"{name}: [0, 0]", guard([0, 0]), False)
        check(f"{name}: [0.0, 0.0]", guard([0.0, 0.0]), False)


def test_rejects_other_junk():
    print("[GREEN] other unusable shapes")
    for name, guard in (("orchestrator", orch_guard), ("worker", worker_guard)):
        check(f"{name}: None", guard(None), False)
        check(f"{name}: []", guard([]), False)
        check(f"{name}: [42.36]", guard([42.36]), False)
        check(f"{name}: ['42.36', '-71.05'] strings", guard(['42.36', '-71.05']), False)
        check(f"{name}: [nan, nan]", guard([float('nan')] * 2), False)
        check(f"{name}: [inf, 0]", guard([float('inf'), 0.0]), False)
        check(f"{name}: [True, True] bools", guard([True, True]), False)
        check(f"{name}: out of range lat 91", guard([91.0, 0.5]), False)
        check(f"{name}: out of range lng -181", guard([42.0, -181.0]), False)


def test_accepts_real_coordinates():
    print("[GREEN] real coordinates still pass -- no false positives")
    for name, guard in (("orchestrator", orch_guard), ("worker", worker_guard)):
        # Fenway Park and Faneuil Hall, from the live runs on 2026-10-16.
        check(f"{name}: Fenway [42.3489, -71.0943]",
              guard([42.3489, -71.0943]), True)
        check(f"{name}: Faneuil [42.3634, -71.0538]",
              guard([42.3634, -71.0538]), True)
        # Nominatim hands back a tuple, not a list.
        check(f"{name}: tuple (43.6976, 7.2769)", guard((43.6976, 7.2769)), True)
        # Null Island is rejected, but a point ON the equator or prime meridian
        # alone is legitimate and must survive.
        check(f"{name}: equator [0.0, 32.58]", guard([0.0, 32.58]), True)
        check(f"{name}: prime meridian [51.48, 0.0]", guard([51.48, 0.0]), True)
        # Integers are valid coordinates.
        check(f"{name}: ints [42, -71]", guard([42, -71]), True)


if __name__ == '__main__':
    test_old_guard_let_none_none_through()
    test_rejects_the_production_failure()
    test_rejects_other_junk()
    test_accepts_real_coordinates()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  {f}")
        sys.exit(1)
    print("ALL TESTS PASSED")
