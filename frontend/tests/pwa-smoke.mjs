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

const browser = await chromium.launch({headless:true})
try {
	const page = await browser.newPage({viewport:{width:390,height:844},isMobile:true})
	await page.route(`${base}/attendance`, route => route.fulfill({contentType:"text/html",body:`<!doctype html><html lang="ar" dir="rtl"><head><meta name="theme-color" content="#176B5B"><link rel="stylesheet" href="/assets/nagi_attendance/attendance/app.css"><script>window.csrf_token="test"</script><script type="module" src="/assets/nagi_attendance/attendance/app.js"></script></head><body><div id="app"></div></body></html>`}))
	await page.route("**/api/method/nagi_attendance.mobile_api.bootstrap**", route => route.fulfill({contentType:"application/json",body:JSON.stringify({message:bootstrap})}))
	await page.route("**/api/method/nagi_attendance.mobile_api.get_attendance_history**", route => route.fulfill({contentType:"application/json",body:JSON.stringify({message:{events:{},records:[]}})}))
	await page.goto(`${base}/attendance`)
	await page.waitForSelector(".bottom-nav")
	assert.equal(await page.locator("html").getAttribute("dir"), "rtl")
	assert.match(await page.locator(".brand strong").innerText(), /شركة الاختبار/)
	assert.equal(await page.locator(".bottom-nav button").count(), 4)
	await page.waitForFunction(async () => Boolean(await navigator.serviceWorker.getRegistration("/attendance")))
	await page.getByText("حسابي", {exact:true}).click()
	await page.selectOption(".settings select", "en")
	assert.equal(await page.locator("html").getAttribute("dir"), "ltr")
	assert.ok(await page.getByText("My Account", {exact:true}).count() >= 1)
	assert.equal(await page.evaluate(() => document.body.scrollWidth <= window.innerWidth), true)
	console.log("PWA smoke: mobile render, company branding, four-tab navigation, RTL/LTR and viewport passed")
} finally {
	await browser.close()
}
