"""
Simple MP3 builder using Polly TTS service
"""
import os
import glob
import requests

def process_directory(directory_name):
    """
    Process all text files in a directory and convert them to MP3 using gTTS.
    
    Args:
        directory_name: Name of the directory containing text files
    """
    print(f"Processing directory: {directory_name}")
    
    # Find all text files in the directory
    text_files = glob.glob(os.path.join(directory_name, "*.txt"))
    
    if not text_files:
        print(f"No text files found in {directory_name}")
        return
    
    print(f"Found {len(text_files)} text files")
    
    for text_file in text_files:
        try:
            # Read the text content
            with open(text_file, 'r', encoding='utf-8') as f:
                text_content = f.read().strip()
            
            if not text_content:
                print(f"Skipping empty file: {text_file}")
                continue
            
            # Generate MP3 filename
            base_name = os.path.splitext(os.path.basename(text_file))[0]
            mp3_file = os.path.join(directory_name, f"{base_name}.mp3")
            
            print(f"Converting {text_file} to {mp3_file}")
            
            # Generate audio using Polly TTS service
            response = requests.post(
                'http://localhost:5018/synthesize',
                json={
                    'text': text_content,
                    'voice_id': 'Joanna',
                    'output_format': 'mp3'
                },
                timeout=300
            )
            
            if response.status_code == 200:
                with open(mp3_file, 'wb') as f:
                    f.write(response.content)
            else:
                raise Exception(f"Polly TTS failed: {response.status_code}")
            
            print(f"Successfully created: {mp3_file}")
            
        except Exception as e:
            print(f"Error processing {text_file}: {str(e)}")
            continue
    
    print(f"Finished processing directory: {directory_name}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        directory = input("Enter directory name: ")
    
    process_directory(directory)