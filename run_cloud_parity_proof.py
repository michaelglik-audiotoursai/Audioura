#!/usr/bin/env python3
"""run_cloud_parity_proof.py — LOCAL-882: the standard CLOUD-PARITY proof harness.

Earlier local proofs PASSED and then the SAME request FAILED on the cloud, four
waves running. LEAD found three reasons the local proof did not predict the cloud,
and this harness removes all three so a local PASS now means a cloud PASS:

  1. SHORT user names, through the quick path. The cloud gets the stops as the
     listener typed them ("Cathedral", "City Hall", "Opera House", …) and resolves
     them through the orchestrator quick path (D762 /preview-stops → a pin + a
     canonical name per stop). The old harnesses fed the already-resolved FULL
     names, so a bare "City Hall" / "Opera House" was never searched. This harness
     feeds the SHORT names and runs them through itinerary_import.preview_stops +
     stops_for_generation — the exact path the orchestrator uses — pinned to the
     SAME coordinates as the cloud (the wave-40 Coordinates lines).

  2. A WARM cache. landmark_wikipedia_evidence.fetch_article returns a cache HIT
     for the stop's article; an article cached by an OLDER rule (the Gia Long
     Palace for the City Hall pin, cached waves 36-39) was served without
     re-running the current gate. The old harnesses always started from an EMPTY
     disposable DB, so they never saw this. This harness runs TWICE on the SAME
     DB: a COLD run, then a WARM run, AFTER first SEEDING the cache by running the
     PREVIOUS subscribed commit (a31ead22's generator) once — so the cache holds
     old-rule entries exactly as the cloud did. The PASS check runs on the WARM
     run.

  3. The quick-path / user-stops code path, end to end, so a defect that only the
     user-stops flow emits (the current-affairs note) is reproduced.

USAGE
    # offline wiring self-check (no network, no spend) — proves the harness builds
    # the quick-path payload and the PASS checks run:
    python3 run_cloud_parity_proof.py --selfcheck

    # LIVE, budget-enforced (own DB on :55982; seed with a31ead22; cold; warm):
    #   docker compose -p local882 -f docker-compose.local882-proof.yml up -d
    #   TASK_BUDGET_ID=LOCAL-882 TASK_BUDGET_USD=0.60 \
    #   PAID_API_LOG=$PWD/_local882_meterlogs/paid_api_calls.jsonl \
    #   AUDIOURA_TASK_BUDGET_DIR=$PWD/_local882_meterlogs METER_MOUNT_GUARD=0 \
    #   METER_SERVICE=LOCAL-882 PYTHONPATH=$PWD/_meter \
    #   python3 run_cloud_parity_proof.py --run
    #
    # phases can be run one at a time too: --seed | --cold | --warm

The cold & warm tour texts are written to submission_artifacts/local882/ (committed).
Run logs go to ./_local882_meterlogs/ (never committed).
"""
import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "tests"))
sys.path.insert(0, os.path.join(_HERE, "_meter"))

BASE_COMMIT = "a31ead22"

# ── Michael's EXACT request: SHORT names + the wave-40 Coordinates pins ──────
REQUEST = "Saigon centre landmarks, Ho Chi Minh City, Vietnam"
CITY = "Ho Chi Minh City"
LOCATION = "Ho Chi Minh City, Vietnam"
# (short name as typed, lat, lng) — the Coordinates lines from the wave-40 text.
SHORT_STOPS = [
    ("Cathedral",            10.779722, 106.699167),
    ("Post Office",          10.780000, 106.700000),
    ("Book Street",          10.780573, 106.699695),
    ("Independence Palace",  10.777050, 106.695370),
    ("War Remnants Museum",  10.779500, 106.692000),
    ("Opera House",          10.776390, 106.702780),
    ("City Hall",            10.776470, 106.700970),
    ("Café Apartments 42",   10.774089, 106.704056),
    ("Bạch Đằng Pier",       10.775240, 106.707002),
    ("Thi Bar",              10.767660, 106.693960),
]


def _load_dotenv():
    try:
        with open(os.path.join(_HERE, ".env"), "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


# ── environment: own DB (:55982), live research, cheap mini arm ──────────────
_OWN_DB = os.environ.get(
    "LOCAL882_DB_URL", "postgresql://admin:password123@localhost:55982/audiotours")


def _apply_live_env():
    _load_dotenv()
    for _k, _v in (("DATABASE_URL", _OWN_DB), ("VENUE_CACHE_DB_URL", _OWN_DB),
                   ("DB_HOST", "localhost"), ("DB_PORT", "55982"),
                   ("DB_NAME", "audiotours"), ("DB_USER", "admin"),
                   ("DB_PASSWORD", "password123")):
        os.environ[_k] = _v
    os.environ.pop("K_SERVICE", None)
    os.environ["LANDMARK_LIVE_LOOKUP"] = "1"
    os.environ["CHEAP_ARM_CATEGORIES"] = "museum,walking,restaurant,facility,specialized"
    os.environ["NARRATION_MODEL"] = "gpt-4.1-mini"
    os.environ["SIGNATURE_STORY_ENABLED"] = "1"
    os.environ["SIGNATURE_STORY_MODEL"] = "gpt-4.1-mini"
    os.environ["RESEARCH_BACKEND"] = "serper"
    os.environ.setdefault("SERP_PROVIDER", "serper")
    os.environ.setdefault("STORIED_MODE", "true")
    os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")
    os.environ["USER_STOPS_ENABLED"] = "true"
    os.environ.setdefault("STORY_PASS_MODEL", "gpt-4.1-mini")
    os.environ.setdefault("TOUR_STORY_MODEL", "gpt-4o-mini")
    os.environ.setdefault("TOUR_SCOPE_COMPARE_MODEL", "gpt-4o-mini")
    # WARM cache parity: the wiki/evidence caches MUST persist across seed → cold →
    # warm (that is the whole point). The tour-text cache and stop pool are
    # disabled so each run re-generates text (we are proving the EVIDENCE cache
    # re-validation, not the text cache).
    os.environ["DISABLE_TOUR_CACHE"] = "1"
    os.environ["DISABLE_STOP_POOL"] = "1"


_METER_DIR = os.path.join(_HERE, "_local882_meterlogs")
_ART_DIR = os.path.join(_HERE, "submission_artifacts", "local882")

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_FIELD_RE = re.compile(
    r"(?i)^(Coordinates|Type/Specialty|Specific Examples|Directions|Address|"
    r"Museum Information|Operational Details|Sources|Orientation):")


class _Tee:
    def __init__(self, *s):
        self._s = s

    def write(self, d):
        for s in self._s:
            s.write(d)
        return len(d)

    def flush(self):
        for s in self._s:
            try:
                s.flush()
            except Exception:
                pass


def _meter_total():
    log = os.environ.get("PAID_API_LOG") or os.path.join(_METER_DIR, "paid_api_calls.jsonl")
    total = 0.0
    try:
        with open(log, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    total += float(row.get("usd", row.get("cost_usd", row.get("cost", 0))) or 0)
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return total


# ── the quick-path payload: SHORT names → preview_stops → forced_stops ───────
def build_forced_stops(log=lambda *a, **k: None):
    """Replicate the orchestrator quick path: resolve the SHORT typed names through
    itinerary_import.preview_stops (pin + canonical per stop), pin each to the EXACT
    wave-40 coordinate (so the geometry matches the cloud), then stops_for_generation
    turns them into the user-stops strings (a maps '/place/<canonical>/@lat,lng' link
    the LOCAL-852/859 parser reads as a user pin). Returns (forced_strings, preview)."""
    import itinerary_import as ii
    # One stop per line, as the listener's pasted itinerary.
    pasted = "\n".join(name for name, _, _ in SHORT_STOPS)
    preview = ii.preview_stops(pasted, CITY, log=log)
    if not preview.get("ok"):
        raise RuntimeError(f"preview failed: {preview.get('error')}")
    stops = preview["stops"]
    if len(stops) != len(SHORT_STOPS):
        raise RuntimeError(f"preview parsed {len(stops)} of {len(SHORT_STOPS)} stops")
    # Pin each resolved stop to the EXACT wave-40 coordinate (cloud parity) while
    # keeping the SHORT typed name as the spoken title and the runtime canonical as
    # the research match_name.
    for st, (name, lat, lng) in zip(stops, SHORT_STOPS):
        st["name"] = st["stop_name"] = name          # the user's short spoken title
        st["lat"], st["lng"] = lat, lng              # the cloud's pin
    forced, pins = ii.stops_for_generation(stops)
    log(f"[parity] built {len(forced)} forced stops, {pins} carrying a pin")
    return forced, preview


# ── generation ───────────────────────────────────────────────────────────────
def _generate(forced, cap_usd, tag):
    """Run the generator in-process with the live meter, writing the log to the
    meter dir and returning (text, log_text)."""
    os.makedirs(_METER_DIR, exist_ok=True)
    before = _meter_total()
    try:
        from live_run_meter import LiveRunMeter
        os.environ["TEST_GEMINI_MAX_USD"] = f"{max(0.0, cap_usd - before):.4f}"
        _lrm = LiveRunMeter(os.environ.get("TASK_BUDGET_ID") or "LOCAL-882",
                            cap_usd=cap_usd - before)
    except Exception:
        _lrm = None
    import generate_tour_text as g
    buf = io.StringIO()
    text = ""
    try:
        with contextlib.redirect_stdout(_Tee(sys.stdout, buf)):
            text, _o, _c = g.generate_tour_text(
                REQUEST, "walking", None, len(forced), forced_stops=list(forced))
    except Exception as e:
        import traceback
        print(f"  generate raised: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
    if _lrm is not None:
        try:
            _lrm.uninstall()
        except Exception:
            pass
    log = buf.getvalue()
    open(os.path.join(_METER_DIR, f"{tag}_log.txt"), "w", encoding="utf-8").write(log)
    return text, log


# ── PASS checks (the wave-40 criteria + the D strings) ───────────────────────
def _blocks(text):
    titles = _STOP_HEADER_RE.findall(text or "")
    bodies = re.split(r"(?mi)^Stop\s+\d+:\s*.+$", text or "")
    return [(int(n), t.strip(), b) for (n, t), b in zip(titles, bodies[1:])]


def _prose(block):
    out = []
    for ln in block[2].split("\n"):
        s = ln.strip()
        if not s:
            continue
        m = re.match(r"(?i)^orientation:\s*(.*)$", s)
        if m:
            if m.group(1).strip():
                out.append(m.group(1).strip())
            continue
        if _FIELD_RE.match(s):
            continue
        out.append(s)
    return " ".join(out)


def _content_sentences(prose):
    try:
        from sentence_split import split_sentences
        sents = split_sentences(prose)
    except Exception:
        sents = re.findall(r"[^.!?]*[.!?]", prose)
    return [s for s in sents if len(s.strip()) >= 15]


def _check(label, ok, detail=""):
    print(f"   [{'PASS' if ok else 'FAIL'}] {label}" + (f": {detail}" if detail else ""),
          flush=True)
    return bool(ok)


# The exact banned strings from the wave-40 report (task D). Folded compare for
# the Vietnamese ones so accents do not matter.
_BANNED = [
    "note on current affairs",
    "no verified developments",
    "museum of commercial trade",
    "gia long",
    "assassinated inside the palace",
    "established in the early 19th century",
    "rising to, and",
    "capacity to seat guests",
    "completed 14 years later",
    "each was picked by you",
    "sydney",
]


def evaluate(text, log, require_ten=True):
    checks = _criteria(text, log, require_ten=require_ten)
    ok = all(v for _, v in checks)
    return bool(ok)


# [LOCAL-888] A sentence that credits Eiffel only to NEGATE it. The old pattern
# needed "not" BEFORE design/build, so "designed not by Eiffel but by Alfred
# Foulhoux" (the correct statement) was reported as crediting Eiffel.
_EIFFEL_CORRECTION_RE = (
    r"mistaken|wrongly|myth|legend|rumou?r|misattribut\w*|"
    r"not .*(design|build)|"
    r"not\s+(?:by|the\s+work\s+of|from|designed\s+by|built\s+by)\s+(?:\w+\s+)?eiffel|"
    r"eiffel[^.]{0,40}\b(?:did\s+not|didn't|never|was\s+not|wasn't)\b|"
    r"\b(?:rather\s+than|instead\s+of|and\s+not|but\s+by|but\s+rather)\b|"
    r"often (?:attribut|credit)|contrary|attributed to|actually|popular(?:ly)?\s+(?:belief|believed)")


def _criteria(text, log, require_ten=True):
    """Return [(label, passed), ...] for every PASS criterion. ``require_ten``
    toggles the 10-stop count check (off for trimmed selfcheck samples)."""
    blocks = _blocks(text)
    low = (text or "").lower()
    results = []

    def _add(label, ok, detail=""):
        results.append((label, _check(label, ok, detail)))

    if require_ten:
        _add("10/10 stops delivered", len(blocks) == 10, len(blocks))

    short = [(n, t, len(_content_sentences(_prose((n, t, b)))))
             for n, t, b in blocks if len(_content_sentences(_prose((n, t, b)))) < 5]
    _add("every stop ≥ 5 content sentences", not short,
         "all ≥5" if not short else f"short: {short}")

    present = [s for s in _BANNED if s in low]
    _add("no banned wave-40 strings", not present, present or "absent")

    pal = next((b for b in blocks if "palace" in b[1].lower()), None)
    if pal:
        pl = _prose(pal)
        pll = pl.lower()
        _add("Palace states 30 April 1975 tank event",
             ("1975" in pll and ("30 april" in pll or "april 30" in pll))
             and ("tank" in pll or "gate" in pll or "stormed" in pll
                  or "crashed" in pll or "surrender" in pll),
             pl[:160])
        import unicodedata
        folded = "".join(c for c in unicodedata.normalize("NFKD", pl)
                         if not unicodedata.combining(c)).lower()
        bad_diem = re.search(r"(?<!ngo )dinh diem", folded)
        _add("Diệm named in full (Ngô Đình Diệm), no bare Đình Diệm",
             not bad_diem, "ok" if not bad_diem else
             folded[max(0, bad_diem.start() - 20):bad_diem.end() + 5])

    ch = next((b for b in blocks if "city hall" in b[1].lower()
               or "people's committee" in b[1].lower()), None)
    if ch:
        chl = _prose(ch).lower()
        _add("City Hall is the Hôtel de Ville (1898-1909), not Gia Long Palace",
             ("1898" in chl or "1908" in chl or "1909" in chl or "ville" in chl)
             and "gia long" not in chl and "commercial trade" not in chl,
             _prose(ch)[:160])

    po = next((b for b in blocks if "post office" in b[1].lower()), None)
    if po:
        pol = _prose(po).lower()
        # PASS criterion 3: Eiffel may appear ONLY as a myth correction OR as the
        # architect of an EARLIER / former structure on the site. FAIL only when an
        # Eiffel sentence credits design/build and is NOT qualified as a correction
        # or as an earlier/former building (i.e. it ties Eiffel to the CURRENT one).
        _eiffel_bad = False
        for _s in re.split(r"(?<=[.!?])\s+", _prose(po)):
            _sl = _s.lower()
            if "eiffel" not in _sl:
                continue
            if not re.search(r"design|built|architect|engineer", _sl):
                continue
            _corrected = bool(re.search(_EIFFEL_CORRECTION_RE, _sl))
            _earlier = bool(re.search(
                r"earlier|former|previous|original|replaced|preceding|stood before|"
                r"18[56]\d", _sl))
            if not (_corrected or _earlier):
                _eiffel_bad = True
                break
        _add("Post Office credited Foulhoux/Vildieu, Eiffel only as myth/earlier building",
             ("foulhoux" in pol or "vildieu" in pol) and not _eiffel_bad,
             _prose(po)[:160])

    op = next((b for b in blocks if "opera" in b[1].lower()), None)
    if op:
        opl = _prose(op).lower()
        ferret_alone = "ferret" in opl and "olivier" not in opl and "guichard" not in opl
        _add("Opera House does not credit Ferret alone", not ferret_alone, _prose(op)[:160])

    s1 = next((b for b in blocks if b[0] == 1), None)
    if s1:
        # Directions may sit on the same line as the label OR on the following
        # line(s); capture the content either way (not just same-line).
        dirs = ""
        lines = s1[2].split("\n")
        for i, ln in enumerate(lines):
            m = re.match(r"(?i)^directions:\s*(.*)$", ln.strip())
            if m:
                dirs = m.group(1).strip()
                if not dirs:
                    for nxt in lines[i + 1:]:
                        if nxt.strip():
                            dirs = nxt.strip()
                            break
                break
        bare = dirs.lower() in ("enjoy the stroll!", "enjoy the stroll",
                                "enjoy the walk!", "")
        _add("Stop 1 Directions is a real next-stop direction, not just 'Enjoy the stroll!'",
             not bare, dirs[:80] or "(empty)")

    return results


# ── seed with the PREVIOUS subscribed commit (a31ead22) ──────────────────────
def seed_with_base(cap_usd):
    """Run a31ead22's generator ONCE against the same DB so the cache holds
    old-rule entries, exactly as the cloud did before this branch. Done in a
    throwaway git worktree of a31ead22, in a SUBPROCESS, so it measures the base
    code (D358: never origin; a31ead22 is this branch's base)."""
    wt = tempfile.mkdtemp(prefix="local882_base_")
    print(f"[seed] creating a31ead22 worktree at {wt}", flush=True)
    subprocess.run(["git", "worktree", "add", "--detach", wt, BASE_COMMIT],
                   cwd=_HERE, check=True)
    try:
        # a tiny driver that runs INSIDE the base worktree: builds the same quick
        # -path forced stops (base itinerary_import, no canonical step) and runs
        # the base generator once, pointed at the SAME DB. Its only job is to WRITE
        # the cache; its output text is kept for the record but not PASS-checked.
        driver = os.path.join(wt, "_local882_seed_driver.py")
        with open(driver, "w", encoding="utf-8") as f:
            f.write(_SEED_DRIVER_SRC)
        env = dict(os.environ)
        env["PAID_API_LOG"] = os.environ.get(
            "PAID_API_LOG", os.path.join(_METER_DIR, "paid_api_calls.jsonl"))
        env["LOCAL882_SEED_CAP_USD"] = f"{cap_usd:.4f}"
        env["LOCAL882_ART_DIR"] = _ART_DIR
        env["PYTHONPATH"] = os.path.join(_HERE, "_meter") + os.pathsep + wt
        r = subprocess.run([sys.executable, driver], cwd=wt, env=env)
        print(f"[seed] base generator exit {r.returncode}", flush=True)
        return r.returncode == 0
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", wt], cwd=_HERE)


# The seed driver source, written into the base worktree and run there. It imports
# the BASE modules (that worktree's generate_tour_text / itinerary_import), so the
# cache rows it writes are genuine old-rule entries.
_SEED_DRIVER_SRC = '''
import io, json, os, sys, contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
REQUEST = "Saigon centre landmarks, Ho Chi Minh City, Vietnam"
CITY = "Ho Chi Minh City"
STOPS = [
    ("Cathedral", 10.779722, 106.699167), ("Post Office", 10.780000, 106.700000),
    ("Book Street", 10.780573, 106.699695), ("Independence Palace", 10.777050, 106.695370),
    ("War Remnants Museum", 10.779500, 106.692000), ("Opera House", 10.776390, 106.702780),
    ("City Hall", 10.776470, 106.700970), ("Café Apartments 42", 10.774089, 106.704056),
    ("Bạch Đằng Pier", 10.775240, 106.707002), ("Thi Bar", 10.767660, 106.693960),
]
import itinerary_import as ii
pasted = "\\n".join(n for n, _, _ in STOPS)
pv = ii.preview_stops(pasted, CITY, log=lambda *a, **k: None)
stops = pv.get("stops") or []
for st, (name, lat, lng) in zip(stops, STOPS):
    st["name"] = st["stop_name"] = name
    st["lat"], st["lng"] = lat, lng
forced, _ = ii.stops_for_generation(stops)
cap = float(os.environ.get("LOCAL882_SEED_CAP_USD", "0.20"))
try:
    from live_run_meter import LiveRunMeter
    os.environ["TEST_GEMINI_MAX_USD"] = f"{cap:.4f}"
    lrm = LiveRunMeter("LOCAL-882", cap_usd=cap)
except Exception:
    lrm = None
import generate_tour_text as g
buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        text, _o, _c = g.generate_tour_text(REQUEST, "walking", None, len(forced), forced_stops=list(forced))
except Exception as e:
    import traceback; traceback.print_exc(); text = ""
art = os.environ.get("LOCAL882_ART_DIR", ".")
os.makedirs(art, exist_ok=True)
open(os.path.join(art, "saigon_seed_base.txt"), "w", encoding="utf-8").write(text or "")
print("[seed-driver] base tour written,", len(text or ""), "chars")
'''


def phase(tag, cap_usd):
    print(f"\n[{tag.upper()}] request={REQUEST!r}", flush=True)
    forced, preview = build_forced_stops(log=print)
    print("[parity] canonical names resolved per stop:", flush=True)
    for s in preview["stops"]:
        print(f"    {s['name']!r:28} -> match_name={s.get('matched_name')!r} "
              f"@{s.get('lat')},{s.get('lng')} ({s.get('source')})", flush=True)
    text, log = _generate(forced, cap_usd, tag)
    open(os.path.join(_ART_DIR, f"saigon_{tag}.txt"), "w", encoding="utf-8").write(text or "")
    return text, log


# ── LOCAL-886: load the CLOUD cache snapshot, run ONLY the warm phase ─────────
SNAPSHOT_GLOB = "cloud_*_cache_*.csv.gz"
_SNAP_TAG = os.environ.get("LOCAL_SNAPSHOT_TAG", "887")      # [LOCAL-887] task number
_SNAP_PORT = os.environ.get("LOCAL886_DB_PORT", f"559{_SNAP_TAG[-2:]}")
_SNAP_DB = os.environ.get(
    "LOCAL886_DB_URL", f"postgresql://admin:password123@localhost:{_SNAP_PORT}/audiotours")
_SNAP_BUDGET_ID = f"LOCAL-{_SNAP_TAG}"


def _ensure_snapshot_tables(conn, log=print):
    """Create each cache table with the GENERATOR'S OWN schema (its own lazy
    CREATE TABLE IF NOT EXISTS) when it is missing. domain_tier_cache has no SQL
    schema in the generator (it is a JSON file cache), so it gets a plain table
    matching the snapshot header."""
    import importlib
    makers = [
        ("landmark_wikipedia_evidence", "_ensure"),
        ("wikidata_landmark_lookup", "_ensure_cache_table"),
        ("local_language", "_ensure_cache"),
        ("thin_verify_cache", "_ensure_table"),
        ("venue_preflight", "_ensure_cache_table"),
        ("venue_resolver", "_ensure_venue_works_table"),
        ("work_story_research", "_ensure_cache_table"),
    ]
    for mod, fn in makers:
        try:
            m = importlib.import_module(mod)
            for flag in ("_TABLE_OK", "_CACHE_TABLE_ENSURED", "_CACHE_TABLE_OK",
                         "_VENUE_WORKS_TABLE_ENSURED"):
                if hasattr(m, flag):
                    setattr(m, flag, False)      # force the CREATE on this fresh DB
            getattr(m, fn)(conn)
            conn.commit()
        except Exception as e:
            conn.rollback()
            log(f"  [snapshot] {mod}.{fn} failed: {type(e).__name__}: {str(e)[:160]}")
    with conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS domain_tier_cache (
            domain TEXT PRIMARY KEY, tier TEXT, checked_at TIMESTAMP,
            expires_at TIMESTAMP)""")
    conn.commit()


def _snap_table_name(path):
    m = re.match(r"cloud_(.+)_cache_\d+\.csv\.gz$", os.path.basename(path))
    return f"{m.group(1)}_cache" if m else None


def load_snapshot(snap_dir, db_url, log=print):
    """Load every cloud_*_cache_*.csv.gz in snap_dir into the matching table of the
    DISPOSABLE proof DB at db_url. Prints the row count per table before and after.
    No DELETE/TRUNCATE: rows go through a temp staging table and INSERT ... ON
    CONFLICT DO NOTHING. Refuses any DB that is not a local own-port DB.
    Returns {table: (before, after)}."""
    import csv
    import glob
    import gzip
    import io
    import psycopg2
    from urllib.parse import urlparse
    u = urlparse(db_url)
    if u.hostname not in ("localhost", "127.0.0.1") or u.port in (None, 5432, 5433):
        raise RuntimeError(f"refusing to load a snapshot into {u.hostname}:{u.port} "
                           f"(not a disposable own-port proof DB)")
    csv.field_size_limit(10 ** 9)
    files = sorted(glob.glob(os.path.join(os.path.expanduser(snap_dir), SNAPSHOT_GLOB)))
    if not files:
        raise RuntimeError(f"no {SNAPSHOT_GLOB} in {snap_dir}")
    conn = psycopg2.connect(db_url)
    result = {}
    try:
        _ensure_snapshot_tables(conn, log)
        for path in files:
            table = _snap_table_name(path)
            if not table:
                continue
            with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
                text = fh.read()
            cols = next(csv.reader([text.split("\n", 1)[0]]))
            if table == "work_story_research_cache" and "id" in cols:
                # SERIAL id: let the DB assign it (a copied id would not advance the sequence)
                keep = [c for c in cols if c != "id"]
            else:
                keep = cols
            col_list = ", ".join(f'"{c}"' for c in keep)
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                before = cur.fetchone()[0]
                cur.execute(f"CREATE TEMP TABLE _snap ON COMMIT DROP AS "
                            f"SELECT {col_list} FROM {table} WITH NO DATA")
                if keep == cols:
                    cur.copy_expert("COPY _snap (%s) FROM STDIN WITH (FORMAT csv, HEADER true)"
                                    % col_list, io.StringIO(text))
                else:   # re-emit the CSV without the dropped column
                    rows = list(csv.reader(io.StringIO(text)))
                    idx = [cols.index(c) for c in keep]
                    out = io.StringIO()
                    w = csv.writer(out)
                    for r in rows:
                        w.writerow([r[i] for i in idx])
                    cur.copy_expert("COPY _snap (%s) FROM STDIN WITH (FORMAT csv, HEADER true)"
                                    % col_list, io.StringIO(out.getvalue()))
                cur.execute(f"INSERT INTO {table} ({col_list}) SELECT {col_list} FROM _snap "
                            f"ON CONFLICT DO NOTHING")
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                after = cur.fetchone()[0]
            conn.commit()
            result[table] = (before, after)
            log(f"  [snapshot] {table:28} rows before={before:4d}  after={after:4d}  "
                f"({os.path.basename(path)})")
    finally:
        conn.close()
    return result


def snapshot_main(snap_dir):
    """--snapshot DIR: load the cloud's warm cache, run ONLY the WARM phase, PASS-check
    it, run the independent gpt-4.1 audit on the same evidence bundle. Own DB
    (:55986), own budget ledger (LOCAL-886, default dir), at most one paid run per
    call; the spend is recorded into the ledger even if the run crashes."""
    global _OWN_DB, _METER_DIR, _ART_DIR
    _OWN_DB, _METER_DIR = _SNAP_DB, os.path.join(_HERE, f"_local{_SNAP_TAG}_meterlogs")
    _ART_DIR = os.path.join(_HERE, "submission_artifacts", f"local{_SNAP_TAG}")
    os.makedirs(_ART_DIR, exist_ok=True)
    os.makedirs(_METER_DIR, exist_ok=True)
    if os.environ.get("TASK_BUDGET_ID") != _SNAP_BUDGET_ID:
        sys.exit(f"refusing live run: launch with TASK_BUDGET_ID={_SNAP_BUDGET_ID}")
    if os.environ.get("AUDIOURA_TASK_BUDGET_DIR"):
        sys.exit("refusing: AUDIOURA_TASK_BUDGET_DIR must be unset (default ledger dir only)")
    import task_budget
    hard_cap = float(os.environ.get("TASK_BUDGET_USD", "0.70") or "0.70")
    spent = task_budget.spent_so_far(_SNAP_BUDGET_ID)
    audit_reserve = float(os.environ.get("LOCAL886_AUDIT_RESERVE", "0.08"))
    print(f"[LOCAL-886] ledger spent_so_far={spent} of cap ${hard_cap:.2f}", flush=True)
    if spent + audit_reserve + 0.10 > hard_cap:
        sys.exit("refusing: not enough ledger headroom for one more run (unproven, hand to LEAD)")
    # [LOCAL-888] sitecustomize may already have imported paid_api_meter with the
    # default /meterlogs path; export the harness log AND re-point the live module,
    # or the run is metered into the void and recorded as $0.
    import meter_guard
    _log_path = os.environ.get("PAID_API_LOG") or os.path.join(_METER_DIR, "paid_api_calls.jsonl")
    _repointed = meter_guard.repoint_meter_log(_log_path)
    print(f"[LOCAL-888] meter log {_log_path} (live meter re-pointed={_repointed})", flush=True)

    _apply_live_env()
    os.environ["DB_PORT"] = _SNAP_PORT
    os.environ["DATABASE_URL"] = os.environ["VENUE_CACHE_DB_URL"] = _SNAP_DB
    os.environ.setdefault("GROUNDING_GATE_ENABLED", "1")
    os.environ.setdefault("GROUNDING_GATE_MODEL", "gpt-4.1-mini")

    print("\n=== LOAD CLOUD CACHE SNAPSHOT ===", flush=True)
    load_snapshot(snap_dir, _SNAP_DB, log=lambda m: print(m, flush=True))

    sys.modules.setdefault("run_cloud_parity_proof", sys.modules[__name__])
    import run_cloud_parity_proof_884 as h884
    meter_before = _meter_total()
    rows_before = meter_guard.count_rows(_log_path)
    rc, run_usd = 1, 0.0
    warm_log, audit_ran = "", False
    try:
        warm_cap = meter_before + (hard_cap - spent - audit_reserve)
        warm_text, warm_log = phase("warm", warm_cap)
        print("\n=== WARM PASS CHECK (cloud-parity + 884 criteria) ===", flush=True)
        warm_ok = h884.evaluate_884(warm_text, warm_log)
        print(f"=== WARM {'PASS' if warm_ok else 'FAIL'} ===", flush=True)
        print("\n=== INDEPENDENT gpt-4.1 AUDIT (same evidence bundle; evidence_chars/stop) ===",
              flush=True)
        ev = h884._build_evidence_by_stop()
        audit, audit_ok = h884.independent_audit(warm_text, ev)
        audit_ran = True
        audit["used_cloud_snapshot"] = True
        with open(os.path.join(_ART_DIR, "saigon_warm_audit.json"), "w", encoding="utf-8") as f:
            json.dump(audit, f, ensure_ascii=False, indent=2)
        uns = audit.get("unsupported")
        print(f"   audit unsupported={len(uns) if isinstance(uns, list) else 'ERROR'}", flush=True)
        for u in (uns or []):
            print(f"      UNSUPPORTED [{u.get('stop')}]: {u.get('claim', '')[:120]}", flush=True)
        rc = 0 if (warm_ok and audit_ok) else 1
    finally:
        run_usd = max(0.0, _meter_total() - meter_before)
        rows_run = meter_guard.count_rows(_log_path) - rows_before
        verdict = meter_guard.check_meter(rows_run, run_usd, warm_log, audit_ran)
        if not verdict["ok"]:
            print("\n" + "!" * 78 + "\n" + verdict["message"] + "\n" + "!" * 78, flush=True)
            rc = 3                      # a mis-metered run never reports success
        run_usd = verdict["record_usd"]
        task_budget.record_run(_SNAP_BUDGET_ID, run_usd, note="snapshot warm run + audit"
                               + ("" if verdict["ok"] else " (ESTIMATE: meter undercount)"))
        print(f"\n[LOCAL-888] meter rows this run: {rows_run}; {verdict['message']}", flush=True)
        print(f"\n[LOCAL-886] run metered ${run_usd:.4f}; ledger now "
              f"${task_budget.spent_so_far(_SNAP_BUDGET_ID)} of ${hard_cap:.2f}", flush=True)
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selfcheck", action="store_true",
                    help="offline wiring check: build the payload + run PASS checks on the wave-40 text")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--cold", action="store_true")
    ap.add_argument("--warm", action="store_true")
    ap.add_argument("--run", action="store_true", help="seed + cold + warm, PASS on warm")
    ap.add_argument("--snapshot", metavar="DIR", default=None,
                    help="LOCAL-886: load the CLOUD cache snapshot (cloud_*_cache_*.csv.gz) "
                         "from DIR into the disposable proof DB, then run ONLY the WARM "
                         "phase + the independent gpt-4.1 audit (no seed, no cold)")
    args = ap.parse_args()

    if args.snapshot:
        return snapshot_main(args.snapshot)

    os.makedirs(_ART_DIR, exist_ok=True)
    os.makedirs(_METER_DIR, exist_ok=True)

    if args.selfcheck:
        return _selfcheck()

    _apply_live_env()
    if os.environ.get("TASK_BUDGET_ID") != "LOCAL-882":
        sys.exit("refusing live run: launch with TASK_BUDGET_ID=LOCAL-882 (see docstring)")
    hard_cap = float(os.environ.get("TASK_BUDGET_USD", "0.60") or "0.60")
    # The WARM run is the one PASS-checked, so it gets the largest share. Seed only
    # needs to PLANT old-rule cache rows (a partial tour still writes them), so it
    # is capped tighter; cold gets a middle share; warm gets whatever remains up to
    # the hard cap.
    seed_cap = float(os.environ.get("LOCAL882_SEED_CAP", "0.18"))
    cold_cap = float(os.environ.get("LOCAL882_COLD_CAP", "0.18"))

    if args.run or args.seed:
        if _meter_total() + 0.01 > hard_cap + 1e-9:
            sys.exit(f"refusing seed: meter ${_meter_total():.4f} near cap ${hard_cap:.2f}")
        seed_with_base(min(_meter_total() + seed_cap, hard_cap))

    if args.run or args.cold:
        phase("cold", min(hard_cap, _meter_total() + cold_cap))

    warm_ok = None
    if args.run or args.warm:
        # warm: the full remaining budget (up to the hard cap).
        text, log = phase("warm", hard_cap)
        print("\n=== WARM PASS CHECK (cloud-parity) ===", flush=True)
        warm_ok = evaluate(text, log)
        print(f"=== WARM {'PASS' if warm_ok else 'FAIL'} === "
              f"(task meter ${_meter_total():.4f} of ${hard_cap:.2f})", flush=True)

    if warm_ok is None:
        return 0
    return 0 if warm_ok else 1


def _selfcheck():
    """No network, no spend. Proves (a) the payload builder shapes the quick-path
    strings and (b) the PASS checks correctly FAIL the wave-40 text and PASS a
    clean text — so a green WARM run is meaningful."""
    print("=== SELFCHECK (offline) ===", flush=True)
    ok = True

    # (a) payload builder with an injected offline resolver (no network).
    import itinerary_import as ii

    def _canon_stub(user_name, pin, city="", local_lang=""):
        return None  # offline: no canonical, matched_name falls back

    def _nom_stub(params):
        return []    # offline: no pin from Nominatim (we override pins anyway)
    # We cannot fully resolve offline; instead feed reviewed objects directly to
    # stops_for_generation, which is what preview feeds downstream.
    objs = [{"name": n, "stop_name": n, "lat": lat, "lng": lng, "matched_name": None}
            for n, lat, lng in SHORT_STOPS]
    forced, pins = ii.stops_for_generation(objs)
    ok &= _check("payload: 10 forced strings built", len(forced) == 10, len(forced))
    ok &= _check("payload: every stop carries a pin (/@lat,lng)",
                 pins == 10, pins)
    ok &= _check("payload: short names kept as spoken titles",
                 all(forced[i].startswith(SHORT_STOPS[i][0]) for i in range(10)),
                 forced[6][:60])

    # (b) the PASS checks must FAIL the actual wave-40 text and PASS a clean one.
    print("\n   -- evaluate the wave-40 text (must FAIL) --", flush=True)
    w40_pass = evaluate(_WAVE40_SAMPLE, "", require_ten=False)
    ok &= _check("wave-40 text is correctly judged a FAIL", not w40_pass)

    print("\n   -- evaluate a clean text (must PASS) --", flush=True)
    clean_pass = evaluate(_CLEAN_SAMPLE, "", require_ten=False)
    ok &= _check("clean text is correctly judged a PASS", clean_pass)

    print(f"\n=== SELFCHECK {'PASS' if ok else 'FAIL'} ===", flush=True)
    return 0 if ok else 1


# A trimmed slice of the wave-40 text (the defective lines) for the selfcheck.
_WAVE40_SAMPLE = """This is a step-by-step audio-guided walking tour of Ho Chi Minh City, Vietnam.

Stop 1: Cathedral
Orientation: The current cathedral was completed in 1880. Construction began when Bishop Isidore Colombert laid the first stone in October 1877, and the building was completed 14 years later using materials brought from France. The twin bell towers rising to, and the large white statue of Mary. The bells still weave through the city. In front stands a statue installed in 1959.
Directions: Enjoy the stroll!

Stop 4: Independence Palace
Orientation: The palace matters here.
The Independence Palace was designed by architect Ngô Viết Thụ under the order of Đình Diệm. President Ngô Đình Diệm and his brother were assassinated inside the palace during a coup. The palace's role as a symbol of power came to an even more dramatic close on 30 April 1975. It continued as a government office. Today it is a museum.
Directions: Head northwest for about 500 meters.

Stop 7: City Hall
Orientation: The wide courtyard softens the bustle.
From 1898 through 1908, the building now known as City Hall was crafted for French colonial governments. Completed in 1890 and designed by Alfred Foulhoux, that building started as a Museum of Commercial Trade before shifting roles. City Hall's steadfast presence reflects the administrative heartbeat.
Directions: Head southeast for roughly 400 meters.

A note on current affairs: this tour draws on documented history, and we found no verified developments from the past five years to include here.
"""

_CLEAN_SAMPLE = """This is a step-by-step audio-guided walking tour of Ho Chi Minh City, Vietnam.

Stop 1: Cathedral
Orientation: You stand before the cathedral's red brick exterior.
The current cathedral was completed in 1880, replacing an earlier church. Designed by Jules Bourard, this neo-Gothic structure echoed Paris. The red bricks were imported from France. The twin bell towers each hold six bronze bells, added in 1895. In front stands a statue of Mary, installed in 1959.
Directions: From the Cathedral, head to the Post Office about 200 metres northeast.

Stop 4: Independence Palace
Orientation: You cross into a wide forecourt.
The Independence Palace was designed by Ngô Viết Thụ, with construction from 1962. It replaced an older residence. On 30 April 1975 a North Vietnamese tank crashed through the palace gates, ending the war. The palace served as the seat of government. Today it is a museum open to the public.
Directions: Head northwest for about 500 metres to the War Remnants Museum.

Stop 7: City Hall
Orientation: The wide courtyard softens the bustle.
From 1898 to 1909, the Hôtel de Ville was built as the administrative centre. Its French colonial façade still frames the square. The building became the People's Committee office after 1975. Trimmed hedges line the courtyard today. Scooters pass on the boulevard beyond.
Directions: Head southeast for roughly 400 metres to the Café Apartments.
"""


if __name__ == "__main__":
    raise SystemExit(main())
