#!/usr/bin/env python3
"""
Newsletter Cleanup Utility - Docker Version
Deletes a specific newsletter and all connected articles for testing purposes.
Uses docker exec to run SQL commands.
"""

import subprocess
import sys
import argparse
import json

class NewsletterCleanupDocker:
    def __init__(self):
        self.container = "development-postgres-2-1"
        self.db_user = "admin"
        self.db_name = "audiotours"

    def execute_sql(self, sql, params=None):
        """Execute SQL command via docker exec"""
        if params:
            # Simple parameter substitution for basic queries
            sql = sql.replace('%s', f"'{params[0]}'") if len(params) == 1 else sql
        
        cmd = [
            "docker", "exec", self.container,
            "psql", "-U", self.db_user, "-d", self.db_name,
            "-c", sql
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout, result.stderr, result.returncode

    def find_newsletter(self, url):
        """Find newsletter by URL"""
        sql = f"SELECT id, url, type FROM newsletters WHERE url = '{url}';"
        stdout, stderr, code = self.execute_sql(sql)
        
        if code != 0:
            print(f"❌ Error finding newsletter: {stderr}")
            return None
            
        lines = stdout.strip().split('\n')
        if len(lines) < 3 or '(0 rows)' in stdout:
            return None
            
        # Parse the data line (skip header and separator)
        data_line = lines[2].strip()
        if '|' in data_line:
            parts = [p.strip() for p in data_line.split('|')]
            return (int(parts[0]), parts[1], parts[2])
        return None

    def get_linked_articles(self, newsletter_id):
        """Get all articles linked to newsletter"""
        sql = f"SELECT article_requests_id FROM newsletters_article_link WHERE newsletters_id = {newsletter_id};"
        stdout, stderr, code = self.execute_sql(sql)
        
        if code != 0:
            return []
            
        article_ids = []
        lines = stdout.strip().split('\n')
        for line in lines[2:]:  # Skip header and separator
            line = line.strip()
            if line and '(' not in line and '-' not in line:
                article_ids.append(line)
        return article_ids

    def delete_newsletter_and_articles(self, url):
        """Delete newsletter and all connected articles"""
        try:
            # Find newsletter
            newsletter = self.find_newsletter(url)
            if not newsletter:
                print(f"❌ Newsletter not found: {url}")
                return False

            newsletter_id, newsletter_url, newsletter_type = newsletter
            print(f"📰 Found newsletter: ID {newsletter_id}, Type: {newsletter_type}")

            # Get linked articles
            article_ids = self.get_linked_articles(newsletter_id)
            print(f"📄 Found {len(article_ids)} linked articles")

            # Delete articles one by one
            deleted_count = 0
            for article_id in article_ids:
                # Delete from news_audios
                sql = f"DELETE FROM news_audios WHERE article_id = '{article_id}';"
                self.execute_sql(sql)
                
                # Delete from newsletters_article_link
                sql = f"DELETE FROM newsletters_article_link WHERE article_requests_id = '{article_id}';"
                self.execute_sql(sql)
                
                # Delete from article_requests
                sql = f"DELETE FROM article_requests WHERE article_id = '{article_id}';"
                stdout, stderr, code = self.execute_sql(sql)
                
                if code == 0 and 'DELETE 1' in stdout:
                    deleted_count += 1
                    print(f"  ✅ Deleted article {article_id}")

            # Delete newsletter
            sql = f"DELETE FROM newsletters WHERE id = {newsletter_id};"
            stdout, stderr, code = self.execute_sql(sql)
            
            newsletter_deleted = 1 if 'DELETE 1' in stdout else 0

            print(f"🎉 Cleanup complete:")
            print(f"   - Newsletter deleted: {newsletter_deleted}")
            print(f"   - Articles deleted: {deleted_count}")
            return True

        except Exception as e:
            print(f"❌ Error during cleanup: {e}")
            return False

    def list_newsletters(self):
        """List all newsletters"""
        sql = "SELECT id, url, type, created_at FROM newsletters ORDER BY created_at DESC LIMIT 10;"
        stdout, stderr, code = self.execute_sql(sql)
        
        if code != 0:
            print(f"❌ Error listing newsletters: {stderr}")
            return
            
        print("📰 Recent newsletters:")
        lines = stdout.strip().split('\n')
        for line in lines[2:]:  # Skip header and separator
            line = line.strip()
            if line and '(' not in line and '-' not in line:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4:
                    newsletter_id = parts[0]
                    url = parts[1][:60] + "..." if len(parts[1]) > 60 else parts[1]
                    
                    # Get article count
                    count_sql = f"SELECT COUNT(*) FROM newsletters_article_link WHERE newsletters_id = {newsletter_id};"
                    count_stdout, _, count_code = self.execute_sql(count_sql)
                    article_count = "0"
                    if count_code == 0:
                        count_lines = count_stdout.strip().split('\n')
                        if len(count_lines) >= 3:
                            article_count = count_lines[2].strip()
                    
                    print(f"  ID {newsletter_id}: {url} ({article_count} articles)")

def main():
    parser = argparse.ArgumentParser(description='Newsletter Cleanup Utility (Docker)')
    parser.add_argument('--url', help='Newsletter URL to delete')
    parser.add_argument('--list', action='store_true', help='List recent newsletters')
    
    args = parser.parse_args()
    
    cleanup = NewsletterCleanupDocker()
    
    if args.list:
        cleanup.list_newsletters()
    elif args.url:
        cleanup.delete_newsletter_and_articles(args.url)
    else:
        print("Usage:")
        print("  python newsletter_cleanup_docker.py --list")
        print("  python newsletter_cleanup_docker.py --url 'https://example.com/newsletter'")

if __name__ == "__main__":
    main()