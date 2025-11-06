#!/usr/bin/env python3
"""
News Generator Service - Processes article text and prepares for audio conversion
"""
import os
import sys
import psycopg2
from flask import Flask, request, jsonify
import uuid
import logging
import re
import json

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Database connection
def clean_article_text(text):
    """Clean article text from ads, navigation, and other artifacts"""
    # Remove common ad patterns
    text = re.sub(r'\bAdvertisement\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bSponsored\b.*?\n', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Subscribe.*?Newsletter', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Follow.*?@\w+', '', text, flags=re.IGNORECASE)
    
    # Remove navigation/UI elements
    text = re.sub(r'Skip to.*?content', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Show \d+ comments', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Most popular on.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Related:.*?\n', '', text, flags=re.IGNORECASE)
    
    # Clean up whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)  # Multiple newlines
    text = re.sub(r'^\s+|\s+$', '', text, flags=re.MULTILINE)
    
    return text.strip()

def clean_concatenated_title(title):
    """Clean title that may have concatenated newsletter/ad content"""
    # Common newsletter/ad patterns to remove
    ad_patterns = [
        r'Get the Gavel Newsletter',
        r'SCOTUS explained by [^\n]+',
        r'Subscribe to [^\n]+',
        r'Sign up for [^\n]+',
        r'Newsletter[^\n]*',
        r'Advertisement[^\n]*'
    ]
    
    cleaned = title
    for pattern in ad_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Clean up extra whitespace and return the longest remaining part
    parts = [part.strip() for part in cleaned.split() if part.strip()]
    if parts:
        # Rejoin and look for the longest sentence-like structure
        rejoined = ' '.join(parts)
        # If we have multiple sentences, take the longest one
        sentences = re.split(r'[.!?]+', rejoined)
        if sentences:
            longest = max(sentences, key=len).strip()
            if len(longest) > 20:
                return longest
    
    return cleaned.strip()

def extract_title_author(text):
    """Extract title and author from article text"""
    lines = text.split('\n')[:20]  # Check more lines
    title = ""
    author = ""
    
    # Debug: log the first few lines
    import logging
    logging.info(f"First 10 lines for title extraction:")
    for i, line in enumerate(lines[:10]):
        logging.info(f"Line {i}: '{line.strip()}'")
    
    # Look for lines with "By" pattern first - these indicate real articles
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.upper() in ['AD', 'ADVERTISEMENT']:
            continue
            
        # If we find "By [Author]" pattern, the title is likely the previous line
        if re.search(r'By\s+[A-Z]', line, re.IGNORECASE):
            logging.info(f"Found 'By' pattern at line {i}: '{line}'")
            
            # Extract author (everything after "By" until comma or end)
            author_match = re.search(r'By\s+(.+?)(?:,.*|$)', line, re.IGNORECASE)
            if author_match:
                author = author_match.group(1).strip()
                logging.info(f"Extracted author: '{author}'")
            
            # Look for title in previous lines (go backwards)
            for j in range(i-1, max(-1, i-5), -1):
                if j >= 0:
                    candidate = lines[j].strip()
                    # Skip short lines, ads, and numbers
                    if (len(candidate) > 20 and 
                        not candidate.upper() in ['AD', 'ADVERTISEMENT'] and
                        not candidate.isdigit() and
                        not re.match(r'^\d+$', candidate)):
                        
                        # Clean concatenated content
                        cleaned_title = clean_concatenated_title(candidate)
                        if len(cleaned_title) > 20:
                            title = cleaned_title
                            logging.info(f"Selected and cleaned title from line {j}: '{title}'")
                            break
            break
    
    # If no "By" pattern found, find the longest meaningful line
    if not title:
        logging.info("No 'By' pattern found, looking for longest line")
        max_len = 0
        for i, line in enumerate(lines):
            line = line.strip()
            if (len(line) > max_len and len(line) > 30 and
                not line.upper() in ['AD', 'ADVERTISEMENT'] and
                not line.isdigit()):
                cleaned_line = clean_concatenated_title(line)
                if len(cleaned_line) > max_len:
                    title = cleaned_line
                    max_len = len(cleaned_line)
                    logging.info(f"New longest candidate from line {i}: '{title}'")
    
    final_title = title or "News Article"
    logging.info(f"Final result - Title: '{final_title}', Author: '{author}'")
    return final_title, author

def generate_summary(text, max_words=100):
    """Generate summary from article text"""
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    # Take first few sentences up to word limit
    summary = ""
    word_count = 0
    
    for sentence in sentences[:5]:  # Max 5 sentences
        words = sentence.split()
        if word_count + len(words) <= max_words:
            summary += sentence + ". "
            word_count += len(words)
        else:
            break
    
    return summary.strip()

def clean_article_with_title_boundary(text, title):
    """Clean article using title as boundary marker"""
    import logging
    
    lines = text.split('\n')
    title_line_index = -1
    
    # Find the line containing the title
    for i, line in enumerate(lines):
        if title in line:
            title_line_index = i
            logging.info(f"Found title at line {i}: '{line.strip()}'")
            break
    
    if title_line_index == -1:
        logging.info("Title not found in text, using basic cleaning")
        return clean_article_text(text)
    
    # Area 1: Everything before the title
    area1_lines = lines[:title_line_index]
    area1_text = '\n'.join(area1_lines)
    logging.info(f"Area 1 (before title): {len(area1_lines)} lines")
    
    # Extract patterns from Area 1 (4+ word phrases)
    area1_patterns = []
    for line in area1_lines:
        line = line.strip()
        if len(line.split()) >= 4:  # 4+ words
            area1_patterns.append(line)
    
    logging.info(f"Found {len(area1_patterns)} patterns to remove from article body")
    
    # Start cleaning from the title line onwards
    clean_lines = lines[title_line_index:]
    clean_text = '\n'.join(clean_lines)
    
    # Remove Area 1 patterns from the article body
    for pattern in area1_patterns:
        if len(pattern) > 10:  # Only remove substantial patterns
            clean_text = clean_text.replace(pattern, '')
            logging.info(f"Removed pattern: '{pattern[:50]}...'")
    
    # Apply basic cleaning
    clean_text = clean_article_text(clean_text)
    
    # Find and remove article end (promotional content)
    clean_text = find_article_end(clean_text)
    
    logging.info(f"Article cleaned: {len(text)} -> {len(clean_text)} characters")
    return clean_text

def find_article_end(text):
    """Find where the actual article content ends - IMPROVED ALGORITHM"""
    import logging
    
    # Improved end marker detection - only truncate if we have substantial content before the marker
    end_markers = [
        r'Follow.*?on Instagram',
        r'sign up for.*?newsletter',
        r'Read \d+ Comments',
        r'Share full article',
        r'Editors\' Picks',
        r'More in \w+',
        r'Related Content',
        r'Dreaming up a future',
        r'Subscribe to.*?newsletter',
        r'Get.*?newsletter',
        r'Terms of Service',
        r'©\d{4}.*?Media Partners',
        r'Helping Plus-Size',
        r'Planning a Huge Wedding',
        r'Related:'
    ]
    
    lines = text.split('\n')
    total_lines = len(lines)
    
    for i, line in enumerate(lines):
        for marker in end_markers:
            if re.search(marker, line, re.IGNORECASE):
                # CRITICAL FIX: Only truncate if we have substantial content before the marker
                # AND the marker appears in the last 20% of the content
                content_before = '\n'.join(lines[:i]).strip()
                
                # Safety checks:
                # 1. Must have at least 500 characters of content before marker
                # 2. Marker must be in last 20% of lines (likely promotional footer)
                # 3. Don't truncate if marker is in first 80% (likely part of actual content)
                
                if (len(content_before) >= 500 and 
                    i >= (total_lines * 0.8)):
                    logging.info(f"Found end marker at line {i}/{total_lines} (last 20%): '{marker}' - truncating")
                    logging.info(f"Article truncated: {len(text)} -> {len(content_before)} characters")
                    return content_before
                else:
                    logging.info(f"Found end marker at line {i}/{total_lines} but NOT truncating - marker too early or insufficient content before it")
                    logging.info(f"Content before marker: {len(content_before)} chars, Position: {i/total_lines*100:.1f}% through text")
    
    logging.info("No valid end markers found for truncation, keeping full text")
    return text

def extract_major_points(text, max_points):
    """AI-generate exact number of major points requested"""
    import logging
    
    if max_points == 0:
        return []
    
    # Split text into sections for the exact number requested
    paragraphs = [p.strip() for p in text.split('\n\n') if len(p.strip()) > 100]
    if len(paragraphs) < max_points:
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 50]
        paragraphs = []
        sentences_per_section = max(1, len(sentences) // max_points)
        for i in range(max_points):
            start = i * sentences_per_section
            end = min(start + sentences_per_section, len(sentences))
            if start < len(sentences):
                para = ". ".join(sentences[start:end])
                paragraphs.append(para)
    
    raw_points = []
    
    # Generate exactly max_points (no more)
    for i in range(min(max_points, len(paragraphs))):
        paragraph = paragraphs[i]
        
        # AI-generate short title (max 4 words)
        title_words = generate_short_title(paragraph)
        short_title = " ".join(title_words)
        
        # AI-generate concise summary
        summary_text = generate_topic_summary(paragraph)
        
        raw_points.append({
            "short_title": short_title,
            "audio_text": f"Topic: {summary_text}",
            "summary": summary_text[:150] + "..." if len(summary_text) > 150 else summary_text,
            "source_text": paragraph
        })
    
    # Merge points with identical titles and create coherent text
    merged_points = merge_duplicate_titles(raw_points)
    
    # Assign segment_ids to final points
    final_points = []
    for i, point in enumerate(merged_points):
        final_points.append({
            "segment_id": i,
            "short_title": point["short_title"],
            "audio_text": point["audio_text"],
            "summary": point["summary"]
        })
        logging.info(f"Final point {i + 1}: '{point['short_title']}' ({len(point['audio_text'])} chars)")
    
    logging.info(f"Generated {len(final_points)} major points (requested {max_points})")
    return final_points

def generate_short_title(text):
    """Generate 4-word title from text"""
    # Extract key words (nouns, adjectives, proper nouns)
    words = re.findall(r'\b[A-Z][a-z]+|\b[a-z]{4,}\b', text)
    
    # Filter common words
    stop_words = {'said', 'that', 'with', 'have', 'this', 'will', 'from', 'they', 'been', 'were', 'their'}
    key_words = [w for w in words[:20] if w.lower() not in stop_words]
    
    # Return first 4 meaningful words
    return key_words[:4] if len(key_words) >= 4 else key_words + ['Topic']

def generate_topic_summary(text):
    """Generate concise topic summary (max 300 chars)"""
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    # Take first 2 sentences and condense
    summary = ". ".join(sentences[:2])
    
    # Trim to reasonable length
    if len(summary) > 300:
        summary = summary[:297] + "..."
    
    return summary

def merge_duplicate_titles(points):
    """Merge points with identical 4-word titles using AI coherence"""
    import logging
    
    merged = {}
    
    for point in points:
        title = point["short_title"]
        
        if title in merged:
            # AI-merge the content for coherence
            existing = merged[title]
            
            # Combine source texts and create coherent summary
            combined_sources = [existing["source_text"], point["source_text"]]
            coherent_text = create_coherent_summary(combined_sources, title)
            
            merged[title] = {
                "short_title": title,
                "audio_text": f"Topic: {coherent_text}",
                "summary": coherent_text[:150] + "..." if len(coherent_text) > 150 else coherent_text,
                "source_text": " ".join(combined_sources)
            }
            logging.info(f"AI-merged duplicate title: '{title}'")
        else:
            merged[title] = point
    
    return list(merged.values())

def create_coherent_summary(source_texts, topic_title):
    """Create coherent summary from multiple sources using AI logic"""
    # Combine all sentences and remove duplicates
    all_sentences = []
    for text in source_texts:
        sentences = re.split(r'[.!?]+', text)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 20 and sentence not in all_sentences:
                all_sentences.append(sentence)
    
    # Select most relevant sentences (max 3 for coherence)
    key_sentences = []
    topic_words = topic_title.lower().split()
    
    # Score sentences by topic relevance
    scored_sentences = []
    for sentence in all_sentences:
        score = sum(1 for word in topic_words if word in sentence.lower())
        scored_sentences.append((score, sentence))
    
    # Take top 3 most relevant sentences
    scored_sentences.sort(reverse=True, key=lambda x: x[0])
    key_sentences = [s[1] for s in scored_sentences[:3]]
    
    # Create coherent text (max 300 chars)
    coherent = ". ".join(key_sentences)
    if len(coherent) > 300:
        coherent = coherent[:297] + "..."
    
    return coherent

def classify_article_type(title, content):
    """AI-classify article into predefined categories"""
    import logging
    
    # Combine title and first 500 chars of content for classification
    text_to_analyze = f"{title} {content[:500]}".lower()
    
    # Define category keywords with weights
    categories = {
        "News and Politics": {
            "keywords": ["election", "government", "president", "congress", "senate", "vote", "policy", "law", "court", "judge", "political", "democrat", "republican", "campaign", "legislation", "federal", "state", "governor", "mayor", "council", "trump", "biden", "harris", "supreme court", "fbi", "justice", "immigration", "border", "security", "military", "defense", "war", "conflict", "diplomacy", "international", "foreign", "embassy", "sanctions", "treaty"],
            "weight": 1.0
        },
        "Business and Investment": {
            "keywords": ["stock", "market", "investment", "finance", "economy", "business", "company", "corporation", "ceo", "profit", "revenue", "earnings", "dividend", "share", "trading", "nasdaq", "dow", "s&p", "wall street", "bank", "banking", "loan", "credit", "debt", "mortgage", "real estate", "property", "startup", "venture", "capital", "ipo", "merger", "acquisition", "cryptocurrency", "bitcoin", "blockchain", "inflation", "recession", "gdp", "unemployment", "jobs", "employment", "salary", "wage"],
            "weight": 1.0
        },
        "Technology": {
            "keywords": ["technology", "tech", "software", "hardware", "computer", "internet", "web", "app", "mobile", "smartphone", "iphone", "android", "apple", "google", "microsoft", "amazon", "facebook", "meta", "twitter", "social media", "ai", "artificial intelligence", "machine learning", "robot", "automation", "cloud", "data", "database", "cybersecurity", "hacking", "privacy", "encryption", "blockchain", "virtual reality", "augmented reality", "gaming", "video game", "streaming", "netflix", "youtube", "podcast", "digital", "online", "e-commerce", "startup", "silicon valley"],
            "weight": 1.0
        },
        "Lifestyle and Entertainment": {
            "keywords": ["entertainment", "movie", "film", "actor", "actress", "celebrity", "music", "singer", "band", "album", "concert", "festival", "tv", "television", "show", "series", "netflix", "streaming", "hollywood", "oscar", "grammy", "award", "fashion", "style", "beauty", "health", "fitness", "diet", "nutrition", "wellness", "lifestyle", "travel", "vacation", "hotel", "restaurant", "food", "recipe", "cooking", "chef", "sport", "sports", "football", "basketball", "baseball", "soccer", "tennis", "golf", "olympics", "athlete", "game", "match", "tournament", "championship"],
            "weight": 1.0
        },
        "Education and Learning": {
            "keywords": ["education", "school", "university", "college", "student", "teacher", "professor", "learning", "study", "research", "science", "scientific", "study", "academic", "scholarship", "degree", "graduation", "curriculum", "classroom", "online learning", "e-learning", "course", "training", "skill", "knowledge", "book", "library", "reading", "writing", "literature", "history", "mathematics", "physics", "chemistry", "biology", "medicine", "medical", "health", "doctor", "hospital", "patient", "treatment", "therapy", "drug", "vaccine", "clinical", "trial", "psychology", "mental health"],
            "weight": 1.0
        }
    }
    
    # Calculate scores for each category
    scores = {}
    for category, data in categories.items():
        score = 0
        keywords = data["keywords"]
        weight = data["weight"]
        
        for keyword in keywords:
            if keyword in text_to_analyze:
                score += weight
                # Bonus for title matches
                if keyword in title.lower():
                    score += 0.5
        
        scores[category] = score
        logging.info(f"Category '{category}': score = {score}")
    
    # Find the category with highest score
    if scores:
        best_category = max(scores.items(), key=lambda x: x[1])
        if best_category[1] > 0:  # Must have at least 1 match
            logging.info(f"Article classified as: {best_category[0]} (score: {best_category[1]})")
            return best_category[0]
    
    logging.info("Article classified as: Others (no clear category match)")
    return "Others"

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )

# Version synchronization with mobile app
SERVICE_VERSION = "1.2.2.85"

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "news_generator_1", "version": SERVICE_VERSION})

@app.route('/process-article/<article_id>', methods=['POST'])
def process_article(article_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get article from database
        cursor.execute("""
            SELECT article_text, request_string 
            FROM article_requests 
            WHERE article_id = %s AND status = 'started'
        """, (article_id,))
        
        result = cursor.fetchone()
        if not result:
            return jsonify({"error": "Article not found or not in started status"}), 404
        
        article_text, request_string = result
        
        # Decode article text if it's bytea
        if isinstance(article_text, memoryview):
            article_text = article_text.tobytes().decode('utf-8')
        elif isinstance(article_text, bytes):
            article_text = article_text.decode('utf-8')
        
        # 1. Check if we have a clean title from RSS processor (Apple Podcasts/Spotify)
        # RSS processors provide clean titles that should be preserved
        if (request_string and 
            ('EPISODE_TITLE:' in article_text or 
             'podcasts.apple.com' in str(article_text) or 
             'spotify.com' in str(article_text))):
            # Use the clean title from RSS processor
            title = request_string
            author = ""  # RSS processors don't extract authors
            logging.info(f"Using RSS processor title: '{title}'")
        else:
            # Extract title and author from article content (standard web scraping)
            title, author = extract_title_author(article_text)
            logging.info(f"Extracted title from content: '{title}'")
        
        # 2. Clean article using title as boundary marker
        cleaned_text = clean_article_with_title_boundary(article_text, title)
        
        # 3. Generate summary from cleaned text
        summary = generate_summary(cleaned_text, 100)
        
        # Get number of major points requested (mobile app always sends this)
        data = request.get_json() if request.is_json else {}
        max_points = data.get('max_major_points', 0)
        
        # Generate major points from cleaned text (can be 0)
        major_points = extract_major_points(cleaned_text, max_points) if max_points > 0 else []
        
        # Classify article type using AI
        article_type = classify_article_type(title, cleaned_text)
        logging.info(f"Article {article_id} classified as: {article_type}")
        
        # Create final content with summary and full article
        # For RSS content, don't add author since it's already clean
        if ('EPISODE_TITLE:' in article_text or 
            'podcasts.apple.com' in str(article_text) or 
            'spotify.com' in str(article_text)):
            final_title = title  # Keep RSS title clean
            logging.info(f"Using clean RSS title: '{final_title}'")
        else:
            final_title = f"{title}" + (f" by {author}" if author else "")
            logging.info(f"Using extracted title with author: '{final_title}'")
        
        processed_text = f"Summary: {summary}\n\nFull Article: {cleaned_text}"
        
        # Update article with processed text, title, major points, type, and status
        cursor.execute("""
            UPDATE article_requests 
            SET article_text = %s, request_string = %s, major_points = %s, article_type = %s, status = 'ready'
            WHERE article_id = %s
        """, (processed_text.encode('utf-8'), final_title, json.dumps(major_points), article_type, article_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "article_id": article_id,
            "message": "Article processed and ready for audio conversion"
        })
        
    except Exception as e:
        logging.error(f"Error processing article {article_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5010, debug=True)