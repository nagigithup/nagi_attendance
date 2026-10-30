const BUILD_ID = "mvuhrj93"
const CACHE_PREFIX = "nagi-attendance-shell-"
const CACHE_NAME = `${CACHE_PREFIX}${BUILD_ID}`
const SHELL_ASSETS = [
	"/assets/nagi_attendance/attendance/app.ClWDV7aP.css",
	"/assets/nagi_attendance/attendance/app.Bcft-PvP.js",
	"/assets/nagi_attendance/images/attendance-app.svg",
	"/assets/nagi_attendance/images/attendance-app-192.png",
	"/assets/nagi_attendance/images/attendance-app-512.png"
]
const SENSITIVE_PATHS = ["/api/", "/files/", "/private/"]

function isSensitive(url) {
	return SENSITIVE_PATHS.some(prefix => url.pathname.startsWith(prefix))
}

function fetchWithoutStorage(request) {
	return fetch(request, { cache: "no-store" })
}

self.addEventListener("install", event => {
	event.waitUntil(
		caches.open(CACHE_NAME).then(cache => cache.addAll(
			SHELL_ASSETS.map(url => new Request(url, { cache: "reload" }))
		))
	)
})

self.addEventListener("activate", event => {
	event.waitUntil(
		caches.keys()
			.then(keys => Promise.all(
				keys
					.filter(key => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
					.map(key => caches.delete(key))
			))
			.then(() => self.clients.claim())
	)
})

self.addEventListener("message", event => {
	if (event.data?.type === "SKIP_WAITING") self.skipWaiting()
})

self.addEventListener("fetch", event => {
	const request = event.request
	const url = new URL(request.url)
	if (url.origin !== self.location.origin || request.method !== "GET") return

	if (isSensitive(url) || (request.mode === "navigate" && url.pathname.startsWith("/attendance"))) {
		event.respondWith(fetchWithoutStorage(request))
		return
	}

	if (url.pathname.endsWith("/manifest.webmanifest")) {
		event.respondWith(
			fetchWithoutStorage(request).catch(() => caches.match(request))
		)
		return
	}

	if (!SHELL_ASSETS.includes(url.pathname)) return
	event.respondWith(
		caches.open(CACHE_NAME).then(async cache => {
			const cached = await cache.match(request)
			if (cached) return cached
			const response = await fetch(request)
			if (response.ok) await cache.put(request, response.clone())
			return response
		})
	)
})
