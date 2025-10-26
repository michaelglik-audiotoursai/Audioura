#!/usr/bin/env python3
"""
Voice Control Service - Processes voice commands for audio tours
"""
import os
import json
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy", 
        "service": "voice_control",
        "description": "Voice command processing service"
    })

@app.route('/process-voice-command', methods=['POST'])
def process_voice_command():
    """Process voice command and return action."""
    try:
        data = request.get_json()
        voice_text = data.get('text', '').lower().strip()
        current_stop = data.get('current_stop', 0)
        total_stops = data.get('total_stops', 10)
        
        print(f"Processing voice command: '{voice_text}'")
        
        # Check for "next stop" command
        if 'next stop' in voice_text or 'next' in voice_text:
            next_stop = current_stop + 1
            if next_stop < total_stops:
                return jsonify({
                    'action': 'next_stop',
                    'stop_number': next_stop,
                    'message': f'Moving to stop {next_stop + 1}'
                })
            else:
                return jsonify({
                    'action': 'end_of_tour',
                    'message': 'You are at the last stop'
                })
        
        # Check for "previous stop" command
        elif 'previous stop' in voice_text or 'previous' in voice_text or 'back' in voice_text:
            prev_stop = current_stop - 1
            if prev_stop >= 0:
                return jsonify({
                    'action': 'previous_stop',
                    'stop_number': prev_stop,
                    'message': f'Moving to stop {prev_stop + 1}'
                })
            else:
                return jsonify({
                    'action': 'start_of_tour',
                    'message': 'You are at the first stop'
                })
        
        # Check for "repeat" command
        elif 'repeat' in voice_text or 'again' in voice_text:
            return jsonify({
                'action': 'repeat_stop',
                'stop_number': current_stop,
                'message': f'Repeating stop {current_stop + 1}'
            })
        
        # Check for "pause" command
        elif 'pause' in voice_text or 'stop' in voice_text:
            return jsonify({
                'action': 'pause',
                'message': 'Pausing audio'
            })
        
        # Check for "play" command
        elif 'play' in voice_text or 'resume' in voice_text:
            return jsonify({
                'action': 'play',
                'message': 'Resuming audio'
            })
        
        else:
            return jsonify({
                'action': 'unknown',
                'message': 'Command not recognized. Try "next stop", "previous", "repeat", "pause", or "play"'
            })
            
    except Exception as e:
        print(f"Error processing voice command: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting Voice Control Service...")
    app.run(host='0.0.0.0', port=5008, debug=True)