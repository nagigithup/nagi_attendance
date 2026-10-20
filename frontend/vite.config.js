import { defineConfig } from "../../hrms/frontend/node_modules/vite/dist/node/index.js"
import vue from "../../hrms/frontend/node_modules/@vitejs/plugin-vue/dist/index.mjs"
import fs from "node:fs"
import path from "node:path"

const buildId = `${Date.now().toString(36)}`
const assetBase = "/assets/nagi_attendance/attendance/"

function serviceWorkerPlugin() {
	return {
		name: "nagi-attendance-service-worker",
		writeBundle(_options, bundle) {
			const generatedAssets = Object.values(bundle)
				.map(output => output.fileName)
				.filter(fileName => /\.(?:js|css)$/.test(fileName))
				.map(fileName => `${assetBase}${fileName}`)
			const shell = [
				...generatedAssets,
				"/assets/nagi_attendance/images/attendance-app.svg",
				"/assets/nagi_attendance/images/attendance-app-192.png",
				"/assets/nagi_attendance/images/attendance-app-512.png",
			]
			const template = fs.readFileSync(path.resolve("src/attendance-sw.js"), "utf8")
			const worker = template
				.replaceAll("__NAGI_BUILD_ID__", buildId)
				.replace("__NAGI_SHELL_ASSETS__", JSON.stringify(shell, null, "\t"))
			fs.writeFileSync(path.resolve("../nagi_attendance/www/attendance-sw.js"), worker)
		},
	}
}

export default defineConfig({
	plugins: [vue(), serviceWorkerPlugin()],
	define: {
		__NAGI_BUILD_ID__: JSON.stringify(buildId),
	},
	resolve: {
		alias: {
			vue: path.resolve("../../hrms/frontend/node_modules/vue/dist/vue.esm-bundler.js"),
		},
	},
	build: {
		outDir: "../nagi_attendance/public/attendance",
		emptyOutDir: false,
		manifest: "asset-manifest.json",
		target: "es2018",
		rollupOptions: {
			input: path.resolve("src/main.js"),
			output: {
				entryFileNames: "app.[hash].js",
				assetFileNames: "app.[hash][extname]",
			},
		},
	},
})
