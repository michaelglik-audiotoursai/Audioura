#!/usr/bin/env python3
"""
Voice NLP Service - Converts natural language to search patterns
"""
import os
from flask import Flask, request, jsonify
import requests
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "voice_nlp"})

@app.route('/generate_short_title', methods=['POST'])
def generate_short_title():
    """Generate AI-shortened title with metadata"""
    try:
        data = request.get_json()
        original_title = data.get('original_title', '').strip()
        article_type = data.get('article_type', 'Others')
        max_words = data.get('max_words', 12)
        
        if not original_title:
            return jsonify({"error": "No original title provided"}), 400
        
        logging.info(f"Generating short title for: {original_title}")
        
        # Try AI generation first
        ai_result = _generate_short_title_with_ai(original_title, max_words)
        if ai_result:
            return jsonify({
                "status": "success",
                "short_title": ai_result,
                "author": "AudioTours AI",
                "method": "ai"
            })
        
        # Fallback to simple truncation
        words = original_title.split()
        short_title = ' '.join(words[:max_words])
        if len(words) > max_words:
            short_title += '...'
        
        return jsonify({
            "status": "success",
            "short_title": short_title,
            "author": "AudioTours",
            "method": "truncation"
        })
        
    except Exception as e:
        logging.error(f"Error generating short title: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/parse_voice_search', methods=['POST'])
def parse_voice_search():
    """Convert natural language voice command to search pattern"""
    try:
        data = request.get_json()
        voice_command = data.get('voice_command', '').strip()
        
        if not voice_command:
            return jsonify({"error": "No voice command provided"}), 400
        
        logging.info(f"Processing voice command: {voice_command}")
        
        # Try AI conversion first
        ai_result = _convert_with_ai(voice_command)
        if ai_result:
            return jsonify({
                "status": "success",
                "search_pattern": ai_result,
                "method": "ai",
                "original_command": voice_command
            })
        
        # Fallback to pattern matching
        pattern_result = _convert_with_patterns(voice_command)
        return jsonify({
            "status": "success", 
            "search_pattern": pattern_result,
            "method": "patterns",
            "original_command": voice_command
        })
        
    except Exception as e:
        logging.error(f"Error parsing voice search: {e}")
        return jsonify({"error": str(e)}), 500

def _convert_with_ai(voice_command):
    """Use OpenAI to convert natural language to search pattern"""
    try:
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if not openai_api_key:
            logging.warning("No OpenAI API key found, skipping AI conversion")
            return None
        
        prompt = f"""Convert this voice command to a search pattern using this format:
- Include terms: just the word (space separated)
- Exclude terms: -word
- Phrases: "exact phrase"

Examples:
"Find articles about Boston" → boston
"Next article with Microsoft and earnings" → microsoft earnings  
"Play something about Tesla but not stock" → tesla -stock
"Articles with artificial intelligence but not Google" → "artificial intelligence" -google

Voice command: "{voice_command}"
Search pattern:"""

        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {openai_api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'gpt-3.5-turbo',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 50,
                'temperature': 0.1
            },
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()
            search_pattern = result['choices'][0]['message']['content'].strip()
            logging.info(f"AI converted '{voice_command}' to '{search_pattern}'")
            return search_pattern
        else:
            logging.warning(f"OpenAI API error: {response.status_code}")
            return None
            
    except Exception as e:
        logging.error(f"AI conversion error: {e}")
        return None

def _generate_short_title_with_ai(original_title, max_words):
    """Use OpenAI to generate a concise title"""
    try:
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if not openai_api_key:
            logging.warning("No OpenAI API key found, skipping AI title generation")
            return None
        
        prompt = f"""Create a concise, engaging title from this article title. Keep it to {max_words} words maximum while preserving the key information and making it compelling for audio listeners.

Original title: "{original_title}"

Short title (max {max_words} words):"""

        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {openai_api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'gpt-3.5-turbo',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 60,
                'temperature': 0.3
            },
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            short_title = result['choices'][0]['message']['content'].strip()
            # Remove quotes if AI added them
            short_title = short_title.strip('"')
            logging.info(f"AI generated short title: '{short_title}' from '{original_title}'")
            return short_title
        else:
            logging.warning(f"OpenAI API error for title generation: {response.status_code}")
            return None
            
    except Exception as e:
        logging.error(f"AI title generation error: {e}")
        return None

def _convert_with_patterns(voice_command):
    """Fallback pattern-based conversion"""
    import re
    
    command_lower = voice_command.lower()
    include_terms = []
    exclude_terms = []
    
    # Extract "about/with/containing" terms
    about_patterns = [
        r'(?:about|with|containing|regarding)\s+([^,]+?)(?:\s+but|\s+without|$)',
        r'(?:find|play|read|next|previous)\s+.*?(?:about|with|containing)\s+([^,]+?)(?:\s+but|\s+without|$)'
    ]
    
    for pattern in about_patterns:
        match = re.search(pattern, command_lower)
        if match:
            terms = match.group(1).strip()
            # Split on "and" and clean up
            for term in re.split(r'\s+and\s+', terms):
                term = term.strip()
                if term and term not in ['the', 'a', 'an']:
                    include_terms.append(term)
    
    # Extract "but not/without" terms  
    exclude_patterns = [
        r'(?:but\s+not|without|except)\s+([^,]+?)(?:\s+and|$)',
        r'(?:not\s+about|not\s+containing)\s+([^,]+?)(?:\s+and|$)'
    ]
    
    for pattern in exclude_patterns:
        match = re.search(pattern, command_lower)
        if match:
            terms = match.group(1).strip()
            for term in re.split(r'\s+and\s+', terms):
                term = term.strip()
                if term and term not in ['the', 'a', 'an']:
                    exclude_terms.append(term)
    
    # Build search pattern
    search_parts = []
    search_parts.extend(include_terms)
    search_parts.extend([f'-{term}' for term in exclude_terms])
    
    search_pattern = ' '.join(search_parts) if search_parts else voice_command
    
    logging.info(f"Pattern converted '{voice_command}' to '{search_pattern}'")
    return search_pattern

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5020, debug=True)