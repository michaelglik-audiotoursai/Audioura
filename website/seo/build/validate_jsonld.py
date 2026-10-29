#!/usr/bin/env python3
"""validate_jsonld.py — LOCAL-812 offline JSON-LD check.

For every generated HTML page, extract each <script type="application/ld+json">
block and assert:
  - it is valid JSON,
  - it has @context = schema.org and a @type,
  - type-specific required/expected properties are present and well-formed.

No network. Exits non-zero if any block fails.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BLOCK_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.S)

EXPECT = {
    "TouristTrip": ["name", "description", "url", "itinerary", "subjectOf"],
    "BreadcrumbList": ["itemListElement"],
    "FAQPage": ["mainEntity"],
    "ItemList": ["itemListElement"],
    "Product": ["name", "offers"],
}


def check_obj(obj, page, errs):
    if not isinstance(obj, dict):
        errs.append("%s: top-level JSON-LD is not an object" % page)
        return
    ctx = obj.get("@context", "")
    if "schema.org" not in str(ctx):
        errs.append("%s: @context missing schema.org (%r)" % (page, ctx))
    typ = obj.get("@type")
    if not typ:
        errs.append("%s: missing @type" % page)
        return
    for prop in EXPECT.get(typ, []):
        if prop not in obj:
            errs.append("%s: %s missing '%s'" % (page, typ, prop))

    # deep checks
    if typ == "TouristTrip":
        it = obj.get("itinerary", {})
        items = it.get("itemListElement", []) if isinstance(it, dict) else []
        if not items:
            errs.append("%s: TouristTrip itinerary empty" % page)
        for el in items:
            item = el.get("item", {})
            if item.get("@type") != "TouristAttraction":
                errs.append("%s: itinerary item not TouristAttraction" % page)
            geo = item.get("geo", {})
            if geo.get("@type") != "GeoCoordinates" or \
                    "latitude" not in geo or "longitude" not in geo:
                errs.append("%s: attraction '%s' bad geo"
                            % (page, item.get("name")))
        ao = obj.get("subjectOf", {})
        if ao.get("@type") != "AudioObject" or not ao.get("contentUrl"):
            errs.append("%s: subjectOf not a valid AudioObject" % page)
    if typ == "FAQPage":
        for q in obj.get("mainEntity", []):
            if q.get("@type") != "Question" or not q.get("name"):
                errs.append("%s: FAQ question malformed" % page)
            ans = q.get("acceptedAnswer", {})
            if ans.get("@type") != "Answer" or not ans.get("text"):
                errs.append("%s: FAQ answer malformed" % page)
    if typ == "BreadcrumbList":
        for li in obj.get("itemListElement", []):
            if li.get("@type") != "ListItem" or "position" not in li:
                errs.append("%s: breadcrumb ListItem malformed" % page)
    if typ == "Product":
        offers = obj.get("offers", [])
        if not offers:
            errs.append("%s: Product has no offers" % page)
        for o in offers:
            if o.get("@type") != "Offer" or "price" not in o or \
                    o.get("priceCurrency") != "USD":
                errs.append("%s: Offer malformed (%r)" % (page, o.get("name")))


def main():
    pages = glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True)
    pages = [p for p in pages
             if "/build/" not in p and "/docs/" not in p]
    errs = []
    total_blocks = 0
    for p in sorted(pages):
        rel = os.path.relpath(p, ROOT)
        html = open(p, encoding="utf-8").read()
        blocks = BLOCK_RE.findall(html)
        if not blocks:
            errs.append("%s: no JSON-LD found" % rel)
        for b in blocks:
            total_blocks += 1
            try:
                obj = json.loads(b)
            except json.JSONDecodeError as e:
                errs.append("%s: invalid JSON (%s)" % (rel, e))
                continue
            check_obj(obj, rel, errs)

    print("Checked %d pages, %d JSON-LD blocks." % (len(pages), total_blocks))
    if errs:
        print("\nFAILURES (%d):" % len(errs))
        for e in errs:
            print("  - " + e)
        sys.exit(1)
    print("All JSON-LD blocks valid.")


if __name__ == "__main__":
    main()
