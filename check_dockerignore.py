#!/usr/bin/env python3
"""
check_dockerignore.py — Verify that every COPY source in every Dockerfile
survives the .dockerignore exclusion rules.

Background: LOCAL-64 found that `*.txt` hid requirements files and
`build_*.py` hid build_manifest.py, causing build failures. This script
prevents that class of bug permanently.

Designed to run in pre-push hook / CI. Exit code 0 = all clear.
Exit code 1 = at least one COPY source is excluded by .dockerignore.

Usage:
    python check_dockerignore.py           # check all Dockerfiles in repo
    python check_dockerignore.py --ci      # same, for CI (outputs summary)
"""

import os
import re
import sys
import glob as globmod
from pathlib import Path
from typing import List, Tuple


def parse_dockerignore(dockerignore_path: str) -> Tuple[List[str], List[str]]:
    """Parse .dockerignore into (exclude_patterns, exception_patterns).
    
    Returns two lists:
        excludes: patterns that EXCLUDE files (lines without ! prefix)
        exceptions: patterns that RE-INCLUDE files (lines with ! prefix, stripped)
    """
    excludes = []
    exceptions = []
    
    if not os.path.exists(dockerignore_path):
        return excludes, exceptions
    
    with open(dockerignore_path, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            if line.startswith('!'):
                exceptions.append(line[1:])  # Remove the ! prefix
            else:
                excludes.append(line)
    
    return excludes, exceptions


def _pattern_matches(pattern: str, path: str) -> bool:
    """Check if a .dockerignore pattern matches a given path.
    
    Simplified matching that handles the patterns actually found in this project:
    - *.ext (matches any file with that extension)
    - prefix_*.ext (matches files starting with prefix_)
    - directory/ (matches a directory name)
    - **/ patterns
    """
    import fnmatch
    
    # Normalize: remove trailing /
    pattern_clean = pattern.rstrip('/')
    path_clean = path.rstrip('/')
    
    # Direct fnmatch on basename
    basename = os.path.basename(path_clean)
    
    # If pattern has no directory separator, match against basename only
    if '/' not in pattern_clean and '**' not in pattern_clean:
        return fnmatch.fnmatch(basename, pattern_clean)
    
    # Pattern with directory — match against full path
    # Handle ** globstar
    if '**' in pattern_clean:
        # Replace ** with wildcard for fnmatch
        regex_pattern = pattern_clean.replace('**/', '').replace('/**', '')
        return fnmatch.fnmatch(basename, regex_pattern) or fnmatch.fnmatch(path_clean, pattern_clean)
    
    # Direct directory match
    return fnmatch.fnmatch(path_clean, pattern_clean) or fnmatch.fnmatch(basename, pattern_clean)


def is_excluded_by_dockerignore(file_path: str, excludes: List[str], exceptions: List[str]) -> Tuple[bool, str]:
    """Check if a file would be excluded by .dockerignore rules.
    
    Docker's logic: a file is excluded if it matches any exclude pattern
    UNLESS it also matches a later exception pattern.
    
    Returns: (excluded: bool, matched_pattern: str or "")
    """
    excluded = False
    matched_pattern = ""
    
    for pattern in excludes:
        if _pattern_matches(pattern, file_path):
            excluded = True
            matched_pattern = pattern
    
    if excluded:
        # Check if any exception re-includes it
        for exception in exceptions:
            if _pattern_matches(exception, file_path):
                excluded = False
                matched_pattern = ""
                break
    
    return excluded, matched_pattern


def extract_copy_sources(dockerfile_path: str) -> List[str]:
    """Extract all COPY source paths from a Dockerfile.
    
    Handles:
        COPY file.py /app/
        COPY *.py /app/
        COPY dir/ /app/dir/
        COPY --from=builder /app /app  (skipped — multi-stage)
    """
    sources = []
    
    with open(dockerfile_path, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            
            # Match COPY instructions
            match = re.match(r'^COPY\s+(.+)$', line, re.IGNORECASE)
            if not match:
                continue
            
            args = match.group(1).strip()
            
            # Skip multi-stage COPY (--from=...)
            if args.startswith('--from') or args.startswith('--chown'):
                # Still need to parse the actual source after the flag
                args = re.sub(r'--\w+=[^\s]+\s*', '', args)
            
            # Split into source(s) and destination
            # The last token is always the destination
            tokens = args.split()
            if len(tokens) < 2:
                continue
            
            # Everything except the last token is a source
            for src in tokens[:-1]:
                # Skip absolute paths (not from build context)
                if src.startswith('/'):
                    continue
                sources.append(src)
    
    return sources


def resolve_copy_source(source: str, context_dir: str) -> List[str]:
    """Resolve a COPY source pattern to actual files in the build context.
    
    Returns list of relative file paths that the pattern would match.
    For wildcards, expand them against the filesystem.
    For directories, just return the directory name.
    """
    # If it's a wildcard, expand it
    if '*' in source or '?' in source:
        full_pattern = os.path.join(context_dir, source)
        matches = globmod.glob(full_pattern)
        return [os.path.relpath(m, context_dir) for m in matches]
    
    # If it's a specific file or directory
    full_path = os.path.join(context_dir, source)
    if os.path.exists(full_path):
        return [source]
    
    # Doesn't exist — still report it (might be generated during build)
    return [source]


def check_dockerfile(dockerfile_path: str, context_dir: str, excludes: List[str], exceptions: List[str]) -> List[dict]:
    """Check one Dockerfile for COPY sources excluded by .dockerignore.
    
    Only reports violations for EXPLICIT file names (not wildcards).
    When a COPY uses a wildcard like `*.py`, .dockerignore is the intended
    filter — that's not a bug. But when a COPY names a specific file like
    `COPY cleanup_newsletter_simple.py /app/`, and .dockerignore excludes
    it, that's a real build-breaking bug.
    
    Returns list of violation dicts: {source, pattern, dockerfile}
    """
    violations = []
    sources = extract_copy_sources(dockerfile_path)
    
    for source in sources:
        # Skip wildcard COPY patterns — .dockerignore is the intended filter
        if '*' in source or '?' in source:
            continue
        
        # Only check explicit file/directory names
        file_path = source
        excluded, matched_pattern = is_excluded_by_dockerignore(file_path, excludes, exceptions)
        if excluded:
            violations.append({
                "dockerfile": os.path.relpath(dockerfile_path, context_dir),
                "source": file_path,
                "copy_pattern": source,
                "excluded_by": matched_pattern,
            })
    
    return violations


def find_all_dockerfiles(repo_root: str) -> List[str]:
    """Find all Dockerfiles in the repository."""
    dockerfiles = []
    
    for root, dirs, files in os.walk(repo_root):
        # Skip .git and other hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for f in files:
            if f == 'Dockerfile' or f.startswith('Dockerfile.'):
                dockerfiles.append(os.path.join(root, f))
    
    return sorted(dockerfiles)


def main():
    """Run the .dockerignore checker against all Dockerfiles."""
    repo_root = os.path.dirname(os.path.abspath(__file__))
    ci_mode = '--ci' in sys.argv
    
    dockerignore_path = os.path.join(repo_root, '.dockerignore')
    excludes, exceptions = parse_dockerignore(dockerignore_path)
    
    if not excludes:
        print("No .dockerignore found or it's empty — nothing to check.")
        sys.exit(0)
    
    dockerfiles = find_all_dockerfiles(repo_root)
    
    if not dockerfiles:
        print("No Dockerfiles found.")
        sys.exit(0)
    
    print(f"{'=' * 70}")
    print(f"  .dockerignore COPY-source checker")
    print(f"  Dockerfiles found: {len(dockerfiles)}")
    print(f"  Exclude patterns: {len(excludes)}, Exception patterns: {len(exceptions)}")
    print(f"{'=' * 70}")
    print()
    
    all_violations = []
    results_table = []
    
    for df_path in dockerfiles:
        # Determine context dir (where docker build runs from)
        # For Dockerfiles in subdirectories, the context is that subdirectory
        df_dir = os.path.dirname(df_path)
        
        # Root-level Dockerfiles (Dockerfile.*) use repo root as context
        # Subdirectory Dockerfiles may use their own .dockerignore or repo's
        if df_dir == repo_root or df_path.startswith(repo_root + '/Dockerfile'):
            context_dir = repo_root
        else:
            context_dir = df_dir
        
        # Only check against the root .dockerignore for root-context builds
        if context_dir != repo_root:
            # Subdirectory Dockerfiles typically don't use the root .dockerignore
            results_table.append({
                "dockerfile": os.path.relpath(df_path, repo_root),
                "status": "SKIP",
                "detail": "sub-directory context (own .dockerignore scope)",
            })
            continue
        
        violations = check_dockerfile(df_path, context_dir, excludes, exceptions)
        
        df_rel = os.path.relpath(df_path, repo_root)
        if violations:
            all_violations.extend(violations)
            results_table.append({
                "dockerfile": df_rel,
                "status": "FAIL",
                "detail": f"{len(violations)} source(s) excluded",
            })
        else:
            results_table.append({
                "dockerfile": df_rel,
                "status": "PASS",
                "detail": "",
            })
    
    # Print results table
    print(f"{'Dockerfile':<45} {'Status':<8} {'Detail'}")
    print(f"{'-' * 45} {'-' * 8} {'-' * 30}")
    for row in results_table:
        print(f"{row['dockerfile']:<45} {row['status']:<8} {row['detail']}")
    
    print()
    
    if all_violations:
        print(f"{'!' * 70}")
        print(f"  FAILURES: {len(all_violations)} COPY source(s) hidden by .dockerignore")
        print(f"{'!' * 70}")
        print()
        for v in all_violations:
            print(f"  Dockerfile: {v['dockerfile']}")
            print(f"  COPY source: {v['source']} (from pattern '{v['copy_pattern']}')")
            print(f"  Excluded by: {v['excluded_by']}")
            print()
        
        if ci_mode:
            print("EXIT 1 — fix .dockerignore or update COPY instructions.")
        sys.exit(1)
    else:
        print(f"ALL CLEAR: Every COPY source survives .dockerignore.")
        sys.exit(0)


if __name__ == "__main__":
    main()
