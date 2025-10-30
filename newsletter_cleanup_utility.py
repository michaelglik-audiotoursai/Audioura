#!/usr/bin/env python3
"""
Newsletter Cleanup Utility
Deletes a specific newsletter and all connected articles for testing purposes.
"""

import psycopg2
import sys
import argparse

class NewsletterCleanup:
    def __init__(self):
        self.conn = psycopg2.connect(
            host="localhost",
            port="5432",
            database="audiotours",
            user="admin",
            password="password"
        )
        self.cursor = self.conn.cursor()

    def find_newsletter(self, url):
        """Find newsletter by URL"""
        self.cursor.execute("SELECT id, url, type FROM newsletters WHERE url = %s", (url,))
        return self.cursor.fetchone()

    def get_linked_articles(self, newsletter_id):
        """Get all articles linked to newsletter"""
        self.cursor.execute(
            "SELECT article_requests_id FROM newsletters_article_link WHERE newsletters_id = %s",
            (newsletter_id,)
        )
        return [row[0] for row in self.cursor.fetchall()]

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

            # Delete in correct order to avoid foreign key constraints
            deleted_count = 0

            for article_id in article_ids:
                # Delete from news_audios
                self.cursor.execute("DELETE FROM news_audios WHERE article_id = %s", (article_id,))
                audio_deleted = self.cursor.rowcount
                
                # Delete from newsletters_article_link
                self.cursor.execute("DELETE FROM newsletters_article_link WHERE article_requests_id = %s", (article_id,))
                link_deleted = self.cursor.rowcount
                
                # Delete from article_requests
                self.cursor.execute("DELETE FROM article_requests WHERE article_id = %s", (article_id,))
                article_deleted = self.cursor.rowcount
                
                if article_deleted > 0:
                    deleted_count += 1
                    print(f"  ✅ Deleted article {article_id} (audio: {audio_deleted}, link: {link_deleted})")

            # Delete newsletter
            self.cursor.execute("DELETE FROM newsletters WHERE id = %s", (newsletter_id,))
            newsletter_deleted = self.cursor.rowcount

            # Commit all changes
            self.conn.commit()

            print(f"🎉 Cleanup complete:")
            print(f"   - Newsletter deleted: {newsletter_deleted}")
            print(f"   - Articles deleted: {deleted_count}")
            return True

        except Exception as e:
            self.conn.rollback()
            print(f"❌ Error during cleanup: {e}")
            return False

    def list_newsletters(self):
        """List all newsletters"""
        self.cursor.execute("SELECT id, url, type, created_at FROM newsletters ORDER BY created_at DESC LIMIT 10")
        newsletters = self.cursor.fetchall()
        
        print("📰 Recent newsletters:")
        for newsletter in newsletters:
            newsletter_id, url, newsletter_type, created_at = newsletter
            # Get article count
            self.cursor.execute("SELECT COUNT(*) FROM newsletters_article_link WHERE newsletters_id = %s", (newsletter_id,))
            article_count = self.cursor.fetchone()[0]
            print(f"  ID {newsletter_id}: {url[:60]}... ({article_count} articles, {created_at})")

    def close(self):
        """Close database connection"""
        self.cursor.close()
        self.conn.close()

def main():
    parser = argparse.ArgumentParser(description='Newsletter Cleanup Utility')
    parser.add_argument('--url', help='Newsletter URL to delete')
    parser.add_argument('--list', action='store_true', help='List recent newsletters')
    
    args = parser.parse_args()
    
    cleanup = NewsletterCleanup()
    
    try:
        if args.list:
            cleanup.list_newsletters()
        elif args.url:
            cleanup.delete_newsletter_and_articles(args.url)
        else:
            print("Usage:")
            print("  python newsletter_cleanup_utility.py --list")
            print("  python newsletter_cleanup_utility.py --url 'https://example.com/newsletter'")
    finally:
        cleanup.close()

if __name__ == "__main__":
    main()