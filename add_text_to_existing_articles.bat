@echo off
echo Adding text content to existing articles for search functionality...

python -c "
import os
import re
import json
from pathlib import Path

# Get saved news from SharedPreferences equivalent
# This is a simplified version - in real app, we'd read from SharedPreferences
news_dirs = []

# Find all article directories in common locations
base_paths = [
    os.path.expanduser('~/AppData/Local/Temp'),
    'C:/temp',
    'C:/Users/micha/AppData/Local/Temp'
]

for base_path in base_paths:
    if os.path.exists(base_path):
        for item in os.listdir(base_path):
            item_path = os.path.join(base_path, item)
            if os.path.isdir(item_path) and 'article_' in item:
                index_file = os.path.join(item_path, 'index.html')
                text_file = os.path.join(item_path, 'audiotours_search_content.txt')
                
                if os.path.exists(index_file) and not os.path.exists(text_file):
                    try:
                        with open(index_file, 'r', encoding='utf-8') as f:
                            html_content = f.read()
                        
                        # Remove HTML tags and clean up text
                        text_content = re.sub(r'<[^>]*>', ' ', html_content)
                        text_content = re.sub(r'\s+', ' ', text_content).strip()
                        
                        with open(text_file, 'w', encoding='utf-8') as f:
                            f.write(text_content)
                        
                        print(f'Added text file to: {item_path}')
                    except Exception as e:
                        print(f'Error processing {item_path}: {e}')

print('Text extraction completed!')
"

echo.
echo Text files added to existing articles for search functionality!