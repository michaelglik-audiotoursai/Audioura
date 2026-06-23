#!/usr/bin/env python3
from advertisement_detector import AdvertisementDetector

# Test SKIMS article
detector = AdvertisementDetector()
content = """Lightweight Cotton Soft, breathable cotton panties elevated with sweet and sexy details Home / Lightweight Cotton Help Return Policy Start Return Track Order Track Return Size Guides Ordering Shipping FAQs Contact Us STAY IN THE KNOW Be the first to discover new drops, special offers, and all things SKIMS Please enter a valid email address By submitting your email you agree to receive recurring automated marketing messages from SKIMS. View Terms & Privacy Text SKIMS to 68805 to never miss a drop!"""

title = "ARTICLE: Lightweight Cotton"

is_ad, confidence, indicators = detector.is_advertisement(content, title)

print(f"Is Advertisement: {is_ad}")
print(f"Confidence Score: {confidence:.2f}")
print(f"Indicators Found: {len(indicators)}")
print("Top indicators:")
for i in indicators[:8]:
    print(f"  - {i}")
print(f"\nReason: {detector.get_ad_reason(indicators)}")