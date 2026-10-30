import assert from "node:assert/strict";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "../../../pos_next/node_modules/playwright/index.mjs";

const root = fileURLToPath(new URL("../public/attendance/", import.meta.url));
const entry = JSON.parse(fs.readFileSync(root + "asset-manifest.json", "utf8"))["src/main.js"];
const browser = await chromium.launch({ headless: true });
let checks = 0;
try {
  for (const lang of ["ar", "en"]) {
    const context = await browser.newContext({ serviceWorkers: "block", viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    let succeed = false, posts = 0;
    const message = lang === "ar" ? "نوع الإجازة هذا غير متاح للتاريخ المحدد." : "This leave type is not available for the selected date.";
    await page.addInitScript(value => localStorage.setItem("nagi-language", value), lang);
    await page.route("http://leave.test/**", async route => {
      const url = new URL(route.request().url());
      if (url.pathname === "/attendance") return route.fulfill({ contentType: "text/html", body: `<meta name="theme-color" content="#176B5B"><div id="app"></div><script>window.csrf_token="test"</script><script type="module" src="/assets/${entry.file}"></script>` });
      if (url.pathname.startsWith("/assets/")) return route.fulfill({ path: root + url.pathname.split("/").pop(), contentType: url.pathname.endsWith(".js") ? "application/javascript" : "text/css" });
      if (url.pathname.endsWith("bootstrap")) {
        assert.equal(url.searchParams.get("_lang"), lang);
        return route.fulfill({ json: { message: {
          employee: { name: "EMP-SELF", employee_name: "Test Employee", company: "Company A" },
          company: { name: "Company A", default_language: "ar", primary_color: "#176B5B" }, companies: [], settings: {}, today: null,
          leave: { types: ["Sick Leave"], balances: {}, upcoming: [], pending_approvals: [], applications: succeed ? [{ name: "LEAVE-SELF", leave_type: "Sick Leave", status: "Open", docstatus: 0, from_date: "2026-11-08", to_date: "2026-11-08", total_leave_days: 1 }] : [] }
        } } });
      }
      if (url.pathname.endsWith("create_leave_application")) {
        const args = route.request().postDataJSON();
        assert.equal(args._lang, lang);
        assert.equal(args.company, "Company A");
        assert.equal(args.employee, undefined);
        posts++;
        if (!succeed) return route.fulfill({ status: 417, json: { exc_type: "ValidationError", _server_messages: JSON.stringify([JSON.stringify({ message })]) } });
        return route.fulfill({ json: { message: { name: "LEAVE-SELF", status: "Open", docstatus: 0 } } });
      }
      throw new Error("Unexpected request: " + url);
    });
    await page.goto("http://leave.test/attendance");
    await page.locator(".bottom-nav button").nth(2).click();
    await page.locator("form select").selectOption("Sick Leave");
    await page.locator('input[type="date"]').nth(0).fill("2026-11-08");
    await page.locator('input[type="date"]').nth(1).fill("2026-11-08");
    await page.locator("form button.primary").click();
    await page.waitForFunction(text => document.querySelector(".toast.error")?.textContent === text, message);
    assert.equal(await page.locator(".app-shell").getAttribute("dir"), lang === "ar" ? "rtl" : "ltr");
    succeed = true;
    await page.locator("form button.primary").click();
    await page.locator(".leave-list .leave-row").waitFor();
    assert.equal(await page.locator(".badge.open").textContent(), lang === "ar" ? "مفتوح" : "Open");
    assert.equal(posts, 2);
    assert.deepEqual(errors, []);
    checks++;
    await context.close();
  }
  console.log(`PASS: ${checks} PWA language flows; localized errors, Open history, selected _lang and employee scope`);
} finally { await browser.close(); }
