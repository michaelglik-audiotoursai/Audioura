"""LOCAL-907D — topic builder: judge never truncates, segments are written in parts to length,
the length floor follows the source, rejected rows rebuild. Fully offline, $0."""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import strict_grounding_gate as sgg
import topic_library as tl
import topic_library_build as tb
from test_local907_topic_library import (REGION_KEY, fake_article, fake_judge, part_llm, region,  # noqa: F401
                                         topic_for)


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOURA_TASK_BUDGET_DIR", str(tmp_path / "budgets"))
    monkeypatch.delenv("TASK_BUDGET_ID", raising=False)
    monkeypatch.delenv("TASK_BUDGET_USD", raising=False)
    monkeypatch.setattr(tb, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def big_article(lang, title, n=170):
    """Like fake_article but with ~4,500-word sections, so the plan is three parts."""
    art = fake_article(lang, title)
    if art is None:
        return None
    seed = abs(hash(title)) % 7
    head = art["text"].split("== ")[0]
    text = head
    for i, h in enumerate(["History", "Economy", "Religion", "Cuisine", "Transportation", "Geography",
                           "Folklore", "Architecture", "Government", "Colonial era", "Revolution",
                           "Industry", "Parks", "Public transit", "Festivals"]):
        text += f"== {h} ==\n" + " ".join(_sentences(n, 100 * i + seed)) + "\n\n"
    art["text"] = text
    return art


def _sentences(n, start=0):
    return [f"In {1000 + start + k} the harbour town of Exampleport recorded {k + 3} new trade "
            f"agreements with merchants who sailed along the coast every single spring season." for k in range(n)]


def _text(n, start=0):
    s = _sentences(n, start)
    return "\n\n".join(" ".join(s[i:i + 5]) for i in range(0, len(s), 5))


# ───────────── 1. the judge never truncates ─────────────
def test_judge_max_tokens_scales_with_the_batch_and_tour_default_stays_900():
    assert tb.GROUND_BATCH_SENTENCES == 12
    assert tb.judge_max_tokens(12) == 12 * 60 + 200 == 920
    assert tb.judge_max_tokens(6) < tb.judge_max_tokens(12) < tb.judge_max_tokens(20)
    assert sgg._MAX_TOKENS == 900                                  # tours are untouched
    import inspect
    assert inspect.signature(sgg._default_classify).parameters["max_tokens"].default == 900


def test_each_judge_call_is_given_a_max_tokens_for_its_batch():
    seen = []

    def judge(system, user, model, *a, **kw):
        seen.append(kw.get("max_tokens"))
        return fake_judge(system, user, model)
    text = _text(30)
    kept, st = tb.ground_text("T", text, text, judge)
    assert seen and all(isinstance(m, int) for m in seen)
    assert max(seen) <= tb.judge_max_tokens(tb.GROUND_BATCH_SENTENCES) * 2
    assert st["judge_failures"] == 0 and st["kept"] == 30


def test_truncated_reply_is_retried_once_with_half_the_batch():
    sizes = []

    def judge(system, user, model, *a, **kw):
        n = len(re.findall(r"(?m)^\d+\. ", user.split("FACTUAL SENTENCES:")[1]))
        sizes.append(n)
        if n >= 10:                                  # a big batch: the reply is cut off
            return None, 1200, 900
        return fake_judge(system, user, model)
    text = _text(12)
    kept, st = tb.ground_text("T", text, text, judge)
    assert sizes[0] >= 10 and max(sizes[1:]) <= 6          # the retry used half the batch
    assert st["judge_retries"] == 1 and st["judge_failures"] == 0
    assert st["kept"] == 12 and tl.word_count(kept) == tl.word_count(text)


def test_a_batch_that_still_fails_after_the_retry_counts_as_a_failure():
    judge = lambda s, u, m, *a, **k: (None, 100, 10)       # noqa: E731
    _kept, st = tb.ground_text("T", _text(12), _text(12), judge)
    assert st["judge_failures"] >= 1 and st["judge_retries"] == 1


def test_truncation_in_a_build_no_longer_rejects(region):
    def judge(system, user, model, *a, **kw):
        n = len(re.findall(r"(?m)^\d+\. ", user.split("FACTUAL SENTENCES:")[1]))
        return (None, 100, 10) if n > 8 else fake_judge(system, user, model)
    row = tb.build_segment(topic_for(region), region, "en", fetch_fn=fake_article,
                           llm_fn=part_llm(good=40, bad=0), classify_fn=judge,
                           meter=tb.BuildMeter(5.0))
    assert row["status"] == "ready"


# ───────────── 2. written in parts ─────────────
def test_three_parts_reach_the_length_with_one_hook_and_one_credit(region):
    llm = part_llm(good=30, bad=0)
    row = tb.build_segment(topic_for(region), region, "en", fetch_fn=big_article, llm_fn=llm,
                           classify_fn=fake_judge, meter=tb.BuildMeter(5.0))
    assert len(llm.calls) == 3 and len(row["parts_words"]) == 3
    assert sum(row["parts_words"]) >= tb.MIN_WORDS_WRITTEN
    assert row["status"] == "ready" and row["survivor_words"] >= row["floor"]
    body = row["text"]
    paras = [p for p in body.split("\n\n") if p.strip()]
    assert len({tb._para_key(p) for p in paras}) == len(paras)           # nothing repeated
    assert body.count("Hear how Exampleport") == 1                       # one hook
    assert body.startswith("Hear how")
    assert body.count(tl.CREDIT_LINE) == 1 and body.rstrip().endswith(tl.CREDIT_LINE)
    # parts 2 and 3 are told to continue, with the previous part's last paragraph as context
    assert "PREVIOUS PART ENDED WITH" not in llm.calls[0]
    assert all("PREVIOUS PART ENDED WITH" in c for c in llm.calls[1:])
    # DIFFERENT source sections: no passage sentence is in two parts' SOURCE blocks
    srcs = [set(re.findall(r"In \d+ the harbour town[^.]*\.", c.split("SOURCE passages (PART):")[1]
                           .split("OVERVIEW")[0])) for c in llm.calls]
    assert not (srcs[0] & srcs[1]) and not (srcs[1] & srcs[2])


def test_repeated_paragraphs_and_a_model_written_credit_are_dropped():
    seen = set()
    a = tb.drop_repeats("Para one here.\n\nPara two here.", seen)
    b = tb.drop_repeats("para one here!\n\nNew para.\n\n" + tl.CREDIT_LINE, seen)
    assert "Para one" not in b and "New para." in b and tl.CREDIT_LINE not in b and "Para two" in a


def test_part_prompts_hook_only_in_part_one():
    p1, p2, p3 = (tb.writer_system(i, 3, 800) for i in (1, 2, 3))
    assert "hook" in p1 and "hook" not in p2.replace("Do NOT write a hook", "")
    assert "Do NOT write a hook" in p2 and "not repeat" in p3
    assert "credit" in p1 and "added separately" in p1


def test_budget_stop_between_parts_keeps_the_parts_already_paid_for(region):
    llm = part_llm(good=30, bad=0, in_tok=1_000_000, out_tok=0)            # $0.40 per write call
    meter = tb.BuildMeter(0.5)
    row = tb.build_segment(topic_for(region), region, "en", fetch_fn=big_article, llm_fn=llm,
                           classify_fn=fake_judge, meter=meter)
    assert len(llm.calls) == 1 and row["budget_stopped"] is True
    assert meter.spent <= 0.5 + 0.01 and meter.exhausted
    assert len(row["parts_words"]) == 1


def test_run_build_reports_a_budget_stop_from_between_parts(region):
    store = tl.MemorySegmentStore()
    llm = part_llm(good=30, bad=0, in_tok=1_000_000, out_tok=0)
    out = tb.run_build(REGION_KEY, "en", max_segments=3, budget_usd=0.5, store=store,
                       fetch_fn=big_article, llm_fn=llm, classify_fn=fake_judge, log=lambda m: None)
    assert out["stopped_on_budget"] and len(llm.calls) == 1 and len(out["built"]) == 1


def test_a_small_source_is_written_in_fewer_parts(region):
    assert tb.plan_part_count(3000) == 3 and tb.plan_part_count(1500) == 2 and tb.plan_part_count(600) == 1


def test_report_has_words_per_part_kept_floor_judge_calls_and_cost(region):
    lines = []
    out = tb.run_build(REGION_KEY, "en", max_segments=1, budget_usd=5.0, store=tl.MemorySegmentStore(),
                       fetch_fn=big_article, llm_fn=part_llm(good=30, bad=0), classify_fn=fake_judge,
                       log=lines.append)
    b = out["built"][0]
    assert len(b["parts_words"]) == 3 and b["survivor_words"] > 0 and b["floor"]
    assert b["judge_calls"] >= 1 and b["cost_usd"] > 0
    joined = "\n".join(lines)
    assert "parts written" in joined and "floor" in joined and "judge calls" in joined


# ───────────── 3. the floor follows the source ─────────────
@pytest.mark.parametrize("src,floor", [(5000, 1200), (2500, 1200), (2499, 1200),
                                       (2000, 1000), (1400, 700), (1000, 700), (400, 700)])
def test_floor_by_source_size(src, floor):
    assert tb.survivor_floor(src) == floor


def test_floor_is_half_the_source_between_the_extremes():
    assert tb.survivor_floor(1800) == 900 and tb.survivor_floor(1300) == 700


def test_a_segment_between_floor_and_1200_is_ready_with_honest_minutes(region):
    # ~2000-word source -> floor 1000; keep ~1050 words -> ready, est_minutes follows the words
    row = tb.build_segment(topic_for(region), region, "en", fetch_fn=fake_article,
                           llm_fn=part_llm(good=22, bad=0), classify_fn=fake_judge,
                           meter=tb.BuildMeter(5.0))
    assert row["floor"] < 1200 and row["floor"] <= row["survivor_words"] < 1200
    assert row["status"] == "ready"
    assert row["est_minutes"] == pytest.approx(row["word_count"] / 150.0, abs=0.01)


def test_below_the_floor_is_rejected_and_the_floor_is_logged(region):
    lines = []
    row = tb.build_segment(topic_for(region), region, "en", fetch_fn=fake_article,
                           llm_fn=part_llm(good=3, bad=0), classify_fn=fake_judge,
                           meter=tb.BuildMeter(5.0), log=lines.append)
    assert row["status"] == "rejected" and f"< {row['floor']}" in row["reject_reason"]
    assert any("floor" in l for l in lines)


# ───────────── 4. rebuilds ─────────────
def _kw(llm):
    return dict(max_segments=2, budget_usd=5.0, fetch_fn=fake_article, llm_fn=llm,
                classify_fn=fake_judge, log=lambda m: None)


def test_a_rejected_row_is_rebuilt_in_place_by_update(region):
    store = tl.MemorySegmentStore()
    title = topic_for(region)["title"]
    rid = store.insert_segment({"region_key": REGION_KEY, "language": "en", "title": title,
                                "theme": "history", "text": "old", "word_count": 1, "status": "rejected"})
    n_before = len(store.list_segments())
    out = tb.run_build(REGION_KEY, "en", store=store, **{**_kw(part_llm(good=30, bad=0)), "max_segments": 1})
    row = store.get_segment(rid)
    assert out["built"][0]["id"] == rid and row["status"] == "ready" and row["text"] != "old"
    assert len(store.list_segments()) == n_before                       # same id, no new row


def test_a_ready_row_is_skipped_unless_rebuild(region):
    store = tl.MemorySegmentStore()
    llm = part_llm(good=30, bad=0)
    tb.run_build(REGION_KEY, "en", store=store, **_kw(llm))
    n = len(llm.calls)
    ids = [s["id"] for s in store.list_segments()]
    again = tb.run_build(REGION_KEY, "en", store=store, **_kw(llm))
    assert again["built"] == [] and len(llm.calls) == n
    forced = tb.run_build(REGION_KEY, "en", store=store, rebuild=True, **_kw(llm))
    assert len(forced["built"]) == len(ids) and len(llm.calls) > n
    assert [s["id"] for s in store.list_segments()] == ids              # UPDATE, never new rows


def test_a_failed_forced_rebuild_never_replaces_a_ready_row(region):
    store = tl.MemorySegmentStore()
    tb.run_build(REGION_KEY, "en", store=store, **{**_kw(part_llm(good=30, bad=0)), "max_segments": 1})
    before = store.list_segments()[0]
    tb.run_build(REGION_KEY, "en", store=store, rebuild=True,
                 **{**_kw(part_llm(good=2, bad=0)), "max_segments": 1})
    after = store.get_segment(before["id"])
    assert after["status"] == "ready" and after["text"] == before["text"]


def test_cli_has_rebuild_flag():
    assert tb._parse(["--region", "x", "--rebuild"]).rebuild is True
    assert tb._parse(["--region", "x"]).rebuild is False


def test_pg_store_update_is_an_update_by_id_and_never_deletes():
    executed = []

    class Cur:
        def execute(self, sql, params=()):
            executed.append((sql, params))

        def close(self):
            pass

    class Conn:
        def cursor(self):
            return Cur()

        def commit(self):
            pass
    tl.PgSegmentStore(Conn()).update_segment(7, {"id": 99, "text": "new", "status": "ready",
                                                 "sources": [{"url": "u"}]})
    sql, params = executed[0]
    assert sql.startswith("UPDATE topic_segments SET") and sql.endswith("WHERE id = %s")
    assert params[-1] == 7 and 99 not in params and "DELETE" not in sql.upper()
    src = open(os.path.join(os.path.dirname(tb.__file__), "topic_library.py"), encoding="utf-8").read()
    assert "DELETE FROM" not in src.upper().replace("DELETE NOTHING", "")
