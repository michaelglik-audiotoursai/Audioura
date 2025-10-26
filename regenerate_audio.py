"""
Regenerate specific audio files with more attempts.
"""
import os
import sys
from TTS.api import TTS
from pydub import AudioSegment

# Initialize TTS model
os.environ["PATH"] += (
    os.pathsep + r"C:\Program Files (x86)\eSpeak\command_line"
)
tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC")

def regenerate_audio(txt_file, directory=None, max_attempts=10):
    """
    Regenerate WAV and MP3 files from a text file with multiple attempts.
    
    Args:
        txt_file: Name of the text file to process
        directory: Directory containing the text file (optional)
        max_attempts: Maximum number of attempts to generate a good WAV file
    """
    # Get current directory to ensure consistent paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Save original directory
    original_dir = os.getcwd()
    
    try:
        # Change to the specified directory if provided
        if directory:
            target_dir = os.path.join(script_dir, directory)
            if not os.path.exists(target_dir):
                print(f"Error: Directory '{directory}' not found")
                return
            os.chdir(target_dir)
            print(f"Changed to directory: {target_dir}")
        
        # Check if text file exists
        if not os.path.exists(txt_file):
            print(f"Error: Text file '{txt_file}' not found")
            return
        
        # Get base name and file paths
        base_name = os.path.splitext(txt_file)[0]
        wav_file = f"{base_name}.wav"
        mp3_file = f"{base_name}.mp3"
        
        # Read text file
        with open(txt_file, "r", encoding="utf-8") as f:
            text_content = f.read()
        
        # Get text file size
        txt_size = os.path.getsize(txt_file)
        print(f"Text file size: {txt_size} bytes")
        
        # Try multiple times to generate a good WAV file
        attempt = 1
        wav_size_ratio = float('inf')
        best_ratio = float('inf')
        best_wav_file = None
        
        print(f"Will try up to {max_attempts} times to generate a good WAV file")
        
        while attempt <= max_attempts:
            print(f"\nAttempt {attempt}/{max_attempts}:")
            
            # Generate WAV file with a unique name for this attempt
            temp_wav_file = f"{base_name}_attempt_{attempt}.wav"
            print(f"Generating WAV file: {temp_wav_file}")
            
            tts.tts_to_file(text_content, file_path=temp_wav_file)
            
            # Check WAV file size ratio
            if os.path.exists(temp_wav_file):
                wav_size = os.path.getsize(temp_wav_file)
                wav_size_ratio = wav_size / txt_size if txt_size > 0 else float('inf')
                
                print(f"WAV file size: {wav_size} bytes")
                print(f"Size ratio: {wav_size_ratio:.1f}x")
                
                # Keep track of the best attempt
                if wav_size_ratio < best_ratio:
                    best_ratio = wav_size_ratio
                    best_wav_file = temp_wav_file
                    print(f"This is the best attempt so far")
                
                # If ratio is good enough, use this file
                if wav_size_ratio <= 4500:
                    print(f"Good ratio achieved, using this file")
                    break
            else:
                print(f"Error: WAV file was not created")
            
            attempt += 1
        
        # Use the best attempt if no good ratio was achieved
        if wav_size_ratio > 4500 and best_wav_file:
            print(f"\nNo attempt achieved a good ratio. Using the best attempt with ratio {best_ratio:.1f}x")
            temp_wav_file = best_wav_file
        
        # Convert the best WAV to MP3
        print(f"\nConverting WAV to MP3...")
        sound = AudioSegment.from_wav(temp_wav_file)
        sound.export(mp3_file, format="mp3", bitrate="192k")
        
        # Copy the best WAV to the final WAV file
        import shutil
        shutil.copy2(temp_wav_file, wav_file)
        
        # Clean up temporary WAV files
        print(f"Cleaning up temporary files...")
        for i in range(1, attempt + 1):
            temp_file = f"{base_name}_attempt_{i}.wav"
            if os.path.exists(temp_file) and temp_file != temp_wav_file:
                os.remove(temp_file)
        
        print(f"\nRegeneration complete!")
        print(f"Final WAV file: {wav_file}")
        print(f"Final MP3 file: {mp3_file}")
        print(f"Final size ratio: {best_ratio:.1f}x")
        
        if best_ratio > 4500:
            print(f"WARNING: Final ratio is still high, audio may be garbled")
    
    finally:
        # Restore original directory
        os.chdir(original_dir)

if __name__ == "__main__":
    # Check if parameters were provided via command line
    if len(sys.argv) > 1:
        txt_file = sys.argv[1]
        directory = sys.argv[2] if len(sys.argv) > 2 else None
        max_attempts = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    else:
        # Get parameters via console input
        print("=== Audio File Regeneration Tool ===")
        
        # Get text file name
        txt_file = input("Enter the text file name (e.g., audio_8_early_entertainment_technology.txt): ")
        
        # Get directory name
        directory = input("Enter the directory name (press Enter to use current directory): ")
        if directory.strip() == "":
            directory = None
        
        # Get max attempts
        try:
            max_attempts_input = input("Enter maximum number of attempts (press Enter for default 10): ")
            max_attempts = int(max_attempts_input) if max_attempts_input.strip() else 10
        except ValueError:
            print("Invalid number, using default 10 attempts")
            max_attempts = 10
    
    # List available directories if needed
    if directory is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dirs = [d for d in os.listdir(script_dir) 
                if os.path.isdir(os.path.join(script_dir, d)) 
                and not d.startswith('.') 
                and not d.startswith('__')]
        
        if dirs:
            print("\nAvailable directories:")
            for i, d in enumerate(dirs, 1):
                print(f"{i}. {d}")
            
            try:
                choice = input("\nEnter directory number (or press Enter to skip): ")
                if choice.strip():
                    choice_num = int(choice)
                    if 1 <= choice_num <= len(dirs):
                        directory = dirs[choice_num-1]
                        print(f"Selected directory: {directory}")
            except ValueError:
                pass
    
    # Run the regeneration
    regenerate_audio(txt_file, directory, max_attempts)