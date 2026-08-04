"""
This module used to hold an OpenAI key as a literal — "designed to keep the
openai private key hidden", which it did not. The full key was committed on
2025-10-26 and has been on origin ever since. Nothing in the codebase imports
this module.

Redacted 2026-08-04 (see DECISIONS.md D81). The key value remains in git
history; removing it there needs a force-push, which is Michael's call. The
key itself must be rotated regardless — redacting the tip does not un-expose
something that has been public in the repository for nine months.
"""
import os

MY_SK = os.environ["OPENAI_API_KEY"]
MY_SK_1 = MY_SK
