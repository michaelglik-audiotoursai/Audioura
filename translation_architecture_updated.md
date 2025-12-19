# Updated Translation Architecture - AudioTours

## Architecture Overview
**Approach**: Single tables with language field, multi-language API support, on-demand translation

## Database Schema Updates

### Tables Requiring Language Field
```sql
-- Tours table (primary content)
ALTER TABLE audio_tours ADD COLUMN language VARCHAR(10) DEFAULT 'en';
ALTER TABLE audio_tours ADD COLUMN original_tour_id INTEGER REFERENCES audio_tours(id);
CREATE INDEX idx_audio_tours_language ON audio_tours(language);
CREATE INDEX idx_audio_tours_original ON audio_tours(original_tour_id);

-- Newsletter articles
ALTER TABLE article_requests ADD COLUMN language VARCHAR(10) DEFAULT 'en';
ALTER TABLE article_requests ADD COLUMN original_article_id VARCHAR(255) REFERENCES article_requests(article_id);
CREATE INDEX idx_article_requests_language ON article_requests(language);
CREATE INDEX idx_article_requests_original ON article_requests(original_article_id);

-- News articles
ALTER TABLE news_audios ADD COLUMN language VARCHAR(10) DEFAULT 'en';
ALTER TABLE news_audios ADD COLUMN original_article_id VARCHAR(255) REFERENCES news_audios(article_id);
CREATE INDEX idx_news_audios_language ON news_audios(language);
CREATE INDEX idx_news_audios_original ON news_audios(original_article_id);

-- Tour requests (for tracking)
ALTER TABLE tour_requests ADD COLUMN language VARCHAR(10) DEFAULT 'en';
CREATE INDEX idx_tour_requests_language ON tour_requests(language);

-- Supported languages configuration
CREATE TABLE supported_languages (
    language_code VARCHAR(10) PRIMARY KEY,
    language_name VARCHAR(50) NOT NULL,
    polly_voice_id VARCHAR(50),
    enabled BOOLEAN DEFAULT TRUE
);

INSERT INTO supported_languages VALUES 
('en', 'English', 'Joanna', TRUE),
('es', 'Spanish', 'Lucia', TRUE),
('fr', 'French', 'Celine', TRUE),
('de', 'German', 'Marlene', TRUE),
('ru', 'Russian', 'Tatyana', TRUE),
('zh', 'Chinese (Simplified)', 'Zhiyu', TRUE);
```

## Updated API Endpoints

### Home Page - Multi-Language Tours
```python
@app.route('/tours-near/<lat>/<lng>')
def get_tours_near(lat, lng):
    languages = request.args.get('languages', 'en').split('|')
    
    # Get tours in all requested languages
    tours_by_language = {}
    for lang in languages:
        tours = get_tours_for_language(lat, lng, lang)
        tours_by_language[lang] = tours
    
    return jsonify({
        'tours_by_language': tours_by_language,
        'available_languages': languages
    })
```

### Download - Multi-Language Content
```python
@app.route('/download/<content_id>')
def download_content(content_id):
    languages = request.args.get('languages', 'en').split('|')
    user_id = request.args.get('user_id')
    
    # Check if translations exist, create if needed
    available_content = {}
    for lang in languages:
        content = get_or_create_translation(content_id, lang)
        if content:
            available_content[lang] = content
    
    return jsonify({
        'available_languages': list(available_content.keys()),
        'download_urls': {lang: f'/download/{content_id}/{lang}' for lang in available_content.keys()}
    })
```

## Translation Workflow

### Tour Translation Process
```python
def translate_tour_on_demand(original_tour_id, target_languages):
    """
    Translate tour into multiple languages simultaneously
    """
    original_tour = get_tour_by_id(original_tour_id)
    translation_jobs = []
    
    for lang in target_languages:
        if lang == 'en':
            continue  # Skip English (original)
            
        # Check if translation already exists
        existing = get_tour_translation(original_tour_id, lang)
        if existing:
            continue
            
        # Start translation job
        job = start_tour_translation_job(original_tour, lang)
        translation_jobs.append(job)
    
    # Wait for all translations to complete
    wait_for_translation_jobs(translation_jobs)
    
    return get_translated_tours(original_tour_id, target_languages)

def start_tour_translation_job(original_tour, target_language):
    """
    Translate single tour to target language
    """
    # Extract ZIP contents
    zip_contents = extract_tour_zip(original_tour.tour_data)
    
    # Translate text content
    translated_html = translate_text(zip_contents['html'], target_language)
    translated_search = translate_text(zip_contents['search_content'], target_language)
    
    # Generate new audio files
    audio_files = generate_translated_audio(translated_html, target_language)
    
    # Create new ZIP
    translated_zip = create_translated_zip(translated_html, translated_search, audio_files)
    
    # Store in database
    new_tour = create_tour_record(
        tour_name=translate_text(original_tour.tour_name, target_language),
        tour_data=translated_zip,
        language=target_language,
        original_tour_id=original_tour.id,
        coordinates=original_tour.coordinates
    )
    
    return new_tour
```

### Article Translation Process
```python
def translate_article_on_demand(original_article_id, target_languages):
    """
    Translate article into multiple languages
    """
    original_article = get_article_by_id(original_article_id)
    
    for lang in target_languages:
        if lang == 'en' or get_article_translation(original_article_id, lang):
            continue
            
        # Translate content
        translated_text = translate_text(original_article.article_text, lang)
        translated_title = translate_text(original_article.request_string, lang)
        
        # Create new article record
        create_article_record(
            article_id=generate_uuid(),
            article_text=translated_text,
            request_string=translated_title,
            language=lang,
            original_article_id=original_article_id,
            url=original_article.url,
            status='finished'
        )
```

## Mobile App Integration Points

### Home Page Language Selection
```dart
class HomePageLanguageSelector extends StatefulWidget {
  @override
  Widget build(BuildContext context) {
    return MultiSelectChip(
      languages: ['en', 'es', 'fr', 'de', 'ru', 'zh'],
      selectedLanguages: selectedLanguages,
      onSelectionChanged: (languages) {
        setState(() {
          selectedLanguages = languages;
        });
        loadToursForLanguages(languages);
      },
    );
  }
}
```

### Download Page Language Selection
```dart
Future<void> downloadTourInLanguages(String tourId, List<String> languages) async {
  // Show translation progress
  showTranslationProgress(languages);
  
  // Request translation
  final response = await http.get(
    Uri.parse('$baseUrl/download/$tourId?languages=${languages.join('|')}&user_id=$userId')
  );
  
  // Handle multi-language response
  final availableLanguages = response.data['available_languages'];
  
  // Download each language version
  for (String lang in availableLanguages) {
    await downloadLanguageVersion(tourId, lang);
  }
  
  hideTranslationProgress();
}
```

### Listen Page Multi-Language Display
```dart
class ListenPageLanguageTabs extends StatefulWidget {
  final Map<String, TourContent> toursByLanguage;
  
  @override
  Widget build(BuildContext context) {
    return TabBarView(
      children: toursByLanguage.entries.map((entry) {
        return TourContentView(
          language: entry.key,
          content: entry.value,
        );
      }).toList(),
    );
  }
}
```

## Translation Service Implementation

### Core Translation Service (Port 5030)
```python
from flask import Flask, request, jsonify
import boto3
from concurrent.futures import ThreadPoolExecutor
import zipfile
import uuid

class TranslationService:
    def __init__(self):
        self.translate_client = boto3.client('translate')
        self.polly_client = boto3.client('polly')
        self.executor = ThreadPoolExecutor(max_workers=5)
    
    def translate_multiple_languages(self, content_id, content_type, languages):
        """
        Translate content into multiple languages simultaneously
        """
        translation_futures = []
        
        for lang in languages:
            if lang != 'en':  # Skip English
                future = self.executor.submit(
                    self.translate_single_language, 
                    content_id, content_type, lang
                )
                translation_futures.append((lang, future))
        
        # Wait for all translations
        results = {}
        for lang, future in translation_futures:
            try:
                results[lang] = future.result(timeout=300)  # 5 minute timeout
            except Exception as e:
                results[lang] = {'error': str(e)}
        
        return results
    
    def translate_single_language(self, content_id, content_type, target_language):
        """
        Translate single piece of content to target language
        """
        if content_type == 'tour':
            return self.translate_tour(content_id, target_language)
        elif content_type == 'article':
            return self.translate_article(content_id, target_language)
    
    def translate_text_aws(self, text, target_language):
        """
        Translate text using AWS Translate
        """
        response = self.translate_client.translate_text(
            Text=text,
            SourceLanguageCode='en',
            TargetLanguageCode=target_language
        )
        return response['TranslatedText']
    
    def generate_audio_aws(self, text, target_language):
        """
        Generate audio using AWS Polly
        """
        voice_map = {
            'es': 'Lucia',
            'fr': 'Celine', 
            'de': 'Marlene',
            'ru': 'Tatyana',
            'zh': 'Zhiyu'
        }
        
        response = self.polly_client.synthesize_speech(
            Text=text,
            OutputFormat='mp3',
            VoiceId=voice_map.get(target_language, 'Joanna')
        )
        
        return response['AudioStream'].read()

# Flask endpoints
app = Flask(__name__)
translation_service = TranslationService()

@app.route('/translate', methods=['POST'])
def translate_content():
    data = request.json
    content_id = data['content_id']
    content_type = data['content_type']  # 'tour' or 'article'
    languages = data['languages']  # ['es', 'fr', 'de']
    
    results = translation_service.translate_multiple_languages(
        content_id, content_type, languages
    )
    
    return jsonify({
        'status': 'completed',
        'translations': results
    })
```

## User Experience Flow

### Tour Download Flow
1. **Home Page**: User selects tour, chooses languages (es|fr|de)
2. **Translation Request**: App calls `/download/tour123?languages=es|fr|de`
3. **Translation Progress**: "Translating tour into Spanish, French, German..."
4. **Parallel Translation**: All 3 languages translated simultaneously
5. **Listen Page**: User sees tabs for English, Spanish, French, German
6. **Language Switching**: User can switch between languages seamlessly

### Article Generation Flow
1. **Generate Page**: User enters topic, selects languages
2. **English Processing**: Article generated in English first (existing flow)
3. **Translation Request**: If languages selected, translate English article
4. **Multi-Language Result**: User gets article in all requested languages

## Cost Optimization Features

### Smart Caching
```python
def get_or_create_translation(content_id, target_language):
    """
    Check cache first, translate only if needed
    """
    # Check if translation exists
    existing = get_cached_translation(content_id, target_language)
    if existing:
        return existing
    
    # Create new translation
    return create_new_translation(content_id, target_language)
```

### Batch Processing
```python
def batch_translate_popular_content():
    """
    Background job to pre-translate popular content
    """
    popular_tours = get_popular_tours()
    popular_articles = get_popular_articles()
    
    for content in popular_tours + popular_articles:
        if should_translate(content):
            translate_content_background(content)
```

## Implementation Timeline

### Phase 1: Database & Core Service (Week 1)
- Add language fields to existing tables
- Create translation service container
- Implement basic AWS Translate + Polly integration

### Phase 2: Multi-Language APIs (Week 2)
- Update existing endpoints to support multiple languages
- Implement translation workflow
- Add parallel processing for multiple languages

### Phase 3: Mobile App Integration (Week 3)
- Add language selection UI to Home, Generate, Listen pages
- Implement multi-language download flow
- Add translation progress indicators

### Phase 4: Optimization & Testing (Week 4)
- Implement caching and cost optimization
- Add error handling and fallbacks
- Performance testing and optimization

**Total Timeline**: 4 weeks
**Estimated Monthly Cost**: $50-150 depending on usage
**Recommended Start**: AWS Translate + Polly for reliability