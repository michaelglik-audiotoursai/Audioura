"""
Create a single-file HTML app with embedded audio files and usage tracking.
"""
import os
import sys
import glob
import base64
import webbrowser
import uuid
import json
import datetime

def create_tracked_app(tour_directory, tracking_url=None):
    """Create a single HTML file with embedded audio and usage tracking."""
    # Get absolute paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tour_dir = os.path.join(script_dir, tour_directory)
    
    # Check if tour directory exists
    if not os.path.exists(tour_dir):
        print(f"Error: Tour directory '{tour_directory}' not found")
        return
    
    # Find all MP3 files
    mp3_files = glob.glob(os.path.join(tour_dir, "audio_*.mp3"))
    if not mp3_files:
        print(f"Error: No audio files found in {tour_dir}")
        return
    
    print(f"Found {len(mp3_files)} audio files")
    
    # Sort files by stop number
    mp3_files.sort(key=lambda f: int(os.path.basename(f).split('_')[1]))
    
    # Create title from directory name
    title = tour_directory.replace("_", " ").title()
    
    # Generate a unique ID for this tour
    tour_id = str(uuid.uuid4())
    
    # Create tracking code
    if not tracking_url:
        tracking_url = "https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec"
    
    tracking_code = f"""
    // Usage tracking
    function trackUsage(event) {{
        const data = {{
            tourId: '{tour_id}',
            tourName: '{title}',
            event: event,
            timestamp: new Date().toISOString(),
            userAgent: navigator.userAgent,
            screenSize: window.innerWidth + 'x' + window.innerHeight
        }};
        
        // Try to get user name if provided
        const userName = localStorage.getItem('userName');
        if (userName) {{
            data.userName = userName;
        }}
        
        // Send tracking data
        fetch('{tracking_url}', {{
            method: 'POST',
            mode: 'no-cors',
            headers: {{
                'Content-Type': 'application/json',
            }},
            body: JSON.stringify(data)
        }}).catch(error => console.log('Tracking error:', error));
    }}
    
    // Track initial load
    document.addEventListener('DOMContentLoaded', function() {{
        // Ask for user name if not already provided
        if (!localStorage.getItem('userName')) {{
            setTimeout(function() {{
                const userName = prompt('Please enter your name to personalize your tour experience:', '');
                if (userName) {{
                    localStorage.setItem('userName', userName);
                    trackUsage('load');
                }}
            }}, 1000);
        }} else {{
            trackUsage('load');
        }}
    }});
    """
    
    # Start building HTML content
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
        }}
        .header {{
            background-color: #2c3e50;
            color: white;
            padding: 20px;
            text-align: center;
        }}
        .tour-container {{
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        .tour-item {{
            background-color: white;
            border-radius: 8px;
            margin-bottom: 20px;
            padding: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        .tour-title {{
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        audio {{
            width: 100%;
        }}
        .offline-notice {{
            background-color: #4CAF50;
            color: white;
            text-align: center;
            padding: 10px;
            margin-bottom: 20px;
        }}
        .loading {{
            text-align: center;
            padding: 20px;
            font-style: italic;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
    </div>
    
    <div class="tour-container">
        <div class="offline-notice">
            This app works offline! Save it to your home screen.
        </div>
        
        <div id="audio-container">
            <div class="loading">Loading audio files...</div>
        </div>
    </div>

    <script>
        // Audio data in base64 format
        const audioData = [
"""
    
    # Add each audio file as base64 data
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
        
        # Add to HTML
        html_content += f"""            {{
                title: "{stop_title}",
                data: "data:audio/mpeg;base64,{mp3_data}"
            }},
"""
    
    # Remove the last comma
    html_content = html_content.rstrip(",\n") + "\n"
    
    # Complete the HTML
    html_content += """        ];
        
        // Create audio elements
        document.addEventListener('DOMContentLoaded', function() {
            const container = document.getElementById('audio-container');
            container.innerHTML = ''; // Remove loading message
            
            audioData.forEach((item, index) => {
                const tourItem = document.createElement('div');
                tourItem.className = 'tour-item';
                
                const titleDiv = document.createElement('div');
                titleDiv.className = 'tour-title';
                titleDiv.textContent = item.title;
                
                const audio = document.createElement('audio');
                audio.controls = true;
                
                const source = document.createElement('source');
                source.src = item.data;
                source.type = 'audio/mpeg';
                
                audio.appendChild(source);
                
                tourItem.appendChild(titleDiv);
                tourItem.appendChild(audio);
                container.appendChild(tourItem);
                
                // Preload audio
                audio.load();
                
                // Track audio plays
                audio.addEventListener('play', function() {
                    // Track this audio play
                    if (typeof trackUsage === 'function') {
                        trackUsage('play_audio_' + (index + 1));
                    }
                    
                    // Pause other audio when one starts playing
                    audioData.forEach((_, idx) => {
                        const otherAudio = document.querySelectorAll('audio')[idx];
                        if (otherAudio !== audio) {
                            otherAudio.pause();
                        }
                    });
                });
            });
        });
        
"""
    
    # Add tracking code
    html_content += tracking_code
    
    # Close script and HTML
    html_content += """
    </script>
</body>
</html>
"""
    
    # Save the HTML file
    output_file = os.path.join(script_dir, f"{tour_directory}_tracked.html")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    # Save tracking info
    tracking_info = {
        "tour_id": tour_id,
        "tour_name": title,
        "created_at": datetime.datetime.now().isoformat(),
        "file_name": os.path.basename(output_file)
    }
    
    tracking_file = os.path.join(script_dir, f"{tour_directory}_tracking.json")
    with open(tracking_file, "w") as f:
        json.dump(tracking_info, f, indent=2)
    
    print(f"\nTracked app created successfully!")
    print(f"HTML file: {output_file}")
    print(f"Tour ID: {tour_id}")
    
    # Create Google Apps Script
    create_google_script_instructions(tour_id, title)
    
    # Open the app in browser
    webbrowser.open(f"file://{output_file}")
    
    return output_file, tour_id

def create_google_script_instructions(tour_id, tour_name):
    """Create instructions for setting up Google Apps Script for tracking."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Create Google Apps Script file
    gas_code = """function doPost(e) {
  // Parse the incoming data
  let data;
  try {
    data = JSON.parse(e.postData.contents);
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      'status': 'error',
      'message': 'Invalid JSON data'
    }));
  }
  
  // Add timestamp if not provided
  if (!data.timestamp) {
    data.timestamp = new Date().toISOString();
  }
  
  // Log to spreadsheet
  const spreadsheetId = ''; // Add your spreadsheet ID here
  const sheet = SpreadsheetApp.openById(spreadsheetId).getSheetByName('Usage') || 
                SpreadsheetApp.openById(spreadsheetId).getSheets()[0];
  
  // Check if headers exist, if not add them
  if (sheet.getLastRow() === 0) {
    sheet.appendRow([
      'Timestamp', 
      'Tour ID', 
      'Tour Name', 
      'User Name', 
      'Event', 
      'User Agent', 
      'Screen Size'
    ]);
  }
  
  // Append the data
  sheet.appendRow([
    data.timestamp,
    data.tourId,
    data.tourName,
    data.userName || 'Anonymous',
    data.event,
    data.userAgent,
    data.screenSize
  ]);
  
  // Return success
  return ContentService.createTextOutput(JSON.stringify({
    'status': 'success'
  }));
}

function doGet() {
  return HtmlService.createHtmlOutput(
    '<h1>Audio Tour Tracking Service</h1><p>This is a tracking endpoint for audio tours.</p>'
  );
}"""
    
    gas_file = os.path.join(script_dir, "tour_tracking_script.gs")
    with open(gas_file, "w") as f:
        f.write(gas_code)
    
    # Create instructions
    instructions = f"""
=== TRACKING SETUP INSTRUCTIONS ===

To track usage of your audio tour, follow these steps:

1. Create a new Google Sheet:
   - Go to https://sheets.google.com
   - Create a new spreadsheet
   - Name it "{tour_name} Usage Tracking"
   - Note the spreadsheet ID from the URL (the long string between /d/ and /edit)

2. Create a Google Apps Script:
   - In your spreadsheet, click Extensions > Apps Script
   - Delete any code in the editor
   - Copy and paste the code from the file: {gas_file}
   - Replace the empty spreadsheetId with your spreadsheet ID
   - Save the project (name it "Audio Tour Tracking")
   - Click Deploy > New deployment
   - Select "Web app" as the type
   - Set "Who has access" to "Anyone"
   - Click "Deploy"
   - Copy the Web app URL

3. Update your HTML file:
   - Open {tour_id}_tracked.html in a text editor
   - Find the line with "https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec"
   - Replace it with your Web app URL
   - Save the file

4. Share your HTML file:
   - Upload to a web hosting service
   - Share the link with your audience
   - Each time someone opens the tour, you'll get a record in your spreadsheet
   - You'll see their name, when they opened it, and which audio files they played

Your tour ID is: {tour_id}
This ID is used to identify this specific tour in the tracking data.
"""
    
    instructions_file = os.path.join(script_dir, f"{tour_name}_tracking_instructions.txt")
    with open(instructions_file, "w") as f:
        f.write(instructions)
    
    print(f"\nTracking instructions created: {instructions_file}")
    print("Follow these instructions to set up usage tracking.")

if __name__ == "__main__":
    # Get tour directory from command line argument or prompt
    if len(sys.argv) > 1:
        tour_dir = sys.argv[1]
    else:
        # List available directories
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dirs = [d for d in os.listdir(script_dir) 
                if os.path.isdir(os.path.join(script_dir, d)) 
                and not d.startswith('.') 
                and not d.startswith('__')
                and d != "mobile_app"]
        
        if not dirs:
            print("No tour directories found.")
            sys.exit(1)
            
        print("Available tour directories:")
        for i, d in enumerate(dirs, 1):
            print(f"{i}. {d}")
            
        try:
            choice = int(input("\nEnter the number of the directory to package (or press Enter for the first one): ") or "1")
            if 1 <= choice <= len(dirs):
                tour_dir = dirs[choice-1]
            else:
                print("Invalid choice. Using the first directory.")
                tour_dir = dirs[0]
        except ValueError:
            print("Invalid input. Using the first directory.")
            tour_dir = dirs[0]
    
    # Create the tracked app
    create_tracked_app(tour_dir)