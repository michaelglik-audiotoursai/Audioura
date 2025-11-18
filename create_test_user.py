#!/usr/bin/env python3
"""
Create test user for Phase 2 testing
"""
import psycopg2
import os

def create_test_user():
    """Create test user in database"""
    
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            database=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            port=os.getenv('DB_PORT', '5433')
        )
        cursor = conn.cursor()
        
        # Create test user
        cursor.execute("""
            INSERT INTO users (secret_id, created_at)
            VALUES (%s, NOW())
            ON CONFLICT (secret_id) DO NOTHING
        """, ("PHASE2-TEST-USER",))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("Test user created successfully")
        return True
        
    except Exception as e:
        print(f"Error creating test user: {e}")
        return False

if __name__ == "__main__":
    create_test_user()