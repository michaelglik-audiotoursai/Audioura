#!/usr/bin/env python3
"""
User Consolidation Service - Phase 3 Implementation
Handles intelligent device merging based on credential matching

LOCAL-321: Removed all reads of decrypted_username / decrypted_password.
  - get_user_credentials_by_device: uses credential_store (encrypted columns only)
  - find_matching_credentials: uses credential_blind_index (HMAC comparison)
    instead of plaintext SQL WHERE clause equality.

When encryption is not yet provisioned (no wrapped_dek in rows), both methods
return empty results — consolidation degrades gracefully to "new_user" for
every submission. This is safe: the table currently has 0 rows, and the
credential endpoints are disabled.
"""

import os
import hmac
import hashlib
import psycopg2
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')


def _compute_credential_blind_index(domain: str, username: str, password: str) -> bytes:
    """Compute a blind index (keyed HMAC-SHA256) over domain+username+password.

    The blind index allows equality matching on credentials without storing
    them in plaintext. The HMAC key must be held outside the database (env var).
    If the key is absent, returns None — matching is unavailable.

    The index is NOT reversible: holding the database alone (including this
    column) does not reveal the credential. An attacker would also need
    CREDENTIAL_BLIND_INDEX_KEY from the environment.
    """
    key = os.environ.get('CREDENTIAL_BLIND_INDEX_KEY')
    if not key:
        return None

    # Canonical input: domain || NUL || username || NUL || password
    # NUL separator prevents domain+user ambiguity (e.g., "a.com\0user" vs "a.co\0muser")
    message = f"{domain}\x00{username}\x00{password}".encode('utf-8')
    return hmac.new(key.encode('utf-8'), message, hashlib.sha256).digest()


class UserConsolidationService:
    """Service for managing user consolidation and device merging"""
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'database': os.getenv('DB_NAME', 'audiotours'),
            'user': os.getenv('DB_USER', 'admin'),
            'password': os.getenv('DB_PASSWORD', 'password123'),
            'port': os.getenv('DB_PORT', '5433')
        }
    
    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(**self.db_config)
    
    def get_user_credentials_by_device(self, device_id: str) -> List[Dict]:
        """Get all credentials for a device.

        LOCAL-321: Reads ONLY via credential_store (encrypted columns).
        Returns empty list if no encrypted credentials exist.
        Never reads decrypted_username or decrypted_password.
        """
        from credential_store import get_credentials_for_device
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Get domains and consolidation metadata (non-secret columns only)
            cursor.execute("""
                SELECT domain, consolidated_user_id
                FROM user_subscription_credentials 
                WHERE device_id = %s AND wrapped_dek IS NOT NULL
                ORDER BY domain
            """, (device_id,))
            
            credentials = []
            for row in cursor.fetchall():
                domain = row[0]
                consolidated_user_id = row[1]
                # Decrypt credentials via credential_store (KMS envelope)
                cred = get_credentials_for_device(device_id, domain)
                if cred:
                    credentials.append({
                        'domain': domain,
                        'username': cred['username'],
                        'password': cred['password'],
                        'consolidated_user_id': consolidated_user_id
                    })
            
            return credentials
            
        finally:
            cursor.close()
            conn.close()
    
    def find_matching_credentials(self, domain: str, username: str, password: str) -> List[str]:
        """Find devices with matching credentials for a domain.

        LOCAL-321: Uses blind index (HMAC) comparison instead of plaintext
        SQL WHERE clause. Requires:
          1. CREDENTIAL_BLIND_INDEX_KEY env var set
          2. credential_blind_index column populated on target rows

        If either prerequisite is unmet, returns [] (no matches). This is
        safe: consolidation degrades to "new_user" for every submission.

        Design note (why not plaintext equality):
          Comparing secrets in a SQL WHERE clause puts them in query
          parameters, statement logs, and pg_stat_statements. It also
          uses non-constant-time comparison. A blind index avoids all of
          these: the HMAC is not reversible, and the secret never appears
          in the query.
        """
        blind_index = _compute_credential_blind_index(domain, username, password)
        if blind_index is None:
            logging.info("[CONSOLIDATION] Blind index key not configured — "
                         "credential matching unavailable")
            return []

        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT device_id FROM user_subscription_credentials 
                WHERE domain = %s AND credential_blind_index = %s
            """, (domain, blind_index))
            
            return [row[0] for row in cursor.fetchall()]
            
        finally:
            cursor.close()
            conn.close()
    
    def has_cross_domain_conflicts(self, device1: str, device2: str) -> Tuple[bool, List[str]]:
        """Check if two devices have conflicting credentials in any domain"""
        device1_creds = self.get_user_credentials_by_device(device1)
        device2_creds = self.get_user_credentials_by_device(device2)
        
        # Create domain maps
        device1_domains = {cred['domain']: (cred['username'], cred['password']) for cred in device1_creds}
        device2_domains = {cred['domain']: (cred['username'], cred['password']) for cred in device2_creds}
        
        # Find common domains
        common_domains = set(device1_domains.keys()) & set(device2_domains.keys())
        conflicts = []
        
        for domain in common_domains:
            if device1_domains[domain] != device2_domains[domain]:
                conflicts.append(domain)
                logging.info(f"Credential conflict in domain {domain}: {device1} vs {device2}")
        
        return len(conflicts) > 0, conflicts
    
    def get_or_create_consolidated_user_id(self, primary_device_id: str) -> str:
        """Get existing consolidated user ID or create new one"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Check if device already has consolidated user ID
            cursor.execute("""
                SELECT consolidated_user_id FROM user_subscription_credentials 
                WHERE device_id = %s AND consolidated_user_id IS NOT NULL
                LIMIT 1
            """, (primary_device_id,))
            
            existing = cursor.fetchone()
            if existing:
                return existing[0]
            
            # Create new consolidated user ID
            consolidated_user_id = f"CONSOLIDATED-{primary_device_id}-{int(datetime.now().timestamp())}"
            
            # Create consolidation map entry
            cursor.execute("""
                INSERT INTO user_consolidation_map (consolidated_user_id, primary_device_id)
                VALUES (%s, %s)
                ON CONFLICT (consolidated_user_id) DO NOTHING
            """, (consolidated_user_id, primary_device_id))
            
            # Update all credentials for primary device
            cursor.execute("""
                UPDATE user_subscription_credentials 
                SET consolidated_user_id = %s 
                WHERE device_id = %s
            """, (consolidated_user_id, primary_device_id))
            
            conn.commit()
            logging.info(f"Created consolidated user ID: {consolidated_user_id} for device {primary_device_id}")
            
            return consolidated_user_id
            
        finally:
            cursor.close()
            conn.close()
    
    def merge_devices_under_user(self, primary_device_id: str, secondary_device_id: str, 
                                trigger_domain: str) -> Dict:
        """Merge secondary device under primary device's consolidated user"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Get or create consolidated user ID
            consolidated_user_id = self.get_or_create_consolidated_user_id(primary_device_id)
            
            # Update all credentials for secondary device
            cursor.execute("""
                UPDATE user_subscription_credentials 
                SET consolidated_user_id = %s 
                WHERE device_id = %s
            """, (consolidated_user_id, secondary_device_id))
            
            # Record consolidation history
            cursor.execute("""
                INSERT INTO device_consolidation_history 
                (consolidated_user_id, merged_device_id, domain, merged_at)
                VALUES (%s, %s, %s, NOW())
            """, (consolidated_user_id, secondary_device_id, trigger_domain))
            
            # Update consolidation map timestamp
            cursor.execute("""
                UPDATE user_consolidation_map 
                SET last_merged_at = NOW() 
                WHERE consolidated_user_id = %s
            """, (consolidated_user_id,))
            
            conn.commit()
            
            # Get synced domains
            cursor.execute("""
                SELECT DISTINCT domain FROM user_subscription_credentials 
                WHERE consolidated_user_id = %s
            """, (consolidated_user_id,))
            
            synced_domains = [row[0] for row in cursor.fetchall()]
            
            logging.info(f"Successfully merged device {secondary_device_id} under {consolidated_user_id}")
            
            return {
                "status": "merged",
                "consolidated_user_id": consolidated_user_id,
                "primary_device": primary_device_id,
                "merged_device": secondary_device_id,
                "trigger_domain": trigger_domain,
                "synced_domains": synced_domains,
                "available_subscriptions": len(synced_domains)
            }
            
        finally:
            cursor.close()
            conn.close()
    
    def handle_credential_submission_with_consolidation(self, device_id: str, domain: str, 
                                                       username: str, password: str) -> Dict:
        """Handle credential submission with intelligent user consolidation"""
        logging.info(f"Processing credential submission for device {device_id}, domain {domain}")
        
        # Step 1: Find existing credentials for this domain
        matching_devices = self.find_matching_credentials(domain, username, password)
        
        # Remove current device from matches (if it exists)
        matching_devices = [d for d in matching_devices if d != device_id]
        
        if not matching_devices:
            # No matching credentials found - store as new user
            logging.info(f"No matching credentials found for {domain} - storing as new user")
            return {
                "action": "new_user",
                "message": f"Credentials stored for new user on {domain}",
                "device_id": device_id,
                "domain": domain
            }
        
        # Step 2: Check each matching device for cross-domain conflicts
        for existing_device in matching_devices:
            has_conflicts, conflict_domains = self.has_cross_domain_conflicts(existing_device, device_id)
            
            if not has_conflicts:
                # No conflicts - merge devices
                logging.info(f"No conflicts found - merging {device_id} with {existing_device}")
                return self.merge_devices_under_user(existing_device, device_id, domain)
            else:
                logging.info(f"Conflicts found in domains {conflict_domains} - keeping devices separate")
        
        # Step 3: All matching devices have conflicts - keep separate
        return {
            "action": "separate",
            "message": f"Credentials stored separately due to conflicts in other domains",
            "device_id": device_id,
            "domain": domain,
            "conflicting_devices": matching_devices,
            "reason": "cross_domain_conflicts"
        }
    
    def get_consolidated_user_status(self, device_id: str) -> Dict:
        """Get consolidation status for a device"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Get device credentials and consolidation info
            cursor.execute("""
                SELECT usc.domain, usc.consolidated_user_id, ucm.primary_device_id
                FROM user_subscription_credentials usc
                LEFT JOIN user_consolidation_map ucm ON usc.consolidated_user_id = ucm.consolidated_user_id
                WHERE usc.device_id = %s
                ORDER BY usc.domain
            """, (device_id,))
            
            credentials = cursor.fetchall()
            
            if not credentials:
                return {
                    "status": "no_credentials",
                    "device_id": device_id,
                    "consolidated": False
                }
            
            consolidated_user_id = credentials[0][1] if credentials[0][1] else None
            primary_device_id = credentials[0][2] if credentials[0][2] else None
            
            domains = [row[0] for row in credentials]
            
            if consolidated_user_id:
                # Get all devices in this consolidated user
                cursor.execute("""
                    SELECT DISTINCT device_id FROM user_subscription_credentials 
                    WHERE consolidated_user_id = %s
                """, (consolidated_user_id,))
                
                all_devices = [row[0] for row in cursor.fetchall()]
                
                # Get consolidation history
                cursor.execute("""
                    SELECT merged_device_id, domain, merged_at 
                    FROM device_consolidation_history 
                    WHERE consolidated_user_id = %s
                    ORDER BY merged_at DESC
                """, (consolidated_user_id,))
                
                merge_history = [
                    {
                        "device_id": row[0],
                        "domain": row[1],
                        "merged_at": row[2].isoformat()
                    }
                    for row in cursor.fetchall()
                ]
                
                return {
                    "status": "consolidated",
                    "device_id": device_id,
                    "consolidated": True,
                    "consolidated_user_id": consolidated_user_id,
                    "primary_device_id": primary_device_id,
                    "is_primary": device_id == primary_device_id,
                    "all_devices": all_devices,
                    "domains": domains,
                    "available_subscriptions": len(domains),
                    "merge_history": merge_history
                }
            else:
                return {
                    "status": "individual",
                    "device_id": device_id,
                    "consolidated": False,
                    "domains": domains,
                    "available_subscriptions": len(domains)
                }
                
        finally:
            cursor.close()
            conn.close()

# Global instance
user_consolidation_service = UserConsolidationService()