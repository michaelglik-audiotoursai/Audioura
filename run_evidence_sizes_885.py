#!/usr/bin/env python3
"""LOCAL-885: per-stop evidence size, before (lead only) vs after (selected passages).
FREE MediaWiki/Wikidata calls only; no DB (use_cache=False), no OpenAI, no Serper."""
import re
import sys
import landmark_wikipedia_evidence as lwe

CITY, LOCATION = "Ho Chi Minh City", "Ho Chi Minh City, Vietnam"
STOPS = [("Cathedral", 10.779722, 106.699167), ("Post Office", 10.780000, 106.700000),
         ("Book Street", 10.780573, 106.699695), ("Independence Palace", 10.777050, 106.695370),
         ("War Remnants Museum", 10.779500, 106.692000), ("Opera House", 10.776390, 106.702780),
         ("City Hall", 10.776470, 106.700970), ("Café Apartments 42", 10.774089, 106.704056),
         ("Bạch Đằng Pier", 10.775240, 106.707002), ("Thi Bar", 10.767660, 106.693960)]
# canonical names the pipeline's resolver gives these short names (LOCAL-882/884 pins)
ALIASES = {"Cathedral": ["Notre-Dame Cathedral Basilica of Saigon"],
           "Post Office": ["Saigon Central Post Office"],
           "Opera House": ["Saigon Opera House"],
           "City Hall": ["Ho Chi Minh City Hall"],
           "Independence Palace": ["Independence Palace"],
           "War Remnants Museum": ["War Remnants Museum"]}
CHECKS = {"Independence Palace": [("30 April 1975 tank", r"30 April 1975|tank")],
          "Opera House": [("1944 bombing", r"1944")],
          "Post Office": [("Vildieu", r"Vildieu"), ("Foulhoux", r"Foulhoux")]}


def main():
    rows = []
    for name, lat, lng in STOPS:
        for lang in lwe.local_languages(LOCATION):
            art = None
            bases = [name] + ALIASES.get(name, [])
            tried = [(b, b) for b in bases] + [(f"{b} {CITY}", b) for b in bases]
            for q, base in tried:
                art = lwe.fetch_article(q, lang, use_cache=False, pin=(lat, lng), city=CITY,
                                        match_name=base)
                if art:
                    break
            if not art:
                rows.append((name, lang, "(no article)", 0, 0, 0, 0, "", ""))
                continue
            ft = art.get("full_text") or ""
            psg = lwe.select_passages(ft, art["lead"])
            before = len(art["lead"]) + len(art.get("infobox", ""))
            after = before + len(psg)
            chk = "; ".join(f"{l}: {'YES' if re.search(rx, psg) else 'no'}"
                            f"{' (in full text)' if re.search(rx, ft) and not re.search(rx, psg) else ''}"
                            for l, rx in CHECKS.get(name, [])) if lang == "en" else ""
            rows.append((name, lang, art["title"], before, after, len(ft), len(psg), chk,
                         ", ".join(lwe.article_sections(ft)[:8])))
    out = ["# LOCAL-885 evidence sizes (free MediaWiki API, no OpenAI/Serper)", "",
           "before = lead + infobox chars (LOCAL-884); after = before + selected passages "
           "(cap 6,000). full = whole-article chars fetched (cap 20,000).", "",
           "| Stop | lang | article | before | after | full | passages | target ≥3000 | checks |",
           "|---|---|---|---|---|---|---|---|---|"]
    for n, lg, t, b, a, f, p, c, secs in rows:
        ok = "n/a" if t == "(no article)" else ("OK" if a >= 3000 else "BELOW")
        out.append(f"| {n} | {lg} | {t} | {b} | {a} | {f} | {p} | {ok} | {c} |")
    print("\n".join(out))


if __name__ == "__main__":
    main()
