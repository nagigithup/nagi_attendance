import assert from "node:assert/strict";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "../../../pos_next/node_modules/playwright/index.mjs";

const read = relative => fs.readFileSync(new URL(relative, import.meta.url), "utf8");
const source = read("../nagi_attendance/page/manager_attendance/manager_attendance.js");
const css = read("../public/css/nagi_attendance.css");
const jquery = fileURLToPath(new URL("../../../frappe/frappe/public/js/lib/jquery/jquery.min.js", import.meta.url));
const translations = Object.fromEntries(read("../translations/ar.csv").split("\n").flatMap(line => {
  const row = line.match(/^"((?:[^"]|"")*)","((?:[^"]|"")*)"/);
  return row ? [[row[1].replaceAll('""', '"'), row[2].replaceAll('""', '"')]] : [];
}));
const actualData = process.env.NAGI_ACTUAL_INBOX_JSON ? JSON.parse(fs.readFileSync(process.env.NAGI_ACTUAL_INBOX_JSON, "utf8")) : null;
const browser = await chromium.launch({ headless: true });
let scenarios = 0;
try {
  for (const lang of ["en", "ar"]) for (const width of [390, 1440]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("http://manager.test/**", route => route.fulfill({ contentType: "text/html", body: `<html><body style="margin:8px"><div id="page"></div></body></html>` }));
    await page.goto("http://manager.test/desk/manager-attendance");
    await page.addStyleTag({ content: `*{box-sizing:border-box}body{font-family:Arial}.modal{position:fixed;inset:0;overflow:auto;background:#0004;z-index:10;padding:20px}.modal-card{max-width:800px;width:100%;margin:auto;background:white;border-radius:12px;padding:18px}.modal .close{float:right}.btn{padding:6px 10px;border:1px solid #ddd;border-radius:5px}.btn-primary{background:#2f7d65;color:#fff}.btn-default{background:#fff}.modal h2{font-size:18px}.modal [hidden]{display:none}${css}` });
    await page.addScriptTag({ path: jquery });
    await page.evaluate(({ lang, translations, actualData }) => {
      sessionStorage.setItem("nagi-attendance-filters", JSON.stringify({ tab: "leave" }));
      window.__ = (key, args = []) => (lang === "ar" ? translations[key] || key : key).replace(/\{(\d+)\}/g, (_match, i) => args[i]);
      const escape = value => String(value).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
      window.testState = { calls: [], routes: [], messages: [], permission: true, requests: ["LEAVE-A", "LEAVE-B"].map((name, i) => ({ name, employee: "EMP-SELF", employee_name: "Test Employee", company: "Company A", department: "Legal", leave_type: "Sick Leave", from_date: "2026-11-15", to_date: "2026-11-15", total_leave_days: 0.5, half_day: 1, half_day_date: "2026-11-15", description: "<script>window.injected=true</script>Medical appointment", leave_approver: "manager@example.com", leave_approver_name: "Test Manager", status: "Open", docstatus: 0, modified: "2026-10-30 10:00:00", actions: ["Approve", "Reject"] })) };
      const permission = { name: "PERMISSION-A", employee: "EMP-SELF", employee_name: "Test Employee", company: "Company A", department: "Legal", permission_date: "2026-11-17", permission_type: "Temporary Exit", from_time: "10:00", to_time: "11:00", duration_hours: 1, reason: "Appointment", status: "Pending", feature_enabled: true, can_action: true };
      class Dialog {
        constructor(options) {
          this.$wrapper = $(`<div class="modal"><div class="modal-card"><button class="close">×</button><h2></h2><div class="dialog-content"></div></div></div>`).appendTo("body");
          this.fields_dict = { content: { $wrapper: this.$wrapper.find(".dialog-content") } };
          this.set_title(options.title);
          this.$wrapper.find(".close").on("click", () => this.hide());
        }
        set_title(title) { this.$wrapper.find("h2").text(title); }
        show() { this.$wrapper.show(); }
        hide() { this.$wrapper.remove(); }
      }
      window.frappe = {
        realtime: {
          listeners: {},
          on(event, callback) { (this.listeners[event] ||= []).push(callback); },
          off(event, callback) { this.listeners[event] = (this.listeners[event] || []).filter(fn => fn !== callback); },
          emit(event, data) { for (const callback of this.listeners[event] || []) callback(data); },
        },
        pages: { "manager-attendance": {} }, boot: { lang }, user: { has_role: () => false }, defaults: { get_user_default: () => "Company A" },
        ui: { Dialog, make_app_page: () => ({ main: $("#page") }) },
        utils: { escape_html: escape, icon: () => "<svg width='16' height='16'></svg>" },
        datetime: { get_today: () => "2026-10-30", str_to_user: value => value },
        scrub: value => String(value).toLowerCase().replaceAll(" ", "-"),
        set_route: (...args) => { testState.routes.push(args); throw new Error("Desk redirect is forbidden"); },
        confirm: () => { throw new Error("Confirmation popup is forbidden"); },
        msgprint: args => testState.messages.push(args), show_alert: () => {},
        call: async ({ method, args }) => {
          testState.calls.push({ method, args });
          const pending = () => testState.requests.filter(r => r.status === "Open");
          const name = method.split(".").pop();
          if (actualData) {
            if (name === "get_manager_pending_context") return { message: actualData.counts };
            if (name === "get_leave_dashboard") return { message: actualData.leave };
            if (name === "get_leave_details") return { message: actualData.details };
            if (name.startsWith("apply_")) throw new Error("Read-only actual-record replay forbids decisions");
          }
          if (name === "get_dashboard_defaults") return { message: {} };
          if (name === "get_manager_pending_context") return { message: { leave_count: pending().length, short_permission_count: Number(testState.permission), total_pending: pending().length + Number(testState.permission), short_permissions: { visible: true, pending_count: Number(testState.permission), filters: { companies: ["Company A"], departments: ["Legal"], employees: [] } } } };
          if (name === "get_leave_dashboard") return { message: { on_leave: [], upcoming: [], pending: pending() } };
          if (name === "get_leave_details") return { message: { request: testState.requests.find(r => r.name === args.name), actions: testState.requests.find(r => r.name === args.name).status === "Open" ? ["Approve", "Reject"] : [], leave_balance: 12.5 } };
          if (name === "apply_leave_action") {
            await new Promise(resolve => setTimeout(resolve, 80));
            const row = testState.requests.find(r => r.name === args.name);
            if (row.status !== "Open") throw new Error("Already processed");
            row.status = args.action === "Approve" ? "Approved" : "Rejected"; row.docstatus = 1;
            return { message: { name: row.name, status: row.status, docstatus: 1 } };
          }
          if (name === "get_short_permission_dashboard") return { message: { rows: testState.permission ? [permission] : [], summary: { pending: Number(testState.permission) }, total: Number(testState.permission), page: 1, page_length: 20 } };
          if (name === "apply_permission_action") { testState.permission = false; return { message: { status: "Rejected" } }; }
          throw new Error("Unexpected API: " + method);
        },
      };
    }, { lang, translations, actualData });
    await page.addScriptTag({ content: source });
    await page.evaluate(() => frappe.pages["manager-attendance"].on_page_load(document.querySelector("#page")));
    await page.waitForFunction(() => frappe.nagi_attendance.initialized);
    const number = value => new Intl.NumberFormat(lang === "ar" ? "ar" : "en").format(value);
    if (actualData) {
      const row = actualData.details.request;
      assert.equal(await page.locator("[data-total-pending]").textContent(), number(actualData.counts.total_pending));
      assert.equal(await page.locator("[data-leave-count]").textContent(), number(actualData.counts.leave_count));
      await page.locator(`[data-leave-view="${row.name}"]`).click();
      await page.locator(".na-leave-detail").waitFor();
      const content = await page.locator(".na-leave-detail").textContent();
      assert.ok(content.includes(row.employee_name));
      assert.ok(content.includes(row.from_date));
      assert.ok(content.includes(row.to_date));
      assert.ok(content.includes(number(row.total_leave_days)));
      assert.equal(await page.locator(".modal [data-leave-action]").count(), actualData.details.actions.length);
      assert.equal(await page.evaluate(() => testState.calls.filter(c => c.method.includes(".apply_")).length), 0);
      assert.deepEqual(errors, []);
      console.log(`PASS actual assigned inbox ${lang} ${width}px: ${row.name}, ${actualData.counts.leave_count} leave + ${actualData.counts.short_permission_count} Short Permission, read-only details`);
      scenarios++;
      await page.close();
      continue;
    }
    assert.equal(await page.locator("[data-total-pending]").textContent(), number(3));
    assert.equal(await page.locator("[data-leave-count]").textContent(), number(2));
    assert.equal(await page.locator("[data-permission-count]").textContent(), number(1));
    // New requests refresh the badge even before the manager visits Leave.
    const beforeLive = await page.evaluate(() => ({
      context: testState.calls.filter(c => c.method.endsWith("get_manager_pending_context")).length,
      leave: testState.calls.filter(c => c.method.endsWith("get_leave_dashboard")).length,
    }));
    await page.evaluate(() => {
      testState.requests.push({ ...testState.requests[0], name: "LEAVE-LIVE" });
      frappe.nagi_attendance.state.tab = "today";
      for (let i = 0; i < 3; i++) frappe.realtime.emit("hrms:refetch_resource", { cache_key: "hrms:team_leaves" });
    });
    await page.waitForFunction(() => document.querySelector("[data-total-pending]").textContent === "4");
    const afterLive = await page.evaluate(() => ({
      context: testState.calls.filter(c => c.method.endsWith("get_manager_pending_context")).length,
      leave: testState.calls.filter(c => c.method.endsWith("get_leave_dashboard")).length,
    }));
    assert.equal(afterLive.context, beforeLive.context + 1, "a burst must cause one context refresh");
    assert.equal(afterLive.leave, beforeLive.leave, "Today must not load the Leave tab just to count");
    await page.evaluate(() => { frappe.nagi_attendance.state.tab = "leave"; frappe.realtime.emit("notification"); });
    await page.locator('[data-leave-view="LEAVE-LIVE"]').waitFor();
    await page.evaluate(() => { testState.requests.pop(); window.dispatchEvent(new Event("focus")); });
    await page.waitForFunction(() => document.querySelector("[data-total-pending]").textContent === "3" && !document.querySelector('[data-leave-view="LEAVE-LIVE"]'));
    // A slow pre-decision refresh must not overwrite a newer inbox count.
    await page.evaluate(async () => {
      const manager = frappe.nagi_attendance, original = manager.call.bind(manager);
      let release, calls = 0;
      manager.call = async method => {
        if (++calls === 1) return new Promise(resolve => { release = resolve; });
        return original(method);
      };
      const older = manager.refresh_permission_context();
      await manager.refresh_permission_context();
      release({ leave_count: 99, short_permission_count: 0, total_pending: 99, short_permissions: { visible: false, pending_count: 0, filters: {} } });
      await older;
      manager.call = original;
    });
    assert.equal(await page.locator("[data-total-pending]").textContent(), number(3));
    await page.locator('[data-leave-view="LEAVE-A"]').click();
    await page.locator(".na-leave-detail").waitFor();
    assert.equal(await page.locator(".na-leave-detail").getAttribute("dir"), lang === "ar" ? "rtl" : "ltr");
    assert.match(await page.locator(".na-leave-detail").textContent(), /Test Employee/);
    assert.match(await page.locator(".na-leave-detail").textContent(), /Legal/);
    assert.equal(await page.evaluate(() => window.injected), undefined);
    assert.equal(await page.locator(".na-leave-detail textarea, .na-leave-detail input").count(), 0);
    assert.equal(await page.locator(".modal [data-leave-action]").count(), 2);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.equal(await page.locator(".na-leave-detail").evaluate(el => el.scrollWidth <= el.clientWidth), true);
    if (process.env.NAGI_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.NAGI_SCREENSHOT_DIR}/manager-leave-${lang}-${width}.png`, fullPage: true });
    await page.evaluate(() => {
      const button = document.querySelector('.modal [data-leave-action="Approve"]');
      frappe.nagi_attendance.apply_leave_action(button);
      frappe.nagi_attendance.apply_leave_action(button);
    });
    await page.waitForFunction(() => testState.requests[0].status === "Approved" && !frappe.nagi_attendance.leave_actions_busy.size);
    assert.equal(await page.locator("[data-total-pending]").textContent(), number(2));
    assert.equal(await page.locator(".modal [data-leave-action]").count(), 0);
    assert.equal(await page.evaluate(() => testState.calls.filter(c => c.method.endsWith(".apply_leave_action")).length), 1);
    await page.locator(".modal .close").click();
    await page.locator('[data-leave-view="LEAVE-B"]').click();
    await page.locator('.modal [data-leave-action="Reject"]').click();
    await page.waitForFunction(() => testState.requests[1].status === "Rejected" && !frappe.nagi_attendance.leave_actions_busy.size);
    assert.equal(await page.locator("[data-total-pending]").textContent(), number(1));
    assert.equal(await page.locator("[data-leave-count]").isHidden(), true);
    await page.locator(".modal .close").click();
    await page.locator('[data-tab="permissions"]').click();
    await page.locator('[data-permission-action="Reject"]').click();
    await page.waitForFunction(() => !testState.permission && !frappe.nagi_attendance.permission_actions_busy.size);
    assert.equal(await page.locator("[data-pending-notification]").isHidden(), true);
    await page.evaluate(() => frappe.pages["manager-attendance"].on_page_show(document.querySelector("#page")));
    const state = await page.evaluate(() => ({ routes: testState.routes, messages: testState.messages, calls: testState.calls.filter(c => c.method.endsWith(".apply_leave_action")) }));
    assert.deepEqual(state.routes, []);
    assert.deepEqual(state.messages, []);
    assert.deepEqual(state.calls.map(c => Object.keys(c.args).sort()), [["action", "modified", "name"], ["action", "modified", "name"]]);
    assert.deepEqual(errors, []);
    console.log(`PASS manager portal ${lang} ${width}px: details, decisions, repeat guard, counts 3→2→1→0, Short Permission, no redirect/confirmation`);
    scenarios++;
    await page.close();
  }
  assert.equal(scenarios, 4);
} finally { await browser.close(); }
