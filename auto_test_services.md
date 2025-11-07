# AudioTours Services Testing Guide

## Overview
This document describes the automated testing system for AudioTours newsletter processing services. The tests validate the complete pipeline from URL processing to final article storage.

## Test Architecture

### Test Components
1. **Individual Technology Tests**: Specific tests for each processor (Spotify, Apple Podcasts, etc.)
2. **Test Suite Runner**: Orchestrates all tests and generates reports
3. **Database Cleanup**: Ensures clean state before each test
4. **Debug File Generation**: Captures detailed processing information
5. **Constant Test IDs**: Prevents storage growth by reusing same article IDs

### Storage Management
**Test Cleanup Strategy**: Tests prevent storage growth through automatic cleanup:
- Removes old test articles before creating new ones
- Uses proper cascade deletion (news_audios → newsletters_article_link → article_requests)
- Services remain unchanged - no modifications to production code
- Each test run provides fresh article IDs for download verification

**Benefits**:
- No storage growth from repeated testing
- Services work exactly as in production
- Fresh article IDs for each test run
- Proper foreign key constraint handling

### Test Flow
```
1. Database Cleanup → 2. Processor Test → 3. Orchestrator Test → 4. Database Verification → 5. ZIP File Verification
```

## Available Tests

### 1. Spotify Processing Test (`test_spotify_processing.py`)
**Purpose**: Tests Spotify episode URL processing end-to-end

**Test URL**: `https://open.spotify.com/episode/5aYNEkTiA5B3rYEQsvMJUr?si=02TAenI7TXK1GHc6RENr5A`

**Steps**:
1. **Database Cleanup**: Removes existing articles with test URL
2. **Direct Processor Test**: Tests `spotify_processor.py` directly
3. **Orchestrator Test**: Tests news orchestrator with Spotify content
4. **Database Verification**: Checks final stored content
5. **ZIP File Verification**: Downloads and validates complete audio package

**Generated Files**:
- `debug_spotify_processor_output.json` - Processor results
- `debug_orchestrator_input.json` - Orchestrator input payload
- `debug_orchestrator_output.json` - Orchestrator response
- `debug_final_article_content.txt` - Final database content
- `debug_spotify_raw_response.html` - Raw Spotify HTML response
- `debug_spotify_extraction.txt` - Content extraction details

### 2. Apple Podcasts Processing Test (`test_apple_processing.py`)
**Purpose**: Tests Apple Podcasts episode URL processing end-to-end

**Test URL**: `https://podcasts.apple.com/us/podcast/babylist-natalie-gordon-how-a-new-mom-used-nap-time/id1150510297?i=1000733348575`

**Steps**: Same as Spotify test but for Apple Podcasts

**ZIP File Contents**:
- `index.html` - Audio player interface
- `audio-1.mp3` - Summary audio
- `audio-2.mp3` to `audio-N.mp3` - Topic segments
- `audio-99.mp3` - Full article audio
- `audio-help.mp3` - Voice commands help
- `audiotours_search_content.txt` - Full text for search

**Generated Files**:
- `debug_apple_processor_output.json` - Apple processor results
- `debug_apple_orchestrator_input.json` - Orchestrator input
- `debug_apple_orchestrator_output.json` - Orchestrator response
- `debug_apple_final_article_content.txt` - Final database content

## Running Tests

### Individual Tests
```bash
# Run Spotify test
python test_spotify_processing.py

# Run Apple Podcasts test  
python test_apple_processing.py
```

### Complete Test Suite
```bash
# Run all tests with summary report
python test_suite_runner.py
```

### Test Suite Output
- Console output with real-time results
- JSON report: `test_suite_report_YYYYMMDD_HHMMSS.json`
- Individual debug files for each test

## Interpreting Results

### Success Indicators
- ✅ **Processor Success**: Content extracted (>100 chars for Spotify, >500 chars for Apple)
- ✅ **Orchestrator Success**: HTTP 200 response with article_id
- ✅ **Database Success**: Article stored with full content
- ✅ **ZIP File Success**: Complete audio package downloadable with all files

### Common Failure Patterns

#### 1. Spotify Issues
- **"Spotify – Web Player" (58 chars)**: Getting login page instead of episode content
- **"Insufficient content extracted"**: Browser automation needed
- **"No module named 'selenium'"**: Selenium not available locally

#### 2. Apple Podcasts Issues  
- **"Could not extract podcast ID"**: URL format issue
- **"Could not find RSS feed"**: iTunes API failure
- **"Episode ID not found in RSS"**: Wrong episode or RSS parsing issue

#### 3. Orchestrator Issues
- **HTTP 500 "foreign key constraint"**: Test user doesn't exist in database
- **HTTP 400**: Invalid payload format
- **Timeout**: Content too large or service overloaded

#### 4. Database Issues
- **"No article found"**: Orchestrator failed to create article
- **Content length mismatch**: Content truncated during processing
- **Foreign key violations**: Cleanup didn't remove all references

## Troubleshooting Guide

### 1. Database Cleanup Failures
```bash
# Manual cleanup if automated cleanup fails
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "
DELETE FROM news_audios WHERE article_id IN (
  SELECT article_id FROM article_requests WHERE url LIKE '%test_url%'
);
DELETE FROM newsletters_article_link WHERE article_requests_id IN (
  SELECT article_id FROM article_requests WHERE url LIKE '%test_url%'  
);
DELETE FROM article_requests WHERE url LIKE '%test_url%';
"
```

### 2. Missing Test User
```bash
# Create test user if missing
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "
INSERT INTO users (secret_id, created_at) 
VALUES ('test_user_spotify', NOW()), ('test_user_apple', NOW()) 
ON CONFLICT (secret_id) DO NOTHING;
"
```

### 3. Container Service Issues
```bash
# Check service status
docker ps | grep -E "(newsletter|orchestrator|postgres)"

# Restart services if needed
docker restart newsletter-processor-1 news-orchestrator-1 development-postgres-2-1
```

### 4. Selenium/Browser Automation Issues
```bash
# Test Selenium in container
docker exec newsletter-processor-1 python3 -c "import selenium; print('Selenium OK')"

# Check Chrome installation
docker exec newsletter-processor-1 which google-chrome
```

## Expected Results (When Working)

### Spotify Processing
- **Processor Output**: 500-2000 chars of episode description
- **Orchestrator**: HTTP 200 with article_id
- **Database**: Full episode content stored

### Apple Podcasts Processing  
- **Processor Output**: 1000-3000 chars of episode description
- **Orchestrator**: HTTP 200 with article_id
- **Database**: Full episode content stored

## Adding New Tests

### 1. Create Test Script
```python
# Follow pattern from existing tests:
# - Database cleanup function
# - Direct processor test
# - Orchestrator test  
# - Database verification
# - Debug file generation
```

### 2. Add to Test Suite
```python
# In test_suite_runner.py, add to tests list:
tests = [
    ("Spotify Processing", "test_spotify_processing.py"),
    ("Apple Podcasts Processing", "test_apple_processing.py"),
    ("New Technology", "test_new_technology.py"),  # Add here
]
```

### 3. Update Documentation
- Add test description to this file
- Document expected results
- Add troubleshooting steps

## Integration with Development Workflow

### Before Code Changes
```bash
# Run baseline tests to ensure current functionality
python test_suite_runner.py
```

### After Code Changes
```bash
# Run tests to verify fixes/changes
python test_suite_runner.py

# Compare results with baseline
# Check debug files for detailed analysis
```

### Continuous Integration
- Tests can be automated in CI/CD pipeline
- JSON reports enable automated result analysis
- Debug files provide detailed failure analysis

## Amazon-Q Agent Instructions

When asked to run tests and interpret results:

1. **Run the test suite**: `python test_suite_runner.py`
2. **Check the summary**: Look for pass/fail counts and success rate
3. **Analyze failures**: 
   - Check console output for immediate errors
   - Review debug files for detailed analysis
   - Compare processor output vs database content
4. **Identify root causes**:
   - Content extraction issues (processor level)
   - Service communication issues (orchestrator level)  
   - Data persistence issues (database level)
5. **Provide actionable recommendations**:
   - Specific fixes needed
   - Services to restart
   - Code changes required

The test system is designed to provide complete visibility into the newsletter processing pipeline, making it easy to identify and fix issues at any stage.

## ZIP File Access and Verification

### How to Access ZIP Files for Verification

#### Step 1: Get Article ID
```bash
# From test output, or query database for recent articles
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "
SELECT article_id, request_string, finished_at 
FROM article_requests 
WHERE status = 'finished' 
ORDER BY finished_at DESC LIMIT 5;"
```

#### Step 2: Download ZIP File
```bash
# Replace [ARTICLE_ID] with actual article ID from Step 1
curl -X GET "http://localhost:5012/download/[ARTICLE_ID]" -o "article.zip"

# Example with real article ID:
curl -X GET "http://localhost:5012/download/54756b09-58ce-4a50-86ba-f88808e208ba" -o "article.zip"
```

#### Step 3: Verify ZIP Contents
```bash
# List files in ZIP
unzip -l article.zip

# Extract ZIP to folder
unzip article.zip -d extracted_article/

# Test HTML player
open extracted_article/index.html  # macOS
start extracted_article/index.html  # Windows
```

### Manual ZIP Download Test
```bash
# Get article_id from test output
ARTICLE_ID="your-article-id-here"

# Download ZIP file
curl -X GET "http://localhost:5012/download/${ARTICLE_ID}" -o "test_${ARTICLE_ID}.zip"

# Extract and verify contents
unzip -l "test_${ARTICLE_ID}.zip"

# Expected files:
# - index.html (audio player)
# - audio-1.mp3 (summary)
# - audio-2.mp3 to audio-N.mp3 (topics)
# - audio-99.mp3 (full article)
# - audio-help.mp3 (voice commands)
# - audiotours_search_content.txt (full text)
```

### Automated ZIP Verification
```bash
# Test ZIP file integrity
python -c "
import zipfile
with zipfile.ZipFile('test_${ARTICLE_ID}.zip', 'r') as z:
    files = z.namelist()
    print(f'ZIP contains {len(files)} files:')
    for f in files:
        print(f'  - {f}')
    # Verify required files
    required = ['index.html', 'audio-1.mp3', 'audio-99.mp3']
    missing = [f for f in required if f not in files]
    if missing:
        print(f'ERROR: Missing files: {missing}')
    else:
        print('SUCCESS: All required files present')
"
```

### Expected ZIP Results (When Working)

#### Spotify Processing ZIP
- **File Count**: 6-8 files
- **Total Size**: 2-5 MB
- **Audio Files**: 4-6 MP3s (summary + topics + full article + help)
- **Text Files**: HTML player + search content

#### Apple Podcasts Processing ZIP  
- **File Count**: 6-8 files
- **Total Size**: 2-5 MB
- **Audio Files**: 4-6 MP3s (summary + topics + full article + help)
- **Text Files**: HTML player + search content

## Audio Quality Improvements

### Enhanced Text Cleaning (2025-11-07)
**Issue**: HTML entities and underscores causing poor audio pronunciation
**Solution**: Comprehensive text cleaning for both audio and search content

**Text Cleaning Applied**:
- `&nbsp;` → ` ` (space)
- `&amp;` → ` and `
- `_` → ` ` (underscores become spaces)
- `&mdash;` → ` - ` (em dash)
- `&copy;` → ` copyright `
- `&trade;` → ` trademark `
- Currency: `&euro;` → ` euros `
- Math: `&times;` → ` times `

**Latest Test Results**:
```bash
# Latest ZIP with enhanced audio pronunciation
curl -X GET "http://localhost:5012/download/e548d641-b415-4a00-8c9b-4cee4dab0545" -o "apple_podcasts_enhanced.zip"

# Verify clean search content
unzip -p apple_podcasts_enhanced.zip audiotours_search_content.txt | head -10
```

**Benefits**:
- ✅ **Audio Quality**: Natural pronunciation without "underscore" or HTML entities
- ✅ **Search Content**: Clean text for better search matching
- ✅ **User Experience**: Professional, clear audio narration