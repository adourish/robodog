const serviceworkerCACHE = 'robodog.service -precache';
const precacheFiles = [
 /* Add an array of files to precache for your app */
];

self.addEventListener('install', function(event) {
 console.log('robodog.service install event processing');

 event.waitUntil(
   caches.open(serviceworkerCACHE).then(function(cache) {
     console.log('robodog.service Cached offline page during install');
     
     return cache.addAll(precacheFiles);
   })
 );
});

self.addEventListener('fetch', function(event) {
  console.debug('robodog.service fetch listen', event)
  if (event.request.url.includes('console.knowledge')) {
    event.respondWith(
      caches.open(serviceworkerCACHE).then(function(cache) {
        return cache.match(event.request).then(function(response) {
          var fetchPromise = fetch(event.request).then(function(networkResponse) {
            cache.put(event.request, networkResponse.clone());
            return networkResponse;
          });
          return response || fetchPromise;
        })
      })
    );
  }
});

self.addEventListener('message', function(event) {
  console.debug('console.service message', event)
  if (event.data.command === 'update') {
    caches.open(serviceworkerCACHE).then(function(cache) {
      cache.put(event.data.url, new Response(event.data.data));
    });
  }
});