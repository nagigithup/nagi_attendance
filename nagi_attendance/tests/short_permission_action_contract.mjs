import assert from "node:assert/strict";
import fs from "node:fs";

const managerSource = fs.readFileSync(
	new URL("../nagi_attendance/page/manager_attendance/manager_attendance.js", import.meta.url),
	"utf8"
);
const mobileSource = fs.readFileSync(new URL("../../frontend/src/App.vue", import.meta.url), "utf8");

const managerHandler = managerSource.match(
	/this\.\$root\.on\("click", "\[data-permission-action\]",[\s\S]*?\n\t\t\}\);/
)?.[0];
assert.ok(managerHandler, "manager permission action handler is missing");
assert.ok(managerHandler.includes("this.apply_permission_action(event.currentTarget)"));
assert.ok(!managerHandler.includes("open_permission"), "actions must not open the details dialog");

const managerAction = managerSource.match(
	/async apply_permission_action\(button\) \{[\s\S]*?\n\t\}/
)?.[0];
assert.ok(managerAction, "direct manager action is missing");
assert.ok(managerAction.includes("permission_actions_busy.has(name)"));
assert.ok(managerAction.includes('$buttons.prop("disabled", true)'));
assert.ok(managerAction.includes('args: { name, action }'));
assert.ok(managerAction.includes('await this.load_permissions()'));
assert.ok(!managerAction.includes("manager_comment"));
assert.ok(!managerAction.includes("frappe.confirm"));

const mobileAction = mobileSource.match(
	/async function permissionAction\([\s\S]*?\n/
)?.[0];
assert.ok(mobileAction, "mobile permission action is missing");
assert.ok(!mobileAction.includes("confirm("), "mobile permission decisions must be one click");
assert.ok(mobileAction.includes("if(busy.value)return"));
assert.ok(mobileAction.includes("await load()"));

console.log("Short Permission direct action contract passed for Desk and Vue");
