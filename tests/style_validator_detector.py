#!/usr/bin/env python3
"""style_validator_detector.py — SHIM (LOCAL-192)

The canonical implementation now lives at the REPO ROOT:
  /style_validator_detector.py

This shim re-exports everything so that existing test scripts using
  from style_validator_detector import validate_paragraph
continue to work unchanged when tests/ is on sys.path.
"""
import sys
import os
import importlib.util

# Load the canonical module from repo root by absolute path to avoid
# circular import when running from within tests/ directory.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CANONICAL_PATH = os.path.join(_REPO_ROOT, 'style_validator_detector.py')

_spec = importlib.util.spec_from_file_location("_style_validator_canonical", _CANONICAL_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Re-export EVERYTHING the canonical module defines.
#
# This used to be a hand-written list, and it cost us twice: R10 shipped and
# was invisible to anything importing through this shim, because nobody
# remembered to add `apply_r10_to_description` and `check_r10_unfulfilled_promise`
# to the list. LOCAL-241's generation silently fell back to post-processing for
# exactly that reason (D135).
#
# A shim that has to be maintained in step with the module it forwards is a
# shim that will drift. Forward dynamically instead.
for _name in dir(_mod):
    if not _name.startswith('__'):
        globals()[_name] = getattr(_mod, _name)

del _name
