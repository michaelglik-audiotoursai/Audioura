# SUBMISSION — LOCAL-882 (completed by LEAD)

Kiro worked for 2 h 35 min, made the changes below and ran the parity proofs, but committed nothing. It sat idle past the 2.5 h cap (the watchdog did not fire). LEAD killed it at 10:1x and is committing its work as found, reviewed and tested.

## What is in it
- `run_cloud_parity_proof.py` + `docker-compose.local882-proof.yml`: the cloud-parity proof (D770). Michael's SHORT stop names and pins go through the itinerary import. It runs a seed run with the previous commit, a cold run and a warm run on one disposable DB.
- `landmark_wikipedia_evidence.py`: `RULES_VERSION` stamped on every cache row. A cache hit is re-validated with `_revalidate_payload` (the current `_pick`, geo and name rules), so an old-rule hit (the Gia Long Palace article for City Hall) no longer bypasses the gates. No DELETE.
- `venue_canonical_resolver.py` + `itinerary_import.py`: a short user name plus its pin resolve to the canonical venue (Wikidata within 300 m, then Places). The canonical en/local labels become `match_name` and aliases; the user's wording stays the spoken title.
- `generate_tour_text.py`, `user_stop_narration.py`: wiring for the above, and for an event at the landmark's own site.
- tests: `tests/test_local882_*` (16), plus the `test_local867` update. 158 related tests pass.

## Live (warm run, short names), spend $0.277 of $0.60
- PASS:
  - City Hall is the Hôtel de Ville (Gardès, completed 1908), not the Gia Long Palace;
  - the Palace has the 30 April 1975 tank;
  - no "inside the palace", no Pier "19th century", no current-affairs note;
  - Post Office: Vildieu + Foulhoux.
- STILL WRONG (→ LOCAL-882B):
  - City Hall "opened in 1909 as a hotel named Hotel de Ville … this hotel became a gathering place". This mistranslates "hôtel de ville" (town hall).
  - Opera House: "Designed by … Olivier to seat guests" is an orphan quantity, and "home to both the Lower House and the Senate" needs its source.

Texts: `submission_artifacts/local882/` (seed, cold, warm, warm_final).
