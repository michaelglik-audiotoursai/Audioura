"""
Enhanced single_file_app_builder.py with voice control support
Adds unique IDs and JavaScript functions for reliable voice commands
"""
import os
import sys
import glob
import base64

def create_single_file_app_with_voice(tour_directory):
    """Create a single HTML file with embedded audio and voice control support."""
    current_dir = os.getcwd()
    print(f"DEBUG: single_file_app_builder_voice working in: {current_dir}")
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
            if '_' in basename:
                number_part = basename.split('_')[1].split('.')[0]
                return int(number_part)
            else:
                return 0
        except (ValueError, IndexError):
            return 0
    
    mp3_files.sort(key=get_stop_number)
    
    # Create title from directory name
    title = tour_directory.replace("_", " ").title()
    
    # Start building HTML content with voice control support
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
        .voice-status {{
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
        <div class="voice-status">
            Voice Control Ready! Use triple volume press or mic button.
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
        
        # Add to HTML
        html_content += f"""            {{
                stopNumber: {stop_num},
                title: "{stop_title}",
                data: "data:audio/mpeg;base64,{mp3_data}"
            }},
"""
    
    # Remove the last comma
    html_content = html_content.rstrip(",\n") + "\n"
    
    # Complete the HTML with voice control functions
    html_content += """        ];
        
        let currentStopIndex = 0;
        let audioElements = [];
        let totalStops = audioData.length;
        
        // Audio Control ID System - Initialize on page load
        window.audioControlIds = []; // Array of audio element IDs
        window.audioPlayingLast = 0;  // Index of last played audio (0-based)
        
        // Global state for voice control
        window.voiceControlState = {
            currentStop: 0,
            totalStops: totalStops,
            isPlaying: false,
            tourTitle: '{title}'
        };
        
        // ID-Based Voice Control Functions
        window.getAudioById = function(audioId) {
            return document.getElementById(audioId);
        };
        
        window.playCurrentStop = function() {
            if (audioElements.length > 0 && window.audioPlayingLast < audioElements.length) {
                const audioElement = audioElements[window.audioPlayingLast];
                if (audioElement) {
                    // Pause all first
                    audioElements.forEach(audio => audio.pause());
                    audioElement.play();
                    console.log('Voice: Playing audio at index', window.audioPlayingLast);
                    return 'SUCCESS: Playing stop ' + (window.audioPlayingLast + 1);
                }
            }
            return 'ERROR: No valid audio to play';
        };
        
        window.pauseAllAudio = function() {
            audioElements.forEach(audio => audio.pause());
            window.voiceControlState.isPlaying = false;
            console.log('Voice: Paused all audio');
            return 'SUCCESS: Paused all audio';
        };
        
        window.nextStop = function() {
            const nextIndex = window.audioPlayingLast + 1;
            if (nextIndex < audioElements.length) {
                window.audioPlayingLast = nextIndex;
            } else {
                // Wrap to first audio
                window.audioPlayingLast = 0;
            }
            return window.playCurrentStop();
        };
        
        window.previousStop = function() {
            const prevIndex = window.audioPlayingLast - 1;
            if (prevIndex >= 0) {
                window.audioPlayingLast = prevIndex;
            } else {
                // Wrap to last audio
                window.audioPlayingLast = audioElements.length - 1;
            }
            return window.playCurrentStop();
        };
        
        window.repeatCurrentStop = function() {
            if (audioElements.length > 0 && window.audioPlayingLast < audioElements.length) {
                const audioElement = audioElements[window.audioPlayingLast];
                if (audioElement) {
                    audioElement.currentTime = 0;
                    audioElement.play();
                    console.log('Voice: Repeating audio at index', window.audioPlayingLast);
                    return 'SUCCESS: Repeating stop ' + (window.audioPlayingLast + 1);
                }
            }
            return 'ERROR: No audio to repeat';
        };
        
        window.goToStop = function(stopNumber) {
            const index = stopNumber - 1; // Convert to 0-based
            if (index >= 0 && index < audioElements.length) {
                window.audioPlayingLast = index;
                return window.playCurrentStop();
            } else {
                console.log('Voice: Invalid stop number', stopNumber);
                return 'ERROR: Invalid stop number ' + stopNumber + ' (valid: 1-' + audioElements.length + ')';
            }
        };
        
        window.getCurrentState = function() {
            return {
                ...window.voiceControlState,
                audioPlayingLast: window.audioPlayingLast,
                audioControlIds: window.audioControlIds,
                totalAudioControls: window.audioControlIds.length
            };
        };
        
        // Create audio elements
        document.addEventListener('DOMContentLoaded', function() {
            const container = document.getElementById('audio-container');
            container.innerHTML = ''; // Remove loading message
            
            audioData.forEach((item, index) => {
                const tourItem = document.createElement('div');
                tourItem.className = 'tour-item';
                tourItem.id = `stop-${item.stopNumber}`;
                
                const titleDiv = document.createElement('div');
                titleDiv.className = 'tour-title';
                titleDiv.textContent = item.title;
                
                const audio = document.createElement('audio');
                const audioId = `audio-${index + 1}`; // Use sequential index for consistent numbering
                audio.id = audioId;
                audio.controls = true;
                
                // Add to audio control ID array
                window.audioControlIds.push(audioId);
                
                const source = document.createElement('source');
                source.src = item.data;
                source.type = 'audio/mpeg';
                
                audio.appendChild(source);
                audioElements.push(audio);
                
                tourItem.appendChild(titleDiv);
                tourItem.appendChild(audio);
                container.appendChild(tourItem);
                
                // Preload audio
                audio.load();
                
                // Track current playing audio with state updates
                audio.addEventListener('play', function() {
                    currentStopIndex = index;
                    window.audioPlayingLast = index; // Update last played tracking
                    window.voiceControlState.currentStop = index + 1;
                    window.voiceControlState.isPlaying = true;
                    console.log('Voice: Auto-detected playing stop', index + 1, 'ID:', audioId);
                    // Pause other audio when one starts playing
                    audioElements.forEach((otherAudio, otherIndex) => {
                        if (otherIndex !== index) {
                            otherAudio.pause();
                        }
                    });
                });
                
                audio.addEventListener('pause', function() {
                    if (currentStopIndex === index) {
                        window.voiceControlState.isPlaying = false;
                        console.log('Voice: Auto-detected pause on stop', index + 1, 'ID:', audioId);
                    }
                });
                
                audio.addEventListener('ended', function() {
                    if (currentStopIndex === index) {
                        window.voiceControlState.isPlaying = false;
                        console.log('Voice: Audio ended on stop', index + 1, 'ID:', audioId);
                    }
                });
            });
            
            console.log('Voice control functions ready:', {
                playCurrentStop: window.playCurrentStop,
                pauseAllAudio: window.pauseAllAudio,
                nextStop: window.nextStop,
                previousStop: window.previousStop,
                repeatCurrentStop: window.repeatCurrentStop,
                goToStop: window.goToStop
            });
        });
    </script>
</body>
</html>
"""
    
    # Save the HTML file in current directory with expected filename pattern
    output_file = f"{tour_directory}_single_file.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"DEBUG: Created voice-enabled file: {output_file}")
    return output_file

if __name__ == "__main__":
    if len(sys.argv) > 1:
        tour_dir = sys.argv[1]
    else:
        tour_dir = input("Enter tour directory name: ")
    
    create_single_file_app_with_voice(tour_dir)