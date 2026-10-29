#!/usr/bin/env python3
"""keyword_research.py — LOCAL-812 SEO keyword research.

Runs ONE Serper organic-search query per catalog tour (10 total) to harvest
each tour's "People also ask" questions and related searches. These inform the
H1, meta description and FAQ wording of the generated tour pages.

COST: Serper is $0.001/query (SERPER_PER_QUERY). 10 tours x 1 query = ~$0.01.
Well under the LOCAL-812 $0.20 paid-API cap.

METERING: every call goes through serper_meter.serper_search (the ONE metered
door, LOCAL-707) so the spend is recorded in paid_api_calls exactly once.

Output: website/seo/KEYWORDS.md (committed) and a machine-readable
website/seo/build/keywords.json (used by the page generator).
"""
import json
import os
import sys
import time

# Repo root is three levels up from website/seo/build/
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from serper_meter import serper_search  # the ONE metered door (LOCAL-707)

TOURS_JSON = os.path.join(_HERE, "tours_data.json")
OUT_MD = os.path.join(_HERE, "..", "KEYWORDS.md")
OUT_JSON = os.path.join(_HERE, "keywords.json")


def main():
    tours = json.load(open(TOURS_JSON, encoding="utf-8"))
    results = []
    total_credits = 0
    for t in tours:
        # Query mirrors how a traveller would search for this exact tour.
        query = "%s audio tour" % t["place_query"]
        r = serper_search(query, num=8)
        credits = r.get("credits", 0)
        total_credits += credits or 0
        paa = [p.get("question") for p in r.get("peopleAlsoAsk", []) if p.get("question")]
        paa_full = [{"question": p.get("question"), "snippet": p.get("snippet", "")}
                    for p in r.get("peopleAlsoAsk", [])]
        related = [s.get("query") for s in r.get("relatedSearches", []) if s.get("query")]
        results.append({
            "source_id": t["source_id"],
            "slug": t["slug"],
            "city": t["city"],
            "query": query,
            "people_also_ask": paa,
            "people_also_ask_full": paa_full,
            "related_searches": related,
        })
        print("  %s -> PAA %d, related %d (credits=%s)" %
              (t["slug"], len(paa), len(related), credits))
        time.sleep(0.4)

    json.dump(results, open(OUT_JSON, "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)

    # Render KEYWORDS.md
    lines = []
    lines.append("# LOCAL-812 — SEO keyword research (Serper)\n")
    lines.append(
        "Source: Serper organic-search API (`google.serper.dev/search`), "
        "routed through the metered door `serper_meter.serper_search` "
        "(LOCAL-707). One query per tour, `num=8`.\n")
    lines.append(
        "**Cost:** Serper bills $0.001/query. 10 queries ≈ **$0.01** "
        "(cap for this task: $0.20). Credits reported by the API this run: "
        "**%d**.\n" % total_credits)
    lines.append(
        "These \"People also ask\" questions and related searches drove the "
        "H1 phrasing, 120–160-char meta descriptions and the 3-question FAQ "
        "on each tour page.\n")
    for res in results:
        lines.append("\n---\n")
        lines.append("## %s\n" % res["slug"])
        lines.append("Query: `%s`\n" % res["query"])
        lines.append("\n**People also ask:**\n")
        if res["people_also_ask"]:
            for q in res["people_also_ask"]:
                lines.append("- %s" % q)
        else:
            lines.append("- _(none returned)_")
        lines.append("\n**Related searches:**\n")
        if res["related_searches"]:
            for q in res["related_searches"]:
                lines.append("- %s" % q)
        else:
            lines.append("- _(none returned)_")
        lines.append("")
    open(OUT_MD, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\nTotal credits this run: %d  (~$%.3f)" %
          (total_credits, total_credits * 0.001))
    print("Wrote %s and %s" % (OUT_MD, OUT_JSON))


if __name__ == "__main__":
    main()
