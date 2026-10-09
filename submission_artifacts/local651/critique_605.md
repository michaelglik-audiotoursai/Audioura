[tool] Reading tour_605.txt:1
[tool] status: Completed
Now let me verify a few factual claims against my knowledge of where these works hang and museum details.

Key facts to check:
- **Sappho and Alcaeus** (Alma-Tadema, 1881) — this is indeed at the Walters Art Museum, Baltimore. Correct.
- **Springtime** (Monet, 1872) — Monet's "Springtime" (Le Printemps / The Reader variants). The Walters does hold a Monet "Springtime" (1872). Correct.
- **The Death of Caesar** (Gérôme) — the Walters Art Museum holds Gérôme's "The Death of Caesar" (c. 1859–1867). Correct.
- Henry Walters purchased in 1917 — plausible provenance detail.
- Hours: "open daily except Monday and Tuesday" — the Walters is open Wednesday–Sunday, so this is accurate-ish. But admission is NOT spoken.

Now the review.

# Audio-Tour Review: tour_605.txt — The Walters Art Museum

**Score: 6.5 / 10**

A listener standing in the museum gets three substantive, work-and-artist-led stops with real emotional and critical content — the core is strong. But it is dragged down by a missing spoken admission price, a boilerplate accession-opener on Stop 1, and a Stop 3 ending that re-tells both prior stops instead of delivering a clean conclusion.

| Stop | Quote (≤20 words) | Criterion | Severity |
|------|-------------------|-----------|----------|
| 1 | "you will see Henry's bequest to the Walters Art Museum" | 1 (dry institutional/provenance filler leads before the work) | Low |
| 1/all | "The museum is open daily except Monday and Tuesday." | 3 (hours spoken but admission price never spoken) | Medium |
| 2 | "Monet's choice to paint his wife in this peaceful setting" | 8 (factual red flag — subject is debated; stated as fact) | Low |
| 3 | "along with works like Sappho and Alcaeus and Monet's Springtime, reflects the impact of the American Civil War" | 5 (re-tells both previous stops' subjects) | Medium |
| 3 | "William Walters began collecting... as a nominal Confederate loyalist at the outbreak of the... Civil War" | 1 (welcome collector story — not a defect; noted as the one genuine provenance story) | None |
| 3 | "This tour highlights the interplay of creativity and historical narratives..." | 6 (conclusion is generic filler, leans on re-told facts rather than a real wrap-up) | Low |
| — | (no stop-count explanation for 3 requested stops) | 7 (3 stops requested, 3 delivered — not short; "That's 3 stops in all" suffices) | None |

Notable passes: no URLs or source lists (4 ✓), no story repeated as a *distinct* narrative (2 ✓), no mid-tour restaurant offer and the single offer is the last sentence (5 ✓, intentional), and all three works are correctly attributed to the Walters (8 ✓).

### Three highest-value code-level improvements

1. **Enforce a spoken admission price alongside hours.** The generator emits hours ("open daily except Monday and Tuesday") but drops admission entirely, failing criterion 3. Add a template slot that requires both `hours` and `admission` to be verbalized (e.g. "General admission is free") and fail generation if the admission field is empty rather than silently omitting it.

2. **Suppress the "bequest/accession" boilerplate opener and lead with the work.** Stop 1 opens with "you will see Henry's bequest to the Walters Art Museum" plus a redundant "Your first stop is…" restatement. Add a lint rule that strips provenance/accession phrasing from the first 1–2 sentences of a stop so the opening line is always the work, artist, and what it depicts.

3. **Detect cross-stop fact re-telling in the final stop.** Stop 3's closing names "Sappho and Alcaeus and Monet's Springtime," re-stating earlier stops' subjects (criterion 5) and bloating the conclusion (criterion 6). Add a check that flags proper-noun artwork titles from earlier stops reappearing in the conclusion, and route the conclusion through a dedicated template that synthesizes a theme without re-listing prior works.
