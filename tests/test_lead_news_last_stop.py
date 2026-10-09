"""LEAD 2026-10-09: news for the LAST stop goes before the conclusion, never after the tour ends (tour 557 v6)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import current_affairs_news as c

TOUR = ("Stop 1: Faneuil Hall\n\nBody one.\n\nDirections: Walk on.\n\n"
        "Stop 2: Massachusetts State House\n\nBody two.\n\n"
        "Together, these stops reveal civic life. That's 2 stops in all.\n\n"
        "If you would like to eat nearby we can build you a restaurant tour.\n")

def test_last_stop_news_precedes_conclusion():
    out, n = c.inject_news_into_text(TOUR, {"Massachusetts State House": {"text": "On October 8, 2026, A and B debated.", "sources": []}})
    assert n == 1
    assert out.index("In recent news:") < out.index("Together, these stops")
    assert out.rstrip().endswith("restaurant tour.")

def test_middle_stop_news_precedes_directions():
    out, n = c.inject_news_into_text(TOUR, {"Faneuil Hall": {"text": "On October 7, 2026, a rally was held.", "sources": []}})
    assert n == 1 and out.index("In recent news:") < out.index("Directions: Walk on.")

def test_prompt_separates_publication_date_from_event_date():
    assert "PUBLISHED" in c._NEWS_PROMPT and "FUTURE event" in c._NEWS_PROMPT
