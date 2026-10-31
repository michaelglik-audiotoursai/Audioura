"""tests/test_local849_serper_goto_links.py — LOCAL-849.

Since ~01:30 UTC on 2026-10-30, Serper returns the real URL only for the first 3
organic results; everything after comes back as an opaque
``https://www.google.com/goto?url=CAES…`` link (vendor: resolve via the free
/resolve endpoint; the CAES ``url=`` is NOT locally decodable). Left alone such a
link is fetched as the Google redirect, judged as host ``google.com`` by the
source-tier gate, and cited as ``google.com`` — all wrong.

What this suite proves (NO real network):
  1. is_goto_link / local_decode — detection, and that a plain ``url=https://…``
     is decoded locally while the opaque CAES ``url=`` is not.
  2. resolve_links on a REAL post-change fixture — top 3 kept untouched; the
     locally-decodable goto decoded with NO /resolve call; the opaque ones sent
     to a single batched /resolve (injected) and rewritten; news goto resolved.
  3. still-unresolved goto -> marked _unresolved_goto, is_resolved False,
     usable_link '' (UNKNOWN host: never judged, never fetched).
  4. fast path (need_beyond_top3=False) makes NO /resolve call and leaves the
     post-top-3 opaque links unresolved.
  5. the batched /resolve is called at most ONCE per search, and its result is
     cached by query (a second search reuses it with no call).
  6. DOMAIN GATE: venue_identity_gate.domain_of treats an unresolved goto link as
     unknown ('') — never google.com.
  7. PAGE FETCH skips an unresolved goto: the museum search chokepoint
     (work_story_searcher._serp_search) drops it, so gather_pages never fetches it
     and never cites google.com.
  8. METER: a /resolve call is priced $0 (0 credits) while /search stays $0.001.
"""
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "_meter"))

import serper_links as sl  # noqa: E402

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures",
                        "local849_serper_goto_search.json")


def _load():
    with open(_FIXTURE) as fh:
        return json.load(fh)


# ── 1. detection + local decode ──────────────────────────────────────────────

def test_is_goto_link():
    assert sl.is_goto_link("https://www.google.com/goto?url=CAESabc")
    assert sl.is_goto_link("https://google.com/goto?url=CAESabc")
    assert sl.is_goto_link("https://www.google.com/url?q=https://x.org/a")
    assert sl.is_goto_link("https://www.google.com/aclk?sa=L")
    assert not sl.is_goto_link("https://www.rijksmuseum.nl/en/collection/SK-C-5")
    assert not sl.is_goto_link("https://news.google.com/articles/abc")  # not /goto
    assert not sl.is_goto_link("")
    assert not sl.is_goto_link(None)


def test_local_decode_plain_target_decodable():
    # Plain url= / q= target -> decoded locally, no network.
    assert sl.local_decode(
        "https://www.google.com/url?q=https%3A%2F%2Fmfa.org%2Fx") == "https://mfa.org/x"
    assert sl.local_decode(
        "https://www.google.com/goto?url=https%3A%2F%2Fa.org%2Fb") == "https://a.org/b"


def test_local_decode_opaque_caes_not_decodable():
    # The opaque CAES reference is NOT a URL -> cannot decode locally.
    assert sl.local_decode("https://www.google.com/goto?url=CAESxQFBVTEx") == ""
    assert sl.local_decode("https://www.rijksmuseum.nl/en") == ""
    assert sl.local_decode("") == ""


# ── 2+3. resolve_links on the real post-change fixture ────────────────────────

def test_resolve_links_full(monkeypatch):
    body = _load()
    calls = {"n": 0, "urls": None}

    def fake_resolve(search_json, goto_urls, timeout):
        # ONE batched call for every still-unresolved (opaque) goto link. The
        # fixture's CAES blobs carry a distinguishing token we key on.
        calls["n"] += 1
        calls["urls"] = list(goto_urls)
        mp = {}
        for g in goto_urls:
            if "Q29uZXdzX255" in g:          # the news CAES blob
                mp[g] = "https://www.anp.nl/night-watch"
            elif "UWVZ3" in g:                # the Smithsonian CAES blob
                mp[g] = "https://www.smithsonianmag.com/nightwatch"
            else:                             # the Guardian CAES blob
                mp[g] = "https://www.theguardian.com/nw"
        return mp

    out = sl.resolve_links(body, query="\"The Night Watch\" Rembrandt",
                           need_beyond_top3=True, _resolver=fake_resolve)
    org = out["organic"]

    # Top 3 untouched.
    assert org[0]["link"] == "https://www.rijksmuseum.nl/en/collection/SK-C-5"
    assert org[1]["link"] == "https://en.wikipedia.org/wiki/The_Night_Watch"
    assert org[2]["link"] == "https://www.britannica.com/topic/The-Night-Watch"
    assert all(not r.get("_resolved_from_goto") for r in org[:3])

    # Ranks 4 & 5: opaque CAES -> resolved via the batched /resolve.
    assert org[3]["link"] == "https://www.smithsonianmag.com/nightwatch"
    assert org[4]["link"] == "https://www.theguardian.com/nw"
    assert org[3]["_resolved_from_goto"] and org[4]["_resolved_from_goto"]

    # Rank 6: plain url= target -> decoded LOCALLY (not in the /resolve batch).
    assert org[5]["link"] == "https://www.dutchmasters.example/night-watch"
    assert org[5]["_resolved_from_goto"]
    assert "goto?url=https" not in json.dumps(org[5])

    # News goto resolved.
    assert out["news"][0]["link"] == "https://www.anp.nl/night-watch"

    # Exactly ONE batched /resolve, and the locally-decoded rank-6 was NOT in it.
    assert calls["n"] == 1
    assert all("url?q=https" not in u for u in calls["urls"])
    # It carried the two opaque CAES links + the opaque news link = 3.
    assert len(calls["urls"]) == 3

    stats = sl.resolve_stats(out)
    assert stats["resolved"] == 4   # 2 opaque organic + 1 local organic + 1 news
    assert stats["unresolved"] == 0


def test_resolve_links_unresolved_is_unknown(monkeypatch):
    body = _load()

    def resolve_nothing(search_json, goto_urls, timeout):
        return {}  # /resolve down / returns nothing

    out = sl.resolve_links(body, query="q", need_beyond_top3=True,
                           _resolver=resolve_nothing)
    org = out["organic"]
    # Rank 6 (plain url=) still decoded locally even when /resolve returns nothing.
    assert org[5]["link"] == "https://www.dutchmasters.example/night-watch"
    # Ranks 4 & 5 (opaque) stay unresolved = unknown host.
    assert org[3].get("_unresolved_goto") is True
    assert org[4].get("_unresolved_goto") is True
    assert sl.is_resolved(org[3]) is False
    assert sl.usable_link(org[3]) == ""
    # The top 3 and the locally-decoded one are usable.
    assert sl.usable_link(org[0]) == "https://www.rijksmuseum.nl/en/collection/SK-C-5"
    assert sl.usable_link(org[5]) == "https://www.dutchmasters.example/night-watch"
    # News goto unresolved -> unknown.
    assert out["news"][0].get("_unresolved_goto") is True
    assert sl.usable_link(out["news"][0]) == ""


# ── 4. fast path: no /resolve call for top-3-only callers ─────────────────────

def test_fast_path_makes_no_resolve_call():
    body = _load()

    def must_not_call(search_json, goto_urls, timeout):
        raise AssertionError("fast path must not call /resolve")

    out = sl.resolve_links(body, query="q", need_beyond_top3=False,
                           _resolver=must_not_call)
    org = out["organic"]
    # Top 3 fine; the plain url= still decodes for free; opaque ranks unresolved.
    assert sl.usable_link(org[0])
    assert org[5]["link"] == "https://www.dutchmasters.example/night-watch"
    assert org[3].get("_unresolved_goto") is True
    assert org[4].get("_unresolved_goto") is True


# ── 5. at most ONE /resolve per search, cached by query ───────────────────────

def test_resolve_called_once_and_cached():
    sl._resolve_cache.clear()
    body = _load()
    n = {"calls": 0}

    def fake_resolve(search_json, goto_urls, timeout):
        n["calls"] += 1
        return {g: "https://real.example/%d" % i for i, g in enumerate(goto_urls)}

    q = "cache-query"
    out1 = sl.resolve_links(body, query=q, need_beyond_top3=True,
                            _resolver=fake_resolve)
    assert n["calls"] == 1
    assert out1["organic"][3]["link"].startswith("https://real.example/")

    # Second identical search: served from cache, NO new /resolve call.
    def boom(search_json, goto_urls, timeout):
        raise AssertionError("should be served from cache")

    out2 = sl.resolve_links(_load(), query=q, need_beyond_top3=True, _resolver=boom)
    assert n["calls"] == 1
    assert out2["organic"][3]["link"].startswith("https://real.example/")


def test_no_goto_means_no_call():
    clean = {"organic": [{"title": "a", "link": "https://a.org/1"},
                         {"title": "b", "link": "https://b.org/2"}]}

    def must_not_call(search_json, goto_urls, timeout):
        raise AssertionError("no goto links -> no /resolve call")

    out = sl.resolve_links(clean, query="q", _resolver=must_not_call)
    assert out["organic"][0]["link"] == "https://a.org/1"


def test_fail_open_on_resolver_exception():
    body = _load()

    def boom(search_json, goto_urls, timeout):
        raise RuntimeError("resolve blew up")

    # Must not raise; opaque goto links left unresolved (unknown), never crash.
    out = sl.resolve_links(body, query="q", need_beyond_top3=True, _resolver=boom)
    assert out["organic"][3].get("_unresolved_goto") is True
    assert sl.usable_link(out["organic"][3]) == ""


# ── 6. the 828 domain gate treats an unresolved goto as unknown ───────────────

def test_domain_gate_unresolved_goto_is_unknown():
    from venue_identity_gate import domain_of
    goto = "https://www.google.com/goto?url=CAESxQFBVTEx"
    assert domain_of(goto) == "", "an opaque goto link must be UNKNOWN, not google.com"
    # A plain url= target the gate CAN read resolves to the real host.
    assert domain_of("https://www.google.com/url?q=https://mfa.org/x") == "mfa.org"
    # A real link is unchanged.
    assert domain_of("https://www.rijksmuseum.nl/en") == "rijksmuseum.nl"


# ── 7. page fetch skips an unresolved goto (museum chokepoint) ────────────────

def test_serp_search_drops_unresolved_goto(monkeypatch):
    """work_story_searcher._serp_search resolves goto links and DROPS any that
    stay unresolved, so gather_pages never fetches the Google redirect and never
    cites google.com. We stub the metered door to return the fixture and stub
    /resolve to recover nothing (worst case)."""
    import work_story_searcher as wss

    monkeypatch.setattr(wss, "SERP_API_KEY", "k")
    body_bytes = json.dumps(_load()).encode()

    import serper_meter
    monkeypatch.setattr(serper_meter, "serper_post",
                        lambda *a, **k: (200, body_bytes))
    # /resolve recovers nothing -> opaque goto links stay unresolved.
    monkeypatch.setattr(sl, "_call_resolve", lambda sj, urls, to: {})

    results, _latency = wss._serp_search("\"The Night Watch\" Rembrandt")
    urls = [r["url"] for r in results]
    # No google.com/goto link survives to be fetched or judged.
    assert all("google.com/goto" not in u for u in urls)
    assert all(not sl.is_goto_link(u) for u in urls)
    # The top 3 real links AND the locally-decoded rank-6 survive.
    assert "https://www.rijksmuseum.nl/en/collection/SK-C-5" in urls
    assert "https://www.dutchmasters.example/night-watch" in urls
    # The two opaque CAES links were dropped (unknown host, never fetched).
    assert len(results) == 4


# ── 8. meter: /resolve is $0, /search is $0.001 ───────────────────────────────

def test_meter_prices_resolve_at_zero(monkeypatch, tmp_path):
    import paid_api_meter as m
    log = tmp_path / "paid_api_calls.jsonl"
    monkeypatch.setattr(m, "LOG", str(log))
    monkeypatch.setattr(m, "_db_write", lambda rec: None)

    m.record_call("https://google.serper.dev/resolve", 200, b"{}", {"links": ["x"]})
    m.record_call("https://google.serper.dev/search", 200, b'{"organic":[]}', {"q": "x"})

    rows = [json.loads(l) for l in open(log) if l.strip()]
    by_url = {r["url"].split("/")[-1]: r for r in rows}
    assert by_url["resolve"]["kind"] == "serper"
    assert by_url["resolve"]["usd"] == 0.0, "/resolve is free (0 credits)"
    assert by_url["search"]["usd"] == 0.001


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
