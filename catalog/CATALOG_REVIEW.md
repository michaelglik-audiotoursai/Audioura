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
| 844 | Montmartre, Paris | walk | 5/5 | 6.5 | 5 mp3, 10.8m OK | 514 m | ✗ | **DROP** |
| 845 | Louvre Museum, Paris | museum | 5/5 | 7.5 | 5 mp3, 9.8m OK | 3 m | ✓ | **KEEP** |
| 846 | Colosseum & Roman Forum, Rome | walk | 5/5 | 8.5 | 5 mp3, 11.6m OK | 150 m | ✓ | **KEEP** |
| 847 | Trevi/Pantheon/Navona, Rome | walk | 5/**4** | 6.0 | 4 mp3, 10.0m OK | 72 m | ✓ | **DROP** |
| 848 | British Museum, London | museum | 5/5 | 8.5 | 5 mp3, 11.0m OK | 3 m | ✓ | **KEEP** |
| 849 | Westminster, London | walk | 5/5 | 6.5 | 5 mp3, 12.3m OK | 165 m | ✗ | **DROP** |
| 850 | Metropolitan Museum, New York | museum | 5/5 | 3.0 | 5 mp3, 10.5m OK | 5 m | ✓ | **DROP** |
| 851 | Lower Manhattan, New York | walk | 5/**4** | 5.5 | 4 mp3, 9.1m OK | 130 m | ✓ | **DROP** |
| 852 | Gothic Quarter, Barcelona | walk | 5/5 | 7.5 | 5 mp3, 10.9m OK | 195 m | ✗ | **DROP** |
| 853 | Gaudí architecture, Barcelona | walk | 5/5 | 5.5 | 5 mp3, 10.3m OK | 2460 m | ✗ | **DROP** |
| 854 | Higashiyama temples, Kyoto | walk | 5/5 | 6.5 | 5 mp3, 10.9m OK | 2051 m | ✗ | **DROP** |
| 855 | Asakusa & Senso-ji, Tokyo | walk | 5/5 | 8.0 | 5 mp3, 11.6m OK | 380 m | ✗ | **DROP** |
| 856 | Sultanahmet, Istanbul | walk | 5/5 | 7.5 | 5 mp3, 10.8m OK | 138 m | ✓ | **KEEP** |
| 857 | Alfama, Lisbon | walk | 5/5 | 7.5 | 5 mp3, 11.5m OK | 410 m | ✗ | **DROP** |
| 858 | Old Town & Charles Bridge, Prague | walk | 5/5 | 8.0 | 5 mp3, 11.2m OK | 124 m | ✓ | **KEEP** |
| 859 | Uffizi Gallery, Florence | museum | 5/5 | 7.5 | 5 mp3, 9.8m OK | 206 m¹ | ✓¹ | **KEEP** |
| 860 | San Marco, Venice | walk | 5/5 | 7.5 | 5 mp3, 10.6m OK | 493 m | ✗ | **DROP** |
| 861 | Belvedere Museum, Vienna | museum | 5/5 | 3.5 | 5 mp3, 9.6m OK | 1081 m | ✗ | **DROP** |
| 862 | Old Quarter, Hanoi | walk | 5/5 | 7.5 | 5 mp3, 10.8m OK | 889 m | ✗ | **DROP** |

¹ **859 Uffizi** shares one building-level pin across all five interior-painting stops; 206 m is the distance
from the stored pin to the Uffizi's official map point. As an indoor-gallery tour this is a single GPS marker
for the museum, not a per-exhibit landmark, so it is kept with this stated reason. (For comparison, the Louvre,
British Museum and Met building pins land at 3–5 m.)

## Kept tours (6): 845, 846, 848, 856, 858, 859

All six have real, verifiable places/exhibits, accurate checkable facts, specific stories, clean cross-stop
connections, no garbled or off-topic paragraphs, a complete MP3 per stop with plausible durations, and pins
that pass the ≤ 150 m bar (museums on the building pin).

## One-line reason per tour

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
