import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync(
	new URL("../nagi_attendance/page/manager_attendance/manager_attendance.js", import.meta.url),
	"utf8"
);
const context = {
	frappe: {
		pages: { "manager-attendance": {} },
		defaults: { get_user_default: () => "Company A" },
	},
	console,
};
vm.createContext(context);
vm.runInContext(`${source}\nglobalThis.ManagerAttendance = NagiAttendance;`, context);

const prototype = context.ManagerAttendance.prototype;

const configured = {
	state: { department: "" },
	call: async () => ({ default_reporting_department: "Legal - A" }),
	persist_state() { this.persisted = true; },
	render_filters() { this.rendered = true; },
	load_active() { this.loaded = true; },
};
await prototype.initialize.call(configured);
assert.equal(configured.state.department, "Legal - A");
assert.equal(configured.persisted, true);
assert.equal(configured.rendered, true);
assert.equal(configured.loaded, true);

const empty = {
	state: { department: "Chosen - A" },
	call: async () => ({ default_reporting_department: null }),
	persist_state() { throw new Error("empty default must not overwrite state"); },
	render_filters() { throw new Error("empty default must preserve existing filters"); },
	load_active() { this.loaded = true; },
};
await prototype.initialize.call(empty);
assert.equal(empty.state.department, "Chosen - A");
assert.equal(empty.loaded, true);

const requests = [];
const scoped = {
	state: {
		date: "2026-10-10",
		year: 2026,
		month: 10,
		employee: "",
		department: "Legal - A",
	},
	loading() {},
	async call(method, args) {
		requests.push({ method, args });
		return method === "get_today_dashboard" ? { filters: { employees: [], departments: [] } } : {};
	},
	populate_filter_options() {},
	render_today() {},
	render_monthly() {},
	render_leave() {},
	render_error(error) { throw error; },
};
await prototype.load_today.call(scoped);
await prototype.load_monthly.call(scoped);
await prototype.load_leave.call(scoped);
assert.deepEqual(
	requests.map(({ method, args }) => [method, args.department]),
	[
		["get_today_dashboard", "Legal - A"],
		["get_monthly_attendance", "Legal - A"],
		["get_leave_dashboard", "Legal - A"],
	]
);

scoped.state.department = "Operations - A";
await prototype.load_today.call(scoped);
assert.equal(requests.at(-1).args.department, "Operations - A");

console.log("manager attendance default-department and filter smoke tests passed");
