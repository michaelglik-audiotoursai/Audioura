#!/usr/bin/env python3
"""
ZIP File Verification Test
Tests that complete audio packages are created and downloadable
"""
import requests
import zipfile
import os
import tempfile
import psycopg2
from datetime import datetime

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )

def get_recent_articles():
    """Get recent finished articles for ZIP testing"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT ar.article_id, ar.request_string, ar.article_type, ar.finished_at
        FROM article_requests ar
        JOIN news_audios na ON ar.article_id = na.article_id
        WHERE ar.status = 'finished' 
        AND ar.finished_at > NOW() - INTERVAL '24 hours'
        ORDER BY ar.finished_at DESC
        LIMIT 5
    """)
    
    articles = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return articles

def test_zip_download(article_id, title):
    """Test ZIP file download and contents"""
    print(f"\n=== Testing ZIP for: {title[:50]}... ===")
    print(f"Article ID: {article_id}")
    
    try:
        # Download ZIP file
        response = requests.get(f'http://localhost:5012/download/{article_id}', timeout=30)
        
        if response.status_code != 200:
            print(f"ERROR: HTTP {response.status_code}")
            return False
        
        print(f"SUCCESS: Downloaded ZIP: {len(response.content)} bytes")
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
            temp_file.write(response.content)
            zip_path = temp_file.name
        
        # Verify ZIP contents
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                files = zip_file.namelist()
                print(f"SUCCESS: ZIP contains {len(files)} files:")
                
                # Categorize files
                html_files = [f for f in files if f.endswith('.html')]
                mp3_files = [f for f in files if f.endswith('.mp3')]
                txt_files = [f for f in files if f.endswith('.txt')]
                
                print(f"  HTML files: {len(html_files)} - {html_files}")
                print(f"  MP3 files: {len(mp3_files)} - {mp3_files}")
                print(f"  TXT files: {len(txt_files)} - {txt_files}")
                
                # Check required files
                required_files = ['index.html', 'audiotours_search_content.txt']
                required_audio = ['audio-1.mp3', 'audio-99.mp3']  # Summary and full article
                
                missing_files = [f for f in required_files if f not in files]
                missing_audio = [f for f in required_audio if f not in files]
                
                if missing_files:
                    print(f"ERROR: Missing required files: {missing_files}")
                    return False
                
                if missing_audio:
                    print(f"ERROR: Missing required audio: {missing_audio}")
                    return False
                
                # Check file sizes
                for file_info in zip_file.infolist():
                    if file_info.filename.endswith('.mp3'):
                        if file_info.file_size < 1000:  # Less than 1KB is suspicious
                            print(f"WARNING: Small MP3 file: {file_info.filename} ({file_info.file_size} bytes)")
                        else:
                            print(f"SUCCESS: Good MP3 size: {file_info.filename} ({file_info.file_size:,} bytes)")
                
                print(f"SUCCESS: ZIP verification PASSED")
                return True
                
        except zipfile.BadZipFile:
            print(f"ERROR: Invalid ZIP file")
            return False
        
        finally:
            # Cleanup
            os.unlink(zip_path)
    
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def main():
    """Run ZIP verification tests on recent articles"""
    print("ZIP FILE VERIFICATION TEST")
    print("=" * 50)
    
    # Get recent articles
    articles = get_recent_articles()
    
    if not articles:
        print("ERROR: No recent finished articles found")
        print("Run some newsletter processing tests first:")
        print("  python test_apple_processing.py")
        print("  python test_spotify_processing.py")
        return
    
    print(f"Found {len(articles)} recent articles to test:")
    
    passed = 0
    total = len(articles)
    
    for article_id, title, article_type, finished_at in articles:
        success = test_zip_download(article_id, title)
        if success:
            passed += 1
    
    print("\n" + "=" * 50)
    print("ZIP VERIFICATION SUMMARY")
    print("=" * 50)
    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success Rate: {(passed/total*100):.1f}%")
    
    if passed == total:
        print("SUCCESS: ALL ZIP FILES VERIFIED SUCCESSFULLY!")
    else:
        print("WARNING: Some ZIP files failed verification")

if __name__ == "__main__":
    main()