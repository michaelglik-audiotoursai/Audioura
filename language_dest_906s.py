"""[LOCAL-906S] Delivery guards from the 906R Mac proofs (two 551 runs + the drive + 552). Pure, free, never raises. Generic names (D769).

1.  foreign-language sentence -- "<Ward> la mot phuong thuoc tinh <Province>, Viet Nam." in an English tour is never delivered (final guard and
                                  every refill candidate). Stop-word + diacritic detector (no new dependency).
2.  caption variants          -- "A person cleans a trash-strewn beach." / "<Place>, <Place>, A person cleans ..." is a photo caption.
3.  a stop title as a place   -- a dash title / topic title is never a subject or a named place: the proper-name core, else "This area".
4.  "known for <verb> ..."     -- a list of bare verbs after "known for" is never delivered (clause cut, else the sentence).
5.  fragments                 -- "As you explore, known for ...", "<Name>, located about 40 minutes away in <District>." (no main verb),
                                  "one of the longest <Name> statue on a mountains" (number agreement: plural noun, or the clause goes).
6.  dangling Their / They     -- no plural referent in the stop -> the sentence goes.
7.  destination stop          -- template filler ("This stop connects naturally to the earlier moments on your tour.") is dropped; a stop
                                  that has NO supported sentence is refilled from its evidence, else it gets the D760 disclosure body.
8.  cross-stop measures       -- one object, one value per tour: the article's value, logged.
9.  operator / closing copy   -- "These tours often start from ...", "recommended ways to get here", "This tour showcases ...",
                                  "Each stop invites ...".
10. period claims             -- "installed in the early 2000s" / "the late 19th century" that no evidence of the stop carries (D771), and
                                  "significantly increasing ..." effect tails that no evidence carries.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

import leftovers_906c as c
import route_content_896 as rc

TAG = "[LOCAL-906S]"


def _emit(log: Optional[Callable]) -> Callable:
    return log or (lambda _m: None)


# ══ 1. a sentence in another language ════════════════════════════════════════════════════════════════════
_EN_STOP = frozenset("the a an and or of in on at to for from with by is are was were be been has have had it its this that these those "
                     "as which who whose their there here you your we our not but also into over near about after before during "
                     "can will would may one two many most some all than then when while where".split())
_FOREIGN_STOP: Dict[str, frozenset] = {
    "vi": frozenset("là một thuộc của và các những được trong tỉnh phường không có này cho với tại ở đã khi để người năm thành phố "
                    "huyện xã nằm là cũng như từ đến rất nhiều".split()),
    "es": frozenset("el los las del es una que por con para su se fue están está como más pero también".split()),
    "fr": frozenset("les des du est une et dans avec sur au aux pour qui sont été fait très aussi mais".split()),
    "de": frozenset("der die das und ist ein eine nicht mit von den dem zu auf im sich auch wurde sind".split()),
    "it": frozenset("il gli del della è una che per con nel sono dei delle anche molto".split()),
    "pt": frozenset("os as do da é um uma que para com em no na não são foi também muito".split()),
    "id": frozenset("yang dan di dengan untuk adalah ini itu dari pada ke juga sebuah dalam".split()),
}
# letters that exist in Vietnamese only (or in practice only there): a name like "Mũi Né" has two of them
_VI_LETTERS = set("ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ"
                  "ĂÂĐÊÔƠƯẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼẾỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴỶỸ")
_WORD = re.compile(r"[^\W\d_][\w'’\-]*", re.UNICODE)


def _lower_words(x: str) -> List[str]:
    return [w.lower() for w in _WORD.findall(x or "")]


def _en_share(words: List[str]) -> float:
    return sum(1 for w in words if w in _EN_STOP) / max(len(words), 1)


def tour_is_english(text: str) -> bool:
    """The tour's own language is English when its prose is full of English function words (guards only run on those)."""
    words = _lower_words(re.sub(r"(?m)^(?:Stop\s+\d+:|Address:|Coordinates:|Type/Specialty:).*$", " ", text or ""))
    return len(words) < 20 or _en_share(words) >= 0.2


def foreign_language(x: str) -> Optional[str]:
    """The language code of ``x`` when it is clearly NOT English (a sentence of >= 4 words), else None. A sentence with a
    few foreign place names but English function words (\"Visit Mũi Né in the Lâm Đồng Province.\") is English."""
    words = _lower_words(x)
    if len(words) < 4 or _en_share(words) >= 0.2:
        return None
    hits = {lang: sum(1 for w in words if w in sw) for lang, sw in _FOREIGN_STOP.items()}
    lang, n = max(hits.items(), key=lambda kv: kv[1])
    if n >= 2 and n / len(words) >= 0.15:
        return lang
    marked = sum(1 for w in re.findall(r"\S+", x or "") if any(ch in _VI_LETTERS for ch in w))
    if marked >= 3 and marked / len(words) >= 0.4:
        return "vi"
    return None


# ══ 2. caption variants ══════════════════════════════════════════════════════════════════════════════════
_CAP_NOUN = (r"(?:person|people|man|men|woman|women|child|children|boy|girl|couple|family|group(?:\s+of\s+\w+)?|tourists?|visitors?|"
             r"hikers?|travell?ers?|swimmers?|workers?|monks?|locals?|fishermen|fisherman|vendors?)")
_CAP_NOT_VERB = frozenset("has is was does lives serves remains stays".split())
_CAPTION_VARIANT = re.compile(r"^(?:(?:[A-ZÀ-Ỹ<][^,.!?]{1,40},\s*){0,2})(?:A|An)\s+" + _CAP_NOUN + r"\s+(?P<v>[a-z]{3,}s|[a-z]+ing)\b")


def caption_variant(x: str) -> bool:
    """\"A person cleans a trash-strewn beach.\" / \"<Place>, <Place>, A person cleans ...\": a photo caption (a short sentence of its own)."""
    s = (x or "").strip()
    if len(s.split()) > 20:
        return False
    m = _CAPTION_VARIANT.match(s)
    return bool(m) and m.group("v").lower() not in _CAP_NOT_VERB


# ══ 4. "known for <bare verb>" ═══════════════════════════════════════════════════════════════════════════
_BARE_VERBS = (r"(?:visit|taste|learn|see|explore|try|enjoy|watch|walk|climb|hike|experience|discover|buy|eat|stay|take|ride|swim|"
               r"photograph|admire|sample|pick|join|shop|relax|dive|surf|sail|cycle|bike|drive|meet|find|feel|witness|observe)")
_KNOWN_FOR_VERB = re.compile(r"(?i)\bknown\s+for\s+" + _BARE_VERBS + r"\b(?!ing\b|s\b)")


def known_for_verb_cut(x: str) -> Optional[str]:
    """The sentence without its \", known for visit ..., taste ...\" tail (None when the head is too short to stand)."""
    m = _KNOWN_FOR_VERB.search(x)
    if not m:
        return None
    head = x[:m.start()].rstrip(" ,;")
    if len(head.split()) < 5 or re.search(r"(?i)\b(?:it|this|that|he|she|they)\s+(?:is|are|was|were)$", head) or rc.is_fragment(head + "."):
        return None
    return head + "."


# ══ 5. fragments ═════════════════════════════════════════════════════════════════════════════════════════
_AS_YOU_PART = re.compile(r"(?i)^(?:as|when|while|if)\s+you\s+[\w\-]+(?:\s+\w+){0,2},\s*(?:known|located|situated|famous|found|set|nestled)\b")
_NAME_PART = re.compile(r"^(?:The\s+)?[A-ZÀ-Ỹ][\w'’\-]*(?:\s+(?:of|de|the|and)?\s*[A-ZÀ-Ỹ][\w'’\-]*){0,4},\s+"
                        r"(?:located|situated|nestled|perched|positioned|found|set|known|lying|standing)\b")
_FINITE = re.compile(r"(?i)\b(?:is|are|was|were|has|have|had|stands?|sits?|rises?|offers?|features?|holds?|lies|remains?|boasts?|draws?|"
                     r"attracts?|makes?|houses?|contains?|serves?|will|can|may|becomes?|became|provides?|includes?|forms?|dominates?|"
                     r"overlooks?|towers?|looms?|marks?|welcomes?|shelters?)\b")


def fragment_reason(x: str) -> Optional[str]:
    s = (x or "").strip()
    if _AS_YOU_PART.match(s):
        return "a subordinate clause + a bare participle phrase (no main clause)"
    m = _NAME_PART.match(s)
    if m and not _FINITE.search(s[m.end():]):
        return "a name + a participle phrase (no main verb)"
    return None


_AGREE_NOUN = (r"(?:statue|tower|temple|pagoda|bridge|building|church|cathedral|monument|landmark|structure|beach|mosque|shrine|"
               r"castle|palace|waterfall|lake|dune|cave|garden|market|monastery|sculpture|fortress|lighthouse|site)")
_ONE_OF_SING = re.compile(r"(?i)\bone\s+of\s+the\s+(?P<sup>(?:[a-z]+est|most\s+[a-z]+|best|least\s+[a-z]+))\s+(?P<mid>(?:[\w'’\-]+\s+){0,3}?)"
                          r"(?P<noun>" + _AGREE_NOUN + r")\b(?!s\b|\s*(?:of|that|which|who))")
_A_PLURAL = re.compile(r"(?i)\b(?P<prep>on|in|at)\s+an?\s+(?P<pl>(?:mountain|hill|island|lake|beach|temple|river|cliff|peak)s)\b")


def _plural(n: str) -> str:
    lo = n.lower()
    if lo.endswith("y") and lo[-2:-1] not in "aeiou":
        return n[:-1] + "ies"
    if lo.endswith(("ch", "sh", "s", "x")):
        return n + "es"
    return n + "s"


def fix_agreement(x: str) -> Optional[str]:
    """\"one of the longest <Name> statue on a mountains in Asia\" -> the noun in the plural and the broken \"on a mountains\" tail cut;
    None when the sentence has no such case."""
    m = _ONE_OF_SING.search(x)
    if not m:
        return None
    new = x[:m.start("noun")] + _plural(m.group("noun")) + x[m.end("noun"):]
    pm = _A_PLURAL.search(new, m.start("noun"))
    if pm:
        new = new[:pm.start()].rstrip(" ,") + "."
    return new if new.strip(". ") and not rc.is_fragment(new) else None


# ══ 6. Their / They with no plural referent ══════════════════════════════════════════════════════════════
_THEIR = re.compile(r"(?i)\b(?:their|they|them|themselves|theirs)\b")
_PLURAL_AGENT = re.compile(
    r"(?i)\b(?:monks|nuns|pilgrims|visitors|tourists|villagers|locals|residents|people|peoples|fishermen|farmers|builders|artisans|craftsmen|"
    r"craftspeople|workers|families|founders|worshippers|worshipers|devotees|followers|disciples|settlers|travell?ers|ancestors|kings|"
    r"emperors|rulers|soldiers|artists|sculptors|monarchs|inhabitants|natives|merchants|traders|fishers|children|men|women|brothers|"
    r"sisters|couples|townspeople|community|communities|dynasty|dynasties|family|crew|team|congregation|clergy|nobles|priests|"
    r"architects|engineers|creators|owners|guides|hosts|guests|crowds|vendors|sellers|growers|cultivators|explorers|colonists|"
    r"missionaries|monarchy|pagodas|temples|towers|shrines|buildings|statues|houses|villages|farms|plantations|beaches|dunes|mountains|"
    r"hills|islands|boats|ships|halls|gardens|stalls|shops|markets)\b")
_NUM_PLURAL = re.compile(r"(?i)\b(?:two|three|four|five|six|seven|eight|nine|ten|both|several|many|numerous|dozens\s+of|hundreds\s+of)\s+"
                         r"(?:[\w\-]+\s+){0,2}?(?P<n>[a-z]+s)\b")
_NOT_REFERENT = frozenset("centuries years decades meters metres kilometers kilometres miles hours minutes days months weeks feet times "
                          "steps degrees seconds generations".split())
_NAME_PAIR = re.compile(r"[A-ZÀ-Ỹ][\w'’\-]+(?:\s+[A-ZÀ-Ỹ][\w'’\-]+){0,3}\s+and\s+(?:the\s+)?[A-ZÀ-Ỹ][\w'’\-]+")


def has_plural_referent(text: str) -> bool:
    t = text or ""
    if _PLURAL_AGENT.search(t) or _NAME_PAIR.search(t):
        return True
    return any(m.group("n").lower() not in _NOT_REFERENT for m in _NUM_PLURAL.finditer(t))


# ══ 7. template filler of the "this stop connects" family ════════════════════════════════════════════════
_CONNECTS = re.compile(r"(?i)^(?:this|the)\s+(?:stop|place|site|spot|location|area|moment)\s+(?:connects?|ties|links|flows|follows|builds|"
                       r"continues|echoes|relates)\b[^.!?]{0,60}\b(?:earlier|previous|preceding|last|tour|journey|moments?|stops?)\b")


def is_connects_filler(x: str) -> bool:
    return bool(_CONNECTS.match((x or "").strip()))


def _is_filler(x: str) -> bool:
    try:
        import splice_copy_906r as sp
        return sp._is_template_filler(x) or is_connects_filler(x)
    except Exception:  # pragma: no cover
        return is_connects_filler(x)


# ══ 9. operator / closing variants ═══════════════════════════════════════════════════════════════════════
_VARIANTS = [re.compile(p) for p in (
    r"(?i)^these\s+tours?\b",
    r"(?i)\btours?\s+(?:often|usually|typically|generally|commonly)\s+(?:start|begin|depart|leave|run)\b",
    r"(?i)\boffer\s+private\s+(?:charters?|tours?|transfers?)\b",
    r"(?i)\b(?:recommended|suggested|best)\s+ways?\s+to\s+(?:get|reach|travel|go)\s+(?:here|there|to)\b",
    r"(?i)\band\s+explore\s+nearby\s+attractions\b|\bexplore\s+nearby\s+attractions\.?$",
    r"(?i)\bpersonali[sz]ed\s+experience\b",
    r"(?i)^this\s+tour\s+(?:showcases?|highlights?|celebrates?|captures?|explores?|brings|offers|reveals|reflects|weaves|blends|combines|"
    r"tells|takes|invites|journeys|traces|illustrates|demonstrates)\b",
    r"(?i)^(?:exploring|visiting|seeing|discovering)\s+(?:these|all\s+(?:of\s+)?these)\s+(?:sites|stops|places|spots|landmarks|locations)\b[^.!?]{0,20}\b(?:allows?|lets?|helps?|gives?)\s+you\b",
    r"(?i)\bcreating\s+(?:lasting|unforgettable|lifelong|lifetime)\s+memories\b",
    r"(?i)^by\s+(?:exploring|visiting|seeing|discovering)\s+(?:these|all\s+(?:of\s+)?these|all\s+the)\b[^.!?]{0,80}?,?\s*you\s+(?:will\s+|can\s+)?(?:gain|get|discover|learn)\b",   # [LOCAL-906W]
    r"(?i)^(?:each|every)\s+(?:stop|place|site)\s+(?:invites?|offers?|reveals?|reflects?|tells?|shows?|captures?|adds?|brings?|"
    r"holds?|deepens?|reminds?)\b",
)]


def variant_reason(x: str) -> Optional[str]:
    s = (x or "").strip()
    return "operator / closing copy" if any(rx.search(s) for rx in _VARIANTS) else None


# ══ 10. a period / effect claim no evidence carries ══════════════════════════════════════════════════════
_DECADE = re.compile(r"(?i)\b(?:(?:in|during|by|from|since|until|through|throughout)\s+)?the\s+(?:(?:early|mid|late)[\s\-]+)?(?P<y>\d{4})s\b")
_CENTURY = re.compile(r"(?i)\b(?:in|during|by|from|since|until|throughout)\s+the\s+(?:(?:early|mid|late)[\s\-]+)?(?P<n>\d{1,2})(?:st|nd|rd|th)\s+century\b")
_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_DATED_CLAUSE = re.compile(r",\s*(?:\w+\s+){0,3}?(?:installed|built|opened|constructed|completed|launched|added|introduced|created|founded|"
                           r"established|erected|renovated|restored|developed)\s+(?:\w+\s+){0,2}?(?:in|during|by)\s+the\s+(?:(?:early|mid|late)[\s\-]+)?"
                           r"(?:\d{4}s|\d{1,2}(?:st|nd|rd|th)\s+century)\s*,", re.I)
_EFFECT_TAIL = re.compile(r",?\s*(?:significantly|greatly|dramatically|substantially|vastly|sharply|hugely|massively)\s+"
                          r"(?:increasing|boosting|improving|enhancing|expanding|raising|transforming|reducing|decreasing|growing|"
                          r"changing|reshaping)\b[^.!?]*")


def _period_supported(x: str, ev: str) -> bool:
    years = [int(y) for y in _YEAR.findall(ev or "")]
    low = (ev or "").lower()
    for m in _DECADE.finditer(x):
        d = int(m.group("y"))
        if not (any(d <= y <= d + 9 for y in years) or f"{d}s" in low):
            return False
    for m in _CENTURY.finditer(x):
        n = int(m.group("n"))
        if not (any((n - 1) * 100 < y <= n * 100 for y in years) or re.search(rf"\b{n}(?:st|nd|rd|th)\s+century\b", low)):
            return False
    return True


def period_rewrite(x: str, ev: str) -> Optional[Tuple[str, str]]:
    """(new sentence or "" for the sentence, why) when ``x`` holds a decade / century phrase or an effect tail the stop's evidence does not
    carry; None when nothing is unsupported or the stop has no evidence to judge by."""
    if not (ev or "").strip():
        return None
    new, why = x, ""
    if (_DECADE.search(new) or _CENTURY.search(new)) and not _period_supported(new, ev):
        m = _DATED_CLAUSE.search(new)
        cut = None
        if m:
            cut = re.sub(r"\s+", " ", new[:m.start()] + new[m.end():]).strip()
        if cut and not (_DECADE.search(cut) or _CENTURY.search(cut)) and not rc.is_fragment(cut):
            new, why = cut, "a period claim no evidence carries (clause cut)"
        else:
            return "", "a period claim no evidence carries"
    m = _EFFECT_TAIL.search(new)
    if m:
        tail = {w for w in rc._content_tokens(m.group(0)) if w not in {"significantly", "greatly", "dramatically", "substantially"}}
        if tail and len(tail & rc._content_tokens(ev)) / len(tail) < 0.5:
            head = new[:m.start()].rstrip(" ,")
            if len(head.split()) >= 6 and not rc.is_fragment(head + "."):
                new, why = head + ".", (why + "; " if why else "") + "an effect tail no evidence carries (clause cut)"
            else:
                return "", "an effect claim no evidence carries"
    return (new, why) if why else None


# ══ 3. a stop title used as a place name ═════════════════════════════════════════════════════════════════
_DASH = re.compile(r"\s+[–—-]\s+")


def _title_core(title: str) -> Optional[str]:
    """The proper-name core of a stop title, None for a topic title (\"Dragon fruit country\")."""
    try:
        import anchor_evidence_906m as a
        if a.is_topic_like(title):
            return None
        cores = a.name_cores(title)
        return cores[0] if cores else None
    except Exception:  # pragma: no cover
        return None


def _is_title_risky(title: str) -> bool:
    if _DASH.search(title or ""):
        return True
    try:
        import anchor_evidence_906m as a
        return a.is_topic_like(title or "")
    except Exception:  # pragma: no cover
        return False


def _title_rx(title: str) -> "re.Pattern":
    parts = [p for p in _DASH.split(title.strip()) if p]
    body = r"\s*[–—-]\s*".join(r"\s+".join(re.escape(w) for w in p.split()) for p in parts)
    return re.compile(r"(?i)(?:\bthe\s+)?" + body)


def title_as_place(x: str, title: str) -> Optional[str]:
    """``x`` with the stop title replaced (None when the title is not in it, or is not a dash / topic title)."""
    if not title or not _is_title_risky(title):
        return None
    rx = _title_rx(title)
    m = rx.search(x)
    if not m:
        return None
    core = _title_core(title)
    look = re.match(r"(?i)^(?:look|watch|keep\s+an\s+eye)\s+(?:out\s+)?for\s+$", x[:m.start()])
    after = re.match(r"\s+(?:in|near|around|at)\s+(?P<rest>[^.!?]+)", x[m.end():])
    if look and after:
        return "You are now " + x[m.end():].strip()
    out, pos = [], 0
    for mm in rx.finditer(x):
        sub = core or ("This area" if mm.start() == 0 else "this area")
        out.append(x[pos:mm.start()] + sub)
        pos = mm.end()
    out.append(x[pos:])
    new = "".join(out)
    return new[:1].upper() + new[1:]


# ══ the sentence pass (body + Orientation of every stop) ═════════════════════════════════════════════════
def _ev_blob(ev_map: Dict[str, str], title: str) -> str:
    return rc._ev_for(ev_map, title) or "" if ev_map else ""


def _judge(x: str, st: Dict, before: str, ctx: Dict) -> Optional[Tuple[str, str, str]]:
    """(action, new sentence, why) for one sentence; action in ("drop", "replace"); None = keep. ``hard`` rules ("lang", "filler") drop
    even the last sentence of a stop (the stop is then refilled or disclosed)."""
    if ctx["english"]:
        lang = foreign_language(x)
        if lang:
            return "hard", "", f"sentence in another language ({lang})"
    if caption_variant(x):
        return "drop", "", "photo caption"
    if is_connects_filler(x):
        return "hard", "", "template filler (\"this stop connects ...\")"
    why = variant_reason(x)
    if why:
        return "drop", "", why
    for t in ctx["titles"]:
        new = title_as_place(x, t)
        if new and new != x:
            return "replace", new, "a stop title (dash / topic phrase) used as a place name"
    cut = known_for_verb_cut(x)
    if _KNOWN_FOR_VERB.search(x):
        return ("replace", cut, "\"known for <verb>\" list cut") if cut else ("drop", "", "\"known for <verb>\" list")
    why = fragment_reason(x)
    if why:
        return "drop", "", f"fragment: {why}"
    fixed = fix_agreement(x)
    if fixed:
        return "replace", fixed, "number agreement"
    if _THEIR.search(x):
        m = _THEIR.search(x)
        if not has_plural_referent(before + " " + x[:m.start()] + " " + st["title"]):
            return "drop", "", "Their/They with no plural referent"
    pr = period_rewrite(x, ctx["ev"].get(st["num"], ""))
    if pr:
        return ("replace", pr[0], pr[1]) if pr[0] else ("drop", "", pr[1])
    return None


def drop_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        import splice_copy_906r as sp
        ev_map = c._ev_map(evidence_by_title)
        titles = [st["title"] for st in c._stops_info(tour_text)]
        english = tour_is_english(tour_text)
        ev = {st["num"]: _ev_blob(ev_map, st["title"]) for st in c._stops_info(tour_text)}
        ctx = {"english": english, "titles": titles, "ev": ev}

        def fn(st: Dict, tg):
            edits, left, before = {}, sp._total(tg), ""
            for i in sorted(tg):
                _p, sents = tg[i]
                for j, x in enumerate(sents):
                    got = _judge(x, st, before, ctx)
                    if not got:
                        before += " " + x
                        continue
                    action, new, why = got
                    if action == "replace":
                        emit(f'  {TAG} Stop {st["num"]}: {why}: "{x[:90]}" -> "{new[:90]}"')
                        edits[(i, j)] = [new]
                        before += " " + new
                    elif action == "hard" or left > 1:
                        emit(f'  {TAG} Stop {st["num"]}: {why} dropped: "{x[:90]}"')
                        edits[(i, j)] = []
                        left -= 1
                    else:
                        before += " " + x
            return edits
        return sp._edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} sentence guard skipped (non-fatal): {err}")
        return tour_text


def drop_closing(tour_text: str, log: Optional[Callable] = None) -> str:
    """The tour's closing lines (after the last stop's body): \"This tour showcases ...\", \"Each stop invites ...\" go; the count line and the
    restaurant offer stay."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        blocks = rc._stop_blocks(tour_text)
        if not blocks:
            return tour_text
        s, e, _num, _title = blocks[-1]
        lines = tour_text[s:e].split("\n")
        body = c._stops_info(tour_text)[-1]["idx"]
        changed = False
        english = tour_is_english(tour_text)
        for i, ln in enumerate(lines):
            if i == 0 or not ln.strip() or rc._KEYED.match(ln) or i in body:
                continue
            sents = rc.split_sentences(ln)
            keep = []
            for x in sents:
                why = None if rc._CLOSING_LINE.match(x) else (variant_reason(x) or ("another language" if english and foreign_language(x) else None))
                if why:
                    emit(f'  {TAG} closing: {why} dropped: "{x[:100]}"')
                    changed = True
                else:
                    keep.append(x)
            lines[i] = " ".join(keep) if keep else None
        if not changed:
            return tour_text
        new = re.sub(r"\n{3,}", "\n\n", "\n".join(x for x in lines if x is not None))
        if not new.endswith("\n") and tour_text[s:e].endswith("\n"):
            new += "\n"
        return tour_text[:s] + new + tour_text[e:]
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} closing guard skipped (non-fatal): {err}")
        return tour_text


# ══ 8. one object, one value across the stops of a tour ═════════════════════════════════════════════════
def _stems(x: str) -> set:
    import refill_quality_906k as k
    return {k._stem(w) for w in k._object_words(x)}


def unify_measures(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        import leftovers_906f as f
        import refill_quality_906k as k
        ev_map = c._ev_map(evidence_by_title)
        stops = f._stops(tour_text)
        if len(stops) < 2:
            return tour_text
        items: List[Dict] = []
        for si, st in enumerate(stops):
            prev = ""
            for i, j, x in st["flat"]:
                ctx_text = x if k.object_nouns(x) else (prev + " " + x + " " + st["title"])
                for mm in k.measures(x):
                    items.append({"si": si, "num": st["num"], "i": i, "j": j, "x": x, "mm": mm, "nouns": k.object_nouns(ctx_text),
                                  "stems": _stems(ctx_text)})
                if k.object_nouns(x):
                    prev = x
        art: List[Tuple[str, List[Dict]]] = []
        for st in stops:
            ev = rc._ev_for(ev_map, st["title"]) or ""
            if ev.strip():
                a, _w = k._article_text(ev, st["title"], c._entries_for(st["title"]))
                art += [(sent, k.measures(sent)) for sent in rc.split_sentences(a)]
        web = [mm for st in stops for sent in rc.split_sentences(rc._ev_for(ev_map, st["title"]) or "") for mm in k.measures(sent)]

        def same_object(a: Dict, b: Dict) -> bool:
            return bool(a["nouns"] & b["nouns"]) and len(a["stems"] & b["stems"]) >= 2

        edits: Dict[int, Dict[Tuple[int, int], List[str]]] = {}
        done = set()
        for a in items:
            if id(a) in done:
                continue
            cl = [b for b in items if b["mm"]["dim"] == a["mm"]["dim"] and (b is a or (b["si"] != a["si"] and same_object(a, b)))]
            vals = []
            for b in cl:
                if not any(k._same(b["mm"]["m"], v["mm"]["m"]) for v in vals):
                    vals.append(b)
            if len({b["si"] for b in cl}) < 2 or len(vals) < 2:
                continue
            for b in cl:
                done.add(id(b))
            dim = a["mm"]["dim"]
            av: List[Dict] = []
            for sent, mms in art:
                if len(a["stems"] & _stems(sent)) >= 2:
                    for mm in mms:
                        if mm["dim"] == dim and not any(k._same(mm["m"], v["m"]) for v in av):
                            av.append(mm)
            if len(av) == 1:
                target, how = av[0], "the article's value"
            else:
                wv = [b for b in vals if any(k._same(b["mm"]["m"], w["m"]) for w in web if w["dim"] == dim)]
                if len(wv) == 1:
                    target, how = wv[0]["mm"], "the value the evidence states"
                else:
                    target, how = None, "no evidence value"
            first = min(b["si"] for b in cl)
            for b in sorted(cl, key=lambda z: -z["mm"]["span"][0]):
                if target is not None and k._same(b["mm"]["m"], target["m"]):
                    continue
                cur = edits.setdefault(b["si"], {})
                sent = (cur.get((b["i"], b["j"])) or [b["x"]])[0]
                if target is not None:
                    s, e = b["mm"]["span"]
                    new = sent[:s] + k.rewrite_measure(b["mm"], target) + sent[e:]
                    emit(f'  {TAG} Stop {b["num"]}: the same object carries two {dim} values across the tour '
                         f'({b["mm"]["raw"]} vs {target["raw"]}): {how} is used')
                    cur[(b["i"], b["j"])] = [new]
                elif b["si"] != first:
                    cs, ce = b["mm"]["span"]
                    lead = re.search(r"(?i)\s*(?:,\s*)?(?:and|but)\s+(?:[\w'’\-]+\s+){0,3}$", sent[:cs])
                    head = sent[:lead.start()] if lead else ""
                    if lead and len(head.split()) >= 5:
                        new = (head + sent[ce:]).strip()
                        new = new if new[-1:] in ".!?" else new + "."
                        emit(f'  {TAG} Stop {b["num"]}: the same object carries two {dim} values across the tour '
                             f'({b["mm"]["raw"]}) and {how} -> the measure clause is omitted: "{sent[:80]}"')
                        cur[(b["i"], b["j"])] = [new]
                    else:
                        emit(f'  {TAG} Stop {b["num"]}: the same object carries two {dim} values across the tour '
                             f'({b["mm"]["raw"]}) and {how} -> sentence dropped: "{sent[:80]}"')
                        cur[(b["i"], b["j"])] = []
        if not edits:
            return tour_text
        return f._each_stop(tour_text, lambda st, all_: edits.get(next((n for n, o in enumerate(all_) if o["num"] == st["num"]), -1), {}))
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} cross-stop measure guard skipped (non-fatal): {err}")
        return tour_text


# ══ 7. a stop with no supported sentence ═════════════════════════════════════════════════════════════════
def _factual(x: str) -> bool:
    if _is_filler(x) or c._is_disclosure(x) or rc.is_mood_filler(x, set()):
        return False
    try:   # [LOCAL-906V] a sensory sentence (sounds, scents, light) states nothing: it is not the stop's factual sentence
        import drive_quality_906v as _v906v
        return not _v906v.sensory_only(x)
    except Exception:  # pragma: no cover
        return True


def _factless_stops(text: str) -> List[int]:
    out = []
    for k, st in enumerate(c._stops_info(text)):
        sents = [x for i in st["idx"] for x in rc.split_sentences(st["lines"][i]) if not rc._CLOSING_LINE.match(x)]
        if any(c._is_disclosure(x) for x in sents):
            continue
        if not any(_factual(x) for x in sents):
            out.append(k)
    return out


def _disclosure_body(text: str, k: int, log: Callable) -> str:
    import delivery_bodies_905 as db
    import leftovers_906f as f
    import refill_quality_906k as kq
    import strict_grounding_gate as sgg
    info = c._stops_info(text)[k]
    body = " ".join(sgg.sensory_body(info["title"], [sgg.NO_HISTORY_DISCLOSURE], sgg.MIN_NO_EVIDENCE_SENTENCES - 1,
                                     register="walking" if re.search(r"(?i)\bwalking\s+tour\b", text[:400]) and not kq.is_driving(text) else "driving"))
    lines = list(info["lines"])
    if info["idx"]:
        return c._set_body(text, info, [body])
    at = next((i for i, ln in enumerate(lines) if i > 0 and (re.match(r"(?i)^directions\s*:", ln) or rc._CLOSING_LINE.match(ln.strip())
                                                           or (info["last"] and db._COUNT_ANY.search(ln)))), None)
    if at is None:
        while len(lines) > 1 and not lines[-1].strip():
            lines.pop()
        lines += ["", body, "", ""]
    else:
        lines[at:at] = [body, ""]
    return text[:info["s"]] + "\n".join(lines) + text[info["e"]:]


def factless_stops(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    """A stop whose every sentence is template filler (or that has none): refilled from its evidence (the 906I refill, with the filler still
    in place so the stop counts as thin), the filler then goes; with no supported sentence the stop gets the D760 disclosure body."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        import leftovers_906f as f
        bad = _factless_stops(tour_text)
        if not bad:
            return tour_text
        t = f.refill_thin_stops(tour_text, evidence_by_title, log)
        still = [k for k in _factless_stops(t) if k in bad]
        infos = c._stops_info(t)
        for k in bad:
            if k not in still or k >= len(infos):
                continue
            title = infos[k]["title"]
            emit(f"  {TAG} Stop {infos[k]['num']} '{title[:40]}': no supported sentence and no refill -> the no-history disclosure body")
            t = _disclosure_body(t, k, emit)
            infos = c._stops_info(t)
        return t
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} factless-stop guard skipped (non-fatal): {err}")
        return tour_text


# ══ the passes ═══════════════════════════════════════════════════════════════════════════════════════════
def run_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    t = drop_pass(tour_text, evidence_by_title, log)
    t = drop_closing(t, log)
    t = unify_measures(t, evidence_by_title, log)
    try:   # [LOCAL-906T] promo / record / neighbour / bearing guards, then the stub-tail guard
        import stub_promo_906t as _t906t
        t = _t906t.run_pass(t, evidence_by_title, log)
    except Exception as err:  # pragma: no cover
        _emit(log)(f"  [LOCAL-906T] pass skipped (non-fatal): {err}")
    return t


def last_word(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    """After every refill: the guards; a stop they left without a supported sentence is refilled or disclosed (always, not only when a
    guard changed the text); the refilled text is guarded again."""
    emit = _emit(log)
    try:
        t = run_pass(tour_text, evidence_by_title, log)
        t2 = factless_stops(t, evidence_by_title, log)
        if t2 != t:
            t2 = run_pass(t2, evidence_by_title, log)
            t2 = _drop_connects(t2, log)
        return t2
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} last word skipped (non-fatal): {err}")
        return tour_text


def _drop_connects(tour_text: str, log: Optional[Callable] = None) -> str:
    """The filler that was kept so the stop could be refilled goes once the stop has a supported sentence."""
    emit = _emit(log)
    try:
        import splice_copy_906r as sp

        def fn(st: Dict, tg):
            sents = [x for _i, (_p, ss) in tg.items() for x in ss]
            if not any(_factual(x) for x in sents) or any(c._is_disclosure(x) for x in sents):
                return {}
            edits = {}
            for i, (prefix, ss) in tg.items():
                if prefix:
                    continue
                for j, x in enumerate(ss):
                    if _is_filler(x):
                        emit(f'  {TAG} Stop {st["num"]}: template filler dropped (the stop has supported sentences): "{x[:80]}"')
                        edits[(i, j)] = []
            return edits
        return sp._edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} filler guard skipped (non-fatal): {err}")
        return tour_text
