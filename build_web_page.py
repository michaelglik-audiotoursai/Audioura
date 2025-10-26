"""
Generate website for audio tour with MP3 files.
"""
import os
import re
import glob

def format_title(directory_name):
    """Convert camel case directory name to space-separated title."""
    # Insert space before capital letters and capitalize first letter
    title = re.sub(r'(?<!^)(?=[A-Z])', ' ', directory_name)
    return title

def extract_stop_number_and_name(filename):
    """Extract stop number and name from audio filename."""
    match = re.match(r'audio_(\d+)_(.*?)\.mp3', filename)
    if match:
        stop_num = match.group(1)
        name = match.group(2).replace('_', ' ').title()
        return int(stop_num), f"Stop {stop_num}: {name}"
    return 999, filename  # Fallback for unexpected filenames

def generate_website(directory):
    """Generate website files for the audio tour."""
    # Use absolute path for directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Check if directory exists in the development folder first
    dev_dir_path = os.path.join(script_dir, directory)
    if os.path.exists(dev_dir_path):
        full_dir_path = dev_dir_path
    else:
        # Fall back to project root directory
        project_root = os.path.dirname(script_dir)
        full_dir_path = os.path.join(project_root, directory)
    
    # Debug info
    print(f"Looking for MP3 files in: {full_dir_path}")
    
    # Get all MP3 files
    mp3_files = glob.glob(os.path.join(full_dir_path, "audio_*.mp3"))
    
    if not mp3_files:
        print(f"No audio MP3 files found in {full_dir_path}")
        return
    
    print(f"Found {len(mp3_files)} MP3 files")
    
    # Sort files by stop number
    mp3_files_with_info = [(f, *extract_stop_number_and_name(os.path.basename(f))) for f in mp3_files]
    mp3_files_with_info.sort(key=lambda x: x[1])  # Sort by stop number
    
    # Format title from directory name
    title = format_title(directory)
    
    # Generate index.html
    generate_index_html(title, mp3_files_with_info, full_dir_path)
    
    # Generate manifest.json
    generate_manifest_json(title, full_dir_path)
    
    # Generate service-worker.js
    generate_service_worker_js(mp3_files, full_dir_path)
    
    print(f"Website files generated in {directory}:")
    print("- index.html")
    print("- manifest.json")
    print("- service-worker.js")

def generate_index_html(title, mp3_files_with_info, directory):
    """Generate index.html file."""
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="manifest" href="manifest.json">
  <style>
    body {{
      font-family: Arial, sans-serif;
      margin: 40px;
      background-color: #f9f9f9;
      color: #333;
    }}
    h1 {{
      color: #2c3e50;
    }}
    .tour-section {{
      margin-top: 30px;
      padding: 20px;
      border-radius: 12px;
      background-color: #ffffff;
      box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }}
    .tour-title {{
      font-size: 20px;
      margin-bottom: 10px;
      font-weight: bold;
    }}
    audio {{
      width: 100%;
      margin-bottom: 20px;
    }}
  </style>
</head>
<body>

  <h1>Welcome to {title} Audio Tour</h1>

  <p>Use the audio guide below to listen to each part of the tour at your own pace — even without Internet.</p>
"""

    # Add audio sections
    for filename, _, title_text in mp3_files_with_info:
        # Extract just the base filename without directory path
        base_filename = os.path.basename(filename)
        html_content += f"""
  <div class="tour-section">
    <div class="tour-title">{title_text}</div>
    <audio controls>
      <source src="{base_filename}" type="audio/mpeg">
      Your browser does not support the audio element.
    </audio>
  </div>
"""

    # Add scripts
    html_content += """
  <script>
    // Register service worker for offline support
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('service-worker.js')
        .then(registration => {
          console.log("Service Worker Registered");
          
          // Force immediate caching of all assets
          if (registration.active) {
            registration.active.postMessage({type: 'CACHE_ALL_NOW'});
          }
          
          // Listen for messages from the service worker
          navigator.serviceWorker.addEventListener('message', event => {
            if (event.data && event.data.type === 'CACHING_COMPLETE') {
              console.log(event.data.message);
              // Show a notification to the user
              if ('Notification' in window && Notification.permission === 'granted') {
                new Notification('Audio Tour Ready', {
                  body: 'All audio files have been cached for offline use.',
                  icon: '/icon.png'
                });
              }
            }
          });
        })
        .catch(err => console.error("Service Worker Failed:", err));
    }
    
    // Add to home screen prompt
    let deferredPrompt;
    window.addEventListener('beforeinstallprompt', (e) => {
      // Prevent Chrome 67 and earlier from automatically showing the prompt
      e.preventDefault();
      // Stash the event so it can be triggered later
      deferredPrompt = e;
      
      // Show a custom "Add to Home Screen" button
      const addToHomeBtn = document.createElement('button');
      addToHomeBtn.style.position = 'fixed';
      addToHomeBtn.style.bottom = '20px';
      addToHomeBtn.style.right = '20px';
      addToHomeBtn.style.padding = '10px 15px';
      addToHomeBtn.style.backgroundColor = '#2c3e50';
      addToHomeBtn.style.color = 'white';
      addToHomeBtn.style.border = 'none';
      addToHomeBtn.style.borderRadius = '5px';
      addToHomeBtn.style.zIndex = '1000';
      addToHomeBtn.textContent = 'Add to Home Screen';
      
      addToHomeBtn.addEventListener('click', (e) => {
        // Show the install prompt
        deferredPrompt.prompt();
        // Wait for the user to respond to the prompt
        deferredPrompt.userChoice.then((choiceResult) => {
          if (choiceResult.outcome === 'accepted') {
            console.log('User accepted the install prompt');
            addToHomeBtn.remove();
          }
          deferredPrompt = null;
        });
      });
      
      document.body.appendChild(addToHomeBtn);
    });
  </script>
  <script>
  document.addEventListener("DOMContentLoaded", () => {
    const audioElements = document.querySelectorAll("audio");
    
    // Preload all audio files
    audioElements.forEach(audio => {
      // Force preloading of audio
      audio.load();
      
      // Pause other audio when one starts playing
      audio.addEventListener("play", () => {
        audioElements.forEach(other => {
          if (other !== audio) {
            other.pause();
          }
        });
      });
    });
    
    // Add offline status indicator
    const offlineIndicator = document.createElement('div');
    offlineIndicator.style.display = 'none';
    offlineIndicator.style.position = 'fixed';
    offlineIndicator.style.top = '10px';
    offlineIndicator.style.left = '10px';
    offlineIndicator.style.padding = '5px 10px';
    offlineIndicator.style.backgroundColor = '#ff9800';
    offlineIndicator.style.color = 'white';
    offlineIndicator.style.borderRadius = '3px';
    offlineIndicator.textContent = 'Offline Mode';
    document.body.appendChild(offlineIndicator);
    
    // Update offline status
    function updateOfflineStatus() {
      if (!navigator.onLine) {
        offlineIndicator.style.display = 'block';
      } else {
        offlineIndicator.style.display = 'none';
      }
    }
    
    window.addEventListener('online', updateOfflineStatus);
    window.addEventListener('offline', updateOfflineStatus);
    updateOfflineStatus();
  });
</script>

</body>
</html>
"""

    with open(os.path.join(directory, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)

def create_placeholder_icons(directory):
    """Create simple placeholder icons for PWA."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # Create icons in two sizes
        for size in [192, 512]:
            icon_path = os.path.join(directory, f"icon-{size}.png")
            
            # Skip if icon already exists
            if os.path.exists(icon_path):
                continue
                
            # Create a blank image with blue background
            img = Image.new('RGB', (size, size), color=(44, 62, 80))
            draw = ImageDraw.Draw(img)
            
            # Draw a simple icon (circle)
            center = size // 2
            radius = size // 3
            draw.ellipse(
                [(center - radius, center - radius), 
                 (center + radius, center + radius)], 
                fill=(255, 255, 255)
            )
            
            # Save the icon
            img.save(icon_path)
            print(f"Created icon: {icon_path}")
    except ImportError:
        print("PIL not installed. Skipping icon creation.")
        # Create empty files as placeholders
        for size in [192, 512]:
            icon_path = os.path.join(directory, f"icon-{size}.png")
            if not os.path.exists(icon_path):
                with open(icon_path, 'wb') as f:
                    f.write(b'')
                print(f"Created empty placeholder: {icon_path}")

def generate_manifest_json(title, directory):
    """Generate manifest.json file."""
    manifest_content = f"""{{
  "name": "{title} Audio Tour",
  "short_name": "Audio Tour",
  "description": "Offline-capable audio tour guide",
  "id": "audiotour-{title.lower().replace(' ', '-')}",
  "start_url": "index.html",
  "scope": "./",
  "display": "standalone",
  "orientation": "portrait",
  "background_color": "#ffffff",
  "theme_color": "#2c3e50",
  "icons": [
    {{
      "src": "icon-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any maskable"
    }},
    {{
      "src": "icon-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any maskable"
    }}
  ],
  "prefer_related_applications": false
}}
"""
    
    # Create simple placeholder icons if they don't exist
    create_placeholder_icons(directory)

    with open(os.path.join(directory, "manifest.json"), "w", encoding="utf-8") as f:
        f.write(manifest_content)

def generate_service_worker_js(mp3_files, directory):
    """Generate service-worker.js file."""
    # Create list of assets to cache
    assets = [
        "./",
        "./index.html",
        "./manifest.json"
    ]
    
    # Add all MP3 files
    for mp3_file in mp3_files:
        # Extract just the base filename without directory path
        base_filename = os.path.basename(mp3_file)
        assets.append(f"./{base_filename}")
    
    # Format assets list as JSON string
    assets_str = ",\n  ".join([f"'{asset}'" for asset in assets])
    
    service_worker_content = f"""const CACHE_NAME = 'audio-tour-v2';
const ASSETS_TO_CACHE = [
  {assets_str}
];

// Force the service worker to activate immediately
self.addEventListener('install', event => {{
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {{
        console.log('Caching all assets');
        return cache.addAll(ASSETS_TO_CACHE);
      }})
      .catch(error => {{
        console.error('Error during cache.addAll():', error);
      }})
  );
}});

// Claim clients immediately so the service worker controls the page on first load
self.addEventListener('activate', event => {{
  event.waitUntil(
    Promise.all([
      // Take control of all clients as soon as the service worker activates
      clients.claim(),
      
      // Clear old caches
      caches.keys().then(cacheNames => {{
        return Promise.all(
          cacheNames.filter(cacheName => cacheName !== CACHE_NAME)
            .map(cacheName => caches.delete(cacheName))
        );
      }})
    ])
  );
}});

// Completely offline-first strategy
self.addEventListener('fetch', event => {{
  // Extract the URL without the host and protocol
  const url = new URL(event.request.url);
  const requestPath = url.pathname;
  
  // Create a new request for just the file path
  const offlineRequest = new Request(requestPath);
  
  event.respondWith(
    // First try to match the exact request
    caches.match(event.request)
      .then(cachedResponse => {{
        if (cachedResponse) {{
          return cachedResponse;
        }}
        
        // If not found, try matching just the path
        return caches.match(offlineRequest)
          .then(pathCachedResponse => {{
            if (pathCachedResponse) {{
              return pathCachedResponse;
            }}
            
            // If still not found and online, fetch from network
            if (navigator.onLine) {{
              return fetch(event.request)
                .then(response => {{
                  // Don't cache if not a valid response
                  if (!response || response.status !== 200) {{
                    return response;
                  }}
                  
                  // Clone the response since we need to use it twice
                  const responseToCache = response.clone();
                  
                  // Cache both the full URL and the path-only version
                  caches.open(CACHE_NAME).then(cache => {{
                    cache.put(event.request, response.clone());
                    cache.put(offlineRequest, responseToCache);
                  }});
                  
                  return response;
                }});
            }}
            
            // If offline and not in cache, return a custom offline page
            // For now, just let the error propagate
            return new Response('Offline content not available', {{
              status: 503,
              statusText: 'Service Unavailable',
              headers: new Headers({{
                'Content-Type': 'text/plain'
              }})
            }});
          }});
      }})
  );
}});

// Listen for messages from the main page
self.addEventListener('message', event => {{
  if (event.data && event.data.type === 'CACHE_ALL_NOW') {{
    // Force cache all assets immediately
    caches.open(CACHE_NAME)
      .then(cache => {{
        return cache.addAll(ASSETS_TO_CACHE);
      }})
      .then(() => {{
        // Notify the page that caching is complete
        self.clients.matchAll().then(clients => {{
          clients.forEach(client => {{
            client.postMessage({{
              type: 'CACHING_COMPLETE',
              message: 'All audio files have been cached for offline use.'
            }});
          }});
        }});
      }});
  }}
}});
"""

    with open(os.path.join(directory, "service-worker.js"), "w", encoding="utf-8") as f:
        f.write(service_worker_content)

if __name__ == "__main__":
    # Directory containing the MP3 files
    tour_directory = "tour_newtonville_and_waban_heritage_trail"
    
    # Generate website
    generate_website(tour_directory)