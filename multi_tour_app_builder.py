"""
Create a multi-page single-file app with all tours.
"""
import os
import sys
import glob
import base64

def create_multi_tour_app():
    """Create a single HTML file with all tours."""
    # Get absolute paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Find all tour directories
    tour_dirs = [d for d in os.listdir(script_dir) 
                if os.path.isdir(os.path.join(script_dir, d)) 
                and not d.startswith('.') 
                and not d.startswith('__')
                and d != "mobile_app"]
    
    if not tour_dirs:
        print("No tour directories found.")
        return
    
    print(f"Found {len(tour_dirs)} tour directories")
    
    # Start building HTML content
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Audio Tours</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
        }
        .header {
            background-color: #2c3e50;
            color: white;
            padding: 20px;
            text-align: center;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        .tour-card {
            background-color: white;
            border-radius: 8px;
            margin-bottom: 20px;
            padding: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            cursor: pointer;
        }
        .tour-card:hover {
            background-color: #f0f0f0;
        }
        .tour-title {
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 10px;
        }
        .tour-stops {
            color: #666;
            font-size: 14px;
        }
        .back-button {
            background-color: #2c3e50;
            color: white;
            border: none;
            padding: 10px 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            cursor: pointer;
        }
        audio {
            width: 100%;
            margin-bottom: 15px;
        }
        .tour-item {
            background-color: white;
            border-radius: 8px;
            margin-bottom: 20px;
            padding: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .stop-title {
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 10px;
        }
        .offline-notice {
            background-color: #4CAF50;
            color: white;
            text-align: center;
            padding: 10px;
            margin-bottom: 20px;
        }
        .loading {
            text-align: center;
            padding: 20px;
            font-style: italic;
            color: #666;
        }
        .page {
            display: none;
        }
        .active {
            display: block;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Audio Tours</h1>
    </div>
    
    <div class="container">
        <div class="offline-notice">
            This app works offline! Save it to your home screen.
        </div>
        
        <!-- Home Page -->
        <div id="home-page" class="page active">
            <h2>Available Tours</h2>
            <div id="tours-container">
                <div class="loading">Loading tours...</div>
            </div>
        </div>
        
        <!-- Tour Pages -->
"""

    # Add tour pages
    tour_data = []
    
    for tour_dir in tour_dirs:
        tour_path = os.path.join(script_dir, tour_dir)
        tour_title = tour_dir.replace("_", " ").title()
        
        # Find MP3 files for this tour
        mp3_files = glob.glob(os.path.join(tour_path, "audio_*.mp3"))
        if not mp3_files:
            continue
            
        # Sort files by stop number
        mp3_files.sort(key=lambda f: int(os.path.basename(f).split('_')[1]))
        
        # Create tour data
        tour_audio_data = []
        
        for mp3_file in mp3_files:
            basename = os.path.basename(mp3_file)
            # Extract stop number and name
            parts = basename.replace('.mp3', '').split('_')
            stop_num = parts[1]
            name = ' '.join(parts[2:]).replace('_', ' ').title()
            stop_title = f"Stop {stop_num}: {name}"
            
            # Read MP3 file as base64
            with open(mp3_file, 'rb') as f:
                mp3_data = base64.b64encode(f.read()).decode('utf-8')
            
            tour_audio_data.append({
                'title': stop_title,
                'data': mp3_data
            })
        
        # Add tour data
        tour_data.append({
            'id': tour_dir,
            'title': tour_title,
            'stops': len(mp3_files),
            'audio': tour_audio_data
        })
        
        # Add tour page
        html_content += f"""
        <div id="{tour_dir}-page" class="page">
            <button class="back-button" onclick="showHomePage()">← Back to Tours</button>
            <h2>{tour_title}</h2>
            <div id="{tour_dir}-container">
                <div class="loading">Loading audio files...</div>
            </div>
        </div>
"""
    
    # Complete the HTML
    html_content += """
    </div>

    <script>
        // Tour data
        const tourData = 
"""
    
    # Add tour data as JSON
    import json
    html_content += json.dumps(tour_data, indent=2)
    
    # Add JavaScript for navigation and audio
    html_content += """
        ;
        
        // Show home page
        function showHomePage() {
            document.querySelectorAll('.page').forEach(page => {
                page.classList.remove('active');
            });
            document.getElementById('home-page').classList.add('active');
        }
        
        // Show tour page
        function showTourPage(tourId) {
            document.querySelectorAll('.page').forEach(page => {
                page.classList.remove('active');
            });
            document.getElementById(tourId + '-page').classList.add('active');
            
            // Load tour content if not already loaded
            const container = document.getElementById(tourId + '-container');
            if (container.innerHTML.includes('Loading')) {
                loadTourContent(tourId);
            }
        }
        
        // Load tour content
        function loadTourContent(tourId) {
            const tour = tourData.find(t => t.id === tourId);
            if (!tour) return;
            
            const container = document.getElementById(tourId + '-container');
            container.innerHTML = '';
            
            tour.audio.forEach(item => {
                const tourItem = document.createElement('div');
                tourItem.className = 'tour-item';
                
                const titleDiv = document.createElement('div');
                titleDiv.className = 'stop-title';
                titleDiv.textContent = item.title;
                
                const audio = document.createElement('audio');
                audio.controls = true;
                
                const source = document.createElement('source');
                source.src = 'data:audio/mpeg;base64,' + item.data;
                source.type = 'audio/mpeg';
                
                audio.appendChild(source);
                
                tourItem.appendChild(titleDiv);
                tourItem.appendChild(audio);
                container.appendChild(tourItem);
                
                // Pause other audio when one starts playing
                audio.addEventListener('play', function() {
                    document.querySelectorAll('audio').forEach(other => {
                        if (other !== audio) {
                            other.pause();
                        }
                    });
                });
            });
        }
        
        // Initialize
        document.addEventListener('DOMContentLoaded', function() {
            // Populate tours list
            const toursContainer = document.getElementById('tours-container');
            toursContainer.innerHTML = '';
            
            tourData.forEach(tour => {
                const tourCard = document.createElement('div');
                tourCard.className = 'tour-card';
                tourCard.onclick = function() { showTourPage(tour.id); };
                
                const titleDiv = document.createElement('div');
                titleDiv.className = 'tour-title';
                titleDiv.textContent = tour.title;
                
                const stopsDiv = document.createElement('div');
                stopsDiv.className = 'tour-stops';
                stopsDiv.textContent = tour.stops + ' stops';
                
                tourCard.appendChild(titleDiv);
                tourCard.appendChild(stopsDiv);
                toursContainer.appendChild(tourCard);
            });
        });
    </script>
</body>
</html>
"""
    
    # Save the HTML file
    output_file = os.path.join(script_dir, "all_tours.html")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"\nMulti-tour app created successfully!")
    print(f"HTML file: {output_file}")
    
    # Open the app in browser
    import webbrowser
    webbrowser.open(f"file://{output_file}")
    
    print("\nTo use on your phone:")
    print("1. Transfer the HTML file to your phone")
    print("2. Open it in your phone's browser")
    print("3. Add to home screen when prompted")
    print("\nNote: This file contains all audio data embedded within it.")
    print("It may be large, but it will work completely offline with no file access issues.")

if __name__ == "__main__":
    create_multi_tour_app()