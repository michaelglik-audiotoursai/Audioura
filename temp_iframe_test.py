
import sys
sys.path.append('/app')
from boston_globe_iframe_auth import authenticate_boston_globe_iframe
import json

credentials = {"username": "glikfamily@gmail.com", "password": "Eight2Four"}
article_url = "https://www.bostonglobe.com/2024/11/13/business/"

print("Starting iframe authentication test...")
try:
    result = authenticate_boston_globe_iframe(credentials, article_url)
    print("iframe Authentication result:", json.dumps(result, indent=2))
except Exception as e:
    print("iframe Authentication error:", str(e))
    import traceback
    traceback.print_exc()
