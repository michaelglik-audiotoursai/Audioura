#!/usr/bin/env python3
"""
Real-time user tracking monitor for debugging
"""
import requests
import time
import json

USER_API_URL = 'http://192.168.0.217:5003'

def monitor_users():
    """Monitor user tracking in real-time"""
    print("User Tracking Monitor - Press Ctrl+C to stop")
    print("=" * 50)
    
    last_count = 0
    
    while True:
        try:
            response = requests.get(f"{USER_API_URL}/users", timeout=5)
            if response.status_code == 200:
                data = response.json()
                current_count = data.get('total_users', 0)
                
                if current_count != last_count:
                    print(f"\n[{time.strftime('%H:%M:%S')}] Users: {current_count}")
                    
                    # Show recent users
                    for user in data.get('users', [])[:3]:
                        print(f"  - {user['secret_id'][:16]}... Tours: {user['tours_count']}")
                    
                    last_count = current_count
                else:
                    print(".", end="", flush=True)
            else:
                print(f"\nError: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            print(f"\n[{time.strftime('%H:%M:%S')}] Cannot connect to user service")
        except KeyboardInterrupt:
            print("\nMonitoring stopped")
            break
        except Exception as e:
            print(f"\nError: {e}")
            
        time.sleep(2)

if __name__ == "__main__":
    monitor_users()