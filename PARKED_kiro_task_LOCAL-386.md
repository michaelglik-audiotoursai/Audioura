# LOCAL-386 — An ungrounded statistic passed both gates. Numbers are claims too.

## Status: LOCAL-385 is MERGED. Branch off `storied`.

The gates now cover every prose field (D304) and the MFA tour's zero-check is
clean for the first time. One claim still walked straight through:

> "With **over 1.2 million visitors annually**, the Museum of Fine Arts in Boston
> stands as a beacon of creativity…"

That number is **not on the exhibition page**. Both gates missed it because
neither inspects numeric claims — the person gate looks for names, the form-claim
gate for form vocabulary. A statistic is neither.

In the same run the person gate correctly removed "Originating from the Boston
Athenæum, the Museum of Fine Arts…" — a claim that happens to be *true* but was
ungrounded. That is the policy working. The visitor statistic is the same class of
claim and survived only because it is expressed as a number.

## Required — a numeric-claim check in the same module

- Scan all `GATED_PROSE_FIELDS` (the list LOCAL-385 defined — **use it, do not
  write a second one**; D304 exists because two gates each chose their own scope).
- Flag quantitative claims: visitor counts, dates, dimensions, prices, "the
  oldest/largest/first", percentages, "over N", "more than N".
- A flagged claim survives only if the number appears in the grounding source for
  that stop, accent- and format-tolerantly (`1.2 million` ≈ `1,200,000`).
  Otherwise drop the sentence, reusing 378's fragment cleanup.
- **Exempt what is already grounded elsewhere**: dates and figures that came from
  the credit line via the work-identity block (e.g. "1971", "40 color
  lithographs") are grounded by construction — do not strip the very facts rounds
  376–385 worked to inject. Check the identity block before the page text.
- Log: `[LOCAL-386] field=<f> ungrounded quantity '<claim>' — dropping sentence`.

## Do NOT

- Do not strip numbers that came from the credit line or the identity block.
- Do not touch the person or form gates' behaviour — they are working.
- Do not add a general "no numbers" rule; a tour with no dates or dimensions is
  worse (D301).

## Acceptance — live, per D284, case-insensitive in python (D299)

`Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA`, 8 requested:

- **Zero:** `1.2 million`, `million visitors`, and any visitor/attendance figure
  not on the page
- **Still present** (must not be stripped): `1971`, `40 color lithographs`,
  `1955`, `1974` where the credit line or page supports them
- **Still zero** (LOCAL-385's win must hold): `ceiling`, `mural`, `installation`,
  `sculpture`, `painting`, `glass`, `stand beneath`, `look up`, `gaze up`,
  `Chagall`, `Rousseau`, `Corbusier`, `Lalanne`, `Matisse`
- **Still present:** `Miró` stop 1; `Dalí` and `Freud` stop 2; `Gris` and
  `Reverdy` stop 3
- Every stop ≥120 words; `That's N stops` == heading count

**Control case (D302):** unscoped `Palais Lascaris, Nice, France` at 4 → 4/4 real
instruments, and the instrument **dates must survive** (`1780`, `1884`, `1696`,
`1581` are in the stop titles and are grounded). A gate that strips them is a
bounce. Bounds `score_tour_file(f,4)`=**81.2**, `score_tour_file(f,8)`=**75.0**.

Env: `DISABLE_TOUR_CACHE=1`,
`DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours`,
`STORIED_MODE=true`.

## Tests

State the expected red-on-revert count; revert breaks the **logic, not the
symbol** (D296); confirm the patch applied. No mirrors, no `inspect.getsource`
(D277).

## PROCESS
- Branch `kiro/local386-numeric-claim-gate` off `storied`.
- Write `SUBMISSION_LOCAL-386.md`.
- Do NOT edit DECISIONS.md / CLAUDE.md / BACKLOG.md / .continuous_dev/STATUS.md.
- Do NOT `DELETE FROM audio_tours`.
