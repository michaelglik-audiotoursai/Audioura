#!/usr/bin/env python3
"""
Legacy Tour Migration Script
Converts directory-based tours to ZIP format and cleans up old directories
"""

import os
import shutil
import zipfile
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOURS_DIR = "/app/tours"

def is_legacy_directory(path):
    """Check if directory is legacy format (has audio files)"""
    try:
        dir_path = Path(path)
        if not dir_path.is_dir():
            return False
        
        # Check for audio files (legacy format indicator)
        audio_files = list(dir_path.glob("*.mp3")) + list(dir_path.glob("audio_*.mp3"))
        
        # Legacy if has audio files (directories should be converted to ZIP)
        return len(audio_files) > 0
        
    except Exception as e:
        logger.error(f"Error checking {path}: {e}")
        return False

def create_zip_from_directory(dir_path, zip_path):
    """Create ZIP file from directory contents"""
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(dir_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Add file to ZIP with relative path
                    arcname = os.path.relpath(file_path, dir_path)
                    zipf.write(file_path, arcname)
        
        # Verify ZIP was created successfully
        if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
            logger.info(f"✅ Created ZIP: {os.path.basename(zip_path)} ({os.path.getsize(zip_path)} bytes)")
            return True
        else:
            logger.error(f"❌ Failed to create ZIP: {zip_path}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error creating ZIP {zip_path}: {e}")
        return False

def migrate_legacy_tours():
    """Main migration function"""
    tours_path = Path(TOURS_DIR)
    
    if not tours_path.exists():
        logger.error(f"Tours directory not found: {TOURS_DIR}")
        return
    
    migrated_count = 0
    skipped_count = 0
    error_count = 0
    
    logger.info("🔍 Scanning for legacy directory tours...")
    
    # Get all directories
    directories = [item for item in tours_path.iterdir() if item.is_dir()]
    logger.info(f"Found {len(directories)} directories to check")
    
    for dir_path in directories:
        dir_name = dir_path.name
        
        # Skip job directories (temporary processing)
        if dir_name.startswith('job_'):
            logger.info(f"⏭️  Skipping job directory: {dir_name}")
            skipped_count += 1
            continue
        
        # Check if it's a legacy directory
        if not is_legacy_directory(dir_path):
            logger.info(f"⏭️  Not legacy format: {dir_name}")
            skipped_count += 1
            continue
        
        # Check if ZIP already exists
        zip_name = f"{dir_name}.zip"
        zip_path = tours_path / zip_name
        
        if zip_path.exists():
            logger.info(f"⏭️  ZIP already exists: {zip_name}")
            skipped_count += 1
            continue
        
        logger.info(f"🔄 Migrating: {dir_name}")
        
        # Create ZIP from directory
        if create_zip_from_directory(dir_path, zip_path):
            # Verify ZIP integrity
            try:
                with zipfile.ZipFile(zip_path, 'r') as zipf:
                    file_count = len(zipf.namelist())
                    logger.info(f"✅ ZIP verified: {file_count} files")
                
                # Remove original directory
                shutil.rmtree(dir_path)
                logger.info(f"🗑️  Removed directory: {dir_name}")
                
                migrated_count += 1
                
            except Exception as e:
                logger.error(f"❌ ZIP verification failed for {zip_name}: {e}")
                # Remove bad ZIP
                if zip_path.exists():
                    os.remove(zip_path)
                error_count += 1
        else:
            error_count += 1
    
    # Summary
    logger.info("=" * 50)
    logger.info("🎉 MIGRATION COMPLETE")
    logger.info(f"✅ Migrated: {migrated_count} tours")
    logger.info(f"⏭️  Skipped: {skipped_count} tours")
    logger.info(f"❌ Errors: {error_count} tours")
    logger.info("=" * 50)

if __name__ == "__main__":
    migrate_legacy_tours()