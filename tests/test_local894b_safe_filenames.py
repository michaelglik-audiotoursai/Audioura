#!/usr/bin/env python3
"""LOCAL-894B -- the full 777-char description reached the file paths ("File name too long").
Also: header mode, other-place aboutness, snippet refill. Offline; generic (D769)."""
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import safe_filename as sf  # noqa: E402
from test_local894_user_list_integrity import REQUEST  # noqa: E402

VI = ("Chùa Linh Sơn Trường Thọ trên núi Tà Cú, tỉnh Bình Thuận — hành trình nửa ngày bằng ô tô "
      "cho gia đình, qua Phan Thiết và những vườn thanh long. ")
LONG_VI = (VI * 30)[:2000]
LONG_EN = ("Create a half-day driving tour from a resort to a mountain and back, " * 40)[:2000]


def _b(s):
    return len(s.encode("utf-8"))


class TestHelper:
    @pytest.mark.parametrize("text", [LONG_VI, LONG_EN, REQUEST, "x" * 5000, "é" * 900])
    @pytest.mark.parametrize("style", ["alnum", "orch"])
    def test_slug_bounded(self, text, style):
        s = sf.safe_component(text, style=style)
        assert _b(s) <= sf.MAX_SLUG_BYTES
        s.encode("utf-8").decode("utf-8")
        assert "/" not in s and "\\" not in s and "\x00" not in s

    def test_short_names_unchanged(self):
        assert sf.safe_component("Boston, MA", style="orch") == "boston_ma"
        assert sf.safe_component("Ham Tien, Mui Ne", style="alnum") == "Ham_Tien__Mui_Ne"
        z, d = sf.tour_zip_names("Boston, MA", "walking", "abcdef1234567", None)
        assert z == "boston_ma_walking_abcdef12.zip" and d == "boston_ma_walking_abcdef12"
        assert sf.generator_output_filename("Boston, MA", "walking", "20260101_000000") == \
            "Boston__MA_walking_tour_20260101_000000.txt"
        assert sf.download_name("Boston, MA") == "boston_ma_tour.zip"

    def test_long_names_differ_by_hash_not_prefix(self):
        a = sf.safe_component(REQUEST, style="orch")
        b = sf.safe_component(REQUEST + " Also add a lunch stop.", style="orch")
        assert a != b and a[:60] == b[:60]

    def test_preferred_short_title_is_the_visible_part(self):
        s = sf.safe_component(REQUEST, preferred="Caty Mui Ne Resort to Ta Cu Mountain", style="orch")
        assert s.startswith("caty_mui_ne_resort_to_ta_cu_mountain_") and _b(s) <= 80

    @pytest.mark.parametrize("text", [LONG_VI, LONG_EN, REQUEST])
    def test_assembled_names_under_255(self, text):
        z, d = sf.tour_zip_names(text, "x" * 300, "0123456789abcdef", None)
        assert _b(z) <= 255 and _b(d) <= 255 and z.endswith(".zip")
        g = sf.generator_output_filename(text, "y" * 300, "20260101_000000")
        assert _b(g) <= 255 and g.endswith(".txt")
        assert _b(sf.download_name(text)) <= 255

    def test_real_filesystem_accepts_the_names(self, tmp_path):
        for text in (LONG_VI, LONG_EN, REQUEST):
            z, d = sf.tour_zip_names(text, "driving", "deadbeefcafe", None)
            (tmp_path / z).write_bytes(b"zip")
            (tmp_path / d).mkdir()
            g = sf.generator_output_filename(text, "driving", "20260101_000000")
            (tmp_path / g).write_text("tour", encoding="utf-8")
        assert len(os.listdir(tmp_path)) == 9


class TestWiring:
    def _src(self, name):
        return open(os.path.join(ROOT, name), encoding="utf-8").read()

    def test_no_raw_location_builders_left(self):
        orch = self._src("tour_orchestrator_service.py")
        assert "safe_location" not in orch and "_tzn894b" in orch
        gen = self._src("generate_tour_text_service.py")
        assert "''.join(c if c.isalnum()" not in gen and "_gof894b" in gen
        assert "safe_location = ''.join" not in self._src("generate_tour_text.py")
        assert "_dn894b" in self._src("map_delivery_service.py")
        assert "_sn894b" in self._src("tour_generation_modernized.py")

    def test_images_ship_the_helper(self):
        assert re.search(r"(?m)^COPY safe_filename\.py /app/", self._src("Dockerfile.orchestrator"))
        assert re.search(r"(?m)^COPY safe_filename\.py /app/", self._src("Dockerfile.modernized"))
        assert "COPY *.py /app/" in self._src("Dockerfile.generator")

    def test_download_reads_the_stored_name(self):
        orch = self._src("tour_orchestrator_service.py")
        assert 'os.path.join(TOURS_DIR, job["output_zip"])' in orch
        assert 'os.path.join(TOURS_DIR, job["extract_dir"])' in orch

    def test_modernized_zip_with_a_long_tour_name(self, tmp_path):
        import tour_generation_modernized as tgm
        mp = pytest.MonkeyPatch()
        mp.setattr(tgm, "TOURS_DIR", str(tmp_path))
        try:
            name = tgm.create_modernized_tour_zip(
                {"tour_name": REQUEST, "text_content": ["a"], "audio_files": [b"x"]},
                "deadbeefcafe")
        finally:
            mp.undo()
        assert _b(name) <= 255 and (tmp_path / name).exists()


class TestHeaderMode:
    def test_driving_intro_is_not_walking(self):
        import spoken_text_hygiene as sth
        t = "This is a step-by-step audio-guided walking tour of Ham Tien, Mui Ne.\n\nStop 1: A\n"
        out, n = sth.enforce_header_mode(t, "driving")
        assert n == 1 and "audio-guided driving tour of Ham Tien, Mui Ne." in out
        assert "walking" not in out.splitlines()[0]

    def test_title_line(self):
        import spoken_text_hygiene as sth
        t = "Step-by-Step Audio Guided Tour: Mui Ne to Ta Cu - Walking Tour\nTour-Category: driving\n"
        out, n = sth.enforce_header_mode(t, "driving")
        assert n == 1 and out.startswith("Step-by-Step Audio Guided Tour: Mui Ne to Ta Cu - Driving Tour")

    def test_walking_and_unknown_are_untouched(self):
        import spoken_text_hygiene as sth
        t = "This is a step-by-step audio-guided walking tour of Hue.\n"
        assert sth.enforce_header_mode(t, "walking") == (t, 0)
        assert sth.enforce_header_mode(t, "") == (t, 0)

    def test_body_is_never_rewritten(self):
        import spoken_text_hygiene as sth
        t = ("This is a step-by-step audio-guided walking tour of Hue.\n\nStop 1: A\n"
             "A walking tour guide once said so.\n")
        out, _ = sth.enforce_header_mode(t, "driving")
        assert out.split("\n", 1)[1] == t.split("\n", 1)[1]

    def test_log_line_names_the_effective_category(self):
        import generate_tour_text as g
        line = g._infer_category_log_line("driving", "walking", "vehicle")
        assert "category='driving'" in line and "source=explicit" in line
        assert g.effective_category_894b("walking", "vehicle") == "driving"
        assert g.effective_category_894b("museum", "vehicle") == "museum"
        assert g.effective_category_894b("walking", "on_foot") == "walking"


EV = json.load(open(os.path.join(ROOT, "submission_artifacts", "local894",
                                 "evidence_bundle.json"), encoding="utf-8"))


class TestOtherPlaceAboutness:
    def setup_method(self):
        import aboutness as ab
        ab.set_route_region(REQUEST, "Ham Tien, Mui Ne", "Binh Thuan province",
                            "Caty Mui Ne Resort", "Ta Cu Mountain", "Phan Thiet")

    def teardown_method(self):
        import aboutness as ab
        ab.set_route_region()

    def test_fansipan_sentence_is_dropped(self):
        import aboutness as ab
        t = "The cable car ascent"
        s = ["Fansipan is the tallest peak in Vietnam, located in the north in Sa Pa.",
             "As you rise, the forest canopy opens beneath the cabin.",
             "The climate changes quickly during your ascent.",
             "You leave behind the coastal heat as you go higher."]
        out, rep = ab.clean_stop(t, s, EV[t])
        assert not any("Fansipan" in x for x in out) and len(out) == 3
        assert rep["tangent"]

    def test_in_region_sentences_stay(self):
        import aboutness as ab
        ref = ab.Referent("The cable car ascent")
        for s in ["Ta Cu Mountain is the highest peak in Binh Thuan province.",
                  "The Reclining Buddha in Ham Tien is a colossal statue that is 49 meters long.",
                  "Phan Thiet was a Cham stronghold near Mui Ne."]:
            assert ab.other_place_reason(s, ref) is None, s

    def test_no_region_no_change(self):
        import aboutness as ab
        ab.set_route_region()
        ref = ab.Referent("The cable car ascent")
        assert ab.other_place_reason(
            "Fansipan is the tallest peak in Vietnam, located in the north in Sa Pa.", ref) is None

    def test_region_follows_the_request(self):
        import aboutness as ab
        import generate_tour_text as g
        ab.set_route_region()
        g._apply_description_location_894(REQUEST, "driving")
        assert ab._REGION_TOKS
        g._apply_description_location_894("Boston, MA", "walking")
        assert not ab._REGION_TOKS


class TestSnippetRefill:
    def test_pagoda_gets_real_facts_from_its_own_evidence(self):
        import aboutness as ab
        t = "Linh Son Truong Tho Pagoda"
        facts = ab.snippet_facts(EV[t], t)
        assert len(facts) >= 4 and "Tran Huu Duc" in " ".join(facts)
        assert not re.search(r"(?i)tickets|skip-the-line|promos|linocut", " ".join(facts))
        for f in facts:
            assert f[:40] in EV[t]

    def test_other_place_snippet_is_not_a_fact_for_the_cable_car(self):
        import aboutness as ab
        ab.set_route_region(REQUEST, "Ta Cu Mountain", "Binh Thuan province")
        try:
            t = "The cable car ascent"
            assert not any("Fansipan" in f for f in ab.snippet_facts(EV[t], t))
        finally:
            ab.set_route_region()

    def test_gate_refill_uses_snippet_facts(self):
        src = open(os.path.join(ROOT, "strict_grounding_gate.py"), encoding="utf-8").read()
        assert "snippet_facts" in src


class TestServiceSavePathEndToEnd:
    """The class of failure LEAD saw: the generator service with the FULL 777-char description
    as ``location`` -- the job must complete and the files must be written."""

    def test_generator_job_completes_and_writes_the_file(self, tmp_path, monkeypatch):
        import generate_tour_text_service as svc
        assert len(REQUEST) > 700
        monkeypatch.setattr(svc, "TOURS_DIR", str(tmp_path))
        text = ("Step-by-Step Audio Guided Tour: Mui Ne to Ta Cu - Driving Tour\n"
                "Tour-Category: driving\n\nStop 1: A\n\nCoordinates: 10.9, 108.2\n\nBody here.\n")

        def fake_gen(location, tour_type, out, *a, **k):
            assert location == REQUEST                      # the generator keeps the WHOLE description
            open(out, "w", encoding="utf-8").write(text)
            return text, out, (10.9, 108.2)
        monkeypatch.setattr(svc, "generate_tour_text", fake_gen)
        job_id = "j894b-e2e-0001"
        svc.ACTIVE_JOBS[job_id] = {"status": "queued"}
        svc.generate_tour_async(job_id, REQUEST, "driving", 8)
        job = svc.ACTIVE_JOBS[job_id]
        job = job if isinstance(job, dict) else dict(job)
        assert "File name too long" not in json.dumps(job, default=str)
        assert job.get("status") == "completed", job
        out = job["output_file"]
        assert _b(out) <= 255 and (tmp_path / out).read_text(encoding="utf-8") == text
        assert out.endswith(".txt")


EV_LIVE = json.load(open(os.path.join(ROOT, "submission_artifacts", "local894b",
                                      "evidence_bundle.json"), encoding="utf-8"))
TOUR_LIVE = open(os.path.join(ROOT, "submission_artifacts", "local894b", "tour.txt"),
                 encoding="utf-8").read()


def _set_route():
    import aboutness as ab
    import user_list_integrity as uli
    i = uli.derive_request_place(REQUEST, "driving")
    parts = (i["location"], i["scope"], i["origin"], i["destination"], " ".join(i["through"]))
    ab.set_route_region(REQUEST, *parts)
    ab.set_route_places(*parts)


class TestOtherPlaceEvidence:
    """The ONE live run (894B) still shipped Fansipan: the cable-car stop's whole evidence was another
    province's cable car, so every sentence was 'supported'. Evidence-level rule, after the run."""

    def setup_method(self):
        _set_route()

    def teardown_method(self):
        import aboutness as ab
        ab.set_route_region()

    def test_route_places_are_phrases(self):
        import aboutness as ab
        assert {"ham tien", "mui ne", "ta cu", "binh thuan", "phan thiet"} <= set(ab._PLACE_TOKS)

    @pytest.mark.parametrize("bundle", ["local894", "local894b"])
    def test_only_the_other_place_evidence_is_dropped(self, bundle):
        import aboutness as ab
        ev = json.load(open(os.path.join(ROOT, "submission_artifacts", bundle,
                                         "evidence_bundle.json"), encoding="utf-8"))
        dropped = [k for k, v in ev.items() if ab.strip_other_place_evidence(v)[1]]
        assert dropped == ["The cable car ascent"], dropped

    def test_gate_removes_fansipan_from_the_delivered_tour(self):
        import strict_grounding_gate as g
        out, _ = g.ground_tour_text(TOUR_LIVE, EV_LIVE, location="Ham Tien, Mui Ne",
                                    classify_fn=lambda *a, **k: (None, 0, 0), register="driving")
        assert "fansipan" in TOUR_LIVE.lower()
        low = out.lower()
        assert "fansipan" not in low and "sa pa" not in low and "toc tien" not in low
        assert len(re.findall(r"(?m)^Stop \d+:", out)) == 8

    def test_no_region_no_change(self):
        import aboutness as ab
        ab.set_route_region()
        assert ab.strip_other_place_evidence(EV_LIVE["The cable car ascent"])[1] == 0
