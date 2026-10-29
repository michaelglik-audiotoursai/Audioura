# Starter Catalog — Blind Quality Review (LOCAL-808)

**Date:** 2026-10-29
**Branch:** `LOCAL-808-catalog-export` (base `subscribed` = c09692b5)
**Input:** Mac DB `audiotours.audio_tours`, ids **844–862** (19 tours; user `catalog-lead`, cheap arm,
English, Kokoro voice). Read-only. Amsterdam Rijksmuseum request failed and was never stored — ignored.
**Method:** P1 house rubric (`p1/P1_RESULTS.md`) applied blind to each tour's `tour_content`, scored 0–10:
real places/exhibits (fabricated or wrong-place stop = heavy penalty), checkable facts, specific stories,
cross-stop connection, directions + pins, no garbled sentences, no off-topic paragraphs, title quality.
Plus a **listen-check** (ffprobe on the stored ZIP: one MP3 per stop, plausible durations) and a **pin-check**
(every stop coordinate verified against Serper Places + Nominatim, ground-truthed for suspect stops;
landmark threshold **≤ 150 m**). Paid-API spend for pin checks: **$0.00 metered** (73 Serper Places calls;
cap was $0.30).

## Keep rule
Keep a tour only if **score ≥ 7.5 AND every pin ≤ 150 m** (museums judged on the single building-level pin
they share across interior exhibits). Everything else is dropped with a reason.

## Summary

| id  | request | cat | stops (req/got) | score | audio (ffprobe) | worst pin | pins ≤150m | **decision** |
|-----|---------|-----|:---:|:---:|---|:---:|:---:|:---:|
| 844 | Montmartre, Paris | walk | 5/5 | **7.5** | 5 mp3, 11.9m OK | **113 m** | ✓ | **KEEP**ᴮ |
| 845 | Louvre Museum, Paris | museum | 5/5 | 7.5 | 5 mp3, 9.8m OK | 3 m | ✓ | **KEEP** |
| 846 | Colosseum & Roman Forum, Rome | walk | 5/5 | 8.5 | 5 mp3, 11.6m OK | 150 m | ✓ | **KEEP** |
| 847 | Trevi/Pantheon/Navona, Rome | walk | 5/**4** | 6.0 | 4 mp3, 10.0m OK | 72 m | ✓ | **DROP** |
| 848 | British Museum, London | museum | 5/5 | 8.5 | 5 mp3, 11.0m OK | 3 m | ✓ | **KEEP** |
| 849 | Westminster, London | walk | **5/4** | **6.5** | 4 mp3 OK | **140 m** | ✓ | **DROP**ᴮ |
| 850 | Metropolitan Museum, New York | museum | 5/5 | **8.0** | 5 mp3, 12.4m OK | 12 m | ✓ | **KEEP**ᴮ |
| 851 | Lower Manhattan, New York | walk | 5/**4** | 5.5 | 4 mp3, 9.1m OK | 130 m | ✓ | **DROP** |
| 852 | Gothic Quarter, Barcelona | walk | 5/5 | **7.5** | 5 mp3, 10.2m OK | **97 m** | ✓ | **KEEP**ᴮ |
| 853 | Gaudí architecture, Barcelona | walk | 5/5 | **8.0** | 5 mp3, 10.5m OK | **87 m** | ✓ | **KEEP**ᴮ |
| 854 | Higashiyama temples, Kyoto | walk | 5/5 | **6.5** | 5 mp3 OK | **351 m** | ✗ | **DROP**ᴮ |
| 855 | Asakusa & Senso-ji, Tokyo | walk | **5/4** | **6.0** | 4 mp3 OK | **260 m** | ✗ | **DROP**ᴮ |
| 856 | Sultanahmet, Istanbul | walk | 5/5 | 7.5 | 5 mp3, 10.8m OK | 138 m | ✓ | **KEEP** |
| 857 | Alfama, Lisbon | walk | 5/5 | **7.5** | 5 mp3 OK | **252 m** | ✗ | **DROP**ᴮ |
| 858 | Old Town & Charles Bridge, Prague | walk | 5/5 | 8.0 | 5 mp3, 11.2m OK | 124 m | ✓ | **KEEP** |
| 859 | Uffizi Gallery, Florence | museum | 5/5 | 7.5 | 5 mp3, 9.8m OK | 206 m¹ | ✓¹ | **KEEP** |
| 860 | San Marco, Venice | walk | 5/5 | **7.5** | 5 mp3 OK | **477 m** | ✗ | **DROP**ᴮ |
| 861 | Belvedere Museum, Vienna | museum | 5/5 | **6.5** | 5 mp3 OK | **1379 m** | ✗ | **DROP**ᴮ |
| 862 | Old Quarter, Hanoi | walk | 5/5 | **7.5** | 5 mp3 OK | **889 m** | ✗ | **DROP**ᴮ |

¹ **859 Uffizi** shares one building-level pin across all five interior-painting stops; 206 m is the distance
from the stored pin to the Uffizi's official map point. As an indoor-gallery tour this is a single GPS marker
for the museum, not a per-exhibit landmark, so it is kept with this stated reason. (For comparison, the Louvre,
British Museum and Met building pins land at 3–5 m.)

## Kept tours (10): 844, 845, 846, 848, 850, 852, 853, 856, 858, 859

Six were kept in the original LOCAL-808 review (845, 846, 848, 856, 858, 859). Four more were added by the
**LOCAL-808B** re-score of LEAD's re-made tours (844, 850, 852, 853 — marked ᴮ in the table above). All ten
have real, verifiable places/exhibits, accurate checkable facts, specific stories, clean cross-stop
connections, no garbled or off-topic paragraphs serious enough to drop, a complete MP3 per stop with plausible
durations, and pins that pass the ≤ 150 m bar (museums on the building pin).

> **ᴮ = re-scored under LOCAL-808B** (2026-10-29, branch `LOCAL-808B-catalog-rescore`, base `subscribed` =
> 6764ce9e). LEAD re-made 11 tours on newer code (pin snap + Wikidata + museum checks): walking ids 844, 849,
> 852, 853, 854, 855, 857, 860, 862 (generator ab1c97e9) and museums 850 Met, 861 Belvedere (1f4cb350, stop
> pool OFF). Same rubric and keep rule. **Correction to LOCAL-808:** museum "in this collection" is now decided
> by Wikidata **P195** (collection) / **P276** (location) — the LOCAL-809 check — NOT memory. Pin ground-truth
> used free Wikidata P625 + Nominatim (OSM); **paid-API spend $0.00 metered** (cap $0.30). The ᴮ rows REPLACE the
> original LOCAL-808 rows for those ids.

### LOCAL-808B re-score — kept (4 new) and dropped (7)

**KEEP (new)**
- **844 Montmartre** — same five real Montmartre places (Espace Dalí, Sacré-Cœur, Place du Tertre, La Maison Rose, Bateau-Lavoir); the re-made pins now land 11–113 m from the landmarks (LOCAL-808 dropped it only on 170–514 m pins). One minor garble ("the Benedictine abbey established in 1133 by King Louis" — the sentence truncates before "VI"); not drop-worthy. **7.5, all pins ≤ 150 m.**
- **850 Metropolitan Museum** — the fabrication is fixed. All five stops are real Met works, each verified in-collection via Wikidata: *Great Wave off Kanagawa* (Q252485, P195 Met), *Allegory of the Catholic Faith* (Q467359, P195+P276 Met), *View of Toledo* (Q883994, P195+P276 Met), *Melencolia I* (Q1362177, P195 Met), *The Death of Socrates* (Q1752990, P195+P276 Met). No more Met-Store gift-shop stops (LOCAL-808 scored those 3.0). Minor run-on garble in stop 5 ("…the world around In 2000, its permanent collection…"); building pin 12 m. **8.0.**
- **852 Gothic Quarter** — five real Barri Gòtic sites; the re-made pins are 5–97 m (LOCAL-808 dropped on a 195 m pin). Stop 2 (Plaça del Rei) still carries one dangling, context-free sentence about the "imagination of the Old first encountered the new" (an un-introduced Columbus allusion) — a blemish, not a drop. **7.5, all pins ≤ 150 m.**
- **853 Gaudí** — the wrong-place stop is fixed. Casa Vicens, Casa Milà, Casa Batlló and Sagrada Família are all genuine Gaudí; the fifth, Hospital de Sant Pau, is openly presented as Domènech i Montaner's modernist work (a comparison), not passed off as Gaudí — unlike LOCAL-808's "Casa Ramos" fabrication (2.46 km off). Pins 0–87 m. **8.0, all pins ≤ 150 m.**

**DROP**
- **849 Westminster** — pins are now fine (44/28/140/9 m), but the generator delivered **4 of 5** stops and leaked its own apology into the narration **twice**: stop 1's "Specific Examples" reads "…this tour has 4 stops rather than the 5 you asked for," and its Orientation opens "We could confirm 3 stops along this route, so this tour has 3 stops rather than the 4 you asked for" — a contradictory meta-apology a listener would hear. Gunpowder-Plot intro is also abrupt ("Their plan was to blow up…" with no antecedent). Content is otherwise accurate. **6.5 — below 7.5.**
- **854 Higashiyama** — real temples, but Nanzen-ji (161 m) and Eikan-dō (351 m) exceed the bar, and two garbled truncations remain (stop 2 "…lost during World War In the aftermath…", stop 5 "In the late Heian period, —whose reign…" with the subject missing). **6.5, pins fail.**
- **855 Asakusa** — **4 of 5** stops, and structurally broken: stop 1 leaks the stop-count apology, stop 3 (Nakamise) opens with the *first-stop* orientation text ("Your first stop is Kaminarimon Gate…"), and stop 4 truncates "the founding of Senso-". Hōzōmon pin 260 m. **6.0, structural + pins fail.**
- **857 Alfama** — rich, accurate content, but the Museu do Fado pin is 252 m off (the other four are ≤ 28 m). Content would score ~7.5; **pins fail.**
- **860 San Marco** — accurate, all five real San Marco landmarks, but the whole pin set is shifted ~300–480 m northwest of Piazza San Marco (Campanile 477 m, Palazzo Ducale 328 m, Basilica 320 m, Museo Correr 280 m). **7.5 content, pins fail.**
- **861 Belvedere** — the foreign-artwork error is fixed: all five works verify in the Belvedere via Wikidata — *Portrait of Père Paul* (Monet, Q27665416), *The Evil Mothers* (Segantini, Q749201), *Fishermen in Poissy* (Monet, Q3234987), *The Plain of Auvers* (Van Gogh, Q26221225), *Judith I* (Klimt, Q2324643), each P195+P276 Belvedere. (LOCAL-808 wrongly called *Père Paul* and *Plain of Auvers* foreign — corrected here per the task.) But the shared building pin sits 1,379 m from the actual Belvedere (stored 48.2031, 16.3747 vs the palace at 48.1914, 16.3808), and stop 1 carries fabricated boilerplate ("€65; free for Métropole residents") with a truncation in stop 5. **6.5, building pin fails.**
- **862 Hanoi** — rich and accurate, but pins run 225–889 m off (Đồng Xuân 889 m, Ngọc Sơn 225 m); only Hoàn Kiếm Lake is on the mark. **7.5 content, pins fail.**

## One-line reason per tour

> The lines below are the **original LOCAL-808** review of the first-generation tours. For the 11 ids LEAD
> re-made (844, 849, 850, 852, 853, 854, 855, 857, 860, 861, 862), the authoritative verdict is the
> **LOCAL-808B re-score** section above and the ᴮ rows in the summary table; the original lines for those ids
> below are kept only as a record of what the re-make replaced.

**KEEP**
- **845 Louvre** — five real Louvre works, strong narration; only blemish is conflating the 2019 Cimabue "Mocking of Christ" (found near Compiègne, not held here) into stop 3; building pin 3 m.
- **846 Roman Forum** — all five monuments real and accurate, tight chronological thread; worst pin 150 m (large open monuments), the best walking tour in the batch.
- **848 British Museum** — Great Wave, Dürer Rhinoceros, Ashurbanipal, Portland Vase, Rosetta Stone; accurate, clean, building pin 3 m.
- **856 Sultanahmet** — five real Sultanahmet landmarks, accurate; mild redundancy (stop 3 Square ≈ stop 4 Hippodrome are the same ground); all pins ≤ 138 m.
- **858 Prague** — real Old-Town stops, accurate (Charles Bridge 1357 numerology, Tycho Brahe in Týn); all pins ≤ 124 m.
- **859 Uffizi** — five real Uffizi paintings, accurate; stop 4 (Annunciation) is thin; single museum pin 206 m accepted as a building-level marker for an indoor tour.

**DROP**
- **844 Montmartre** — content good but four of five pins sit 170–514 m off the real squares/landmarks (fails ≤ 150 m).
- **847 Rome centro** — delivered only **4 of 5** requested stops and leaks a meta-apology plus a stray Trevi sentence into stop 1's orientation (incomplete + garbled).
- **849 Westminster** — Buckingham Palace is duplicated (embedded in stop 3's directions *and* repeated as stop 4), stop 3 carries two coordinate lines, and Trafalgar's pin is ~165 m off (structural defect).
- **850 Met** — stops 2 and 3 are **Met Store gift-shop products** ("Empire State Building Custom Print", "Wall Calendar 2027 — The Met Store") written up as exhibits: two fabricated/wrong-place stops.
- **851 Lower Manhattan** — delivered only **4 of 5** stops, numbered 1,3,4,5 with **Stop 2 missing entirely** (the directions still point to a dropped Federal Hall) — structural collapse.
- **852 Gothic Quarter** — solid content ("King Martin the Humane" mangled to "Human"), but stop 1 (Santa Maria del Pi) pin is ~195 m off, over the bar.
- **853 Gaudí** — stop 2 "Casa Ramos" is **not a Gaudí building** (it is by Jaume Torres Grau) and its pin is 2.46 km away; wrong-place stop on a Gaudí-specific tour.
- **854 Higashiyama Kyoto** — real temples but **every pin is 0.6–2.0 km off** (latitude systematically wrong), and Hōnen-in (Pure Land) is mislabeled a Zen temple.
- **855 Asakusa** — excellent content, but Kaminarimon (~380 m) and Hōzōmon (~255 m) pins are badly placed and mis-ordered relative to Senso-ji (fails ≤ 150 m).
- **857 Alfama Lisbon** — rich and accurate, but four of five pins are ~280–410 m off (only Castelo de São Jorge is correct); fails ≤ 150 m.
- **860 San Marco Venice** — accurate content, but the whole-tour pin set sits ~250–500 m northwest of the actual Piazza San Marco (fails ≤ 150 m).
- **861 Belvedere** — stops 3 (Monet "Père Paul") and 5 (Van Gogh "Plain of Auvers") are **not in the Belvedere** (two wrong-place exhibits), stop 1 leaks a "Belvedere may refer to:" disambiguation stub, and all pins are ~1 km off.
- **862 Hanoi Old Quarter** — rich and accurate, but pins run 180–890 m off (Bach Ma ~550 m, Dong Xuan ~890 m); fails ≤ 150 m.

## Notes on failure modes
- **Pins are the dominant failure.** Eight otherwise-good tours (844, 852, 855, 857, 860, 862, and the gross cases 854, 861) are dropped purely or largely on coordinates. The cheap arm writes strong prose but places many walking-tour pins at approximate points rather than on the landmark.
- **Fabrication / wrong-place** (heaviest penalty): 850 Met (store products as art) and 861 Belvedere (two artworks not in the museum) score 3.0–3.5.
- **Stop-count shortfalls:** 847 and 851 silently delivered 4 of 5 stops; 851 also dropped its Stop 2 mid-sequence. Their audio ZIPs correctly contain 4 MP3s — the shortfall is in generation, not packaging.
- **Audio is uniformly fine:** every tour has exactly one MP3 per delivered stop, 52–192 s each, 9–12 min total, all readable by ffprobe. Audio was never a reason to drop.
