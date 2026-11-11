# SUBMISSION — LOCAL-894B (bounce of LOCAL-894: "File name too long")

Branch `LOCAL-894-user-list-integrity`, on fc55fa64 (`git merge-base --is-ancestor fc55fa64 HEAD` = 0).
Ledger `LOCAL-894B`: **$0.3367 of $0.45** (one live run, metered; 344 meter rows). No second run.

## Verdict
- **Crash: fixed and proven live.** The job completed with the full 777-char description as `location`. There is no `File name too long` in either log.
- **Header: fixed and proven live.** It reads "Caty Mui Ne Resort to Ta Cu Mountain - Driving Tour" / `Tour-Category: driving`.
- **Aboutness: not proven live.** The live run still shipped one Fansipan sentence. Root cause found, fixed after the run, and tested offline against the run's own evidence (below).
- **Thin Pagoda: partly fixed.** The refill now gets facts (4 sentences, up from 2), but the founding story is still removed by the legend gates. Handing that to LEAD.
- **Pins: 1/8. Not fixed.** Diagnosis below. Handing to LEAD.

## 1. One safe-filename helper (`safe_filename.py`)
- **What it does:**
  - A slug of at most 80 UTF-8 bytes, cut on a character boundary, NFC-normalised (Vietnamese safe).
  - When cut, it ends in an 8-char sha1 of the FULL text. The job id is kept where there was one.
  - A final `safe_name` guard keeps every assembled name ≤ 255 bytes.
  - Short input returns exactly the old shape: `boston_ma_walking_abcdef12.zip`, `Boston__MA_walking_tour_<ts>.txt`, `boston_ma_tour.zip`.
- **Builders replaced** (every path built from location / request / tour_name in a shipped service):
  - Orchestrator zip + extract dir: `tour_zip_names`. For a description, the visible part is the derived short title.
  - Generator service output .txt, and `generate_tour_text.py`'s default output file: `generator_output_filename`.
  - Modernized (TTS/ZIP) `create_modernized_tour_zip`: `<tour_name>_<job8>.zip`, bounded.
  - Map-delivery download name: `download_name`.
- **Translation:** has no path built from text; it uses ids and stored names.
- **Legacy scripts left alone:** `direct_fix.py`, `generate_audio_tour.py`, `modified_*`, `*_map_delivery_service.py` variants. They are not in any Dockerfile or compose file.
- **Downloads read the stored name, not a re-derived one:**
  - `/download` uses `job["output_zip"]` / `job["extract_dir"]`, or the DB row (`tour_{id}.zip`).
  - Modernized `/download` uses `job["output_zip"|"zip_filename"]`.
- `Dockerfile.orchestrator` and `Dockerfile.modernized` COPY the helper. Live, it was checked present in all three images.

## 2. Header matches the category
- `effective_category_894b()`: walking + vehicle → `driving` (likewise biking / road_trip / animal).
- The LOCAL-474 log line now reads `category='driving' template=walking (source=explicit)`.
- `spoken_text_hygiene.enforce_header_mode` rewrites only the FIRST line's mode word. It runs after the 880 intro fix and in the final pass.

## 3. Aboutness on a user stop (why 891 missed it)
- **Why 891 missed it:**
  - 891's `tangent_reason` needs the stop's OWN ARTICLE. User-list stops on this path have only snippets, so it returns early.
  - Worse: the cable-car search returned **another province's cable car**. That made every Fansipan sentence "supported" by the stop's evidence.
- **What I added:**
  - **Sentence rule** `other_place_reason`: the subject is a named place outside the listener's route region, placed "in <other place>". It sits in `clean_stop`. This was live, but the delivered sentence's subject was "It", so the rule did not fire.
  - **Evidence rule** `strip_other_place_evidence` (added AFTER the live run):
    - Evidence that places itself outside the route region and never names a route place phrase (`ham tien`, `mui ne`, `ta cu`, `binh thuan`, `phan thiet`) is dropped in the grounding gate.
    - Sentences naming its proper names (Fansipan Mountain, Sa Pa, Toc Tien) are dropped too.
    - On both runs' bundles (894 and 894B), it drops ONLY the cable-car evidence.
    - Replayed on the live tour: no Fansipan / Sa Pa / Toc Tien, still 8 stops.
- **Route region:** set from the request in `_apply_description_location_894`. A plain place request clears it, so behaviour there is unchanged.

## 4. Thin landmark stops
- **What I added:** `aboutness.snippet_facts`. It gives plain English sentences that name the stop, without ad copy or near-duplicates, for stops with no own article (where `refill_facts` returned []). The gate's 888 refill now uses it.
- **Live result:** the refill ran (Pagoda re-gated, `renarrated=True`), going from 2 sentences to 4.
- **Remaining:** the Tran Huu Duc / Emperor Tu Duc story was removed by `[LOCAL-881] … DROPPED (evidence flags a myth / misattribution)` and `[LOCAL-855B] dropped (folk-tale / legend narrative)`. The evidence calls it "a legend of healing". D760 says to disclose a legend, not drop it. That is a policy call for LEAD.
- The delivered Pagoda body also misattributes the Buddha's 49 m to the pagoda.

## Live run (`-p local894b`, ports 26100/26102/26103/55995; job 95387eb5)
| check | result |
|---|---|
| job status | **completed** (573 s) |
| 8 stops, user order, user titles | PASS |
| no ghost stop / announcement | PASS |
| location/scope | PASS: 'Ham Tien, Mui Ne' / 'Binh Thuan province', through=['Phan Thiet'] |
| driving register | PASS |
| stored `tour_name` | `Caty Mui Ne Resort to Ta Cu Mountain - Driving Tour` (51 chars) |
| header line | `Caty Mui Ne Resort to Ta Cu Mountain - Driving Tour` + `Tour-Category: driving`. **PASS** (no "walking tour") |
| no "File name too long" | PASS |
| pins | **1/8** (`[D762] user-stop pins resolved 1/8 (city Phan Thiet)`). **FAIL** |
| per-stop sentences | 3 · 5 · 6 · 2 · 8 · 4 · 5 · 6 |
| no off-region sentence | **FAIL live** (1 Fansipan sentence in stop 5). Fixed offline after the run (§3) |
| audit unsupported | **4**, all in stop 5. All four come from the other-province evidence |
| meter total | **$0.3367** |

- **Pins, diagnosis:**
  - The D762 preview used city "Phan Thiet". The Ta Cu stops are about 30 km away, in Ham Thuan Nam.
  - The generator's 858B lookups returned "no in-scope authority" for 7 stops. Two of those stops name no place, by design.
  - Then 858B cluster-collapse cleared the model pins.
  - LEAD's 8/8 was on the merge with subscribed fc31ad75; this branch alone gives 1/8.
- **Stop 4 (Ta Cu):** only 2 sentences.
- **What my post-run fix does not cover:** in the offline replay, "ticket office … 6:00 a.m." (also the other cable car's) still survives. It names no place and the factual detector does not flag a clock time.

## Tests (offline)
- `tests/test_local894b_safe_filenames.py`: 39 pass. It covers:
  - 2000-char Vietnamese and English inputs;
  - the 777-char request through the generator service's real save path (`generate_tour_async`), with the job completed and the file written;
  - modernized zip, orchestrator names, ≤ 255 bytes on a real filesystem, short names unchanged;
  - header mode, the Fansipan cases, snippet refill, and evidence-level rejection on both live bundles.
- With 474/880/883–892/894: **322 passed**.

Artifacts: `submission_artifacts/local894b/` (tour.txt, evidence_bundle.json, audit.json). Run and meter logs are not committed.
