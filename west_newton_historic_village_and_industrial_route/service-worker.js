const CACHE_NAME = 'newton-tour-v1';
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './manifest.json',
  './audio_1_west_newton_square_and_railroad_station.mp3',
  './audio_2_second_church_in_newton.mp3',
  './audio_3_jackson_homestead_and_museum.mp3',
  './audio_4_site_of_newton_cotton_factory.mp3',
  './audio_5_myrtle_baptist_church_and_cemetery.mp3',
  './audio_6_nathaniel_allen_house.mp3',
  './audio_7_site_of_new_england_hospital_for_women_and_children_temporary_campus.mp3',
  './audio_8_west_newton_branch_library_closed.mp3'
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
