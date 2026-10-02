#!/usr/bin/env python3
"""
Amazon Polly TTS Service - Alternative TTS provider with higher rate limits
"""
import os
import boto3
from flask import Flask, request, jsonify, send_file as _send_file
import inspect as _inspect
import tempfile
import logging
from botocore.exceptions import ClientError, BotoCoreError


def _compat_send_file(path_or_file, **kwargs):
    """Version-tolerant send_file wrapper.

    Flask <2.0 uses ``attachment_filename``; Flask >=2.0 renamed it to
    ``download_name``.  This helper accepts either and maps to whichever the
    installed Flask supports, so the same code runs on both.
    """
    sig = _inspect.signature(_send_file)
    params = sig.parameters

    download_name = kwargs.pop("download_name", None)
    attachment_filename = kwargs.pop("attachment_filename", None)
    name = download_name or attachment_filename

    if name:
        if "download_name" in params:
            kwargs["download_name"] = name
        else:
            kwargs["attachment_filename"] = name

    return _send_file(path_or_file, **kwargs)


send_file = _compat_send_file

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
    # [LOCAL-323] Neural voice list — must match Engine selection below
    NEURAL_VOICES = frozenset(['Joanna', 'Matthew', 'Amy', 'Brian'])

    try:
        if not polly_client:
            return jsonify({"error": "Polly client not available"}), 500
            
        data = request.get_json()
        text = data.get('text', '')
        voice_id = data.get('voice_id', 'Joanna')  # Default female voice
        output_format = data.get('output_format', 'mp3')
        # [LOCAL-323] Optional metering fields — callers pass these for attribution
        user_id = data.get('user_id')
        job_id = data.get('job_id')
        
        if not text:
            return jsonify({"error": "No text provided"}), 400

        engine = 'neural' if voice_id in NEURAL_VOICES else 'standard'
        logging.info(f"Synthesizing {len(text)} characters with voice {voice_id} (engine={engine})")
        
        # Track total characters actually submitted to Polly
        total_chars_submitted = 0

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
                total_chars_submitted += len(chunk)
                response = polly_client.synthesize_speech(
                    Text=chunk,
                    OutputFormat=output_format,
                    VoiceId=voice_id,
                    Engine=engine
                )
                audio_segments.append(response['AudioStream'].read())
            
            # Combine all audio segments
            combined_audio = b''.join(audio_segments)
        else:
            # Single request for short text
            total_chars_submitted = len(text)
            response = polly_client.synthesize_speech(
                Text=text,
                OutputFormat=output_format,
                VoiceId=voice_id,
                Engine=engine
            )
            combined_audio = response['AudioStream'].read()
        
        # [LOCAL-323] Meter TTS cost — non-fatal, in its own try block.
        # Pattern matches generate_tour_text_service.py: metering must never break delivery.
        try:
            from cost_meter import record_operation
            from cost_rates import tts_cost
            _tts_cost = tts_cost(total_chars_submitted, engine=engine)
            record_operation(
                operation_type="tts_generate",
                our_cost_usd=_tts_cost,
                cache_hit=False,
                user_id=user_id,
                job_id=job_id,
                breakdown={
                    "chars": total_chars_submitted,
                    "engine": engine,
                    "voice_id": voice_id,
                },
            )
            logging.info(f"[LOCAL-323] TTS metered: {total_chars_submitted} chars, engine={engine}, cost=${_tts_cost:.6f}")
        except Exception as _meter_err:
            logging.warning(f"[LOCAL-323] TTS cost metering failed (non-fatal): {_meter_err}")

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
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5018')), debug=False)