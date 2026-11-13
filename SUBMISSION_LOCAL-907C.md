# SUBMISSION — LOCAL-907C: guide-worthy topic plans

Branch `LOCAL-907C-guide-worthy-plan`, base subscribed f650ea1c. **$0 paid**: no LLM call, no build without `--dry-run`; plans read real Wikipedia through `wiki_client` (free), run with `env -u OPENAI_API_KEY`.

## What changed

- `topic_relevance.py`: `not_guide_worthy()` (generic category + first-sentence rules for school, university/college, hotel, restaurant, company, organisation, convention centre, airfield, sports club/venue, film/TV/album/song/book, festival, other administrative division; minor places by stated population < 20,000 or article size); `own_category()` (a category counts only when the region is its subject: 'History of X', 'People from X', 'X'; not 'Islands of X-Y-Z', 'Films set in X'); `section_denied()` (Funding, Finance, Budget, Governance, Politics, Government, Elections, Future, Facilities, Ridership, Fleet, References, See also, Proposed extensions; Management/Administration only for an agency-like article, not a province); `kind_theme()` (festival→arts/people_economy unless religious, venue→people_economy, lighthouse→history unless haunted/legend, ski resort→nature); `reconcile_hint_theme()`.
- `check_relevance`: a located article outside the radius can no longer pass on mentions (a reservoir shared by 3 provinces); a category rescue needs ≤ 1.5× radius; ethnic-group pages of a wider area need coordinates or a hint.
- `topic_library_build.py`: seed sections ≤ 2 per seed article; gated linked articles ≤ 25% of the plan (`int(0.25*max)`); seeds+hints are chosen first; size check drops minor places after the fetch; thin plans are reported; drop counts by reason in the dry-run output (`Dropped by reason:`) and `[LOCAL-907C] topic '<t>' dropped: not guide-worthy (<reason>)` log lines.
- `data/topic_regions.json`: removed 'Thiên Y A Na' from HCMC (kept in Mui Ne); removed the 'Mekong Delta' alias from HCMC (it let Hòa Hảo / Khmer Krom in by mention). Every hint title was re-checked by the dry runs (`hint ... dropped: page does not exist` appears in no log: `grep 'does not exist' /tmp/d907c/*.err` empty).
- Judgement calls: the small-place word threshold is 3,000 not ~1,500 when no population is stated, because the cited offenders (Allston 2,662; Andon 1,620) are above 1,500. A hint keeps its editorial theme unless the classifier wins by a margin ≥ 6 (so a crude classifier cannot move Củ Chi tunnels to 'modern').

## Tests
`tests/test_local907c_guide_worthy.py` (46 tests, mocked): excluded kinds, small commune vs big neighbourhood, own vs broader category (Levant Isle / Verdon Pass shape, generic names), section denylist + max 2 per seed, 5+ theme fallbacks, 25% linked cap, thin report, Thiên Y A Na pruning. One 907B test (`plan_order…`) now asks for 12 segments because 3 × 25% = 0 linked. `pytest tests/test_local907*.py tests/test_local89[6-9]*.py tests/test_local90*.py tests/test_lead905*.py` → **704 passed**.

## The five dry-run plans (real Wikipedia)

### mui_ne_binh_thuan (max 30)
```
Plan for mui_ne_binh_thuan (en): 23 topics, 9 themes
   1. [history         ] Chams: History  (why: seed; source 2394 words; est $0.0173)
   2. [modern          ] Bình Thuận province  (why: seed; source 1578 words; est $0.0168)
   3. [people_economy  ] Dragon fruit  (why: hint; source 975 words; est $0.0165)
   4. [religion_customs] Buddhism in Vietnam  (why: hint; source 6143 words; est $0.0194)
   5. [food            ] Fish sauce: Regional variations  (why: seed; source 1526 words; est $0.0168)
   6. [transport       ] Da Lat–Thap Cham railway  (why: hint; source 1862 words; est $0.0170)
   7. [nature          ] Núi Chúa National Park  (why: hint; source 1268 words; est $0.0167)
   8. [legends         ] Legendary Champa rulers  (why: hint; source 3064 words; est $0.0177)
   9. [arts            ] Chams: Culture  (why: seed; source 1966 words; est $0.0171)
  10. [history         ] Champa  (why: hint; source 10867 words; est $0.0199)
  11. [modern          ] Ninh Thuận province  (why: hint; source 1748 words; est $0.0169)
  12. [religion_customs] Caodaism  (why: hint; source 4147 words; est $0.0183)
  13. [food            ] Bánh xèo  (why: hint; source 591 words; est $0.0163)
  14. [legends         ] Thiên Y A Na  (why: hint; source 672 words; est $0.0163)
  15. [arts            ] Art of Champa  (why: hint; source 3422 words; est $0.0179)
  16. [history         ] Panduranga (Champa)  (why: hint; source 2579 words; est $0.0174)
  17. [modern          ] Phan Thiết (city)  (why: hint; source 1588 words; est $0.0168)
  18. [religion_customs] Islam in Vietnam  (why: hint; source 6986 words; est $0.0199)
  19. [food            ] Vietnamese cuisine  (why: hint; source 6407 words; est $0.0195)
  20. [religion_customs] Po Nagar  (why: hint; source 679 words; est $0.0163)
  21. [religion_customs] Vietnamese folk religion  (why: hint; source 2701 words; est $0.0175)
  22. [religion_customs] Whale worship  (why: hint; source 2073 words; est $0.0171)
  23. [religion_customs] Đạo Mẫu  (why: hint; source 995 words; est $0.0165)
Themes: history=3, modern=3, people_economy=1, religion_customs=7, food=3, transport=1, nature=1, legends=2, arts=2
Themes with >= 2 topics: 6/9  |  thin: people_economy, transport, nature
[LOCAL-907C] thin: 23 of 30 requested topics -- a shorter plan is preferred to filler
Dropped by reason: minor place=1, no clear theme=2, off-region / excluded=1403
Estimated paid cost: $0.4019  |  spent by this plan: $0.0000 (dry run)
```

### ho_chi_minh_city (max 50)
```
Plan for ho_chi_minh_city (en): 31 topics, 9 themes
   1. [history         ] Ho Chi Minh City: History  (why: seed; source 1292 words; est $0.0167)
   2. [modern          ] Bitexco Financial Tower  (why: hint; source 1886 words; est $0.0170)
   3. [people_economy  ] Chợ Lớn  (why: hint; source 1967 words; est $0.0171)
   4. [religion_customs] Caodaism  (why: hint; source 4147 words; est $0.0183)
   5. [food            ] Vietnamese cuisine: Food in relation to lifestyle  (why: seed; source 1142 words; est $0.0166)
   6. [transport       ] Ho Chi Minh City: Transport  (why: seed; source 577 words; est $0.0163)
   7. [nature          ] Cần Giờ Mangrove Forest  (why: hint; source 516 words; est $0.0162)
   8. [legends         ] Lạc Long Quân  (why: hint; source 1826 words; est $0.0170)
   9. [arts            ] Ho Chi Minh City Opera House  (why: hint; source 773 words; est $0.0164)
  10. [history         ] Vietnamese cuisine: Historical influences  (why: seed; source 577 words; est $0.0163)
  11. [modern          ] Bến Thành Market  (why: hint; source 1330 words; est $0.0167)
  12. [religion_customs] Notre-Dame Cathedral Basilica of Saigon  (why: hint; source 1122 words; est $0.0166)
  13. [food            ] Bánh mì  (why: hint; source 2149 words; est $0.0172)
  14. [transport       ] Ho Chi Minh City Metro  (why: hint; source 1496 words; est $0.0168)
  15. [arts            ] The Tale of Kieu  (why: hint; source 2263 words; est $0.0172)
  16. [history         ] Củ Chi tunnels  (why: hint; source 1509 words; est $0.0168)
  17. [modern          ] Thủ Đức (city)  (why: hint; source 902 words; est $0.0165)
  18. [religion_customs] Thien Hau Temple of Cholon  (why: hint; source 510 words; est $0.0162)
  19. [food            ] Coffee production in Vietnam  (why: hint; source 3454 words; est $0.0179)
  20. [transport       ] Tan Son Nhat International Airport  (why: hint; source 4100 words; est $0.0183)
  21. [history         ] Fall of Saigon  (why: hint; source 6922 words; est $0.0198)
  22. [religion_customs] Tết  (why: hint; source 3353 words; est $0.0178)
  23. [food            ] Pho  (why: hint; source 3832 words; est $0.0181)
  24. [history         ] Independence Palace  (why: hint; source 568 words; est $0.0163)
  25. [religion_customs] Đạo Mẫu  (why: hint; source 995 words; est $0.0165)
  26. [history         ] War Remnants Museum  (why: hint; source 790 words; est $0.0164)
  27. [history         ] Arrest and assassination of Ngo Dinh Diem  (why: mentions; source 6686 words; est $0.0197)
  28. [modern          ] District 1, Ho Chi Minh City  (why: coord; source 1019 words; est $0.0165)
  29. [history         ] Siege of Saigon  (why: mentions; source 1731 words; est $0.0169)
  30. [modern          ] Ho Chi Minh City Hall  (why: coord; source 1440 words; est $0.0168)
  31. [modern          ] Thảo Điền  (why: mentions; source 1625 words; est $0.0169)
Themes: history=8, modern=6, people_economy=1, religion_customs=5, food=4, transport=3, nature=1, legends=1, arts=2
Themes with >= 2 topics: 6/9  |  thin: people_economy, nature, legends
[LOCAL-907C] thin: 31 of 50 requested topics -- a shorter plan is preferred to filler
Dropped by reason: airfield=1, company=2, hotel=5, minor place=84, no clear theme=13, off-region / excluded=1186, organisation=1, other administrative division=3, school=8, sports club/venue=7, university/college=23
Estimated paid cost: $0.5298  |  spent by this plan: $0.0000 (dry run)
```

### boston_ma (max 50)
```
Plan for boston_ma (en): 49 topics, 9 themes
   1. [history         ] Massachusetts Bay Transportation Authority: History  (why: seed; source 2378 words; est $0.0173)
   2. [modern          ] History of Boston: 20th century  (why: seed; source 2476 words; est $0.0173)
   3. [people_economy  ] Boston: Demographics  (why: seed; source 816 words; est $0.0164)
   4. [religion_customs] Old North Church  (why: hint; source 9590 words; est $0.0199)
   5. [food            ] Cuisine of New England: Regional specialties  (why: seed; source 2173 words; est $0.0172)
   6. [transport       ] Massachusetts Bay Transportation Authority: Services  (why: seed; source 2516 words; est $0.0174)
   7. [nature          ] Boston: Geography  (why: seed; source 1815 words; est $0.0170)
   8. [legends         ] Boston Strangler  (why: hint; source 2494 words; est $0.0174)
   9. [arts            ] Boston Symphony Orchestra  (why: hint; source 4401 words; est $0.0184)
  10. [history         ] Big Dig: Origin  (why: seed; source 1178 words; est $0.0166)
  11. [modern          ] Boston Latin School  (why: hint; source 2533 words; est $0.0174)
  12. [people_economy  ] Fenway Park  (why: hint; source 8245 words; est $0.0199)
  13. [food            ] Cuisine of New England: Traditional foods and drinks  (why: seed; source 1757 words; est $0.0169)
  14. [transport       ] Boston Harbor  (why: hint; source 2053 words; est $0.0171)
  15. [nature          ] Boston Common  (why: hint; source 2188 words; est $0.0172)
  16. [legends         ] Great Molasses Flood  (why: hint; source 2399 words; est $0.0173)
  17. [arts            ] Museum of Fine Arts, Boston  (why: hint; source 3818 words; est $0.0181)
  18. [history         ] History of Boston: Foundation by Europeans  (why: seed; source 974 words; est $0.0165)
  19. [modern          ] Boston Marathon  (why: hint; source 5313 words; est $0.0189)
  20. [people_economy  ] History of Irish Americans in Boston  (why: hint; source 6367 words; est $0.0195)
  21. [food            ] Boston cream pie  (why: hint; source 568 words; est $0.0163)
  22. [transport       ] Logan International Airport  (why: hint; source 5895 words; est $0.0193)
  23. [nature          ] Boston Public Garden  (why: hint; source 3072 words; est $0.0177)
  24. [legends         ] Salem witch trials  (why: hint; source 10026 words; est $0.0199)
  25. [history         ] Battle of Bunker Hill  (why: hint; source 6337 words; est $0.0195)
  26. [modern          ] Massachusetts Institute of Technology  (why: hint; source 10027 words; est $0.0199)
  27. [food            ] Clam chowder  (why: hint; source 684 words; est $0.0163)
  28. [transport       ] South Station  (why: hint; source 2823 words; est $0.0175)
  29. [nature          ] Charles River  (why: hint; source 2871 words; est $0.0176)
  30. [history         ] Boston Light  (why: hint; source 1154 words; est $0.0166)
  31. [nature          ] Emerald Necklace  (why: hint; source 919 words; est $0.0165)
  32. [history         ] Boston Massacre  (why: hint; source 4376 words; est $0.0184)
  33. [history         ] Boston Tea Party  (why: hint; source 5441 words; est $0.0190)
  34. [history         ] Faneuil Hall  (why: hint; source 8265 words; est $0.0199)
  35. [history         ] Paul Revere  (why: hint; source 4692 words; est $0.0186)
  36. [history         ] Samuel Adams  (why: hint; source 9650 words; est $0.0199)
  37. [history         ] Sons of Liberty  (why: hint; source 2275 words; est $0.0172)
  38. [history         ] Battles of Lexington and Concord  (why: coord; source 9710 words; est $0.0199)
  39. [modern          ] Boston Neck  (why: coord; source 915 words; est $0.0165)
  40. [religion_customs] Archdiocese of Boston  (why: coord; source 2094 words; est $0.0171)
  41. [transport       ] Longfellow Bridge  (why: coord; source 2329 words; est $0.0173)
  42. [nature          ] Back Bay Fens  (why: coord; source 3807 words; est $0.0181)
  43. [arts            ] Boston Athenæum  (why: coord; source 2109 words; est $0.0171)
  44. [history         ] Boston Central Library  (why: coord; source 10854 words; est $0.0199)
  45. [modern          ] East Boston  (why: coord; source 4183 words; est $0.0183)
  46. [religion_customs] Cathedral of the Holy Cross (Boston)  (why: coord; source 1038 words; est $0.0165)
  47. [transport       ] Port of Boston  (why: coord; source 2562 words; est $0.0174)
  48. [nature          ] Castle Island (Massachusetts)  (why: coord; source 831 words; est $0.0164)
  49. [arts            ] Boston Opera House  (why: coord; source 868 words; est $0.0164)
Themes: history=13, modern=6, people_economy=3, religion_customs=3, food=4, transport=6, nature=7, legends=3, arts=4
Themes with >= 2 topics: 9/9
[LOCAL-907C] thin: 49 of 50 requested topics -- a shorter plan is preferred to filler
Dropped by reason: airfield=3, company=18, convention centre=2, dull seed section=2, festival=3, film/TV/album/song/book=6, hotel=1, minor place=9, no clear theme=34, off-region / excluded=1082, organisation=5, restaurant=2, school=43, sports club/venue=9, university/college=25
Estimated paid cost: $0.8747  |  spent by this plan: $0.0000 (dry run)
```

### nice_cote_d_azur (max 40)
```
Plan for nice_cote_d_azur (en): 30 topics, 8 themes
   1. [history         ] Nice: History  (why: seed; source 2367 words; est $0.0173)
   2. [modern          ] Alpes-Maritimes: Administration  (why: seed; source 647 words; est $0.0163)
   3. [people_economy  ] Grasse  (why: hint; source 1911 words; est $0.0170)
   4. [religion_customs] Nice Cathedral  (why: hint; source 695 words; est $0.0163)
   5. [food            ] Provence wine  (why: hint; source 3181 words; est $0.0177)
   6. [transport       ] Nice Côte d'Azur Airport  (why: hint; source 543 words; est $0.0163)
   7. [nature          ] Alpes-Maritimes: Geography  (why: seed; source 933 words; est $0.0165)
   8. [arts            ] Nice: Architecture  (why: seed; source 981 words; est $0.0165)
   9. [history         ] Antibes  (why: hint; source 2990 words; est $0.0176)
  10. [modern          ] Hotel Negresco  (why: hint; source 716 words; est $0.0164)
  11. [people_economy  ] Niçard dialect  (why: hint; source 997 words; est $0.0165)
  12. [food            ] Salade niçoise  (why: hint; source 1364 words; est $0.0167)
  13. [transport       ] Nice tramway  (why: hint; source 1312 words; est $0.0167)
  14. [nature          ] Mercantour National Park  (why: hint; source 622 words; est $0.0163)
  15. [arts            ] Gustav-Adolf Mossa  (why: hint; source 1070 words; est $0.0166)
  16. [history         ] County of Nice  (why: hint; source 1887 words; est $0.0170)
  17. [modern          ] Èze  (why: hint; source 812 words; est $0.0164)
  18. [nature          ] Villefranche-sur-Mer  (why: hint; source 1658 words; est $0.0169)
  19. [arts            ] Opéra de Nice  (why: hint; source 525 words; est $0.0163)
  20. [history         ] Siege of Nice  (why: hint; source 1611 words; est $0.0169)
  21. [history         ] Terra Amata (archaeological site)  (why: hint; source 637 words; est $0.0163)
  22. [history         ] Treaty of Turin (1860)  (why: hint; source 5105 words; est $0.0188)
  23. [history         ] Grotte du Vallonnet  (why: coord; source 1019 words; est $0.0165)
  24. [modern          ] Menton  (why: coord; source 3033 words; est $0.0177)
  25. [religion_customs] Diocese of Nice  (why: coord; source 2164 words; est $0.0172)
  26. [transport       ] Gare du Sud  (why: coord; source 977 words; est $0.0165)
  27. [nature          ] Île Sainte-Marguerite  (why: coord; source 2245 words; est $0.0172)
  28. [arts            ] Asian Art Museum (Nice)  (why: coord; source 1005 words; est $0.0165)
  29. [modern          ] Monte Carlo  (why: coord; source 1862 words; est $0.0170)
  30. [transport       ] Le Train Bleu  (why: mentions; source 1578 words; est $0.0168)
Themes: history=7, modern=5, people_economy=2, religion_customs=2, food=2, transport=4, nature=4, legends=0, arts=4
Themes with >= 2 topics: 8/9  |  thin: legends
[LOCAL-907C] thin: 30 of 40 requested topics -- a shorter plan is preferred to filler
Dropped by reason: airfield=1, company=3, convention centre=2, festival=3, film/TV/album/song/book=4, hotel=1, minor place=117, no clear theme=59, off-region / excluded=1096, other administrative division=2, school=3, sports club/venue=10, university/college=4
Estimated paid cost: $0.5047  |  spent by this plan: $0.0000 (dry run)
```

### san_diego_ca (max 40)
```
Plan for san_diego_ca (en): 40 topics, 9 themes
   1. [history         ] History of San Diego: Ethnic and cultural groups history  (why: seed; source 2675 words; est $0.0175)
   2. [modern          ] Gaslamp Quarter, San Diego  (why: hint; source 551 words; est $0.0163)
   3. [people_economy  ] Economy of San Diego  (why: seed; source 1691 words; est $0.0169)
   4. [religion_customs] Mission San Luis Rey de Francia  (why: hint; source 1345 words; est $0.0167)
   5. [food            ] Beer in San Diego County, California  (why: hint; source 2015 words; est $0.0171)
   6. [transport       ] San Diego Trolley: Current service  (why: seed; source 1225 words; est $0.0166)
   7. [nature          ] San Diego: Geography  (why: seed; source 1723 words; est $0.0169)
   8. [legends         ] Kumeyaay traditional narratives  (why: hint; source 686 words; est $0.0163)
   9. [arts            ] Balboa Park (San Diego)  (why: hint; source 6573 words; est $0.0196)
  10. [history         ] History of San Diego: War and postwar period (1941–present)  (why: seed; source 2650 words; est $0.0174)
  11. [people_economy  ] San Diego County, California: Demographics  (why: seed; source 1083 words; est $0.0166)
  12. [religion_customs] Roman Catholic Diocese of San Diego  (why: hint; source 1915 words; est $0.0170)
  13. [food            ] Mission burrito  (why: hint; source 1235 words; est $0.0166)
  14. [transport       ] San Diego International Airport  (why: hint; source 4750 words; est $0.0186)
  15. [nature          ] Coronado, California  (why: hint; source 3066 words; est $0.0177)
  16. [legends         ] Whaley House (San Diego, California)  (why: hint; source 1858 words; est $0.0170)
  17. [arts            ] Chicano Park  (why: hint; source 2776 words; est $0.0175)
  18. [history         ] San Diego Trolley: History  (why: seed; source 2460 words; est $0.0173)
  19. [people_economy  ] Hispanics and Latinos in San Diego  (why: hint; source 2032 words; est $0.0171)
  20. [religion_customs] San Diego California Temple  (why: hint; source 1578 words; est $0.0168)
  21. [food            ] Taco  (why: hint; source 2521 words; est $0.0174)
  22. [transport       ] San Diego–Coronado Bridge  (why: hint; source 1786 words; est $0.0170)
  23. [nature          ] La Jolla  (why: hint; source 4924 words; est $0.0187)
  24. [arts            ] Panama–California Exposition  (why: hint; source 3592 words; est $0.0180)
  25. [history         ] Cabrillo National Monument  (why: hint; source 1941 words; est $0.0170)
  26. [people_economy  ] Naval Base San Diego  (why: hint; source 1187 words; est $0.0166)
  27. [nature          ] Mission Bay (San Diego)  (why: hint; source 2361 words; est $0.0173)
  28. [arts            ] San Diego Comic-Con  (why: hint; source 4766 words; est $0.0186)
  29. [history         ] Hotel del Coronado  (why: hint; source 3370 words; est $0.0178)
  30. [people_economy  ] San Diego–Tijuana  (why: hint; source 8891 words; est $0.0199)
  31. [nature          ] Point Loma, San Diego  (why: hint; source 4399 words; est $0.0184)
  32. [arts            ] USS Midway Museum  (why: hint; source 1247 words; est $0.0167)
  33. [history         ] Mission San Diego de Alcalá  (why: hint; source 1893 words; est $0.0170)
  34. [people_economy  ] Scripps Institution of Oceanography  (why: hint; source 4426 words; est $0.0184)
  35. [nature          ] San Diego Zoo  (why: hint; source 7670 words; est $0.0199)
  36. [history         ] Old Town San Diego State Historic Park  (why: hint; source 1322 words; est $0.0167)
  37. [nature          ] SeaWorld San Diego  (why: hint; source 2296 words; est $0.0172)
  38. [nature          ] Sunset Cliffs, San Diego  (why: hint; source 668 words; est $0.0163)
  39. [nature          ] Torrey Pines State Natural Reserve  (why: hint; source 1068 words; est $0.0166)
  40. [history         ] Battle of San Pasqual  (why: coord; source 4177 words; est $0.0183)
Themes: history=8, modern=1, people_economy=6, religion_customs=3, food=3, transport=3, nature=9, legends=2, arts=5
Themes with >= 2 topics: 8/9  |  thin: modern
Dropped by reason: airfield=5, company=15, convention centre=2, dull seed section=4, festival=1, film/TV/album/song/book=2, hotel=2, minor place=13, no clear theme=45, off-region / excluded=1118, organisation=1, other administrative division=2, restaurant=3, school=34, sports club/venue=10, university/college=10
Estimated paid cost: $0.6973  |  spent by this plan: $0.0000 (dry run)
```

## Honest assessment against LEAD's bar
- Mui Ne 23/30 and HCMC 31/50 are reported thin on purpose (no filler). Boston 49/50, Nice 30/40, San Diego 40/40.
- Gone from the earlier lists: all schools/universities/hotels/restaurants/Saigon Hotpot, convention centres, Hanscom Field, Allston, Andon/Ascros/Lantosque, Levant Island, Verdon Gorge, The Big Blue, Hồ Tràm, the MBTA Funding/Management and San Diego Politics/Government/Cruise/Proposed-extension sections, HCMC's Thiên Y A Na. Fenway Park → people_economy, Boston Light → history, Boston Book Festival is no longer a plan item.
- Still questionable (not fixed): HCMC 'Thảo Điền' (neighbourhood phrased without a settlement cue), Boston 'Boston Neck', Nice 'Gare du Sud', 'Le Train Bleu' (mentions). Also hints are exempt by instruction, so 'Boston Latin School', 'Hotel Negresco', 'Hotel del Coronado' remain. San Diego has 9 nature/11 history from hint-theme reconciliation; Mui Ne has 7 religion_customs, all hints. The 9-theme balance is better than 907B for HCMC (modern 12 → 6) but people_economy/legends stay thin in HCMC and Mui Ne.
- Estimate of items plainly regional AND a 10-minute guide topic: ≈ 95–97% by my read of the lists above; LEAD should spot-check the 'coord' / 'mentions' rows, which are now at most 25% of each plan.
