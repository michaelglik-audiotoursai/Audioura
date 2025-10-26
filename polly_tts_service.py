#!/usr/bin/env python3
"""
Amazon Polly TTS Service - Alternative TTS provider with higher rate limits
"""
import os
import boto3
from flask import Flask, request, jsonify, send_file
import tempfile
import logging
from botocore.exceptions import ClientError, BotoCoreError

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

# Initialize Polly client
try:
    polly_client = boto3.client(
        'polly',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_REGION', 'us-east-1')
    )
    logging.info("Polly client initialized successfully")
except Exception as e:
    logging.error(f"Failed to initialize Polly client: {e}")
    polly_client = None

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy" if polly_client else "unhealthy",
        "service": "polly_tts",
        "polly_available": polly_client is not None
    })

@app.route('/synthesize', methods=['POST'])
def synthesize_speech():
    try:
        if not polly_client:
            return jsonify({"error": "Polly client not available"}), 500
            
        data = request.get_json()
        text = data.get('text', '')
        voice_id = data.get('voice_id', 'Joanna')  # Default female voice
        output_format = data.get('output_format', 'mp3')
        
        if not text:
            return jsonify({"error": "No text provided"}), 400
            
        logging.info(f"Synthesizing {len(text)} characters with voice {voice_id}")
        
        # Split text if too long (use 2000 char limit for safety)
        if len(text) > 2000:
            logging.info(f"Text too long ({len(text)} chars), splitting by sentences")
            
            import re
            sentences = re.split(r'(?<=[.!?])\s+', text)
            
            chunks = []
            current_chunk = ""
            
            # Simple word-by-word chunking to avoid complex logic
            all_words = text.split()
            
            for word in all_words:
                # Skip extremely long words that would break chunking
                if len(word) > 100:
                    logging.warning(f"Long word found ({len(word)} chars): {word[:100]}...")
                    if len(word) > 1900:
                        logging.warning(f"Skipping extremely long word: {len(word)} chars")
                        continue
                    
                word_separator_length = 1 if current_chunk else 0
                if len(current_chunk) + len(word) + word_separator_length > 2000 and current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = word
                else:
                    current_chunk += " " + word if current_chunk else word
            
            # Add final chunk
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            # Validate chunks
            for i, chunk in enumerate(chunks):
                if len(chunk) > 2000:
                    logging.warning(f"Chunk {i+1} exceeds 2000 chars: {len(chunk)}")
            
            audio_segments = []
            
            for i, chunk in enumerate(chunks):
                logging.info(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
                response = polly_client.synthesize_speech(
                    Text=chunk,
                    OutputFormat=output_format,
                    VoiceId=voice_id,
                    Engine='neural' if voice_id in ['Joanna', 'Matthew', 'Amy', 'Brian'] else 'standard'
                )
                audio_segments.append(response['AudioStream'].read())
            
            # Combine all audio segments
            combined_audio = b''.join(audio_segments)
        else:
            # Single request for short text
            response = polly_client.synthesize_speech(
                Text=text,
                OutputFormat=output_format,
                VoiceId=voice_id,
                Engine='neural' if voice_id in ['Joanna', 'Matthew', 'Amy', 'Brian'] else 'standard'
            )
            combined_audio = response['AudioStream'].read()
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{output_format}') as tmp_file:
            tmp_file.write(combined_audio)
            tmp_filename = tmp_file.name
            
        logging.info(f"Audio synthesized successfully: {tmp_filename}")
        
        return send_file(
            tmp_filename,
            as_attachment=True,
            download_name=f'speech.{output_format}',
            mimetype=f'audio/{output_format}'
        )
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'Throttling':
            logging.error("Polly rate limit exceeded")
            return jsonify({"error": "Rate limit exceeded"}), 429
        else:
            logging.error(f"Polly client error: {e}")
            return jsonify({"error": f"Polly error: {error_code}"}), 500
            
    except Exception as e:
        logging.error(f"Error synthesizing speech: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/voices', methods=['GET'])
def list_voices():
    """List available Polly voices"""
    try:
        if not polly_client:
            return jsonify({"error": "Polly client not available"}), 500
            
        response = polly_client.describe_voices()
        voices = []
        
        for voice in response['Voices']:
            voices.append({
                'id': voice['Id'],
                'name': voice['Name'],
                'gender': voice['Gender'],
                'language': voice['LanguageCode'],
                'engine': voice.get('SupportedEngines', ['standard'])
            })
            
        return jsonify({"voices": voices})
        
    except Exception as e:
        logging.error(f"Error listing voices: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5018, debug=True)