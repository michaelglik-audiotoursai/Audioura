# SUBMISSION LOCAL-885 — full-article Wikipedia evidence (OpenAI spend: $0.00)

No tour generation, LLM or Serper call was made. Only free MediaWiki/Wikidata calls and offline unit tests.

## Changes (landmark_wikipedia_evidence.py)
- `fetch_full_text` (`prop=extracts&explaintext=1`, no exintro), up to 20 KB, run only AFTER `_pick` has accepted the article. The 878/881/883/884 acceptance rules are untouched.
- `RULES_VERSION` = `local885-fulltext`. Old-version rows, and same-version rows with no `full_text`, are re-fetched via ON CONFLICT (no DELETE).
- `article_sections`, `split_paragraphs`, `select_passages`: rank paragraphs by years, exact dates, story verbs, named people. Reference-like sections are dropped. Output is capped at 6 KB and emitted in article order.
- `evidence_for` appends `Passages:` to each language item. The narrator sees the en passages; the local edition (vi) goes to the gate/audit only.
- `cached_evidence` returns ONE memoised `EvidenceBundle` (list subclass), the same object for narrator, gate-sink and audit.
- `run_evidence_sizes_885.py` + `submission_artifacts/local885/evidence_sizes.md`.

## Results (free API)
Cathedral 859→6424, Independence Palace 1193→3335 (30 April 1975 tank: yes), War Remnants 309→4820, Opera House 1087→4523 (1944 bombing: yes), City Hall 1141→7039, Post Office en 540→2130 (whole article is 2,136 chars; Vildieu and Foulhoux present; vi edition 3,409). Four stops have no accepted article.

## Tests
`tests/test_local885_full_article_evidence.py`: 10 pass. 872/878/881/882/883/884 suites: 165 pass, 3 fail in `test_local882_cache_revalidation.py`. Those 3 fail identically on the base commit 2dbada8c (verified by stashing my changes), caused by LOCAL-884's coordinate-less payload strictness. I did not touch them.

## Not verified
Nothing was run end to end through tour generation (no budget). The narrator prompt now carries up to about 10 KB of Wikipedia text per stop; its effect on output is unmeasured. The gate's local-language feed relies on the shared bundle (`_wiki_evidence_sink_record` takes the same items).
