#!/usr/bin/env python3
"""Create fresh test tour for REQ-016 validation"""

import os
import zipfile
from pathlib import Path

# Create fresh test tour content
test_stops = [
    "Boston Common Historic Overview\n\nBoston Common, established in 1634, is America's oldest public park. This 50-acre green space has served as a central gathering place for Bostonians for nearly four centuries.",
    
    "Freedom Trail Starting Point\n\nThe Freedom Trail begins here at Boston Common. This red-brick path connects 16 historically significant sites throughout Boston, telling the story of the American Revolution.",
    
    "Boston Common Swan Boats\n\nThe famous Swan Boats have been operating on the lagoon since 1877. These pedal-powered boats are a beloved Boston tradition and offer peaceful rides around the pond.",
    
    "Public Garden Adjacent Beauty\n\nJust across Charles Street lies the Public Garden, featuring the iconic bronze sculptures of Mrs. Mallard and her eight ducklings from the children's book 'Make Way for Ducklings'.",
    
    "Central Burying Ground\n\nThis historic cemetery, dating to 1756, contains the graves of many notable figures including composer William Billings and several Revolutionary War soldiers."
]

# Create tour directory
tour_dir = Path("/app/tours/fresh_test_tour_boston_common_walking_test001")
tour_dir.mkdir(exist_ok=True)

# Write text files
for i, content in enumerate(test_stops, 1):
    text_file = tour_dir / f"audio_{i}.txt"
    with open(text_file, 'w', encoding='utf-8') as f:
        f.write(content)

# Create simple HTML file
html_content = '''<!DOCTYPE html>
<html>
<head><title>Fresh Test Tour</title></head>
<body>
<h1>Fresh Test Tour - Boston Common</h1>
<div>Stop 1: <audio controls><source src="audio_1.mp3"></audio></div>
<div>Stop 2: <audio controls><source src="audio_2.mp3"></audio></div>
<div>Stop 3: <audio controls><source src="audio_3.mp3"></audio></div>
<div>Stop 4: <audio controls><source src="audio_4.mp3"></audio></div>
<div>Stop 5: <audio controls><source src="audio_5.mp3"></audio></div>
</body>
</html>'''

html_file = tour_dir / "index.html"
with open(html_file, 'w', encoding='utf-8') as f:
    f.write(html_content)

# Create ZIP file
zip_path = tour_dir.parent / f"{tour_dir.name}.zip"
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for file_path in tour_dir.rglob('*'):
        if file_path.is_file():
            arcname = file_path.relative_to(tour_dir)
            zipf.write(file_path, arcname)

print(f"Created fresh test tour: {tour_dir}")
print(f"Created ZIP: {zip_path}")
print(f"Stops: {len(test_stops)}")