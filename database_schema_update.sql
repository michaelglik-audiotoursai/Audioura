-- AudioTours Database Schema Update for Tour Content Storage
-- Phase 1: Add tour content storage columns to existing audio_tours table

-- Add tour content storage to existing table
ALTER TABLE audio_tours ADD COLUMN tour_content TEXT;
ALTER TABLE audio_tours ADD COLUMN content_language VARCHAR(10) DEFAULT 'en';

-- Add original tour linking for translations
ALTER TABLE audio_tours ADD COLUMN original_tour_id INTEGER REFERENCES audio_tours(id);

-- Create index for performance
CREATE INDEX idx_audio_tours_language ON audio_tours(content_language);
CREATE INDEX idx_audio_tours_original ON audio_tours(original_tour_id);

-- Update existing tours to mark them as English
UPDATE audio_tours SET content_language = 'en' WHERE content_language IS NULL;

-- Add comment for documentation
COMMENT ON COLUMN audio_tours.tour_content IS 'Original ChatGPT-generated tour narration text for translation purposes';
COMMENT ON COLUMN audio_tours.content_language IS 'Language code (en, es, fr, de, ru, zh) for tour content';
COMMENT ON COLUMN audio_tours.original_tour_id IS 'Reference to original tour for translations';