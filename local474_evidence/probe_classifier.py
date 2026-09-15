import generate_tour_text as g

loc_rest = "Bread Thyme restaurant tour in West Roxbury, MA"
loc_mus  = "Museum of Fine Arts, Boston"

cases = [
    ("empty_on_restaurant_loc", loc_rest, ""),
    ("none_on_restaurant_loc",  loc_rest, None),
    ("explicit_museum",         loc_mus,  "museum"),
    ("explicit_museum_on_rest", loc_rest, "museum"),
    ("empty_on_museum_loc",     loc_mus,  ""),
]

for name, loc, tt in cases:
    # Mirror the generate_tour_text entry normalization for the None case so we
    # exercise exactly what the function does after [LOCAL-474].
    tt_norm = "" if tt is None else tt
    try:
        cat = g._classify_tour_category(loc, tt_norm)
    except Exception as e:
        cat = "EXC:%r" % (e,)
    print("%-26s tour_type=%-8r -> category=%s" % (name, tt, cat))
