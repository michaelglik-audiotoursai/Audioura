#!/bin/bash

# AudioTours Flutter Web Demo Server
# Copies essential files and starts web server

set -e

echo "🚀 Starting AudioTours Web Demo Server"
echo "======================================="

# Clean up previous demo directory
echo "Cleaning up previous demo directory..."
rm -rf ~/audiotours_web_demo

# Create fresh demo directory
echo "Creating fresh demo directory..."
mkdir ~/audiotours_web_demo

# Copy only essential files for web demo
echo "Copying essential files from Windows shared folder..."
cp -r /media/sf_audiotours/audio_tour_app/lib ~/audiotours_web_demo/
cp -r /media/sf_audiotours/audio_tour_app/web ~/audiotours_web_demo/
cp /media/sf_audiotours/audio_tour_app/pubspec.yaml ~/audiotours_web_demo/
cp /media/sf_audiotours/audio_tour_app/pubspec.lock ~/audiotours_web_demo/ 2>/dev/null || echo "No pubspec.lock found, continuing..."

# Copy assets if they exist
if [ -d "/media/sf_audiotours/audio_tour_app/assets" ]; then
    cp -r /media/sf_audiotours/audio_tour_app/assets ~/audiotours_web_demo/
    echo "✅ Assets copied"
else
    echo "⚠️  No assets directory found, creating empty one"
    mkdir -p ~/audiotours_web_demo/assets/images
fi

# Copy .env file if it exists
if [ -f "/media/sf_audiotours/audio_tour_app/.env" ]; then
    cp /media/sf_audiotours/audio_tour_app/.env ~/audiotours_web_demo/
    echo "✅ .env file copied"
else
    echo "⚠️  No .env file found, creating empty one"
    touch ~/audiotours_web_demo/.env
fi

# Navigate to demo directory
cd ~/audiotours_web_demo

echo "✅ Files copied successfully"
echo "📁 Demo directory: ~/audiotours_web_demo"

# Initialize Flutter project
echo "Initializing Flutter web demo..."
flutter pub get

# Check version
VERSION=$(grep "^version:" pubspec.yaml | cut -d' ' -f2)
echo "🎯 Running AudioTours v$VERSION"

echo ""
echo "🌐 Starting Flutter web server..."
echo "📍 URL: http://localhost:8080"
echo "🔗 Windows access: http://localhost:8080 (via port forwarding)"
echo ""
echo "Press Ctrl+C to stop the server"
echo "======================================="

# Start the web server (this will block until Ctrl+C)
flutter run -d web-server --web-port 8080 --web-hostname 0.0.0.0

# This runs when server stops (Ctrl+C pressed)
echo ""
echo "🛑 Web server stopped"
echo "🧹 Cleaning up demo directory..."
cd ~
rm -rf ~/audiotours_web_demo
echo "✅ Demo directory cleaned up"
echo "📁 Back to home directory: $(pwd)"
echo "🎉 Demo session complete!"