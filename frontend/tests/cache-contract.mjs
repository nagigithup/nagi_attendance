import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import vm from "node:vm"
import { fileURLToPath } from "node:url"

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const appRoot = path.resolve(frontendRoot, "..")
const publicRoot = path.join(appRoot, "nagi_attendance/public/attendance")
const manifest = JSON.parse(fs.readFileSync(path.join(publicRoot, "asset-manifest.json"), "utf8"))
const entry = Object.values(manifest).find(value => value.isEntry)

assert.match(entry.file, /^app\.[A-Za-z0-9_-]+\.js$/)
assert.ok(entry.css.every(file => /^app\.[A-Za-z0-9_-]+\.css$/.test(file)))
assert.ok(fs.existsSync(path.join(publicRoot, entry.file)))
assert.ok(entry.css.every(file => fs.existsSync(path.join(publicRoot, file))))

const pageTemplate = fs.readFileSync(path.join(appRoot, "nagi_attendance/www/attendance.html"), "utf8")
assert.ok(pageTemplate.includes("frontend_assets.javascript"))
assert.ok(pageTemplate.includes("frontend_assets.stylesheets"))
assert.ok(!pageTemplate.includes('src="/assets/nagi_attendance/attendance/app.js"'))

const mainSource = fs.readFileSync(path.join(frontendRoot, "src/main.js"), "utf8")
assert.ok(mainSource.includes('updateViaCache: "none"'))
assert.ok(mainSource.includes("يتوفر تحديث جديد"))
assert.ok(mainSource.includes("A new version is available"))

const workerSource = fs.readFileSync(path.join(appRoot, "nagi_attendance/www/attendance-sw.js"), "utf8")
assert.ok(!workerSource.includes("__NAGI_BUILD_ID__"))
assert.ok(!workerSource.includes("__NAGI_SHELL_ASSETS__"))
assert.ok(workerSource.includes(entry.file))
assert.ok(entry.css.every(file => workerSource.includes(file)))

const handlers = {}
const deletedCaches = []
const fetchCalls = []
const precached = []
let claimed = false
let skipped = false

class MockRequest {
	constructor(url, options = {}) {
		this.url = new URL(url, "https://attendance.test").href
		this.method = options.method || "GET"
		this.mode = options.mode || "same-origin"
		this.cache = options.cache
	}
}

const cache = {
	async addAll(requests) { precached.push(...requests) },
	async match() { return undefined },
	async put() {},
}
const context = {
	URL,
	Request: MockRequest,
	console,
	Promise,
	caches: {
		async open() { return cache },
		async keys() { return ["nagi-attendance-shell-v4", "nagi-attendance-shell-unrelated-build", "other-app-cache"] },
		async delete(key) { deletedCaches.push(key); return true },
		async match() { return undefined },
	},
	async fetch(request, options = {}) {
		fetchCalls.push({ request, options })
		return { ok: true, clone() { return this } }
	},
	self: {
		location: { origin: "https://attendance.test" },
		clients: { async claim() { claimed = true } },
		async skipWaiting() { skipped = true },
		addEventListener(type, handler) { handlers[type] = handler },
	},
}
vm.runInNewContext(workerSource, context)

let pending
handlers.install({ waitUntil(value) { pending = value } })
await pending
assert.ok(precached.length >= 2)
assert.ok(precached.every(request => request.cache === "reload"))
assert.ok(precached.some(request => request.url.endsWith(entry.file)))

handlers.activate({ waitUntil(value) { pending = value } })
await pending
assert.ok(deletedCaches.includes("nagi-attendance-shell-v4"))
assert.ok(deletedCaches.includes("nagi-attendance-shell-unrelated-build"))
assert.ok(!deletedCaches.includes("other-app-cache"))
assert.equal(claimed, true)

handlers.message({ data: { type: "SKIP_WAITING" } })
await Promise.resolve()
assert.equal(skipped, true)

let response
handlers.fetch({
	request: new MockRequest("https://attendance.test/api/method/nagi_attendance.mobile_api.bootstrap"),
	respondWith(value) { response = value },
})
await response
assert.equal(fetchCalls.at(-1).options.cache, "no-store")

handlers.fetch({
	request: new MockRequest("https://attendance.test/attendance", { mode: "navigate" }),
	respondWith(value) { response = value },
})
await response
assert.equal(fetchCalls.at(-1).options.cache, "no-store")

console.log("cache contract passed: hashed assets, legacy-cache cleanup, no-store HR requests, safe worker activation, and bilingual update notice")
