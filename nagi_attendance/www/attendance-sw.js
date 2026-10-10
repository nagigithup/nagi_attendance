const CACHE = "nagi-attendance-shell-v3"
const SHELL = [
	"/assets/nagi_attendance/attendance/app.js",
	"/assets/nagi_attendance/attendance/app.css",
	"/assets/nagi_attendance/images/attendance-app.svg",
	"/assets/nagi_attendance/images/attendance-app-192.png",
	"/assets/nagi_attendance/images/attendance-app-512.png"
]
self.addEventListener("install", event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL))))
self.addEventListener("activate", event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))))
self.addEventListener("fetch", event => {
	const url = new URL(event.request.url)
	if (event.request.method !== "GET" || url.pathname.startsWith("/api/") || url.pathname.startsWith("/files/") || url.pathname.startsWith("/private/")) return
	if (!SHELL.includes(url.pathname)) return
	event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)))
})
