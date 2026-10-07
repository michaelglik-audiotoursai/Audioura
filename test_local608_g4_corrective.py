#!/usr/bin/env python3
"""test_local608_g4_corrective.py — LOCAL-608 item 3 / G4 corrective action.

Backports two stacked subscribed commits:

  * ba5afb9 (D611 x G4): Stop 1's sourced opening section (About + visiting facts)
    counts as elements a prolog claim may trace to. The orientation legitimately
    restates it ("from Devlin Hall to Brighton"); on 354da34 G4 failed those true,
    sourced claims on every McMullen reuse.
  * 2649a3e: run_qa exposes content_qa_runner.G4_UNGROUNDED_SENTENCES — the full
    text of each ungrounded prolog/epilog sentence — so the service can remove just
    those sentences and re-check (corrective action) instead of discarding the tour,
    and write the corrected text back to the delivered file.

RED on 354da34:
  * the Devlin-Hall prolog claim FAILS G4 (opening section not counted as an element);
  * content_qa_runner.G4_UNGROUNDED_SENTENCES does not exist.
GREEN after the port.

The content_qa_runner side (which drives the corrective loop and write-back in
generate_tour_text_service) is tested here; the service wiring is additionally
exercised by the live container run.

Run: python3 -m pytest test_local608_g4_corrective.py -q
"""
import os
import io
import sys
import contextlib
import importlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["STORIED_MODE"] = "true"


def _run_qa_capture(tour_text, story_elements):
    import content_qa_runner as cqr
    importlib.reload(cqr)  # fresh module-level counters per call
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            cqr.run_qa(tour_text, story_elements=story_elements)
        except SystemExit:
            pass
    return cqr, buf.getvalue()


# A Stop 1 whose opening section states the fact, and an Orientation (prolog) that
# restates it with a year + causal verb — the exact McMullen "Devlin Hall → Brighton"
# shape that failed G4 on reuse.
_OPENING = ("The McMullen Museum opened in 1960 when the collection moved from "
            "Devlin Hall to its Brighton campus home, a well documented relocation.")
_GROUNDED_TOUR = f"""Audio Guided Tour: McMullen Museum - Museum Tour
Tour-Category: museum
Location: McMullen Museum

Stop 1: McMullen Museum — Overview

{_OPENING}

Orientation: In 1960 the museum opened when the collection moved from Devlin Hall to Brighton, a documented relocation of the McMullen holdings.

This gallery holds the earliest works.

Directions: Continue to the next gallery.

Stop 2: Second Gallery
Address: 2 Beta St
Coordinates: 1,2
Orientation: Welcome.

More works here.

Directions: Done.
"""

# A prolog claim that traces to nothing — a fabricated benefactor and year.
_UNGROUNDED_TOUR = """Audio Guided Tour: Example Museum - Museum Tour
Tour-Category: museum
Location: Example Museum

Stop 1: Example Museum — Overview

Address: 1 Alpha St

Orientation: In 1823 the fictional benefactor Zorblax Quintano founded the entire institution single handedly.

Gallery works here.

Directions: Continue.

Stop 2: Second
Address: 2 Beta St
Coordinates: 1,2
Orientation: Welcome.

More.

Directions: Done.
"""

_UNRELATED_ELEMENTS = [{"text": "An unrelated element about glazing techniques.", "type": "work"}]


def test_g4_ungrounded_sentences_attribute_exists():
    import content_qa_runner as cqr
    assert hasattr(cqr, "G4_UNGROUNDED_SENTENCES"), \
        "content_qa_runner.G4_UNGROUNDED_SENTENCES must exist (2649a3e)"


def test_opening_section_grounds_prolog_claim():
    """ba5afb9: the Stop 1 opening section counts as an element, so the Devlin-Hall
    prolog claim traces and G4 PASSES (it FAILED on 354da34)."""
    cqr, output = _run_qa_capture(_GROUNDED_TOUR, _UNRELATED_ELEMENTS)
    assert "PASS: G4 Prolog/epilog claims trace to story elements" in output, \
        f"Expected G4 PASS (opening section grounds the claim), got:\n{output}"
    assert cqr.G4_UNGROUNDED_SENTENCES == [], \
        f"No ungrounded sentences expected, got {cqr.G4_UNGROUNDED_SENTENCES}"


def test_ungrounded_claim_recorded_verbatim_for_corrective_removal():
    """2649a3e: a genuinely ungrounded prolog claim FAILS G4 and its FULL text is
    recorded in G4_UNGROUNDED_SENTENCES as a verbatim substring of the tour — which
    is exactly what the service's corrective loop removes with tour_text.replace()."""
    cqr, output = _run_qa_capture(_UNGROUNDED_TOUR, _UNRELATED_ELEMENTS)
    assert "FAIL: G4 Prolog/epilog claims trace to story elements" in output, \
        f"Expected G4 FAIL for the fabricated claim, got:\n{output}"
    assert cqr.G4_UNGROUNDED_SENTENCES, "G4_UNGROUNDED_SENTENCES must be populated"
    # Each recorded sentence is a verbatim substring of the tour (service relies on
    # `all(_g4s in tour_text ...)` and tour_text.replace(_g4s, '')).
    for _s in cqr.G4_UNGROUNDED_SENTENCES:
        assert _s in _UNGROUNDED_TOUR, f"recorded sentence not verbatim in tour: {_s!r}"
    assert any("Zorblax" in _s for _s in cqr.G4_UNGROUNDED_SENTENCES)


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-q']))
