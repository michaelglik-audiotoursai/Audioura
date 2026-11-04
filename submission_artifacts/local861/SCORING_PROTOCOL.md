# LOCAL-861 blind scoring protocol (P1 blind method, TOUR_QUALITY_RUBRIC.md criteria)

The scorer sees ONE text at a time as `blind/<id>.txt` plus its research log
`_local861_blindlogs/<id>.log` (model names redacted). The scorer must NOT open
`BLIND_KEY.json`, `_local861_raw/`, `_local861_meterlogs/`, or git history, and must
not infer the arm from anything but the text itself. Scores are written to
`scores/<id>.json` before the key is read by anyone.

`tour_rubric_scorer.py` is NOT used: it counts facts and does not check truth.

## Per stop (every `Stop N:` block)

1. **d511_story (y/n)** — D511/STORY_DEFINITION.md: the stop narrates a *story*, not a
   description: a named agent (person/institution) does something specific, with a
   cause→consequence chain (Forster/Prince), and a reason it was worth telling
   (Labov evaluation / "He did?"). Restating what a painting depicts, mood words,
   or "invites reflection" = **n**. Shortfall/placeholder stops = **n**.
   Give a one-line `story_quote`.
2. **sourced_specifics (int)** — count of distinct concrete, checkable specifics
   (dates, names of people, materials/dimensions, provenance/acquisition, documented
   anecdote, price, place) that you TRACED to (a) the research log snippets/canon for
   that stop, or (b) an independently verifiable authority you consulted (web search),
   and that are true and about THIS work/venue. Specifics you could not trace do not count.
3. **fabrications (list)** — claims that cannot be traced to the log/canon and that you
   could not verify, OR that are false. Include invented quotes, invented dates,
   invented provenance, invented sensory/room claims, invented relationships between
   people/works. Each item: `{claim, why}`. Interpretive framing clearly signalled as
   interpretation is NOT a fabrication; stating a guess as documented fact IS.
4. **wrong_venue_works (list)** — named works the text places in this museum that are
   held elsewhere (or a stop whose subject is not at this venue). Each: `{work, actually_at}`.
   Also flag a stop that is not a single canonical work/room/exhibit (A6).

## Per text

`stops_delivered`, `stops_requested` (6), `stories` (count of y), `fabrication_count`,
`wrong_venue_count`, `sourced_specifics_total`, `garbled_or_template_defects` (short list),
`overall_0_10` (0–10: real works, truth, story quality, no template smell; a fabricated or
wrong-venue stop is a heavy penalty), and `one_line_verdict`.

JSON schema:

```json
{"id": "t1234", "venue_from_text": "...", "stops_delivered": 6, "stops_requested": 6,
 "stops": [{"n": 1, "title": "...", "d511_story": "y|n", "story_quote": "...",
            "sourced_specifics": 3, "specifics_traced": ["..."],
            "fabrications": [{"claim": "...", "why": "..."}],
            "wrong_venue_works": [{"work": "...", "actually_at": "..."}]}],
 "totals": {"stories": 0, "fabrication_count": 0, "wrong_venue_count": 0,
            "sourced_specifics_total": 0},
 "defects": ["..."], "overall_0_10": 0.0, "one_line_verdict": "..."}
```
