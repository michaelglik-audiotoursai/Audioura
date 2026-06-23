#!/usr/bin/env python3
"""
Test orchestrator processing pipeline step by step
Tests: JSON decode → UTF-8 encode → bytea storage simulation
"""
import json
import os

def test_orchestrator_pipeline():
    """Test the 3 steps of orchestrator processing"""
    print("ORCHESTRATOR PROCESSING PIPELINE TEST")
    print("=" * 50)
    
    # Read the cleaned Guy Raz content from step 4
    input_file = "step_4_after_guy_raz_specific_cleaning.txt"
    
    if not os.path.exists(input_file):
        print(f"ERROR: {input_file} not found. Run test_cleaning_pipeline.py first.")
        return
    
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract just the content part (skip header)
    content_start = content.find("============================================================\n\n")
    if content_start != -1:
        clean_content = content[content_start + 62:]
    else:
        clean_content = content
    
    print(f"Input content: {len(clean_content)} chars")
    
    # Step 1: Article Formatting (simulate newsletter processor)
    title = "Newsletter Article"
    formatted_content = f"NEWSLETTER: {title}\n\nCONTENT: {clean_content}"
    
    with open("orchestrator_step1_formatted.txt", 'w', encoding='utf-8') as f:
        f.write("=== ORCHESTRATOR STEP 1: Article Formatting ===\n")
        f.write(f"Length: {len(formatted_content)} chars\n")
        f.write("=" * 60 + "\n\n")
        f.write(formatted_content)
    
    print(f"Step 1 (Article Formatting): {len(formatted_content)} chars -> orchestrator_step1_formatted.txt")
    
    # Step 2: JSON Payload Creation (simulate newsletter processor)
    payload = {
        'article_text': formatted_content,
        'request_string': title,
        'secret_id': 'test_user',
        'major_points_count': 4
    }
    
    # Convert to JSON string (what gets transmitted)
    json_string = json.dumps(payload, ensure_ascii=False)
    
    with open("orchestrator_step2_json_payload.txt", 'w', encoding='utf-8') as f:
        f.write("=== ORCHESTRATOR STEP 2: JSON Payload Creation ===\n")
        f.write(f"JSON Length: {len(json_string)} chars\n")
        f.write(f"Article Text Length: {len(payload['article_text'])} chars\n")
        f.write("=" * 60 + "\n\n")
        f.write("JSON Structure:\n")
        f.write(f"- article_text: {len(payload['article_text'])} chars\n")
        f.write(f"- request_string: '{payload['request_string']}'\n")
        f.write(f"- secret_id: '{payload['secret_id']}'\n")
        f.write(f"- major_points_count: {payload['major_points_count']}\n\n")
        f.write("Full JSON:\n")
        f.write(json_string)
    
    print(f"Step 2 (JSON Payload): {len(json_string)} chars -> orchestrator_step2_json_payload.txt")
    
    # Step 3: JSON Decode (simulate orchestrator receiving)
    try:
        decoded_payload = json.loads(json_string)
        decoded_article_text = decoded_payload['article_text']
        
        with open("orchestrator_step3_json_decoded.txt", 'w', encoding='utf-8') as f:
            f.write("=== ORCHESTRATOR STEP 3: JSON Decode ===\n")
            f.write(f"Decoded Article Text Length: {len(decoded_article_text)} chars\n")
            f.write(f"Decode Success: True\n")
            f.write("=" * 60 + "\n\n")
            f.write(decoded_article_text)
        
        print(f"Step 3 (JSON Decode): {len(decoded_article_text)} chars -> orchestrator_step3_json_decoded.txt")
        
    except Exception as e:
        print(f"Step 3 (JSON Decode): ERROR - {e}")
        return
    
    # Step 4: UTF-8 Encode (simulate orchestrator database prep)
    try:
        utf8_bytes = decoded_article_text.encode('utf-8')
        
        with open("orchestrator_step4_utf8_encoded.txt", 'w', encoding='utf-8') as f:
            f.write("=== ORCHESTRATOR STEP 4: UTF-8 Encode ===\n")
            f.write(f"UTF-8 Bytes Length: {len(utf8_bytes)} bytes\n")
            f.write(f"Encode Success: True\n")
            f.write("=" * 60 + "\n\n")
            f.write("Hex representation (first 200 bytes):\n")
            f.write(utf8_bytes[:200].hex() + "\n\n")
            f.write("Decoded back to text:\n")
            f.write(utf8_bytes.decode('utf-8'))
        
        print(f"Step 4 (UTF-8 Encode): {len(utf8_bytes)} bytes -> orchestrator_step4_utf8_encoded.txt")
        
    except Exception as e:
        print(f"Step 4 (UTF-8 Encode): ERROR - {e}")
        return
    
    # Step 5: Bytea Storage Simulation (simulate PostgreSQL bytea)
    try:
        # Simulate what PostgreSQL does with bytea
        # PostgreSQL stores UTF-8 bytes directly in bytea column
        
        with open("orchestrator_step5_bytea_simulation.txt", 'w', encoding='utf-8') as f:
            f.write("=== ORCHESTRATOR STEP 5: Bytea Storage Simulation ===\n")
            f.write(f"Bytea Length: {len(utf8_bytes)} bytes\n")
            f.write("=" * 60 + "\n\n")
            f.write("PostgreSQL bytea hex format:\n")
            f.write("\\\\x" + utf8_bytes.hex() + "\n\n")
            f.write("Decoded from bytea (what convert_from(bytea, 'UTF8') returns):\n")
            f.write(utf8_bytes.decode('utf-8'))
        
        print(f"Step 5 (Bytea Storage): {len(utf8_bytes)} bytes -> orchestrator_step5_bytea_simulation.txt")
        
    except Exception as e:
        print(f"Step 5 (Bytea Storage): ERROR - {e}")
        return
    
    # Summary
    print("\n" + "=" * 50)
    print("ORCHESTRATOR PIPELINE SUMMARY")
    print("=" * 50)
    print(f"Original content: {len(clean_content)} chars")
    print(f"Step 1 (Formatted): {len(formatted_content)} chars")
    print(f"Step 2 (JSON): {len(json_string)} chars")
    print(f"Step 3 (Decoded): {len(decoded_article_text)} chars")
    print(f"Step 4 (UTF-8): {len(utf8_bytes)} bytes")
    print(f"Step 5 (Bytea): {len(utf8_bytes)} bytes")
    
    # Verify content integrity
    if decoded_article_text == formatted_content:
        print("\nSUCCESS: Content preserved through orchestrator pipeline")
    else:
        print("\nERROR: Content corrupted in orchestrator pipeline")
        print(f"Original length: {len(formatted_content)}")
        print(f"Final length: {len(decoded_article_text)}")

if __name__ == "__main__":
    test_orchestrator_pipeline()