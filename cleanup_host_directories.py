#!/usr/bin/env python3
"""
Host-based Legacy Directory Cleanup Script
Removes directory-based tours that have corresponding ZIP files from host system
"""

import os
import shutil
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOURS_DIR = r"c:\Users\micha\eclipse-workspace\AudioTours\development\tours"

def has_corresponding_zip(dir_path):
    """Check if directory has a corresponding ZIP file"""
    try:
        dir_name = dir_path.name
        zip_name = f"{dir_name}.zip"
        zip_path = dir_path.parent / zip_name
        
        return zip_path.exists() and zip_path.is_file()
        
    except Exception as e:
        logger.error(f"Error checking ZIP for {dir_path}: {e}")
        return False

def has_audio_files(dir_path):
    """Check if directory contains audio files"""
    try:
        if not dir_path.is_dir():
            return False
        
        audio_files = list(dir_path.glob("*.mp3")) + list(dir_path.glob("audio_*.mp3"))
        return len(audio_files) > 0
        
    except Exception as e:
        logger.error(f"Error checking audio files in {dir_path}: {e}")
        return False

def get_directory_size(dir_path):
    """Calculate directory size in bytes"""
    try:
        total_size = 0
        for root, dirs, files in os.walk(dir_path):
            for file in files:
                file_path = os.path.join(root, file)
                if os.path.exists(file_path):
                    total_size += os.path.getsize(file_path)
        return total_size
    except Exception as e:
        logger.error(f"Error calculating size for {dir_path}: {e}")
        return 0

def cleanup_legacy_directories():
    """Main cleanup function"""
    tours_path = Path(TOURS_DIR)
    
    if not tours_path.exists():
        logger.error(f"Tours directory not found: {TOURS_DIR}")
        return
    
    deleted_count = 0
    skipped_count = 0
    error_count = 0
    total_space_saved = 0
    
    logger.info("🔍 Scanning for legacy directories to cleanup...")
    
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
        
        # Check if it has audio files (legacy format)
        if not has_audio_files(dir_path):
            logger.info(f"⏭️  No audio files: {dir_name}")
            skipped_count += 1
            continue
        
        # Check if corresponding ZIP exists
        if not has_corresponding_zip(dir_path):
            logger.info(f"⏭️  No corresponding ZIP: {dir_name}")
            skipped_count += 1
            continue
        
        # Calculate space savings
        dir_size = get_directory_size(dir_path)
        
        logger.info(f"🗑️  Deleting: {dir_name} ({dir_size:,} bytes)")
        
        try:
            # Remove directory
            shutil.rmtree(dir_path)
            logger.info(f"✅ Deleted: {dir_name}")
            
            deleted_count += 1
            total_space_saved += dir_size
            
        except Exception as e:
            logger.error(f"❌ Error deleting {dir_name}: {e}")
            error_count += 1
    
    # Summary
    logger.info("=" * 50)
    logger.info("🎉 CLEANUP COMPLETE")
    logger.info(f"🗑️  Deleted: {deleted_count} directories")
    logger.info(f"⏭️  Skipped: {skipped_count} directories")
    logger.info(f"❌ Errors: {error_count} directories")
    logger.info(f"💾 Space saved: {total_space_saved:,} bytes ({total_space_saved/1024/1024:.1f} MB)")
    logger.info("=" * 50)

if __name__ == "__main__":
    cleanup_legacy_directories()