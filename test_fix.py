"""
Test script to verify the text_to_index_fixed.py works correctly
"""
import os
import tempfile
import shutil

def test_text_to_index_fixed():
    """Test that text_to_index_fixed works in current directory"""
    
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"Testing in directory: {temp_dir}")
        
        # Create a simple test tour file
        test_file = os.path.join(temp_dir, "test_tour.txt")
        with open(test_file, 'w') as f:
            f.write("""Step-by-Step Audio Guided Tour: Test Tour

Stop 1: Test Exhibit

Orientation: Stand in front of the exhibit.

This is a test description for the exhibit. It contains enough text to test the processing functionality.

Stop 2: Another Test Exhibit

Orientation: Move to the second exhibit.

This is another test description to verify the system works correctly with multiple stops.
""")
        
        # Change to the temp directory
        original_cwd = os.getcwd()
        os.chdir(temp_dir)
        
        try:
            # Import and test the fixed version
            import sys
            sys.path.insert(0, original_cwd)
            from text_to_index_fixed import main as text_to_index_main
            
            print("Testing text_to_index_fixed...")
            result = text_to_index_main("test_tour.txt")
            print(f"Result: {result}")
            
            # Check if directory was created
            if os.path.exists(result):
                print(f"✓ Directory '{result}' was created successfully")
                print(f"Contents: {os.listdir(result)}")
            else:
                print(f"✗ Directory '{result}' was not created")
                
        except Exception as e:
            print(f"✗ Error: {e}")
        finally:
            os.chdir(original_cwd)

if __name__ == "__main__":
    test_text_to_index_fixed()