"""
Script to restore the original tour_orchestrator_service.py file
"""
import os
import shutil

def restore_original_file():
    """Restore the original tour_orchestrator_service.py file"""
    try:
        # Check if backup exists
        if os.path.exists('tour_orchestrator_service.py.bak'):
            # Restore from backup
            shutil.copy('tour_orchestrator_service.py.bak', 'tour_orchestrator_service.py')
            print("Restored original file from backup")
        else:
            print("Backup file not found")
        
        return True
    except Exception as e:
        print(f"Error restoring file: {e}")
        return False

if __name__ == "__main__":
    restore_original_file()