#!/usr/bin/env python3
"""
Test Step 3 Guy Raz content for binary detection
"""

def is_binary_content_original(text):
    """Original binary detection function from newsletter processor"""
    if not text or not isinstance(text, str):
        return True
    
    try:
        # Check for null bytes (common in binary)
        if '\x00' in text:
            return True
        
        # Check for excessive non-printable characters (more aggressive)
        printable_chars = 0
        control_chars = 0
        
        for c in text:
            if c.isprintable() or c.isspace():
                printable_chars += 1
            elif ord(c) < 32 and c not in '\n\r\t':  # Control characters
                control_chars += 1
        
        total_chars = len(text)
        if total_chars > 0:
            printable_ratio = printable_chars / total_chars
            control_ratio = control_chars / total_chars
            
            # More aggressive detection
            if printable_ratio < 0.8:  # Less than 80% printable = likely binary
                print(f"FAIL: Printable ratio {printable_ratio:.4f} < 0.8")
                return True
            if control_ratio > 0.1:  # More than 10% control chars = likely binary
                print(f"FAIL: Control ratio {control_ratio:.4f} > 0.1")
                return True
        
        # Check for common binary patterns
        binary_patterns = [
            '\ufffd',  # Unicode replacement character
            '\u0000',  # Null character
            '\u0001',  # Start of heading
            '\u0002',  # Start of text
        ]
        
        for pattern in binary_patterns:
            if pattern in text:
                print(f"FAIL: Found binary pattern {repr(pattern)}")
                return True
        
        # Check for suspicious character sequences (new)
        suspicious_count = 0
        for i in range(len(text) - 1):
            c1, c2 = text[i], text[i + 1]
            # Look for patterns like random chars followed by symbols
            if (not c1.isalnum() and not c1.isspace() and 
                not c2.isalnum() and not c2.isspace() and
                c1 != c2):  # Different non-alphanumeric chars in sequence
                suspicious_count += 1
        
        if total_chars > 0 and suspicious_count / total_chars > 0.3:  # 30% suspicious = binary
            suspicious_ratio = suspicious_count / total_chars
            print(f"FAIL: Suspicious ratio {suspicious_ratio:.4f} > 0.3")
            return True
        
        # Try to encode as UTF-8 to catch encoding issues
        text.encode('utf-8')
        
        return False
        
    except (UnicodeError, UnicodeEncodeError, UnicodeDecodeError) as e:
        print(f"FAIL: Unicode error {e}")
        return True
    except Exception as e:
        print(f"FAIL: Exception {e}")
        return True

def main():
    # Read step 3 content
    try:
        with open('step_3_after_is_binary_content_validation.txt', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract just the content part (skip the header)
        lines = content.split('\n')
        content_start = False
        actual_content = []
        
        for line in lines:
            if line.strip() == '=' * 60:
                content_start = True
                continue
            if content_start and line.strip():
                actual_content.append(line)
        
        step3_text = '\n'.join(actual_content)
        
        print("=== TESTING STEP 3 CONTENT ===")
        print(f"Content length: {len(step3_text)} chars")
        print(f"Content preview: {step3_text[:200]}...")
        print()
        
        print("Testing with original binary detection function:")
        is_binary = is_binary_content_original(step3_text)
        print(f"Result: {'BINARY' if is_binary else 'CLEAN'}")
        
        if not is_binary:
            print("\nStep 3 content passes binary detection!")
            print("The issue must be happening elsewhere in the pipeline.")
        
    except FileNotFoundError:
        print("Error: step_3_after_is_binary_content_validation.txt not found")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()