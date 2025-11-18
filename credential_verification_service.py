#!/usr/bin/env python3
"""
Credential Verification Service - Security Fix
Verifies credentials are valid before granting access to premium content
"""

import os
import psycopg2
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

class CredentialVerificationService:
    """Service for verifying subscription credentials are actually valid"""
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'database': os.getenv('DB_NAME', 'audiotours'),
            'user': os.getenv('DB_USER', 'admin'),
            'password': os.getenv('DB_PASSWORD', 'password123'),
            'port': os.getenv('DB_PORT', '5433')
        }
    
    def get_db_connection(self):
        return psycopg2.connect(**self.db_config)
    
    def verify_credentials_for_domain(self, device_id, domain, username, password):
        """Verify credentials are actually valid by attempting authentication"""
        
        if domain == 'bostonglobe.com':
            return self._verify_boston_globe_credentials(username, password)
        elif domain == 'nytimes.com':
            return self._verify_nytimes_credentials(username, password)
        else:
            logging.warning(f"Verification not implemented for domain: {domain}")
            return {'valid': False, 'error': f'Verification not supported for {domain}'}
    
    def _verify_boston_globe_credentials(self, username, password):
        """Verify Boston Globe credentials by attempting login"""
        try:
            from boston_globe_session_auth import BostonGlobeSessionAuth
            
            auth = BostonGlobeSessionAuth()
            success = auth.authenticate_once(username, password)
            auth.close()
            
            if success:
                return {'valid': True, 'message': 'Boston Globe credentials verified'}
            else:
                return {'valid': False, 'error': 'Boston Globe authentication failed'}
                
        except Exception as e:
            logging.error(f"Boston Globe verification error: {e}")
            return {'valid': False, 'error': f'Verification failed: {str(e)}'}
    
    def _verify_nytimes_credentials(self, username, password):
        """Verify NYTimes credentials - placeholder for future implementation"""
        # TODO: Implement NYTimes authentication
        logging.warning("NYTimes credential verification not yet implemented")
        return {'valid': False, 'error': 'NYTimes verification not implemented'}
    
    def mark_credentials_verified(self, device_id, domain):
        """Mark credentials as verified in database"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE user_subscription_credentials 
                SET verified_at = NOW()
                WHERE device_id = %s AND domain = %s
            """, (device_id, domain))
            
            conn.commit()
            logging.info(f"Marked credentials as verified for {device_id} on {domain}")
            
        finally:
            cursor.close()
            conn.close()
    
    def are_credentials_verified(self, device_id, domain):
        """Check if credentials have been verified"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT verified_at FROM user_subscription_credentials 
                WHERE device_id = %s AND domain = %s
            """, (device_id, domain))
            
            result = cursor.fetchone()
            return result is not None and result[0] is not None
            
        finally:
            cursor.close()
            conn.close()

# Global instance
credential_verification_service = CredentialVerificationService()