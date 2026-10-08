"""
LOCAL-624: Narration splices on new venues.

Two defects shipped on the 2026-10-08 Statens Museum for Kunst run (tour 470):

  Stop 1, "In a Roman Osteria" by Carl Bloch — the ARTIST was given an
  appositive that describes the WORK:
    "...commissioned Carl Bloch, an oil-on-canvas painting by Bloch, to create
     a painting..."
    "Bloch, an intensified version of Marstrand's painting, reached a pivotal
     moment in his career..."

  Stop 2, "View from the Artist's Window" — a sentence lost its object:
    "...faithfully rendered in oil with the meticulous attention to detail
     that characterized."

Root cause (proven by replay in scratch/replay_624.py):
  1. unglossed_reference_gate Stage 3a corpus-first (_search_corpus_for_fact)
     returned the painting's OWN record as the raw fact for the PERSON Carl
     Bloch — the artist appears in it only as "...by Carl Bloch" — and that was
     composed into a work-description appositive and spliced after the name.
     None of the five mechanical guards checked entity-type vs gloss-type.
  2. The degrade path (_excise_governed_construction) removed "the Danish
     Golden Age" — the object of the transitive verb "characterized" — leaving
     "...that characterized." None of the degrade guards tested the END of the
     clause.

These tests assert the fixes on the EXACT 470 sentences, plus the owner's other
dangling-clause example forms, and guard against false positives.

Pure — no network, no API key.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import unglossed_reference_gate as urg


# ── Deliverable 1: a gloss must match the entity's type ────────────────────────

# The exact appositives the 470 run spliced onto the person Carl Bloch.
BLOCH_HOST = (
    "In 1866, Moritz G. Melchior, a Danish merchant known for his interest in "
    "art, commissioned Carl Bloch to create a painting that would capture the "
    "essence of a lively Roman tavern."
)
BLOCH_WORK_GLOSSES = [
    "an oil-on-canvas painting by Bloch",
    "an intensified version of Marstrand's painting",
]


def test_person_rejects_work_description_gloss_exact_470():
    """The two 470 glosses must be rejected when the entity is a PERSON."""
    for gloss in BLOCH_WORK_GLOSSES:
        passed, reason = urg.validate_gloss(
            gloss, BLOCH_HOST, "Carl Bloch", category="person")
        assert not passed, f"work-description gloss must fail for a person: {gloss!r}"
        assert reason == "type_mismatch_work_for_person", reason


def test_person_accepts_a_personhood_gloss():
    """A legitimate person gloss (a painter, not a painting) still passes."""
    for gloss in [
        "a Danish painter renowned for his technical skill",
        "a nineteenth-century history painter",
        "an artist known for his evocative compositions",
    ]:
        passed, reason = urg.validate_gloss(
            gloss, BLOCH_HOST, "Carl Bloch", category="person")
        assert passed, f"legitimate person gloss wrongly rejected ({reason}): {gloss!r}"


def test_work_entity_may_be_described_as_a_painting():
    """A WORK entity legitimately described as a painting must NOT be blocked."""
    host = "You are standing before In a Roman Osteria."
    passed, reason = urg.validate_gloss(
        "an oil-on-canvas painting from 1866", host,
        "In a Roman Osteria", category="work")
    assert passed, f"work-as-painting wrongly rejected: {reason}"


def test_corpus_first_rejects_work_record_for_a_person():
    """Stage 3a must not hand a person the painting's own record as their fact.

    The stop corpus holds the painting's record; the artist appears in it only
    as "...by Carl Bloch". For a PERSON entity the corpus-first search must
    return None (fall through to model/degrade), while for the WORK entity it
    still returns the fact.
    """
    painting_record = [
        "In a Roman Osteria is an oil-on-canvas painting by Carl Bloch, created "
        "in 1866. It is an intensified version of Marstrand's painting of a "
        "similar subject.",
    ]
    assert urg._search_corpus_for_fact(
        "Carl Bloch", painting_record, category="person") is None
    assert urg._search_corpus_for_fact(
        "Bloch", painting_record, category="person") is None
    # The work entity still gets its fact.
    fact = urg._search_corpus_for_fact(
        "In a Roman Osteria", painting_record, category="work")
    assert fact and "painting" in fact.lower()


def test_full_splice_is_not_shipped_end_to_end():
    """Compose+insert the work gloss, then validate: the splice must be rejected.

    Reproduces the delivered-text shape and asserts the gate would drop the
    gloss (degrade the name) rather than ship it.
    """
    spliced = urg._insert_composed_gloss(
        BLOCH_HOST, "Carl Bloch", "an oil-on-canvas painting by Bloch")
    # The spliced string is exactly the delivered defect shape.
    assert "Carl Bloch, an oil-on-canvas painting by Bloch," in spliced
    # And the guard rejects that gloss for the person.
    passed, reason = urg.validate_gloss(
        "an oil-on-canvas painting by Bloch", BLOCH_HOST,
        "Carl Bloch", category="person")
    assert not passed and reason == "type_mismatch_work_for_person"


def test_earlier_tour_454_van_ruisdael_same_class():
    """The same person-glossed-as-work class appeared earlier in tour 454:
        "...a time when van Ruisdael, the 1665 Baroque landscape painting, was
         working..."
    The person van Ruisdael must not receive the work's description.
    """
    host = ("The painting before you is oil on canvas, created around "
            "1670-1675, a time when van Ruisdael was working at the height of "
            "his powers.")
    passed, reason = urg.validate_gloss(
        "the 1665 Baroque landscape painting", host, "van Ruisdael",
        category="person")
    assert not passed and reason == "type_mismatch_work_for_person"


def test_role_phrase_glosses_are_not_blocked():
    """Precision: a person gloss that merely NAMES an art form in a role phrase
    must NOT be rejected — over-blocking a real artist gloss is the same family
    of damage as the splice.
    """
    host = "This work was created by the master himself."
    for gloss in [
        "a prominent figure in the Hudson River School of painting",
        "a master of landscape painting",
        "a pioneer of abstract sculpture",
        "an engraver and painter of religious scenes",
        "a Danish merchant known for his interest in art",
    ]:
        passed, reason = urg.validate_gloss(gloss, host, "Someone",
                                            category="person")
        assert passed, f"role-phrase person gloss wrongly rejected ({reason}): {gloss!r}"


# ── Deliverable 2: no truncated clauses ────────────────────────────────────────

# The exact 470 Stop 2 truncation.
TRUNCATED_470 = (
    "Rorbye's childhood home at Amaliegade 45 in Copenhagen provides the scene, "
    "faithfully rendered in oil with the meticulous attention to detail that "
    "characterized."
)


def test_truncated_clause_exact_470_is_illformed():
    assert not urg._degrade_sentence_is_wellformed(TRUNCATED_470)


def test_truncated_clause_exact_470_dropped_by_final_net():
    repaired, dropped = urg.validate_and_repair_full_text(TRUNCATED_470)
    assert dropped, "the truncated 470 sentence must be dropped by the final net"
    assert "that characterized." not in repaired


def test_degrade_at_source_drops_the_truncated_sentence():
    """Fix at source: removing the object of 'characterized' drops the sentence
    rather than emitting '...that characterized.'"""
    original = (
        "Rorbye's childhood home at Amaliegade 45 in Copenhagen provides the "
        "scene, faithfully rendered in oil with the meticulous attention to "
        "detail that characterized the Danish Golden Age."
    )
    out = urg._degrade_reference_in_text(original, "Danish Golden Age", original)
    assert out.strip() == "", f"truncation must be dropped at source, got: {out!r}"


def test_other_dangling_forms_are_illformed():
    for s in [
        "The technique, which revealed.",
        "a tradition that shaped.",
        "the influence that shaped.",
        "In this painting, stands .",
        "In this painting, stands.",
    ]:
        assert not urg._degrade_sentence_is_wellformed(s), f"should be ill-formed: {s!r}"


def test_stranded_bare_object_live_473_is_illformed():
    """The 2026-10-08 Wallraf-Richartz live run (tour 473) shipped a stranded
    bare object — the degrade cut the determiner off the object:
        "...in a trade with Theodor Fischer, an art dealer from Switzerland, to
         obtain painting."
    A transitive acquire/create verb welded onto a determiner-less work-noun is
    ill-formed and must be dropped."""
    s = ("In 1938, the museum deaccessioned the canvas in a trade with Theodor "
         "Fischer, an art dealer from Switzerland, to obtain painting.")
    assert not urg._degrade_sentence_is_wellformed(s)
    repaired, dropped = urg.validate_and_repair_full_text(s)
    assert dropped and "to obtain painting." not in repaired


def test_mass_noun_and_determined_object_survive():
    """Precision: a work-noun as a mass noun or with a determiner is well-formed."""
    for s in [
        "He devoted his life to religious painting.",
        "She was a master of landscape painting.",
        "The museum acquired the painting in 1938.",
        "The trade allowed the museum to obtain a van Gogh painting.",
        "He created a monumental sculpture.",
    ]:
        assert urg._degrade_sentence_is_wellformed(s), f"wrongly flagged: {s!r}"


def test_legitimate_sentences_survive():
    """False-positive guard — well-formed sentences must stay well-formed."""
    for s in [
        "The crowd gathered.",
        "The museum is open daily except Tuesday.",
        "Raphael painted the Holy Family with warmth and tenderness.",
        "This work, which he completed in 1866, hangs here.",
        "He studied under Eckersberg, who shaped Danish painting.",
        "The sculpture stands in the courtyard.",
    ]:
        assert urg._degrade_sentence_is_wellformed(s), f"wrongly flagged: {s!r}"


def test_validate_degrade_output_reports_truncated_clause():
    issues = urg.validate_degrade_output(TRUNCATED_470)
    guards = {i["guard"] for i in issues}
    assert "truncated_clause" in guards, issues


# ── Deliverable 3: a further class found by the scan — empty interpolated field ─

def test_empty_parenthetical_field_repaired_exact_469():
    """Tour 469 (Unterlinden) shipped '...pour les Musées (État / ), and private
    donors.' — a field interpolation left an empty parenthetical. Repair excises
    the broken parenthetical and keeps the real funding story."""
    text = ("This addition was made possible through the Fonds Régional "
            "d'Acquisition pour les Musées (État / ), and private donors.")
    repaired, _ = urg.validate_and_repair_full_text(text)
    assert "(État / )" not in repaired and "( /" not in repaired
    assert "private donors" in repaired  # the real content survives


def test_legitimate_parentheticals_preserved():
    for s in [
        "Schongauer, a master engraver born in Colmar (around 1445), crafted this.",
        "the Isenheim Altarpiece (1512-1516) remains a symbol.",
        "the museum (open daily except Tuesday) welcomes visitors.",
    ]:
        repaired, _ = urg.validate_and_repair_full_text(s)
        assert repaired.strip() == s.strip(), f"legit parenthetical changed: {repaired!r}"


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
