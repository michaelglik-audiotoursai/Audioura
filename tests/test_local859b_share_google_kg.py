#!/usr/bin/env python3
"""test_local859b_share_google_kg.py — LOCAL-859B.

Google now resolves share.google through a Knowledge-Graph SEARCH url, not a
``/maps/place`` url (GCloud_Storied_1 probed Michael's REAL links, orch
ef0cee57, 2026-11-03 20:3x). The live chain is:

  1. share.google/<id>                   -> 302 www.google.com/share.google?q=<id>
  2. www.google.com/share.google?q=<id>  -> 301 www.google.com/search?kgmid=<KG
       id>&q=<place name>&source=sh/x/(loc|kp)/…
  3. a JS-only search page (NO /maps/place, @lat,lng, !3d!4d, 0x…:0x… or ftid).

HEAD stops at hop 2, so the resolver must follow with GET. The canonical hop-2
target ``search?kgmid=…&q=…&source=…`` carries the place NAME in ``q`` and the
Knowledge-Graph id in ``kgmid`` — we read those and never fetch the JS page.

Michael's real links showed the two shapes this file proves, OFFLINE and
deterministically:

  * Thi Bar  → ``kgmid=/g/11c…`` with ``source=…/loc`` → a LOCAL PLACE. HIGH
    confidence: trust ``q`` (Google's place name, usually with address/city) and
    look it up with Serper /places.
  * Rambutan → ``kgmid=/m/0fs6v`` with ``source=…/kp`` → a Freebase TOPIC (the
    FRUIT, not the bar). LOW confidence: ignore ``q`` and use the stop NAME the
    listener typed, via the LOCAL-859 name-lookup fallback.

Also proven: the resolver NEVER logs the full share id (4-char truncation); a
HEAD-only resolver that stops at hop 2 yields no kgmid (so GET is required); and
no-network degrades to the typed-name path (never a crash, never the centroid).

Run:
    python3 -m pytest tests/test_local859b_share_google_kg.py -q
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import user_stop_input as u  # noqa: E402


# The two REAL shapes (ids truncated/obfuscated — a share id is public, we never
# hardcode Michael's real one).
_LOC_SEARCH = ("https://www.google.com/search?kgmid=/g/11c5qd9z"
               "&q=Thi+Bar+Saigon,+Ng%C3%B4+Th%E1%BB%9Di+Nhi%E1%BB%87m,"
               "+District+3&source=sh/x/loc/1/en")
_KP_SEARCH = ("https://www.google.com/search?kgmid=/m/0fs6v"
              "&q=Rambutan&source=sh/x/kp/1/en")


# ───────────────────── 1. KG search-url parsing ─────────────────────────────
class TestKgSearchUrlParse:
    def test_loc_shape_q_kgmid_source(self):
        q, kgmid, source = u.parse_kg_search_url(_LOC_SEARCH)
        assert kgmid == "/g/11c5qd9z"
        assert source.startswith("sh/x/loc")
        # q is the place name, URL-unquoted, with the address/district.
        assert q.startswith("Thi Bar Saigon")
        assert "District 3" in q

    def test_kp_shape_q_kgmid_source(self):
        q, kgmid, source = u.parse_kg_search_url(_KP_SEARCH)
        assert kgmid == "/m/0fs6v"
        assert source.startswith("sh/x/kp")
        # "Rambutan" alone is a bare one-word token; it is still returned as q
        # (the confidence gate — not the parser — decides to ignore it).
        assert q == "Rambutan"

    def test_hop1_share_google_q_is_not_a_search_url(self):
        # www.google.com/share.google?q=<id> is NOT the search url; no KG fields.
        assert u.parse_kg_search_url(
            "https://www.google.com/share.google?q=1v4xAbc9") == (None, None, None)

    def test_bare_id_q_rejected_but_kgmid_kept(self):
        # A ?q=<opaque id> on a search url is not a place name.
        q, kgmid, _s = u.parse_kg_search_url(
            "https://www.google.com/search?q=1v4xAbc9Z&kgmid=/g/1")
        assert q is None
        assert kgmid == "/g/1"

    def test_non_search_url_returns_none_triple(self):
        assert u.parse_kg_search_url(
            "https://www.google.com/maps/place/X/@1,2,17z") == (None, None, None)
        assert u.parse_kg_search_url("") == (None, None, None)


# ───────────────────── 2. confidence gate ───────────────────────────────────
class TestKgConfidence:
    def test_g_plus_loc_is_high(self):
        assert u.kg_confidence("/g/11c5qd9z", "sh/x/loc/1/en") == "high"

    def test_m_topic_is_low(self):
        assert u.kg_confidence("/m/0fs6v", "sh/x/kp/1/en") == "low"

    def test_kp_source_is_low_even_with_g_id(self):
        # A knowledge-panel source is a topic panel, not a local place.
        assert u.kg_confidence("/g/11c5qd9z", "sh/x/kp/1/en") == "low"

    def test_g_without_loc_source_is_low(self):
        # Conservative: a /g/ id with no loc source is not trusted over the name.
        assert u.kg_confidence("/g/11c5qd9z", "") == "low"

    def test_missing_everything_is_low(self):
        assert u.kg_confidence(None, None) == "low"


# ───────────────────── 3. mocked GET chain (both shapes) ─────────────────────
class _FakeResp:
    def __init__(self, url, text=""):
        self.url = url
        self.text = text


class _FakeCookies:
    def set(self, *a, **k):
        pass


class _KgSession:
    """A requests.Session stand-in replaying the LOCAL-859B chain. GET follows
    all redirects and lands on the canonical ``search?kgmid=…&q=…&source=…`` url
    (hop-2 target); the body is the JS-only page (no coordinate). A HEAD stops at
    hop 2 (``share.google?q=<id>``) with no kgmid — modelled by ``head``."""

    # share id -> final search url after following GET.
    PAGES = {
        "thibX1Y2Z3": _LOC_SEARCH,
        "rambQ9Z8": _KP_SEARCH,
    }
    _JS_BODY = "<!DOCTYPE html><html><body>loading…</body></html>"

    def __init__(self):
        self.headers = {}
        self.cookies = _FakeCookies()

    def _id(self, url):
        import re
        m = re.search(r"(?:share\.google/|[?&]q=)([^/?&#\s]+)", url)
        return m.group(1) if m else ""

    def get(self, url, timeout=None, allow_redirects=True):
        sid = self._id(url)
        if sid in self.PAGES:
            return _FakeResp(self.PAGES[sid], self._JS_BODY)
        # Fallback endpoints (maps?q=<id>, …): JS-only, no coordinate.
        return _FakeResp(url, "<html><body>no map</body></html>")

    def head(self, url, timeout=None, allow_redirects=True):
        # HEAD stops at hop 2 — the share.google?q=<id> page, no kgmid.
        sid = self._id(url)
        return _FakeResp(f"https://www.google.com/share.google?q={sid}")


def _install_fake_requests(monkeypatch, session_cls=_KgSession):
    fake = types.ModuleType("requests")
    fake.Session = session_cls
    monkeypatch.setitem(sys.modules, "requests", fake)


class TestResolveShareLinkKg:
    def test_loc_resolves_high_with_q(self, monkeypatch):
        _install_fake_requests(monkeypatch)
        logs = []
        out = u.resolve_share_link_kg("https://share.google/thibX1Y2Z3",
                                      log=logs.append)
        assert out is not None
        assert out["kgmid"] == "/g/11c5qd9z"
        assert out["confidence"] == "high"
        assert out["q"].startswith("Thi Bar Saigon")
        assert out["lat"] is None and out["lng"] is None  # no coord in KG flow
        assert any(l.startswith("[LOCAL-859B] share link") for l in logs)

    def test_kp_resolves_low(self, monkeypatch):
        _install_fake_requests(monkeypatch)
        out = u.resolve_share_link_kg("https://share.google/rambQ9Z8",
                                      log=lambda *_a: None)
        assert out["kgmid"] == "/m/0fs6v"
        assert out["confidence"] == "low"

    def test_full_share_id_is_never_logged(self, monkeypatch):
        _install_fake_requests(monkeypatch)
        logs = []
        full_id = "thibX1Y2Z3"
        u.resolve_share_link_kg(f"https://share.google/{full_id}",
                                log=logs.append)
        joined = "\n".join(logs)
        assert full_id not in joined            # never the whole id
        assert "thib…" in joined                # truncated to 4 chars

    def test_head_only_resolver_sees_no_kgmid(self, monkeypatch):
        # A resolver that only did HEAD would stop at share.google?q=<id>, which
        # is NOT a search url -> no kgmid. Proves GET is required.
        _install_fake_requests(monkeypatch)
        sess = _KgSession()
        head_final = sess.head("https://share.google/thibX1Y2Z3").url
        assert u.parse_kg_search_url(head_final) == (None, None, None)
        # Whereas following with GET lands on the search url with the kgmid.
        get_final = sess.get("https://share.google/thibX1Y2Z3").url
        _q, kgmid, _s = u.parse_kg_search_url(get_final)
        assert kgmid == "/g/11c5qd9z"

    def test_not_a_share_link_returns_none(self, monkeypatch):
        _install_fake_requests(monkeypatch)
        assert u.resolve_share_link_kg("https://an-spa.vn/en") is None


# ───────────────────── 4. parse_user_stop surfaces KG fields ────────────────
class TestParseUserStopKg:
    def test_loc_stop_high_confidence_q(self, monkeypatch):
        _install_fake_requests(monkeypatch)
        logs = []
        p = u.parse_user_stop("Thi Bar Saigon https___share.google_thibX1Y2Z3",
                              log=logs.append)
        # No coordinate from the KG flow -> still needs the confidence-gated
        # name lookup by the caller.
        assert p["needs_geocode"] is True
        assert p["lat"] is None
        assert p["kg_confidence"] == "high"
        assert p["kg_q"].startswith("Thi Bar Saigon")
        assert p["kgmid"] == "/g/11c5qd9z"
        assert p["how"] == "share_kg"
        assert any(l.startswith("[LOCAL-859B] share link") for l in logs)
        # The typed name is kept as the stop name (not overwritten by q).
        assert p["name"] == "Thi Bar Saigon"

    def test_kp_stop_low_confidence_discards_q_for_gating(self, monkeypatch):
        _install_fake_requests(monkeypatch)
        p = u.parse_user_stop("Rambutan https___share.google_rambQ9Z8",
                              log=lambda *_a: None)
        assert p["needs_geocode"] is True
        assert p["kg_confidence"] == "low"
        # q was parsed, but the LOW gate means the caller ignores it; the parser
        # still records it for the log/audit.
        assert p["kgmid"] == "/m/0fs6v"
        assert p["name"] == "Rambutan"

    def test_full_id_never_in_parse_user_stop_logs(self, monkeypatch):
        _install_fake_requests(monkeypatch)
        logs = []
        u.parse_user_stop("Thi Bar Saigon https___share.google_thibX1Y2Z3",
                          log=logs.append)
        assert "thibX1Y2Z3" not in "\n".join(logs)


# ───────────────────── 5. no-network degrades to typed name ─────────────────
class TestNoNetworkFallback:
    def test_broken_requests_degrades_no_kg_fields(self, monkeypatch):
        class _Boom:
            def __init__(self):
                raise RuntimeError("network down")
        _install_fake_requests(monkeypatch, session_cls=_Boom)
        p = u.parse_user_stop("Thi Bar Saigon https___share.google_thibX1Y2Z3",
                              log=lambda *_a: None)
        # Resolver returned None: no coord, no KG fields -> the caller uses the
        # typed NAME via name_lookup_in_bbox (never the centroid).
        assert p["needs_geocode"] is True
        assert p["lat"] is None
        assert p["kg_confidence"] is None
        assert p["kgmid"] is None

    def test_requests_absent_degrades(self, monkeypatch):
        # No requests module at all: default_resolver returns None.
        monkeypatch.setitem(sys.modules, "requests", None)
        assert u.default_resolver("https://share.google/thibX1Y2Z3") is None


# ───────────────────── 6. end-to-end confidence gate shape ───────────────────
class TestConfidenceGateIntegration:
    def test_high_uses_q_low_uses_typed_name(self, monkeypatch):
        """Mirrors the generate_tour_text wiring: HIGH stops feed ``kg_q`` to the
        name lookup, LOW stops feed the typed name. Here we assert the stop dict
        carries exactly the inputs that wiring keys on."""
        _install_fake_requests(monkeypatch)
        hi = u.parse_user_stop("Thi Bar Saigon https___share.google_thibX1Y2Z3",
                               log=lambda *_a: None)
        lo = u.parse_user_stop("Rambutan https___share.google_rambQ9Z8",
                               log=lambda *_a: None)
        # HIGH: the caller will look up kg_q (has address/district).
        assert hi["kg_confidence"] == "high" and hi["kg_q"]
        # LOW: the caller ignores kg_q and looks up the typed name.
        assert lo["kg_confidence"] == "low"
        assert lo["name"] == "Rambutan"
