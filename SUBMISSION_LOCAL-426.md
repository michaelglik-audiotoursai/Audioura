# SUBMISSION_LOCAL-426.md

## Summary

LOCAL-426 fixes provenance tracking when exhibition works are sourced from
third-party sites instead of the venue's own page. Previously, when mfa.org
returned 429 and works were fetched from airmail.news, the result recorded
`exhibition_url = mfa.org` — hiding that the content actually came from a
different source. This made the verifier (LOCAL-424) treat third-party
claims as museum-sourced evidence.

## Changes

### exhibition_checklist.py

1. **`ExhibitionChecklistResult`**: Added two fields:
   - `content_url` — the URL the works text was actually fetched from
   - `is_third_party` — boolean flag for downstream verifiers

2. **Third-party path**: Each work dict now carries `source_url` pointing to
   the actual source page. `content_url` is set to the third-party URL (not
   the venue URL). `is_third_party = True` is set.

3. **`is_usable_exhibition_source(url)`** — New module-scope function implementing
   a scored domain quality gate:
   - **Allowlist**: arts publications (artnet, artnews, hyperallergic, airmail.news),
     newspapers (NYT, Guardian, Boston Globe), wire services (AP, Reuters, BBC)
   - **Blocklist**: content farms (Reddit, Medium, Quora, Pinterest, Wikipedia,
     Buzzfeed, blogspot, etc.)
   - **Unknown domains**: accepted only if URL path contains arts/exhibition keywords;
     rejected otherwise.

4. **`_search_exhibition_works_from_web`**: Now calls `is_usable_exhibition_source()`
   before fetching any third-party URL.

### generate_tour_text.py

- `[LOCAL-364] Result:` line now shows `content_url` (not venue URL) and `THIRD-PARTY` flag
- Per-work output includes `[source: <url>]` tag showing where each work came from
- Warning logged when third-party source detected

## How third-party is exposed downstream

The verifier can now distinguish evidence strength:
- `result.is_third_party == True` → weaker evidence, third-party source
- `work['source_url']` → the actual page that supplied the claim
- `result.content_url` → where text came from (differs from `exhibition_url`)
- `result.exhibition_url` → the venue's own URL (for reference, may be unreachable)

A verifier fed `source_url = airmail.news` can appropriately flag claims as
requiring additional corroboration vs. one fed `source_url = mfa.org` which
would incorrectly treat them as museum-sourced.

## Live run — per-work provenance

```
  [LOCAL-364] ═══ EXHIBITION CHECKLIST RETRIEVAL ═══
  [LOCAL-364] Exhibition search term: 'Picasso, Miro, Dali: Unbound'
  [LOCAL-364] Venue URL: http://www.mfa.org/
  [LOCAL-364] Searching for exhibition 'Picasso, Miro, Dali: Unbound' on http://www.mfa.org
  [LOCAL-425] HTTP 429 from http://www.mfa.org/exhibitions — retrying (attempt 1/2)
  [LOCAL-425] HTTP 429 from http://www.mfa.org/exhibitions — giving up (attempt 2/2)
  [LOCAL-425] Searching: Picasso, Miro, Dali: Unbound site:www.mfa.org
  [LOCAL-425] Search hit: https://www.mfa.org/exhibition/picasso-miro-dali-unbound — Picasso, Miró, Dalí: Unbound
  [LOCAL-425] Web search found exhibition URL: https://www.mfa.org/exhibition/picasso-miro-dali-unbound
  [LOCAL-425] HTTP 429 from https://www.mfa.org/exhibition/picasso-miro-dali-unbound — retrying (attempt 1/2)
  [LOCAL-425] HTTP 429 from https://www.mfa.org/exhibition/picasso-miro-dali-unbound — giving up (attempt 2/2)
  [LOCAL-425] Venue page unreachable — trying third-party sources for works
  [LOCAL-425] Searching for exhibition works: "Picasso, Miro, Dali: Unbound" works OR checklist OR objects Museum of Fine Arts, Boston
  [LOCAL-425] Skipping (venue domain, likely 429): https://www.mfa.org/exhibition/picasso-miro-dali-unbound
  [LOCAL-425] Skipping (shopping/store site): https://mfashop.com/picasso-miro-dali-unbound/...
  [LOCAL-426] Skipping (source quality gate): https://exploreboston.com/events/picasso-miro-dali-unbound-opens-at-the-mfa/ — unknown domain: exploreboston.com — no arts/exhibition signal in URL path
  [LOCAL-425] Trying third-party source: https://airmail.news/arts-intel/events/picasso-miro-dali-unbound (allowed domain: airmail.news (arts publication / newspaper / wire service))
  [LOCAL-425] ✓ Extracted 3 works from https://airmail.news/arts-intel/events/picasso-miro-dali-unbound
  [LOCAL-425] ✓ THIRD-PARTY PATH: 3 works
  [LOCAL-364] Result: ExhibitionChecklistResult(path=prose_llm, works=3, title='Picasso, Miro, Dali: Unbound', url='https://airmail.news/arts-intel/events/picasso-miro-dali-unbound', THIRD-PARTY)
  [LOCAL-426] ⚠️  THIRD-PARTY SOURCE — works came from https://airmail.news/arts-intel/events/picasso-miro-dali-unbound, NOT from https://www.mfa.org/exhibition/picasso-miro-dali-unbound
  [LOCAL-364/368] ✓ PROSE_LLM PATH: 3 works from exhibition page
    Source: https://airmail.news/arts-intel/events/picasso-miro-dali-unbound
    Venue: https://www.mfa.org/exhibition/picasso-miro-dali-unbound (unreachable)
      - Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (by Joan Miró) [source: https://airmail.news/arts-intel/events/picasso-miro-dali-unbound]
      - Au Soleil du Plafond (by Juan Gris and Pierre Reverdy) [source: https://airmail.news/arts-intel/events/picasso-miro-dali-unbound]
      - Moses and Monotheism (by Salvador Dalí) [source: https://airmail.news/arts-intel/events/picasso-miro-dali-unbound]
```

The `[LOCAL-364] Result:` line no longer claims a URL that did not supply the content.

## Red output (neutralisation)

Production code neutralised: `_w['source_url'] = _search_url` (venue URL) instead
of `_w['source_url'] = _third_party_url`, `is_third_party = False`, `content_url = _search_url`.

```
FAILED tests/test_local426_third_party_provenance.py::test_third_party_works_carry_their_actual_source_url

    def test_third_party_works_carry_their_actual_source_url():
        """A work extracted from airmail.news must report airmail.news as its source,
        NOT mfa.org. This is the core LOCAL-426 provenance assertion."""

        ...

        # (a) Each work must carry source_url == the third-party URL
        for work in result.works:
            assert 'source_url' in work, (
                f"Work '{work.get('title')}' has no source_url field — "
                f"provenance is lost (LOCAL-426)"
            )
>           assert work['source_url'] == THIRD_PARTY_URL, (
                f"Work '{work.get('title')}' reports source_url='{work['source_url']}' "
                f"but text came from {THIRD_PARTY_URL} — the venue URL must NOT be the source"
            )
E           AssertionError: Work 'Guitar' reports source_url='https://www.mfa.org/exhibition/picasso-miro-dali-unbound' but text came from https://airmail.news/arts-intel/events/picasso-miro-dali-unbound — the venue URL must NOT be the source
E           assert 'https://www....-dali-unbound' == 'https://airm...-dali-unbound'
E
E             - https://airmail.news/arts-intel/events/picasso-miro-dali-unbound
E             + https://www.mfa.org/exhibition/picasso-miro-dali-unbound

tests/test_local426_third_party_provenance.py:128: AssertionError
----------------------------- Captured stdout call -----------------------------
  [LOCAL-364] Searching for exhibition 'Picasso, Miró, Dalí: Unbound' on https://www.mfa.org
  [LOCAL-425] Web search found exhibition URL: https://www.mfa.org/exhibition/picasso-miro-dali-unbound
  [LOCAL-425] Venue page unreachable — trying third-party sources for works
  [LOCAL-425] ✓ THIRD-PARTY PATH: 3 works
    Venue URL (confirmed): https://www.mfa.org/exhibition/picasso-miro-dali-unbound
    Content source: https://airmail.news/arts-intel/events/picasso-miro-dali-unbound
    - Guitar by Pablo Picasso
    - The Farm by Joan Miró
    - The Persistence of Memory by Salvador Dalí

=========================== short test summary info ============================
FAILED tests/test_local426_third_party_provenance.py::test_third_party_works_carry_their_actual_source_url
========================= 1 failed, 1 warning in 0.70s =========================
```

## Control (D302/D326)

Palais Lascaris 4/4, dates intact:
```
STOPS: 4
  Stop 1: Raquel (panneau, fin du XVIe siècle)
  Stop 2: Basse de violon by Paolo Antonio Testore (Milan, 1696)
  Stop 3: Guitar by Antonio de Torres (Almeria, 1884)
  Stop 4: Guitare baroque by Giovanni Tesler (Ancona, 1618)
DATE-CONTAINING LINES: 13
CONTROL: Palais 4/4
```

## Test suite (green after fix)

```
tests/test_local426_third_party_provenance.py::test_third_party_works_carry_their_actual_source_url PASSED
tests/test_local426_third_party_provenance.py::test_venue_path_works_do_not_get_third_party_source PASSED
tests/test_local426_third_party_provenance.py::test_source_quality_gate_rejects_content_farms PASSED
tests/test_local426_third_party_provenance.py::test_source_quality_gate_accepts_arts_publications PASSED
tests/test_local426_third_party_provenance.py::test_source_quality_gate_unknown_domain_with_arts_path PASSED
========================= 5 passed, 1 warning in 0.69s =========================
```

Existing tests (102) pass with no regression.
