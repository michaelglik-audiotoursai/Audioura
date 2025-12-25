#!/usr/bin/env python3
"""
Extract actual tour content from HTML
"""
import re
import base64
import tempfile
import os
from pydub import AudioSegment
import speech_recognition as sr

def extract_tour_content():
    # Read the HTML file
    with open('/tmp/russian_index.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Find all base64 audio data
    audio_pattern = r'data:audio/[^;]+;base64,([A-Za-z0-9+/=]+)'
    audio_matches = re.findall(audio_pattern, html_content)
    
    print(f"Found {len(audio_matches)} audio segments")
    
    # Decode first few audio segments to extract text
    for i, audio_base64 in enumerate(audio_matches[:3]):
        try:
            # Decode base64 to audio bytes
            audio_bytes = base64.b64decode(audio_base64)
            
            # Save as MP3 file
            audio_file = f'/tmp/tour_audio_{i+1}.mp3'
            with open(audio_file, 'wb') as f:
                f.write(audio_bytes)
            
            print(f"Audio {i+1}: {len(audio_bytes)} bytes saved to {audio_file}")
            
            # Try to extract text using speech recognition (if available)
            # This would show us what the actual tour content is
            
        except Exception as e:
            print(f"Error processing audio {i+1}: {e}")

if __name__ == '__main__':
    extract_tour_content()