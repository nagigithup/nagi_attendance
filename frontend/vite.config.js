import { defineConfig } from "../../hrms/frontend/node_modules/vite/dist/node/index.js"
import vue from "../../hrms/frontend/node_modules/@vitejs/plugin-vue/dist/index.mjs"
import path from "node:path"

export default defineConfig({
	plugins: [vue()],
	resolve: {
		alias: {
			vue: path.resolve("../../hrms/frontend/node_modules/vue/dist/vue.esm-bundler.js"),
		},
	},
	build: {
		outDir: "../nagi_attendance/public/attendance",
		emptyOutDir: false,
		target: "es2018",
		rollupOptions: {
			input: path.resolve("src/main.js"),
			output: { entryFileNames: "app.js", assetFileNames: "app.[ext]" },
		},
	},
})
