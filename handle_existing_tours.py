#!/usr/bin/env python3
"""
Handle Existing Tours Without Tour Content
Provides graceful error handling for translation attempts on old tours
"""

import psycopg2
import logging

def check_tour_content_availability():
    """Check which tours have tour content available"""
    conn = psycopg2.connect(
        host="development-postgres-2-1",
        database="audiotours",
        user="admin",
        password="password123"
    )
    
    try:
        cursor = conn.cursor()
        
        # Check total tours
        cursor.execute("SELECT COUNT(*) FROM audio_tours")
        total_tours = cursor.fetchone()[0]
        
        # Check tours with content
        cursor.execute("SELECT COUNT(*) FROM audio_tours WHERE tour_content IS NOT NULL AND tour_content != ''")
        tours_with_content = cursor.fetchone()[0]
        
        # Check tours without content
        cursor.execute("SELECT COUNT(*) FROM audio_tours WHERE tour_content IS NULL OR tour_content = ''")
        tours_without_content = cursor.fetchone()[0]
        
        print(f"Tour Content Analysis:")
        print(f"  Total tours: {total_tours}")
        print(f"  Tours with content: {tours_with_content}")
        print(f"  Tours without content: {tours_without_content}")
        print(f"  Content availability: {(tours_with_content/total_tours)*100:.1f}%")
        
        # List some tours without content
        cursor.execute("""
            SELECT id, tour_name, created_at 
            FROM audio_tours 
            WHERE tour_content IS NULL OR tour_content = ''
            ORDER BY created_at DESC 
            LIMIT 10
        """)
        
        old_tours = cursor.fetchall()
        if old_tours:
            print(f"\nRecent tours without content (showing up to 10):")
            for tour in old_tours:
                print(f"  ID {tour[0]}: {tour[1]} (created: {tour[2]})")
        
        return {
            'total': total_tours,
            'with_content': tours_with_content,
            'without_content': tours_without_content,
            'old_tours': old_tours
        }
        
    finally:
        conn.close()

def create_translation_error_response(tour_id):
    """Create a standardized error response for old tours"""
    return {
        'status': 'error',
        'error_code': 'OLD_TOUR_NO_CONTENT',
        'message': f'This is an old tour (ID: {tour_id}) created before tour content storage was implemented. Translation is not available for this tour. Please create a new tour instead.',
        'suggestion': 'Generate a new tour with the same location and tour type to enable translation features.',
        'tour_id': tour_id
    }

def update_translation_service_error_handling():
    """Update translation service to handle old tours gracefully"""
    error_handling_code = '''
    def translate_tour_with_graceful_error_handling(self, original_tour_id, target_language):
        """Enhanced translation with graceful error handling for old tours"""
        conn = self.get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Get original tour with tour_content
            cursor.execute(
                "SELECT id, tour_name, request_string, audio_tour, number_requested, lat, lng, tour_content, content_language, created_at FROM audio_tours WHERE id = %s", 
                (original_tour_id,)
            )
            original_tour = cursor.fetchone()
            if not original_tour:
                return {
                    'status': 'error',
                    'error_code': 'TOUR_NOT_FOUND',
                    'message': f'Tour with ID {original_tour_id} not found.'
                }
            
            tour_content = original_tour[7]  # tour_content column
            created_at = original_tour[9]    # created_at column
            
            if not tour_content:
                # This is an old tour without stored content
                logging.warning(f"Translation attempted on old tour {original_tour_id} without stored content")
                return {
                    'status': 'error',
                    'error_code': 'OLD_TOUR_NO_CONTENT',
                    'message': f'This is an old tour created before tour content storage was implemented. Translation is not available for this tour. Please create a new tour instead.',
                    'suggestion': 'Generate a new tour with the same location and tour type to enable translation features.',
                    'tour_id': original_tour_id,
                    'tour_name': original_tour[1],
                    'created_at': str(created_at)
                }
            
            # Proceed with normal translation for tours with content
            return self.translate_tour_with_audio(original_tour_id, target_language)
            
        except Exception as e:
            logging.error(f"Error in graceful translation handling: {e}")
            return {
                'status': 'error',
                'error_code': 'TRANSLATION_ERROR',
                'message': f'An error occurred during translation: {str(e)}'
            }
        finally:
            conn.close()
    '''
    
    print("Error handling code for translation service:")
    print(error_handling_code)
    return error_handling_code

if __name__ == '__main__':
    print("Analyzing tour content availability...")
    analysis = check_tour_content_availability()
    
    print(f"\nRecommendations:")
    if analysis['without_content'] > 0:
        print(f"- {analysis['without_content']} tours cannot be translated (old tours without stored content)")
        print(f"- Users attempting to translate these tours will receive a clear error message")
        print(f"- Suggest users create new tours for translation functionality")
    
    if analysis['with_content'] > 0:
        print(f"- {analysis['with_content']} tours are ready for translation")
        print(f"- These tours have stored content and can be translated to any supported language")
    
    print(f"\nError handling approach:")
    print(f"- Old tours: Return clear error message suggesting new tour creation")
    print(f"- New tours: Full translation functionality with stored content")
    print(f"- Graceful degradation: System continues working for both old and new tours")