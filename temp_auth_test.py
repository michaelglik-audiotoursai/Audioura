
import sys
sys.path.append('/app')
from newsletter_processor_service import authenticate_boston_globe_enhanced
import json

credentials = {"username": "glikfamily@gmail.com", "password": "Eight2Four"}
article_url = "https://www.bostonglobe.com/2024/11/13/business/"

print("Starting authentication test...")
result = authenticate_boston_globe_enhanced(credentials, article_url)
print("Authentication result:", json.dumps(result, indent=2))
