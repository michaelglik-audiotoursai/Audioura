#!/usr/bin/env python3
"""
Check specific user tracking data
"""
import requests
import json

USER_API_URL = 'http://192.168.0.217:5003'
USER_ID = 'txzs7duahw03g810'

def check_user_data():
    print(f"Checking user: {USER_ID}")
    print("=" * 40)
    
    # Check specific user
    try:
        response = requests.get(f"{USER_API_URL}/user/{USER_ID}")
        if response.status_code == 200:
            user_data = response.json()
            print("✅ User found in database:")
            print(f"  App Version: {user_data.get('app_version', 'N/A')}")
            print(f"  Total Records: {user_data.get('total_records', 0)}")
            print(f"  Tours: {user_data.get('tours_count', 0)}")
            print(f"  Coordinates: {user_data.get('coordinates_count', 0)}")
            print(f"  Created: {user_data.get('created_at', 'N/A')}")
            
            # Show tour requests
            tours = user_data.get('tours', [])
            if tours:
                print("\n📱 Tour Requests:")
                for tour in tours:
                    print(f"  - {tour.get('request_string', 'N/A')}")
                    print(f"    Tour ID: {tour.get('tour_id', 'N/A')}")
                    print(f"    Time: {tour.get('timestamp', 'N/A')}")
            else:
                print("\n⚠️ No tour requests found")
                
        else:
            print(f"❌ User not found: {response.status_code}")
            
            # Check all users to see if user exists with different ID
            print("\nChecking all users...")
            all_response = requests.get(f"{USER_API_URL}/users")
            if all_response.status_code == 200:
                all_data = all_response.json()
                print(f"Total users in system: {all_data.get('total_users', 0)}")
                
                # Look for recent users
                recent_users = all_data.get('users', [])[:5]
                print("\nRecent users:")
                for user in recent_users:
                    print(f"  - {user['secret_id']} (v{user.get('app_version', '?')}) Tours: {user.get('tours_count', 0)}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_user_data()