import { chromium } from "../../../pos_next/node_modules/playwright/index.mjs"
import assert from "node:assert/strict"

const base = "http://127.0.0.1:8001"
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
	let logoutMethod = null
	let nextAction = "IN"
	let lastLog = null
	let includeDailyAttendance = false
	const attendanceActions = []
	const dialogs = []
	page.on("dialog", async dialog => {
		dialogs.push(dialog.type())
		await dialog.dismiss()
	})
	await page.route(`${base}/attendance`, route => route.fulfill({contentType:"text/html",body:`<!doctype html><html lang="ar" dir="rtl"><head><meta name="theme-color" content="#176B5B"><link rel="stylesheet" href="/assets/nagi_attendance/attendance/app.css"><script>window.csrf_token="test"</script><script type="module" src="/assets/nagi_attendance/attendance/app.js"></script></head><body><div id="app"></div></body></html>`}))
	await page.route("**/api/method/nagi_attendance.mobile_api.bootstrap**", route => route.fulfill({contentType:"application/json",body:JSON.stringify({message:{...bootstrap,today:{...bootstrap.today,logs:lastLog?[lastLog]:[],last_log:lastLog,next_action:nextAction,status:nextAction === "IN" ? "Not Checked In" : "Checked In"}}})}))
	await page.route("**/api/method/nagi_attendance.mobile_api.create_checkin", async route => {
		const action = route.request().postDataJSON().log_type
		attendanceActions.push(action)
		await new Promise(resolve => setTimeout(resolve, 200))
		const recordedTime = action === "IN" ? "2026-10-10 09:15:00" : "2026-10-10 17:05:00"
		lastLog = {name:`LOG-${attendanceActions.length}`,log_type:action,time:recordedTime,shift:"09:00–17:00"}
		nextAction = action === "IN" ? "OUT" : "IN"
		return route.fulfill({contentType:"application/json",body:JSON.stringify({message:lastLog})})
	})
	await page.route("**/api/method/nagi_attendance.mobile_api.get_attendance_history**", route => route.fulfill({contentType:"application/json",body:JSON.stringify({message:{events:{},checkins:historyCheckins,records:includeDailyAttendance?dailyAttendance:[]}})}))
	await page.route("**/api/method/logout", route => {
		logoutMethod = route.request().method()
		return route.fulfill({contentType:"application/json",body:JSON.stringify({message:"Logged Out"})})
	})
	await page.goto(`${base}/attendance`)
	await page.waitForSelector(".bottom-nav")
	assert.equal(await page.locator("html").getAttribute("dir"), "rtl")
	assert.match(await page.locator(".brand strong").innerText(), /شركة الاختبار/)
	assert.equal(await page.locator(".bottom-nav button").count(), 4)
	await page.waitForFunction(async () => Boolean(await navigator.serviceWorker.getRegistration("/attendance")))
	await page.waitForFunction(async () => (await caches.keys()).includes("nagi-attendance-shell-v4"))
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
	await page.getByText("حسابي", {exact:true}).click()
	await page.selectOption(".settings select", "en")
	assert.equal(await page.locator("html").getAttribute("dir"), "ltr")
	assert.ok(await page.getByText("My Account", {exact:true}).count() >= 1)
	assert.equal(await page.evaluate(() => document.body.scrollWidth <= window.innerWidth), true)
	await page.getByText("Attendance", {exact:true}).last().click()
	assert.ok(await page.getByText("Check-in activity", {exact:true}).count() >= 1)
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
	console.log("PWA smoke: bilingual check-in history, Arabic Check In, English Check Out, loading lock, no confirmation dialog, navigation and POST logout passed")
} finally {
	await browser.close()
}
