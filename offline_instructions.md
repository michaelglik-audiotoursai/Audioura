# Making Your Audio Tour Work Offline

## The Problem

When you add a website to your home screen that uses an IP address (like `http://192.168.0.217:8000`), it will try to connect to that specific IP address when launched. When you're on a different network, that IP address is no longer valid, causing the "site cannot be reached" error.

## Solution: Create a Proper Offline PWA

Follow these steps to make your audio tour work completely offline:

1. **Regenerate your tour website** with the updated code:
   ```
   python text_to_index.py
   ```

2. **Access the tour on your phone** while connected to your home network:
   - Start the server: `python start_server.py`
   - On your phone, navigate to the URL shown in the terminal
   - Wait for the page to fully load (all audio files should be cached)

3. **Add to home screen properly**:
   - On iOS (Safari): Tap the share icon (square with up arrow) → "Add to Home Screen"
   - On Android (Chrome): Tap the menu (three dots) → "Add to Home Screen" or "Install app"

4. **Test offline mode while still on your home network**:
   - Stop the server (press Ctrl+C)
   - Open the app from your home screen (not from browser history)
   - Verify that all audio files play correctly

5. **Use on different networks**:
   - When away from home, always open the tour from the home screen icon
   - The offline indicator should appear when you're not connected to your home network
   - All audio should still play correctly

## Troubleshooting

If you still have issues:

1. **Clear browser cache** and try again:
   - iOS: Settings → Safari → Clear History and Website Data
   - Android: Chrome → Settings → Privacy → Clear browsing data

2. **Force reload the page** while on your home network:
   - iOS: Tap and hold the refresh button, then tap "Reload Without Content Blockers"
   - Android: Tap and hold the refresh button, then tap "Reload"

3. **Check storage permissions**:
   - Make sure your browser has permission to use storage on your device

4. **Try a different browser**:
   - Chrome tends to have the best PWA support on both iOS and Android

## Technical Details

The updated service worker now:
1. Caches files by path rather than full URL
2. Works completely offline by matching cached resources by path
3. Has a unique ID in the manifest to ensure proper installation
4. Shows an offline indicator when not connected to the original network