# AudioTours Translation Project - Complete Architecture

## Project Overview
**Objective**: Add multi-language support to AudioTours without modifying existing Docker services
**Approach**: Post-processing translation of ZIP files with mobile language preferences
**Target Languages**: Spanish, French, German, Russian, Chinese (Simplified)

## Core Design Principles
- ✅ **Zero Service Changes**: Keep all existing Docker services unchanged
- ✅ **Post-Processing Translation**: Translate ZIP files after English creation
- ✅ **Mobile Language Preferences**: Multi-language selection in mobile app
- ✅ **Single Table Architecture**: Add language fields to existing tables
- ✅ **On-Demand Translation**: Translate only when requested
- ✅ **Cost Optimization**: AWS Translate + Polly for reliability

## Database Schema Changes

### Tables Requiring Language Field Addition
```sql
-- Tours table (primary content)
ALTER TABLE audio_tours ADD COLUMN language VARCHAR(10) DEFAULT 'en';
ALTER TABLE audio_tours ADD COLUMN original_tour_id INTEGER REFERENCES audio_tours(id);
CREATE INDEX idx_audio_tours_language ON audio_tours(language);

-- Newsletter articles
ALTER TABLE article_requests ADD COLUMN language VARCHAR(10) DEFAULT 'en';
ALTER TABLE article_requests ADD COLUMN original_article_id VARCHAR(255) REFERENCES article_requests(article_id);
CREATE INDEX idx_article_requests_language ON article_requests(language);

-- News articles
ALTER TABLE news_audios ADD COLUMN language VARCHAR(10) DEFAULT 'en';
ALTER TABLE news_audios ADD COLUMN original_article_id VARCHAR(255) REFERENCES news_audios(article_id);
CREATE INDEX idx_news_audios_language ON news_audios(language);

-- Tour requests (for tracking)
ALTER TABLE tour_requests ADD COLUMN language VARCHAR(10) DEFAULT 'en';

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

## API Endpoints - Multi-Language Support

### Home Page Tours
```
GET /tours-near/{lat}/{lng}?languages=en|es|ru
Response: Tours available in requested languages
```

### Download Endpoints
```
GET /download/{tour_id}?languages=es|en|ru&user_id=USER123
GET /download/{article_id}?languages=es|en|ru&user_id=USER123
Response: Content in all available requested languages
```

## Translation Service Architecture

### New Translation Microservice (Port 5030)
```python
# Core translation service
class TranslationService:
    def __init__(self):
        self.translate_client = boto3.client('translate')  # AWS Translate
        self.polly_client = boto3.client('polly')          # AWS Polly TTS
        self.executor = ThreadPoolExecutor(max_workers=5)  # Parallel processing
    
    def translate_multiple_languages(self, content_id, content_type, languages):
        # Translate content into multiple languages simultaneously
        pass
    
    def translate_tour_zip(self, original_zip_data, target_language):
        # Extract ZIP → Translate text → Generate audio → Rebuild ZIP
        pass
    
    def translate_article(self, article_text, target_language):
        # Translate content → Generate audio → Create ZIP
        pass
```

## User Experience Workflow

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

## Mobile App Integration Points

### Language Selection UI
- **Home Page**: Multi-select language chips for tour browsing
- **Generate Page**: Language selection for news article generation
- **Listen Page**: Language tabs for downloaded content
- **NO Settings Page**: Language selection contextual to content

### API Integration
```dart
// Multi-language tour request
Future<List<Tour>> getToursNear(double lat, double lng, List<String> languages) async {
  String languageParam = languages.join('|');
  final response = await http.get(
    Uri.parse('$baseUrl/tours-near/$lat/$lng?languages=$languageParam')
  );
  return parseMultiLanguageTours(response);
}

// Multi-language download
Future<void> downloadContent(String contentId, List<String> languages) async {
  String languageParam = languages.join('|');
  showTranslationProgress(languages);
  
  final response = await http.get(
    Uri.parse('$baseUrl/download/$contentId?languages=$languageParam&user_id=$userId')
  );
  
  await processMultiLanguageContent(response);
  hideTranslationProgress();
}
```

## Cost Analysis

### Translation Costs (AWS Translate + Polly)
- **AWS Translate**: $15 per 1 million characters
- **AWS Polly**: $4 per 1 million characters
- **Total**: $19 per 1 million characters

### Usage Scenarios
- **Light Usage** (50 tours + 100 articles/month): ~$31/month
- **Medium Usage** (200 tours + 500 articles/month): ~$134/month
- **Heavy Usage** (500 tours + 1000 articles/month): ~$296/month

### Per Content Costs
- **Per Tour** (5 languages): ~$1.86
- **Per Article** (5 languages): ~$0.60

## Implementation Timeline

### Phase 1: Database & Core Service (Week 1)
**Services Amazon-Q Responsibilities**:
- Add language fields to existing tables
- Create translation service container (Port 5030)
- Implement AWS Translate + Polly integration
- Create basic translation workflow

### Phase 2: Multi-Language APIs (Week 2)
**Services Amazon-Q Responsibilities**:
- Update existing endpoints to support multiple languages
- Implement parallel translation processing
- Add translation progress tracking
- Deploy enhanced APIs

### Phase 3: Mobile App Integration (Week 3)
**Mobile App Amazon-Q Responsibilities**:
- Add language selection UI (Home, Generate, Listen pages)
- Implement multi-language download flow
- Add translation progress indicators
- Update voice control for language support

### Phase 4: Optimization & Testing (Week 4)
**All Amazon-Qs Collaboration**:
- Implement caching and cost optimization
- Add error handling and fallbacks
- Performance testing and optimization
- End-to-end integration testing

## Technical Specifications

### Translation Workflow
```
1. User Selects Content + Languages
2. Check Existing Translations (cache)
3. Translate Missing Languages (parallel)
4. Generate Audio in Target Languages
5. Store Translated Content in Same Tables
6. Return Multi-Language Content to Mobile App
```

### Database Storage Pattern
```
Original Tour:  {id: 123, language: 'en', original_tour_id: NULL}
Spanish Tour:   {id: 124, language: 'es', original_tour_id: 123}
French Tour:    {id: 125, language: 'fr', original_tour_id: 123}
German Tour:    {id: 126, language: 'de', original_tour_id: 123}
```

## Quality Assurance

### Translation Quality
- **AWS Translate**: Enterprise-grade translation quality
- **AWS Polly**: Natural-sounding multi-language TTS
- **Context Preservation**: Maintain tour/article structure
- **Error Handling**: Fallback to original language if translation fails

### Performance Optimization
- **Parallel Processing**: Translate multiple languages simultaneously
- **Smart Caching**: Store translations permanently (one-time cost)
- **On-Demand**: Only translate when requested
- **Background Jobs**: Pre-translate popular content

## Success Metrics

### Technical Metrics
- Translation accuracy and quality
- Translation speed (target: <2 minutes for 5 languages)
- Cost per translation
- Cache hit rate
- User engagement with translated content

### Business Metrics
- Multi-language content usage
- User retention with language features
- Cost per active user
- Revenue impact from international users

## Risk Mitigation

### Technical Risks
- **Translation Quality**: Use AWS enterprise APIs
- **Cost Overrun**: Implement usage monitoring and limits
- **Performance**: Parallel processing and caching
- **Service Reliability**: Fallback to original language

### Business Risks
- **User Adoption**: Gradual rollout with user feedback
- **Cost Management**: Start with popular content only
- **Quality Control**: Manual review of critical translations

## Communication Protocols

### Between Amazon-Q Teams
- **Services ↔ Mobile App**: Via communication layer documents
- **Progress Tracking**: Weekly status updates
- **Issue Resolution**: Shared issue tracking
- **Testing Coordination**: Joint integration testing

### Documentation Requirements
- API specification updates
- Mobile app UI/UX guidelines
- Translation quality standards
- Cost monitoring procedures

---

**Project Status**: Ready for Phase 1 Implementation
**Next Step**: Services Amazon-Q database schema updates
**Timeline**: 4 weeks total implementation
**Budget**: $50-150/month estimated operational cost