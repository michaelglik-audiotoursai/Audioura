import base64

# Read base64 data
with open('russian_tour_b64.txt', 'r') as f:
    b64_data = f.read().strip()

# Decode to binary
zip_data = base64.b64decode(b64_data)

# Write ZIP file
with open('durant_kenrick_russian.zip', 'wb') as f:
    f.write(zip_data)

print(f"Russian tour ZIP created: {len(zip_data)} bytes")