#!/usr/bin/env python3
"""[LOCAL-767] A church / civic / facility tour must DEGRADE, not hard-fail, when
Gemini returns nothing — plus [LOCAL-275] the `_venue_parts_used` NameError.

## The field failure (GCloud_Storied, 2026-10-25 17:3x, ClickUp wdvrdaz5vd)

POST /generate-complete-tour {"location":"Newton City Hall, Newton, MA",
"tour_type":"landmark","total_stops":1} failed on `tour-generator-storied`: the
venue is `worship_civic`, so `generate_tour_text` called `venue_parts.
build_tour_stops()`, whose `default_ask` is `story_leads.gemini_with_sources()`.
With no usable Gemini key that returns '', the D577 outage guard raised
`ServiceUnavailable`, and the caller RE-RAISED it — taking out the whole tour.
Beta generated these venues fine (it had no venue-parts path). A missing or
exhausted Gemini key (a prepaid balance!) must never take out a whole CLASS of
tours.

## What this proves, and why each test is RED on the baseline

1. `build_tour_stops` with an empty ask AND a dead probe still RAISES
   `ServiceUnavailable`. This is unchanged and deliberately so — D582 says an
   outage must stay distinguishable from "this venue has nothing to describe", so
   the SIGNAL is kept. (Green on both trees; it is the contract the fix relies on.)

2. The CALLER (`generate_tour_text`) must CATCH `ServiceUnavailable` and fall back
   to the standard path with the LOCAL-767 log, NOT re-raise. On the baseline the
   caller body contains `raise` inside the `except _vp.ServiceUnavailable` block
   and the abort banner `*** SERVICE UNAVAILABLE — ABORTING ***`; the fix replaces
   both with `[LOCAL-767] venue-parts unavailable (reason=…) — falling back to
   standard stops`. Asserted by source inspection — the LOCAL-485 pattern, because
   `generate_tour_text` makes network calls and cannot run offline.

3. D577's own case still refuses: a venue that TRULY has nothing to describe while
   the service is LIVE must still degrade to [] (not raise) — the fix must not
   turn every empty answer into an outage. (Green on both; guards against
   over-correction.)

4. [LOCAL-275] `_build_closing_offer` references `_venue_parts_used`, which is a
   LOCAL of `generate_tour_text`, not a parameter of this module-level function —
   so Part 2 raised `NameError: name '_venue_parts_used' is not defined`, caught by
   `except Exception as e: print("Part 2 error: {e}")`. The fix adds a
   `venue_parts_used=False` parameter. RED on the baseline: the signature has no
   such parameter and the body names the undefined global.

5. The startup log line `[LOCAL-767] GEMINI key present=<bool>` exists in the
   generator (source assertion), and never prints the key value.

Deterministic and offline: every model call into venue_parts is INJECTED, exactly
as the module was designed for, and the caller tests read source text. No network,
no key required — which is the whole point, since the failure IS a keyless run.
"""
import inspect
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import venue_parts as vp
import generate_tour_text as gtt


# ── Injected model stand-ins ─────────────────────────────────────────────────
def _ask_empty(_prompt):
    """A keyless/dead Gemini: every ungrounded ask comes back empty."""
    return ''


def _ask_grounded_empty(_prompt):
    """A keyless/dead grounded Gemini: ('', []) — exactly default_ask_grounded's
    keyless return."""
    return '', []


# A LIVE service that genuinely has nothing to DESCRIBE for this one obscure venue:
# Q1 answers ("a small roadside shrine"), Q2 answers with real class parts, and the
# grounded Q3 positively reports that THIS shrine has none of them (everything
# "absent"), with a probe that answers "ok". That is "we asked, the venue has
# nothing" — D577's own case — and it must degrade to [], never raise an outage.
def _ask_live_but_venue_unknown(prompt):
    p = prompt.lower()
    if 'reply with the single word' in p:
        return 'ok'
    if 'what kind of place' in p:
        return 'a small roadside shrine'
    if 'consist of' in p or 'parts, spaces and fixtures' in p:
        return '["Niche", "Statue", "Offering Shelf", "Railing"]'
    return ''          # everything venue-specific: the service is UP, the venue is obscure


def _ask_grounded_live_but_venue_unknown(prompt):
    p = prompt.lower()
    if 'reply with the single word' in p:
        return 'ok', []          # LIVE — the probe succeeds
    # Q3 "which of these does it have?" — the service answers, and the honest answer
    # is NONE: a bare roadside shrine has no niche/statue/shelf/railing of note.
    if 'which of the' in p and 'actually have' in p:
        return ('{"present": [], "absent": ["Niche", "Statue", "Offering Shelf", '
                '"Railing"], "unknown": []}'), []
    return '', []                # story questions: nothing is known, but service is up


# ── 1. The signal is kept: dead service still RAISES ─────────────────────────
class TestOutageStillRaises:
    def test_empty_ask_and_dead_probe_raises_service_unavailable(self):
        try:
            vp.build_tour_stops('Newton City Hall', 'Newton, MA', 1,
                                ask=_ask_empty, ask_grounded=_ask_grounded_empty)
        except vp.ServiceUnavailable:
            print("  ✅ empty ask + dead probe still raises ServiceUnavailable "
                  "(outage stays visible — D582)")
            return
        raise AssertionError(
            "build_tour_stops must still RAISE ServiceUnavailable when the ask is "
            "empty and the liveness probe also fails — the outage signal is what "
            "the LOCAL-767 fallback is built on; swallowing it reintroduces D582.")


# ── 2. THE FIX: the caller degrades, it does not re-raise ────────────────────
# generate_tour_text makes network calls and cannot run offline (see LOCAL-485),
# so the behaviour is asserted against the SOURCE of the except block that handles
# ServiceUnavailable — the same source-assertion technique LOCAL-485 uses to prove
# wiring that cannot be exercised in a unit test.
class TestCallerDegradesNotAborts:
    def _caller_src(self):
        src = inspect.getsource(getattr(gtt, "_generate_tour_text_impl", gtt.generate_tour_text))
        m = re.search(r'except _vp\.ServiceUnavailable.*?(?=\n        except |\n    if )',
                      src, re.S)
        assert m, "could not locate the venue-parts ServiceUnavailable handler"
        return m.group(0)

    def test_handler_does_not_reraise(self):
        block = self._caller_src()
        bare_raise = re.search(r'^\s*raise\s*$', block, re.M)
        assert not bare_raise, (
            "the ServiceUnavailable handler still RE-RAISES — a keyless/dead Gemini "
            "will hard-fail the whole tour (the LOCAL-767 field failure). It must "
            "fall back to the standard stop path instead.")
        print("  ✅ the ServiceUnavailable handler no longer re-raises")

    def test_handler_logs_local767_fallback(self):
        block = self._caller_src()
        assert 'LOCAL-767' in block and 'falling back to standard stops' in block, (
            "the handler must LOUDLY log '[LOCAL-767] venue-parts unavailable "
            "(reason=…) — falling back to standard stops' so the degrade is not "
            "silent (D582).")
        assert 'ABORTING' not in block, (
            "the old '*** SERVICE UNAVAILABLE — ABORTING ***' banner must be gone.")
        print("  ✅ the handler logs the LOCAL-767 loud-degrade line, no ABORT banner")

    def test_handler_clears_venue_parts_used(self):
        block = self._caller_src()
        assert re.search(r'_venue_parts_used\s*=\s*False', block), (
            "after the outage the handler must set _venue_parts_used = False so "
            "every downstream branch takes its ordinary (standard) route.")
        print("  ✅ the handler leaves _venue_parts_used False → standard path")


# ── 3. D577's own case survives: live service, obscure venue -> degrade, not raise
class TestLiveServiceEmptyVenueDegrades:
    def test_live_probe_with_empty_venue_returns_empty_not_raise(self):
        try:
            stops, ev = vp.build_tour_stops(
                'Obscure Roadside Shrine #7', 'Nowhere', 1,
                ask=_ask_live_but_venue_unknown,
                ask_grounded=_ask_grounded_live_but_venue_unknown)
        except vp.ServiceUnavailable as e:
            raise AssertionError(
                "a LIVE service (probe answers 'ok') that simply has nothing for an "
                f"obscure venue must DEGRADE to [], never raise an outage: {e}")
        assert stops == [], f"expected no stops for an unknown venue, got {stops}"
        print("  ✅ live service + unknown venue degrades to [] (D577 case intact)")


# ── 4. [LOCAL-275] _build_closing_offer must accept venue_parts_used ─────────
class TestLocal275ClosingOfferParam:
    def test_signature_has_venue_parts_used(self):
        sig = inspect.signature(gtt._build_closing_offer)
        assert 'venue_parts_used' in sig.parameters, (
            "[LOCAL-275] _build_closing_offer must take a venue_parts_used "
            "parameter — the body references it, and without the parameter it is "
            "an undefined name (a module-level function cannot see the "
            "_venue_parts_used local of generate_tour_text). That NameError is the "
            "'Part 2 error: name _venue_parts_used is not defined' from the field.")
        print("  ✅ _build_closing_offer takes venue_parts_used")

    def test_body_does_not_name_the_undefined_global(self):
        src = inspect.getsource(gtt._build_closing_offer)
        assert '_venue_parts_used' not in src, (
            "[LOCAL-275] the body still names the undefined global "
            "'_venue_parts_used'; it must use the 'venue_parts_used' parameter.")
        print("  ✅ _build_closing_offer body uses the parameter, not the undefined global")

    def test_part2_runs_without_nameerror(self):
        poi_list = [{'name': 'Main Hall', 'coordinates': '42.3370, -71.2092'},
                    {'name': 'Council Chamber', 'coordinates': '42.3371, -71.2093'}]
        for vpu in (True, False):
            out = gtt._build_closing_offer(poi_list, 'facility', 'walking',
                                           'Newton City Hall, Newton, MA',
                                           sentence_budget=3, venue_parts_used=vpu)
            assert isinstance(out, str), f"closing offer must be a string, got {out!r}"
        print("  ✅ Part 2 builds a closing offer for venue_parts_used in {True, False} "
              "— no NameError")


# ── 5. startup key-presence log line ─────────────────────────────────────────
class TestGeminiKeyPresenceLog:
    def test_generator_logs_key_presence(self):
        src = inspect.getsource(getattr(gtt, "_generate_tour_text_impl", gtt.generate_tour_text))
        assert '[LOCAL-767] GEMINI key present=' in src, (
            "the generator must log '[LOCAL-767] GEMINI key present=<bool>' at "
            "startup so a keyless run is visible at a glance.")
        line = next(l for l in src.splitlines()
                    if '[LOCAL-767] GEMINI key present=' in l)
        # Must be a bool expression, never a raw key value interpolated.
        assert 'GEMINI_API_KEY' not in line and 'GOOGLE_API_KEY' not in line, (
            "the key-presence line must not interpolate the key itself.")
        print("  ✅ generator logs GEMINI key presence as a bool, never the value")


def run_all():
    classes = [TestOutageStillRaises, TestCallerDegradesNotAborts,
               TestLiveServiceEmptyVenueDegrades, TestLocal275ClosingOfferParam,
               TestGeminiKeyPresenceLog]
    total = passed = failed = 0
    for cls in classes:
        print(f"\n{'=' * 64}\n  {cls.__name__}\n{'=' * 64}")
        inst = cls()
        for name in sorted(dir(inst)):
            if not name.startswith("test_"):
                continue
            total += 1
            try:
                getattr(inst, name)()
                passed += 1
            except AssertionError as e:
                failed += 1
                print(f"  ❌ {name}: {e}")
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"  ❌ {name}: EXCEPTION: {type(e).__name__}: {e}")
    print(f"\n{'=' * 64}\n  RESULTS: {passed}/{total} passed, {failed} failed\n{'=' * 64}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all())
