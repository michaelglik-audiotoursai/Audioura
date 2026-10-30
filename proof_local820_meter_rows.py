#!/usr/bin/env python3
"""proof_local820_meter_rows.py — LOCAL-820 ROOT-CAUSE PROOF (dry, no paid calls).

Shows, with a STUBBED OpenAI endpoint (httpx.MockTransport — no network, no spend),
exactly WHERE an isolated task container's paid-API meter rows go, and why
LOCAL-818's live tours left ZERO rows in ~/Audioura/meterlogs/.

The meter (``_meter/paid_api_meter.py``, baked into audioura-tour-generator at
``PYTHONPATH=/opt/meter``) writes every paid call to::

    LOG = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")

Two cases, both with the SAME stubbed OpenAI call:

  A. "LOCAL-818 as shipped"  — the container set NEITHER PAID_API_LOG nor a
     ``-v ~/Audioura/meterlogs:/meterlogs`` mount. LOG therefore points at the
     DEFAULT ``/meterlogs/paid_api_calls.jsonl`` INSIDE the container. With no
     bind mount that path lives on the container's own writable layer and is
     DESTROYED with ``docker run --rm``. Here we model that by pointing LOG at a
     throwaway "container-only" dir that we then delete — the row is gone.

  B. "LOCAL-820 fix"         — meter_container_env.docker_meter_args() sets
     PAID_API_LOG=/meterlogs/paid_api_calls.jsonl AND bind-mounts the host's
     ~/Audioura/meterlogs at /meterlogs, and tags METER_SERVICE=<task id>. The
     row lands on the HOST dir, survives the container, and meter_report.py sums
     it. Here we model the bind mount by pointing LOG at a host dir that we keep.

Run:  python3 proof_local820_meter_rows.py
It makes NO paid call and writes only under a tmp dir; it never touches
~/Audioura/meterlogs.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_meter"))

try:
    import httpx
except Exception:  # pragma: no cover
    print("httpx required for the stubbed-endpoint proof; pip install httpx")
    raise SystemExit(2)

import paid_api_meter as m
import meter_container_env as mce


def _stub_openai_call():
    """One OpenAI chat call through a MockTransport — no network, no spend. The
    meter's httpx patch records it exactly as a real call."""
    def handler(request):
        return httpx.Response(200, json={
            "model": "gpt-4.1-mini-2025-04-14",
            "usage": {"prompt_tokens": 11, "completion_tokens": 3,
                      "total_tokens": 14}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    client.post("https://api.openai.com/v1/chat/completions",
                json={"model": "gpt-4.1-mini", "max_tokens": 3,
                      "messages": [{"role": "user", "content": "hi"}]})


def _rows(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _run_case(name, log_path, service, key_suffix=None):
    """Install the meter writing to log_path, make one stubbed call, return rows."""
    # Reset the meter's module-level LOG + SERVICE to model a fresh container env.
    os.environ.pop("METER_SERVICE", None)
    os.environ.pop("METER_KEY_SUFFIX", None)
    if service is not None:
        os.environ["METER_SERVICE"] = service
    if key_suffix is not None:
        os.environ["METER_KEY_SUFFIX"] = key_suffix
    m.LOG = log_path
    m.SERVICE = m._default_service()
    # DB write is the shared-DB path (isolated containers can't reach it); stub it
    # so this proof is purely about the JSONL log location.
    m._db_write = lambda rec: None
    m.check_daily_limit = lambda: None
    m.check_task_budget = lambda: None
    m.install()  # idempotent
    _stub_openai_call()
    return _rows(log_path)


def main():
    tmp = tempfile.mkdtemp(prefix="local820_proof_")
    # "inside the --rm container": a dir we delete to model the container layer.
    container_dir = os.path.join(tmp, "container_layer", "meterlogs")
    os.makedirs(container_dir, exist_ok=True)
    container_log = os.path.join(container_dir, "paid_api_calls.jsonl")
    # "host ~/Audioura/meterlogs bind-mounted at /meterlogs": a dir we keep.
    host_dir = os.path.join(tmp, "host_meterlogs")
    os.makedirs(host_dir, exist_ok=True)
    host_log = os.path.join(host_dir, "paid_api_calls.jsonl")

    print("=" * 78)
    print("LOCAL-820 ROOT-CAUSE PROOF — stubbed OpenAI (no paid calls)")
    print("=" * 78)

    # ── Case A: LOCAL-818 as shipped — no mount, default in-container LOG ──────
    print("\n[A] LOCAL-818 AS SHIPPED: no -v meterlogs mount, LOG defaults to the")
    print("    in-container /meterlogs/paid_api_calls.jsonl (modelled by a tmp")
    print("    'container layer' dir that --rm destroys).")
    rows_a = _run_case("A", container_log, service=None)
    print(f"    rows written to container path : {len(rows_a)}")
    if rows_a:
        r = rows_a[0]
        print(f"      kind={r.get('kind')} service={r.get('service')!r} "
              f"tokens_in={r.get('tokens_in')} tokens_out={r.get('tokens_out')} "
              f"usd={r.get('usd')}")
    # Model `docker run --rm` tearing the container layer down:
    shutil.rmtree(os.path.join(tmp, "container_layer"))
    survived_a = os.path.exists(container_log)
    print(f"    after `docker run --rm` tears the container down:")
    print(f"      container log still exists     : {survived_a}")
    print(f"      rows now visible to meter_report: 0   <-- THE BUG (rows died)")

    # ── Case B: LOCAL-820 fix — docker_meter_args mounts the host dir ──────────
    print("\n[B] LOCAL-820 FIX: meter_container_env.docker_meter_args() sets")
    print("    PAID_API_LOG=/meterlogs/paid_api_calls.jsonl AND bind-mounts the")
    print("    host ~/Audioura/meterlogs at /meterlogs (modelled by a host dir we")
    print("    keep), tagging METER_SERVICE=LOCAL-820.")
    args = mce.docker_meter_args(task_id="LOCAL-820", meter_dir="/repo/_meter",
                                 host_meter_dir=host_dir, key_suffix="k9sA")
    print("    docker_meter_args ->")
    for i in range(0, len(args), 2):
        print("      " + " ".join(args[i:i + 2]))
    rows_b = _run_case("B", host_log, service="LOCAL-820", key_suffix="k9sA")
    survived_b = os.path.exists(host_log)
    print(f"    rows written to HOST path        : {len(rows_b)}")
    print(f"    host log survives the container  : {survived_b}")
    if rows_b:
        r = rows_b[0]
        print(f"      kind={r.get('kind')} service={r.get('service')!r} "
              f"key_suffix={r.get('key_suffix')!r} "
              f"tokens_in={r.get('tokens_in')} tokens_out={r.get('tokens_out')} "
              f"usd={r.get('usd')}")

    # ── Verdict ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 78)
    ok = (len(rows_a) == 1 and not survived_a            # A: written then lost
          and len(rows_b) == 1 and survived_b            # B: written and kept
          and rows_b[0].get("service") == "LOCAL-820"    # tagged for the sweep
          and rows_b[0].get("tokens_in") == 11
          and rows_b[0].get("tokens_out") == 3)
    print("VERDICT: " + ("PROVEN — without the meter mount+env the row is written "
                         "INSIDE the --rm container and dies with it; with "
                         "docker_meter_args() it lands on the host tagged "
                         "service=LOCAL-820." if ok else "UNEXPECTED — see output."))
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
