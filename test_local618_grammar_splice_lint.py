"""
LOCAL-618 #2: Deterministic grammar & splice lint on final spoken text.

The critic's Sevilla runs shipped garbled clauses — "Gertrud Dübi…-Müller first
came into the world" (ellipsis-hyphen splice), verbless fragments, a stray
opening quote. flag_sentence detects four defect classes; grammar_splice_lint
drops the flagged sentence or hands exactly one to a metered LLM rewrite.

Pure (rewrite_fn injected / absent).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spoken_text_hygiene import flag_sentence, grammar_splice_lint


def test_splice_flagged():
    assert 'splice' in flag_sentence("Gertrud Dübi\u2026-Müller first came into the world.")
    assert 'splice' in flag_sentence("The text ...-and the image blur together.")


def test_unbalanced_quote_flagged():
    assert 'unbalanced' in flag_sentence('He said "this is the finest work in the room.')
    assert 'unbalanced' in flag_sentence("The painting (an oil on canvas is remarkable.")


def test_verbless_flagged():
    assert 'verbless' in flag_sentence("A large oil painting of a saint in a gold frame.")


def test_verbless_short_sentence_exempt():
    # Short pointer / label phrases legitimately lack a finite verb.
    assert 'verbless' not in flag_sentence("The Night Watch.")


def test_repeated_pair_flagged():
    assert 'repeated_pair' in flag_sentence("She came into came into the world in 1888.")
    assert 'repeated_pair' in flag_sentence("The the painting hangs here.")


def test_clean_sentence_not_flagged():
    assert flag_sentence("Murillo painted this Virgin in 1678 for the convent.") == []


def test_lint_drops_flagged_sentence_without_rewrite():
    text = (
        "Murillo painted this Virgin in 1678. "
        "Gertrud Dübi\u2026-Müller first came into the world. "
        "The convent cook kept the napkin."
    )
    cleaned, rep = grammar_splice_lint(text)  # no rewrite_fn
    assert rep['flagged'] == 1 and rep['dropped'] == 1 and rep['rewritten'] == 0
    assert "D\u00fcbi" not in cleaned, f"spliced sentence must be dropped: {cleaned}"
    assert "Murillo painted this Virgin in 1678." in cleaned
    assert "The convent cook kept the napkin." in cleaned


def test_lint_uses_single_metered_rewrite():
    calls = {"n": 0}
    def rewrite(sentence):
        calls["n"] += 1
        return "Gertrud D\u00fcbi-M\u00fcller was born in 1888."
    text = (
        "Murillo painted this Virgin in 1678. "
        "Gertrud Dübi\u2026-Müller first came into the world. "
        "A large oil painting of a saint in a gold frame."
    )
    cleaned, rep = grammar_splice_lint(text, rewrite_fn=rewrite)
    # Two sentences flagged, but the rewrite is used at most ONCE (metered).
    assert rep['flagged'] == 2
    assert calls["n"] == 1, "rewrite_fn must be called at most once"
    assert rep['rewritten'] == 1
    assert "Gertrud D\u00fcbi-M\u00fcller was born in 1888." in cleaned
    # The second flagged (verbless) sentence is dropped, not rewritten.
    assert rep['dropped'] == 1


def test_lint_never_empties_paragraph():
    text = "A saint in a gold frame."  # single short-but-5+word-less? ensure non-empty
    cleaned, rep = grammar_splice_lint(text)
    assert cleaned.strip(), "must not ship an empty paragraph"


def test_rewrite_failure_falls_back_to_drop():
    def rewrite(sentence):
        return ""  # rewrite failed
    text = ("Murillo painted this Virgin in 1678. "
            "Gertrud Dübi\u2026-Müller first came into the world.")
    cleaned, rep = grammar_splice_lint(text, rewrite_fn=rewrite)
    assert rep['dropped'] == 1 and rep['rewritten'] == 0
    assert "D\u00fcbi" not in cleaned


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  [PASS] {fn.__name__}"); passed += 1
        except Exception:
            print(f"  [FAIL] {fn.__name__}"); traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
