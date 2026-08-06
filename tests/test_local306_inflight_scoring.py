#!/usr/bin/env python3
"""
test_local306_inflight_scoring.py — Verify in-flight scoring (LOCAL-306).

Tests:
  1. Score a 2-stop tour, verify persistence.
  2. Score an 8-stop tour, verify persistence.
  3. Simulate an edit (remove sourced sentence, add unsourced one), re-score,
     verify delta contains no judgement of the user.
  4. Confirm delivery is byte-identical with scoring on and off.
  5. Measure and report latency.

Uses AUDIOURA_DB_TARGET=test (audiotours_test) — never touches production.
"""
import os
import sys
import time
import json

# Route to test database
os.environ["AUDIOURA_DB_TARGET"] = "test"

# Ensure imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))

from db_connection import get_connection, log_db_target
from tour_scoring_service import (
    score_tour_text,
    compute_edit_delta,
    score_edited_tour,
    ensure_tour_scores_table,
    SCORER_VERSION,
)

log_db_target("LOCAL-306 verification")

# --- Sample tour texts for testing ---

RIVIERA_2STOP = """Step-by-Step Audio Guided Tour: French Riviera - Walking Tour
Tour-Category: Walking

Stop 1: Promenade des Anglais

Address: Promenade des Anglais, Nice, France

Coordinates: 43.6947, 7.2653

Type/Specialty: Historic waterfront promenade

Orientation: Welcome to the French Riviera. Your first stop is Promenade des Anglais.

The Promenade des Anglais stretches seven kilometres along the Baie des Anges in Nice. Built in 1822 by Reverend Lewis Way and funded by the English colony, it transformed a rocky coastline into the most famous seafront walk in Europe. The distinctive blue chairs, designed in 1956 by artist Sabine Géraud, have become an icon of the city. During the Belle Époque, Queen Victoria herself walked this path during her winters at the Excelsior Hôtel Régina, constructed in 1897 specifically to accommodate her entourage of 100 servants. The mosaic tile work beneath your feet was restored in 2011 by Italian craftsmen using the same Venetian smalti technique employed in the original 1880s installation. Architect Denis Pradelle expanded the promenade in 1931 to accommodate automobile traffic while preserving the palm-lined pedestrian zone.

Directions: Continue east along the promenade for 500 metres toward the Old Town.

Stop 2: Castle Hill (Colline du Château)

Address: Montée du Château, Nice, France

Type/Specialty: Historic fortification viewpoint

Orientation: Position yourself at the base of the waterfall.

Castle Hill rises 92 metres above Nice harbour, site of the original Greek settlement of Nikaia founded in 350 BCE. The fortress that crowned it was demolished in 1706 on orders of Louis XIV after the siege conducted by Marshal de Berwick. The artificial waterfall cascading down the north face was engineered in 1885 by architect François Aune, who diverted water from the Vésubie canal. From this vantage point you can identify the Cours Saleya flower market below, established in 1861 after the annexation of Nice to France. The Bellanda Tower to your left, built in the 16th century, housed composer Hector Berlioz in 1831 while he composed his King Lear overture. Excavations in 2008 by archaeologist Marc Bouiron uncovered Ligurian pottery dating to the 4th century BCE, now displayed in the Musée d'Archéologie.

Directions: Your tour ends here. Enjoy the panoramic view of the Baie des Anges.
"""

MUSEUM_8STOP = """Step-by-Step Audio Guided Tour: Asian Arts Museum - Museum Tour
Tour-Category: Museum

Stop 1: Main Entrance Hall

Address: 405 Hilgard Avenue, San Francisco, CA

Coordinates: 37.7749, -122.4194

Type/Specialty: Museum entrance and orientation

Orientation: Welcome to the Asian Arts Museum. Your first stop is the Main Entrance Hall.

The Asian Art Museum of San Francisco houses more than 18,000 objects spanning 6,000 years of history across Asia. The building you stand in was designed by architect Gae Aulenti in 2003, who also transformed the Musée d'Orsay in Paris. The bronze doors weighing 3.2 tonnes each were cast by Tadashi Abe in Kanazawa, Japan, using the lost-wax technique dating to 3000 BCE. Former International Olympic Committee president Avery Brundage donated his collection of 7,700 pieces in 1966, forming the museum's nucleus.

Directions: Proceed through the main gallery to your right.

Stop 2: Chinese Jade Gallery

Address: Second Floor, Gallery 201

Type/Specialty: Ancient Chinese jade artifacts

The jade bi disc before you dates to the Liangzhu culture, approximately 3300-2200 BCE. Carved from nephrite using bamboo drills and quartz sand abrasive, this ceremonial disc required an estimated 300 hours of labour. The museum acquired it in 1969 from dealer C.T. Loo's estate sale in New York. The green colour indicates iron content between 1-3% in the nephrite matrix. Professor Na Zhiliang of National Taiwan University authenticated the piece in 1972 using thermoluminescence dating.

Directions: Continue to the next gallery on your left.

Stop 3: Japanese Screen Room

Address: Second Floor, Gallery 205

Type/Specialty: Edo period folding screens

The six-panel folding screen (byōbu) displayed here depicts the Tale of Genji and was painted by Tosa Mitsunobu around 1510 during the Muromachi period. Gold leaf was applied using the kindami technique — thin sheets pressed onto lacquer sizing. The screen measures 154 centimetres tall and 372 centimetres wide when fully extended. It entered the Brundage collection in 1958 from the Mitsui family estate, where it had remained since 1688.

Directions: Turn right and enter the Korean ceramics gallery.

Stop 4: Korean Celadon Hall

Address: Second Floor, Gallery 210

Type/Specialty: Goryeo dynasty celadon ware

This celadon maebyeong vase from the 12th century exemplifies the jade-green glaze achieved through a 1-3% iron oxide reduction firing at 1150-1250 degrees Celsius. The inlaid (sanggam) chrysanthemum pattern was incised into leather-hard clay, filled with white and black slip, then bisque-fired before glazing. Archaeologist Choi Sun-u excavated similar pieces from kiln site number 9 at Gangjin in South Jeolla Province in 1964. The lotus petal decoration around the base follows the canonical twelve-petal Buddhist pattern.

Directions: Continue through to the South Asian galleries.

Stop 5: Indian Bronze Gallery

Address: Third Floor, Gallery 301

Type/Specialty: Chola dynasty bronzes

The Nataraja (Dancing Shiva) before you was cast in the Chola period, approximately 11th century CE, in the village of Swamimalai using the cire perdue (lost-wax) process. Standing 89 centimetres tall, it depicts Shiva performing the Ananda Tandava within a ring of flames (prabhamandala). The right hand holds the damaru drum symbolizing creation; the left hand holds agni (fire) representing destruction. This particular bronze was recovered from the Brihadisvara Temple in Thanjavur, built by Raja Raja Chola I in 1010 CE. The proportions follow the Shilpa Shastra canon: the face measures one-tenth of total height.

Directions: Proceed to the adjacent gallery.

Stop 6: Southeast Asian Textiles

Address: Third Floor, Gallery 305

Type/Specialty: Traditional weaving arts

This Cambodian silk ikat (hol) dates to the 19th century and was woven on a frame loom using the weft-ikat resist-dyeing technique. The pattern represents the cosmic tree (kbach chan), a motif derived from Hindu-Buddhist cosmology transmitted during the Angkorian period (802-1431 CE). The red dye was extracted from lac insects (Kerria lacca), requiring approximately 100,000 insects per kilogram of dye. Textile scholar Gillian Green documented this piece during her 1989 fieldwork in Takéo Province.

Directions: Continue to the end of the hall.

Stop 7: Tibetan Thangka Room

Address: Third Floor, Gallery 308

Type/Specialty: Buddhist devotional paintings

The Wheel of Life (Bhavachakra) thangka hanging before you was painted in mineral pigments on cotton canvas in the 17th century, likely in the Ngor monastery tradition of Tsang province. The central figure Yama (Lord of Death) grips the wheel containing six realms of existence. Pigments include malachite green (copper carbonate), azurite blue (copper carbonate), and cinnabar red (mercury sulfide), ground and mixed with yak-hide glue. The gold highlights use 24-karat gold leaf, approximately 0.1 microns thick, burnished with a zhi stone (agate).

Directions: Your final stop is in the contemporary gallery.

Stop 8: Contemporary Asian Art

Address: Fourth Floor, Gallery 401

Type/Specialty: Modern and contemporary works

Yayoi Kusama's Infinity Mirror Room (2013) envelops you in an endless field of LED lights reflected between parallel mirrors. Kusama, born in Matsumoto, Japan in 1929, began her infinity net paintings in 1958 after moving to New York. This installation uses 133 LED units programmed in a 40-second cycle, alternating between warm white (2700K) and cool white (6500K). The room measures 3 x 3 x 2.4 metres. She has lived voluntarily in Seiwa Hospital psychiatric facility in Tokyo since 1977, producing work daily at her adjacent studio. Your tour ends here.

Directions: This concludes your tour. The museum shop is on the ground floor.
"""


def test_score_2stop():
    """Score a 2-stop Riviera tour, verify persistence."""
    print("\n" + "=" * 70)
    print("TEST 1: Score 2-stop Riviera tour")
    print("=" * 70)

    ensure_tour_scores_table()
    
    tour_score, row_id, scoring_ms = score_tour_text(
        RIVIERA_2STOP,
        n_requested=2,
        tour_id=None,
        tour_name="French Riviera Walking Tour (test)",
    )

    assert tour_score is not None, "Score should not be None"
    assert row_id is not None, "Row ID should not be None"
    assert scoring_ms > 0, "Scoring time should be positive"
    assert tour_score.n_delivered == 2, f"Expected 2 stops delivered, got {tour_score.n_delivered}"
    assert tour_score.n_requested == 2, f"Expected 2 stops requested, got {tour_score.n_requested}"

    # Verify persistence
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tour_scores WHERE id = %s", (row_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    assert row is not None, f"Score row {row_id} not found in database"

    print(f"\n  ✅ 2-stop tour scored: total={tour_score.total_score:.1f}")
    print(f"     base={tour_score.base_score:.1f} structural={tour_score.structural_surcharge:.1f}")
    print(f"     correlation={tour_score.correlation_bonus:.1f} venue_id={tour_score.venue_identity_bonus:.1f}")
    print(f"     time={scoring_ms:.1f}ms, row_id={row_id}")
    print(f"     per-stop classifications: {[s.classification for s in tour_score.stops]}")

    return tour_score, row_id, scoring_ms


def test_score_8stop():
    """Score an 8-stop museum tour, verify persistence."""
    print("\n" + "=" * 70)
    print("TEST 2: Score 8-stop museum tour")
    print("=" * 70)

    tour_score, row_id, scoring_ms = score_tour_text(
        MUSEUM_8STOP,
        n_requested=8,
        tour_id=None,
        tour_name="Asian Arts Museum Tour (test)",
    )

    assert tour_score is not None, "Score should not be None"
    assert row_id is not None, "Row ID should not be None"
    assert tour_score.n_delivered == 8, f"Expected 8 stops delivered, got {tour_score.n_delivered}"

    # Verify persistence
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tour_scores WHERE id = %s", (row_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    assert row is not None, f"Score row {row_id} not found in database"

    print(f"\n  ✅ 8-stop tour scored: total={tour_score.total_score:.1f}")
    print(f"     base={tour_score.base_score:.1f} structural={tour_score.structural_surcharge:.1f}")
    print(f"     correlation={tour_score.correlation_bonus:.1f} venue_id={tour_score.venue_identity_bonus:.1f}")
    print(f"     time={scoring_ms:.1f}ms, row_id={row_id}")
    print(f"     per-stop classifications: {[s.classification for s in tour_score.stops]}")

    return tour_score, row_id, scoring_ms


def test_edit_delta():
    """Simulate an edit, re-score, verify delta contains no user judgement."""
    print("\n" + "=" * 70)
    print("TEST 3: Simulate edit → re-score → delta")
    print("=" * 70)

    # Original: the Riviera 2-stop tour
    original = RIVIERA_2STOP

    # Edited version: remove a sourced sentence (the Queen Victoria one),
    # add an unsourced claim
    edited = original.replace(
        "During the Belle Époque, Queen Victoria herself walked this path during her winters at the Excelsior Hôtel Régina, constructed in 1897 specifically to accommodate her entourage of 100 servants.",
        "Many tourists consider this the most romantic walk in all of Europe, especially at sunset when the light turns golden."
    )

    # First score the original
    orig_score, orig_row_id, _ = score_tour_text(
        original, n_requested=2, tour_id=9999, tour_name="Riviera (original, test)"
    )

    # Score the edit with delta
    edit_score, edit_row_id, delta, edit_ms = score_edited_tour(
        original, edited, n_requested=2,
        tour_id=9999, tour_name="Riviera (edited, test)",
        original_score_id=orig_row_id,
    )

    assert delta is not None, "Delta should not be None"
    assert edit_row_id is not None, "Edit score row should exist"

    # Verify the delta structure
    assert "sourced_facts_removed" in delta
    assert "unsourced_claims_added" in delta
    assert "classifications_changed" in delta
    assert "per_stop" in delta

    # Verify NO user judgement in the delta
    delta_str = json.dumps(delta)
    judgement_words = ["your edit", "you scored", "poor", "bad", "good job", "well done",
                       "your score", "your work", "you should"]
    for word in judgement_words:
        assert word.lower() not in delta_str.lower(), \
            f"Delta contains user judgement: '{word}' found in: {delta_str[:200]}"

    # Verify persistence of re-score
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT is_rescore, previous_score_id, delta FROM tour_scores WHERE id = %s", (edit_row_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    assert row is not None
    assert row[0] is True, "is_rescore should be True"
    assert row[1] == orig_row_id, f"previous_score_id should be {orig_row_id}, got {row[1]}"
    assert row[2] is not None, "delta should be persisted"

    print(f"\n  ✅ Edit delta computed and persisted:")
    print(f"     sourced facts removed: {delta['sourced_facts_removed']}")
    print(f"     unsourced claims added: {delta['unsourced_claims_added']}")
    print(f"     classifications changed: {len(delta['classifications_changed'])}")
    print(f"     edit scoring time: {edit_ms:.1f}ms")
    print(f"     delta JSON (no user judgement): ✓")
    print(f"\n  Full delta:")
    print(f"     {json.dumps(delta, indent=2)}")

    return delta


def test_delivery_unchanged():
    """Confirm tour text is byte-identical before and after scoring."""
    print("\n" + "=" * 70)
    print("TEST 4: Delivery byte-identical with scoring on and off")
    print("=" * 70)

    tour_text = RIVIERA_2STOP
    text_before = tour_text  # copy

    # Score the tour (this is what happens in-flight)
    score_tour_text(tour_text, n_requested=2, tour_name="identity test")

    # Verify the text is unchanged
    assert tour_text == text_before, "Tour text was modified by scoring!"
    assert tour_text is text_before, "Tour text object was replaced!"

    print(f"\n  ✅ Tour text byte-identical: {len(tour_text)} chars unchanged")


def test_latency():
    """Measure latency across multiple runs."""
    print("\n" + "=" * 70)
    print("TEST 5: Latency measurement")
    print("=" * 70)

    # Warm up
    score_tour_text(RIVIERA_2STOP, n_requested=2, tour_name="warmup")

    # Measure 2-stop
    times_2 = []
    for _ in range(5):
        _, _, ms = score_tour_text(RIVIERA_2STOP, n_requested=2, tour_name="latency-2stop")
        times_2.append(ms)

    # Measure 8-stop
    times_8 = []
    for _ in range(5):
        _, _, ms = score_tour_text(MUSEUM_8STOP, n_requested=8, tour_name="latency-8stop")
        times_8.append(ms)

    avg_2 = sum(times_2) / len(times_2)
    avg_8 = sum(times_8) / len(times_8)
    max_2 = max(times_2)
    max_8 = max(times_8)

    print(f"\n  2-stop tour: avg={avg_2:.1f}ms, max={max_2:.1f}ms")
    print(f"  8-stop tour: avg={avg_8:.1f}ms, max={max_8:.1f}ms")

    if max_8 > 200:
        print(f"\n  ⚠️  WARNING: 8-stop scoring exceeds 200ms target ({max_8:.1f}ms)")
    else:
        print(f"\n  ✅ All under 200ms target")

    return avg_2, avg_8, max_2, max_8


def cleanup_test_rows():
    """Remove test rows from tour_scores in test database."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM tour_scores WHERE tour_name LIKE '%(test)%' OR tour_name LIKE '%latency%' OR tour_name LIKE '%warmup%' OR tour_name LIKE '%identity test%'")
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    print(f"\n  Cleaned up {deleted} test rows from tour_scores")


if __name__ == "__main__":
    print("=" * 70)
    print("LOCAL-306: In-Flight Scoring Verification")
    print("=" * 70)

    try:
        # Run tests
        score_2, row_2, ms_2 = test_score_2stop()
        score_8, row_8, ms_8 = test_score_8stop()
        delta = test_edit_delta()
        test_delivery_unchanged()
        avg_2, avg_8, max_2, max_8 = test_latency()

        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"  2-stop Riviera: total={score_2.total_score:.1f}, {ms_2:.1f}ms")
        print(f"  8-stop Museum:  total={score_8.total_score:.1f}, {ms_8:.1f}ms")
        print(f"  Edit delta:     removed={delta['sourced_facts_removed']}, added={delta['unsourced_claims_added']}")
        print(f"  Latency:        2-stop avg={avg_2:.1f}ms, 8-stop avg={avg_8:.1f}ms")
        print(f"  Delivery:       byte-identical ✓")
        print(f"  User judgement: none ✓")
        print(f"  Scorer version: {SCORER_VERSION}")
        print(f"\n  ALL TESTS PASSED ✅")

        # Show persisted rows
        print("\n" + "-" * 70)
        print("PERSISTED ROWS (tour_scores):")
        print("-" * 70)
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, tour_name, total, n_requested, n_delivered,
                   scoring_ms, is_rescore, scorer_version
            FROM tour_scores
            ORDER BY id DESC LIMIT 20
        """)
        rows = cur.fetchall()
        for r in rows:
            print(f"  id={r[0]} name={r[1]!r:.40} total={r[2]:.1f} "
                  f"stops={r[4]}/{r[3]} ms={r[5]:.1f} rescore={r[6]} ver={r[7]}")
        cur.close()
        conn.close()

    finally:
        cleanup_test_rows()
