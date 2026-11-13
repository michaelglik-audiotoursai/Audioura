"""LOCAL-907 (D772) — Regional Topic Library. Fully offline: Wikipedia, the LLM, the grounding
judge, translation and Kokoro are all mocked. No DB, no network, $0."""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fillings_payload as fp
import listening_events as le
import topic_library as tl
import topic_library_build as tb
import topic_picker as tp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGION_KEY = "boston_ma"


@pytest.fixture(autouse=True)
def _isolated_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIOURA_TASK_BUDGET_DIR", str(tmp_path / "budgets"))
    monkeypatch.delenv("TASK_BUDGET_ID", raising=False)
    monkeypatch.delenv("TASK_BUDGET_USD", raising=False)
    monkeypatch.setattr(tb, "CACHE_DIR", str(tmp_path / "cache"))


# ───────────────────────── fake sources ─────────────────────────
SECTION_HEADINGS = ["History", "Economy", "Religion", "Cuisine", "Transportation",
                    "Geography", "Folklore", "Architecture", "Government"]
EXTRA_HEADINGS = ["Colonial era", "Revolution", "Industry", "Parks", "Public transit", "Festivals"]


def facts(seed, n, base_year):
    """n distinct factual sentences (~24 words each), every year/number present in the source."""
    return [f"In {base_year + k} the harbour town of Exampleport recorded {k + 3} new trade "
            f"agreements with merchants who sailed along the coast every single spring season ({seed})."
            .replace(f" ({seed})", "") for k in range(n)]


def fake_article(lang, title):
    """Every seed gets an article with several sections of ~600 words and a few links."""
    if title.lower().startswith("missing"):
        return None
    seed = abs(hash(title)) % 7
    headings = SECTION_HEADINGS if title.endswith("Boston") or title == "Boston" else EXTRA_HEADINGS
    text = "Exampleport is a coastal place with a long record. " * 5 + "\n\n"
    for i, h in enumerate(headings):
        text += f"== {h} ==\n" + " ".join(facts(seed, 80, 1000 + 100 * i)) + "\n\n"
    text += "== References ==\n" + "x " * 700
    return {"lang": lang, "site": "wikipedia", "title": title,
            "url": f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}",
            "revision_id": 123456 + len(title), "licence": tl.LICENCE, "text": text,
            "links": ["Local cuisine tradition", "Harbour ferry network", "Old legends"]}


@pytest.fixture
def region():
    return tl.get_region(REGION_KEY)


# ───────────────────────── data ─────────────────────────
def test_regions_data_has_the_five_regions():
    regions = tl.load_regions()
    assert set(regions) == {"mui_ne_binh_thuan", "ho_chi_minh_city", "boston_ma",
                            "nice_cote_d_azur", "san_diego_ca"}
    for r in regions.values():
        assert r["display_name"] and r["radius_km"] > 0
        assert {"lat", "lng"} <= set(r["centre"]) and r["seed_articles"]["en"]
        assert set(r["default_themes"]) <= set(tl.THEMES)


def test_no_place_names_in_code():
    """D769: regions are data. None of the region names appears in the new code."""
    names = re.compile(r"mui ?n[eé]|binh thuan|b[ìi]nh thu[ậa]n|ho chi minh|\bboston\b|\bNice\b|san diego",
                       re.I)
    for f in ("topic_library.py", "topic_library_build.py", "topic_picker.py",
              "listening_events.py", "fillings_payload.py"):
        src = open(os.path.join(ROOT, f), encoding="utf-8").read()
        assert not names.search(src), f


def test_migration_is_additive_only():
    sql = open(os.path.join(ROOT, "migrations", "local907_topic_library.sql"), encoding="utf-8").read()
    for t in ("topic_segments", "listening_events", "listener_theme_weights"):
        assert f"CREATE TABLE IF NOT EXISTS {t}" in sql
    body = re.sub(r"--.*", "", sql)
    assert not re.search(r"\b(DROP|DELETE|TRUNCATE|ALTER)\b", body, re.I)
    for col in ("region_key", "theme", "title", "language", "text", "word_count", "est_minutes",
                "sources", "credit_line", "centroid_lat", "centroid_lng", "radius_km", "audio_path",
                "source_segment_id", "status", "cost_usd", "created_at", "at_sec", "weight"):
        assert col in sql


# ───────────────────────── plan ─────────────────────────
def test_dry_run_plans_distinct_topics_across_themes_for_zero_dollars(region, capsys):
    def boom(*a, **k):
        raise AssertionError("a dry run must not make a paid call")
    out = tb.run_build(REGION_KEY, "en", max_segments=9, dry_run=True, fetch_fn=fake_article,
                       llm_fn=boom, classify_fn=boom, store=None)
    topics = out["topics"]
    assert len(topics) == 9
    assert len({t["title"] for t in topics}) == 9
    assert len({t["theme"] for t in topics}) >= 5
    rt = tb.region_tokens(region, "en")
    for i, a in enumerate(topics):
        for b in topics[i + 1:]:
            assert tb.overlap(a["tokens"], b["tokens"]) <= tb.MAX_OVERLAP, (a["title"], b["title"])
    assert out["estimated_cost_usd"] > 0 and out["spent_usd"] == 0.0
    printed = capsys.readouterr().out
    assert "Estimated paid cost" in printed and "$0.0000" in printed
    assert rt is not None


def test_plan_respects_max_segments_and_skips_missing_seed(region):
    topics = tb.plan_topics(region, "en", 4, fetch_fn=lambda l, t: None if t == "Boston" else fake_article(l, t))
    assert len(topics) == 4


def test_overlapping_titles_are_rejected():
    a = frozenset({"colonial", "trade", "routes"})
    assert tb.overlap(a, frozenset({"colonial", "trade", "harbour"})) > tb.MAX_OVERLAP
    assert tb.overlap(a, frozenset({"festivals", "winter"})) == 0.0


def test_fetch_records_revision_licence_and_caches(tmp_path):
    calls = []

    def http(url, params):
        calls.append(params["prop"])
        if params["prop"].startswith("extracts"):
            return {"query": {"pages": [{"title": "Example", "fullurl": "https://en.wikipedia.org/wiki/Example",
                                         "extract": "Lead.\n\n== History ==\nText.",
                                         "revisions": [{"revid": 987}]}]}}
        return {"query": {"pages": [{"links": [{"title": "Other"}]}]}}
    a = tb.fetch_article("en", "Example", cache_dir=str(tmp_path), http_get=http)
    assert a["revision_id"] == 987 and a["licence"] == "CC BY-SA 4.0" and a["links"] == ["Other"]
    n = len(calls)
    assert tb.fetch_article("en", "Example", cache_dir=str(tmp_path), http_get=http)["revision_id"] == 987
    assert len(calls) == n                                        # second read came from disk


# ───────────────────────── write + ground ─────────────────────────
def written_text(good, bad, region_=None):
    """good supported sentences (taken from the topic's own source section) interleaved with
    bad invented ones, 5 per paragraph, led by a one-line hook."""
    topic = tb.plan_topics(tl.get_region(REGION_KEY), "en", 1, fetch_fn=fake_article)[0]
    evidence, _ = tb.gather_evidence(topic, fake_article)
    src = [x.strip() for x in re.findall(r"In \d+ the harbour town[^.]*\.", evidence)]
    src = list(dict.fromkeys(src))
    assert len(src) >= good, (len(src), good)
    fake = [f"In {1900 + k} smugglers dug a secret tunnel number {k + 40} beneath Exampleport harbour." for k in range(bad)]
    allv = []
    for i in range(max(good, bad)):
        if i < good:
            allv.append(src[i])
        if i < bad:
            allv.append(fake[i])
    allv[0] = "Hear how Exampleport grew from a muddy landing into a great port of the world."
    return "\n\n".join(" ".join(allv[i:i + 5]) for i in range(0, len(allv), 5))


def fake_judge(system, user, model, *a, **k):
    """The grounding judge: 'secret tunnel' sentences are UNSUPPORTED, the rest SUPPORTED."""
    lines = user.split("FACTUAL SENTENCES:")[1].split("Return the JSON")[0].strip().splitlines()
    verdicts = []
    for ln in lines:
        m = re.match(r"(\d+)\.\s*(.*)", ln)
        if m:
            bad = "secret tunnel" in m.group(2)
            verdicts.append({"i": int(m.group(1)), "verdict": "UNSUPPORTED" if bad else "SUPPORTED",
                             "evidence": "", "legend": False})
    return {"verdicts": verdicts}, 1500, 300


def make_llm(text, in_tok=3000, out_tok=2700):
    calls = []

    def llm(system, user, model, max_tokens):
        calls.append(model)
        return text, in_tok, out_tok
    llm.calls = calls
    return llm


def part_llm(good=40, bad=6, in_tok=3000, out_tok=1500):
    """LOCAL-907D writer mock: writes from the passages of the part it is asked for (the writer
    only sees its own slice of the source), the hook in part 1 only."""
    calls = []

    def llm(system, user, model, max_tokens):
        calls.append(user)
        passages = user.split("SOURCE passages (PART):")[1].split("OVERVIEW")[0]
        src = list(dict.fromkeys(x.strip() for x in re.findall(r"In \d+ the harbour town[^.]*\.", passages)))
        part = int(re.search(r"PART: (\d+) of", user).group(1))
        fake = [f"In {1900 + k} smugglers dug a secret tunnel number {k + 40} beneath Exampleport harbour."
                for k in range(bad)]
        allv = []
        for i in range(max(good, bad)):
            if i < good and i < len(src):
                allv.append(src[i])
            if i < bad:
                allv.append(fake[i])
        if part == 1:
            allv[0] = "Hear how Exampleport grew from a muddy landing into a great port of the world."
        return "\n\n".join(" ".join(allv[i:i + 5]) for i in range(0, len(allv), 5)), in_tok, out_tok
    llm.calls = calls
    return llm


def topic_for(region):
    return tb.plan_topics(region, "en", 1, fetch_fn=fake_article)[0]


def test_write_and_ground_drops_unsupported_and_fills_fields(region):
    topic = topic_for(region)
    llm = part_llm(good=40, bad=6)
    meter = tb.BuildMeter(budget_usd=5.0)
    row = tb.build_segment(topic, region, "en", fetch_fn=fake_article, llm_fn=llm,
                           classify_fn=fake_judge, meter=meter)
    assert row["status"] == "ready"
    assert "secret tunnel" not in row["text"]                        # unsupported sentences dropped
    assert row["text"].rstrip().endswith(tl.CREDIT_LINE)             # credit line present, last
    assert row["credit_line"] == tl.CREDIT_LINE
    assert row["ground_stats"]["dropped"] >= 12
    assert len(llm.calls) == 2                                       # LOCAL-907D: written in parts
    src = row["sources"][0]
    assert src["url"].startswith("https://en.wikipedia.org/wiki/") and src["title"]
    assert src["revision_id"] and src["licence"] == "CC BY-SA 4.0"
    assert row["word_count"] == tl.word_count(row["text"]) >= tb.MIN_SURVIVOR_WORDS
    assert row["est_minutes"] == pytest.approx(row["word_count"] / 150.0, abs=0.01)
    assert (row["centroid_lat"], row["centroid_lng"]) == (region["centre"]["lat"], region["centre"]["lng"])
    assert row["radius_km"] == region["radius_km"] and row["cost_usd"] > 0 and row["language"] == "en"
    assert row["text"].startswith("Hear how")                        # the one-line hook leads


def test_short_survivor_is_rejected(region):
    topic = topic_for(region)
    row = tb.build_segment(topic, region, "en", fetch_fn=fake_article,
                           llm_fn=make_llm(written_text(good=30, bad=45)),
                           classify_fn=fake_judge, meter=tb.BuildMeter(5.0))
    assert row["status"] == "rejected"
    assert row["survivor_words"] < tb.MIN_SURVIVOR_WORDS and "grounded words" in row["reject_reason"]


def test_unjudged_text_is_never_trusted(region):
    """If the judge returns nothing the gate would KEEP every sentence; the builder rejects instead."""
    row = tb.build_segment(topic_for(region), region, "en", fetch_fn=fake_article,
                           llm_fn=make_llm(written_text(75, 0)),
                           classify_fn=lambda s, u, m, *a, **k: (None, 0, 0), meter=tb.BuildMeter(5.0))
    assert row["status"] == "rejected" and row["reject_reason"] == "grounding_unavailable"


def test_clean_spoken_strips_citations_parentheses_tables_markdown():
    raw = "## Title\nThe port opened in 1850 (see note) [1] and grew.\n| a | b |\n- **Bold** point here."
    out = tb.clean_spoken(raw)
    assert "(" not in out and "[" not in out and "|" not in out and "#" not in out and "**" not in out
    assert "The port opened in 1850 and grew." in out


# ───────────────────────── budget ─────────────────────────
def test_budget_stop_before_any_call_when_budget_is_below_the_estimate():
    store = tl.MemorySegmentStore()
    llm = make_llm(written_text(75, 0))
    out = tb.run_build(REGION_KEY, "en", max_segments=3, budget_usd=0.0005, store=store,
                       fetch_fn=fake_article, llm_fn=llm, classify_fn=fake_judge, log=lambda m: None)
    assert out["stopped_on_budget"] and out["built"] == [] and llm.calls == []
    assert out["spent_usd"] == 0.0


def test_budget_stops_the_build_midway_and_never_overspends(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK_BUDGET_ID", "LOCAL-907-TEST")
    monkeypatch.setenv("TASK_BUDGET_USD", "0.60")
    store = tl.MemorySegmentStore()
    llm = make_llm(written_text(75, 0), in_tok=100_000, out_tok=0)            # $0.04 per write call
    out = tb.run_build(REGION_KEY, "en", max_segments=4, budget_usd=0.07, store=store,
                       fetch_fn=fake_article, llm_fn=llm, classify_fn=fake_judge, log=lambda m: None)
    assert out["stopped_on_budget"] is True
    assert len(out["built"]) == 1 and len(llm.calls) == 1                     # the 2nd never started
    assert 0.04 < out["spent_usd"] <= 0.07 + 1e-9
    import task_budget
    assert task_budget.spent_so_far("LOCAL-907-TEST") == pytest.approx(out["spent_usd"], abs=1e-6)
    # the ledger is cumulative: a fresh run is refused once the task budget is gone
    task_budget.record_run("LOCAL-907-TEST", 0.60)
    out2 = tb.run_build(REGION_KEY, "en", max_segments=4, budget_usd=5.0, store=tl.MemorySegmentStore(),
                        fetch_fn=fake_article, llm_fn=llm, classify_fn=fake_judge, log=lambda m: None)
    assert out2["stopped_on_budget"] and out2["built"] == [] and len(llm.calls) == 1


def test_real_build_refuses_without_any_limit():
    with pytest.raises(ValueError, match="without a limit"):
        tb.run_build(REGION_KEY, "en", store=tl.MemorySegmentStore(), fetch_fn=fake_article,
                     llm_fn=make_llm("x"), classify_fn=fake_judge)


def test_rerun_skips_segments_already_built(region):
    store = tl.MemorySegmentStore()
    kw = dict(max_segments=2, budget_usd=5.0, store=store, fetch_fn=fake_article,
              llm_fn=part_llm(good=40, bad=0), classify_fn=fake_judge, log=lambda m: None)
    first = tb.run_build(REGION_KEY, "en", **kw)
    n_calls = len(kw["llm_fn"].calls)
    second = tb.run_build(REGION_KEY, "en", **kw)
    assert len(first["built"]) == 2 and second["built"] == [] and len(kw["llm_fn"].calls) == n_calls


# ───────────────────────── translation ─────────────────────────
class FakeTranslationService:
    """Shaped like translation_service.TranslationService: 'aws' by default, with an AWS fallback."""
    def __init__(self):
        self.translation_engine = "aws"
        self._llm_cost_total = 0.0
        self.aws_calls = 0
        self.llm_calls = 0

    def _translate_text_aws(self, text, lang, preserve_voice_commands=False):
        self.aws_calls += 1
        return "AWS:" + text

    def translate_text(self, text, lang, preserve_voice_commands=False):
        if self.translation_engine == "llm":
            self.llm_calls += 1
            self._llm_cost_total += 0.001
            return f"[{lang}] {text}"
        return self._translate_text_aws(text, lang)


def ready_english(store, n=2):
    ids = []
    for i in range(n):
        ids.append(store.insert_segment({
            "region_key": REGION_KEY, "theme": "history", "title": f"Topic {i}", "language": "en",
            "text": "Para one.\n\n" + tl.CREDIT_LINE, "word_count": 1800, "est_minutes": 12.0,
            "sources": [{"url": "u", "revision_id": 1, "licence": "CC BY-SA 4.0"}],
            "credit_line": tl.CREDIT_LINE, "centroid_lat": 42.36, "centroid_lng": -71.05,
            "radius_km": 35, "audio_path": "x.mp3", "source_segment_id": None,
            "status": "ready", "cost_usd": 0.01}))
    store.insert_segment({"region_key": REGION_KEY, "theme": "food", "title": "Bad", "language": "en",
                          "text": "x", "word_count": 5, "est_minutes": 0.1, "sources": [],
                          "credit_line": "", "status": "rejected", "cost_usd": 0})
    return ids


def test_translation_uses_llm_engine_keeps_source_id_and_never_regrounds(monkeypatch):
    svc = FakeTranslationService()
    fn = tb.make_llm_translate_fn(svc)
    assert svc.translation_engine == "llm"                         # forced, whatever the env said
    with pytest.raises(tb.TranslationEngineError):                 # AWS is closed off
        svc._translate_text_aws("x", "vi")
    monkeypatch.setattr(tb, "ground_text", lambda *a, **k: (_ for _ in ()).throw(AssertionError("re-grounded")))
    store = tl.MemorySegmentStore()
    src_ids = ready_english(store)
    out = tb.run_translate(REGION_KEY, "vi", "en", store=store, translate_fn=fn, budget_usd=1.0,
                           log=lambda m: None)
    assert svc.aws_calls == 0 and svc.llm_calls >= 6
    vi = store.list_segments(REGION_KEY, "vi")
    assert sorted(s["source_segment_id"] for s in vi) == sorted(src_ids)      # rejected one not translated
    assert all(s["status"] == "ready" and s["text"].startswith("[vi]") and s["audio_path"] is None for s in vi)
    assert all(s["sources"] == [{"url": "u", "revision_id": 1, "licence": "CC BY-SA 4.0"}] for s in vi)
    assert out["spent_usd"] > 0
    again = tb.run_translate(REGION_KEY, "vi", "en", store=store, translate_fn=fn, budget_usd=1.0,
                             log=lambda m: None)
    assert again["translated"] == []                                # already translated: skipped


def test_translation_engine_failure_never_falls_back_to_aws():
    svc = FakeTranslationService()

    def failing(text, lang, preserve_voice_commands=False):
        return svc._translate_text_aws(text, lang)                 # what the real service does on LLM failure
    svc.translate_text = failing
    fn = tb.make_llm_translate_fn(svc)
    with pytest.raises(tb.TranslationEngineError):
        fn("hello", "vi")
    assert svc.aws_calls == 0


# ───────────────────────── audio ─────────────────────────
def test_render_audio_via_mocked_kokoro(tmp_path):
    store = tl.MemorySegmentStore()
    ids = ready_english(store, 2)
    store.set_audio_path(ids[1], "keep.mp3")
    seen = []

    def render(text, voice):
        seen.append((len(text), voice))
        return b"MP3"
    done = tb.run_render_audio(REGION_KEY, store=store, out_dir=str(tmp_path), render_fn=render,
                               log=lambda m: None, duration_fn=lambda b: 1.0)
    store2 = store.get_segment(ids[0])
    # ready_english sets audio_path on both; clear the first so it needs rendering
    assert done == []                                              # both already have audio
    store._rows[ids[0]]["audio_path"] = None
    done = tb.run_render_audio(REGION_KEY, store=store, out_dir=str(tmp_path), render_fn=render,
                               log=lambda m: None, duration_fn=lambda b: 1.0)
    assert done == [ids[0]] and seen and seen[0][1] == "Joanna"
    rel = store.get_segment(ids[0])["audio_path"]
    assert open(os.path.join(str(tmp_path), rel), "rb").read().startswith(b"MP3") and store2


def test_tts_chunking_keeps_paragraphs_whole():
    text = "\n\n".join(["word " * 300] * 5)
    chunks = tb._chunks_for_tts(text, max_chars=2500)
    assert all(len(c) <= 2600 for c in chunks) and "\n\n".join(chunks) == text


# ───────────────────────── picker ─────────────────────────
CENTRE = (42.36, -71.05)


def seg(i, theme="history", minutes=11.0, lat=CENTRE[0], lng=CENTRE[1], radius=40, **kw):
    s = {"id": i, "region_key": REGION_KEY, "theme": theme, "title": f"Seg {i}", "language": "en",
         "est_minutes": minutes, "status": "ready", "centroid_lat": lat, "centroid_lng": lng,
         "radius_km": radius, "audio_path": f"a{i}.mp3", "credit_line": tl.CREDIT_LINE}
    s.update(kw)
    return s


def car_tour(km_straight=18.0, extra_stops=None, **kw):
    """Stop 1 -> Stop 2 about km_straight apart (north-south); optional further stops."""
    dlat = km_straight / 111.19
    stops = [{"title": "A", "lat": CENTRE[0], "lng": CENTRE[1], "type_specialty": "Museum"},
             {"title": "B", "lat": CENTRE[0] + dlat, "lng": CENTRE[1], "type_specialty": "Park"}]
    stops += extra_stops or []
    t = {"tour_id": 1, "mode": "car", "area": "rural", "stops": stops}
    t.update(kw)
    return t


POOL = [seg(1, "history", 10), seg(2, "food", 12), seg(3, "nature", 9), seg(4, "arts", 11),
        seg(5, "transport", 13), seg(6, "legends", 10), seg(7, "religion_customs", 12)]


def test_leg_minutes_by_mode():
    t = car_tour(18.0)                                   # 18 km * 1.3 = 23.4 road-km at 45 km/h (LOCAL-909: rural 40-50)
    assert tp.leg_minutes(t, 0) == pytest.approx(31.2, abs=0.5)
    t["area"] = "city"
    assert tp.leg_minutes(t, 0) == pytest.approx(56.2, abs=0.5)           # 25 km/h
    assert tp.leg_minutes(dict(t, mode="bike"), 0) == pytest.approx(100.3, abs=1)    # 14 km/h
    assert tp.leg_minutes(dict(t, mode="walk"), 0) == pytest.approx(311.7, abs=2)    # 4.5 km/h
    assert tp.leg_minutes(dict(t, mode=None, tour_type="driving tour", area=None), 0) == pytest.approx(31.2, abs=0.5)


def test_route_data_overrides_the_estimate():
    t = car_tour(18.0, legs=[{"minutes": 20}])
    assert tp.leg_minutes(t, 0) == 20
    t = car_tour(18.0, legs=[{"distance_km": 45}])
    assert tp.leg_minutes(t, 0) == pytest.approx(60.0)


def test_forty_minute_car_leg_gets_three_to_five_items_that_fit():
    t = car_tour(18.0)
    out = tp.pick_fillings(t, segments=POOL)
    items = out[0]
    minutes = tp.leg_minutes(t, 0)
    assert 3 <= len(items) <= 5
    assert sum(i["minutes"] for i in items) <= minutes + tp.SLACK_MINUTES
    assert [i["segment_id"] for i in items][0] == items[0]["segment_id"]    # first = default auto-play
    assert set(items[0]) >= {"segment_id", "title", "theme", "minutes", "audio_path", "credit_line"}


def test_five_minute_leg_gets_nothing():
    t = car_tour(18.0, extra_stops=[{"title": "C", "lat": CENTRE[0] + 0.1621, "lng": CENTRE[1]}])
    assert tp.leg_minutes(t, 1) < tp.MIN_LEG_MINUTES
    t2 = {"mode": "walk", "stops": [{"title": "A", "lat": CENTRE[0], "lng": CENTRE[1]},
                                   {"title": "B", "lat": CENTRE[0] + 0.0029, "lng": CENTRE[1]}]}
    assert tp.leg_minutes(t2, 0) == pytest.approx(5.0, abs=0.6)
    assert tp.pick_fillings(t2, segments=POOL) == {}
    assert 1 not in tp.pick_fillings(t, segments=POOL)


def test_no_segment_repeats_within_a_tour_or_across_recent_tours():
    stops = [{"title": s, "lat": CENTRE[0] + 0.16 * i, "lng": CENTRE[1]} for i, s in enumerate("ABCD")]
    t = {"mode": "car", "area": "rural", "stops": stops}
    pool = [dict(p, radius_km=120) for p in POOL] + [seg(10 + i, "history", 9, radius=120) for i in range(8)]
    out = tp.pick_fillings(t, segments=pool)
    ids = [i["segment_id"] for legs in out.values() for i in legs]
    assert len(out) == 3 and len(ids) == len(set(ids))
    out2 = tp.pick_fillings(t, segments=pool, recent_segment_ids=ids[:4])
    ids2 = [i["segment_id"] for legs in out2.values() for i in legs]
    assert not set(ids2) & set(ids[:4]) and len(ids2) == len(set(ids2))


def test_region_match_excludes_far_segments():
    far = seg(99, "history", 10, lat=10.9, lng=108.2)
    out = tp.pick_fillings(car_tour(18.0), segments=POOL + [far])
    assert 99 not in [i["segment_id"] for i in out[0]]
    assert tp.pick_fillings(car_tour(18.0), segments=[far]) == {}


def test_theme_fit_to_stop_type_ranks_first():
    t = car_tour(18.0)                                   # Museum -> history, Park -> nature
    top = [i["theme"] for i in tp.pick_fillings(t, segments=POOL)[0]][:2]
    assert set(top) == {"history", "nature"}


def test_listener_weights_reorder_the_list():
    t = car_tour(18.0)
    pool = [seg(i, th, 9) for i, th in enumerate(["food", "arts", "transport", "legends", "religion_customs"], 1)]
    base = [i["theme"] for i in tp.pick_fillings(t, segments=pool)[0]]
    liked = [i["theme"] for i in tp.pick_fillings(t, {"religion_customs": 5.0}, segments=pool)[0]]
    hated = [i["theme"] for i in tp.pick_fillings(t, {"food": -5.0}, segments=pool)[0]]
    assert liked[0] == "religion_customs" and base[0] != "religion_customs"
    assert base[0] == "food" and "food" not in hated[:1] and hated != base


def test_picker_is_deterministic_and_pure():
    t = car_tour(18.0)
    before = json.dumps(t, sort_keys=True)
    a = tp.pick_fillings(t, {"food": 1.0}, segments=POOL)
    b = tp.pick_fillings(t, {"food": 1.0}, segments=list(reversed(POOL)))
    assert a == b and json.dumps(t, sort_keys=True) == before


def test_only_ready_segments_in_the_tour_language_are_offered():
    pool = [seg(1, status="draft"), seg(2, status="rejected"), seg(3, language="vi"), seg(4)]
    out = tp.pick_fillings(car_tour(18.0), segments=pool)
    assert [i["segment_id"] for i in out[0]] == [4]


# ───────────────────────── events → weights ─────────────────────────
def test_weight_deltas():
    assert le.weight_delta("finish") == 1.0
    assert le.weight_delta("skip", 10) == -1.0 and le.weight_delta("skip", 59.9) == -1.0
    assert le.weight_delta("skip", 60) == -0.3 and le.weight_delta("skip", 300) == -0.3
    assert le.weight_delta("choose") == 0.5 and le.weight_delta("start") == 0.0


def test_replay_decay_and_clamp():
    themes = {1: "food", 2: "history"}
    ev = lambda tour, seg_, act, at=0: {"tour_id": tour, "segment_id": seg_, "action": act, "at_sec": at}
    w = le.replay([ev("t1", 1, "finish"), ev("t1", 2, "skip", 5)], themes)
    assert w == {"food": 1.0, "history": -1.0}
    w = le.replay([ev("t1", 1, "finish"), ev("t2", 2, "choose")], themes)       # t2 decays t1's weights
    assert w["food"] == pytest.approx(0.95) and w["history"] == pytest.approx(0.5)
    w = le.replay([ev(f"t{i}", 1, "finish") for i in range(1, 12)], themes)
    assert w["food"] == 5.0 or w["food"] <= le.WEIGHT_MAX                      # clamped
    assert le.replay([ev("t", 1, "finish")] * 9, themes)["food"] == 5.0
    assert le.replay([ev("t", 2, "skip", 1)] * 9, themes)["history"] == -5.0


def test_apply_event_updates_weights_and_decays_once_per_new_tour():
    repo = le.MemoryRepo({1: "food", 2: "history"})
    base = {"user_id": "u1", "at_sec": 0.0}
    le.apply_event(repo, dict(base, tour_id="t1", segment_id=1, action="finish"))
    le.apply_event(repo, dict(base, tour_id="t1", segment_id=1, action="finish"))     # same tour: no decay
    assert repo.get_weights("u1") == {"food": 2.0}
    r = le.apply_event(repo, dict(base, tour_id="t2", segment_id=2, action="skip", at_sec=12.0))
    assert r["weight_delta"] == -1.0 and r["theme"] == "history"
    assert repo.get_weights("u1")["food"] == pytest.approx(1.9)                       # 2.0 x 0.95
    assert repo.get_weights("u1")["history"] == -1.0
    le.apply_event(repo, dict(base, tour_id="t2", segment_id=2, action="start"))      # start: stored, no move
    assert repo.get_weights("u1")["history"] == -1.0 and len(repo.events) == 4
    with pytest.raises(le.UnknownSegment):
        le.apply_event(repo, dict(base, tour_id="t2", segment_id=77, action="finish"))


def test_recent_segment_ids_covers_last_five_tours_only():
    repo = le.MemoryRepo({i: "food" for i in range(1, 9)})
    for i in range(1, 8):
        le.apply_event(repo, {"user_id": "u", "tour_id": f"t{i}", "segment_id": i, "action": "finish", "at_sec": 0})
    assert repo.recent_segment_ids("u") == [3, 4, 5, 6, 7]
    assert repo.recent_segment_ids("other") == []


def test_validate_event():
    ok = le.validate_event({"user_id": "u", "tour_id": 12, "segment_id": "5", "action": "skip", "at_sec": 30})
    assert ok == {"user_id": "u", "tour_id": "12", "segment_id": 5, "action": "skip", "at_sec": 30.0}
    bad = [None, [], {}, {"user_id": "u", "tour_id": "t", "segment_id": 1, "action": "like"},
           {"user_id": "", "tour_id": "t", "segment_id": 1, "action": "skip"},
           {"user_id": "u", "tour_id": "t", "segment_id": 0, "action": "skip"},
           {"user_id": "u", "tour_id": "t", "segment_id": "x", "action": "skip"},
           {"user_id": "u", "tour_id": "t", "segment_id": 1, "action": "skip", "at_sec": -1},
           {"user_id": "u", "tour_id": "t", "segment_id": 1, "action": "skip", "at_sec": "soon"},
           {"user_id": "u" * 200, "tour_id": "t", "segment_id": 1, "action": "skip"}]
    for b in bad:
        with pytest.raises(le.ValidationError):
            le.validate_event(b)


class RecordingConn:
    def __init__(self):
        self.sql = []
        self.committed = 0

    def cursor(self):
        outer = self

        class C:
            def execute(self, sql, params=()):
                outer.sql.append((sql, params))

            def fetchone(self):
                return ("history",) if "SELECT theme" in outer.sql[-1][0] else (7,) if "RETURNING" in outer.sql[-1][0] else None

            def fetchall(self):
                return []

            def close(self):
                pass
        return C()

    def commit(self):
        self.committed += 1


def test_pg_repo_sql_is_parameterised_and_never_deletes():
    conn = RecordingConn()
    repo = le.PgRepo(conn)
    le.apply_event(repo, {"user_id": "u'; DROP TABLE x;--", "tour_id": "t", "segment_id": 3,
                          "action": "finish", "at_sec": 0.0})
    text = " ".join(s for s, _ in conn.sql)
    assert "DELETE" not in text.upper() and "DROP" not in text.upper()
    assert all("DROP TABLE x" not in s for s, _ in conn.sql)                    # value only in params
    assert any("ON CONFLICT (user_id, theme)" in s and "LEAST" in s and "GREATEST" in s for s, _ in conn.sql)
    assert conn.committed == 1


# ───────────────────────── API + payload ─────────────────────────
def test_listening_events_endpoint(monkeypatch):
    import user_api_with_cors as api
    repo = le.MemoryRepo({5: "food"})
    monkeypatch.setattr(api, "_listening_repo", lambda: repo)
    c = api.app.test_client()
    r = c.post("/listening-events", json={"user_id": "u", "tour_id": "t", "segment_id": 5,
                                          "action": "finish", "at_sec": 600})
    assert r.status_code == 201 and r.get_json()["weight_delta"] == 1.0
    assert repo.get_weights("u") == {"food": 1.0}
    assert c.post("/listening-events", json={"user_id": "u", "tour_id": "t", "segment_id": 5,
                                             "action": "dance"}).status_code == 400
    assert c.post("/listening-events", data="not json", content_type="text/plain").status_code == 400
    assert c.post("/listening-events", json={"user_id": "u", "tour_id": "t", "segment_id": 6,
                                             "action": "skip"}).status_code == 404
    assert len(repo.events) == 1                                            # only the valid one stored
    assert c.open("/listening-events", method="OPTIONS").status_code == 200


def test_payload_is_additive_and_old_fields_unchanged():
    old = {"job_id": "j", "status": "completed", "progress": "done", "location": "L", "tour_type": "walking",
           "total_stops": 2, "created_at": "now", "netlify_ready": True, "coordinates": [1.0, 2.0],
           "final_tour_id": 9, "replaced_version_no": None}
    snapshot = json.loads(json.dumps(old))
    assert fp.attach_fillings(dict(old), []) == snapshot                    # nothing to add: untouched
    fillings = fp.build_fillings(car_tour(18.0), {"food": 1.0}, segments=POOL)
    new = fp.attach_fillings(dict(old), fillings)
    assert {k: v for k, v in new.items() if k != "fillings"} == snapshot
    f = new["fillings"][0]
    assert f["leg"] == 0 and f["after_stop"] == 1 and f["minutes"] == pytest.approx(31.2, abs=0.5)
    it = f["items"][0]
    assert set(it) >= {"segment_id", "title", "theme", "minutes", "audio_url", "credit_line"}
    assert it["audio_url"].endswith(".mp3") and it["credit_line"] == tl.CREDIT_LINE
    no_audio = fp.build_fillings(car_tour(18.0), segments=[seg(1, audio_path=None)] * 1)
    assert no_audio == []                                   # [LOCAL-907E] text-only items are left out


def test_orchestrator_wiring_is_additive():
    src = open(os.path.join(ROOT, "tour_orchestrator_service.py"), encoding="utf-8").read()
    assert 'response["fillings"] = job["fillings"]' in src
    assert 'response["final_tour_id"] = job["final_tour_id"]' in src       # old field still there
    assert "fillings_for_tour" in src


TOUR_TEXT = """Stop 1: Old Fort
Coordinates: 42.3601, -71.0589
Type/Specialty: Historic fort and museum
Orientation: stand at the gate.

Stop 2: Harbour Beach
Coordinates: 42.5, -71.0589
Type/Specialty: Beach and park
"""


def test_stops_from_tour_text_and_fillings_for_tour_never_raises():
    stops = fp.stops_from_tour_text(TOUR_TEXT)
    assert [s["title"] for s in stops] == ["Old Fort", "Harbour Beach"]
    assert stops[0]["lat"] == 42.3601 and "fort" in stops[0]["type_specialty"].lower()

    def broken():
        raise RuntimeError("no db")
    assert fp.fillings_for_tour(TOUR_TEXT, "driving tour", "u", connect=broken) == []
    assert fp.fillings_for_tour("no stops here", connect=broken) == []


def test_fillings_for_tour_reads_only_and_disabled_by_env(monkeypatch):
    class Conn(RecordingConn):
        def cursor(self):
            outer = self

            class C:
                def execute(self, sql, params=()):
                    outer.sql.append((sql, params))

                def fetchall(self):
                    last = outer.sql[-1][0]
                    if "FROM topic_segments" in last:
                        return [(1, REGION_KEY, "history", "Seg 1", "en", "", 1800, 12.0, [], tl.CREDIT_LINE,
                                 CENTRE[0], CENTRE[1], 40.0, "a.mp3", [3.0, 7.5], None, "ready", 0.01, None)]
                    return []

                def fetchone(self):
                    return None

                def close(self):
                    pass
            return C()

        def rollback(self):
            pass

        def close(self):
            pass
    conn = Conn()
    out = fp.fillings_for_tour(TOUR_TEXT, "driving tour", "u", connect=lambda: conn)
    assert out and out[0]["items"][0]["segment_id"] == 1
    assert all(re.match(r"\s*SELECT", s) for s, _ in conn.sql)                # read-only
    monkeypatch.setenv("TOPIC_FILLINGS_ENABLED", "false")
    assert fp.fillings_for_tour(TOUR_TEXT, "driving tour", "u", connect=lambda: conn) == []
