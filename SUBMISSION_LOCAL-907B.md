# SUBMISSION — LOCAL-907B: region-relevant Topic Library plan

Branch `LOCAL-907B-region-relevant-plan` (from subscribed `ceb76055`). Paid spend: **$0** (no LLM call, no non-`--dry-run` build, item 2b not used). Free Wikipedia reads only, through the new polite client.

## What changed
- `wiki_client.py` (new): User-Agent `AudiouraTopicLibrary/1.0 (contact: audiotoursai@gmail.com)`; serial requests >= 200 ms apart; `maxlag=5`; 429/503 (also `maxlag` error bodies and network errors) back off honouring `Retry-After`, else 2/4/8/16 s, max 5 tries, then `WikiFetchError`.
- `topic_relevance.py` (new): batched (50 titles/query), disk-cached `WikiMeta` (exists, redirects, `prop=coordinates`, visible `prop=categories`, lead); the relevance gate (coord / mentions >= 3 in lead + first 2 sections, folded and diacritic-insensitive / category naming a region name); exclusions (`List of`, disambiguation, publishers, media, sports leagues, whole other countries/cities, biographies without coordinates, terror/crime pages, anything mapped more than 2x the radius away, pages about the wider country); theme classification from the article's own title, first sentence, lead and categories. It returns `None` (topic dropped) rather than a wrong theme.
- `topic_library_build.py`: planning order seed sections -> `topic_hints` -> gated linked articles. `fetch_article` uses the polite client. A page that fails after the retries is logged and skipped, never a crash. Dry-run lines show the relevance reason, source words, URL, theme counts and which themes are thin. `-v` prints every `[LOCAL-907B] topic '<title>' dropped: <reason> (<scores>)` line (about 1,100-1,400 per region).
- `data/topic_regions.json` (DATA, D769): per region `aliases`, `generic_seeds`, `generic_tokens`, `exclude_title_terms`, and 24-33 `topic_hints` (title + editorial theme). Every hint was checked against the live API; titles that do not exist were dropped or replaced with the real article (no articles exist for `Kê Gà Lighthouse`, `Cours Saleya`, `Old Nice`, `Castle Hill, Nice`, `Jade Emperor Pagoda, Ho Chi Minh City` ...; redirects are followed, e.g. `Pitaya` -> `Dragon fruit`).
- `tests/test_local907b_region_relevance.py`: 38 tests, network mocked (gate by coord / mentions / category and the far-away rule, excluded page kinds, hints used and existence-checked, 429 -> retry, 5x429 -> skipped without a crash, Retry-After, User-Agent, 200 ms pacing, 50-title batching, 5 theme-classification leads, dry-run output fields).

## Tests
`pytest tests/test_local907*.py tests/test_local89[6-9]*.py tests/test_local90*.py tests/test_lead905*.py`: **all pass, no new failures** (`test_local88_tour_pollution.py` was not run).

## Dry runs on the real Wikipedia (free), 2026-11-12

No crash and no 429 in these five runs. The 429 backoff path is therefore proven only by the mocked tests; I could not provoke a real 429.

| region | requested | planned | gate drops logged | tracebacks | themes |
|---|---|---|---|---|---|
| mui_ne_binh_thuan | 30 | 24 | 1401 | 0 | >= 2 topics in 7/9  |  thin: transport, nature |
| ho_chi_minh_city | 50 | 48 | 1157 | 0 | >= 2 topics in 9/9 |
| boston_ma | 50 | 50 | 1135 | 0 | >= 2 topics in 9/9 |
| nice_cote_d_azur | 40 | 40 | 1136 | 0 | >= 2 topics in 8/9  |  thin: legends |
| san_diego_ca | 40 | 40 | 1156 | 0 | >= 2 topics in 9/9 |

Why some plans are shorter than requested: Mui Ne gives 24 because Wikipedia's own material for the district is thin (the Mũi Né article is 497 words; Tà Cú, Po Klong Garai, Cham Calendar are stubs under the 500-word floor). I stopped rather than pad with off-region articles. Thin themes there: transport (1), nature (1). HCMC gives 48 (candidate pool exhausted). Nice is thin on legends (1) only.

`why:` values: `seed` = seed section/article, `hint` = topic_hint that exists, `coord` / `mentions` / `category` = linked article that passed the gate.

### Relevance, honestly

Judged by eye from the plans below. Plainly regional: nearly all. Marginal (kept because they pass the gate and Wikipedia has nothing closer, but LEAD may want to strike them): Mui Ne `Buddhism in Vietnam`, `Islam in Vietnam`, `Vietnamese folk religion`, `Đạo Mẫu`, `Vietnamese cuisine` (national pages standing in for local faith/food; the Cham and Bình Thuận topics come first in each theme); HCMC `Dầu Tiếng Reservoir`, `Tiền Giang province`, `Hồ Tràm`, `Hòa Hảo`; Boston `Boston Book Festival` (filed under religion_customs: the classifier treats 'festival' as a custom); Nice `The Big Blue`, `Ligures`, `Verdon Gorge`, `Le Train Bleu`. About 15 of 202 topics (7%) are marginal, so roughly 93% are plainly about the region. The old failures (Ancient Rome, Bayon, Acehnese people, Cambridge Scholars Publishing, Al Jazeera Arabic, Christmas Island, Beijing cuisine, Fish diseases, Puchero, Saint Petersburg, Busan, ASEAN Basketball League, Baháʼí Faith ...) are all gone; grep the plans.

## The five plans (verbatim `--dry-run` output)

### mui_ne_binh_thuan (--max-segments 30)
```
Plan for mui_ne_binh_thuan (en): 24 topics, 9 themes
   1. [history         ] Chams: History  (why: seed; source 2394 words; est $0.0173)
        https://en.wikipedia.org/wiki/Chams
   2. [modern          ] Bình Thuận province  (why: seed; source 1578 words; est $0.0168)
        https://en.wikipedia.org/wiki/B%C3%ACnh_Thu%E1%BA%ADn_province
   3. [people_economy  ] Dragon fruit  (why: hint; source 975 words; est $0.0165)
        https://en.wikipedia.org/wiki/Dragon_fruit
   4. [religion_customs] Buddhism in Vietnam  (why: hint; source 6143 words; est $0.0194)
        https://en.wikipedia.org/wiki/Buddhism_in_Vietnam
   5. [food            ] Fish sauce: Regional variations  (why: seed; source 1526 words; est $0.0168)
        https://en.wikipedia.org/wiki/Fish_sauce
   6. [transport       ] Da Lat–Thap Cham railway  (why: hint; source 1862 words; est $0.0170)
        https://en.wikipedia.org/wiki/Da_Lat%E2%80%93Thap_Cham_railway
   7. [nature          ] Núi Chúa National Park  (why: hint; source 1268 words; est $0.0167)
        https://en.wikipedia.org/wiki/N%C3%BAi_Ch%C3%BAa_National_Park
   8. [legends         ] Legendary Champa rulers  (why: hint; source 3064 words; est $0.0177)
        https://en.wikipedia.org/wiki/Legendary_Champa_rulers
   9. [arts            ] Chams: Culture  (why: seed; source 1966 words; est $0.0171)
        https://en.wikipedia.org/wiki/Chams
  10. [history         ] Champa  (why: hint; source 10867 words; est $0.0199)
        https://en.wikipedia.org/wiki/Champa
  11. [modern          ] Ninh Thuận province  (why: hint; source 1748 words; est $0.0169)
        https://en.wikipedia.org/wiki/Ninh_Thu%E1%BA%ADn_province
  12. [people_economy  ] Churu people  (why: mentions; source 885 words; est $0.0165)
        https://en.wikipedia.org/wiki/Churu_people
  13. [religion_customs] Caodaism  (why: hint; source 4147 words; est $0.0183)
        https://en.wikipedia.org/wiki/Caodaism
  14. [food            ] Bánh xèo  (why: hint; source 591 words; est $0.0163)
        https://en.wikipedia.org/wiki/B%C3%A1nh_x%C3%A8o
  15. [legends         ] Thiên Y A Na  (why: hint; source 672 words; est $0.0163)
        https://en.wikipedia.org/wiki/Thi%C3%AAn_Y_A_Na
  16. [arts            ] Art of Champa  (why: hint; source 3422 words; est $0.0179)
        https://en.wikipedia.org/wiki/Art_of_Champa
  17. [history         ] Panduranga (Champa)  (why: hint; source 2579 words; est $0.0174)
        https://en.wikipedia.org/wiki/Panduranga_(Champa)
  18. [modern          ] Phan Thiết (city)  (why: hint; source 1588 words; est $0.0168)
        https://en.wikipedia.org/wiki/Phan_Thi%E1%BA%BFt_(city)
  19. [religion_customs] Islam in Vietnam  (why: hint; source 6986 words; est $0.0199)
        https://en.wikipedia.org/wiki/Islam_in_Vietnam
  20. [food            ] Vietnamese cuisine  (why: hint; source 6407 words; est $0.0195)
        https://en.wikipedia.org/wiki/Vietnamese_cuisine
  21. [legends         ] Whale worship  (why: hint; source 2073 words; est $0.0171)
        https://en.wikipedia.org/wiki/Whale_worship
  22. [religion_customs] Po Nagar  (why: hint; source 679 words; est $0.0163)
        https://en.wikipedia.org/wiki/Po_Nagar
  23. [religion_customs] Vietnamese folk religion  (why: hint; source 2701 words; est $0.0175)
        https://en.wikipedia.org/wiki/Vietnamese_folk_religion
  24. [religion_customs] Đạo Mẫu  (why: hint; source 995 words; est $0.0165)
        https://en.wikipedia.org/wiki/%C4%90%E1%BA%A1o_M%E1%BA%ABu
Themes: history=3, modern=3, people_economy=2, religion_customs=6, food=3, transport=1, nature=1, legends=3, arts=2
Themes with >= 2 topics: 7/9  |  thin: transport, nature
Estimated paid cost: $0.4184  |  spent by this plan: $0.0000 (dry run)
```

### ho_chi_minh_city (--max-segments 50)
```
Plan for ho_chi_minh_city (en): 48 topics, 9 themes
   1. [history         ] Ho Chi Minh City: History  (why: seed; source 1292 words; est $0.0167)
        https://en.wikipedia.org/wiki/Ho_Chi_Minh_City
   2. [modern          ] Bitexco Financial Tower  (why: hint; source 1886 words; est $0.0170)
        https://en.wikipedia.org/wiki/Bitexco_Financial_Tower
   3. [people_economy  ] Chợ Lớn  (why: hint; source 1967 words; est $0.0171)
        https://en.wikipedia.org/wiki/Ch%E1%BB%A3_L%E1%BB%9Bn
   4. [religion_customs] Caodaism  (why: hint; source 4147 words; est $0.0183)
        https://en.wikipedia.org/wiki/Caodaism
   5. [food            ] Vietnamese cuisine: Food in relation to lifestyle  (why: seed; source 1142 words; est $0.0166)
        https://en.wikipedia.org/wiki/Vietnamese_cuisine
   6. [transport       ] Ho Chi Minh City: Transport  (why: seed; source 577 words; est $0.0163)
        https://en.wikipedia.org/wiki/Ho_Chi_Minh_City
   7. [nature          ] Cần Giờ Mangrove Forest  (why: hint; source 516 words; est $0.0162)
        https://en.wikipedia.org/wiki/C%E1%BA%A7n_Gi%E1%BB%9D_Mangrove_Forest
   8. [legends         ] Lạc Long Quân  (why: hint; source 1826 words; est $0.0170)
        https://en.wikipedia.org/wiki/L%E1%BA%A1c_Long_Qu%C3%A2n
   9. [arts            ] Ho Chi Minh City Opera House  (why: hint; source 773 words; est $0.0164)
        https://en.wikipedia.org/wiki/Ho_Chi_Minh_City_Opera_House
  10. [history         ] Vietnamese cuisine: Historical influences  (why: seed; source 577 words; est $0.0163)
        https://en.wikipedia.org/wiki/Vietnamese_cuisine
  11. [modern          ] Thủ Đức (city)  (why: hint; source 902 words; est $0.0165)
        https://en.wikipedia.org/wiki/Th%E1%BB%A7_%C4%90%E1%BB%A9c_(city)
  12. [people_economy  ] Ho Chi Minh City Stock Exchange  (why: coord; source 1090 words; est $0.0166)
        https://en.wikipedia.org/wiki/Ho_Chi_Minh_City_Stock_Exchange
  13. [religion_customs] Notre-Dame Cathedral Basilica of Saigon  (why: hint; source 1122 words; est $0.0166)
        https://en.wikipedia.org/wiki/Notre-Dame_Cathedral_Basilica_of_Saigon
  14. [food            ] Vietnamese cuisine: Popular dishes  (why: seed; source 1134 words; est $0.0166)
        https://en.wikipedia.org/wiki/Vietnamese_cuisine
  15. [transport       ] Ho Chi Minh City Metro  (why: hint; source 1496 words; est $0.0168)
        https://en.wikipedia.org/wiki/Ho_Chi_Minh_City_Metro
  16. [nature          ] Bình Quới  (why: coord; source 1199 words; est $0.0166)
        https://en.wikipedia.org/wiki/B%C3%ACnh_Qu%E1%BB%9Bi
  17. [legends         ] Thiên Y A Na  (why: hint; source 672 words; est $0.0163)
        https://en.wikipedia.org/wiki/Thi%C3%AAn_Y_A_Na
  18. [arts            ] The Tale of Kieu  (why: hint; source 2263 words; est $0.0172)
        https://en.wikipedia.org/wiki/The_Tale_of_Kieu
  19. [history         ] Củ Chi tunnels  (why: hint; source 1509 words; est $0.0168)
        https://en.wikipedia.org/wiki/C%E1%BB%A7_Chi_tunnels
  20. [modern          ] Caravelle Hotel  (why: coord; source 813 words; est $0.0164)
        https://en.wikipedia.org/wiki/Caravelle_Hotel
  21. [people_economy  ] Khmer Krom  (why: mentions; source 1356 words; est $0.0167)
        https://en.wikipedia.org/wiki/Khmer_Krom
  22. [religion_customs] Tết  (why: hint; source 3353 words; est $0.0178)
        https://en.wikipedia.org/wiki/T%E1%BA%BFt
  23. [food            ] Vietnamese cuisine: Regional cuisines  (why: seed; source 613 words; est $0.0163)
        https://en.wikipedia.org/wiki/Vietnamese_cuisine
  24. [transport       ] Tan Son Nhat International Airport  (why: hint; source 4100 words; est $0.0183)
        https://en.wikipedia.org/wiki/Tan_Son_Nhat_International_Airport
  25. [nature          ] Dầu Tiếng Reservoir  (why: mentions; source 2730 words; est $0.0175)
        https://en.wikipedia.org/wiki/D%E1%BA%A7u_Ti%E1%BA%BFng_Reservoir
  26. [arts            ] Bến Dược Memorial Temple  (why: mentions; source 1163 words; est $0.0166)
        https://en.wikipedia.org/wiki/B%E1%BA%BFn_D%C6%B0%E1%BB%A3c_Memorial_Temple
  27. [history         ] Fall of Saigon  (why: hint; source 6922 words; est $0.0198)
        https://en.wikipedia.org/wiki/Fall_of_Saigon
  28. [modern          ] Cát Lái  (why: coord; source 850 words; est $0.0164)
        https://en.wikipedia.org/wiki/C%C3%A1t_L%C3%A1i
  29. [religion_customs] Đạo Mẫu  (why: hint; source 995 words; est $0.0165)
        https://en.wikipedia.org/wiki/%C4%90%E1%BA%A1o_M%E1%BA%ABu
  30. [food            ] Bánh mì  (why: hint; source 2149 words; est $0.0172)
        https://en.wikipedia.org/wiki/B%C3%A1nh_m%C3%AC
  31. [history         ] Independence Palace  (why: hint; source 568 words; est $0.0163)
        https://en.wikipedia.org/wiki/Independence_Palace
  32. [modern          ] District 1, Ho Chi Minh City  (why: coord; source 1019 words; est $0.0165)
        https://en.wikipedia.org/wiki/District_1,_Ho_Chi_Minh_City
  33. [religion_customs] Hòa Hảo  (why: mentions; source 10084 words; est $0.0199)
        https://en.wikipedia.org/wiki/H%C3%B2a_H%E1%BA%A3o
  34. [food            ] Coffee production in Vietnam  (why: hint; source 3454 words; est $0.0179)
        https://en.wikipedia.org/wiki/Coffee_production_in_Vietnam
  35. [history         ] War Remnants Museum  (why: hint; source 790 words; est $0.0164)
        https://en.wikipedia.org/wiki/War_Remnants_Museum
  36. [modern          ] Ho Chi Minh City Hall  (why: coord; source 1440 words; est $0.0168)
        https://en.wikipedia.org/wiki/Ho_Chi_Minh_City_Hall
  37. [food            ] Pho  (why: hint; source 3832 words; est $0.0181)
        https://en.wikipedia.org/wiki/Pho
  38. [history         ] Siege of Saigon  (why: category; source 1731 words; est $0.0169)
        https://en.wikipedia.org/wiki/Siege_of_Saigon
  39. [modern          ] Ho Chi Minh City University of Social Sciences and Humanities  (why: coord; source 819 words; est $0.0164)
        https://en.wikipedia.org/wiki/Ho_Chi_Minh_City_University_of_Social_Sciences_and_Humanities
  40. [history         ] Arrest and assassination of Ngo Dinh Diem  (why: mentions; source 6686 words; est $0.0197)
        https://en.wikipedia.org/wiki/Arrest_and_assassination_of_Ngo_Dinh_Diem
  41. [modern          ] Marie Curie High School  (why: coord; source 963 words; est $0.0165)
        https://en.wikipedia.org/wiki/Marie_Curie_High_School
  42. [modern          ] Royal Melbourne Institute of Technology Vietnam  (why: coord; source 1198 words; est $0.0166)
        https://en.wikipedia.org/wiki/Royal_Melbourne_Institute_of_Technology_Vietnam
  43. [modern          ] Saigon (ward)  (why: coord; source 1224 words; est $0.0166)
        https://en.wikipedia.org/wiki/Saigon_(ward)
  44. [modern          ] Hồ Tràm  (why: category; source 1468 words; est $0.0168)
        https://en.wikipedia.org/wiki/H%E1%BB%93_Tr%C3%A0m
  45. [modern          ] Phú Mỹ Hưng Urban Area  (why: mentions; source 1493 words; est $0.0168)
        https://en.wikipedia.org/wiki/Ph%C3%BA_M%E1%BB%B9_H%C6%B0ng_Urban_Area
  46. [modern          ] Saigon Hotpot  (why: mentions; source 1457 words; est $0.0168)
        https://en.wikipedia.org/wiki/Saigon_Hotpot
  47. [modern          ] Thảo Điền  (why: mentions; source 1625 words; est $0.0169)
        https://en.wikipedia.org/wiki/Th%E1%BA%A3o_%C4%90i%E1%BB%81n
  48. [modern          ] Tiền Giang province  (why: mentions; source 1644 words; est $0.0169)
        https://en.wikipedia.org/wiki/Ti%E1%BB%81n_Giang_province
Themes: history=8, modern=15, people_economy=3, religion_customs=5, food=6, transport=3, nature=3, legends=2, arts=3
Themes with >= 2 topics: 9/9
Estimated paid cost: $0.8162  |  spent by this plan: $0.0000 (dry run)
```

### boston_ma (--max-segments 50)
```
Plan for boston_ma (en): 50 topics, 9 themes
   1. [history         ] Massachusetts Bay Transportation Authority: History  (why: seed; source 2378 words; est $0.0173)
        https://en.wikipedia.org/wiki/Massachusetts_Bay_Transportation_Authority
   2. [modern          ] History of Boston: 20th century  (why: seed; source 2476 words; est $0.0173)
        https://en.wikipedia.org/wiki/History_of_Boston
   3. [people_economy  ] Boston: Demographics  (why: seed; source 816 words; est $0.0164)
        https://en.wikipedia.org/wiki/Boston
   4. [religion_customs] Old North Church  (why: hint; source 9590 words; est $0.0199)
        https://en.wikipedia.org/wiki/Old_North_Church
   5. [food            ] Cuisine of New England: Regional specialties  (why: seed; source 2173 words; est $0.0172)
        https://en.wikipedia.org/wiki/Cuisine_of_New_England
   6. [transport       ] Massachusetts Bay Transportation Authority: Funding  (why: seed; source 3149 words; est $0.0177)
        https://en.wikipedia.org/wiki/Massachusetts_Bay_Transportation_Authority
   7. [nature          ] Boston: Geography  (why: seed; source 1815 words; est $0.0170)
        https://en.wikipedia.org/wiki/Boston
   8. [legends         ] Boston Light  (why: hint; source 1154 words; est $0.0166)
        https://en.wikipedia.org/wiki/Boston_Light
   9. [arts            ] Boston: Culture  (why: seed; source 866 words; est $0.0164)
        https://en.wikipedia.org/wiki/Boston
  10. [history         ] Big Dig: Origin  (why: seed; source 1178 words; est $0.0166)
        https://en.wikipedia.org/wiki/Big_Dig
  11. [modern          ] Massachusetts Bay Transportation Authority: Management and administration  (why: seed; source 557 words; est $0.0163)
        https://en.wikipedia.org/wiki/Massachusetts_Bay_Transportation_Authority
  12. [people_economy  ] Boston: Sports  (why: seed; source 694 words; est $0.0163)
        https://en.wikipedia.org/wiki/Boston
  13. [religion_customs] Archdiocese of Boston  (why: coord; source 2094 words; est $0.0171)
        https://en.wikipedia.org/wiki/Archdiocese_of_Boston
  14. [food            ] Cuisine of New England: Traditional foods and drinks  (why: seed; source 1757 words; est $0.0169)
        https://en.wikipedia.org/wiki/Cuisine_of_New_England
  15. [transport       ] Massachusetts Bay Transportation Authority: Services  (why: seed; source 2516 words; est $0.0174)
        https://en.wikipedia.org/wiki/Massachusetts_Bay_Transportation_Authority
  16. [nature          ] Boston Common  (why: hint; source 2188 words; est $0.0172)
        https://en.wikipedia.org/wiki/Boston_Common
  17. [legends         ] Boston Strangler  (why: hint; source 2494 words; est $0.0174)
        https://en.wikipedia.org/wiki/Boston_Strangler
  18. [arts            ] Boston Public Library  (why: hint; source 4651 words; est $0.0186)
        https://en.wikipedia.org/wiki/Boston_Public_Library
  19. [history         ] History of Boston: Foundation by Europeans  (why: seed; source 974 words; est $0.0165)
        https://en.wikipedia.org/wiki/History_of_Boston
  20. [modern          ] Boston Latin School  (why: hint; source 2533 words; est $0.0174)
        https://en.wikipedia.org/wiki/Boston_Latin_School
  21. [people_economy  ] Boston: Education  (why: seed; source 671 words; est $0.0163)
        https://en.wikipedia.org/wiki/Boston
  22. [religion_customs] Cathedral of the Holy Cross (Boston)  (why: coord; source 1038 words; est $0.0165)
        https://en.wikipedia.org/wiki/Cathedral_of_the_Holy_Cross_(Boston)
  23. [food            ] Boston cream pie  (why: hint; source 568 words; est $0.0163)
        https://en.wikipedia.org/wiki/Boston_cream_pie
  24. [transport       ] Boston Harbor  (why: hint; source 2053 words; est $0.0171)
        https://en.wikipedia.org/wiki/Boston_Harbor
  25. [nature          ] Charles River  (why: hint; source 2871 words; est $0.0176)
        https://en.wikipedia.org/wiki/Charles_River
  26. [legends         ] Great Molasses Flood  (why: hint; source 2399 words; est $0.0173)
        https://en.wikipedia.org/wiki/Great_Molasses_Flood
  27. [arts            ] Boston Symphony Orchestra  (why: hint; source 4401 words; est $0.0184)
        https://en.wikipedia.org/wiki/Boston_Symphony_Orchestra
  28. [history         ] History of Boston: Colonial era  (why: seed; source 754 words; est $0.0164)
        https://en.wikipedia.org/wiki/History_of_Boston
  29. [modern          ] Boston Marathon  (why: hint; source 5313 words; est $0.0189)
        https://en.wikipedia.org/wiki/Boston_Marathon
  30. [people_economy  ] Faneuil Hall  (why: hint; source 8265 words; est $0.0199)
        https://en.wikipedia.org/wiki/Faneuil_Hall
  31. [religion_customs] King's Chapel  (why: coord; source 1248 words; est $0.0167)
        https://en.wikipedia.org/wiki/King%27s_Chapel
  32. [food            ] Clam chowder  (why: hint; source 684 words; est $0.0163)
        https://en.wikipedia.org/wiki/Clam_chowder
  33. [transport       ] Logan International Airport  (why: hint; source 5895 words; est $0.0193)
        https://en.wikipedia.org/wiki/Logan_International_Airport
  34. [nature          ] Emerald Necklace  (why: hint; source 919 words; est $0.0165)
        https://en.wikipedia.org/wiki/Emerald_Necklace
  35. [legends         ] Salem witch trials  (why: hint; source 10026 words; est $0.0199)
        https://en.wikipedia.org/wiki/Salem_witch_trials
  36. [arts            ] Fenway Park  (why: hint; source 8245 words; est $0.0199)
        https://en.wikipedia.org/wiki/Fenway_Park
  37. [history         ] History of Boston: Boston and the American Revolution, 1765–1775  (why: seed; source 627 words; est $0.0163)
        https://en.wikipedia.org/wiki/History_of_Boston
  38. [modern          ] Massachusetts Institute of Technology  (why: hint; source 10027 words; est $0.0199)
        https://en.wikipedia.org/wiki/Massachusetts_Institute_of_Technology
  39. [people_economy  ] History of Irish Americans in Boston  (why: hint; source 6367 words; est $0.0195)
        https://en.wikipedia.org/wiki/History_of_Irish_Americans_in_Boston
  40. [religion_customs] Basilica and Shrine of Our Lady of Perpetual Help  (why: category; source 1360 words; est $0.0167)
        https://en.wikipedia.org/wiki/Basilica_and_Shrine_of_Our_Lady_of_Perpetual_Help
  41. [transport       ] South Station  (why: hint; source 2823 words; est $0.0175)
        https://en.wikipedia.org/wiki/South_Station
  42. [nature          ] Back Bay Fens  (why: coord; source 3807 words; est $0.0181)
        https://en.wikipedia.org/wiki/Back_Bay_Fens
  43. [arts            ] Museum of Fine Arts, Boston  (why: hint; source 3818 words; est $0.0181)
        https://en.wikipedia.org/wiki/Museum_of_Fine_Arts,_Boston
  44. [history         ] History of Boston: Geographic expansion  (why: seed; source 550 words; est $0.0163)
        https://en.wikipedia.org/wiki/History_of_Boston
  45. [modern          ] Allston  (why: coord; source 2662 words; est $0.0174)
        https://en.wikipedia.org/wiki/Allston
  46. [people_economy  ] Boston Convention and Exhibition Center  (why: coord; source 847 words; est $0.0164)
        https://en.wikipedia.org/wiki/Boston_Convention_and_Exhibition_Center
  47. [religion_customs] Boston Book Festival  (why: category; source 3125 words; est $0.0177)
        https://en.wikipedia.org/wiki/Boston_Book_Festival
  48. [transport       ] Hanscom Field  (why: coord; source 1352 words; est $0.0167)
        https://en.wikipedia.org/wiki/Hanscom_Field
  49. [nature          ] Castle Island (Massachusetts)  (why: coord; source 831 words; est $0.0164)
        https://en.wikipedia.org/wiki/Castle_Island_(Massachusetts)
  50. [arts            ] Berklee College of Music  (why: coord; source 3142 words; est $0.0177)
        https://en.wikipedia.org/wiki/Berklee_College_of_Music
Themes: history=6, modern=6, people_economy=6, religion_customs=6, food=4, transport=6, nature=6, legends=4, arts=6
Themes with >= 2 topics: 9/9
Estimated paid cost: $0.8715  |  spent by this plan: $0.0000 (dry run)
```

### nice_cote_d_azur (--max-segments 40)
```
Plan for nice_cote_d_azur (en): 40 topics, 9 themes
   1. [history         ] Nice: History  (why: seed; source 2367 words; est $0.0173)
        https://en.wikipedia.org/wiki/Nice
   2. [modern          ] Alpes-Maritimes: Administration  (why: seed; source 647 words; est $0.0163)
        https://en.wikipedia.org/wiki/Alpes-Maritimes
   3. [people_economy  ] Grasse  (why: hint; source 1911 words; est $0.0170)
        https://en.wikipedia.org/wiki/Grasse
   4. [religion_customs] Nice Cathedral  (why: hint; source 695 words; est $0.0163)
        https://en.wikipedia.org/wiki/Nice_Cathedral
   5. [food            ] Provence wine  (why: hint; source 3181 words; est $0.0177)
        https://en.wikipedia.org/wiki/Provence_wine
   6. [transport       ] Nice Côte d'Azur Airport  (why: hint; source 543 words; est $0.0163)
        https://en.wikipedia.org/wiki/Nice_C%C3%B4te_d%27Azur_Airport
   7. [nature          ] Alpes-Maritimes: Geography  (why: seed; source 933 words; est $0.0165)
        https://en.wikipedia.org/wiki/Alpes-Maritimes
   8. [legends         ] Èze  (why: hint; source 812 words; est $0.0164)
        https://en.wikipedia.org/wiki/%C3%88ze
   9. [arts            ] Nice: Architecture  (why: seed; source 981 words; est $0.0165)
        https://en.wikipedia.org/wiki/Nice
  10. [history         ] Antibes  (why: hint; source 2990 words; est $0.0176)
        https://en.wikipedia.org/wiki/Antibes
  11. [modern          ] Hotel Negresco  (why: hint; source 716 words; est $0.0164)
        https://en.wikipedia.org/wiki/Hotel_Negresco
  12. [people_economy  ] Niçard dialect  (why: hint; source 997 words; est $0.0165)
        https://en.wikipedia.org/wiki/Ni%C3%A7ard_dialect
  13. [religion_customs] Diocese of Nice  (why: coord; source 2164 words; est $0.0172)
        https://en.wikipedia.org/wiki/Diocese_of_Nice
  14. [food            ] Salade niçoise  (why: hint; source 1364 words; est $0.0167)
        https://en.wikipedia.org/wiki/Salade_ni%C3%A7oise
  15. [transport       ] Nice tramway  (why: hint; source 1312 words; est $0.0167)
        https://en.wikipedia.org/wiki/Nice_tramway
  16. [nature          ] Mercantour National Park  (why: hint; source 622 words; est $0.0163)
        https://en.wikipedia.org/wiki/Mercantour_National_Park
  17. [arts            ] Nice: Culture  (why: seed; source 578 words; est $0.0163)
        https://en.wikipedia.org/wiki/Nice
  18. [history         ] County of Nice  (why: hint; source 1887 words; est $0.0170)
        https://en.wikipedia.org/wiki/County_of_Nice
  19. [modern          ] Andon, Alpes-Maritimes  (why: coord; source 1620 words; est $0.0169)
        https://en.wikipedia.org/wiki/Andon,_Alpes-Maritimes
  20. [transport       ] Gare du Sud  (why: coord; source 977 words; est $0.0165)
        https://en.wikipedia.org/wiki/Gare_du_Sud
  21. [nature          ] Villefranche-sur-Mer  (why: hint; source 1658 words; est $0.0169)
        https://en.wikipedia.org/wiki/Villefranche-sur-Mer
  22. [arts            ] Gustav-Adolf Mossa  (why: hint; source 1070 words; est $0.0166)
        https://en.wikipedia.org/wiki/Gustav-Adolf_Mossa
  23. [history         ] Siege of Nice  (why: hint; source 1611 words; est $0.0169)
        https://en.wikipedia.org/wiki/Siege_of_Nice
  24. [modern          ] Ascros  (why: coord; source 1065 words; est $0.0166)
        https://en.wikipedia.org/wiki/Ascros
  25. [transport       ] Isola 2000  (why: mentions; source 879 words; est $0.0164)
        https://en.wikipedia.org/wiki/Isola_2000
  26. [nature          ] Île Sainte-Marguerite  (why: coord; source 2245 words; est $0.0172)
        https://en.wikipedia.org/wiki/%C3%8Ele_Sainte-Marguerite
  27. [arts            ] Opéra de Nice  (why: hint; source 525 words; est $0.0163)
        https://en.wikipedia.org/wiki/Op%C3%A9ra_de_Nice
  28. [history         ] Terra Amata (archaeological site)  (why: hint; source 637 words; est $0.0163)
        https://en.wikipedia.org/wiki/Terra_Amata_(archaeological_site)
  29. [modern          ] Lantosque  (why: coord; source 979 words; est $0.0165)
        https://en.wikipedia.org/wiki/Lantosque
  30. [transport       ] Le Train Bleu  (why: mentions; source 1578 words; est $0.0168)
        https://en.wikipedia.org/wiki/Le_Train_Bleu
  31. [nature          ] Levant Island  (why: category; source 1097 words; est $0.0166)
        https://en.wikipedia.org/wiki/Levant_Island
  32. [arts            ] Asian Art Museum (Nice)  (why: coord; source 1005 words; est $0.0165)
        https://en.wikipedia.org/wiki/Asian_Art_Museum_(Nice)
  33. [history         ] Treaty of Turin (1860)  (why: hint; source 5105 words; est $0.0188)
        https://en.wikipedia.org/wiki/Treaty_of_Turin_(1860)
  34. [modern          ] Menton  (why: coord; source 3033 words; est $0.0177)
        https://en.wikipedia.org/wiki/Menton
  35. [nature          ] Verdon Gorge  (why: category; source 1177 words; est $0.0166)
        https://en.wikipedia.org/wiki/Verdon_Gorge
  36. [arts            ] Cannes Film Festival  (why: coord; source 3969 words; est $0.0182)
        https://en.wikipedia.org/wiki/Cannes_Film_Festival
  37. [history         ] Grotte du Vallonnet  (why: coord; source 1019 words; est $0.0165)
        https://en.wikipedia.org/wiki/Grotte_du_Vallonnet
  38. [modern          ] Monte Carlo  (why: coord; source 1862 words; est $0.0170)
        https://en.wikipedia.org/wiki/Monte_Carlo
  39. [arts            ] The Big Blue  (why: category; source 2245 words; est $0.0172)
        https://en.wikipedia.org/wiki/The_Big_Blue
  40. [history         ] Ligures  (why: category; source 7261 words; est $0.0199)
        https://en.wikipedia.org/wiki/Ligures
Themes: history=8, modern=7, people_economy=2, religion_customs=2, food=2, transport=5, nature=6, legends=1, arts=7
Themes with >= 2 topics: 8/9  |  thin: legends
Estimated paid cost: $0.6759  |  spent by this plan: $0.0000 (dry run)
```

### san_diego_ca (--max-segments 40)
```
Plan for san_diego_ca (en): 40 topics, 9 themes
   1. [history         ] History of San Diego: Ethnic and cultural groups history  (why: seed; source 2675 words; est $0.0175)
        https://en.wikipedia.org/wiki/History_of_San_Diego
   2. [modern          ] San Diego: Government  (why: seed; source 1175 words; est $0.0166)
        https://en.wikipedia.org/wiki/San_Diego
   3. [people_economy  ] Economy of San Diego  (why: seed; source 1691 words; est $0.0169)
        https://en.wikipedia.org/wiki/Economy_of_San_Diego
   4. [religion_customs] Mission San Diego de Alcalá  (why: hint; source 1893 words; est $0.0170)
        https://en.wikipedia.org/wiki/Mission_San_Diego_de_Alcal%C3%A1
   5. [food            ] Beer in San Diego County, California  (why: hint; source 2015 words; est $0.0171)
        https://en.wikipedia.org/wiki/Beer_in_San_Diego_County,_California
   6. [transport       ] San Diego Trolley: Current service  (why: seed; source 1225 words; est $0.0166)
        https://en.wikipedia.org/wiki/San_Diego_Trolley
   7. [nature          ] San Diego: Geography  (why: seed; source 1723 words; est $0.0169)
        https://en.wikipedia.org/wiki/San_Diego
   8. [legends         ] Hotel del Coronado  (why: hint; source 3370 words; est $0.0178)
        https://en.wikipedia.org/wiki/Hotel_del_Coronado
   9. [arts            ] Balboa Park (San Diego)  (why: hint; source 6573 words; est $0.0196)
        https://en.wikipedia.org/wiki/Balboa_Park_(San_Diego)
  10. [history         ] History of San Diego: War and postwar period (1941–present)  (why: seed; source 2650 words; est $0.0174)
        https://en.wikipedia.org/wiki/History_of_San_Diego
  11. [modern          ] San Diego County, California: Politics  (why: seed; source 618 words; est $0.0163)
        https://en.wikipedia.org/wiki/San_Diego_County,_California
  12. [people_economy  ] San Diego County, California: Demographics  (why: seed; source 1083 words; est $0.0166)
        https://en.wikipedia.org/wiki/San_Diego_County,_California
  13. [religion_customs] Mission San Luis Rey de Francia  (why: hint; source 1345 words; est $0.0167)
        https://en.wikipedia.org/wiki/Mission_San_Luis_Rey_de_Francia
  14. [food            ] Mission burrito  (why: hint; source 1235 words; est $0.0166)
        https://en.wikipedia.org/wiki/Mission_burrito
  15. [transport       ] San Diego Trolley: Proposed extensions  (why: seed; source 1004 words; est $0.0165)
        https://en.wikipedia.org/wiki/San_Diego_Trolley
  16. [nature          ] La Jolla  (why: hint; source 4924 words; est $0.0187)
        https://en.wikipedia.org/wiki/La_Jolla
  17. [legends         ] Kumeyaay traditional narratives  (why: hint; source 686 words; est $0.0163)
        https://en.wikipedia.org/wiki/Kumeyaay_traditional_narratives
  18. [arts            ] Chicano Park  (why: hint; source 2776 words; est $0.0175)
        https://en.wikipedia.org/wiki/Chicano_Park
  19. [history         ] San Diego Trolley: History  (why: seed; source 2460 words; est $0.0173)
        https://en.wikipedia.org/wiki/San_Diego_Trolley
  20. [modern          ] Coronado, California  (why: hint; source 3066 words; est $0.0177)
        https://en.wikipedia.org/wiki/Coronado,_California
  21. [people_economy  ] Port of San Diego: Cruise facilities  (why: seed; source 611 words; est $0.0163)
        https://en.wikipedia.org/wiki/Port_of_San_Diego
  22. [religion_customs] Roman Catholic Diocese of San Diego  (why: hint; source 1915 words; est $0.0170)
        https://en.wikipedia.org/wiki/Roman_Catholic_Diocese_of_San_Diego
  23. [food            ] Taco  (why: hint; source 2521 words; est $0.0174)
        https://en.wikipedia.org/wiki/Taco
  24. [transport       ] San Diego International Airport  (why: hint; source 4750 words; est $0.0186)
        https://en.wikipedia.org/wiki/San_Diego_International_Airport
  25. [nature          ] Mission Bay (San Diego)  (why: hint; source 2361 words; est $0.0173)
        https://en.wikipedia.org/wiki/Mission_Bay_(San_Diego)
  26. [legends         ] Whaley House (San Diego, California)  (why: hint; source 1858 words; est $0.0170)
        https://en.wikipedia.org/wiki/Whaley_House_(San_Diego,_California)
  27. [arts            ] San Diego Comic-Con  (why: hint; source 4766 words; est $0.0186)
        https://en.wikipedia.org/wiki/San_Diego_Comic-Con
  28. [history         ] History of San Diego: Emergence of a regional city (1900–1941)  (why: seed; source 2117 words; est $0.0171)
        https://en.wikipedia.org/wiki/History_of_San_Diego
  29. [modern          ] Gaslamp Quarter, San Diego  (why: hint; source 551 words; est $0.0163)
        https://en.wikipedia.org/wiki/Gaslamp_Quarter,_San_Diego
  30. [people_economy  ] Hispanics and Latinos in San Diego  (why: hint; source 2032 words; est $0.0171)
        https://en.wikipedia.org/wiki/Hispanics_and_Latinos_in_San_Diego
  31. [religion_customs] San Diego California Temple  (why: hint; source 1578 words; est $0.0168)
        https://en.wikipedia.org/wiki/San_Diego_California_Temple
  32. [transport       ] San Diego–Coronado Bridge  (why: hint; source 1786 words; est $0.0170)
        https://en.wikipedia.org/wiki/San_Diego%E2%80%93Coronado_Bridge
  33. [nature          ] Point Loma, San Diego  (why: hint; source 4399 words; est $0.0184)
        https://en.wikipedia.org/wiki/Point_Loma,_San_Diego
  34. [arts            ] Museum of Contemporary Art San Diego  (why: coord; source 1375 words; est $0.0167)
        https://en.wikipedia.org/wiki/Museum_of_Contemporary_Art_San_Diego
  35. [history         ] History of San Diego: Mexican period (1821–1848)  (why: seed; source 1065 words; est $0.0166)
        https://en.wikipedia.org/wiki/History_of_San_Diego
  36. [modern          ] SeaWorld San Diego  (why: hint; source 2296 words; est $0.0172)
        https://en.wikipedia.org/wiki/SeaWorld_San_Diego
  37. [people_economy  ] Naval Base San Diego  (why: hint; source 1187 words; est $0.0166)
        https://en.wikipedia.org/wiki/Naval_Base_San_Diego
  38. [transport       ] Cross Border Xpress  (why: coord; source 1386 words; est $0.0167)
        https://en.wikipedia.org/wiki/Cross_Border_Xpress
  39. [nature          ] San Diego Zoo  (why: hint; source 7670 words; est $0.0199)
        https://en.wikipedia.org/wiki/San_Diego_Zoo
  40. [arts            ] Old Globe Theatre  (why: coord; source 957 words; est $0.0165)
        https://en.wikipedia.org/wiki/Old_Globe_Theatre
Themes: history=5, modern=5, people_economy=5, religion_customs=4, food=3, transport=5, nature=5, legends=3, arts=5
Themes with >= 2 topics: 9/9
Estimated paid cost: $0.6887  |  spent by this plan: $0.0000 (dry run)
```
