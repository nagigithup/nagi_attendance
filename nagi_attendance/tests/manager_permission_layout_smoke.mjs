import assert from "node:assert/strict";
import fs from "node:fs";

import { chromium } from "../../../pos_next/node_modules/playwright/index.mjs";

const css = fs.readFileSync(
	new URL("../public/css/nagi_attendance.css", import.meta.url),
	"utf8"
);
const arabicTranslations = fs.readFileSync(
	new URL("../translations/ar.csv", import.meta.url),
	"utf8"
);

for (const translation of [
	'"Pending","بانتظار الموافقة"',
	'"Approved","تمت الموافقة"',
	'"Rejected","مرفوض"',
	'"Cancelled","ملغي"',
	'"{0} hour","{0} ساعة"',
	'"{0} hours","{0} ساعات"',
	'"No permission requests","لا توجد طلبات إذن"',
	'"Clear filters","مسح عوامل التصفية"',
]) {
	assert.ok(arabicTranslations.includes(translation), `missing Arabic translation: ${translation}`);
}

const icon = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"></circle></svg>';
const filters = Array.from(
	{ length: 7 },
	(_, index) => `<label>Filter ${index + 1}<select><option>Value</option></select></label>`
).join("");
const cards = ["pending", "approved", "rejected", "approved_hours"]
	.map(
		(status) => `<article class="na-permission-stat na-permission-stat-${status}">
		<span class="na-permission-stat-icon">${icon}</span><div><span>Summary label</span><strong>12</strong></div>
	</article>`
	)
	.join("");
const headers = ["Employee", "Company", "Date", "Type", "Time", "Duration", "Reason", "Status", "Actions"]
	.map((label) => `<th>${label}</th>`)
	.join("");

function documentMarkup(direction) {
	return `<!doctype html><html dir="${direction}"><head><style>body{margin:0}${css}</style></head><body>
		<main class="nagi-attendance" dir="${direction}">
			<section class="na-filters na-permission-filters">${filters}</section>
			<section class="na-view"><div class="na-permission-stats">${cards}</div>
				<section class="na-panel na-permission-panel"><div class="na-panel-head"><h3>Requests</h3></div>
					<div class="na-permission-table-wrap"><table class="na-permission-table"><thead><tr>${headers}</tr></thead>
					<tbody><tr class="na-permission-row"><td><button class="na-permission-person"><strong>Employee</strong><small>EMP-1</small></button></td><td><div class="na-permission-company"><strong>Company</strong><small>Department</small></div></td><td>2026-10-14</td><td>Type</td><td class="na-time">09:00 – 10:00</td><td>1 hour</td><td><span class="na-reason">A long reason</span></td><td><span class="na-badge status-pending">Pending</span></td><td><div class="na-permission-actions"><button>Approve</button><button>Reject</button></div></td></tr></tbody></table></div>
				</section>
			</section>
		</main></body></html>`;
}

const scenarios = [
	{ width: 1920, cards: 4, filters: 7 },
	{ width: 1440, cards: 4, filters: 7 },
	{ width: 1024, cards: 2, filters: 4 },
	{ width: 768, cards: 2, filters: 2 },
	{ width: 390, cards: 1, filters: 1 },
];

const browser = await chromium.launch({ headless: true });
try {
	for (const direction of ["rtl", "ltr"]) {
		for (const scenario of scenarios) {
			const page = await browser.newPage({ viewport: { width: scenario.width, height: 900 } });
			await page.setContent(documentMarkup(direction));
			const layout = await page.evaluate(() => {
				const columns = (selector) => getComputedStyle(document.querySelector(selector)).gridTemplateColumns.split(" ").length;
				const wrapper = document.querySelector(".na-permission-table-wrap");
				const tableHeaders = [...document.querySelectorAll(".na-permission-table th")];
				return {
					cardColumns: columns(".na-permission-stats"),
					filterColumns: columns(".na-permission-filters"),
					bodyFits: document.documentElement.scrollWidth <= window.innerWidth,
					tableContained: wrapper.scrollWidth >= wrapper.clientWidth,
					firstHeaderX: tableHeaders[0].getBoundingClientRect().x,
					lastHeaderX: tableHeaders.at(-1).getBoundingClientRect().x,
				};
			});
			assert.equal(layout.cardColumns, scenario.cards, `${direction} cards at ${scenario.width}px`);
			assert.equal(layout.filterColumns, scenario.filters, `${direction} filters at ${scenario.width}px`);
			assert.equal(layout.bodyFits, true, `${direction} page overflow at ${scenario.width}px`);
			assert.equal(layout.tableContained, true);
			assert.equal(
				direction === "rtl" ? layout.firstHeaderX > layout.lastHeaderX : layout.firstHeaderX < layout.lastHeaderX,
				true,
				`${direction} table order at ${scenario.width}px`
			);
			await page.close();
		}
	}

	const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
	await page.setContent(documentMarkup("rtl"));
	await page.locator(".na-permission-table-wrap").evaluate((element) => {
		element.outerHTML = '<div class="na-permission-empty"><h4>لا توجد طلبات إذن</h4><p>لا توجد طلبات تطابق عوامل التصفية الحالية.</p><button data-clear-permission-filters>مسح عوامل التصفية</button></div>';
	});
	assert.equal(await page.locator(".na-permission-table").count(), 0);
	assert.equal(await page.locator("[data-clear-permission-filters]").isVisible(), true);
	assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
	await page.screenshot({ path: "/tmp/nagi-short-permission-rtl-390.png", fullPage: true });
	await page.close();

	console.log("manager Short Permission responsive RTL/LTR layout smoke passed at 1920, 1440, 1024, 768 and 390px");
} finally {
	await browser.close();
}
