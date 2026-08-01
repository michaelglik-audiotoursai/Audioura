#!/usr/bin/env python3
"""
ZIP File Quality Verification Test
Verifies audio package completeness and quality
"""
import zipfile
import os
import json
from datetime import datetime

def analyze_zip_file(zip_path):
    """Analyze ZIP file contents and quality"""
    print(f"=== ANALYZING: {zip_path} ===")
    
    if not os.path.exists(zip_path):
        print(f"ERROR: ZIP file not found: {zip_path}")
        return None
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            files = zip_ref.namelist()
            
            # Basic file analysis
            total_files = len(files)
            total_size = sum(zip_ref.getinfo(f).file_size for f in files)
            
            print(f"  Total files: {total_files}")
            print(f"  Total size: {total_size:,} bytes ({total_size/1024/1024:.1f} MB)")
            
            # Categorize files
            audio_files = [f for f in files if f.endswith('.mp3')]
            html_files = [f for f in files if f.endswith('.html')]
            text_files = [f for f in files if f.endswith('.txt')]
            
            print(f"  Audio files: {len(audio_files)}")
            print(f"  HTML files: {len(html_files)}")
            print(f"  Text files: {len(text_files)}")
            
            # Required files check
            required_files = ['index.html', 'audio-1.mp3', 'audio-99.mp3', 'audio-help.mp3']
            missing_required = [f for f in required_files if f not in files]
            
            if missing_required:
                print(f"  WARNING: Missing required files: {missing_required}")
            else:
                print(f"  SUCCESS: All required files present")
            
            # Audio file analysis
            print(f"\\n  Audio File Details:")
            for audio_file in sorted(audio_files):
                size = zip_ref.getinfo(audio_file).file_size
                duration_est = size / 16000  # Rough estimate: 16KB per second
                print(f"    {audio_file}: {size:,} bytes (~{duration_est:.1f}s)")
            
            # Check search content
            search_files = [f for f in files if 'search_content' in f]
            if search_files:
                search_file = search_files[0]
                search_content = zip_ref.read(search_file).decode('utf-8')
                search_length = len(search_content)
                print(f"\\n  Search Content: {search_length} chars")
                
                # Check for HTML entities (should be cleaned)
                html_entities = ['&nbsp;', '&amp;', '&mdash;', '&copy;', '&trade;']
                found_entities = [entity for entity in html_entities if entity in search_content]
                
                if found_entities:
                    print(f"    WARNING: HTML entities found: {found_entities}")
                else:
                    print(f"    SUCCESS: No HTML entities (clean text)")
                
                # Check for underscores (should be cleaned for audio)
                underscore_count = search_content.count('_')
                if underscore_count > 5:  # Allow some underscores in URLs, etc.
                    print(f"    WARNING: Many underscores found: {underscore_count}")
                else:
                    print(f"    SUCCESS: Minimal underscores ({underscore_count})")
            
            # HTML player analysis
            if 'index.html' in files:
                html_content = zip_ref.read('index.html').decode('utf-8')
                
                # Check for voice control features
                voice_features = ['voice control', 'speech recognition', 'audio1', 'audio2']
                found_features = [f for f in voice_features if f.lower() in html_content.lower()]
                print(f"\\n  Voice Control Features: {len(found_features)}/4")
                
                # Check for proper audio IDs
                audio_ids = [f'audio-{i}' for i in range(1, 10)]
                found_ids = [aid for aid in audio_ids if aid in html_content]
                print(f"  Audio IDs found: {len(found_ids)}")
            
            return {
                'zip_path': zip_path,
                'total_files': total_files,
                'total_size': total_size,
                'audio_files': len(audio_files),
                'html_files': len(html_files),
                'text_files': len(text_files),
                'missing_required': missing_required,
                'search_content_length': search_length if search_files else 0,
                'html_entities_found': found_entities if search_files else [],
                'underscore_count': underscore_count if search_files else 0,
                'voice_features': len(found_features) if 'index.html' in files else 0,
                'audio_ids_found': len(found_ids) if 'index.html' in files else 0
            }
            
    except Exception as e:
        print(f"ERROR: Failed to analyze ZIP: {e}")
        return None

def main():
    """Test multiple ZIP files for quality"""
    print("ZIP FILE QUALITY VERIFICATION")
    print("=" * 60)
    print(f"Started at: {datetime.now()}")
    
    # Test files to analyze
    test_files = [
        "recent_test.zip",
        "apple_test_latest.zip", 
        "apple_test_second.zip"
    ]
    
    results = []
    
    for zip_file in test_files:
        if os.path.exists(zip_file):
            result = analyze_zip_file(zip_file)
            if result:
                results.append(result)
        else:
            print(f"\\nSKIPPED: {zip_file} (not found)")
    
    # Generate summary
    if results:
        print(f"\\n{'='*60}")
        print("QUALITY SUMMARY")
        print(f"{'='*60}")
        
        avg_size = sum(r['total_size'] for r in results) / len(results)
        avg_audio_files = sum(r['audio_files'] for r in results) / len(results)
        
        print(f"Files analyzed: {len(results)}")
        print(f"Average size: {avg_size:,.0f} bytes ({avg_size/1024/1024:.1f} MB)")
        print(f"Average audio files: {avg_audio_files:.1f}")
        
        # Quality checks
        complete_packages = sum(1 for r in results if not r['missing_required'])
        clean_text = sum(1 for r in results if not r['html_entities_found'])
        voice_ready = sum(1 for r in results if r['voice_features'] >= 2)
        
        print(f"\\nQuality Metrics:")
        print(f"  Complete packages: {complete_packages}/{len(results)}")
        print(f"  Clean text (no HTML entities): {clean_text}/{len(results)}")
        print(f"  Voice control ready: {voice_ready}/{len(results)}")
        
        # Overall quality score
        quality_score = (complete_packages + clean_text + voice_ready) / (len(results) * 3)
        print(f"\\nOverall Quality Score: {quality_score*100:.1f}%")
        
        if quality_score >= 0.9:
            print("Status: EXCELLENT - Production ready audio packages")
        elif quality_score >= 0.7:
            print("Status: GOOD - Minor improvements possible")
        else:
            print("Status: NEEDS WORK - Quality issues detected")
        
        # Save detailed results
        report_file = f"zip_quality_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'summary': {
                    'files_analyzed': len(results),
                    'average_size_bytes': avg_size,
                    'average_audio_files': avg_audio_files,
                    'complete_packages': complete_packages,
                    'clean_text': clean_text,
                    'voice_ready': voice_ready,
                    'quality_score': quality_score
                },
                'detailed_results': results
            }, f, indent=2)
        
        print(f"\\nDetailed report saved to: {report_file}")
        
        return 0 if quality_score >= 0.7 else 1
    else:
        print("\\nERROR: No ZIP files found to analyze")
        return 1

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)