"""repro_local826b_stop4.py — reproduce the Rijksmuseum Stop 4 corruption.

The LOCAL-628 stop editor (an LLM pass) re-emitted Stop 3 (Jewish Bride) with
Stop 4's (Merry Drinker) full body glued after Stop 3's Directions line as a
HEADERLESS body. normalise_stop_headers -> dedupe_and_fix_stop_count then
de-splices: it keeps Stop 3's Directions hand-off and DROPS everything after it
— silently deleting the real, narrated, paid Merry Drinker stop. The delivered
text is then left with a truncated "Stop 4:" header (restored by LOCAL-632) and
a duplicate "Stop 4" for the Great Wave, and the tour ships 4 stops for 5.

This script builds the pre-guard glued shape and runs the REAL guard, then
checks the delivery invariant. Before the fix: the Merry Drinker body is gone
and the delivery check FAILS (duplicate/absent-body). After the fix: the stop
survives with its header and body, numbering is sequential.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tour_conclusion import normalise_stop_headers, count_delivered_stops

GLUED = """Step-by-Step Audio Guided Tour: Rijks Museum, Amsterdam, Netherlands
Tour-Category: museum

Stop 3: Het Joodse Bruidje (The Jewish Bride)

Address: Museumstraat 1, 1071 XX Amsterdam, Netherlands

Coordinates: 52.360000, 4.885278

Orientation: As you stand here facing 'Het Joodse bruidje,' position yourself to catch the full interaction of the two figures.

Created between 1665 and 1669, this painting shows a Jewish father bestowing a necklace on his daughter. The work is oil on canvas.

Directions: Proceed to A Militiaman Holding a Berkemeyer, Known as the 'Merry Drinker' (Een schutter die een berkenmeier vasthoudt, bekend als 'De vrolijke drinker').

Address: Museumstraat 1, 1071 XX Amsterdam, Netherlands

Coordinates: 52.360000, 4.885278

Orientation: Stand close to observe the militiaman holding his glass.

Frans Hals painted the Merry Drinker around 1628 to 1630, capturing a live, convivial moment. The loose brushwork conveys spontaneity and warmth, a hallmark of Hals's mature style. The sitter's raised glass and open smile invite the viewer into the scene.

Directions: Your final stop in Rijksmuseum: De grote golf bij Kanagawa (The Great Wave off Kanagawa).

Stop 5: De grote golf bij Kanagawa (The Great Wave off Kanagawa)

Address: Museumstraat 1, 1071 XX Amsterdam, Netherlands

Coordinates: 52.360000, 4.885278

Orientation: Stand close to the print.

The Great Wave off Kanagawa was created by Katsushika Hokusai in late 1831 during Japan's Edo period. This iconic woodblock print depicts a massive wave.

Sources: This tour draws on information from www.rijksmuseum.nl and the Wikipedia article on the museum.
"""


def show(label, text):
    import re
    print(f"\n=== {label} ===")
    print(f"  count_delivered_stops: {count_delivered_stops(text)}")
    for m in re.finditer(r'(?m)^Stop \d+:.*$', text):
        print("   ", m.group(0)[:70])


def main():
    show("INPUT (editor glued Merry Drinker body after Stop 3 Directions)", GLUED)
    out = normalise_stop_headers(GLUED)
    show("AFTER normalise_stop_headers (LOCAL-801 de-splice)", out)
    # Did the Merry Drinker survive with a body?
    has_md_body = "Frans Hals painted the Merry Drinker" in out
    print(f"\n  Merry Drinker BODY present after guard: {has_md_body}")


if __name__ == "__main__":
    main()
