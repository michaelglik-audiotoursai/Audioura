#!/usr/bin/env python3
"""
Test content cleaning pipeline step by step
Reads extracted Guy Raz content and tests each cleaning function
"""
import re
import sys
import os

def is_binary_content(text):
    """Binary content detection from newsletter processor"""
    if not text or not isinstance(text, str):
        return True
    
    try:
        # Check for null bytes
        if '\x00' in text:
            return True
        
        # Check printable ratio
        printable_chars = 0
        control_chars = 0
        
        for c in text:
            if c.isprintable() or c.isspace():
                printable_chars += 1
            elif ord(c) < 32 and c not in '\n\r\t':
                control_chars += 1
        
        total_chars = len(text)
        if total_chars > 0:
            printable_ratio = printable_chars / total_chars
            control_ratio = control_chars / total_chars
            
            if printable_ratio < 0.8:
                return True
            if control_ratio > 0.1:
                return True
        
        # Check for binary patterns
        binary_patterns = ['\ufffd', '\u0000', '\u0001', '\u0002']
        for pattern in binary_patterns:
            if pattern in text:
                return True
        
        # Check suspicious sequences
        suspicious_count = 0
        for i in range(len(text) - 1):
            c1, c2 = text[i], text[i + 1]
            if (not c1.isalnum() and not c1.isspace() and 
                not c2.isalnum() and not c2.isspace() and
                c1 != c2):
                suspicious_count += 1
        
        if total_chars > 0 and suspicious_count / total_chars > 0.3:
            return True
        
        text.encode('utf-8')
        return False
        
    except (UnicodeError, UnicodeEncodeError, UnicodeDecodeError):
        return True
    except Exception:
        return True

def clean_text_content(text):
    """Enhanced clean function from newsletter processor"""
    if not text or not isinstance(text, str):
        return ""
    
    try:
        # Remove null bytes and problematic characters
        cleaned = text.replace('\x00', '').replace('\ufffd', '')
        
        # Enhanced binary character removal
        binary_chars = ['\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07', '\x08', 
                       '\x0b', '\x0c', '\x0e', '\x0f', '\x10', '\x11', '\x12', '\x13',
                       '\x14', '\x15', '\x16', '\x17', '\x18', '\x19', '\x1a', '\x1b',
                       '\x1c', '\x1d', '\x1e', '\x1f']
        
        for char in binary_chars:
            cleaned = cleaned.replace(char, '')
        
        # Remove sequences of random symbols
        binary_pattern = r'[^\w\s.,!?;:()\[\]{}"\'-]{3,}'
        cleaned = re.sub(binary_pattern, ' ', cleaned)
        
        # Remove high Unicode values
        cleaned = ''.join(c for c in cleaned if ord(c) < 65536 and (c.isprintable() or c in '\n\r\t '))
        
        # Guy Raz specific patterns
        guy_raz_patterns = [
            r'AgH \$\+[^\s]{10,}',
            r'i\$UDzk\][^\s]{10,}',
            r'[A-Za-z0-9]{2,}[\$\+\{\}\<\>\=\"\|\,\~\`\^\&\*\#\@\!\%]{3,}[A-Za-z0-9]{2,}'
        ]
        
        for pattern in guy_raz_patterns:
            cleaned = re.sub(pattern, ' ', cleaned)
        
        # Normalize whitespace
        cleaned = ' '.join(cleaned.split())
        
        if is_binary_content(cleaned):
            return ""
        
        return cleaned.strip()
        
    except Exception as e:
        return ""

def guy_raz_specific_cleaning(text):
    """Guy Raz specific cleaning from newsletter processor"""
    if not text:
        return text
    
    try:
        import re
        # Remove non-ASCII characters
        text = re.sub(r'[^\x20-\x7E\n\r\t]+', ' ', text)
        
        # Remove Guy Raz binary contamination patterns
        guy_raz_binary_patterns = [
            'AgH $+춬B(k97la}<E"} 9ý|,47APe_ƮʗD>',
            'i$UDzk]#JB <;=\'E5 A~A|k64DC/~U"BF,56oC#',
            r'[A-Za-z0-9]{1,3}[\$\+\{\}\<\>\=\"\|\,\~\`\^\&\*\#\@\!\%]{2,}[A-Za-z0-9]{1,10}'
        ]
        
        for pattern in guy_raz_binary_patterns:
            if isinstance(pattern, str):
                text = text.replace(pattern, ' ')
            else:
                text = re.sub(pattern, ' ', text)
        
        # Final cleanup
        text = ' '.join(text.split())
        return text
        
    except Exception as e:
        return text

def write_step_result(step_name, content, step_num):
    """Write step result to file"""
    filename = f"step_{step_num}_{step_name.replace(' ', '_').lower()}.txt"
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"=== STEP {step_num}: {step_name} ===\n")
        f.write(f"Content Length: {len(content)} characters\n")
        f.write(f"Is Binary: {is_binary_content(content)}\n")
        f.write("=" * 60 + "\n\n")
        f.write(content)
    
    print(f"Step {step_num} ({step_name}): {len(content)} chars -> {filename}")
    return filename

def main():
    """Test cleaning pipeline step by step"""
    print("CONTENT CLEANING PIPELINE TEST")
    print("=" * 50)
    
    # Read original extracted content
    input_file = "extracted_content_guy_raz_substack.txt"
    
    if not os.path.exists(input_file):
        print(f"ERROR: {input_file} not found")
        return
    
    with open(input_file, 'r', encoding='utf-8') as f:
        original_content = f.read()
    
    # Extract just the content part (skip header)
    content_start = original_content.find("============================================================\n\n")
    if content_start != -1:
        content = original_content[content_start + 62:]  # Skip header
    else:
        content = original_content
    
    print(f"Original content: {len(content)} chars")
    
    # Step 1: Simulate element.get_text() (already done, this is our input)
    step1_content = content
    write_step_result("Original Content", step1_content, 1)
    
    # Step 2: clean_text_content()
    step2_content = clean_text_content(step1_content)
    write_step_result("After clean_text_content", step2_content, 2)
    
    # Step 3: is_binary_content() validation
    step3_binary = is_binary_content(step2_content)
    step3_content = step2_content if not step3_binary else ""
    write_step_result("After is_binary_content validation", step3_content, 3)
    
    # Step 4: Guy Raz specific cleaning
    step4_content = guy_raz_specific_cleaning(step3_content)
    write_step_result("After Guy Raz specific cleaning", step4_content, 4)
    
    # Summary
    print("\n" + "=" * 50)
    print("PIPELINE SUMMARY")
    print("=" * 50)
    print(f"Step 1 (Original): {len(step1_content)} chars")
    print(f"Step 2 (clean_text_content): {len(step2_content)} chars")
    print(f"Step 3 (binary validation): {len(step3_content)} chars (binary: {step3_binary})")
    print(f"Step 4 (Guy Raz cleaning): {len(step4_content)} chars")
    
    if len(step4_content) == 0:
        print("\nERROR: Content was completely removed by cleaning pipeline!")
    elif len(step4_content) < len(step1_content) * 0.5:
        print("\nWARNING: Content significantly reduced by cleaning pipeline")
    else:
        print("\nSUCCESS: Content preserved through cleaning pipeline")

if __name__ == "__main__":
    main()