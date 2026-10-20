import { createApp } from "vue"
import App from "./App.vue"
import "./style.css"

createApp(App).mount("#app")

function showUpdateNotice(worker) {
	if (!worker || document.querySelector("[data-nagi-update-notice]")) return
	const notice = document.createElement("aside")
	notice.className = "app-update-notice"
	notice.dataset.nagiUpdateNotice = ""
	notice.setAttribute("role", "status")
	notice.innerHTML = `
		<div>
			<strong>يتوفر تحديث جديد</strong>
			<span>A new version is available</span>
		</div>
		<button type="button">تحديث الآن / Update now</button>
	`
	const button = notice.querySelector("button")
	button.addEventListener("click", () => {
		button.disabled = true
		button.textContent = "جارٍ التحديث… / Updating…"
		window.sessionStorage.setItem("nagi-update-reload", "1")
		worker.postMessage({ type: "SKIP_WAITING" })
	})
	document.body.appendChild(notice)
}

if ("serviceWorker" in navigator && window.isSecureContext) {
	let reloading = false
	navigator.serviceWorker.addEventListener("controllerchange", () => {
		if (reloading || window.sessionStorage.getItem("nagi-update-reload") !== "1") return
		reloading = true
		window.sessionStorage.removeItem("nagi-update-reload")
		window.location.reload()
	})

	window.addEventListener("load", async () => {
		try {
			const registration = await navigator.serviceWorker.register(
				`/attendance-sw.js?v=${encodeURIComponent(__NAGI_BUILD_ID__)}`,
				{ scope: "/attendance", updateViaCache: "none" }
			)
			if (registration.waiting && navigator.serviceWorker.controller) {
				showUpdateNotice(registration.waiting)
			}
			const watchInstalling = installing => {
				if (!installing) return
				const notifyWhenInstalled = () => {
					if (installing.state === "installed" && navigator.serviceWorker.controller) {
						showUpdateNotice(installing)
					}
				}
				notifyWhenInstalled()
				installing.addEventListener("statechange", () => {
					notifyWhenInstalled()
				})
			}
			watchInstalling(registration.installing)
			registration.addEventListener("updatefound", () => watchInstalling(registration.installing))
		} catch (error) {
			console.warn("Nagi Attendance service worker registration failed", error)
		}
	})
}
