# tools/

CLI diagnostic utilities. These are **not tests** — they are tools that
require command-line arguments (location names, API keys, etc.) to do anything
useful. They were mislocated in `tests/` where they polluted test discovery.

## Usage

```bash
python3 tools/coordinates_test_tool.py "Boston Public Library"
python3 tools/mapbox_tool.py "Hall Memorial Library" pk.eyXXX
python3 tools/tour_generation_tool.py "Museum of Fine Arts, Boston"
python3 tools/zip_quality_tool.py  # checks recent_test.zip etc.
```

## Why they are here

They print usage instructions and exit when run without arguments.
Running them inside `pytest` or a test runner causes false noise —
they're not asserting anything, they're probing live services.
