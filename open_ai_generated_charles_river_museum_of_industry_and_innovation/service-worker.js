const CACHE_NAME = 'audio-tour-v2';
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './manifest.json',
  './audio_10_industrial_revolution_artifacts.mp3',
  './audio_1_1_textile_machinery_collection.mp3',
  './audio_2_waltham_watch_company_artifacts.mp3',
  './audio_3_boston_manufacturing_company_model.mp3',
  './audio_4_francis_cabot_lowell_portrait.mp3',
  './audio_5_waltham_lowell_system_timeline.mp3',
  './audio_6_waltham_fire_department_exhibit.mp3',
  './audio_7_metz_company_fire_engine.mp3',
  './audio_8_waltham_telegraph_and_morse_code_collection.mp3',
  './audio_9_boston_manufacturing_company_waterwheel_replica.mp3'
];

// Force the service worker to activate immediately
self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Caching all assets');
        return cache.addAll(ASSETS_TO_CACHE);
      })
      .catch(error => {
        console.error('Error during cache.addAll():', error);
      })
  );
});

// Claim clients immediately so the service worker controls the page on first load
self.addEventListener('activate', event => {
  event.waitUntil(
    Promise.all([
      // Take control of all clients as soon as the service worker activates
      clients.claim(),
      
      // Clear old caches
      caches.keys().then(cacheNames => {
        return Promise.all(
          cacheNames.filter(cacheName => cacheName !== CACHE_NAME)
            .map(cacheName => caches.delete(cacheName))
        );
      })
    ])
  );
});

// Completely offline-first strategy
self.addEventListener('fetch', event => {
  // Extract the URL without the host and protocol
  const url = new URL(event.request.url);
  const requestPath = url.pathname;
  
  // Create a new request for just the file path
  const offlineRequest = new Request(requestPath);
  
  event.respondWith(
    // First try to match the exact request
    caches.match(event.request)
      .then(cachedResponse => {
        if (cachedResponse) {
          return cachedResponse;
        }
        
        // If not found, try matching just the path
        return caches.match(offlineRequest)
          .then(pathCachedResponse => {
            if (pathCachedResponse) {
              return pathCachedResponse;
            }
            
            // If still not found and online, fetch from network
            if (navigator.onLine) {
              return fetch(event.request)
                .then(response => {
                  // Don't cache if not a valid response
                  if (!response || response.status !== 200) {
                    return response;
                  }
                  
                  // Clone the response since we need to use it twice
                  const responseToCache = response.clone();
                  
                  // Cache both the full URL and the path-only version
                  caches.open(CACHE_NAME).then(cache => {
                    cache.put(event.request, response.clone());
                    cache.put(offlineRequest, responseToCache);
                  });
                  
                  return response;
                });
            }
            
            // If offline and not in cache, return a custom offline page
            // For now, just let the error propagate
            return new Response('Offline content not available', {
              status: 503,
              statusText: 'Service Unavailable',
              headers: new Headers({
                'Content-Type': 'text/plain'
              })
            });
          });
      })
  );
});

// Listen for messages from the main page
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'CACHE_ALL_NOW') {
    // Force cache all assets immediately
    caches.open(CACHE_NAME)
      .then(cache => {
        return cache.addAll(ASSETS_TO_CACHE);
      })
      .then(() => {
        // Notify the page that caching is complete
        self.clients.matchAll().then(clients => {
          clients.forEach(client => {
            client.postMessage({
              type: 'CACHING_COMPLETE',
              message: 'All audio files have been cached for offline use.'
            });
          });
        });
      });
  }
});
