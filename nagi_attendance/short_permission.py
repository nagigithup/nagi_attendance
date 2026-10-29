from __future__ import annotations

from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_datetime, get_time, getdate, now_datetime, today

from nagi_attendance.company import get_company_settings, get_current_employee, require_authenticated_user

PERMISSION_TYPES = {
	"Late Arrival": "allow_late_arrival_permission",
	"Early Departure": "allow_early_departure_permission",
	"Temporary Exit": "allow_temporary_exit_permission",
}
ACTIVE_STATUSES = ("Pending", "Approved")
ADMIN_ROLES = {"System Manager", "HR Manager"}


def _roles(user=None) -> set[str]:
	return set(frappe.get_roles(user or frappe.session.user))


def _is_admin(user=None) -> bool:
	return bool(ADMIN_ROLES & _roles(user))


def _employee_details(employee: str) -> frappe._dict:
	row = frappe.db.get_value(
		"Employee",
		employee,
		["name", "employee_name", "company", "department", "reports_to", "leave_approver", "user_id"],
		as_dict=True,
	)
	if not row or not row.company:
		frappe.throw(_("A valid employee and company are required."))
	return row


def resolve_approver(employee: frappe._dict) -> str:
	if employee.leave_approver and employee.leave_approver != employee.user_id:
		return employee.leave_approver
	if employee.reports_to:
		manager_user = frappe.db.get_value("Employee", employee.reports_to, "user_id")
		if manager_user and manager_user != employee.user_id:
			return manager_user
	frappe.throw(_("No authorized approver is configured for this employee."))


def _interval(permission_date, from_time, to_time) -> tuple[datetime, datetime]:
	start = datetime.combine(getdate(permission_date), get_time(from_time))
	end = datetime.combine(getdate(permission_date), get_time(to_time))
	if end <= start:
		end += timedelta(days=1)
	if end - start >= timedelta(days=1):
		frappe.throw(_("Permission duration must be less than 24 hours."))
	return start, end


def _shift_window(employee: str, start: datetime):
	from hrms.hr.doctype.shift_assignment.shift_assignment import get_employee_shift

	shift = get_employee_shift(employee, start, consider_default_shift=True)
	if not shift:
		# A late-arrival request starts after shift start; reverse resolution is needed
		# when it falls outside the check-in buffer.
		shift = get_employee_shift(
			employee, start, consider_default_shift=True, next_shift_direction="reverse"
		)
	return shift


def _validate_limits(doc, settings, start: datetime, end: datetime):
	hours = (end - start).total_seconds() / 3600
	per_request = flt(settings.maximum_permission_hours_per_request)
	if per_request and hours > per_request:
		frappe.throw(_("Permission duration exceeds the company limit of {0} hours.").format(per_request))
	month_start = getdate(doc.permission_date).replace(day=1)
	month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
	monthly_limit = flt(settings.maximum_permission_hours_per_month)
	if monthly_limit:
		filters = {
			"employee": doc.employee,
			"permission_date": ["between", [month_start, month_end]],
			"status": ["in", ACTIVE_STATUSES],
		}
		if not doc.is_new():
			filters["name"] = ["!=", doc.name]
		used = flt(frappe.db.get_value("Attendance Permission Request", filters, [{"SUM": "duration_hours"}]))
		if used + hours > monthly_limit:
			frappe.throw(_("Monthly permission hours exceed the company limit of {0}.").format(monthly_limit))


def _validate_overlap(doc, start: datetime, end: datetime, settings):
	if not cint(settings.allow_overlapping_permission):
		rows = frappe.get_all(
			"Attendance Permission Request",
			filters={
				"employee": doc.employee,
				"permission_date": doc.permission_date,
				"status": ["in", ACTIVE_STATUSES],
			},
			fields=["name", "from_time", "to_time"],
		)
		for row in rows:
			if row.name == doc.name:
				continue
			other_start, other_end = _interval(doc.permission_date, row.from_time, row.to_time)
			if max(start, other_start) < min(end, other_end):
				frappe.throw(_("This permission overlaps request {0}.").format(row.name))
	if frappe.db.exists(
		"Leave Application",
		{
			"employee": doc.employee,
			"status": "Approved",
			"docstatus": 1,
			"from_date": ["<=", doc.permission_date],
			"to_date": [">=", doc.permission_date],
		},
	):
		frappe.throw(_("An approved leave application already covers this date."))


def _notify(user: str | None, subject: str, docname: str):
	if not user:
		return
	frappe.get_doc(
		{
			"doctype": "Notification Log",
			"for_user": user,
			"subject": subject,
			"type": "Alert",
			"document_type": "Attendance Permission Request",
			"document_name": docname,
		}
	).insert(ignore_permissions=True)


class AttendancePermissionRequest(Document):
	def validate(self):
		if not self.is_new():
			stored = frappe.db.get_value(
				self.doctype,
				self.name,
				[
					"employee",
					"company",
					"approver",
					"status",
					"decision_by",
					"decision_on",
					"manager_comment",
					"cancelled_by",
					"cancelled_on",
				],
				as_dict=True,
			)
			if (
				stored
				and not self.flags.permission_action
				and any(self.get(field) != stored.get(field) for field in stored)
			):
				frappe.throw(
					_("Protected permission fields can only be changed through the approval APIs."),
					frappe.PermissionError,
				)
		employee = _employee_details(self.employee)
		self.company = employee.company
		self.department = employee.department
		self.employee_name = employee.employee_name
		settings = get_company_settings(employee.company)
		if not cint(settings.enable_short_permission):
			frappe.throw(_("Short Permission is disabled for this company."), frappe.PermissionError)
		if self.flags.permission_action and self.status == "Cancelled":
			return
		if self.permission_type not in PERMISSION_TYPES:
			frappe.throw(_("Invalid permission type."))
		if not cint(settings.get(PERMISSION_TYPES[self.permission_type])):
			frappe.throw(_("This permission type is disabled for this company."))
		if cint(settings.require_permission_reason) and not (self.reason or "").strip():
			frappe.throw(_("Permission reason is required."))
		if (
			self.is_new()
			and not cint(settings.allow_retrospective_permission)
			and getdate(self.permission_date) < getdate(today())
		):
			frappe.throw(_("Retrospective permission requests are disabled."))
		start, end = _interval(self.permission_date, self.from_time, self.to_time)
		shift = _shift_window(self.employee, start)
		if get_time(self.to_time) <= get_time(self.from_time) and (
			not shift or shift.end_datetime.date() == shift.start_datetime.date()
		):
			frappe.throw(_("From Time must be earlier than To Time for a same-day shift."))
		if shift and (start < shift.start_datetime or end > shift.end_datetime):
			frappe.throw(_("The permission interval must be within the employee's scheduled shift."))
		self.duration_hours = round((end - start).total_seconds() / 3600, 2)
		_validate_limits(self, settings, start, end)
		_validate_overlap(self, start, end, settings)
		if self.is_new():
			self.approver = resolve_approver(employee)
			self.status = "Pending"

	def before_insert(self):
		user = require_authenticated_user()
		if not _is_admin(user):
			own = get_current_employee(self.company)
			if own.name != self.employee:
				frappe.throw(_("You can only create your own permission request."), frappe.PermissionError)

	def after_insert(self):
		_notify(
			self.approver,
			_("Short Permission request {0} requires your approval.").format(self.name),
			self.name,
		)


def get_permission_query_conditions(user=None):
	user = user or frappe.session.user
	if user == "Administrator" or _is_admin(user):
		return None
	user_sql = frappe.db.escape(user)
	return f"(`tabAttendance Permission Request`.`approver` = {user_sql} OR EXISTS (SELECT 1 FROM `tabEmployee` e WHERE e.name = `tabAttendance Permission Request`.`employee` AND e.user_id = {user_sql}))"


def has_permission(doc, ptype="read", user=None):
	user = user or frappe.session.user
	if user == "Administrator" or _is_admin(user):
		return True
	owner_user = frappe.db.get_value("Employee", doc.employee, "user_id")
	if ptype == "read":
		return user in {owner_user, doc.approver}
	if ptype == "create":
		return user == owner_user
	return False


def _ensure_enabled(company: str):
	settings = get_company_settings(company)
	if not cint(settings.enable_short_permission):
		frappe.throw(_("Short Permission is disabled for this company."), frappe.PermissionError)
	return settings


@frappe.whitelist(methods=["POST"])
def create_permission_request(
	permission_date, permission_type, from_time, to_time, reason=None, company=None
):
	employee = get_current_employee(company)
	_ensure_enabled(employee.company)
	doc = frappe.get_doc(
		{
			"doctype": "Attendance Permission Request",
			"employee": employee.name,
			"permission_date": permission_date,
			"permission_type": permission_type,
			"from_time": from_time,
			"to_time": to_time,
			"reason": reason,
		}
	).insert()
	return {"name": doc.name, "status": doc.status, "duration_hours": doc.duration_hours}


@frappe.whitelist()
def get_permission_dashboard(company=None):
	employee = get_current_employee(company)
	_ensure_enabled(employee.company)
	fields = [
		"name",
		"employee",
		"employee_name",
		"permission_date",
		"permission_type",
		"from_time",
		"to_time",
		"duration_hours",
		"reason",
		"approver",
		"status",
		"manager_comment",
	]
	mine = frappe.get_list(
		"Attendance Permission Request",
		filters={"employee": employee.name, "company": employee.company},
		fields=fields,
		order_by="permission_date desc",
		limit=100,
	)
	pending = frappe.get_list(
		"Attendance Permission Request",
		filters={"approver": frappe.session.user, "company": employee.company, "status": "Pending"},
		fields=fields,
		order_by="permission_date asc",
		limit=100,
	)
	return {"requests": mine, "pending_approvals": pending}


@frappe.whitelist(methods=["POST"])
def apply_permission_action(name, action, manager_comment=None):
	user = require_authenticated_user()
	# Serialize decisions for one request. A second concurrent click/request waits,
	# reloads the committed status, and is rejected by the Pending check below.
	doc = frappe.get_doc("Attendance Permission Request", name, for_update=True)
	_ensure_enabled(doc.company)
	if doc.status != "Pending" or action not in {"Approve", "Reject"}:
		frappe.throw(_("This approval action is not available."))
	if user == frappe.db.get_value("Employee", doc.employee, "user_id"):
		frappe.throw(_("Employees cannot approve their own permission requests."), frappe.PermissionError)
	if user != doc.approver and not _is_admin(user):
		frappe.throw(_("You are not authorized to approve this request."), frappe.PermissionError)
	# Recheck current company limits and conflicts at approval time.
	doc.validate()
	doc.flags.permission_action = True
	doc.status = "Approved" if action == "Approve" else "Rejected"
	doc.manager_comment = (manager_comment or "").strip() or None
	doc.decision_by = user
	doc.decision_on = now_datetime()
	doc.save(ignore_permissions=True, ignore_version=False)
	_notify(
		frappe.db.get_value("Employee", doc.employee, "user_id"),
		_("Short Permission request {0} was {1}.").format(doc.name, doc.status),
		doc.name,
	)
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def cancel_permission_request(name, company=None):
	employee = get_current_employee(company)
	doc = frappe.get_doc("Attendance Permission Request", name)
	_ensure_enabled(employee.company)
	if doc.employee != employee.name or doc.company != employee.company or doc.status not in ACTIVE_STATUSES:
		frappe.throw(_("You cannot cancel this permission request."), frappe.PermissionError)
	doc.flags.permission_action = True
	doc.status = "Cancelled"
	doc.cancelled_by = frappe.session.user
	doc.cancelled_on = now_datetime()
	doc.save(ignore_permissions=True, ignore_version=False)
	_notify(doc.approver, _("Short Permission request {0} was cancelled.").format(doc.name), doc.name)
	return {"name": doc.name, "status": doc.status}


def worked_intervals_from_logs(logs, check_in_out_type: str, calculation_type: str):
	logs = sorted(logs, key=lambda row: get_datetime(row.time))
	if len(logs) < 2:
		return []
	if calculation_type == "First Check-in and Last Check-out":
		if check_in_out_type == "Strictly based on Log Type in Employee Checkin":
			first = next((row for row in logs if row.log_type == "IN"), None)
			last = next((row for row in reversed(logs) if row.log_type == "OUT"), None)
		else:
			first, last = logs[0], logs[-1]
		return (
			[(get_datetime(first.time), get_datetime(last.time))]
			if first and last and first.time < last.time
			else []
		)
	if check_in_out_type == "Strictly based on Log Type in Employee Checkin":
		intervals, open_in = [], None
		for row in logs:
			if row.log_type == "IN" and open_in is None:
				open_in = get_datetime(row.time)
			elif row.log_type == "OUT" and open_in is not None:
				out_time = get_datetime(row.time)
				if open_in < out_time:
					intervals.append((open_in, out_time))
				open_in = None
		return intervals
	return [
		(get_datetime(logs[index].time), get_datetime(logs[index + 1].time))
		for index in range(0, len(logs) - 1, 2)
		if get_datetime(logs[index].time) < get_datetime(logs[index + 1].time)
	]


def _merge_intervals(intervals):
	merged = []
	for start, end in sorted(intervals):
		if merged and start <= merged[-1][1]:
			merged[-1] = (merged[-1][0], max(merged[-1][1], end))
		else:
			merged.append((start, end))
	return merged


def _interval_hours(intervals) -> float:
	return sum((end - start).total_seconds() for start, end in intervals) / 3600


def approved_permission_hours(
	employee: str,
	shift_start: datetime,
	shift_end: datetime,
	worked_intervals=None,
):
	company = frappe.db.get_value("Employee", employee, "company", cache=True)
	settings = get_company_settings(company) if company else frappe._dict()
	if not cint(settings.get("enable_short_permission")) or not cint(
		settings.get("permission_counted_as_authorized_working_time")
	):
		return frappe._dict(hours=0.0, approved_hours=0.0, covers_start=False, covers_end=False)
	rows = frappe.get_all(
		"Attendance Permission Request",
		filters={
			"employee": employee,
			"permission_date": getdate(shift_start),
			"status": "Approved",
		},
		fields=["from_time", "to_time"],
	)
	intervals = []
	for row in rows:
		start, end = _interval(getdate(shift_start), row.from_time, row.to_time)
		start, end = max(start, shift_start), min(end, shift_end)
		if start < end:
			intervals.append((start, end))
	merged = _merge_intervals(intervals)
	worked = _merge_intervals(
		[
			(max(start, shift_start), min(end, shift_end))
			for start, end in (worked_intervals or [])
			if max(start, shift_start) < min(end, shift_end)
		]
	)
	overlap = []
	for permission_start, permission_end in merged:
		for worked_start, worked_end in worked:
			start, end = max(permission_start, worked_start), min(permission_end, worked_end)
			if start < end:
				overlap.append((start, end))
	approved_hours = _interval_hours(merged)
	return frappe._dict(
		hours=max(0.0, approved_hours - _interval_hours(_merge_intervals(overlap))),
		approved_hours=approved_hours,
		covers_start=any(start <= shift_start < end for start, end in merged),
		covers_end=any(start < shift_end <= end for start, end in merged),
	)
