"""test_local572_pools_in_scope.py — LOCAL-572 r2 lint test.

Guards the invariant that bounced r1: a worker thread that does NOT copy the
tour's dead-host context falls back to the process-level default set, which is
exactly the cross-tour leak this task removes. r2 funnels every pool/thread on
the tour path through `dead_host_breaker.tour_executor()` / `tour_thread()`,
whose workers run inside the active tour's cold set.

This test fails if any module in the tour call graph constructs a raw
`ThreadPoolExecutor(...)` or `threading.Thread(...)` directly instead of the
helper. The list of guarded modules is kept EXPLICIT below — when a new module
on the tour path grows a pool, add it here (and route it through the helper).

Why AST, not grep: we flag CALL expressions only, so `from concurrent.futures
import ThreadPoolExecutor` (an import, needed because `as_completed`/`wait` still
come from there) does not trip the lint — only an actual `ThreadPoolExecutor(`
construction does.
"""
import ast
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# Modules reachable from generate_tour_text() that fan out to worker threads.
# Every pool/thread created here runs network fetches whose 429/timeout must
# stay cold for THIS tour only. Keep this list explicit and in sync with the
# conversions in SUBMISSION_LOCAL-572.md (## r2).
TOUR_PATH_MODULES = [
    "generate_tour_text.py",
    "fact_extractor.py",
    "story_element_extractor.py",
    "venue_parts.py",
    "story_first.py",
    "work_story_searcher.py",
]

# The only sanctioned ways to create a worker pool/thread on the tour path.
ALLOWED_FACTORIES = {"tour_executor", "tour_thread"}


def _call_name(node: ast.Call) -> str:
    """Return the dotted name being called, e.g. 'ThreadPoolExecutor' or
    'threading.Thread' or 'dead_host_breaker.tour_executor'."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts = []
        cur = func
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


def _find_raw_pools(path: str):
    """Return list of (lineno, call_name) for forbidden raw pool/thread
    constructions in the given source file."""
    with open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        last = name.rsplit(".", 1)[-1]
        # Forbidden: a direct ThreadPoolExecutor(...) construction, or a
        # threading.Thread(...) construction, unless it is the sanctioned helper.
        is_pool = last == "ThreadPoolExecutor"
        is_thread = name.endswith("threading.Thread") or last == "Thread"
        if (is_pool or is_thread) and last not in ALLOWED_FACTORIES:
            offenders.append((node.lineno, name))
    return offenders


class TestPoolsInTourScope(unittest.TestCase):
    def test_no_raw_pools_or_threads_on_tour_path(self):
        """Every pool/thread on the tour path must go through tour_executor /
        tour_thread so its workers run in the active tour's cold set."""
        all_offenders = {}
        for mod in TOUR_PATH_MODULES:
            path = os.path.join(_ROOT, mod)
            self.assertTrue(
                os.path.exists(path),
                f"tour-path module missing: {mod} (fix TOUR_PATH_MODULES)",
            )
            offenders = _find_raw_pools(path)
            if offenders:
                all_offenders[mod] = offenders

        if all_offenders:
            lines = ["Raw ThreadPoolExecutor/threading.Thread on the tour path "
                     "(use dead_host_breaker.tour_executor / tour_thread):"]
            for mod, offs in all_offenders.items():
                for lineno, name in offs:
                    lines.append(f"  {mod}:{lineno}: {name}(...)")
            self.fail("\n".join(lines))

    def test_helpers_exist(self):
        """tour_executor and tour_thread must exist and be callable."""
        import dead_host_breaker
        self.assertTrue(callable(getattr(dead_host_breaker, "tour_executor", None)))
        self.assertTrue(callable(getattr(dead_host_breaker, "tour_thread", None)))


if __name__ == "__main__":
    unittest.main()
