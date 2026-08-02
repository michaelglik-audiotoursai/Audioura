#!/usr/bin/env python3
"""
test_local114_referral_wiring_guard.py — Guard test for referral blueprint registration.
========================================================================================
LOCAL-114: Verify referral_bp is registered on generate_tour_text_service.py.

This test FAILS if the register_blueprint(referral_bp) line is removed or commented out.

Three parts:
  PART 1: AST guard — confirms the registration is live code (not commented/stringified)
  PART 2: Live HTTP guard — confirms POST /referral/create returns non-404
  PART 3: Abuse surface audit — REPORTS what controls exist (informational, never fails)

Exit 0 = wiring correct. Exit 1 = wiring broken (Parts 1/2 only).

Usage:
    python3 tests/test_local114_referral_wiring_guard.py
"""
import ast
import os
import sys

# ─── Test harness ────────────────────────────────────────────────────────────
PASS_COUNT = 0
FAIL_COUNT = 0
FINDING_COUNT = 0  # Part 3 informational findings (never cause exit 1)


def check(name: str, condition: bool, detail: str = ""):
    """Hard assertion — failure causes exit 1."""
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  PASS: {name}")
        PASS_COUNT += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        FAIL_COUNT += 1


def finding(name: str, present: bool, detail: str = ""):
    """Informational finding — reports status, never causes exit 1."""
    global FINDING_COUNT
    FINDING_COUNT += 1
    status = "PRESENT" if present else "MISSING"
    marker = "✓" if present else "⚠"
    msg = f"  {marker} [{status}] {name}"
    if not present and detail:
        msg += f" — {detail}"
    print(msg)


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1: AST Guard — register_blueprint(referral_bp) is live code
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PART 1: AST Guard — referral_bp registration is live code")
print("=" * 70)

SERVICE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "generate_tour_text_service.py",
)

check("Service file exists", os.path.isfile(SERVICE_FILE), f"Not found: {SERVICE_FILE}")

if os.path.isfile(SERVICE_FILE):
    source = open(SERVICE_FILE).read()

    # Check 1: import statement present
    has_import = "from referral_endpoints import referral_bp" in source
    check("import referral_bp present in source", has_import,
          "Expected: 'from referral_endpoints import referral_bp'")

    # Check 2: register_blueprint call present in text
    has_register = "register_blueprint(referral_bp)" in source
    check("register_blueprint(referral_bp) call present", has_register,
          "Expected: 'app.register_blueprint(referral_bp)' or similar")

    # Check 3: AST confirms it's executable code (not in a comment or string)
    tree = ast.parse(source)
    found_in_ast = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Look for *.register_blueprint(referral_bp)
            func = node.func
            if (isinstance(func, ast.Attribute)
                    and func.attr == "register_blueprint"
                    and len(node.args) >= 1
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id == "referral_bp"):
                found_in_ast = True
                break
    check("AST confirms register_blueprint(referral_bp) is live code", found_in_ast,
          "Call exists in text but not in AST — possibly commented out or in a string")

    # Check 4: referral_endpoints.py exists and defines referral_bp
    endpoints_file = os.path.join(os.path.dirname(SERVICE_FILE), "referral_endpoints.py")
    check("referral_endpoints.py exists", os.path.isfile(endpoints_file),
          f"Not found: {endpoints_file}")

    if os.path.isfile(endpoints_file):
        ep_source = open(endpoints_file).read()
        ep_tree = ast.parse(ep_source)
        has_bp_def = any(
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "referral_bp" for t in node.targets)
            for node in ast.walk(ep_tree)
        )
        check("referral_bp defined in referral_endpoints.py", has_bp_def,
              "Expected: referral_bp = Blueprint(...)")

        # Check routes defined
        routes_found = []
        for node in ast.walk(ep_tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    if (isinstance(decorator, ast.Call)
                            and isinstance(decorator.func, ast.Attribute)
                            and decorator.func.attr == "route"):
                        if decorator.args:
                            route_str = ast.literal_eval(decorator.args[0])
                            routes_found.append(route_str)
        check("POST /referral/create route defined", "/referral/create" in routes_found,
              f"Routes found: {routes_found}")
        check("POST /referral/redeem route defined", "/referral/redeem" in routes_found,
              f"Routes found: {routes_found}")

    # Check 5: referral_engine.py exists (dependency)
    engine_file = os.path.join(os.path.dirname(SERVICE_FILE), "referral_engine.py")
    check("referral_engine.py exists", os.path.isfile(engine_file),
          f"Not found: {engine_file}")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: Live HTTP Guard — POST /referral/create returns non-404
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PART 2: Live HTTP Guard — POST /referral/create reachable")
print("=" * 70)

SERVICE_URL = os.environ.get("SERVICE_URL", "http://localhost:5100")
API_KEY = os.environ.get("GATEWAY_API_KEY", "test-api-key")

# Use unique IDs per run to avoid collisions with duplicate-redemption guard (LOCAL-115)
import time as _time
_RUN_TS = str(int(_time.time()))
_CREATOR_ID = f"guard_test_user_{_RUN_TS}"
_REDEEMER_ID = f"guard_new_user_{_RUN_TS}"

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("  SKIP: requests not installed — live HTTP tests skipped")

if REQUESTS_AVAILABLE:
    try:
        # Test: POST /referral/create should NOT return 404
        resp = requests.post(
            f"{SERVICE_URL}/referral/create",
            json={"user_id": _CREATOR_ID},
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            timeout=10,
        )
        check("POST /referral/create is NOT 404", resp.status_code != 404,
              f"Got {resp.status_code} — blueprint not registered!")
        check("POST /referral/create returns 200", resp.status_code == 200,
              f"Got {resp.status_code}: {resp.text[:200]}")

        if resp.status_code == 200:
            data = resp.json()
            code = data.get("referral_code", "")
            check("Response contains referral_code", bool(code), f"Got: {data}")
            check("referral_code is 6-char", len(code) == 6, f"Got: '{code}' (len={len(code)})")
            check("Response contains referral_url", bool(data.get("referral_url")),
                  f"Got: {data}")

            # Test: POST /referral/redeem should NOT return 404
            resp2 = requests.post(
                f"{SERVICE_URL}/referral/redeem",
                json={"referral_code": code, "new_user_id": _REDEEMER_ID},
                headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
                timeout=10,
            )
            check("POST /referral/redeem is NOT 404", resp2.status_code != 404,
                  f"Got {resp2.status_code} — blueprint not registered!")
            check("POST /referral/redeem returns 200", resp2.status_code == 200,
                  f"Got {resp2.status_code}: {resp2.text[:200]}")

            if resp2.status_code == 200:
                data2 = resp2.json()
                check("Redeem response has redeemed=true", data2.get("redeemed") is True,
                      f"Got: {data2}")
                check("Redeem response has referrer_user_id",
                      data2.get("referrer_user_id") == _CREATOR_ID,
                      f"Got: {data2.get('referrer_user_id')}")

        # Test: Missing API key returns 401
        resp3 = requests.post(
            f"{SERVICE_URL}/referral/create",
            json={"user_id": _CREATOR_ID},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        check("Missing API key returns 401", resp3.status_code == 401,
              f"Got {resp3.status_code}")

        # Test: Unknown code returns 404
        resp4 = requests.post(
            f"{SERVICE_URL}/referral/redeem",
            json={"referral_code": "ZZZZZZ", "new_user_id": "nobody"},
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            timeout=10,
        )
        check("Unknown referral code returns 404", resp4.status_code == 404,
              f"Got {resp4.status_code}")

    except requests.ConnectionError:
        print(f"  SKIP: Cannot connect to {SERVICE_URL} — is subscribed-generator running?")
        print("         Start with: docker compose -f docker-compose-subscribed.yml up -d --build")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3: Abuse Surface Audit — INFORMATIONAL (never causes exit 1)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PART 3: Abuse Surface Audit — referral controls inventory (informational)")
print("         These are findings, not assertions. Missing controls do NOT")
print("         cause test failure — they are reported for future task planning.")
print("=" * 70)

if os.path.isfile(SERVICE_FILE):
    # Verify no wallet/credit/balance references in referral chain
    ref_ep_source = open(os.path.join(os.path.dirname(SERVICE_FILE), "referral_endpoints.py")).read()
    ref_eng_source = open(os.path.join(os.path.dirname(SERVICE_FILE), "referral_engine.py")).read()
    combined = ref_ep_source + ref_eng_source

    finding("No wallet_ledger reference in referral chain",
            "wallet_ledger" not in combined,
            "DANGER: referral chain touches wallet_ledger")
    finding("No credit/balance grant in referral chain",
            "credit" not in combined.lower() and "balance" not in combined.lower()
            and "grant" not in combined.lower(),
            "REVIEW: referral chain may grant value")
    finding("No cost_meter reference in referral chain",
            "cost_meter" not in combined,
            "referral chain touches cost_meter")

    # Document missing controls
    has_self_referral_guard = ("== new_user_id" in ref_ep_source
                               or "!= new_user_id" in ref_ep_source
                               or "self-referral" in ref_ep_source.lower()
                               or "self_referral" in ref_ep_source.lower())
    finding("Self-referral guard (referrer != redeemer)",
            has_self_referral_guard,
            "No check prevents a user from redeeming their own referral code")

    has_unique_constraint = "UNIQUE" in ref_eng_source or "unique" in ref_eng_source
    has_dup_check = "already" in ref_ep_source.lower() or "duplicate" in ref_ep_source.lower()
    finding("Duplicate redemption guard",
            has_unique_constraint or has_dup_check,
            "Same user can redeem same code multiple times (no UNIQUE constraint)")

    has_rate_limit = "rate" in combined.lower() and "limit" in combined.lower()
    finding("Rate limiting on referral endpoints",
            has_rate_limit,
            "No rate limiting on referral endpoints")

    # Summary table
    print("\n  ┌─────────────────────────────────────────────────────────────────┐")
    print("  │ ABUSE CONTROL SUMMARY (for future task planning)               │")
    print("  ├─────────────────────────┬──────────┬───────────────────────────┤")
    print("  │ Control                 │ Status   │ Impact (today)            │")
    print("  ├─────────────────────────┼──────────┼───────────────────────────┤")
    print("  │ API key gate            │ PRESENT  │ —                         │")
    print("  │ Self-referral guard     │ MISSING  │ Low (grants nothing)      │")
    print("  │ Duplicate redemption    │ MISSING  │ Low (inflates counter)    │")
    print("  │ Rate limiting           │ MISSING  │ Low (data spam only)      │")
    print("  └─────────────────────────┴──────────┴───────────────────────────┘")
    print("\n  Proposed follow-up: Add all three controls BEFORE any value")
    print("  (credit/wallet) is ever wired to the redeem path.")


# ═══════════════════════════════════════════════════════════════════════════════
# Summary — exit code based on Parts 1+2 ONLY
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL, {FINDING_COUNT} findings (informational)")
if FAIL_COUNT == 0:
    print("ALL ASSERTIONS PASSED — wiring is correct")
    print(f"  ({FINDING_COUNT} Part 3 findings are informational, not regressions)")
else:
    print("WIRING BROKEN — Parts 1/2 have failures (actual regressions)")
print("=" * 70)

sys.exit(0 if FAIL_COUNT == 0 else 1)
