#!/usr/bin/env python3
"""teasers.py — LOCAL-812.

Turn a stop's raw 'Orientation' narration (story_source) into a short, 1–2
sentence teaser that is REWRITTEN, not the full narration verbatim. The page
must not republish the audio; it should entice.

Strategy:
  1. Drop the stock navigation/positioning preamble sentences that open almost
     every stop ("You are about to…", "Stand/Face/Pause…", "From the X Metro…").
  2. Keep the first 1–2 substantive sentences that actually describe the place
     or artwork.
  3. Hard-cap at ~220 chars on a sentence boundary so the teaser is a taste,
     not a transcript.
  4. Fall back to a title/type sentence when there is no usable prose.
"""
import re

# Sentence openers that are navigation/positioning filler, not description.
_PREAMBLE_RE = re.compile(
    r"^(you are about to|your first stop|from the [^.]*metro|stand\b|standing\b|"
    r"face\b|facing\b|pause\b|begin\b|as you (approach|arrive|stand|walk)|step\b|"
    r"from (this|here|plaça|place|several|just)|in this room|direct your|"
    r"locate |look for|the best vantage|this vantage|walk down|walk towards|"
    r"position (yourself|your)|head (south|north|east|west|towards|down)|"
    r"turn (left|right)|continue )",
    re.I,
)

# A sentence is "substantive" if it carries a concrete descriptive hook:
# a year, a proper name, or clear descriptive verbs — not just positioning.
_SUBSTANTIVE_RE = re.compile(
    r"\b(1[0-9]{3}|20[0-9]{2})\b|"            # a year
    r"\b(was|is|were|became|built|founded|commissioned|designed|painted|"
    r"created|stands|rises|houses|holds|known|home to|one of|opened|"
    r"completed|dedicated)\b",
    re.I,
)


def _split_sentences(text):
    # naive but robust sentence splitter on . ! ? followed by space + capital
    text = re.sub(r"\s+", " ", text or "").strip()
    # Repair a known source defect: a missing regnal numeral + period after
    # "King Louis" runs two sentences together ("…King Louis For centuries…").
    text = re.sub(r"King Louis For centuries",
                  "King Louis VI. For centuries", text)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[\"“A-ZÀ-Ý0-9])", text)
    return [p.strip() for p in parts if p.strip()]


def make_teaser(story_source, title, type_label, max_len=220):
    sents = _split_sentences(story_source)
    # drop navigation/positioning sentences anywhere in the lead-in
    non_nav = [s for s in sents if not _PREAMBLE_RE.match(s)]
    # prefer the first substantive sentence as the teaser's opener
    kept = []
    substantive = [s for s in non_nav if _SUBSTANTIVE_RE.search(s)]
    if substantive:
        # start from the first substantive sentence, keep the flow after it
        start = non_nav.index(substantive[0])
        kept = non_nav[start:]
    else:
        kept = non_nav
    if not kept:
        kept = sents  # everything looked like preamble; keep original order

    teaser = ""
    for s in kept:
        candidate = (teaser + " " + s).strip()
        if len(candidate) > max_len:
            if teaser:
                break
            # single long sentence: cut at a word boundary, add ellipsis
            cut = s[:max_len].rsplit(" ", 1)[0].rstrip(",;:—- ")
            teaser = cut + "…"
            break
        teaser = candidate
        if len(teaser) >= max_len * 0.6:  # one strong sentence is enough
            break

    teaser = teaser.strip()
    if not teaser:
        teaser = ("%s — one of the highlights on this tour, with its full story "
                  "narrated in the Audioura app." % title)
    return teaser


if __name__ == "__main__":
    import json
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    tours = json.load(open(os.path.join(here, "tours_data.json")))
    for t in tours:
        print("===", t["slug"])
        for s in t["stops"]:
            tz = make_teaser(s["story_source"], s["title"], s["type"])
            print("  [%d] %s\n      %s" % (len(tz), s["title"], tz))
