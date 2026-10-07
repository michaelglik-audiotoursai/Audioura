"""
Process tour text files and create directory structure with POI audio text files.
"""
import os
import re

# [LOCAL-602 r2 / D617 item 9] The spoken text a listener hears must contain NO
# URL and NO "Sources" block — a synthesiser would read them aloud. The strip is
# a deterministic pass in spoken_text_hygiene; imported defensively so a missing
# module degrades to the pre-602 behaviour rather than crashing the packer.
try:
    from spoken_text_hygiene import strip_sources_and_urls as _strip_spoken
except Exception:  # pragma: no cover - defensive
    _strip_spoken = None

def process_tour_file(filename):
    # Get the absolute path of the script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Ensure the file path is absolute
    if not os.path.isabs(filename):
        file_path = os.path.join(script_dir, filename)
    else:
        file_path = filename
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract tour name
    tour_match = re.search(r'Step-by-Step Audio Guided Tour: (.*?)(?:\n|$)', content)
    if not tour_match:
        print(f"No tour name found in {filename}")
        return
    
    tour_name = tour_match.group(1).strip()
    # Create directory name from tour name
    dir_name = os.path.splitext(os.path.basename(filename))[0]
    
    # Create full directory path in the script directory
    dir_path = os.path.join(script_dir, dir_name)
    
    # Create directory if it doesn't exist
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        print(f"Created directory: {dir_path}")
    
    # Find all POIs
    poi_matches = re.finditer(r'Stop (\d+): (.*?)(?:\n|$)(.*?)(?=Stop \d+:|$)', content, re.DOTALL)
    
    for match in poi_matches:
        stop_num = match.group(1)
        poi_name = match.group(2).strip()
        poi_content = match.group(3).strip()

        # [LOCAL-602 r2 / D617 item 9] Strip URLs and any "Sources:" block so the
        # SPOKEN audio file never reads a web address aloud. The full-text / web
        # view (generated separately) keeps its Sources line.
        if _strip_spoken is not None:
            poi_content, _rep = _strip_spoken(poi_content)
            if _rep.get('urls') or _rep.get('sources_blocks'):
                print(f"   [LOCAL-602] stop {stop_num} spoken-text: stripped "
                      f"{_rep.get('urls', 0)} URL(s), "
                      f"{_rep.get('sources_blocks', 0)} Sources block(s)")
        
        # Create filename from POI name
        file_name = f"audio_{stop_num}_" + re.sub(r'[^a-z0-9]', '_', poi_name.lower())
        file_name = re.sub(r'_+', '_', file_name)  # Replace multiple underscores with single
        file_name = file_name.rstrip('_') + '.txt'
        
        # Write POI content to file
        file_path = os.path.join(dir_path, file_name)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(poi_content)
        
        print(f"Created file: {file_path}")

if __name__ == "__main__":
    process_tour_file("tour_newton_centre.txt")