##### READY FOR REVIEW

## Commit

```
04b9916 LOCAL-49: Fix tour_content persistence regression in orchestrator
```

Branch: `kiro/local49-persist-tour-content`
Commits ahead of storied: 1

## What changed

### `tour_orchestrator_service.py`

**Root cause:** Commit `2a97ba3` ("M02 Tasks 8+9: HTTP content passing") introduced
`tour_content = status_data.get("tour_content")` at line 612, correctly capturing
tour content from the text generator's HTTP response. However, it left the downstream
block (previously at line ~794) which unconditionally executed `tour_content = None`
and attempted to read from a shared-volume file. Since shared volumes were eliminated
in the Docker migration, the file read always fails silently, and `tour_content`
stays NULL when stored to the database.

**Fix:** Replace the unconditional `tour_content = None` + file-read with a conditional:
- If `tour_content` is already populated (from HTTP response at line 612), use it directly.
- Only fall back to file read if `tour_content` is falsy.
- Move the ZIP-embedding of `tour_content.txt` outside the conditional so it works
  regardless of source.

### `tests/test_local49_tour_content_persist.py` (new)

Integration regression test with two cases:
1. `test_tour_content_persisted_on_generation` — generates a fresh tour, asserts
   non-NULL non-empty `tour_content`, and asserts `_split_tour_content_into_stops()`
   returns exactly `stops_count` stops.
2. `test_existing_tours_have_content` — asserts no NULL `tour_content` in the DB.

## Acceptance criteria evidence

### 1. Live end-to-end generation with `length(tour_content) > 0` and stop count match

```
 id |                      tour_name                       | content_len | stops_count 
----+------------------------------------------------------+-------------+-------------
 42 | LOCAL49 Final Verification 1785510869 - Walking Tour |        8258 |           3
```

### 2. `_split_tour_content_into_stops(tour_content)` returns exactly `stops_count`

```
_split_tour_content_into_stops returned: 3 stops
Content length: 8259 chars
```

stops_count in DB = 3, parsed stops = 3. Match confirmed.

### 3. Rows 21 and 24 backfilled — no NULLs

```
SELECT id, tour_name FROM audio_tours WHERE tour_content IS NULL;
 id | tour_name 
----+-----------
(0 rows)
```

Tours 21 and 24 specifically:
```
 21 | Asian arts museum, nice, France - museum Tour        |        8663 |           6
 24 | Musée Marc Chagall, Nice, France - museum Tour       |       12657 |           6
```

### 4. Regression suite green — verbatim exit lines

```
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0 -- /Applications/Xcode.app/Contents/Developer/usr/bin/python3
cachedir: .pytest_cache
rootdir: /Users/micha/audioura-worktrees/LOCAL-49
collecting ... collected 2 items

tests/test_local49_tour_content_persist.py::test_tour_content_persisted_on_generation PASSED [ 50%]
tests/test_local49_tour_content_persist.py::test_existing_tours_have_content PASSED [100%]

=================== 2 passed, 3 warnings in 72.38s (0:01:12) ===================
```
