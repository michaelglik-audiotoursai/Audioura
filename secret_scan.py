#!/usr/bin/env python3
"""
secret_scan.py — Pre-merge secret scanner for Audioura.

Detects hardcoded secrets in staged changes, commit ranges, or the full
working tree. Exits non-zero on any finding.

Modes:
  --staged         Scan currently staged files (git diff --cached)
  --range A..B     Scan commits in a range (git log --diff-filter)
  --tree           Scan the entire working tree

Usage:
  python3 secret_scan.py --staged
  python3 secret_scan.py --range origin/storied..HEAD
  python3 secret_scan.py --tree
  python3 secret_scan.py --tree --json   # machine-readable output
"""
import argparse
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Whitelist: obvious placeholders that must NOT fire.
# ---------------------------------------------------------------------------
WHITELIST_PATTERNS = [
    re.compile(r"^sk-x{8,}$", re.IGNORECASE),             # sk-xxxxxxxx...
    re.compile(r"^your[_-]?key[_-]?here$", re.IGNORECASE),
    re.compile(r"<REDACTED>", re.IGNORECASE),
    re.compile(r"^<YOUR[_-]?.*?KEY>$", re.IGNORECASE),
    re.compile(r"^REPLACE[_-]?WITH[_-]?YOUR", re.IGNORECASE),
    re.compile(r"^insert[_-]?your[_-]?key", re.IGNORECASE),
    re.compile(r"^example[_-]?key", re.IGNORECASE),
    re.compile(r"^test[_-]?key[_-]?123", re.IGNORECASE),
    re.compile(r"^fake[_-]?(api[_-]?)?key", re.IGNORECASE),
    re.compile(r"^dummy[_-]?(api[_-]?)?key", re.IGNORECASE),
    re.compile(r"^placeholder", re.IGNORECASE),
    re.compile(r"^x{16,}$", re.IGNORECASE),              # long runs of x
    re.compile(r"^0{20,}$"),                              # long runs of zeros
    re.compile(r"^1{20,}$"),                              # long runs of ones
    re.compile(r"^A{20,}$"),                              # long runs of A
    re.compile(r"FAKE", re.IGNORECASE),                   # anything with FAKE in it
    re.compile(r"EXAMPLE", re.IGNORECASE),                # anything with EXAMPLE
    re.compile(r"DUMMY", re.IGNORECASE),                  # anything with DUMMY
    re.compile(r"TEST(?:ING|_)", re.IGNORECASE),          # TEST_ or TESTING prefix
]

# Files that contain intentional test fixtures (not real secrets).
# These are skipped in --tree mode to avoid flagging the scanner's own tests.
ALLOWLISTED_FILES = {
    "tests/test_secret_scan.py",
    "secret_scan.py",  # contains pattern literals (e.g. PEM header in return value)
}

# Files/paths to always skip (binary, generated, or known-safe).
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".mp3", ".wav", ".ogg", ".m4a", ".mp4", ".mov", ".avi",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ttf", ".otf", ".woff", ".woff2",
    ".so", ".dylib", ".dll", ".exe", ".o", ".a",
    ".aab", ".apk",
    ".lock",  # package lock files
    ".xib", ".storyboard",  # Apple Interface Builder (XML, not secrets)
    ".download",  # downloaded vendor JS bundles
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".dart_tool",
    ".pub-cache", "build", ".gradle", ".idea", ".vscode",
    "APK_BUILDS",
}

# ---------------------------------------------------------------------------
# Known secret structure — for near-match detection.
# We never store real key material. The near-match detector uses:
# - known prefixes (e.g. sk-proj-)
# - known length ranges
# - entropy threshold
# - absence of FAKE/TEST/EXAMPLE markers
# ---------------------------------------------------------------------------
KNOWN_SECRET_PREFIXES = [
    "sk-proj-",   # OpenAI project keys
]
KNOWN_SECRET_LENGTHS = range(50, 200)


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """A single secret finding."""
    file: str
    line: int
    detector: str
    matched: str  # masked value
    commit: Optional[str] = None
    date: Optional[str] = None


def mask_value(value: str) -> str:
    """Show first 8 chars, mask the rest."""
    if len(value) <= 8:
        return value[:4] + "…"
    return value[:8] + "…" + f"[{len(value)} chars]"


def shannon_entropy(s: str) -> float:
    """Calculate Shannon entropy of a string."""
    if not s:
        return 0.0
    freq = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    length = len(s)
    entropy = 0.0
    for count in freq.values():
        p = count / length
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def is_whitelisted(value: str) -> bool:
    """Check if a value matches any whitelist pattern."""
    for pat in WHITELIST_PATTERNS:
        if pat.search(value):
            return True
    return False


def longest_common_substring_length(a: str, b: str) -> int:
    """Return the length of the longest common substring between a and b."""
    if len(a) > len(b):
        a, b = b, a
    m, n = len(a), len(b)
    prev = [0] * (m + 1)
    best = 0
    for j in range(1, n + 1):
        curr = [0] * (m + 1)
        for i in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                curr[i] = prev[i - 1] + 1
                if curr[i] > best:
                    best = curr[i]
        prev = curr
    return best


# ---------------------------------------------------------------------------
# DETECTORS — each takes (line_text, line_number, filepath) → list[Finding]
#
# CRITICAL DESIGN PRINCIPLE (from bounce #2):
#   Detect the SHAPE of the secret anywhere in the line.
#   Context (quotes, assignment, prose) is never a precondition.
#   A key pasted bare into a markdown doc is just as dangerous as one
#   in an assignment statement.
# ---------------------------------------------------------------------------

# Pattern: OpenAI keys — bare anywhere in the line.
# sk- or sk-proj- followed by 20+ alphanum/underscore/dash characters.
# No requirement about what precedes or follows it.
OPENAI_RE = re.compile(r"""(sk-(?:proj-)?[A-Za-z0-9_-]{20,})""")


def detect_openai(line: str, lineno: int, filepath: str) -> list:
    findings = []
    for m in OPENAI_RE.finditer(line):
        val = m.group(1)
        if not is_whitelisted(val):
            findings.append(Finding(
                file=filepath, line=lineno,
                detector="openai_key",
                matched=mask_value(val),
            ))
    return findings


# Pattern: AWS Access Key IDs — bare anywhere (AKIA + 16 uppercase alphanum)
AWS_ACCESS_KEY_RE = re.compile(r"""(AKIA[0-9A-Z]{16})""")


def detect_aws_access_key(line: str, lineno: int, filepath: str) -> list:
    findings = []
    for m in AWS_ACCESS_KEY_RE.finditer(line):
        val = m.group(1)
        if not is_whitelisted(val):
            findings.append(Finding(
                file=filepath, line=lineno,
                detector="aws_access_key",
                matched=mask_value(val),
            ))
    return findings


# Pattern: AWS Secret Keys (40-char base64-ish after known variable names)
# This one DOES require context because 40 chars of base64 is too generic.
AWS_SECRET_RE = re.compile(
    r"""(?:aws_secret_access_key|AWS_SECRET_ACCESS_KEY|secret_key)\s*[=:]\s*["']?([A-Za-z0-9/+=]{40,45})["']?""",
    re.IGNORECASE,
)


def detect_aws_secret(line: str, lineno: int, filepath: str) -> list:
    findings = []
    for m in AWS_SECRET_RE.finditer(line):
        val = m.group(1)
        if not is_whitelisted(val):
            findings.append(Finding(
                file=filepath, line=lineno,
                detector="aws_secret_key",
                matched=mask_value(val),
            ))
    return findings


# Pattern: Google/GCP API keys — bare anywhere (AIzaSy + 33 chars)
GOOGLE_KEY_RE = re.compile(r"""(AIzaSy[A-Za-z0-9_-]{33})""")


def detect_google_key(line: str, lineno: int, filepath: str) -> list:
    findings = []
    for m in GOOGLE_KEY_RE.finditer(line):
        val = m.group(1)
        if not is_whitelisted(val):
            findings.append(Finding(
                file=filepath, line=lineno,
                detector="google_api_key",
                matched=mask_value(val),
            ))
    return findings


# Pattern: Anthropic keys — bare anywhere (sk-ant- + 20 chars)
ANTHROPIC_KEY_RE = re.compile(r"""(sk-ant-[A-Za-z0-9_-]{20,})""")


def detect_anthropic_key(line: str, lineno: int, filepath: str) -> list:
    findings = []
    for m in ANTHROPIC_KEY_RE.finditer(line):
        val = m.group(1)
        if not is_whitelisted(val):
            findings.append(Finding(
                file=filepath, line=lineno,
                detector="anthropic_key",
                matched=mask_value(val),
            ))
    return findings


# Pattern: Private key blocks
PRIVATE_KEY_RE = re.compile(r"-----BEGIN\s+(RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE KEY-----")


def detect_private_key(line: str, lineno: int, filepath: str) -> list:
    if PRIVATE_KEY_RE.search(line):
        return [Finding(
            file=filepath, line=lineno,
            detector="private_key_block",
            matched="-----BEGIN PRIVATE KEY-----",
        )]
    return []


# Pattern: High-entropy literal assigned to a name containing KEY/TOKEN/SECRET/PASSWORD.
# This one requires assignment context because it's the generic catch-all.
SENSITIVE_ASSIGN_RE = re.compile(
    r"""(?:^|[\s,;(])([A-Za-z_]*(?:KEY|TOKEN|SECRET|PASSWORD|APIKEY|API_KEY)[A-Za-z_0-9]*)\s*[=:]\s*["']([^"']{16,})["']""",
    re.IGNORECASE,
)


def detect_high_entropy_secret(line: str, lineno: int, filepath: str) -> list:
    findings = []
    for m in SENSITIVE_ASSIGN_RE.finditer(line):
        var_name = m.group(1)
        val = m.group(2)
        if is_whitelisted(val):
            continue
        # Require meaningful entropy (> 3.5 bits/char for 16+ char strings)
        if shannon_entropy(val) < 3.5:
            continue
        # Skip environment variable reads
        if "os.environ" in line or "os.getenv" in line or "ENV[" in line:
            continue
        # Skip shell command substitutions
        if val.startswith("$(") or val.startswith("`"):
            continue
        # Skip cryptographic digests. A pure-hex string of exactly MD5/SHA-1/
        # SHA-256 length is a hash, not a credential — our tour_cache keys are
        # SHA-256 of the request and appear in SQL examples in the docs. No
        # provider's API key is pure lowercase hex at these lengths (AWS secret
        # keys are 40 chars but mixed-case base64-ish, not hex).
        #
        # This matters more than the noise it removes: on 2026-08-04 the tick
        # alarm fired six times on cache keys in CLICKUP_OFFLINE_QUEUE.md. An
        # alarm that cries wolf is one we learn to skip past, and this one has
        # to still be believed the day it catches something real.
        if len(val) in (32, 40, 64) and all(c in "0123456789abcdefABCDEF" for c in val):
            continue
        findings.append(Finding(
            file=filepath, line=lineno,
            detector="high_entropy_assignment",
            matched=f"{var_name}={mask_value(val)}",
        ))
    return findings


# Near-match detector: catches literals that are structurally identical to
# known secret types but lack whitelist markers.
LONG_LITERAL_RE = re.compile(r"""["']([A-Za-z0-9_/+=.{}\[\]-]{30,})["']""")


def detect_near_match_by_structure(line: str, lineno: int, filepath: str) -> list:
    """Detect literals that look structurally like known secret types but
    lack the whitelist markers that would make them obviously fake."""
    findings = []
    for m in LONG_LITERAL_RE.finditer(line):
        val = m.group(1)
        # Must match a known secret prefix
        if not val.startswith("sk-proj-") and not val.startswith("sk-") \
                and not val.startswith("AKIA"):
            continue
        # Must be in the length range of known secrets
        if len(val) not in KNOWN_SECRET_LENGTHS:
            continue
        # Must have high entropy (real-looking)
        if shannon_entropy(val) < 4.0:
            continue
        # If it contains obvious fake markers, it's fine
        if is_whitelisted(val):
            continue
        findings.append(Finding(
            file=filepath, line=lineno,
            detector="near_match_secret",
            matched=mask_value(val),
        ))
    return findings


# All detectors in priority order
DETECTORS = [
    detect_openai,
    detect_aws_access_key,
    detect_aws_secret,
    detect_google_key,
    detect_anthropic_key,
    detect_private_key,
    detect_high_entropy_secret,
    detect_near_match_by_structure,
]


# ---------------------------------------------------------------------------
# Scanning logic
# ---------------------------------------------------------------------------


def scan_content(content: str, filepath: str) -> list:
    """Scan a string of file content, return findings."""
    findings = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        for detector in DETECTORS:
            findings.extend(detector(line, lineno, filepath))
    return findings


def should_skip_file(filepath: str) -> bool:
    """Return True if this file should be skipped."""
    p = Path(filepath)
    if p.suffix.lower() in SKIP_EXTENSIONS:
        return True
    for part in p.parts:
        if part in SKIP_DIRS:
            return True
    # Skip .env files (they're supposed to have secrets)
    if p.name == ".env" or p.name.startswith(".env."):
        return True
    # Skip allowlisted files (test fixtures, scanner itself)
    normalized = str(p).replace("\\", "/")
    if normalized in ALLOWLISTED_FILES:
        return True
    return False


def scan_tree(root: str = ".") -> list:
    """Scan the entire working tree."""
    findings = []
    root_path = Path(root).resolve()
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Prune skipped directories
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            filepath = Path(dirpath) / fname
            rel_path = str(filepath.relative_to(root_path))
            if should_skip_file(rel_path):
                continue
            try:
                content = filepath.read_text(errors="ignore")
            except (OSError, PermissionError):
                continue
            findings.extend(scan_content(content, rel_path))
    return findings


def scan_staged() -> list:
    """Scan currently staged files."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Error: git diff failed: {result.stderr}", file=sys.stderr)
        sys.exit(2)
    findings = []
    for filepath in result.stdout.strip().splitlines():
        if not filepath or should_skip_file(filepath):
            continue
        # Get the staged content
        show_result = subprocess.run(
            ["git", "show", f":{filepath}"],
            capture_output=True, text=True,
        )
        if show_result.returncode == 0:
            findings.extend(scan_content(show_result.stdout, filepath))
    return findings


def _scan_commit(commit_hash: str, commit_date: str) -> list:
    """Scan all files touched in a single commit, return findings."""
    diff_result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "-r", "--name-only",
         "--diff-filter=ACMR", "--root", commit_hash],
        capture_output=True, text=True,
    )
    if diff_result.returncode != 0:
        return []

    findings = []
    for filepath in diff_result.stdout.strip().splitlines():
        if not filepath or should_skip_file(filepath):
            continue
        try:
            show_result = subprocess.run(
                ["git", "show", f"{commit_hash}:{filepath}"],
                capture_output=True,
            )
            if show_result.returncode != 0:
                continue
            try:
                content = show_result.stdout.decode("utf-8", errors="ignore")
            except Exception:
                continue
        except Exception:
            continue
        file_findings = scan_content(content, filepath)
        for f in file_findings:
            f.commit = commit_hash[:10]
            f.date = commit_date[:10]
        findings.extend(file_findings)
    return findings


def scan_range(commit_range: str) -> list:
    """Scan all file versions touched in a commit range.

    Handles the edge case where the left side of A..B is a root commit
    (has no parent). In git, A..B excludes A itself, so if A is the root
    commit where a secret was introduced, it would be missed. We detect
    this and include the left-side commit explicitly.
    """
    result = subprocess.run(
        ["git", "log", "--pretty=format:%H %aI", "--root", commit_range],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Error: git log failed: {result.stderr}", file=sys.stderr)
        sys.exit(2)

    findings = []

    # If range is A..B format, check if A is a root commit and include it.
    if ".." in commit_range and not commit_range.startswith(".."):
        left_ref = commit_range.split("..")[0]
        # Resolve the ref to a hash
        resolve = subprocess.run(
            ["git", "rev-parse", left_ref],
            capture_output=True, text=True,
        )
        if resolve.returncode == 0:
            left_hash = resolve.stdout.strip()
            # Check if this commit has parents
            parents = subprocess.run(
                ["git", "rev-parse", f"{left_hash}^"],
                capture_output=True, text=True,
            )
            if parents.returncode != 0:
                # It's a root commit — include it in the scan
                date_result = subprocess.run(
                    ["git", "log", "-1", "--pretty=format:%aI", left_hash],
                    capture_output=True, text=True,
                )
                commit_date = date_result.stdout.strip()[:10] if date_result.returncode == 0 else "unknown"
                findings.extend(_scan_commit(left_hash, commit_date))

    for log_line in result.stdout.strip().splitlines():
        if not log_line:
            continue
        parts = log_line.split(" ", 1)
        commit_hash = parts[0]
        commit_date = parts[1][:10] if len(parts) > 1 else "unknown"
        findings.extend(_scan_commit(commit_hash, commit_date))
    return findings


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def format_findings(findings: list, json_output: bool = False) -> str:
    """Format findings for display."""
    if not findings:
        return "No secrets detected."

    if json_output:
        import json
        return json.dumps([
            {
                "file": f.file,
                "line": f.line,
                "detector": f.detector,
                "matched": f.matched,
                "commit": f.commit,
                "date": f.date,
            }
            for f in findings
        ], indent=2)

    lines = []
    lines.append(f"⚠️  {len(findings)} potential secret(s) detected:\n")
    for f in findings:
        loc = f"{f.file}:{f.line}"
        if f.commit:
            loc = f"{f.commit} {f.date} {loc}"
        lines.append(f"  [{f.detector}] {loc}")
        lines.append(f"    → {f.matched}")
        lines.append("")
    return "\n".join(lines)


def deduplicate_findings(findings: list) -> list:
    """Remove duplicate findings (same file+line+detector across commits)."""
    seen = set()
    deduped = []
    for f in findings:
        key = (f.file, f.line, f.detector, f.matched)
        if key not in seen:
            seen.add(key)
            deduped.append(f)
    return deduped


def main():
    parser = argparse.ArgumentParser(
        description="Scan for hardcoded secrets in the repository.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true",
                      help="Scan staged files (pre-commit hook)")
    mode.add_argument("--range", metavar="A..B",
                      help="Scan commits in a range")
    mode.add_argument("--tree", action="store_true",
                      help="Scan the entire working tree")
    parser.add_argument("--json", action="store_true",
                        help="Output in JSON format")
    args = parser.parse_args()

    if args.staged:
        findings = scan_staged()
    elif args.range:
        findings = scan_range(args.range)
    elif args.tree:
        findings = scan_tree()
    else:
        parser.print_help()
        sys.exit(2)

    output = format_findings(findings, json_output=args.json)
    print(output)

    if findings:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
