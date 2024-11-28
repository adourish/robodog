const CACHE = 'pwabuilder-precache';
const precacheFiles = [
 /* Add an array of files to precache for your app */
];

self.addEventListener('install', function(event) {
 console.log('[PWA Builder] Install Event processing');

 event.waitUntil(
   caches.open(CACHE).then(function(cache) {
     console.log('[PWA Builder] Cached offline page during install');
     
     return cache.addAll(precacheFiles);
   })
 );
});

self.addEventListener('fetch', function(event) {
 console.log('[PWA Builder] The service worker is serving the asset.');

 event.respondWith(
   caches.open(CACHE).then(function(cache) {
     return cache.match(event.request).then(function(response) {
       return response || fetch(event.request);
     })
   })
 );
});