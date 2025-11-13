#!/usr/bin/env python3
"""
Analyze large modules and suggest function extraction for testing
"""

import os
import ast
import re

def analyze_file(filepath):
    """Analyze Python file for functions and complexity"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        tree = ast.parse(content)
        
        functions = []
        classes = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Calculate function complexity
                lines = node.end_lineno - node.lineno if hasattr(node, 'end_lineno') else 0
                functions.append({
                    'name': node.name,
                    'lines': lines,
                    'args': len(node.args.args),
                    'testable': lines < 50 and not node.name.startswith('_')
                })
            elif isinstance(node, ast.ClassDef):
                classes.append({
                    'name': node.name,
                    'lines': node.end_lineno - node.lineno if hasattr(node, 'end_lineno') else 0
                })
        
        return {
            'file': os.path.basename(filepath),
            'total_lines': len(content.splitlines()),
            'functions': functions,
            'classes': classes
        }
    except Exception as e:
        return {'file': os.path.basename(filepath), 'error': str(e)}

def suggest_modularization(analysis):
    """Suggest how to break down large modules"""
    suggestions = []
    
    if analysis['total_lines'] > 300:
        # Find testable functions
        testable_funcs = [f for f in analysis.get('functions', []) if f['testable']]
        large_funcs = [f for f in analysis.get('functions', []) if f['lines'] > 30]
        
        if testable_funcs:
            suggestions.append(f"Extract {len(testable_funcs)} testable functions to utils module")
        
        if large_funcs:
            suggestions.append(f"Break down {len(large_funcs)} large functions (>30 lines)")
            
        # Suggest module splits
        if 'service' in analysis['file'].lower():
            suggestions.append("Split into: core_logic.py + api_handlers.py + utils.py")
        elif 'processor' in analysis['file'].lower():
            suggestions.append("Split into: content_extraction.py + validation.py + processing.py")
    
    return suggestions

def main():
    """Analyze all Python files in development directory"""
    dev_dir = "."
    large_modules = []
    
    for file in os.listdir(dev_dir):
        if file.endswith('.py') and not file.startswith('test_'):
            filepath = os.path.join(dev_dir, file)
            analysis = analyze_file(filepath)
            
            if 'error' not in analysis and analysis['total_lines'] > 300:
                large_modules.append(analysis)
    
    print("=== LARGE MODULES ANALYSIS ===")
    for module in sorted(large_modules, key=lambda x: x['total_lines'], reverse=True):
        print(f"\nFILE: {module['file']} ({module['total_lines']} lines)")
        
        testable = [f for f in module.get('functions', []) if f['testable']]
        if testable:
            print(f"  TESTABLE: {', '.join([f['name'] for f in testable[:5]])}")
        
        suggestions = suggest_modularization(module)
        for suggestion in suggestions:
            print(f"  SUGGEST: {suggestion}")

if __name__ == "__main__":
    main()