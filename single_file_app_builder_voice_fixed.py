"""
Fixed version of single_file_app_builder.py with proper voice control audio initialization
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
    
    # Complete the HTML with FIXED voice control functions
    html_content += """        </div>
    </div>

    <script>
        let audioElements = [];
        let currentStopIndex = 0;
        let audioInitialized = false;
        
        // Initialize audioElements array by finding existing elements
        function initializeAudioElements() {
            audioElements = [];
            const audioTags = document.querySelectorAll('audio');
            audioTags.forEach((audio, index) => {
                audioElements.push(audio);
                
                // CRITICAL: Add the missing event listeners that were in the old dynamic code
                audio.addEventListener('play', function() {
                    initializeAudioContext(); // ← This was the missing key!
                    currentStopIndex = index;
                    // Pause other audio when one starts playing
                    audioElements.forEach((otherAudio, otherIndex) => {
                        if (otherIndex !== index && !otherAudio.paused) {
                            otherAudio.pause();
                        }
                    });
                });
                
                // Handle loading events for debugging
                audio.addEventListener('loadedmetadata', function() {
                    console.log(`Audio ${index + 1} metadata loaded`);
                });
                
                audio.addEventListener('canplaythrough', function() {
                    console.log(`Audio ${index + 1} ready to play`);
                });
            });
            console.log("VOICE: Found", audioElements.length, "audio elements with event listeners attached");
        }
        
        // Initialize audio context on first user interaction
        function initializeAudioContext() {
            if (!audioInitialized && audioElements.length > 0) {
                console.log("VOICE: Initializing audio context for", audioElements.length, "elements");
                // Try to load and prepare first audio element
                audioElements.forEach((audio, index) => {
                    audio.load();
                    // Set volume to ensure it's audible
                    audio.volume = 1.0;
                    console.log("VOICE: Audio element", index + 1, "loaded and volume set");
                });
                audioInitialized = true;
                console.log("VOICE: Audio context initialization complete");
            } else if (audioInitialized) {
                console.log("VOICE: Audio context already initialized");
            } else {
                console.log("VOICE: No audio elements found for initialization");
            }
        }
        
        // Pause all audio elements
        function pauseAllAudio() {
            audioElements.forEach(audio => {
                if (!audio.paused) {
                    audio.pause();
                }
            });
        }
        
        // Mobile app integration - FIXED functions for voice control
        window.playAudio = function() {
            initializeAudioContext();
            
            // CRITICAL: Auto-unlock audio context on first play command
            if (!audioInitialized && audioElements.length > 0) {
                try {
                    const firstAudio = audioElements[0];
                    firstAudio.muted = true;
                    firstAudio.play().then(() => {
                        setTimeout(() => {
                            firstAudio.pause();
                            firstAudio.currentTime = 0;
                            firstAudio.muted = false;
                            audioInitialized = true;
                            console.log("VOICE: Audio context auto-unlocked on first play");
                            // Now play the requested audio
                            if (audioElements[currentStopIndex]) {
                                const audio = audioElements[currentStopIndex];
                                pauseAllAudio();
                                setTimeout(() => {
                                    audio.play().catch(e => console.log("Play error:", e));
                                }, 100);
                            }
                        }, 100);
                    }).catch(e => {
                        console.log("VOICE: Auto-unlock failed:", e);
                        firstAudio.muted = false;
                    });
                    return "Playing Audio (unlocking context)";
                } catch (e) {
                    console.log("VOICE: Auto-unlock error:", e);
                }
            }
            
            if (audioElements[currentStopIndex]) {
                const audio = audioElements[currentStopIndex];
                pauseAllAudio();
                // Small delay to ensure pause completes
                setTimeout(() => {
                    // CRITICAL: Simulate DOM click instead of audio.play() to bypass WebView restrictions
                    try {
                        const clickEvent = new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        });
                        audio.dispatchEvent(clickEvent);
                        console.log("VOICE: Simulated click on audio element");
                    } catch (e) {
                        console.log("VOICE: Click simulation failed, trying play():", e);
                        audio.play().catch(e2 => console.log("Play error:", e2));
                    }
                }, 50);
                return "Playing Audio";
            }
            return "No audio to play";
        };
        
        window.pauseAudio = function() {
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].pause();
                return "Audio Paused";
            }
            return "No audio to pause";
        };
        
        window.nextStop = function() {
            initializeAudioContext();
            if (currentStopIndex < audioElements.length - 1) {
                pauseAllAudio();
                currentStopIndex++;
                const audio = audioElements[currentStopIndex];
                // Small delay to ensure pause completes
                setTimeout(() => {
                    // CRITICAL: Simulate DOM click for next stop
                    try {
                        const clickEvent = new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        });
                        audio.dispatchEvent(clickEvent);
                        console.log("VOICE: Simulated click for next stop");
                    } catch (e) {
                        console.log("VOICE: Click simulation failed, trying play():", e);
                        audio.play().catch(e2 => console.log("Play error:", e2));
                    }
                }, 50);
                return "Next Stop";
            }
            return "Already at last stop";
        };
        
        window.previousStop = function() {
            initializeAudioContext();
            if (currentStopIndex > 0) {
                pauseAllAudio();
                currentStopIndex--;
                const audio = audioElements[currentStopIndex];
                // Small delay to ensure pause completes
                setTimeout(() => {
                    // CRITICAL: Simulate DOM click for previous stop
                    try {
                        const clickEvent = new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        });
                        audio.dispatchEvent(clickEvent);
                        console.log("VOICE: Simulated click for previous stop");
                    } catch (e) {
                        console.log("VOICE: Click simulation failed, trying play():", e);
                        audio.play().catch(e2 => console.log("Play error:", e2));
                    }
                }, 50);
                return "Previous Stop";
            }
            return "Already at first stop";
        };
        
        window.repeatStop = function() {
            initializeAudioContext();
            if (audioElements[currentStopIndex]) {
                const audio = audioElements[currentStopIndex];
                pauseAllAudio();
                audio.currentTime = 0;
                // Small delay to ensure pause completes
                setTimeout(() => {
                    // CRITICAL: Simulate DOM click for repeat stop
                    try {
                        const clickEvent = new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        });
                        audio.dispatchEvent(clickEvent);
                        console.log("VOICE: Simulated click for repeat stop");
                    } catch (e) {
                        console.log("VOICE: Click simulation failed, trying play():", e);
                        audio.play().catch(e2 => console.log("Play error:", e2));
                    }
                }, 50);
                return "Repeating Stop";
            }
            return "No audio to repeat";
        };
        
        // DEBUG: Initialize command for testing
        window.initializeAudio = function() {
            const wasInitialized = audioInitialized;
            initializeAudioContext();
            
            // CRITICAL: Trigger user interaction to bypass autoplay restrictions
            if (!wasInitialized && audioElements.length > 0) {
                try {
                    // Simulate a brief play/pause to unlock audio context
                    const firstAudio = audioElements[0];
                    firstAudio.muted = true; // Mute to avoid sound
                    firstAudio.play().then(() => {
                        setTimeout(() => {
                            firstAudio.pause();
                            firstAudio.currentTime = 0;
                            firstAudio.muted = false; // Unmute for future playback
                            console.log("VOICE: Audio context unlocked via user interaction");
                        }, 100);
                    }).catch(e => {
                        console.log("VOICE: Audio unlock failed:", e);
                        firstAudio.muted = false;
                    });
                    return "Initialized and Unlocked (" + audioElements.length + " elements)";
                } catch (e) {
                    console.log("VOICE: Audio unlock error:", e);
                    return "Initialized (" + audioElements.length + " elements, unlock failed)";
                }
            }
            
            if (wasInitialized) {
                return "Already Initialized (" + audioElements.length + " elements)";
            } else {
                return "Initialized (" + audioElements.length + " elements loaded)";
            }
        };
        
        // Initialize when DOM is ready
        document.addEventListener('DOMContentLoaded', function() {
            initializeAudioElements();
            // Initialize audio context on any user interaction
            document.addEventListener('click', initializeAudioContext, { once: true });
            document.addEventListener('touchstart', initializeAudioContext, { once: true });
        });
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