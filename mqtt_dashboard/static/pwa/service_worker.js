// Cache name
const CACHE_NAME = 'elkland-airstrip-weather-cache-v1';

// Files to cache
const FILES_TO_CACHE = [
  '/',
  '/index.html',
  '/manifest.json',
  'https://cdn.jsdelivr.net/npm/chart.js',
  'https://cdn.jsdelivr.net/npm/moment',
  'https://cdn.jsdelivr.net/npm/chartjs-adapter-moment',
  'https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/css/bootstrap.min.css',
  'https://fonts.googleapis.com/css2?family=Sen:wght@400;700&display=swap',
  'https://cdnjs.cloudflare.com/ajax/libs/moment-timezone/0.5.33/moment-timezone-with-data-10-year-range.min.js',
  'https://code.jquery.com/jquery-3.3.1.slim.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/popper.js/1.14.7/umd/popper.min.js',
  'https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/js/bootstrap.min.js'
];

// Install event
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        return cache.addAll(FILES_TO_CACHE);
      })
      .catch(err => console.error('Cache install error:', err))
  );
});

// Activate event
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.filter(cacheName => {
          return cacheName !== CACHE_NAME;
        }).map(cacheName => {
          return caches.delete(cacheName);
        })
      );
    })
  );
});

// Fetch event
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response; // Return cached response if available
        }
        return fetch(event.request); // Fetch from network if not in cache
      })
  );
});
