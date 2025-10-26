"""
Fixed version of build_web_page.py that works in current directory
"""
import os
import glob

def generate_website(directory_name):
    """
    Generate a website with audio files. Works in current directory.
    
    Args:
        directory_name: Name of the directory containing audio files
    """
    current_dir = os.getcwd()
    print(f"DEBUG: build_web_page working in: {current_dir}")
    print(f"DEBUG: Looking for directory: {directory_name}")
    
    # Look for MP3 files in the directory (relative path)
    audio_dir = os.path.join(current_dir, directory_name)
    mp3_pattern = os.path.join(audio_dir, "*.mp3")
    
    print(f"Looking for MP3 files in: {audio_dir}")
    mp3_files = glob.glob(mp3_pattern)
    
    if not mp3_files:
        print(f"No audio MP3 files found in {audio_dir}")
        # List what files are actually there
        if os.path.exists(audio_dir):
            files_in_dir = os.listdir(audio_dir)
            print(f"Files in directory: {files_in_dir}")
        else:
            print(f"Directory {audio_dir} does not exist")
        return
    
    print(f"Found {len(mp3_files)} MP3 files")
    
    # Sort files
    mp3_files.sort()
    
    # Create simple index.html
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{directory_name.replace('_', ' ').title()}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .audio-item {{ margin: 20px 0; padding: 15px; border: 1px solid #ccc; }}
        audio {{ width: 100%; }}
    </style>
</head>
<body>
    <h1>{directory_name.replace('_', ' ').title()}</h1>
"""
    
    for i, mp3_file in enumerate(mp3_files, 1):
        filename = os.path.basename(mp3_file)
        html_content += f"""
    <div class="audio-item">
        <h3>Stop {i}: {filename.replace('.mp3', '').replace('_', ' ').title()}</h3>
        <audio controls>
            <source src="{filename}" type="audio/mpeg">
            Your browser does not support the audio element.
        </audio>
    </div>
"""
    
    html_content += """
    
    <script>
        let audioElements = [];
        let currentStopIndex = 0;
        let wasPlayingBeforeVoice = false;
        
        // Core audio control - always call this to play current audio
        window.playAudio = function() {
            // Stop all other audio first
            audioElements.forEach((audio, index) => {
                if (index !== currentStopIndex) {
                    audio.pause();
                    audio.currentTime = 0;
                }
            });
            
            // Play current audio
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].play();
                return "Success: Playing stop-" + currentStopIndex;
            }
            return "Error: No audio to play";
        };
        
        window.pauseAudio = function() {
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].pause();
                return "Success: Audio paused";
            }
            return "Error: No audio to pause";
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
            if (currentStopIndex < audioElements.length - 1) {
                currentStopIndex++;
                return "Success: Moved to stop-" + currentStopIndex;
            }
            return "Error: Already at last stop";
        };
        
        window.previousStop = function() {
            if (currentStopIndex > 0) {
                currentStopIndex--;
                return "Success: Moved to stop-" + currentStopIndex;
            }
            return "Error: Already at first stop";
        };
        
        // Reset current audio to beginning
        window.repeatStop = function() {
            if (audioElements[currentStopIndex]) {
                audioElements[currentStopIndex].currentTime = 0;
                return "Success: Reset stop-" + currentStopIndex + " to beginning";
            }
            return "Error: No audio to reset";
        };
        
        // Seek forward/backward in current audio with bounds checking
        window.seekForward = function(seconds = 10) {
            if (audioElements[currentStopIndex]) {
                const audio = audioElements[currentStopIndex];
                const newTime = audio.currentTime + seconds;
                const maxTime = audio.duration || 0;
                
                if (newTime >= maxTime) {
                    audio.currentTime = maxTime - 1; // 1 second before end
                    return "Success: Moved to near end (" + seconds + "s would exceed duration)";
                } else {
                    audio.currentTime = newTime;
                    return "Success: Moved forward " + seconds + " seconds";
                }
            }
            return "Error: No audio to seek";
        };
        
        window.seekBackward = function(seconds = 10) {
            if (audioElements[currentStopIndex]) {
                const audio = audioElements[currentStopIndex];
                const newTime = audio.currentTime - seconds;
                
                if (newTime < 0) {
                    audio.currentTime = 0; // Beginning of audio
                    return "Success: Moved to beginning (" + seconds + "s would go below 0)";
                } else {
                    audio.currentTime = newTime;
                    return "Success: Moved backward " + seconds + " seconds";
                }
            }
            return "Error: No audio to seek";
        };
        
        window.initializeAudio = function() {
            return "Success: Audio system initialized with " + audioElements.length + " stops";
        };
        
        // Initialize audio elements array
        document.addEventListener('DOMContentLoaded', function() {
            const audios = document.querySelectorAll('audio');
            audioElements = Array.from(audios);
            
            // Track current playing audio
            audioElements.forEach((audio, index) => {
                audio.addEventListener('play', function() {
                    currentStopIndex = index;
                });
            });
        });
    </script>
</body>
</html>
"""
    
    # Save index.html in the directory
    index_file = os.path.join(audio_dir, "index.html")
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"DEBUG: Created index.html at: {index_file}")
    
    # Also rename MP3 files to audio_X.mp3 format for single_file_app_builder
    for i, mp3_file in enumerate(mp3_files, 1):
        old_path = mp3_file
        new_filename = f"audio_{i}.mp3"
        new_path = os.path.join(audio_dir, new_filename)
        
        if old_path != new_path:
            os.rename(old_path, new_path)
            print(f"DEBUG: Renamed {os.path.basename(old_path)} to {new_filename}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        directory = input("Enter directory name: ")
    
    generate_website(directory)