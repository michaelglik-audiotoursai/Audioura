#!/bin/bash

# Fix keystore issue for app upgrades
# This ensures the same signing key is used consistently

echo "=== KEYSTORE FIX FOR APP UPGRADES ==="

SOURCE_DIR="/media/sf_audiotours"
KEYSTORE_PATH="$SOURCE_DIR/audio_tour_app/android/app/debug.keystore"

if [ -f "$KEYSTORE_PATH" ]; then
    echo "✅ Original keystore found at: $KEYSTORE_PATH"
    
    # Create backup
    cp "$KEYSTORE_PATH" "$SOURCE_DIR/debug.keystore.backup"
    echo "✅ Keystore backed up"
    
    # Show keystore info
    echo "Keystore details:"
    keytool -list -v -keystore "$KEYSTORE_PATH" -alias androiddebugkey -storepass android -keypass android 2>/dev/null | grep -E "(Alias name|Creation date|Certificate fingerprints)" || echo "Could not read keystore details"
    
else
    echo "❌ Keystore not found!"
    echo "Creating new debug keystore..."
    
    # Generate new keystore if missing
    keytool -genkey -v -keystore "$KEYSTORE_PATH" -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 -storepass android -keypass android -dname "CN=Android Debug,O=Android,C=US"
    
    if [ -f "$KEYSTORE_PATH" ]; then
        echo "✅ New keystore created"
    else
        echo "❌ Failed to create keystore"
        exit 1
    fi
fi

echo "=== KEYSTORE FIX COMPLETED ==="