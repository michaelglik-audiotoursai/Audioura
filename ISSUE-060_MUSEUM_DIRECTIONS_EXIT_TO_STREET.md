# ISSUE-060: Museum Tours — Directions Tell Visitor to Exit to Street

**Filed**: 2026-05-22  
**Priority**: Low — not blocking any release  
**Affects**: All single-venue museum tours  
**Status**: Backlog (not fixing in current release)

---

## Symptom

In museum tours (e.g. Fairbanks House, Armenian Museum of America), the "directions to next stop"
text instructs the visitor to walk outside to the street — e.g. "Continue on East Street to reach
the next exhibit." This is wrong for a tour that stays entirely inside one building.

Observed in:
- Fairbanks House Tour in Dedham, MA (4 stops) — "continue going on East Street"
- Armenian Museum of America, Watertown, MA (6 stops, RU) — directions reference leaving the museum

---

## Root Cause

PHASE 3B generates walking directions between stops using a generic prompt that has no awareness
of whether the tour is single-venue (indoors). The museum constraint in PHASE 3A keeps the
**stop names** inside the building, but PHASE 3B's direction prompt still generates
street-navigation language because it treats every tour as an outdoor walking tour.

The `tour_category='museum'` and `venue_name` fields are available at PHASE 3B call time
but are not currently injected into the direction-generation prompt.

---

## Positive Note

Stop names and exhibit descriptions are correct — Fairbanks House correctly names
"Master Bedroom Gallery" etc. Only the *directions between stops* are wrong.

---

## Proposed Fix (deferred)

When `tour_category == 'museum'` and `venue_name` is not null, inject into the PHASE 3B prompt:

> "This tour takes place entirely inside {venue_name}. All directions between stops must
> describe movement within the building only (e.g. 'proceed to the next gallery',
> 'walk through the doorway to your left'). Do NOT reference streets, exits, or outdoor navigation."

This is a prompt-only change in `generate_tour_text.py` PHASE 3B — no structural changes needed.

---

## Notes

- This issue has likely always existed (pre-dates all sessions). Not a regression.
- Fix is low-risk (prompt injection only) but deferred until after Tours_Step_Maps merge.
- File under "Category-aware PHASE 5 prompts" architectural item in REMINDER_LIST_BEFORE_PRODUCTION.md.
