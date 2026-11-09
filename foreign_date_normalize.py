"""foreign_date_normalize.py — LOCAL-879 §3.

Tour 547's Stop 4 (Independence Palace) shipped Vietnamese date forms inside
English narration:

    "construction began on 1 tháng 7 năm 1962 and was completed on 31 tháng 10
     năm 1966"

The vi local-edition evidence (LOCAL-875 / 873) reached the English narrator
verbatim. A date written in the SOURCE language must be rendered in the TOUR's
language before it is spoken. "1 tháng 7 năm 1962" → "1 July 1962".

This module normalises local-language dates and numbers into the tour language.
It is deterministic, offline and idempotent: a date already in the tour language
is left exactly as-is, and English prose is never touched (no English month name
or weekday is a trigger). The scope is deliberately narrow — only recognised
foreign month-name / date-structure forms — so it can run as a final pass on the
assembled text without risk to ordinary prose.

Coverage (the ticket's minimum): vi (`tháng`/`năm`), fr, es, ru, zh.

Public API:
    normalize_foreign_dates(text, lang="en") -> (new_text, n_changed)

Only English ("en") output is implemented today (the shipping tour language);
for any other target the text is returned unchanged (a foreign date in a foreign
tour is already in-language).
"""
from __future__ import annotations

import re
from typing import Tuple

__all__ = ["normalize_foreign_dates", "contains_foreign_date"]

# ── English month names, indexed 1..12 (the normalisation TARGET). ───────────
_EN_MONTHS = [
    "", "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]

# ── Vietnamese: numeric months, "tháng M" / "tháng M năm YYYY". ───────────────
# Vietnamese writes months as "tháng <number>" and years as "năm <number>".
#   "1 tháng 7 năm 1962"  -> day=1  month=7  year=1962
#   "tháng 7 năm 1962"    ->        month=7  year=1962
#   "tháng 7"             ->        month=7
_VI_DMY = re.compile(
    r"(?i)\b(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{3,4})\b")
_VI_MY = re.compile(r"(?i)\btháng\s+(\d{1,2})\s+năm\s+(\d{3,4})\b")
_VI_M = re.compile(r"(?i)\btháng\s+(\d{1,2})\b")
# A bare "năm 1962" → "1962" (year word with no month).
_VI_Y = re.compile(r"(?i)\bnăm\s+(\d{3,4})\b")

# ── French month names. ──────────────────────────────────────────────────────
_FR_MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}
# "1er juillet 1962" / "1 juillet 1962" / "juillet 1962"
_FR_DMY = re.compile(
    r"(?i)\b(\d{1,2})(?:er)?\s+(" + "|".join(_FR_MONTHS) + r")\s+(\d{3,4})\b")
_FR_MY = re.compile(r"(?i)\b(" + "|".join(_FR_MONTHS) + r")\s+(\d{3,4})\b")

# ── Spanish month names ("1 de julio de 1962"). ──────────────────────────────
_ES_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_ES_DMY = re.compile(
    r"(?i)\b(\d{1,2})\s+de\s+(" + "|".join(_ES_MONTHS) + r")\s+de\s+(\d{3,4})\b")
_ES_MY = re.compile(
    r"(?i)\b(" + "|".join(_ES_MONTHS) + r")\s+de\s+(\d{3,4})\b")

# ── Russian month names (genitive, as used in a date). ───────────────────────
_RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11,
    "декабря": 12,
}
# "1 июля 1962 года" / "1 июля 1962" / "июля 1962"
_RU_DMY = re.compile(
    r"(?i)\b(\d{1,2})\s+(" + "|".join(_RU_MONTHS) + r")\s+(\d{3,4})(?:\s+года)?\b")
_RU_MY = re.compile(
    r"(?i)\b(" + "|".join(_RU_MONTHS) + r")\s+(\d{3,4})(?:\s+года)?\b")

# ── Chinese dates ("1962年7月1日", "1962年7月", "7月1日"). ─────────────────────
_ZH_YMD = re.compile(r"(\d{3,4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_ZH_YM = re.compile(r"(\d{3,4})\s*年\s*(\d{1,2})\s*月")
_ZH_MD = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def _mname(n: int) -> str:
    return _EN_MONTHS[n] if 1 <= n <= 12 else ""


def _en_dmy(day: str, month: int, year: str) -> str:
    mn = _mname(month)
    if not mn:
        return f"{day} {month} {year}"
    d = str(int(day))
    return f"{d} {mn} {year}"


def _en_my(month: int, year: str) -> str:
    mn = _mname(month)
    return f"{mn} {year}" if mn else f"{month} {year}"


def contains_foreign_date(text: str) -> bool:
    """True when ``text`` carries a recognised foreign-language date form."""
    if not text:
        return False
    for rx in (_VI_DMY, _VI_MY, _VI_M, _VI_Y, _FR_DMY, _ES_DMY, _RU_DMY,
               _ZH_YMD, _ZH_YM, _ZH_MD):
        if rx.search(text):
            return True
    return False


def normalize_foreign_dates(text: str, lang: str = "en") -> Tuple[str, int]:
    """Render recognised foreign-language dates in the tour language (English).

    Returns ``(new_text, n_changed)``. Deterministic, offline and idempotent: a
    date already in English is not a trigger, so a second pass changes nothing.
    For a non-English target the text is returned unchanged.
    """
    if not text or (lang or "en").lower() != "en":
        return text or "", 0

    n = 0

    def _count(fn):
        nonlocal n

        def _wrapped(m):
            nonlocal n
            n += 1
            return fn(m)
        return _wrapped

    out = text
    # Vietnamese — most specific first (DMY, then MY, then bare month, then year).
    out = _VI_DMY.sub(_count(lambda m: _en_dmy(m.group(1), int(m.group(2)), m.group(3))), out)
    out = _VI_MY.sub(_count(lambda m: _en_my(int(m.group(1)), m.group(2))), out)
    out = _VI_M.sub(_count(lambda m: _mname(int(m.group(1))) or m.group(0)), out)
    out = _VI_Y.sub(_count(lambda m: m.group(1)), out)
    # French.
    out = _FR_DMY.sub(_count(lambda m: _en_dmy(m.group(1), _FR_MONTHS[m.group(2).lower()], m.group(3))), out)
    out = _FR_MY.sub(_count(lambda m: _en_my(_FR_MONTHS[m.group(1).lower()], m.group(2))), out)
    # Spanish.
    out = _ES_DMY.sub(_count(lambda m: _en_dmy(m.group(1), _ES_MONTHS[m.group(2).lower()], m.group(3))), out)
    out = _ES_MY.sub(_count(lambda m: _en_my(_ES_MONTHS[m.group(1).lower()], m.group(2))), out)
    # Russian.
    out = _RU_DMY.sub(_count(lambda m: _en_dmy(m.group(1), _RU_MONTHS[m.group(2).lower()], m.group(3))), out)
    out = _RU_MY.sub(_count(lambda m: _en_my(_RU_MONTHS[m.group(1).lower()], m.group(2))), out)
    # Chinese — year-month-day, then year-month, then month-day.
    out = _ZH_YMD.sub(_count(lambda m: _en_dmy(m.group(3), int(m.group(2)), m.group(1))), out)
    out = _ZH_YM.sub(_count(lambda m: _en_my(int(m.group(2)), m.group(1))), out)
    out = _ZH_MD.sub(_count(lambda m: (lambda mn: f"{int(m.group(2))} {mn}" if mn else m.group(0))(_mname(int(m.group(1))))), out)

    # Tidy any double spaces a substitution left behind.
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out, n
