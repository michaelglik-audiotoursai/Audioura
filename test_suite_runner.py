#!/usr/bin/env python3
"""
Comprehensive Newsletter Processing Test Suite
Runs all technology tests in sequence with proper cleanup
"""
import os
import sys
import subprocess
import json
from datetime import datetime

def run_test(test_name, test_script):
    """Run a single test and capture results"""
    print(f"\n{'='*60}")
    print(f"RUNNING TEST: {test_name}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run([sys.executable, test_script], 
                              capture_output=True, text=True, cwd=os.getcwd())
        
        return {
            'test_name': test_name,
            'script': test_script,
            'exit_code': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'success': result.returncode == 0,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {
            'test_name': test_name,
            'script': test_script,
            'exit_code': -1,
            'stdout': '',
            'stderr': str(e),
            'success': False,
            'timestamp': datetime.now().isoformat()
        }

def main():
    """Run all newsletter processing tests"""
    print("NEWSLETTER PROCESSING TEST SUITE")
    print("=" * 60)
    print(f"Started at: {datetime.now()}")
    
    # Define test suite
    tests = [
        ("Spotify Processing", "test_spotify_processing.py"),
        ("Apple Podcasts Processing", "test_apple_processing.py"),
        # Add more tests here as needed
    ]
    
    results = []
    
    # Run each test
    for test_name, test_script in tests:
        if not os.path.exists(test_script):
            print(f"WARNING: Test script {test_script} not found, skipping...")
            continue
            
        result = run_test(test_name, test_script)
        results.append(result)
        
        # Print summary
        status = "PASSED" if result['success'] else "FAILED"
        print(f"\nTEST RESULT: {test_name} - {status}")
        if not result['success']:
            print(f"Error: {result['stderr'][:200]}...")
    
    # Generate summary report
    print(f"\n{'='*60}")
    print("TEST SUITE SUMMARY")
    print(f"{'='*60}")
    
    passed = sum(1 for r in results if r['success'])
    total = len(results)
    
    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success Rate: {(passed/total*100):.1f}%" if total > 0 else "N/A")
    
    # Save detailed results
    report_file = f"test_suite_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump({
            'summary': {
                'total_tests': total,
                'passed': passed,
                'failed': total - passed,
                'success_rate': (passed/total*100) if total > 0 else 0,
                'timestamp': datetime.now().isoformat()
            },
            'results': results
        }, f, indent=2)
    
    print(f"\nDetailed report saved to: {report_file}")
    
    # List debug files created
    debug_files = [f for f in os.listdir('.') if f.startswith('debug_')]
    if debug_files:
        print(f"\nDebug files created:")
        for file in debug_files:
            print(f"  - {file}")
    
    return total - passed  # Return number of failures for exit code

if __name__ == "__main__":
    failures = main()
    sys.exit(failures)