#!/usr/bin/env python3
"""
Simple Newsletter Cleanup Utility
Deletes a specific newsletter and all connected articles for testing purposes.
"""

import subprocess
import sys
import argparse

def execute_sql(sql):
    """Execute SQL command via docker exec"""
    cmd = [
        "docker", "exec", "development-postgres-2-1",
        "psql", "-U", "admin", "-d", "audiotours",
        "-c", sql
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout, result.stderr, result.returncode

def cleanup_newsletter(url):
    """Delete newsletter and all connected articles"""
    print(f"Cleaning up newsletter: {url}")
    
    # Find newsletter ID
    sql = f"SELECT id FROM newsletters WHERE url = '{url}';"
    stdout, stderr, code = execute_sql(sql)
    
    if code != 0 or '(0 rows)' in stdout:
        print("ERROR: Newsletter not found")
        return False
    
    # Extract newsletter ID from output
    lines = stdout.strip().split('\n')
    newsletter_id = None
    for line in lines:
        line = line.strip()
        if line.isdigit():
            newsletter_id = line
            break
    
    if not newsletter_id:
        print("ERROR: Could not extract newsletter ID")
        return False
    
    print(f"Found newsletter ID: {newsletter_id}")
    
    # Get linked articles
    sql = f"SELECT article_requests_id FROM newsletters_article_link WHERE newsletters_id = {newsletter_id};"
    stdout, stderr, code = execute_sql(sql)
    
    article_ids = []
    if code == 0:
        lines = stdout.strip().split('\n')
        for line in lines:
            line = line.strip()
            if len(line) == 36 and '-' in line:  # UUID format
                article_ids.append(line)
    
    print(f"Found {len(article_ids)} linked articles")
    
    # Delete articles
    deleted_count = 0
    for article_id in article_ids:
        # Delete from news_audios
        sql = f"DELETE FROM news_audios WHERE article_id = '{article_id}';"
        execute_sql(sql)
        
        # Delete from newsletters_article_link
        sql = f"DELETE FROM newsletters_article_link WHERE article_requests_id = '{article_id}';"
        execute_sql(sql)
        
        # Delete from article_requests
        sql = f"DELETE FROM article_requests WHERE article_id = '{article_id}';"
        stdout, stderr, code = execute_sql(sql)
        
        if code == 0 and 'DELETE 1' in stdout:
            deleted_count += 1
            print(f"  Deleted article {article_id}")
    
    # Delete newsletter
    sql = f"DELETE FROM newsletters WHERE id = {newsletter_id};"
    stdout, stderr, code = execute_sql(sql)
    
    newsletter_deleted = 1 if 'DELETE 1' in stdout else 0
    
    print(f"Cleanup complete: Newsletter deleted: {newsletter_deleted}, Articles deleted: {deleted_count}")
    return True

def list_newsletters():
    """List recent newsletters"""
    sql = "SELECT id, LEFT(url, 60) as url_preview, type FROM newsletters ORDER BY created_at DESC LIMIT 10;"
    stdout, stderr, code = execute_sql(sql)
    
    if code != 0:
        print(f"ERROR: {stderr}")
        return
    
    print("Recent newsletters:")
    print(stdout)

def main():
    parser = argparse.ArgumentParser(description='Newsletter Cleanup Utility')
    parser.add_argument('--url', help='Newsletter URL to delete')
    parser.add_argument('--list', action='store_true', help='List recent newsletters')
    
    args = parser.parse_args()
    
    if args.list:
        list_newsletters()
    elif args.url:
        cleanup_newsletter(args.url)
    else:
        print("Usage:")
        print("  python cleanup_newsletter_simple.py --list")
        print("  python cleanup_newsletter_simple.py --url 'https://example.com/newsletter'")

if __name__ == "__main__":
    main()