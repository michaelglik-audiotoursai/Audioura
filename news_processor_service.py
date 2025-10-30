#!/usr/bin/env python3
"""
News Processor Service - Converts article text to audio and creates HTML package
"""
import os
import sys
import psycopg2
from flask import Flask, request, jsonify
import uuid
import logging
import tempfile
import zipfile
import shutil
import json
from datetime import datetime
# Removed gTTS import - using Polly exclusively
import requests
import asyncio
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

# Force unbuffered output for real-time logs
import sys
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

# Database connection
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )

# Version synchronization with mobile app
SERVICE_VERSION = "1.2.2.83"

def generate_short_title(original_title, article_type):
    """Generate AI-shortened title with metadata"""
    try:
        # Get current date
        current_date = datetime.now().strftime("%m/%d/%Y")
        
        # Call voice control service to generate short title
        response = requests.post(
            'http://development-voice-control-1:5008/generate_short_title',
            json={
                'original_title': original_title,
                'article_type': article_type,
                'max_words': 12
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            short_title = data.get('short_title', original_title[:60] + '...')
            author = data.get('author', 'AudioTours')
            
            # Format: Short Title | Author | Type | Date
            formatted_title = f"{short_title} | {author} | {article_type} | {current_date}"
            logging.info(f"AI short title generated: {formatted_title}")
            return formatted_title
        else:
            logging.error(f"OpenAI service failed: {response.status_code}")
            
    except Exception as e:
        logging.error(f"Error generating short title: {e}")
    
    # Fallback: truncate original title and add metadata
    words = original_title.split()
    short_title = ' '.join(words[:12])
    if len(words) > 12:
        short_title += '...'
    
    current_date = datetime.now().strftime("%m/%d/%Y")
    fallback_title = f"{short_title} | AudioTours | {article_type} | {current_date}"
    logging.info(f"Fallback short title: {fallback_title}")
    return fallback_title

def clean_text_for_polly(text):
    """Clean text thoroughly before sending to Polly TTS to control costs"""
    if not text:
        return ""
    
    import re
    
    # Remove HTML tags completely
    text = re.sub(r'<[^>]+>', '', text)
    
    # Remove URLs to reduce TTS costs
    text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '[URL]', text)
    
    # Remove email addresses
    text = re.sub(r'\S+@\S+', '[EMAIL]', text)
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove control characters
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    
    # Limit to 5000 characters per TTS call to control costs
    if len(text) > 5000:
        text = text[:5000] + "... Content truncated for cost control."
        logging.warning(f"Text truncated to 5000 characters for Polly cost control")
    
    return text.strip()

def generate_audio_with_polly(text, output_path):
    """Generate audio using Polly TTS service with cost controls"""
    try:
        # Clean text before sending to Polly
        clean_text = clean_text_for_polly(text)
        
        if not clean_text:
            logging.error("No clean text available for TTS")
            raise Exception("No clean text for TTS")
        
        logging.info(f"Sending {len(clean_text)} clean characters to Polly (original: {len(text)})")
        
        response = requests.post(
            'http://polly-tts-1:5018/synthesize',
            json={
                'text': clean_text,
                'voice_id': 'Joanna',
                'output_format': 'mp3'
            },
            timeout=300  # 5 minutes for very long articles
        )
        
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            logging.info(f"Polly TTS successful: {len(clean_text)} chars -> {output_path}")
            return True
        else:
            logging.error(f"Polly failed with status {response.status_code}: {response.text}")
            raise Exception(f"Polly TTS failed: {response.status_code}")
            
    except Exception as e:
        logging.error(f"Polly request failed: {e}")
        raise e

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "news_processor_1", "version": SERVICE_VERSION})

@app.route('/process-audio/<article_id>', methods=['POST'])
def process_audio(article_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get article and major points from database
        cursor.execute("""
            SELECT article_text, request_string, major_points, article_type 
            FROM article_requests 
            WHERE article_id = %s AND status = 'ready'
        """, (article_id,))
        
        result = cursor.fetchone()
        if not result:
            return jsonify({"error": "Article not found or not ready"}), 404
        
        article_text, request_string, major_points_json, article_type = result
        article_type = article_type or 'Others'  # Default if None
        
        # Decode article text
        if isinstance(article_text, memoryview):
            article_text = article_text.tobytes().decode('utf-8')
        elif isinstance(article_text, bytes):
            article_text = article_text.decode('utf-8')
        
        # Parse major points if available
        major_points = []
        if major_points_json:
            try:
                # Check if it's already a list or needs JSON parsing
                if isinstance(major_points_json, list):
                    major_points = major_points_json
                else:
                    major_points = json.loads(major_points_json)
                logging.info(f"Parsed {len(major_points)} major points")
                for i, point in enumerate(major_points):
                    logging.info(f"Point {i}: {point.get('short_title', 'NO_TITLE')} - segment_id: {point.get('segment_id', 'NO_ID')}")
            except Exception as e:
                logging.error(f"Failed to parse major_points: {e}")
                major_points = []
        
        # Split article into summary and full text
        parts = article_text.split('\n\nFull Article:', 1)
        if len(parts) == 2:
            summary_text = parts[0].replace('Summary: ', '')
            full_text = parts[1]
        else:
            # Fallback if format is different
            summary_text = article_text[:200] + "..."
            full_text = article_text
        
        # Create temporary directory for HTML package
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_files = []
            
            # Generate summary audio (Audio 1) using Polly TTS
            summary_text_full = f"Article Summary: {summary_text}"
            summary_path = os.path.join(temp_dir, "audio_1.mp3")
            
            generate_audio_with_polly(summary_text_full, summary_path)
            logging.info("Summary audio generated with Polly")
            
            audio_files.append(("audio_1.mp3", "Summary"))
            
            # Generate topics list only if we have major points
            if major_points and len(major_points) > 0:
                topics_text = "Here are the major topics covered in this article: "
                for i, point in enumerate(major_points, 1):
                    short_title = point.get('short_title', point.get('point', f'Topic {i}'))
                    topics_text += f"{short_title}. "
                topics_text += "You can ask me to play any of these topics by saying 'Play topic' followed by the number."
                
                topics_path = os.path.join(temp_dir, "audio-topics.mp3")
                
                generate_audio_with_polly(topics_text, topics_path)
                logging.info("Topics audio generated with Polly")
                audio_files.append(("audio-topics.mp3", "Topics List"))
                

                
                # Generate individual point audios (may have gaps due to merging)
                for i, point in enumerate(major_points, 1):
                    try:
                        logging.info(f"Processing point {i}: {point}")
                        point_text = point.get('audio_text', f"Topic {i}: {point.get('summary', point.get('point', ''))}")
                        logging.info(f"Point {i} text length: {len(point_text)}")
                        
                        # Use segment_id for proper numbering (handles merged topics)
                        segment_id = point.get('segment_id', i)
                        logging.info(f"Point {i} segment_id: {segment_id}")
                        point_path = os.path.join(temp_dir, f"audio-{segment_id+1}.mp3")
                        
                        generate_audio_with_polly(point_text, point_path)
                        logging.info(f"Point {i} audio generated with Polly")
                        # Use the actual short title instead of generic "Topic X"
                        topic_title = point.get('short_title', 'Topic ' + str(i))
                        audio_files.append((f"audio-{segment_id+1}.mp3", topic_title))
                        logging.info(f"Successfully created audio for point {i}")
                    except Exception as e:
                        logging.error(f"Error processing point {i}: {e}")
                        # Continue with next point instead of failing completely
                        continue
            
            # Generate help commands audio (always generate regardless of major points)
            help_text = """Here are the voice commands you can use: 
            Say 'Play' to start or resume audio. Say 'Pause' to stop audio. 
            Say 'Next topic' or 'Previous topic' to navigate between sections. 
            Say 'Forward 10 seconds' or 'Backward 5 seconds' to skip within audio. 
            Say 'Repeat' to restart current audio from beginning. 
            Say 'Play topic' followed by a number or topic name to jump to specific sections. 
            Say 'Play summary' for article summary or 'Play full article' for complete text. 
            Say 'List major topics' to hear all available sections. 
            Say 'Next article' or 'Previous article' to switch between articles. 
            You can also say 'What are my options' anytime to hear this help again."""
            
            help_path = os.path.join(temp_dir, "audio-help.mp3")
            
            generate_audio_with_polly(help_text, help_path)
            logging.info("Help audio generated with Polly")
            audio_files.append(("audio-help.mp3", "Help Commands"))
            
            # Generate full article audio (always last, high number to avoid conflicts)
            # Use high number for full article to avoid conflicts with topic numbering
            full_path = os.path.join(temp_dir, "audio-99.mp3")
            full_text_complete = f"Full Article: {full_text}"
            
            generate_audio_with_polly(full_text_complete, full_path)
            logging.info("Full article audio generated with Polly")
            audio_files.append(("audio-99.mp3", "Full Article"))
            
            # Create search content file for full-text search
            search_content_path = os.path.join(temp_dir, "audiotours_search_content.txt")
            search_content = f"{request_string}\n\n{summary_text}\n\n{full_text}"
            with open(search_content_path, 'w', encoding='utf-8') as f:
                f.write(search_content)
            logging.info("Search content file created")
            
            # Generate AI short title only if original title exceeds 12 words
            title_words = len(request_string.split())
            if title_words > 12:
                short_title = generate_short_title(request_string, article_type)
                short_title_path = os.path.join(temp_dir, "audiotours_short_title.txt")
                with open(short_title_path, 'w', encoding='utf-8') as f:
                    f.write(short_title)
                logging.info(f"Short title generated ({title_words} words): {short_title}")
            else:
                logging.info(f"Title has {title_words} words (≤12), no short title needed")
            
            # Create HTML file with all audio files
            html_content = create_news_html_with_points(summary_text, full_text, request_string, major_points, audio_files)
            html_path = os.path.join(temp_dir, "index.html")
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # Create ZIP file with HTML, MP3s, and text files
            zip_path = os.path.join(temp_dir, f"{article_id}.zip")
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                zipf.write(html_path, "index.html")
                zipf.write(search_content_path, "audiotours_search_content.txt")
                # Only include short title file if it was created
                if title_words > 12:
                    zipf.write(short_title_path, "audiotours_short_title.txt")
                for audio_file, _ in audio_files:
                    audio_path = os.path.join(temp_dir, audio_file)
                    zipf.write(audio_path, audio_file)
            
            # Read ZIP file as binary
            with open(zip_path, 'rb') as f:
                zip_data = f.read()
        
        # Store in news_audios table with article type
        cursor.execute("""
            INSERT INTO news_audios (article_id, article_name, news_article, number_requested, article_type)
            VALUES (%s, %s, %s, %s, %s)
        """, (article_id, request_string[:255], zip_data, 1, article_type))
        
        # Update article_requests status
        cursor.execute("""
            UPDATE article_requests 
            SET status = 'finished', finished_at = %s
            WHERE article_id = %s
        """, (datetime.now(), article_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "article_id": article_id,
            "message": "Article audio processed and stored"
        })
        
    except Exception as e:
        logging.error(f"Error processing audio for {article_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

def create_news_html_with_points(summary_text, full_text, title, major_points, audio_files):
    # Create sections for each audio file (hide topics list from UI)
    audio_sections = ""
    for i, (audio_file, section_title) in enumerate(audio_files):
        # Determine proper audio ID based on file structure
        if audio_file == "audio-1.mp3":
            audio_id = "audio-1"
        elif audio_file == "audio-topics.mp3":
            audio_id = "audio-topics"
            # Hide topics list from UI - voice-only access
            audio_sections += f'<audio id="{audio_id}" preload="metadata" style="display:none;"><source src="{audio_file}" type="audio/mpeg"></audio>'
            continue
        elif audio_file == "audio-help.mp3":
            audio_id = "audio-help"
            # Hide help commands from UI - voice-only access
            audio_sections += f'<audio id="{audio_id}" preload="metadata" style="display:none;"><source src="{audio_file}" type="audio/mpeg"></audio>'
            continue
        else:
            # Extract number from filename like audio-3.mp3, audio-4.mp3, etc.
            try:
                if "-" in audio_file:
                    audio_num = audio_file.split("-")[1].split(".")[0]
                    audio_id = f"audio-{audio_num}"
                else:
                    # Handle files like audio_1.mp3
                    audio_num = audio_file.split("_")[1].split(".")[0] if "_" in audio_file else str(i+1)
                    audio_id = f"audio-{audio_num}"
            except IndexError as e:
                logging.error(f"Error parsing audio filename {audio_file}: {e}")
                audio_id = f"audio-{i+1}"  # Fallback ID
        
        section_class = "summary" if i == 0 else "full-article" if "Full Article" in section_title else "topic-section"
        
        audio_sections += f'''
        <div class="section {section_class}">
            <h2>{section_title}</h2>
            <audio id="{audio_id}" controls preload="metadata">
                <source src="{audio_file}" type="audio/mpeg">
            </audio>
        </div>'''
    
    # Use regular string formatting to avoid f-string nesting issues
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .article-container {{ max-width: 800px; margin: 0 auto; }}
        audio {{ width: 100%; margin: 20px 0; }}
        .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
        .summary {{ background-color: #f0f8ff; }}
        .topic-section {{ background-color: #f5f5f5; }}
        .full-article {{ background-color: #f9f9f9; }}
    </style>
</head>
<body>
    <div class="article-container">
        <h1>{title}</h1>
        {audio_sections}
    </div>
    
    <script>
        let currentIndex = 0;
        let audioElements = [];
        let currentAudio = null;
        let autoPlayEnabled = true;
        let timerVariable = 0;
        let timeOutParameterGlobal = 100;
        let listIsBeingRead = false;
        
        // Safe timer function to prevent concurrent timers
        function safeSetTimeout(func, timeout) {{
            if (timerVariable < 1) {{
                timerVariable++;
                setTimeout(() => {{
                    timerVariable--;
                    timeOutParameterGlobal = 100;
                    func();
                }}, timeout);
                return "DEBUG: Timer set for " + timeout + "ms";
            }}
            return "DEBUG: Timer blocked (active=" + timerVariable + ")";
        }}
        
        document.addEventListener('DOMContentLoaded', function() {{
            audioElements = Array.from(document.querySelectorAll('audio'));
            if (audioElements.length > 0) {{
                currentAudio = audioElements[0];
                safeSetTimeout(() => playAudioByIndex(0), 1000);
            }}
            
            audioElements.forEach((audio, index) => {{
                audio.addEventListener('play', function() {{
                    audioElements.forEach((otherAudio, otherIndex) => {{
                        if (otherIndex !== index && !otherAudio.paused) {{
                            otherAudio.pause();
                            otherAudio.currentTime = 0;
                        }}
                    }});
                    currentIndex = index;
                    currentAudio = audio;
                }});
                
                // Auto-advance to next audio when current ends (only if auto-play enabled)
                audio.addEventListener('ended', function() {{
                    if (autoPlayEnabled && index < audioElements.length - 1) {{
                        // Skip hidden audio-topics when auto-advancing
                        let nextIndex = index + 1;
                        while (nextIndex < audioElements.length && audioElements[nextIndex].style.display === 'none') {{
                            nextIndex++;
                        }}
                        if (nextIndex < audioElements.length) {{
                            safeSetTimeout(() => playAudioByIndex(nextIndex), 500);
                        }}
                    }}
                }});
            }});
        }});
        
        function playAudioByIndex(index) {{
            audioElements.forEach(audio => {{
                audio.pause();
                audio.currentTime = 0;
            }});
            
            if (index >= 0 && index < audioElements.length) {{
                currentIndex = index;
                currentAudio = audioElements[index];
                currentAudio.play();
                return true;
            }}
            return false;
        }}
        
        window.playAudio = function() {{
            if (currentAudio) {{
                currentAudio.play();
                return "DEBUG: Playing currentAudio (index=" + currentIndex + ", id=" + currentAudio.id + ")";
            }}
            return "ERROR: No currentAudio set";
        }};
        
        window.pauseAudio = function() {{
            // Pause ALL audio but DON'T reset time unless explicitly requested
            audioElements.forEach(audio => {{
                audio.pause();
            }});
            return "DEBUG: All audio paused (currentIndex=" + currentIndex + ", time preserved)";
        }};
        
        window.resetVoiceControlState = function() {{
            // Only reset specific flags, preserve audio state
            listIsBeingRead = false;
            
            // Pause all audio but DON'T reset currentTime
            audioElements.forEach(audio => {{
                audio.pause();
            }});
            
            return "DEBUG: Voice control state reset (listIsBeingRead=false, time preserved)";
        }};
        
        window.playPoint = function(pointNumber) {{
            // Play specific topic by number
            const topicAudio = document.getElementById('audio-' + (pointNumber + 1));
            if (topicAudio) {{
                const topicIndex = Array.from(audioElements).indexOf(topicAudio);
                if (topicIndex >= 0) {{
                    return playAudioByIndex(topicIndex) ? 'Playing topic ' + pointNumber : 'Failed to play topic';
                }}
            }}
            return 'Topic ' + pointNumber + ' not found';
        }};
        
        window.seekForward = function(seconds) {{
            if (currentAudio) {{
                const maxTime = currentAudio.duration || 0;
                currentAudio.currentTime = Math.min(maxTime, currentAudio.currentTime + seconds);
                if (currentAudio.paused) {{
                    currentAudio.play();
                }}
                return "DEBUG: Seeked forward " + seconds + "s to " + currentAudio.currentTime.toFixed(1) + "s";
            }}
            return "ERROR: No current audio";
        }};
        
        window.seekBackward = function(seconds) {{
            if (currentAudio) {{
                currentAudio.currentTime = Math.max(0, currentAudio.currentTime - seconds);
                if (currentAudio.paused) {{
                    currentAudio.play();
                }}
                return "DEBUG: Seeked backward " + seconds + "s to " + currentAudio.currentTime.toFixed(1) + "s";
            }}
            return "ERROR: No current audio";
        }};
        
        window.listPoints = function() {{
            // Pause all audio but DON'T reset their time
            audioElements.forEach(audio => {{
                audio.pause();
            }});
            
            const topicsAudio = document.getElementById('audio-topics');
            if (topicsAudio) {{
                // Always reset topics audio to beginning (but preserve other audio times)
                topicsAudio.currentTime = 0;
                
                // Set flag and play topics
                listIsBeingRead = true;
                topicsAudio.addEventListener('ended', function() {{
                    listIsBeingRead = false;
                }}, {{ once: true }});
                
                topicsAudio.play();
                return "DEBUG: Playing topics list (listIsBeingRead=true, duration=" + (topicsAudio.duration || 'unknown') + "s, other audio times preserved)";
            }}
            return "ERROR: Topics list not found";
        }};
        
        window.isListBeingRead = function() {{
            return listIsBeingRead ? "true" : "false";
        }};
        
        window.getTopicsAudioDuration = function() {{
            const topicsAudio = document.getElementById('audio-topics');
            return topicsAudio ? (topicsAudio.duration || 0).toString() : "0";
        }};
        
        window.showHelp = function() {{
            // Pause all audio first
            audioElements.forEach(audio => {{
                audio.pause();
            }});
            
            const helpAudio = document.getElementById('audio-help');
            if (helpAudio) {{
                // Always reset help audio to beginning
                helpAudio.currentTime = 0;
                helpAudio.play();
                return "DEBUG: Playing help commands (duration=" + (helpAudio.duration || 'unknown') + "s)";
            }}
            return "ERROR: Help audio not found";
        }};
        
        window.getHelpText = function() {{
            return JSON.stringify({{
                title: "Voice Commands Help",
                commands: [
                    {{ category: "Playback Control", items: ["Play", "Pause", "Repeat"] }},
                    {{ category: "Navigation", items: ["Next topic", "Previous topic", "Next article", "Previous article"] }},
                    {{ category: "Seeking", items: ["Forward [X] seconds", "Backward [X] seconds"] }},
                    {{ category: "Content Selection", items: ["Play summary", "Play full article", "Play topic [number/name]"] }},
                    {{ category: "Information", items: ["List major topics", "What are my options"] }}
                ]
            }});
        }};
        
        window.playFullArticle = function() {{
            const fullArticleAudio = document.getElementById('audio-99');
            if (fullArticleAudio) {{
                const fullIndex = Array.from(audioElements).indexOf(fullArticleAudio);
                if (fullIndex >= 0) {{
                    return playAudioByIndex(fullIndex) ? 'Playing full article' : 'Failed to play full article';
                }}
            }}
            return 'Full article not found';
        }};
        
        window.repeatTopic = function() {{
            if (currentAudio) {{
                currentAudio.currentTime = 0;
                return "DEBUG: Reset currentAudio to 0s (index=" + currentIndex + ", id=" + currentAudio.id + ")";
            }}
            return "ERROR: No currentAudio to repeat";
        }};
        
        window.nextTopic = function() {{
            // Skip hidden audio-topics when advancing
            let nextIndex = currentIndex + 1;
            while (nextIndex < audioElements.length && audioElements[nextIndex].style.display === 'none') {{
                nextIndex++;
            }}
            
            if (nextIndex < audioElements.length) {{
                currentIndex = nextIndex;
                currentAudio = audioElements[currentIndex];
                return "DEBUG: Advanced to next (index=" + currentIndex + ", id=" + currentAudio.id + ")";
            }}
            return "ERROR: No next topic available";
        }};
        
        window.previousTopic = function() {{
            // Skip hidden audio-topics when going back
            let prevIndex = currentIndex - 1;
            while (prevIndex >= 0 && audioElements[prevIndex].style.display === 'none') {{
                prevIndex--;
            }}
            
            if (prevIndex >= 0) {{
                currentIndex = prevIndex;
                currentAudio = audioElements[currentIndex];
                return "DEBUG: Moved to previous (index=" + currentIndex + ", id=" + currentAudio.id + ")";
            }}
            return "ERROR: No previous topic available";
        }};
        
        window.getTopicNames = function() {{
            const topics = [];
            // Get topic titles from HTML sections
            document.querySelectorAll('.topic-section h2').forEach((h2, index) => {{
                const title = h2.textContent.toLowerCase();
                const words = title.split(' ').filter(word => word.length > 2); // Skip short words
                topics.push({{
                    index: index + 1,
                    title: title,
                    words: words
                }});
            }});
            return JSON.stringify(topics);
        }};
        
        window.findTopicByName = function(searchText) {{
            const topics = JSON.parse(window.getTopicNames());
            const search = searchText.toLowerCase();
            let bestMatch = null;
            let bestScore = 0;
            
            topics.forEach(topic => {{
                let score = 0;
                
                // Exact phrase match (highest score)
                if (topic.title.includes(search)) {{
                    score = 100;
                }}
                
                // Word matching
                const searchWords = search.split(' ').filter(word => word.length > 2);
                searchWords.forEach(searchWord => {{
                    topic.words.forEach(topicWord => {{
                        // Exact word match
                        if (topicWord === searchWord) {{
                            score += 50;
                        }}
                        // Partial word match (fuzzy)
                        else if (topicWord.includes(searchWord) || searchWord.includes(topicWord)) {{
                            score += 25;
                        }}
                        // Similar words (basic fuzzy)
                        else if (Math.abs(topicWord.length - searchWord.length) <= 2) {{
                            let matches = 0;
                            for (let i = 0; i < Math.min(topicWord.length, searchWord.length); i++) {{
                                if (topicWord[i] === searchWord[i]) matches++;
                            }}
                            if (matches >= Math.min(topicWord.length, searchWord.length) * 0.6) {{
                                score += 15;
                            }}
                        }}
                    }});
                }});
                
                if (score > bestScore) {{
                    bestScore = score;
                    bestMatch = topic;
                }}
            }});
            
            if (bestMatch && bestScore >= 15) {{ // Minimum threshold
                return JSON.stringify({{
                    found: true,
                    topic: bestMatch.index,
                    title: bestMatch.title,
                    score: bestScore
                }});
            }}
            
            return JSON.stringify({{ found: false }});
        }};
    </script>
</body>
</html>"""
    
    return html_template.format(title=title, audio_sections=audio_sections)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5011, debug=True)