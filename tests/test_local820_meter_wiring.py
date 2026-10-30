"""tests/test_local820_meter_wiring.py — GUARD: isolated task containers MUST meter.

LOCAL-820: the isolated ``docker run --rm`` task containers wrote their paid-API
meter rows to ``/meterlogs`` INSIDE the container, where ``--rm`` destroyed them.
LOCAL-818's two live tours left ZERO rows in ~/Audioura/meterlogs — the real
source of the ~16k unmetered OpenAI calls. The fix wires every isolated-container
harness with ``meter_container_env.docker_meter_args()`` so each run bind-mounts
the shared host meterlog dir, writes the canonical log, installs the meter
(PYTHONPATH=/opt/meter) and tags its rows ``service=<task id>``.

These tests FAIL if that wiring regresses or if a NEW harness starts a generator
container without the meter contract. They are pure/offline — they READ source
files; they make no paid call, start no container, and touch no network.

THE METER CONTRACT (the five signals every metered generator container carries):
  1. PYTHONPATH=/opt/meter                          install the meter (sitecustomize)
  2. PAID_API_LOG=/meterlogs/paid_api_calls.jsonl   the ONE canonical log every sweep reads
  3. METER_SERVICE=<task id>                         tag rows so meter_report.py totals per task
  4. -v <host meterlogs>:/meterlogs                  land rows on the host (survive --rm)
  5. -v <repo>/_meter:/opt/meter:ro                  the metered code, in lock-step with the branch
"""
import glob
import os
import re
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# The image name every isolated generator container runs. A wrapper that
# launches it is making paid calls and MUST meter them.
_GENERATOR_IMAGE_RE = re.compile(r"audioura-tour-generator")

# The five contract signals as source substrings (host-dir path is a variable in
# the wrappers, so match the ``:/meterlogs`` / ``:/opt/meter:ro`` mount tails).
_CONTRACT_SIGNALS = {
    "PYTHONPATH=/opt/meter": "PYTHONPATH=/opt/meter",
    "canonical PAID_API_LOG": "PAID_API_LOG=/meterlogs/paid_api_calls.jsonl",
    "METER_SERVICE tag": "METER_SERVICE=",
    "meterlogs bind-mount": ":/meterlogs",
    "_meter bind-mount (:/opt/meter:ro)": ":/opt/meter:ro",
}


def _read(path):
    with open(path, encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def _generator_shell_wrappers():
    """Every run_local*.sh in the repo root that launches the generator image via
    ``docker run``. These are the real paid-call container surfaces."""
    out = []
    for path in sorted(glob.glob(os.path.join(_ROOT, "run_local*.sh"))):
        src = _read(path)
        if "docker run" in src and _GENERATOR_IMAGE_RE.search(src):
            out.append(path)
    return out


# ── 1. the shared runner uses the helper ─────────────────────────────────────

def test_isolated_test_runner_uses_docker_meter_args():
    """isolated_test.py is the SHARED runner the run_local*_container.py harnesses
    copy from. It must build its ``docker run`` argv with
    meter_container_env.docker_meter_args() — not a hand-rolled command that
    forgets the meter (the LOCAL-820 bug)."""
    path = os.path.join(_ROOT, "isolated_test.py")
    assert os.path.exists(path), "isolated_test.py (the shared runner) is missing"
    src = _read(path)
    assert "meter_container_env" in src, (
        "isolated_test.py must import meter_container_env")
    assert "docker_meter_args" in src, (
        "isolated_test.py must call docker_meter_args() when building docker_cmd "
        "— otherwise every isolated run's paid-API spend dies inside the --rm "
        "container (LOCAL-820)")
    # The call must feed the actual docker command, not sit in a comment: the
    # token appears where docker_cmd is extended.
    assert re.search(r"docker_cmd\s*\+=\s*mce\.docker_meter_args|"
                     r"docker_cmd\s*\+=\s*meter_container_env\.docker_meter_args",
                     src), (
        "docker_meter_args() must be appended to docker_cmd in isolated_test.py")


# ── 2. every generator shell wrapper carries the full contract ────────────────

def test_at_least_one_generator_wrapper_exists():
    """Sanity: the scan actually finds generator wrappers (so a silent glob/path
    break can't make the contract test vacuously pass)."""
    wrappers = _generator_shell_wrappers()
    assert wrappers, (
        "found no run_local*.sh launching the generator image — the guard would "
        "be vacuous; check the glob/path")


@pytest.mark.parametrize("wrapper", _generator_shell_wrappers(),
                         ids=lambda p: os.path.basename(p))
def test_generator_wrapper_carries_meter_contract(wrapper):
    """Any run_local*.sh that starts a generator container MUST carry all five
    meter-contract signals. A new wrapper that forgets them FAILS here before it
    can burn un-metered spend."""
    src = _read(wrapper)
    missing = [label for label, token in _CONTRACT_SIGNALS.items()
               if token not in src]
    assert not missing, (
        "%s launches the generator image but is MISSING meter-contract signal(s): "
        "%s. Add the args meter_container_env.docker_meter_args() returns "
        "(see run_local818_live.sh)." % (os.path.basename(wrapper), missing))


# ── 3. the helper itself still produces the contract ──────────────────────────

def test_docker_meter_args_emits_full_contract(tmp_path):
    """The whole fix rests on docker_meter_args(); pin its output so a change to
    the helper can't silently drop a signal the wrappers rely on."""
    import meter_container_env as mce
    args = mce.docker_meter_args(task_id="LOCAL-820",
                                 meter_dir="/repo/_meter",
                                 host_meter_dir=str(tmp_path),
                                 key_suffix="k9sA")
    joined = " ".join(args)
    assert "PYTHONPATH=/opt/meter" in joined
    assert "PAID_API_LOG=/meterlogs/paid_api_calls.jsonl" in joined
    assert "METER_SERVICE=LOCAL-820" in joined
    assert "%s:/meterlogs" % tmp_path in joined
    assert "/repo/_meter:/opt/meter:ro" in joined
    assert "METER_KEY_SUFFIX=k9sA" in joined


# ── 4. the shell wrappers are valid bash (so the contract is in live code) ────

@pytest.mark.parametrize("wrapper", _generator_shell_wrappers(),
                         ids=lambda p: os.path.basename(p))
def test_generator_wrapper_is_valid_bash(wrapper):
    """A wrapper that carries the signals but does not parse would never run; keep
    the contract in executable code, not a broken script."""
    if not os.path.exists("/bin/bash"):  # pragma: no cover - macOS/Linux have bash
        pytest.skip("bash not available")
    res = subprocess.run(["bash", "-n", wrapper],
                         capture_output=True, text=True)
    assert res.returncode == 0, (
        "%s is not valid bash:\n%s" % (os.path.basename(wrapper), res.stderr))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
