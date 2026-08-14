# Autonomous run — 2026-08-13 20:0x, Michael at the gym

**Standing instruction, his words:** "continuously improve the routines to get higher and
higher scores for stories for all 9 items in the different tours and stops in your matrix
where our routine determined a need for stories. The limit to spend should be no more than
$10 USD."

**This is NOT the break exception in CLAUDE.md.** He asked for continuous work while away,
so RULE ZERO is in full force: keep the queue moving, decide reversible things, record the
reasoning here and in `DECISIONS.md`.

## Spend ceiling — $10.00

`cost_ledger` does not capture story_lab / sweep spend (530 rows, $47.79 lifetime, $0.00 in
the last 12h while ~$0.09 was actually spent today). So track it here by hand, from the
`estimated_cost` each search returns and the token cost of each writer call.

| when | what | $ | running |
|---|---|---|---|
| 16:0x | S3 live, stop 2 enriched, 16 queries | 0.0160 | 0.0160 |
| 17:2x | sweep, MFA stops 1-3 production records | 0.0110 | 0.0270 |
| 17:3x | enriched records, MFA stops 1 and 3 | 0.0300 | 0.0570 |
| 17:3x | sweep, Fruitlands stops 1-3 | 0.0150 | 0.0720 |
| 17:4x | sweep, Beacon Hill stops 1-3 | 0.0090 | 0.0810 |
| 18:0x | story_writer, 2 × gpt-4o | ~0.0100 | ~0.0910 |
| 11:5x-19:0x | checklist prose-LLM calls, gpt-4o-mini | ~0.0050 | ~0.0960 |

**Remaining at handover: ~$9.90.** Stop and report at $9.00; never cross $10.

## The 9 stops, and where each stood at handover (D433)

```
MFA Unbound     Le Lézard aux plumes d'or    needs story, SILENCE  (catalogue only)
MFA Unbound     Moses and Monotheism         needs story, WRITE    (Dalí/Freud 1938)
MFA Unbound     Au Soleil du Plafond         needs story, WRITE    (Gris/Rosenberg 1927)
Fruitlands      Hudson River from Fort P.    needs story, SILENCE
Fruitlands      The Brothers (1883)          needs story, SILENCE
Fruitlands      The Print Room               needs story, SILENCE
Beacon Hill     Massachusetts State House    needs story, SILENCE
Beacon Hill     Cheers Beacon Hill           needs story, SILENCE
Beacon Hill     Louisburg Square             needs story, WRITE
```

**3 of 9 sourceable. Raising that is the job.** The measured blocker (D433) is that six
stops retrieve CATALOGUE — accession number, medium, dimensions, nobody doing anything.
`consequence` is the most-missing element by a wide margin.

## Plan, in order

1. Review, verify and merge LOCAL-462 / 463 / 464 as they land. Verify by effect, never by
   `exit=0`. Neutralise each suite personally; check no fixture was edited (D432).
2. Wire the chain end to end: matrix → Request_to_AI → Structure_AI_output →
   story_writer → Validate_Story → Evaluate_Story. Run on stop 2 first (known good).
3. Then the six SILENCE stops. The hypothesis to test, from D433 and D430: the queries ask
   about OBJECTS and get catalogues back; the ones that worked ask about PEOPLE DOING
   THINGS. `Request_to_AI`'s template is person-shaped by construction — that is the
   experiment.
4. R5 from LOCAL-459 was never honestly delivered: **fetch the page, do not rank the
   teaser.** A SERP snippet is ~200 chars; `freud.org.uk` has a whole article behind it.
   The three WRITE stops all happened to have a consequence inside the teaser, which is
   luck. This is the highest-value unbuilt thing.
5. Re-run `story_sweep.py` after each change and record the 9-stop table in `DECISIONS.md`,
   so improvement is measured and not asserted.

## Standing cautions that have each caught something today

- Three times today the INSTRUMENT, not the subject, produced the alarming reading: the
  FLAT-handle gap in the sweep (D433), LOCAL-459's fabricated fixture (D432), and the
  `top 2:` heading in `ORIGINAL_stop2.txt` (D436). **Check the instrument first.**
- A task may not modify the fixture it is judged against (D432). Check the diffstat.
- An uncommitted file does not exist to a dispatched task (D431). Commit before citing.
- `exit=0` means nothing. Commits, submission doc, and behaviour change (CLAUDE.md).

## If this session dies

Everything above is on disk. `bash restart.sh`, read this file and the D42x-D43x block of
`DECISIONS.md`, then continue at step 1. The three task files are in flight; check
`kiro_sessions_ran.md` for their terminal records before re-dispatching anything.
