"""D762 quick path: a whole itinerary pasted into one own-stop field expands."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from itinerary_import import expand_pasted_lists

MICHAEL = ("Cathedral → Post Office → Book Street → Independence Palace → War Remnants Museum → "
           "Opera House/Đồng Khởi → City Hall & Nguyễn Huệ → Café Apartments 42 → "
           "Bạch Đằng Pier (tour-bus + waterbus) → Thi Bar")


class T(unittest.TestCase):
    def test_michael_list_in_one_field(self):
        out, n = expand_pasted_lists([MICHAEL], "Ho Chi Minh City")
        self.assertEqual(n, 1)
        self.assertEqual(len(out), 10)
        self.assertTrue(out[0].startswith("Cathedral"))
        self.assertTrue(out[-1].startswith("Thi Bar"))
        self.assertFalse(any("tour-bus" in s for s in out))

    def test_commas_alone_do_not_split(self):
        s = "Thi Bar Saigon, 224 Đề Thám, District 1"
        self.assertEqual(expand_pasted_lists([s]), ([s], 0))

    def test_mixed_fields_keep_order(self):
        out, n = expand_pasted_lists(["Rambutan", "Longan -> An Spa", "Acoustic Bar"])
        self.assertEqual(n, 1)
        self.assertEqual([o.split(" http")[0] for o in out],
                         ["Rambutan", "Longan", "An Spa", "Acoustic Bar"])

    def test_non_list_passthrough(self):
        self.assertEqual(expand_pasted_lists(None), (None, 0))


if __name__ == "__main__":
    unittest.main()
