"""
Create tracked HTML apps that share a single Google Sheet for tracking multiple tours.
"""
import os
import sys
import glob
import base64
import webbrowser
import uuid
import json
import datetime

def create_tracked_app_with_shared_sheet(tour_directory, sheet_id, tracking_url=None, use_tabs=False):
    """Create a single HTML file with embedded audio and shared sheet tracking."""
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
    
    # Create tracking code with shared sheet support
    if not tracking_url:
        tracking_url = "https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec"
    
    # Determine sheet name based on use_tabs setting
    sheet_name = tour_directory if use_tabs else "AllTours"
    
    tracking_code = f"""
    // Usage tracking with shared sheet
    function trackUsage(event) {{
        const data = {{
            tourId: '{tour_id}',
            tourName: '{title}',
            tourDirectory: '{tour_directory}',
            sheetId: '{sheet_id}',
            sheetName: '{sheet_name}',
            useTabs: {str(use_tabs).lower()},
            event: event,
            timestamp: new Date().toISOString(),
            userAgent: navigator.userAgent,
            screenSize: window.innerWidth + 'x' + window.innerHeight,
            url: window.location.href
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
        .tracking-info {{
            background-color: #e8f4f8;
            border: 1px solid #bee5eb;
            border-radius: 5px;
            padding: 10px;
            margin-bottom: 20px;
            font-size: 12px;
            color: #0c5460;
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
        
        <div class="tracking-info">
            <strong>Tracking:</strong> Sheet ID: {sheet_id} | {"Tab: " + sheet_name if use_tabs else "Single sheet for all tours"}
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
    output_file = os.path.join(script_dir, f"{tour_directory}_shared_tracked.html")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    # Save tracking info
    tracking_info = {
        "tour_id": tour_id,
        "tour_name": title,
        "tour_directory": tour_directory,
        "sheet_id": sheet_id,
        "sheet_name": sheet_name,
        "use_tabs": use_tabs,
        "created_at": datetime.datetime.now().isoformat(),
        "file_name": os.path.basename(output_file)
    }
    
    tracking_file = os.path.join(script_dir, f"{tour_directory}_shared_tracking.json")
    with open(tracking_file, "w") as f:
        json.dump(tracking_info, f, indent=2)
    
    print(f"\nShared tracked app created successfully!")
    print(f"HTML file: {output_file}")
    print(f"Tour ID: {tour_id}")
    print(f"Sheet ID: {sheet_id}")
    print(f"Sheet Name: {sheet_name}")
    
    return output_file, tour_id

def create_google_script_for_shared_tracking():
    """Create Google Apps Script code for shared tracking."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    gas_code = """function doPost(e) {
  // Parse the incoming data
  let data;
  try {
    data = JSON.parse(e.postData.contents);
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      'status': 'error',
      'message': 'Invalid JSON'
    })).setMimeType(ContentService.MimeType.JSON);
  }
  
  try {
    // Open the spreadsheet by ID
    const spreadsheet = SpreadsheetApp.openById(data.sheetId);
    
    let sheet;
    if (data.useTabs) {
      // Use separate tabs for each tour
      sheet = spreadsheet.getSheetByName(data.sheetName);
      if (!sheet) {
        // Create new sheet if it doesn't exist
        sheet = spreadsheet.insertSheet(data.sheetName);
        // Add headers
        sheet.getRange(1, 1, 1, 9).setValues([[
          'Timestamp', 'Tour Name', 'Tour Directory', 'User Name', 'Event', 
          'User Agent', 'Screen Size', 'URL', 'Tour ID'
        ]]);
      }
    } else {
      // Use single sheet for all tours
      sheet = spreadsheet.getSheetByName('AllTours');
      if (!sheet) {
        // Create AllTours sheet if it doesn't exist
        sheet = spreadsheet.insertSheet('AllTours');
        // Add headers
        sheet.getRange(1, 1, 1, 9).setValues([[
          'Timestamp', 'Tour Name', 'Tour Directory', 'User Name', 'Event', 
          'User Agent', 'Screen Size', 'URL', 'Tour ID'
        ]]);
      }
    }
    
    // Add the data
    sheet.appendRow([
      data.timestamp,
      data.tourName || '',
      data.tourDirectory || '',
      data.userName || 'Anonymous',
      data.event || '',
      data.userAgent || '',
      data.screenSize || '',
      data.url || '',
      data.tourId || ''
    ]);
    
    return ContentService.createTextOutput(JSON.stringify({
      'status': 'success'
    })).setMimeType(ContentService.MimeType.JSON);
    
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      'status': 'error',
      'message': error.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  return ContentService.createTextOutput(JSON.stringify({
    'status': 'ready',
    'message': 'Tracking endpoint is active'
  })).setMimeType(ContentService.MimeType.JSON);
}
"""
    
    # Save the Google Apps Script code
    gas_file = os.path.join(script_dir, "shared_tracking_script.gs")
    with open(gas_file, "w") as f:
        f.write(gas_code)
    
    # Create setup instructions
    instructions = """
SETUP INSTRUCTIONS FOR SHARED TRACKING:

1. Create a new Google Spreadsheet
2. Note the spreadsheet ID from the URL (the long string between /d/ and /edit)
3. Go to Extensions > Apps Script
4. Replace the default code with the contents of 'shared_tracking_script.gs'
5. Save the script (Ctrl+S)
6. Click "Deploy" > "New deployment"
7. Choose type: "Web app"
8. Execute as: "Me"
9. Who has access: "Anyone"
10. Click "Deploy"
11. Copy the web app URL
12. Use this URL as the tracking_url parameter

The script will automatically:
- Create tabs for each tour (if use_tabs=True)
- Or use a single "AllTours" sheet (if use_tabs=False)
- Add appropriate headers
- Track all usage data with tour identification
"""
    
    instructions_file = os.path.join(script_dir, "shared_tracking_setup.txt")
    with open(instructions_file, "w") as f:
        f.write(instructions)
    
    print(f"\nGoogle Apps Script created: {gas_file}")
    print(f"Setup instructions: {instructions_file}")

def main():
    """Main function to create tracked apps with shared sheet."""
    # Get parameters from command line or console input
    if len(sys.argv) >= 3:
        # Use command line arguments
        tour_directory = sys.argv[1]
        sheet_id = sys.argv[2]
        tracking_url = sys.argv[3] if len(sys.argv) > 3 else None
        use_tabs = sys.argv[4].lower() == 'true' if len(sys.argv) > 4 else False
    else:
        # Get parameters from console input
        print("=== Shared Sheet Tracked App Builder ===\n")
        
        # Get tour directory
        tour_directory = input("Enter tour directory name: ").strip()
        if not tour_directory:
            print("Error: Tour directory is required")
            return
        
        # Get sheet ID
        sheet_id = input("Enter Google Sheet ID: ").strip()
        if not sheet_id:
            print("Error: Google Sheet ID is required")
            return
        
        # Get tracking URL (optional)
        tracking_url = input("Enter tracking URL (press Enter to use default): ").strip()
        if not tracking_url:
            tracking_url = None
        
        # Get use_tabs option
        use_tabs_input = input("Use separate tabs for each tour? (y/n, default: n): ").strip().lower()
        use_tabs = use_tabs_input in ['y', 'yes', 'true']
    
    # Create the tracked app
    output_file, tour_id = create_tracked_app_with_shared_sheet(
        tour_directory, sheet_id, tracking_url, use_tabs
    )
    
    # Create Google Apps Script if it doesn't exist
    script_dir = os.path.dirname(os.path.abspath(__file__))
    gas_file = os.path.join(script_dir, "shared_tracking_script.gs")
    if not os.path.exists(gas_file):
        create_google_script_for_shared_tracking()

if __name__ == "__main__":
    main()