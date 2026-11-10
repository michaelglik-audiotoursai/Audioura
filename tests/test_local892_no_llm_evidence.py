#!/usr/bin/env python3
"""LOCAL-892 -- an LLM's own output is never EVIDENCE. Offline.

Generic fixtures carry the rule; the replay runs the 891 persisted Saigon bundle
(submission_artifacts/local891/saigon_warm_evidence_bundle.json) and the shipped 891 text through the
real gate (``strict_grounding_gate.apply_grounding_gate``) and the aboutness audit with an
evidence-faithful judge (SUPPORTED only when the evidence the judge was SHOWN carries the sentence's
distinctive words -- what an honest judge does).

The 891 harness persisted no per-item source, so the LLM-sourced passages of the replay are RECONSTRUCTED
from their shape: ``facts_as_snippets`` glues the stop's title onto each fact ('Cathedral In 1959, the
Vatican anointed ...'). ``claim_provenance`` of the 891 run confirms the Pier one
(source 'knowledge_fallback:openai'). Book Street's two Tet segments are an INFERENCE from the same shape.
The Thi Bar segments are real SERP titles and are left alone. This is a replay, not a measurement."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import aboutness as ab                      # noqa: E402
import llm_evidence as le                   # noqa: E402
import strict_grounding_gate as sgg         # noqa: E402
import claim_provenance as cp               # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A891 = os.path.join(ROOT, "submission_artifacts", "local891")
BUNDLE = json.load(open(os.path.join(A891, "saigon_warm_evidence_bundle.json"), encoding="utf-8"))
T891 = open(os.path.join(A891, "saigon_warm.txt"), encoding="utf-8").read()


@pytest.fixture(autouse=True)
def _clean():
    le.clear_registry()
    ab.set_location("")
    yield
    le.clear_registry()
    ab.set_location("")


def faithful_judge(_system, user, _model):
    """SUPPORTED iff >= 60% of the sentence's distinctive tokens occur in the EVIDENCE the judge was
    shown; UNSUPPORTED otherwise. Names the best-overlap item as its source."""
    ev = user.split("FACTUAL SENTENCES:")[0]
    items = {m.group(1): m.group(3) for m in re.finditer(
        r"(?m)^\[(E\d+) \| about_stop=(true|false)[^\]]*\] (.*)$", ev)}
    shown = set(ab.toks(ev))
    sents = re.findall(r"(?m)^(\d+)\. (.*)$", user.split("FACTUAL SENTENCES:")[-1])
    out = []
    for i, s in sents:
        st = {t for t in ab.toks(s) if len(t) > 3}
        cov = len(st & shown) / max(1, len(st))
        best = max(items, key=lambda k: len(st & set(ab.toks(items[k]))), default="")
        out.append({"i": int(i), "verdict": "SUPPORTED" if cov >= 0.6 else "UNSUPPORTED",
                    "evidence": "x", "legend": False, "source": best})
    return {"verdicts": out}, 10, 10


def llm_passages(title, ev, glue_title):
    """Reconstruct the knowledge-fallback passages: the glued '<title> <fact>' segments of the tail."""
    first = re.search(r"(?:(?<=\. )|(?<=\]\s)|(?<=\.\[1\] ))" + re.escape(glue_title) + r" (?=[A-Z])", ev)
    if not first:
        return []
    tail = ev[first.start():]
    parts = re.split(r"(?:(?<=\. )|(?<=\.\] )|(?<=\.\[1\] ))(?=" + re.escape(glue_title) + r" [A-Z])", tail)
    return [p.strip() for p in parts if p.strip()]


def body(title_part, text=T891):
    for n, t, b in sgg._split_blocks(text):
        if title_part.lower() in t.lower():
            return t, sgg._content_sentences(sgg._block_body_prose(b))
    raise KeyError(title_part)


# ───────────────────────── module rule ─────────────────────────
def test_source_classifier():
    assert le.is_llm_source("knowledge_fallback:openai")
    assert le.is_llm_source("parametric") and le.is_llm_source("spine") and le.is_llm_source("fact_extractor")
    assert not le.is_llm_source("https://en.wikipedia.org/wiki/X")
    assert not le.is_llm_source("snippet")
    assert not le.is_evidence_record({"snippet": "x", "source": "knowledge_fallback:gemini"})
    assert not le.is_evidence_record({"snippet": "x", "link": "https://a.example", "llm": True})
    assert le.is_evidence_record({"snippet": "x", "link": "https://a.example", "source": "serper"})


def test_lore_rules():
    assert not le.lore_is_evidence({"fact": "A thing happened.", "confidence": "high"})
    assert le.lore_is_evidence({"fact": "A thing happened.", "source": "https://a.example/p", "_thin_search": True})
    assert le.lore_is_evidence({"fact": "A venue-chain fact", "source": "https://x.example"})


def test_facts_as_snippets_flags_and_registers():
    import stop_knowledge_fallback as skf
    sn = skf.facts_as_snippets({"provider": "openai", "facts": [
        {"fact": "In 1975 the pier was an evacuation point for many people.", "confidence": "high"}]}, "Some Pier")
    assert sn[0]["llm"] is True and sn[0]["source"] == "knowledge_fallback:openai"
    assert not le.is_evidence_record(sn[0])
    import stop_coherence as sc
    assert sc.snippets_as_evidence_texts(sn) == []          # never flattened into evidence
    assert "evacuation" not in le.scrub("x Some Pier In 1975 the pier was an evacuation point for many people. y")


def test_provenance_pool_never_counts_llm_as_corpus():
    rec = {"snippet": "In 1975 the pier was a significant evacuation point for many people fleeing the city.",
           "title": "Some Pier", "source": "knowledge_fallback:openai", "link": "https://x.example", "llm": True}
    pool = cp.SourcePool(snippets_per_stop={"Some Pier": [rec]})
    r = pool.classify("In 1975 the pier was a significant evacuation point for many people fleeing the city.",
                      "Some Pier")
    assert r["class"] == cp.PARAMETRIC


# ───────────────────────── gate: only-LLM support => UNSUPPORTED ─────────────────────────
ARTICLE = ("Some Pier - Wikipedia (en). Some Pier is a wharf on the river in Riverton, opened in 1881 and "
           "renamed in 1955. It stretches along the river for about 1.3 kilometres.\n"
           "Passages: [History] The wharf was opened in 1881 for river trade. It was renamed in 1955. "
           "The park beside it was renovated in 2021 and completed in 2022.")
LLM = "Some Pier In 1975, during the siege, Some Pier was a significant evacuation point for many people fleeing."
SENT = "In 1975, during the siege, the pier was a significant evacuation point for many people fleeing."
GOOD = "The wharf was opened in 1881 for river trade."


def run_gate(evidence, sentences):
    prose = " ".join(sentences)
    out, rep = sgg.apply_grounding_gate("Some Pier", prose, evidence, classify_fn=faithful_judge)
    return out, rep


def test_bundle_with_only_knowledge_fallback_item_is_unsupported():
    le.register([LLM[len("Some Pier "):], LLM], stop="Some Pier")
    out, rep = run_gate(ARTICLE + " " + LLM, [GOOD, SENT])
    assert "evacuation" not in out and GOOD in out
    assert rep["unsupported"] >= 1


def test_no_other_evidence_at_all_everything_factual_is_dropped():
    le.register([LLM], stop="Some Pier")
    out, rep = run_gate(LLM, [SENT])
    assert "evacuation" not in out and rep["no_evidence"] is True


def test_control_same_text_as_real_source_is_kept():
    """The SAME words from a real (non-LLM) source stay supported: the rule is about provenance."""
    real = ARTICLE + " Some Pier In 1975, during the siege, Some Pier was a significant evacuation point for many people fleeing."
    out, rep = run_gate(real, [GOOD, SENT])
    assert "evacuation" in out


def test_audit_excludes_llm_items():
    le.register([LLM], stop="Some Pier")
    tour = "Stop 1: Some Pier\n\n" + GOOD + " " + SENT + "\n"
    a = ab.audit_tour(tour, {"Some Pier": ARTICLE + " " + LLM})
    assert all("evacuation" not in it["text"] for it in a["items"]["Some Pier"])


# ───────────────────────── cache ─────────────────────────
def test_cache_rows_are_classified():
    import work_story_research as w
    ev, llm = w.classify_cached_row("k:abc:v1", ["Piet Mondrian created X in 1930.", "It was shown in 1931."])
    assert ev == [] and len(llm) == 2                      # no QID => only the LLM fallback could fill it
    ev, llm = w.classify_cached_row("qid:Q1:v1", ["only one passage here that is long enough"])
    assert ev == [] and len(llm) == 1                      # below MIN_PASSAGES => fallback may have added
    ev, llm = w.classify_cached_row("qid:Q1:v1", ["p one is long enough", "p two is long enough"])
    assert len(ev) == 2 and llm == []                      # verbatim Wikipedia
    ev, llm = w.classify_cached_row("qid:Q1:v1", ["wiki one", le.LLM_CACHE_MARK + "llm one"])
    assert ev == ["wiki one"] and llm == ["llm one"]       # new rows are marked


def test_research_marks_fallback_passages():
    import work_story_research as w
    res = w.museum_work_research(
        "Obscure Work", "A. Artist", use_cache=False, allow_fallback=True,
        fetch=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no net")),
        serp=lambda q: [{"url": "https://a.example/x"}],
        page_fetch=lambda u: "Obscure Work was stolen in 1911 and recovered two years later. " * 5,
        answer=lambda prompt, **k: {"text": "Obscure Work was stolen from the hall in 1911 by a night guard."})
    assert res["llm_passages"] and res["evidence_passages"] == []


# ───────────────────────── unanchored person ─────────────────────────
def test_unanchored_person():
    r = ab.Referent("War Remnants Museum")
    its = [{"about_stop": True, "text": "US anthropologist Christina Schwenkel wrote the museum attempts to convey"}]
    assert ab.unanchored_person("Faced with the documented horrors, Wilson expressed disbelief.", r, its)
    assert ab.unanchored_person("William Wilson expressed disbelief at the horrors.", r, its)
    assert not ab.unanchored_person("Colonel William Wilson expressed disbelief.", r, its)
    assert not ab.unanchored_person("Christina Schwenkel wrote that the museum conveys self-representation.", r, its)
    its2 = its + [{"about_stop": True, "text": "Colonel William Wilson, a combat veteran, is quoted in the museum."}]
    assert not ab.unanchored_person("Wilson expressed disbelief.", r, its2)    # role added by the evidence
    assert not ab.unanchored_person("The museum said it welcomes visitors.", r, its)


def test_clean_stop_drops_unanchored_person():
    ev = ("Some Museum - Wikipedia (en). Some Museum is a museum in Riverton. It opened in 1975.\n"
          "Passages: [History] The museum opened in 1975. It shows aircraft in a yard.")
    sents = ["The museum opened in 1975.", "It shows aircraft in a yard.",
             "Faced with the documented horrors, Wilson expressed disbelief at what he saw.",
             "The yard holds several aircraft."]
    out, rep = ab.clean_stop("Some Museum", sents, ev)
    assert not any("Wilson" in s for s in out)


# ───────────────────────── D769: the tour's own location tokens ─────────────────────────
def test_no_hardcoded_saigon():
    src = open(os.path.join(ROOT, "aboutness.py"), encoding="utf-8").read()
    assert not re.search(r'\{"city",\s*"saigon"\}', src)
    ab.set_location("Ho Chi Minh City, Vietnam")
    assert {"minh", "vietnam"} <= set(ab.location_tokens("Ho Chi Minh City, Vietnam"))
    r_loc = ab.Referent("Riverton Central Post Office", location="Riverton, Nowhere")
    assert "riverton" not in r_loc.name_toks and "central" in r_loc.name_toks
    r_none = ab.Referent("Riverton Central Post Office", location="")
    assert "riverton" in r_none.name_toks                      # nothing is hard-coded: no location, no removal


def test_regional_tokens_from_evidence():
    ev = {f"S{i}": ("Riverton is the old city. " * 12 + f"Stop {i} text about Riverton and Elsewhere. ") * 2
          for i in range(5)}
    ev["S0"] = ev["S0"] + " Quux"
    assert "riverton" in ab.regional_tokens(ev)


# ───────────────────────── 891 replay ─────────────────────────
GLUE = {"Bạch Đằng Pier": "Bạch Đằng Pier", "Cathedral": "Cathedral", "Book Street": "Book Street",
        "War Remnants Museum": "War Remnants Museum", "Post Office": "Post Office",
        "Opera House": "Opera House", "Independence Palace": "Independence Palace",
        "Café Apartments 42": "Café Apartments 42"}


def reconstructed():
    out = {}
    for t, g in GLUE.items():
        out[t] = llm_passages(t, BUNDLE[t]["evidence"], g)
    return out


def replay_stop(title):
    llm = reconstructed()
    le.clear_registry()
    for t, ps in llm.items():
        le.register(ps)
    ev = BUNDLE[title]["evidence"]
    ab.set_location("Ho Chi Minh City, Vietnam", {k: v["evidence"] for k, v in BUNDLE.items()})
    _t, sents = body(title)
    out, rep = sgg.apply_grounding_gate(title, " ".join(sents), ev, classify_fn=faithful_judge)
    return sents, out, rep


def test_replay_reconstruction_finds_the_known_llm_passages():
    llm = reconstructed()
    assert len(llm["Bạch Đằng Pier"]) == 3
    assert any("evacuation point" in p for p in llm["Bạch Đằng Pier"])
    assert any("1945" in p and "Japanese" in p for p in llm["Bạch Đằng Pier"])
    assert any("In 1959, the Vatican anointed" in p for p in llm["Cathedral"])
    assert any("executed a handcuffed" in p for p in llm["Book Street"])
    assert any("Wilson" in p for p in llm["War Remnants Museum"])


def test_replay_pier_has_no_evacuation_and_no_1945_clash():
    sents, out, rep = replay_stop("Bạch Đằng Pier")
    assert re.search(r"evacuat", " ".join(sents)), "891 text must carry the evacuation sentence"
    assert not re.search(r"(?i)evacuat|refuge|fleeing", out)
    assert not re.search(r"1945|August Revolution|Japanese", out)


def test_replay_cathedral_has_no_1959_basilica():
    sents, out, rep = replay_stop("Cathedral")
    assert any("1959" in s and "basilica" in s for s in sents)
    assert not any("1959" in s and "basilica" in s.lower() for s in sgg._content_sentences(out))


def test_replay_book_street_has_no_tet_execution():
    sents, out, rep = replay_stop("Book Street")
    assert re.search(r"(?i)tet|execut", " ".join(sents))
    assert not re.search(r"(?i)\btet\b|execut|Eddie Adams|Pulitzer", out)


def test_replay_wrm_has_no_wilson():
    sents, out, rep = replay_stop("War Remnants Museum")
    assert "Wilson" in " ".join(sents)
    assert "Wilson" not in out


def test_replay_audit_flags_nothing_llm_only():
    llm = reconstructed()
    for t, ps in llm.items():
        le.register(ps)
    ev = {t: b["evidence"] for t, b in BUNDLE.items()}
    ab.set_location("Ho Chi Minh City, Vietnam", ev)
    a = ab.audit_tour(T891, ev)
    for t, items in a["items"].items():
        for it in items:
            assert "evacuation point" not in it["text"] and "In 1959, the Vatican anointed" not in it["text"]
    flagged = {(o["stop"]) for o in a["offtopic"]}
    assert "War Remnants Museum" in flagged                     # Wilson: a person with no role


def test_replay_judge_is_never_shown_an_llm_passage():
    """Discriminating: with the registry the judge's prompt carries none of the reconstructed LLM
    passages; without it (control) the same prompts DO carry them."""
    needles = {"Bạch Đằng Pier": "significant evacuation point", "Cathedral": "In 1959, the Vatican anointed",
               "Book Street": "executed a handcuffed", "War Remnants Museum": "Colonel William Wilson"}
    ab.set_location("Ho Chi Minh City, Vietnam", {k: v["evidence"] for k, v in BUNDLE.items()})
    for fixed in (False, True):
        le.clear_registry()
        if fixed:
            for ps in reconstructed().values():
                le.register(ps)
        for title, needle in needles.items():
            seen = []

            def judge(system, user, model, _seen=seen):
                _seen.append(user.split("FACTUAL SENTENCES:")[0])
                return faithful_judge(system, user, model)
            _t, sents = body(title)
            sgg.apply_grounding_gate(title, " ".join(sents), BUNDLE[title]["evidence"], classify_fn=judge)
            shown = any(needle in u for u in seen)
            if title == "Book Street":
                continue          # 891's title-glue split already marks the Tet segment as context
            assert shown is (not fixed), (title, fixed)


def test_llm_only_supported_counter():
    tour = "Stop 1: Some Pier\n\n" + GOOD + " " + SENT + "\n"
    r = ab.llm_only_supported(tour, {"Some Pier": ARTICLE}, {"Some Pier": [LLM]})
    assert r["Some Pier"] == [SENT]                           # carried by the LLM lead only
    r2 = ab.llm_only_supported("Stop 1: Some Pier\n\n" + GOOD + "\n", {"Some Pier": ARTICLE}, {"Some Pier": [LLM]})
    assert r2["Some Pier"] == []


def test_replay_891_text_counts_llm_only_support():
    """On the SHIPPED 891 text the counter finds the sentences the 891 run shipped on LLM-only support."""
    llm = reconstructed()
    ev = {t: b["evidence"] for t, b in BUNDLE.items()}
    r = ab.llm_only_supported(T891, ev, llm)
    assert any("evacuation" in x for x in r["Bạch Đằng Pier"])
    assert sum(len(v) for v in r.values()) >= 3
