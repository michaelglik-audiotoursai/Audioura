#!/usr/bin/env python3
"""faqs.py — LOCAL-812.

Builds a 3-question FAQ for each tour page from the REAL "People also ask"
questions harvested by the Serper keyword research (keywords.json), answered
honestly from what Audioura actually is: a free, self-guided audio-tour app.

We never invent facts about ticket prices, opening hours or third-party audio
guides (those change and we can't verify them). Instead each answer truthfully
frames how Audioura's self-guided audio tour works, and — where a question is
specifically about Audioura (duration, self-guided, cost) — answers it directly
from tours_data.json.
"""
import re


def _fmt_km(km):
    return ("%.1f" % km).rstrip("0").rstrip(".")


def _duration_answer(t):
    name = t["short_title"].split(" — ")[0]
    lm = t.get("listen_min")
    if lm:
        listen = ("about %d minute%s of narration"
                  % (lm, "" if lm == 1 else "s"))
    else:
        listen = "narration for every stop"
    walk = ""
    if t.get("distance_km"):
        walk = (" The stops are spread over roughly a %s km walk, so your total "
                "time depends on how long you linger." % _fmt_km(t["distance_km"]))
    return ("The %s tour has %d stops with %s. Because it's self-guided you can "
            "pause, linger or pick it up again whenever you like.%s"
            % (name, t["stops_count"], listen, walk))


def _selfguided_answer(t):
    return ("Yes. Audioura is a self-guided audio tour: you set your own pace "
            "and the app narrates each stop as you reach it, triggered by GPS "
            "or a tap. Triple-click your headphone button to jump between "
            "stops without looking at your phone.")


def _worth_answer(t):
    place = t["place_query"]
    return ("If you like context without a guided group or a screen, yes — "
            "this %d-stop audio tour tells the story behind each highlight at "
            "%s so you can just look and listen. It's free to start in the "
            "Audioura app." % (t["stops_count"], place))


def _cost_answer(t):
    return ("Audioura is free to download and you can start listening right "
            "away. Premium passes and tour packs unlock more tours — see the "
            "pricing page for details.")


def _free_download_answer(t):
    return ("Audioura's tours play inside the app rather than as a separate "
            "download. Install the app, open this tour and press play — the "
            "first tour is free.")


def _generic_howto(t):
    return ("Open the Audioura app, search for this tour, and press play at the "
            "first stop. The app guides you from stop to stop by voice, so your "
            "phone can stay in your pocket.")


def _ticket_answer(t):
    return ("Audioura provides the audio tour, not venue admission. Entry "
            "tickets and opening hours are set by the site itself and can "
            "change, so check the official venue before you go — then let "
            "Audioura narrate your visit once you're inside.")


# Map recurring PAA question shapes to a truthful answer generator.
_RULES = [
    (re.compile(r"\bhow (long|many hours|much time)\b", re.I), _duration_answer),
    (re.compile(r"\bself[- ]?guided|self guided|audio guide|guided tour\b", re.I),
     _selfguided_answer),
    (re.compile(r"\bworth (it|visiting|a visit)\b", re.I), _worth_answer),
    (re.compile(r"\b(ticket|entrance|entry|admission|how much does an)\b", re.I),
     _ticket_answer),
    (re.compile(r"\b(free|cost|price|how much)\b", re.I), _cost_answer),
    (re.compile(r"\bdownload|pdf|app\b", re.I), _free_download_answer),
]


def _answer_for(question, t):
    for rx, fn in _RULES:
        if rx.search(question):
            return fn(t)
    return _generic_howto(t)


# Always-available, honest fallback questions (used to top up to 3).
def _fallback_questions(t):
    return [
        ("How long is the %s audio tour?" % t["short_title"].split(" — ")[0],
         _duration_answer(t)),
        ("Is this a self-guided tour?", _selfguided_answer(t)),
        ("How much does the Audioura tour cost?", _cost_answer(t)),
        ("How do I start the tour?", _generic_howto(t)),
    ]


def build_faq(t, kw, n=3):
    """Return a list of (question, answer) pairs, length n. Prefer real PAA
    questions; de-duplicate by the answer so we don't repeat the same reply."""
    out = []
    used_answers = set()
    paa = (kw or {}).get("people_also_ask", []) or []
    # keep PAA questions short enough to be natural on-page
    for q in paa:
        if len(q) > 90:
            continue
        a = _answer_for(q, t)
        key = a[:40]
        if key in used_answers:
            continue
        out.append((q, a))
        used_answers.add(key)
        if len(out) >= n:
            break
    # top up with fallbacks if PAA didn't yield n distinct answers
    for q, a in _fallback_questions(t):
        if len(out) >= n:
            break
        key = a[:40]
        if key in used_answers:
            continue
        out.append((q, a))
        used_answers.add(key)
    return out[:n]


if __name__ == "__main__":
    import json
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    tours = json.load(open(os.path.join(here, "tours_data.json")))
    kws = {k["source_id"]: k
           for k in json.load(open(os.path.join(here, "keywords.json")))}
    for t in tours:
        print("===", t["slug"])
        for q, a in build_faq(t, kws.get(t["source_id"], {})):
            print("  Q:", q)
            print("     A:", a)
