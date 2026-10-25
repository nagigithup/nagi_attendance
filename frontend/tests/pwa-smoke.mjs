import { chromium } from "../../../pos_next/node_modules/playwright/index.mjs"
import assert from "node:assert/strict"
import fs from "node:fs"
import http from "node:http"

const assetManifest = JSON.parse(fs.readFileSync(new URL("../../nagi_attendance/public/attendance/asset-manifest.json", import.meta.url), "utf8"))
const assetEntry = Object.values(assetManifest).find(value => value.isEntry)
const stylesheetLinks = (assetEntry.css || []).map(file => `<link rel="stylesheet" href="/assets/nagi_attendance/attendance/${file}">`).join("")
const workerSource = fs.readFileSync(new URL("../../nagi_attendance/www/attendance-sw.js", import.meta.url), "utf8")
const attendanceHtml = `<!doctype html><html lang="ar" dir="rtl"><head><meta name="theme-color" content="#176B5B">${stylesheetLinks}<script>window.csrf_token="test"</script><script type="module" src="/assets/nagi_attendance/attendance/${assetEntry.file}"></script></head><body><div id="app"></div></body></html>`
let logoutMethod = null
let nextAction = "IN"
let lastLog = null
let includeDailyAttendance = false
let shortPermissionEnabled = false
const attendanceActions = []

const server = http.createServer(async (request, response) => {
	const url = new URL(request.url, "http://127.0.0.1")
	const respondJson = message => {
		response.setHeader("Content-Type", "application/json")
		response.end(JSON.stringify({message}))
	}
	if (url.pathname.endsWith("/nagi_attendance.mobile_api.bootstrap")) {
		respondJson({...bootstrap,settings:{...bootstrap.settings,enable_short_permission:shortPermissionEnabled},...(shortPermissionEnabled?{short_permission:{requests:[],pending_approvals:[]}}:{}),today:{...bootstrap.today,logs:lastLog?[lastLog]:[],last_log:lastLog,next_action:nextAction,status:nextAction === "IN" ? "Not Checked In" : "Checked In"}})
		return
	}
	if (url.pathname.endsWith("/nagi_attendance.mobile_api.create_checkin")) {
		let body = ""
		for await (const chunk of request) body += chunk
		const action = JSON.parse(body).log_type
		attendanceActions.push(action)
		await new Promise(resolve => setTimeout(resolve, 200))
		const recordedTime = action === "IN" ? "2026-10-10 09:15:00" : "2026-10-10 17:05:00"
		lastLog = {name:`LOG-${attendanceActions.length}`,log_type:action,time:recordedTime,shift:"09:00–17:00"}
		nextAction = action === "IN" ? "OUT" : "IN"
		respondJson(lastLog)
		return
	}
	if (url.pathname.endsWith("/nagi_attendance.mobile_api.get_attendance_history")) {
		respondJson({events:{},checkins:historyCheckins,records:includeDailyAttendance?dailyAttendance:[]})
		return
	}
	if (url.pathname === "/api/method/logout") {
		logoutMethod = request.method
		respondJson("Logged Out")
		return
	}
	if (url.pathname === "/attendance") {
		response.setHeader("Content-Type", "text/html; charset=utf-8")
		response.end(attendanceHtml)
		return
	}
	if (url.pathname === "/attendance-sw.js") {
		response.setHeader("Content-Type", "application/javascript; charset=utf-8")
		response.end(workerSource)
		return
	}
	const assetPrefix = "/assets/nagi_attendance/attendance/"
	if (url.pathname.startsWith(assetPrefix)) {
		const filename = url.pathname.slice(assetPrefix.length)
		if (!/^[A-Za-z0-9._-]+$/.test(filename)) {
			response.writeHead(400).end()
			return
		}
		const contents = fs.readFileSync(new URL(`../../nagi_attendance/public/attendance/${filename}`, import.meta.url))
		response.setHeader("Content-Type", filename.endsWith(".css") ? "text/css" : "application/javascript")
		response.end(contents)
		return
	}
	const imagePrefix = "/assets/nagi_attendance/images/"
	if (url.pathname.startsWith(imagePrefix)) {
		const filename = url.pathname.slice(imagePrefix.length)
		if (!/^[A-Za-z0-9._-]+$/.test(filename)) {
			response.writeHead(400).end()
			return
		}
		const contents = fs.readFileSync(new URL(`../../nagi_attendance/public/images/${filename}`, import.meta.url))
		response.setHeader("Content-Type", filename.endsWith(".svg") ? "image/svg+xml" : "image/png")
		response.end(contents)
		return
	}
	response.writeHead(404).end()
})
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve))
const base = `http://127.0.0.1:${server.address().port}`

const bootstrap = {
	user: "employee@example.com",
	employee: {name:"EMP-0001",employee_name:"موظف الاختبار",first_name:"موظف",designation:"مستشار",department:"القانونية",company:"شركة الاختبار",image:null},
	company: {name:"شركة الاختبار",abbr:"TEST",logo:null,currency:"AED",timezone:"Asia/Dubai",primary_color:"#315C8A",default_language:"ar",product_name:"Nagi Attendance & Leave"},
	companies: [{name:"شركة الاختبار",abbr:"TEST",primary_color:"#315C8A"}],
	settings: {enable_mobile_attendance:true,enable_mobile_leave:true,allow_attendance_history:true,enable_gps_validation:false,attendance_start_date:"2026-01-01"},
	today: {date:"2026-10-09",status:"Not Checked In",attendance:null,logs:[],last_log:null,next_action:"IN",shift:{name:"09:00–17:00",start_time:"09:00:00",end_time:"17:00:00"}},
	leave: {balances:{"Annual Leave":{allocated_leaves:20,balance_leaves:12}},types:["Annual Leave"],applications:[],upcoming:[],pending_approvals:[],configuration_error:null},
	languages:["ar","en"]
}
const historyCheckins = [
	{name:"HISTORY-4",time:"2026-10-10 20:30:00",log_type:"OUT",shift:null},
	{name:"HISTORY-3",time:"2026-10-10 12:00:00",log_type:"IN",shift:"09:00–17:00"},
	{name:"HISTORY-2",time:"2026-10-10 12:00:00",log_type:"OUT",shift:"09:00–17:00"},
	{name:"HISTORY-1",time:"2026-10-10 08:15:00",log_type:"IN",shift:"09:00–17:00"},
]
const dailyAttendance = [
	{name:"ATT-1",attendance_date:"2026-10-10",status:"Present",shift:"09:00–17:00",in_time:"2026-10-10 08:15:00",out_time:"2026-10-10 20:30:00",late_entry:0},
]

const browser = await chromium.launch({headless:true})
try {
	const page = await browser.newPage({viewport:{width:390,height:844},isMobile:true})
	const dialogs = []
	page.on("dialog", async dialog => {
		dialogs.push(dialog.type())
		await dialog.dismiss()
	})
	await page.goto(`${base}/attendance`)
	await page.waitForSelector(".bottom-nav")
	assert.equal(await page.locator("html").getAttribute("dir"), "rtl")
	assert.match(await page.locator(".brand strong").innerText(), /شركة الاختبار/)
	assert.equal(await page.locator(".bottom-nav button").count(), 4)
	assert.equal(await page.getByText("طلب إذن", {exact:true}).count(), 0)
	await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller))
	await page.waitForFunction(async () => (await caches.keys()).some(key => key.startsWith("nagi-attendance-shell-") && key !== "nagi-attendance-shell-v4"))
	const attendanceButton = page.locator(".check-button")
	assert.equal(await attendanceButton.innerText(), "تسجيل الحضور")
	await attendanceButton.click()
	assert.equal(await attendanceButton.isDisabled(), true)
	assert.equal(await attendanceButton.innerText(), "جارٍ التحميل…")
	await page.getByText("تمت العملية بنجاح.", {exact:true}).waitFor()
	await page.getByText("تسجيل الانصراف", {exact:true}).waitFor()
	const expectedArabicTime = new Intl.DateTimeFormat("ar-SA", {hour:"2-digit",minute:"2-digit"}).format(new Date("2026-10-10T09:15:00"))
	assert.equal(await page.locator(".hero-time").innerText(), expectedArabicTime)
	assert.deepEqual(attendanceActions, ["IN"])
	assert.deepEqual(dialogs, [])
	await page.getByText("الحضور", {exact:true}).last().click()
	await page.getByText("حركات الحضور والانصراف", {exact:true}).waitFor()
	assert.equal(await page.locator(".checkin-record").count(), 4)
	assert.deepEqual(await page.locator(".checkin-record .grow strong").allInnerTexts(), ["تسجيل الانصراف","تسجيل الحضور","تسجيل الانصراف","تسجيل الحضور"])
	assert.match(await page.locator(".checkin-record").first().innerText(), /خارج الوردية/)
	const expectedHistoryTime = new Intl.DateTimeFormat("ar-SA", {hour:"2-digit",minute:"2-digit"}).format(new Date("2026-10-10T20:30:00"))
	assert.equal(await page.locator(".checkin-record .times").first().innerText(), expectedHistoryTime)
	assert.equal(await page.getByText("لا توجد سجلات حضور لهذه الفترة.", {exact:true}).count(), 0)
	includeDailyAttendance = true
	await page.locator(".page-title button").click()
	await page.getByText("الحضور اليومي المحتسب", {exact:true}).waitFor()
	shortPermissionEnabled = true
	await page.reload()
	await page.waitForSelector(".bottom-nav")
	assert.equal(await page.locator(".bottom-nav button").count(), 5)
	await page.getByText("طلب إذن", {exact:true}).click()
	await page.getByText("طلب إذن أثناء الدوام", {exact:true}).waitFor()
	await page.getByText("حسابي", {exact:true}).click()
	await page.selectOption(".settings select", "en")
	assert.equal(await page.locator("html").getAttribute("dir"), "ltr")
	assert.ok(await page.getByText("My Account", {exact:true}).count() >= 1)
	assert.equal(await page.evaluate(() => document.body.scrollWidth <= window.innerWidth), true)
	await page.getByText("Permission", {exact:true}).click()
	await page.getByText("Permission During Working Hours", {exact:true}).waitFor()
	await page.getByText("Attendance", {exact:true}).last().click()
	await page.getByText("Check-in activity", {exact:true}).waitFor()
	assert.deepEqual(await page.locator(".checkin-record .grow strong").allInnerTexts(), ["Check Out","Check In","Check Out","Check In"])
	await page.getByText("Home", {exact:true}).click()
	assert.equal(await attendanceButton.innerText(), "Check Out")
	await attendanceButton.click()
	assert.equal(await attendanceButton.isDisabled(), true)
	assert.equal(await attendanceButton.innerText(), "Loading…")
	await page.getByText("Completed successfully.", {exact:true}).waitFor()
	await page.getByText("Check In", {exact:true}).waitFor()
	const expectedEnglishTime = new Intl.DateTimeFormat("en-GB", {hour:"2-digit",minute:"2-digit"}).format(new Date("2026-10-10T17:05:00"))
	assert.equal(await page.locator(".hero-time").innerText(), expectedEnglishTime)
	assert.deepEqual(attendanceActions, ["IN", "OUT"])
	assert.deepEqual(dialogs, [])
	await page.getByText("My Account", {exact:true}).click()
	await Promise.all([
		page.waitForURL("**/login?redirect-to=/attendance"),
		page.getByText("Log out", {exact:true}).click(),
	])
	assert.equal(logoutMethod, "POST")
	console.log("PWA smoke: Short Permission enabled/disabled in Arabic/English, check-in history, attendance actions, navigation and POST logout passed")
} finally {
	await browser.close()
	await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()))
}
