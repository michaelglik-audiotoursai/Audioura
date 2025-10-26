"""
Simplified version of single_file_app_builder.py with direct HTML element clicking
"""
import os
import sys
import glob
import base64

def create_single_file_app(tour_directory):
    """Create a single HTML file with embedded audio. Works in current directory."""
    current_dir = os.getcwd()
    print(f"DEBUG: single_file_app_builder working in: {current_dir}")
    print(f"DEBUG: Looking for directory: {tour_directory}")
    
    # Check if tour directory exists in current directory
    tour_dir = os.path.join(current_dir, tour_directory)
    if not os.path.exists(tour_dir):
        print(f"Error: Tour directory '{tour_directory}' not found in {current_dir}")
        return None
    
    # Find all MP3 files
    mp3_files = glob.glob(os.path.join(tour_dir, "audio_*.mp3"))
    if not mp3_files:
        print(f"Error: No audio files found in {tour_dir}")
        return None
    
    print(f"Found {len(mp3_files)} audio files")
    
    # Sort files by stop number
    def get_stop_number(filename):
        basename = os.path.basename(filename)
        try:
            # Handle audio_1.mp3 format
            if '_' in basename:
                number_part = basename.split('_')[1].split('.')[0]  # Get number before .mp3
                return int(number_part)
            else:
                return 0
        except (ValueError, IndexError):
            return 0
    
    mp3_files.sort(key=get_stop_number)
    
    # Create title from directory name
    title = tour_directory.replace("_", " ").title()
    
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
"""
    
    # Generate audio elements directly in HTML
    for i, mp3_file in enumerate(mp3_files):
        basename = os.path.basename(mp3_file)
        # Extract stop number and name
        parts = basename.replace('.mp3', '').split('_')
        if len(parts) >= 2:
            stop_num = parts[1]
            name = ' '.join(parts[2:]).replace('_', ' ').title() if len(parts) > 2 else f"Audio {stop_num}"
        else:
            stop_num = "1"
            name = "Audio"
        stop_title = f"Stop {stop_num}: {name}"
        
        # Read MP3 file as base64
        with open(mp3_file, 'rb') as f:
            mp3_data = base64.b64encode(f.read()).decode('utf-8')
        
        # Add audio element directly to HTML
        html_content += f"""            <div class="tour-item">
                <div class="tour-title">{stop_title}</div>
                <audio id="audio-{i}" controls preload="metadata">
                    <source src="data:audio/mpeg;base64,{mp3_data}" type="audio/mpeg">
                </audio>
            </div>
"""
    
    # Complete the HTML with simplified voice control functions
    html_content += """        </div>
    </div>

    <script>
        let currentStopIndex = 0;
        let lastAsyncError = null;
        
        // Helper function to get current time
        function getTimeStamp() {
            const now = new Date();
            return now.getHours().toString().padStart(2, '0') + ':' + 
                   now.getMinutes().toString().padStart(2, '0') + ':' + 
                   now.getSeconds().toString().padStart(2, '0');
        }
        
        // Helper function to store async errors
        function storeAsyncError(functionName, error) {
            lastAsyncError = `OLD_ERROR[${getTimeStamp()}|${functionName}]: ${error.name}: ${error.message}`;
        }
        
        // Helper function to get and clear error report
        function getErrorReport() {
            if (lastAsyncError) {
                const report = ` | ${lastAsyncError}`;
                lastAsyncError = null; // Clear after reporting
                return report;
            }
            return '';
        }
        
        // Voice control functions with enhanced error reporting
        window.playAudio = function() {
            const errorReport = getErrorReport();
            const audio = document.getElementById(`audio-${currentStopIndex}`);
            if (audio) {
                try {
                    const playPromise = audio.play();
                    if (playPromise !== undefined) {
                        playPromise.catch(error => {
                            storeAsyncError('playAudio', error);
                        });
                    }
                    return `Success: Playing audio-${currentStopIndex}${errorReport}`;
                } catch (error) {
                    return `Error: ${error.message} - audio-${currentStopIndex}${errorReport}`;
                }
            }
            const totalAudios = document.querySelectorAll('audio').length;
            return `No audio found - currentStop:${currentStopIndex}, total:${totalAudios}${errorReport}`;
        };
        
        window.pauseAudio = function() {
            const audio = document.getElementById(`audio-${currentStopIndex}`);
            if (audio) {
                audio.pause();
                return `Audio Paused - paused audio-${currentStopIndex}`;
            }
            return `No audio to pause - currentStop:${currentStopIndex}`;
        };
        
        window.nextStop = function() {
            const errorReport = getErrorReport();
            const totalAudios = document.querySelectorAll('audio').length;
            if (currentStopIndex < totalAudios - 1) {
                currentStopIndex++;
                const audio = document.getElementById(`audio-${currentStopIndex}`);
                if (audio) {
                    try {
                        const playPromise = audio.play();
                        if (playPromise !== undefined) {
                            playPromise.catch(error => {
                                storeAsyncError('nextStop', error);
                            });
                        }
                        return `Next Stop - playing audio-${currentStopIndex}${errorReport}`;
                    } catch (error) {
                        return `Next Stop error - ${error.message} - audio-${currentStopIndex}${errorReport}`;
                    }
                }
                return `Next Stop failed - audio-${currentStopIndex} not found${errorReport}`;
            }
            return `Already at last stop - currentStop:${currentStopIndex}, total:${totalAudios}${errorReport}`;
        };
        
        window.previousStop = function() {
            const errorReport = getErrorReport();
            if (currentStopIndex > 0) {
                currentStopIndex--;
                const audio = document.getElementById(`audio-${currentStopIndex}`);
                if (audio) {
                    try {
                        const playPromise = audio.play();
                        if (playPromise !== undefined) {
                            playPromise.catch(error => {
                                storeAsyncError('previousStop', error);
                            });
                        }
                        return `Previous Stop - playing audio-${currentStopIndex}${errorReport}`;
                    } catch (error) {
                        return `Previous Stop error - ${error.message} - audio-${currentStopIndex}${errorReport}`;
                    }
                }
                return `Previous Stop failed - audio-${currentStopIndex} not found${errorReport}`;
            }
            return `Already at first stop - currentStop:${currentStopIndex}${errorReport}`;
        };
        
        window.repeatStop = function() {
            const errorReport = getErrorReport();
            const audio = document.getElementById(`audio-${currentStopIndex}`);
            if (audio) {
                try {
                    audio.currentTime = 0;
                    const playPromise = audio.play();
                    if (playPromise !== undefined) {
                        playPromise.catch(error => {
                            storeAsyncError('repeatStop', error);
                        });
                    }
                    return `Repeating Stop - reset and playing audio-${currentStopIndex}${errorReport}`;
                } catch (error) {
                    return `Repeat Stop error - ${error.message} - audio-${currentStopIndex}${errorReport}`;
                }
            }
            return `No audio to repeat - audio-${currentStopIndex} not found${errorReport}`;
        };
        
        // DEBUG: Initialize command for testing
        window.initializeAudio = function() {
            const totalAudios = document.querySelectorAll('audio').length;
            return `Initialized - found ${totalAudios} audio elements, currentStop:${currentStopIndex}`;
        };
    </script>
</body>
</html>
"""
    
    # Save the HTML file in current directory
    output_file = f"{tour_directory}_single_file.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"DEBUG: Created single file: {output_file}")
    return output_file

if __name__ == "__main__":
    if len(sys.argv) > 1:
        tour_dir = sys.argv[1]
    else:
        tour_dir = input("Enter tour directory name: ")
    
    create_single_file_app(tour_dir)