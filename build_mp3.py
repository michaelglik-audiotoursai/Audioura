"""
Module for converting text files to MP3 audio files.
"""
import os
import glob
os.environ["PATH"] += (
    os.pathsep + r"C:\Program Files (x86)\eSpeak\command_line"
)
from TTS.api import TTS
from pydub import AudioSegment

# Initialize TTS model
tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC")

def convert_text_to_mp3(input_file):
    """Convert text file to MP3 audio file."""
    base_name = os.path.splitext(input_file)[0]
    wav_file = f"{base_name}.wav"
    mp3_file = f"{base_name}.mp3"
    
    # Step 1: Read text file and convert to WAV
    with open(input_file, "r", encoding="utf-8") as f:
        text_file_input = f.read()
    
    # Get text file size
    txt_size = os.path.getsize(input_file)
    
    # Try up to 3 times if the WAV file is too large
    max_attempts = 3
    attempt = 1
    wav_size_ratio = float('inf')  # Initialize with infinity
    
    while attempt <= max_attempts and wav_size_ratio > 4500:
        print(f"Converting {input_file} to WAV... (Attempt {attempt}/{max_attempts})")
        tts.tts_to_file(text_file_input, file_path=wav_file)
        
        # Check WAV file size ratio
        if os.path.exists(wav_file):
            wav_size = os.path.getsize(wav_file)
            wav_size_ratio = wav_size / txt_size if txt_size > 0 else float('inf')
            
            if wav_size_ratio > 4500:
                print(f"WARNING: WAV file size ratio is high ({wav_size_ratio:.1f}x). Retrying...")
                attempt += 1
            else:
                break
        else:
            print(f"ERROR: WAV file {wav_file} was not created")
            return None
    
    # Issue warning if still problematic after all attempts
    if wav_size_ratio > 4500:
        print(f"WARNING: Potential audio garbling in {wav_file}")
        print(f"         Text size: {txt_size} bytes, WAV size: {wav_size} bytes, Ratio: {wav_size_ratio:.1f}x")
    
    # Step 2: Convert WAV to MP3
    print(f"Converting {wav_file} to MP3...")
    sound = AudioSegment.from_wav(wav_file)
    sound.export(mp3_file, format="mp3", bitrate="192k")
    
    print(f"Created {mp3_file}")
    return mp3_file

def process_directory(directory):
    """Process all text files in the specified directory."""
    # Save current directory
    original_dir = os.getcwd()
    
    try:
        # Change to the target directory
        os.chdir(directory)
        
        # Get all text files
        txt_files = glob.glob("audio_*.txt")
        
        if not txt_files:
            print(f"No audio text files found in {directory}")
            return
        
        # Convert each text file to MP3
        created_files = []
        for txt_file in txt_files:
            mp3_file = convert_text_to_mp3(txt_file)
            created_files.append(os.path.basename(mp3_file))
        
        # Print summary
        print(f"\nCreated {len(created_files)} MP3 files in {directory}:")
        for file in created_files:
            print(f"- {file}")
    
    finally:
        # Restore original directory
        os.chdir(original_dir)

if __name__ == "__main__":
    # Directory containing the text files
    tour_directory = "tour_newtonville_and_waban_heritage_trail"
    
    # Process the directory
    process_directory(tour_directory)