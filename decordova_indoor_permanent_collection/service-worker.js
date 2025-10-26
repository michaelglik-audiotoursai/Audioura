const CACHE_NAME = 'newton-tour-v1';
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './manifest.json',
  './audio_1_museum_entrance_orientation.mp3',
  './audio_2_photography_gallery_harold_edgerton_ellen_carey.mp3',
  './audio_3_new_england_voices_dehner_mazur_selvage.mp3',
  './audio_4_sculpture_and_space_lewitt_oppenheimer.mp3',
  './audio_5_video_art_new_media_oursler_lucier.mp3',
  './audio_6_rooftop_gallery_takenaga_phillips_agha.mp3',
  './audio_7_material_transformations_booker_park_lugo.mp3',
  './audio_8_emerging_voices_hobbs_da_corte.mp3'
];

// Install: pre-cache assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
});

// Fetch: serve from cache if available
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request).then(response => response || fetch(event.request))
  );
});

// Activate: clean up old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
      )
    )
  );
});
