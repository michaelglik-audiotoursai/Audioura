#!/usr/bin/env python3
"""
Test database storage and retrieval
Tests: UTF-8 → bytea → UTF-8 round trip
"""
import psycopg2
import os

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )

def test_database_storage():
    """Test database storage and retrieval"""
    print("DATABASE STORAGE TEST")
    print("=" * 50)
    
    # Read the Guy Raz content
    input_file = "step_4_after_guy_raz_specific_cleaning.txt"
    
    if not os.path.exists(input_file):
        print(f"ERROR: {input_file} not found. Run test_cleaning_pipeline.py first.")
        return
    
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract content
    content_start = content.find("============================================================\n\n")
    if content_start != -1:
        test_content = content[content_start + 62:]
    else:
        test_content = content
    
    # Format as article
    formatted_content = f"NEWSLETTER: Test Article\n\nCONTENT: {test_content}"
    
    print(f"Original content: {len(formatted_content)} chars")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create test table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_content_storage (
                id SERIAL PRIMARY KEY,
                article_text BYTEA,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Step 1: Store content as bytea (simulate orchestrator)
        utf8_bytes = formatted_content.encode('utf-8')
        cursor.execute(
            "INSERT INTO test_content_storage (article_text) VALUES (%s) RETURNING id",
            (utf8_bytes,)
        )
        test_id = cursor.fetchone()[0]
        conn.commit()
        
        with open("db_step1_stored.txt", 'w', encoding='utf-8') as f:
            f.write("=== DATABASE STEP 1: Store as Bytea ===\n")
            f.write(f"Test ID: {test_id}\n")
            f.write(f"UTF-8 Bytes Length: {len(utf8_bytes)} bytes\n")
            f.write("=" * 60 + "\n\n")
            f.write("Original content:\n")
            f.write(formatted_content)
        
        print(f"Step 1 (Store): {len(utf8_bytes)} bytes -> db_step1_stored.txt")
        
        # Step 2: Retrieve as bytea (simulate news generator)
        cursor.execute("SELECT article_text FROM test_content_storage WHERE id = %s", (test_id,))
        retrieved_bytes = cursor.fetchone()[0]
        
        with open("db_step2_retrieved_bytes.txt", 'w', encoding='utf-8') as f:
            f.write("=== DATABASE STEP 2: Retrieve as Bytea ===\n")
            f.write(f"Retrieved Bytes Length: {len(retrieved_bytes)} bytes\n")
            # Handle memoryview comparison
            if hasattr(retrieved_bytes, 'tobytes'):
                bytes_data = retrieved_bytes.tobytes()
            else:
                bytes_data = bytes(retrieved_bytes)
            f.write(f"Bytes Match Original: {bytes_data == utf8_bytes}\n")
            f.write("=" * 60 + "\n\n")
            f.write("Hex representation (first 200 bytes):\n")
            f.write(bytes_data[:200].hex() + "\n\n")
            f.write("Raw bytes (as received from database):\n")
            f.write(str(retrieved_bytes))
        
        print(f"Step 2 (Retrieve Bytes): {len(retrieved_bytes)} bytes -> db_step2_retrieved_bytes.txt")
        
        # Step 3: Decode to UTF-8 (simulate news generator)
        try:
            # Handle memoryview from psycopg2
            if hasattr(retrieved_bytes, 'tobytes'):
                bytes_data = retrieved_bytes.tobytes()
            else:
                bytes_data = bytes(retrieved_bytes)
            
            decoded_content = bytes_data.decode('utf-8')
            
            with open("db_step3_decoded_utf8.txt", 'w', encoding='utf-8') as f:
                f.write("=== DATABASE STEP 3: Decode UTF-8 ===\n")
                f.write(f"Decoded Length: {len(decoded_content)} chars\n")
                f.write(f"Content Match Original: {decoded_content == formatted_content}\n")
                f.write("=" * 60 + "\n\n")
                f.write(decoded_content)
            
            print(f"Step 3 (Decode UTF-8): {len(decoded_content)} chars -> db_step3_decoded_utf8.txt")
            
        except Exception as e:
            print(f"Step 3 (Decode UTF-8): ERROR - {e}")
            return
        
        # Step 4: PostgreSQL convert_from function (what mobile app uses)
        cursor.execute("SELECT convert_from(article_text, 'UTF8') FROM test_content_storage WHERE id = %s", (test_id,))
        pg_decoded = cursor.fetchone()[0]
        
        with open("db_step4_pg_convert_from.txt", 'w', encoding='utf-8') as f:
            f.write("=== DATABASE STEP 4: PostgreSQL convert_from ===\n")
            f.write(f"PostgreSQL Decoded Length: {len(pg_decoded)} chars\n")
            f.write(f"PG Content Match Original: {pg_decoded == formatted_content}\n")
            f.write(f"PG Content Match Python Decode: {pg_decoded == decoded_content}\n")
            f.write("=" * 60 + "\n\n")
            f.write(pg_decoded)
        
        print(f"Step 4 (PG convert_from): {len(pg_decoded)} chars -> db_step4_pg_convert_from.txt")
        
        # Cleanup
        cursor.execute("DELETE FROM test_content_storage WHERE id = %s", (test_id,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        # Summary
        print("\n" + "=" * 50)
        print("DATABASE STORAGE SUMMARY")
        print("=" * 50)
        print(f"Original: {len(formatted_content)} chars")
        print(f"UTF-8 Bytes: {len(utf8_bytes)} bytes")
        print(f"Retrieved Bytes: {len(retrieved_bytes)} bytes")
        print(f"Python Decoded: {len(decoded_content)} chars")
        print(f"PostgreSQL Decoded: {len(pg_decoded)} chars")
        
        # Handle memoryview for final comparison
        if hasattr(retrieved_bytes, 'tobytes'):
            final_bytes = retrieved_bytes.tobytes()
        else:
            final_bytes = bytes(retrieved_bytes)
            
        if (final_bytes == utf8_bytes and 
            decoded_content == formatted_content and 
            pg_decoded == formatted_content):
            print("\nSUCCESS: Database storage/retrieval works perfectly")
        else:
            print("\nERROR: Database storage/retrieval corrupted content")
            
    except Exception as e:
        print(f"Database test failed: {e}")

if __name__ == "__main__":
    test_database_storage()