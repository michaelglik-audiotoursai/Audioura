"""
Prepare single HTML file for Netlify deployment by creating a directory with index.html
"""
import os
import shutil

def prepare_for_netlify(single_html_file):
    """
    Create a Netlify-ready directory from a single HTML file.
    
    Args:
        single_html_file: Path to the single HTML file created by single_file_app_builder
        
    Returns:
        str: Name of the created directory
    """
    # Get the base name without extension
    base_name = os.path.splitext(single_html_file)[0]
    netlify_dir = f"{base_name}_netlify"
    
    # Create the netlify directory
    if os.path.exists(netlify_dir):
        shutil.rmtree(netlify_dir)
    os.makedirs(netlify_dir)
    
    # Copy the single HTML file as index.html
    shutil.copy2(single_html_file, os.path.join(netlify_dir, "index.html"))
    
    # Create manifest.json for PWA
    manifest_content = {
        "name": base_name.replace("_", " ").title(),
        "short_name": base_name.replace("_", " ").title(),
        "description": "Audio Tour App",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#2c3e50",
        "icons": [
            {
                "src": "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTkyIiBoZWlnaHQ9IjE5MiIgdmlld0JveD0iMCAwIDE5MiAxOTIiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIxOTIiIGhlaWdodD0iMTkyIiBmaWxsPSIjMmMzZTUwIi8+Cjx0ZXh0IHg9Ijk2IiB5PSIxMDAiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSI0OCIgZmlsbD0id2hpdGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiPvCfjoY8L3RleHQ+Cjwvc3ZnPgo=",
                "sizes": "192x192",
                "type": "image/svg+xml"
            }
        ]
    }
    
    with open(os.path.join(netlify_dir, "manifest.json"), "w") as f:
        import json
        json.dump(manifest_content, f, indent=2)
    
    # Create service worker for offline functionality
    service_worker_content = """
const CACHE_NAME = 'audio-tour-v1';
const urlsToCache = [
  '/',
  '/index.html'
];

self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) {
        return cache.addAll(urlsToCache);
      })
  );
});

self.addEventListener('fetch', function(event) {
  event.respondWith(
    caches.match(event.request)
      .then(function(response) {
        if (response) {
          return response;
        }
        return fetch(event.request);
      }
    )
  );
});
"""
    
    with open(os.path.join(netlify_dir, "service-worker.js"), "w") as f:
        f.write(service_worker_content)
    
    print(f"Created Netlify-ready directory: {netlify_dir}")
    print(f"Contents: index.html, manifest.json, service-worker.js")
    
    return netlify_dir

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        html_file = sys.argv[1]
    else:
        html_file = input("Enter the single HTML file name: ")
    
    prepare_for_netlify(html_file)