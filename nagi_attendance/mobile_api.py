from __future__ import annotations

from datetime import datetime, time

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, get_datetime, getdate, now_datetime, today

from nagi_attendance.company import (
	company_brand,
	get_company_settings,
	get_current_employee,
	get_user_employees,
	require_authenticated_user,
)
from nagi_attendance.short_permission import (
	apply_permission_action,
	cancel_permission_request,
	create_permission_request,
	get_permission_dashboard,
)


def _day_bounds(value):
	value = getdate(value)
	return datetime.combine(value, time.min), datetime.combine(value, time.max)


def _normalize_log_type(value) -> str:
	return str(value or "").strip().upper()


def _next_checkin_action(last) -> str:
	return "OUT" if last and _normalize_log_type(last.log_type) == "IN" else "IN"


def _attendance_window(employee: str, value) -> frappe._dict:
	from hrms.hr.doctype.shift_assignment.shift_assignment import get_actual_start_end_datetime_of_shift

	value = get_datetime(value)
	shift = get_actual_start_end_datetime_of_shift(employee, value, consider_default_shift=True)
	if shift:
		return frappe._dict(
			start=shift.actual_start,
			end=shift.actual_end,
			attendance_date=getdate(shift.start_datetime),
		)
	start, end = _day_bounds(value)
	return frappe._dict(start=start, end=end, attendance_date=getdate(value))


def _attendance_state(employee: str, value, *, for_update: bool = False) -> frappe._dict:
	window = _attendance_window(employee, value)
	last = frappe.db.get_value(
		"Employee Checkin",
		{"employee": employee, "time": ("between", [window.start, window.end])},
		["name", "log_type", "time"],
		as_dict=True,
		order_by="time desc, creation desc, name desc",
		for_update=for_update,
	)
	return frappe._dict(window=window, last=last, next_action=_next_checkin_action(last))


def _settings_payload(settings) -> dict:
	effective_gps = bool(
		settings.enable_gps_validation
		or frappe.db.get_single_value("HR Settings", "allow_geolocation_tracking")
	)
	return {
		"enable_mobile_attendance": bool(settings.enable_mobile_attendance),
		"enable_mobile_leave": bool(settings.enable_mobile_leave),
		"allow_attendance_history": bool(settings.allow_attendance_history),
		"enable_gps_validation": effective_gps,
		"attendance_start_date": str(settings.attendance_start_date)
		if settings.attendance_start_date
		else None,
		"enable_short_permission": bool(settings.enable_short_permission),
	}


def _active_shift(employee: frappe._dict, value=None) -> frappe._dict | None:
	value = getdate(value or today())
	assignments = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": employee.name,
			"start_date": ("<=", value),
			"docstatus": 1,
			"status": "Active",
		},
		or_filters=[["end_date", ">=", value], ["end_date", "is", "not set"]],
		fields=["shift_type", "shift_location", "start_date", "end_date"],
		order_by="start_date desc",
		limit=1,
	)
	assignment = assignments[0] if assignments else None
	shift_name = assignment.shift_type if assignment else employee.default_shift
	if not shift_name:
		return None
	shift = frappe.db.get_value(
		"Shift Type",
		shift_name,
		["name", "start_time", "end_time", "enable_late_entry_marking", "late_entry_grace_period"],
		as_dict=True,
	)
	if shift:
		shift["location"] = assignment.shift_location if assignment else None
		shift["start_time"] = str(shift.start_time) if shift.start_time is not None else None
		shift["end_time"] = str(shift.end_time) if shift.end_time is not None else None
	return shift


def _today_summary(employee: frappe._dict) -> dict:
	server_time = now_datetime()
	value = getdate(server_time)
	state = _attendance_state(employee.name, server_time)
	attendance = frappe.get_list(
		"Attendance",
		filters={"employee": employee.name, "attendance_date": state.window.attendance_date, "docstatus": 1},
		fields=[
			"name",
			"status",
			"in_time",
			"out_time",
			"working_hours",
			"late_entry",
			"early_exit",
			"shift",
		],
		limit=1,
	)
	logs = frappe.get_list(
		"Employee Checkin",
		filters={"employee": employee.name, "time": ["between", [state.window.start, state.window.end]]},
		fields=["name", "time", "log_type", "shift", "latitude", "longitude"],
		order_by="time asc, creation asc, name asc",
		limit_page_length=0,
	)
	row = attendance[0] if attendance else None
	last = next((log for log in reversed(logs) if state.last and log.name == state.last.name), state.last)
	next_action = state.next_action
	status = row.status if row else ("Checked In" if next_action == "OUT" else "Not Checked In")
	return {
		"date": str(value),
		"status": status,
		"attendance": row,
		"logs": logs,
		"last_log": last,
		"next_action": next_action,
		"shift": _active_shift(employee, state.window.attendance_date),
	}


def _leave_data(employee: frappe._dict, include_pending_approvals: bool = True) -> dict:
	from hrms.api import get_leave_applications
	from hrms.hr.doctype.leave_application.leave_application import get_leave_details

	result = {"balances": {}, "types": [], "applications": [], "upcoming": [], "configuration_error": None}
	try:
		details = get_leave_details(employee.name, getdate(today()))
		result["balances"] = {
			leave_type: {
				"allocated_leaves": values.get("total_leaves"),
				"balance_leaves": values.get("remaining_leaves"),
			}
			for leave_type, values in details["leave_allocation"].items()
		}
		result["types"] = list(details["leave_allocation"].keys()) + details["lwps"]
	except (frappe.PermissionError, frappe.ValidationError) as exc:
		result["configuration_error"] = str(exc)
	result["applications"] = get_leave_applications(employee.name, limit=50)
	result["upcoming"] = [
		row
		for row in result["applications"]
		if row.status == "Approved" and getdate(row.to_date) >= getdate(today())
	][:5]
	result["pending_approvals"] = _pending_approvals(employee) if include_pending_approvals else []
	return result


def _pending_approvals(employee: frappe._dict) -> list[dict]:
	from hrms.api import get_leave_applications

	try:
		rows = get_leave_applications(employee.name, frappe.session.user, True, 50)
	except (frappe.PermissionError, frappe.ValidationError):
		return []
	result = []
	for row in rows:
		if row.employee == employee.name:
			continue
		if frappe.db.get_value("Employee", row.employee, "company", cache=True) != employee.company:
			continue
		doc = frappe.get_doc("Leave Application", row.name)
		actions = _approval_actions(doc)
		if actions:
			row["actions"] = actions
			result.append(row)
	return result


@frappe.whitelist()
def bootstrap(company: str | None = None):
	user = require_authenticated_user()
	employee = get_current_employee(company)
	settings = get_company_settings(employee.company)
	companies = []
	seen = set()
	for row in get_user_employees(user):
		if row.company not in seen:
			seen.add(row.company)
			companies.append(company_brand(row.company))
	result = {
		"user": user,
		"employee": employee,
		"company": company_brand(employee.company),
		"companies": companies,
		"settings": _settings_payload(settings),
		"today": _today_summary(employee) if settings.enable_mobile_attendance else None,
		"leave": _leave_data(employee) if settings.enable_mobile_leave else None,
		"languages": ["ar", "en"],
	}
	if settings.enable_short_permission:
		from nagi_attendance.short_permission import get_permission_dashboard

		result["short_permission"] = get_permission_dashboard(employee.company)
	return result


@frappe.whitelist()
def get_attendance_history(
	company: str | None = None, from_date: str | None = None, to_date: str | None = None
):
	employee = get_current_employee(company)
	settings = get_company_settings(employee.company)
	if not settings.enable_mobile_attendance or not settings.allow_attendance_history:
		frappe.throw(_("Attendance history is disabled for this company."), frappe.PermissionError)
	end = getdate(to_date or today())
	start = getdate(from_date or add_months(end, -1))
	if start > end:
		frappe.throw(_("From Date cannot be after To Date."))
	if (end - start).days > 370:
		frappe.throw(_("Attendance history is limited to 12 months per request."))
	from hrms.api import get_attendance_for_calendar, get_holidays_for_calendar

	attendance = get_attendance_for_calendar(employee.name, str(start), str(end))
	holidays = get_holidays_for_calendar(employee.name, str(start), str(end))
	events = {str(value): status for value, status in attendance.items()}
	for value in holidays:
		events.setdefault(str(value), "Holiday")
	checkin_start = _day_bounds(start)[0]
	checkin_end = _day_bounds(end)[1]
	return {
		"events": events,
		"checkins": frappe.get_list(
			"Employee Checkin",
			filters={"employee": employee.name, "time": ["between", [checkin_start, checkin_end]]},
			fields=["name", "time", "log_type", "shift"],
			order_by="time desc, creation desc, name desc",
			limit_page_length=0,
		),
		"records": frappe.get_list(
			"Attendance",
			filters={"employee": employee.name, "attendance_date": ["between", [start, end]], "docstatus": 1},
			fields=[
				"name",
				"attendance_date",
				"status",
				"leave_type",
				"shift",
				"in_time",
				"out_time",
				"working_hours",
				"late_entry",
				"early_exit",
			],
			order_by="attendance_date desc",
			limit_page_length=0,
		),
	}


@frappe.whitelist(methods=["POST"])
def create_checkin(log_type: str, latitude=None, longitude=None, accuracy=None, company: str | None = None):
	employee = get_current_employee(company)
	settings = get_company_settings(employee.company)
	if not settings.enable_mobile_attendance:
		frappe.throw(_("Mobile attendance is disabled for this company."), frappe.PermissionError)
	if not frappe.db.get_single_value("HR Settings", "allow_employee_checkin_from_mobile_app"):
		frappe.throw(_("Mobile employee check-in is disabled in HR Settings."))
	server_time = now_datetime()
	if settings.attendance_start_date and getdate(server_time) < getdate(settings.attendance_start_date):
		frappe.throw(
			_("Mobile attendance is not available before {0}.").format(settings.attendance_start_date)
		)
	log_type = _normalize_log_type(log_type)
	if log_type not in {"IN", "OUT"}:
		frappe.throw(_("Invalid attendance action."))
	# Serialize state transitions per employee. The following locking read is a
	# current read, so a request waiting here sees a concurrent request's commit.
	frappe.db.get_value("Employee", employee.name, "name", for_update=True)
	state = _attendance_state(employee.name, server_time, for_update=True)
	expected = state.next_action
	if log_type != expected:
		frappe.throw(_("Your attendance changed. Refresh and try again."))
	gps_required = bool(
		settings.enable_gps_validation
		or frappe.db.get_single_value("HR Settings", "allow_geolocation_tracking")
	)
	if gps_required and (latitude in (None, "") or longitude in (None, "")):
		frappe.throw(_("Location permission is required for attendance."))
	doc = frappe.get_doc(
		{
			"doctype": "Employee Checkin",
			"employee": employee.name,
			"log_type": log_type,
			"time": server_time,
			"latitude": flt(latitude) if latitude not in (None, "") else None,
			"longitude": flt(longitude) if longitude not in (None, "") else None,
			"device_id": "Nagi Attendance PWA",
		}
	)
	doc.insert()
	return {"name": doc.name, "log_type": doc.log_type, "time": str(doc.time)}


@frappe.whitelist(methods=["POST"])
def create_leave_application(
	leave_type: str,
	from_date: str,
	to_date: str,
	description: str | None = None,
	half_day: int | str = 0,
	half_day_date: str | None = None,
	company: str | None = None,
):
	employee = get_current_employee(company)
	settings = get_company_settings(employee.company)
	if not settings.enable_mobile_leave:
		frappe.throw(_("Mobile leave is disabled for this company."), frappe.PermissionError)
	from hrms.api import get_leave_approval_details, get_leave_types

	allowed_types = get_leave_types(employee.name, from_date)
	if leave_type not in allowed_types:
		frappe.throw(_("This leave type is not available for the selected date."))
	approval = get_leave_approval_details(employee.name)
	doc = frappe.get_doc(
		{
			"doctype": "Leave Application",
			"employee": employee.name,
			"company": employee.company,
			"posting_date": today(),
			"leave_type": leave_type,
			"from_date": from_date,
			"to_date": to_date,
			"half_day": cint(half_day),
			"half_day_date": half_day_date if cint(half_day) else None,
			"description": description,
			"leave_approver": approval.get("leave_approver"),
			"status": "Open",
		}
	)
	# Native HRMS keeps employee requests Open (draft) until an approver decides.
	# Submitting here requires approver rights and HRMS rejects Open submissions.
	doc.insert()
	return {"name": doc.name, "status": doc.status, "docstatus": doc.docstatus}


def _approval_actions(doc) -> list[str]:
	from nagi_attendance.leave_approval import leave_actions

	return leave_actions(doc)


@frappe.whitelist(methods=["POST"])
def apply_leave_action(name: str, action: str, modified: str | None = None):
	require_authenticated_user()
	from nagi_attendance.leave_approval import decide_leave

	return decide_leave(name, action, modified)


@frappe.whitelist(methods=["POST"])
def cancel_leave_application(name: str, company: str | None = None):
	employee = get_current_employee(company)
	doc = frappe.get_doc("Leave Application", name)
	if doc.employee != employee.name or doc.company != employee.company:
		frappe.throw(_("You can only cancel your own leave request."), frappe.PermissionError)
	doc.check_permission("cancel")
	doc.cancel()
	return {"name": doc.name, "status": doc.status, "docstatus": doc.docstatus}
