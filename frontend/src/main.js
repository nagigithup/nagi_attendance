import { createApp } from "vue"
import App from "./App.vue"
import "./style.css"

createApp(App).mount("#app")

if ("serviceWorker" in navigator && window.isSecureContext) {
	window.addEventListener("load", () => navigator.serviceWorker.register(
		"/attendance-sw.js",
		{ scope: "/attendance" }
	))
}
