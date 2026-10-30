"""Shared native HRMS leave decisions for the manager portal and employee PWA."""

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name
from frappe.utils import get_datetime


def is_assigned_approver(doc) -> bool:
	return bool(
		doc.leave_approver
		and doc.leave_approver == frappe.session.user
		and frappe.db.get_value("Employee", doc.employee, "user_id") != frappe.session.user
	)


def check_leave_scope(doc):
	doc.check_permission("read")
	if (
		doc.company != frappe.db.get_value("Employee", doc.employee, "company")
		or not frappe.has_permission("Company", "read", doc.company)
	):
		frappe.throw(_("You are not authorized to access this leave request."), frappe.PermissionError)


def leave_actions(doc) -> list[str]:
	if doc.docstatus != 0 or doc.status != "Open" or not is_assigned_approver(doc):
		return []
	try:
		check_leave_scope(doc)
		if not doc.has_permission("write"):
			return []
		if get_workflow_name("Leave Application"):
			# Employee submission/edit transitions are not manager approval actions.
			# This keeps a configured authoring Draft out of the approval inbox.
			return list(dict.fromkeys(
				row.action for row in get_transitions(doc)
				if row.allowed not in {"Employee", "Employee Self Service"}
			))
		return ["Approve", "Reject"] if doc.has_permission("submit") else []
	except (frappe.PermissionError, frappe.ValidationError):
		return []


def decide_leave(name: str, action: str, modified: str | None = None) -> dict:
	# Lock before loading status/workflow state. Concurrent decisions must recheck
	# the current row after the first transaction has finished.
	doc = frappe.get_doc("Leave Application", name, for_update=True)
	check_leave_scope(doc)
	doc.check_permission("write")
	if modified and get_datetime(modified) != get_datetime(doc.modified):
		frappe.throw(_("This leave request changed. Reload it before taking action."), frappe.TimestampMismatchError)
	if action not in leave_actions(doc):
		frappe.throw(_("This approval action is not available to you."), frappe.PermissionError)
	if get_workflow_name("Leave Application"):
		doc = apply_workflow(doc, action)
	else:
		doc.check_permission("submit")
		doc.status = {"Approve": "Approved", "Reject": "Rejected"}[action]
		doc.save()
		doc.submit()
		# Preserve the authenticated manager in the native document timeline.
		doc.add_comment("Info", _(doc.status))
	return {"name": doc.name, "status": doc.status, "docstatus": doc.docstatus}


def notify_leave_approvers(doc, method=None):
	"""Invalidate only approver inboxes, after the native transaction commits."""
	from hrms import refetch_resource

	users = {doc.leave_approver}
	before = doc.get_doc_before_save()
	if before:
		users.add(before.leave_approver)
	employee_user = frappe.db.get_value("Employee", doc.employee, "user_id")
	for user in users:
		if user and user != employee_user:
			refetch_resource("hrms:team_leaves", user=user)
