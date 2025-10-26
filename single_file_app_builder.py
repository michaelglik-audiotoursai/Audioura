"""
Simplified version of single_file_app_builder.py with direct HTML element clicking
"""
import os
import sys
import glob
import base64
import re

def _extract_stop_titles(directory_name):
    """
    Extract stop titles from the original tour text file.
    
    Args:
        directory_name: Name of the directory (also the base name of the tour file)
    
    Returns:
        List of stop titles
    """
    try:
        # Look for the original tour text file
        tour_file = f"{directory_name}.txt"
        if not os.path.exists(tour_file):
            print(f"DEBUG: Original tour file {tour_file} not found")
            return []
        
        # Read the tour file
        with open(tour_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split content by "Stop X:" pattern and extract titles
        stops = re.split(r'\n\s*Stop\s+(\d+):\s*', content)
        
        stop_titles = []
        # Process stops in pairs (number, content)
        for i in range(1, len(stops), 2):
            if i + 1 < len(stops):
                stop_content = stops[i + 1].strip()
                # Extract the first line as the title
                lines = stop_content.split('\n')
                if lines:
                    title = lines[0].strip()
                    # Clean up the title (remove markdown, extra whitespace, periods)
                    title = re.sub(r'^\*\*"?', '', title)  # Remove leading **"
                    title = re.sub(r'"?\*\*$', '', title)  # Remove trailing "**
                    title = re.sub(r'^\d+\.\s*', '', title)  # Remove leading numbers
                    title = title.strip('.')
                    stop_titles.append(title)
        
        return stop_titles
        
    except Exception as e:
        print(f"DEBUG: Error extracting stop titles: {e}")
        return []

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
    
    # Extract stop titles from the original tour text
    stop_titles = _extract_stop_titles(tour_directory)
    print(f"DEBUG: Single file builder extracted {len(stop_titles)} stop titles: {stop_titles}")
    
    # Generate audio elements directly in HTML
    for i, mp3_file in enumerate(mp3_files):
        basename = os.path.basename(mp3_file)
        # Extract stop number
        parts = basename.replace('.mp3', '').split('_')
        if len(parts) >= 2:
            stop_num = parts[1]
        else:
            stop_num = str(i + 1)
        
        # Use extracted stop title or fallback
        if i < len(stop_titles):
            stop_title = f"{stop_titles[i]}: Audio {stop_num}"
        else:
            stop_title = f"Stop {stop_num}: Audio {stop_num}"
        
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
        
        // Voice control functions with proper audio control
        let audioElements = [];
        let wasPlayingBeforeVoice = false;
        
        // Initialize audio elements array
        document.addEventListener('DOMContentLoaded', function() {
            const audios = document.querySelectorAll('audio');
            audioElements = Array.from(audios);
            
            // Add event listeners to track manual play
            audioElements.forEach((audio, index) => {
                audio.addEventListener('play', function() {
                    currentStopIndex = index;
                });
            });
        });
        
        // Core audio control - stops other audio first
        window.playAudio = function() {
            const errorReport = getErrorReport();
            // Stop all other audio first
            audioElements.forEach((audio, index) => {
                if (index !== currentStopIndex) {
                    audio.pause();
                    audio.currentTime = 0;
                }
            });
            
            // Play current audio
            if (audioElements[currentStopIndex]) {
                try {
                    const playPromise = audioElements[currentStopIndex].play();
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
            return `No audio found - currentStop:${currentStopIndex}${errorReport}`;
        };
        
        window.pauseAudio = function() {
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].pause();
                return `Audio Paused - paused audio-${currentStopIndex}`;
            }
            return `No audio to pause - currentStop:${currentStopIndex}`;
        };
        
        // Pause for voice recognition
        window.pauseAllAudio = function() {
            wasPlayingBeforeVoice = false;
            if (audioElements[currentStopIndex] && !audioElements[currentStopIndex].paused) {
                wasPlayingBeforeVoice = true;
                audioElements[currentStopIndex].pause();
            }
            return "Success: Audio paused for voice recognition";
        };
        
        // Navigation - just change pointer, don't play
        window.nextStop = function() {
            const errorReport = getErrorReport();
            if (currentStopIndex < audioElements.length - 1) {
                // Stop all audio first
                audioElements.forEach(audio => audio.pause());
                currentStopIndex++;
                // Play the next audio
                try {
                    const playPromise = audioElements[currentStopIndex].play();
                    if (playPromise !== undefined) {
                        playPromise.catch(error => {
                            storeAsyncError('nextStop', error);
                        });
                    }
                    return `Success: Playing stop-${currentStopIndex}${errorReport}`;
                } catch (error) {
                    return `Error: ${error.message} - stop-${currentStopIndex}${errorReport}`;
                }
            }
            return `Error: Already at last stop${errorReport}`;
        };
        
        window.previousStop = function() {
            const errorReport = getErrorReport();
            if (currentStopIndex > 0) {
                // Stop all audio first
                audioElements.forEach(audio => audio.pause());
                currentStopIndex--;
                // Play the previous audio
                try {
                    const playPromise = audioElements[currentStopIndex].play();
                    if (playPromise !== undefined) {
                        playPromise.catch(error => {
                            storeAsyncError('previousStop', error);
                        });
                    }
                    return `Success: Playing stop-${currentStopIndex}${errorReport}`;
                } catch (error) {
                    return `Error: ${error.message} - stop-${currentStopIndex}${errorReport}`;
                }
            }
            return `Error: Already at first stop${errorReport}`;
        };
        
        // Reset current audio to beginning
        window.repeatStop = function() {
            const errorReport = getErrorReport();
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].currentTime = 0;
                return `Success: Reset stop-${currentStopIndex} to beginning${errorReport}`;
            }
            return `Error: No audio to reset${errorReport}`;
        };
        
        // Seek forward/backward in current audio with bounds checking
        window.seekForward = function(seconds = 10) {
            if (audioElements[currentStopIndex]) {
                const audio = audioElements[currentStopIndex];
                const newTime = audio.currentTime + seconds;
                const maxTime = audio.duration || 0;
                
                if (newTime >= maxTime) {
                    audio.currentTime = maxTime - 1;
                    return `Success: Moved to near end (${seconds}s would exceed duration)`;
                } else {
                    audio.currentTime = newTime;
                    return `Success: Moved forward ${seconds} seconds`;
                }
            }
            return "Error: No audio to seek";
        };
        
        window.seekBackward = function(seconds = 10) {
            if (audioElements[currentStopIndex]) {
                const audio = audioElements[currentStopIndex];
                const newTime = audio.currentTime - seconds;
                
                if (newTime < 0) {
                    audio.currentTime = 0;
                    return `Success: Moved to beginning (${seconds}s would go below 0)`;
                } else {
                    audio.currentTime = newTime;
                    return `Success: Moved backward ${seconds} seconds`;
                }
            }
            return "Error: No audio to seek";
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