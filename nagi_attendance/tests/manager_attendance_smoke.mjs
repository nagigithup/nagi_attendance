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
	async refresh_permission_context() { this.permissionContextLoaded = true; },
	load_active() { this.loaded = true; },
};
await prototype.initialize.call(configured);
assert.equal(configured.state.department, "Legal - A");
assert.equal(configured.persisted, true);
assert.equal(configured.rendered, true);
assert.equal(configured.permissionContextLoaded, true);
assert.equal(configured.loaded, true);

const empty = {
	state: { department: "Chosen - A" },
	call: async () => ({ default_reporting_department: null }),
	persist_state() { throw new Error("empty default must not overwrite state"); },
	render_filters() { throw new Error("empty default must preserve existing filters"); },
	async refresh_permission_context() { this.permissionContextLoaded = true; },
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
		permission_company: "Company A",
		permission_from: "2026-10-01",
		permission_to: "2026-10-31",
		permission_status: "Pending",
		permission_type: "Temporary Exit",
		permission_page: 2,
	},
	permission_context: { visible: true },
	loading() {},
	async call(method, args) {
		requests.push({ method, args });
		return method === "get_today_dashboard" ? { filters: { employees: [], departments: [] } } : {};
	},
	populate_filter_options() {},
	render_today() {},
	render_monthly() {},
	render_leave() {},
	render_permissions() {},
	render_error(error) { throw error; },
};
await prototype.load_today.call(scoped);
await prototype.load_monthly.call(scoped);
await prototype.load_leave.call(scoped);
await prototype.load_permissions.call(scoped);
assert.deepEqual(
	requests.map(({ method, args }) => [method, args.department]),
	[
		["get_today_dashboard", "Legal - A"],
		["get_monthly_attendance", "Legal - A"],
		["get_leave_dashboard", "Legal - A"],
		["get_short_permission_dashboard", "Legal - A"],
	]
);
assert.deepEqual(JSON.parse(JSON.stringify(requests[3].args)), {
	company: "Company A",
	department: "Legal - A",
	employee: "",
	from_date: "2026-10-01",
	to_date: "2026-10-31",
	status: "Pending",
	permission_type: "Temporary Exit",
	page: 2,
	page_length: 20,
});

scoped.state.department = "Operations - A";
await prototype.load_today.call(scoped);
assert.equal(requests.at(-1).args.department, "Operations - A");

console.log("manager attendance default-department and filter smoke tests passed");
