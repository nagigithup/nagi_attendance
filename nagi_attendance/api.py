from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, time, timedelta

import frappe
from frappe import _
from frappe.model.workflow import get_workflow_name
from frappe.utils import add_days, cint, flt, get_datetime, get_time, getdate, now_datetime, today

from nagi_attendance.company import get_company_settings
from nagi_attendance.leave_approval import (
	check_leave_scope,
	decide_leave,
	is_assigned_approver,
	leave_actions,
)
from nagi_attendance.short_permission import (
	_is_admin,
	_shift_window,
)

EMPLOYEE_FIELDS = [
	"name",
	"employee_name",
	"image",
	"department",
	"designation",
	"company",
	"holiday_list",
	"default_shift",
]
ATTENDANCE_FIELDS = [
	"name",
	"employee",
	"attendance_date",
	"status",
	"leave_type",
	"shift",
	"in_time",
	"out_time",
	"working_hours",
	"late_entry",
	"early_exit",
]


def has_app_permission() -> bool:
	"""Use the existing Desk Page roles to decide whether its app icon is visible."""
	return frappe.session.user != "Guest" and bool(
		frappe.get_doc("Page", "manager-attendance").is_permitted()
	)


def _require_access(*doctypes: str) -> None:
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in to view Nagi Attendance."), frappe.PermissionError)
	if not has_app_permission():
		frappe.throw(_("You do not have permission to view Manager Attendance."), frappe.PermissionError)
	if not frappe.has_permission("Employee", "read"):
		frappe.throw(_("You do not have permission to read employee attendance."), frappe.PermissionError)
	for doctype in doctypes:
		if not frappe.has_permission(doctype, "read"):
			frappe.throw(_("You do not have permission to read {0}.").format(doctype), frappe.PermissionError)


def _employees(
	employee: str | None = None,
	department: str | None = None,
	attendance_period: tuple[date, date] | None = None,
) -> list[frappe._dict]:
	filters: dict = {"status": "Active"}
	if employee:
		filters["name"] = employee
	if department:
		filters["department"] = department
	employees = frappe.get_list(
		"Employee",
		filters=filters,
		fields=EMPLOYEE_FIELDS,
		order_by="employee_name asc",
		limit_page_length=0,
	)
	if not attendance_period or not employees:
		return employees

	# The existing company policy uses active Shift Assignments as the explicit
	# attendance requirement. Employees without one (Adan partners, for example)
	# remain visible in HRMS but are not reported as absent/missing on this dashboard.
	policy_companies = {
		row.company
		for row in employees
		if row.company and get_company_settings(row.company).get("prevent_automatic_absence")
	}
	if not policy_companies:
		return employees

	required = {row.name for row in employees if row.company not in policy_companies}
	start, end = attendance_period
	assignments = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": ["in", [row.name for row in employees if row.company in policy_companies]],
			"start_date": ["<=", end],
			"docstatus": 1,
		},
		or_filters=[["end_date", ">=", start], ["end_date", "is", "not set"]],
		pluck="employee",
	)
	required.update(assignments)
	return [row for row in employees if row.name in required]


def _get_rows(doctype: str, filters: dict, fields: list[str], order_by: str | None = None):
	if not frappe.has_permission(doctype, "read"):
		return []
	return frappe.get_list(
		doctype,
		filters=filters,
		fields=fields,
		order_by=order_by,
		limit_page_length=0,
	)


def _day_bounds(value: date) -> tuple[datetime, datetime]:
	return datetime.combine(value, time.min), datetime.combine(value, time.max)


def _format_duration(hours: float) -> str:
	total_minutes = max(0, round(flt(hours) * 60))
	return f"{total_minutes // 60}h {total_minutes % 60:02d}m"


def _format_time(value) -> str | None:
	return get_datetime(value).strftime("%H:%M") if value else None


def _live_hours(logs: list[frappe._dict], as_of: datetime | None = None) -> float:
	"""Pair IN/OUT logs and include an open IN interval for today's live view."""
	seconds = 0.0
	open_in = None
	for log in sorted(logs, key=lambda row: get_datetime(row.time)):
		log_time = get_datetime(log.time)
		if log.log_type == "OUT":
			if open_in and log_time > open_in:
				seconds += (log_time - open_in).total_seconds()
			open_in = None
		else:
			if open_in is None:
				open_in = log_time
	if open_in and as_of and as_of > open_in:
		seconds += (as_of - open_in).total_seconds()
	return round(seconds / 3600, 2)


def _holiday_map(employees: list[frappe._dict], start: date, end: date) -> dict[str, dict[str, str]]:
	"""Return only the holiday date/label data needed by the authorized dashboard.

	The caller has already passed Employee, Attendance and Checkin permission checks.
	Using this narrow server-side projection avoids granting HR User broad read access
	to the Holiday List master merely to render attendance cells.
	"""
	from hrms.utils.holiday_list import get_holiday_list_assignments, resolve_holiday_list_assignment

	assigned_to = [row.name for row in employees] + [row.company for row in employees if row.company]
	assignments = get_holiday_list_assignments(assigned_to)
	list_names = {assignment.holiday_list for rows in assignments.values() for assignment in rows} | {
		row.holiday_list for row in employees if row.holiday_list
	}
	if not list_names:
		return {}
	holiday_rows = frappe.db.get_all(
		"Holiday",
		filters={"parent": ["in", list(list_names)], "holiday_date": ["between", [start, end]]},
		fields=["parent", "holiday_date", "description", "weekly_off"],
	)
	by_list = defaultdict(dict)
	for row in holiday_rows:
		by_list[row.parent][str(row.holiday_date)] = (
			"Weekly Off" if row.weekly_off else (row.description or "Holiday")
		)
	result = defaultdict(dict)
	for employee in employees:
		cursor = start
		while cursor <= end:
			assignment = resolve_holiday_list_assignment(
				assignments.get(employee.name, []), assignments.get(employee.company, []), cursor
			)
			list_name = assignment.holiday_list if assignment else employee.holiday_list
			if list_name and str(cursor) in by_list[list_name]:
				result[employee.name][str(cursor)] = by_list[list_name][str(cursor)]
			cursor = add_days(cursor, 1)
	return result


def _late_from_checkin(first_log, shift_name: str | None) -> bool:
	if not first_log or not shift_name:
		return False
	shift = frappe.db.get_value(
		"Shift Type",
		shift_name,
		["start_time", "enable_late_entry_marking", "late_entry_grace_period"],
		as_dict=True,
	)
	if not shift or not cint(shift.enable_late_entry_marking):
		return False
	start = get_datetime(first_log.time).replace(
		hour=shift.start_time.seconds // 3600,
		minute=(shift.start_time.seconds % 3600) // 60,
		second=0,
		microsecond=0,
	)
	return get_datetime(first_log.time) > start + timedelta(minutes=cint(shift.late_entry_grace_period))


def _resolve_status(
	attendance: frappe._dict | None,
	leave: frappe._dict | None,
	holiday: str | None,
	logs: list[frappe._dict],
	shift: str | None,
	value: date,
) -> tuple[str, str | None, bool]:
	"""Apply the documented leave > holiday > attendance > live-checkin precedence."""
	if leave:
		return "On Leave", leave.leave_type, False
	if holiday:
		return holiday if holiday == "Weekly Off" else "Holiday", holiday, False
	if attendance:
		return attendance.status, attendance.leave_type, bool(attendance.late_entry)
	if logs:
		late = _late_from_checkin(logs[0], logs[0].shift or shift)
		return ("Late" if late else "Present"), None, late
	if value < getdate(today()):
		return "Absent", None, False
	return "Not Checked In", None, False


def _today_data(value: date, employee: str | None = None, department: str | None = None) -> dict:
	employees = _employees(employee, department, attendance_period=(value, value))
	names = [row.name for row in employees]
	if not names:
		return {"date": str(value), "summary": _empty_summary(), "employees": [], "timeline": []}

	start, end = _day_bounds(value)
	attendances = _get_rows(
		"Attendance",
		{"employee": ["in", names], "attendance_date": value, "docstatus": 1},
		ATTENDANCE_FIELDS,
	)
	leaves = _get_rows(
		"Leave Application",
		{
			"employee": ["in", names],
			"from_date": ["<=", value],
			"to_date": [">=", value],
			"status": "Approved",
			"docstatus": 1,
		},
		["name", "employee", "leave_type", "from_date", "to_date", "total_leave_days"],
	)
	checkins = _get_rows(
		"Employee Checkin",
		{"employee": ["in", names], "time": ["between", [start, end]]},
		["name", "employee", "employee_name", "time", "log_type", "shift"],
		"time asc",
	)
	attendance_by_employee = {row.employee: row for row in attendances}
	leave_by_employee = {row.employee: row for row in leaves}
	logs_by_employee = defaultdict(list)
	for row in checkins:
		logs_by_employee[row.employee].append(row)
	holidays = _holiday_map(employees, value, value)

	result = []
	for employee_row in employees:
		attendance = attendance_by_employee.get(employee_row.name)
		leave = leave_by_employee.get(employee_row.name)
		logs = logs_by_employee[employee_row.name]
		holiday = holidays.get(employee_row.name, {}).get(str(value))
		shift = attendance.shift if attendance else (logs[0].shift if logs else employee_row.default_shift)
		status, detail, late = _resolve_status(attendance, leave, holiday, logs, shift, value)
		in_time = attendance.in_time if attendance else (logs[0].time if logs else None)
		out_logs = [log for log in logs if log.log_type == "OUT"]
		out_time = attendance.out_time if attendance else (out_logs[-1].time if out_logs else None)
		working_hours = (
			flt(attendance.working_hours)
			if attendance
			else _live_hours(logs, now_datetime() if value == getdate(today()) else None)
		)
		result.append(
			{
				**employee_row,
				"status": status,
				"status_detail": detail,
				"attendance": attendance.name if attendance else None,
				"leave_application": leave.name if leave else None,
				"shift": shift,
				"in_time": str(in_time) if in_time else None,
				"out_time": str(out_time) if out_time else None,
				"in_time_label": _format_time(in_time),
				"out_time_label": _format_time(out_time),
				"working_hours": working_hours,
				"working_hours_label": _format_duration(working_hours),
				"late": late,
				"early_exit": bool(attendance.early_exit) if attendance else False,
			}
		)

	summary = _empty_summary()
	summary["total"] = len(result)
	for row in result:
		if row["status"] in {"Present", "Late", "Work From Home", "Half Day"}:
			summary["present"] += 1
		if row["status"] == "Absent":
			summary["absent"] += 1
		if row["status"] == "On Leave":
			summary["leave"] += 1
		if row["late"] or row["status"] == "Late":
			summary["late"] += 1
		if row["status"] == "Not Checked In":
			summary["not_checked_in"] += 1

	employee_names = {row.name: row.employee_name for row in employees}
	timeline = [
		{
			"name": row.name,
			"employee": row.employee,
			"employee_name": employee_names.get(row.employee, row.employee_name),
			"time": str(row.time),
			"time_label": _format_time(row.time),
			"log_type": row.log_type or "IN",
			"late": bool(
				row == logs_by_employee[row.employee][0]
				and _late_from_checkin(
					row,
					row.shift or next((e.default_shift for e in employees if e.name == row.employee), None),
				)
			),
		}
		for row in checkins
	]
	return {"date": str(value), "summary": summary, "employees": result, "timeline": timeline}


def _empty_summary() -> dict[str, int]:
	return {"total": 0, "present": 0, "absent": 0, "leave": 0, "late": 0, "not_checked_in": 0}


@frappe.whitelist()
def get_today_dashboard(date: str | None = None, employee: str | None = None, department: str | None = None):
	_require_access("Attendance", "Employee Checkin", "Leave Application")
	value = getdate(date or today())
	data = _today_data(value, employee, department)
	data["filters"] = {
		"employees": _employees(department=department, attendance_period=(value, value)),
		"departments": frappe.get_list("Department", pluck="name", order_by="name asc", limit_page_length=0),
	}
	return data


@frappe.whitelist()
def get_dashboard_defaults(company: str | None = None) -> dict:
	"""Return a permitted company's reporting preference, never an authorization filter."""
	_require_access()
	company = company or frappe.defaults.get_user_default("Company")
	if not company or not frappe.get_list(
		"Company", filters={"name": company}, pluck="name", limit_page_length=1
	):
		return {"company": None, "default_reporting_department": None}

	department = get_company_settings(company).get("default_reporting_department")
	if department and not frappe.get_list(
		"Department",
		filters={"name": department, "company": company},
		pluck="name",
		limit_page_length=1,
	):
		department = None
	return {"company": company, "default_reporting_department": department}


SHORT_PERMISSION_STATUSES = {"Pending", "Approved", "Rejected", "Cancelled"}
SHORT_PERMISSION_TYPES = {"Late Arrival", "Early Departure", "Temporary Exit"}


def _permission_scope() -> frappe._dict:
	"""Resolve manager scope without exposing unrestricted Employee or request rows."""
	user = frappe.session.user
	employees = frappe.get_list(
		"Employee",
		filters={"status": "Active"},
		fields=[
			"name",
			"employee_name",
			"company",
			"department",
			"user_id",
			"reports_to",
			"leave_approver",
		],
		order_by="employee_name asc",
		limit=0,
	)
	if not _is_admin(user):
		manager_employees = {row.name for row in employees if row.user_id == user}
		employees = [
			row
			for row in employees
			if (
				(row.leave_approver == user and row.leave_approver != row.user_id)
				or (
					(not row.leave_approver or row.leave_approver == row.user_id)
					and row.reports_to in manager_employees
				)
			)
		]

	# Keep historical request companies in scope even if the employee is now inactive.
	history_filters = {} if _is_admin(user) else {"approver": user}
	history_companies = frappe.get_list(
		"Attendance Permission Request",
		filters=history_filters,
		pluck="company",
		group_by="company",
		limit=0,
	)
	companies = sorted({row.company for row in employees if row.company} | set(history_companies))
	enabled_companies = [
		company for company in companies if cint(get_company_settings(company).get("enable_short_permission"))
	]
	return frappe._dict(
		employees=employees,
		companies=companies,
		enabled_companies=enabled_companies,
		is_admin=_is_admin(user),
	)


def _permission_base_filters(scope: frappe._dict) -> dict:
	filters = {}
	if not scope.is_admin:
		filters["approver"] = frappe.session.user
	return filters


def _permission_request_filters(scope: frappe._dict, **values) -> tuple[dict, dict]:
	filters = _permission_base_filters(scope)
	summary_filters = dict(filters)
	company = values.get("company")
	if company:
		if company not in scope.companies:
			frappe.throw(
				_("You are not authorized to view this company's permission requests."),
				frappe.PermissionError,
			)
		summary_filters["company"] = company
	for field in ("department", "employee", "permission_type"):
		if values.get(field):
			summary_filters[field] = values[field]
	from_date, to_date = values.get("from_date"), values.get("to_date")
	if from_date and to_date and getdate(from_date) > getdate(to_date):
		frappe.throw(_("From Date cannot be after To Date."))
	if from_date and to_date:
		summary_filters["permission_date"] = ["between", [from_date, to_date]]
	elif from_date:
		summary_filters["permission_date"] = [">=", from_date]
	elif to_date:
		summary_filters["permission_date"] = ["<=", to_date]
	filters = dict(summary_filters)
	status = values.get("status")
	if status:
		if status not in SHORT_PERMISSION_STATUSES:
			frappe.throw(_("Invalid permission status."))
		filters["status"] = status
		if status == "Pending":
			if company and company not in scope.enabled_companies:
				# Pending My Approval contains actionable requests only. Historical
				# pending rows for a disabled company remain available in the All view.
				filters["name"] = "__no_actionable_permission_request__"
			elif not company:
				filters["company"] = ["in", scope.enabled_companies]
	permission_type = values.get("permission_type")
	if permission_type and permission_type not in SHORT_PERMISSION_TYPES:
		frappe.throw(_("Invalid permission type."))
	return filters, summary_filters


def _can_manage_permission(doc, scope: frappe._dict) -> bool:
	if doc.status != "Pending" or doc.company not in scope.enabled_companies:
		return False
	employee_user = frappe.db.get_value("Employee", doc.employee, "user_id")
	return employee_user != frappe.session.user and (scope.is_admin or doc.approver == frappe.session.user)


@frappe.whitelist()
def get_short_permission_context() -> dict:
	_require_access("Attendance Permission Request")
	scope = _permission_scope()
	visible = bool(scope.enabled_companies)
	pending_count = 0
	if visible:
		filters = _permission_base_filters(scope)
		filters.update({"status": "Pending", "company": ["in", scope.enabled_companies]})
		# The badge is the signed-in manager's inbox, including for HR admins.
		filters["approver"] = frappe.session.user
		rows = frappe.get_list(
			"Attendance Permission Request",
			filters=filters,
			fields=["name", "employee", "company", "approver", "status"],
			limit=0,
		)
		pending_count = len({row.name for row in rows if _can_manage_permission(row, scope)})
	return {
		"visible": visible,
		"pending_count": pending_count,
		"filters": {
			"companies": scope.companies,
			"departments": sorted({row.department for row in scope.employees if row.department}),
			"employees": [
				{"name": row.name, "employee_name": row.employee_name, "company": row.company}
				for row in scope.employees
			],
		},
	}


@frappe.whitelist()
def get_short_permission_dashboard(
	company: str | None = None,
	department: str | None = None,
	employee: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	status: str | None = "Pending",
	permission_type: str | None = None,
	page: int | str = 1,
	page_length: int | str = 20,
) -> dict:
	_require_access("Attendance Permission Request")
	scope = _permission_scope()
	if not scope.enabled_companies:
		return {"visible": False, "rows": [], "summary": {}, "total": 0, "page": 1, "page_length": 20}
	page = max(1, cint(page))
	page_length = min(100, max(10, cint(page_length)))
	filters, summary_filters = _permission_request_filters(
		scope,
		company=company,
		department=department,
		employee=employee,
		from_date=from_date,
		to_date=to_date,
		status=status,
		permission_type=permission_type,
	)
	fields = [
		"name",
		"employee",
		"employee_name",
		"company",
		"department",
		"permission_date",
		"permission_type",
		"from_time",
		"to_time",
		"duration_hours",
		"reason",
		"approver",
		"status",
		"manager_comment",
		"decision_by",
		"decision_on",
	]
	rows = frappe.get_list(
		"Attendance Permission Request",
		filters=filters,
		fields=fields,
		order_by="permission_date desc, creation desc",
		start=(page - 1) * page_length,
		limit=page_length,
	)
	for row in rows:
		row["can_action"] = _can_manage_permission(row, scope)
		row["feature_enabled"] = row.company in scope.enabled_companies

	grouped = frappe.get_list(
		"Attendance Permission Request",
		filters=summary_filters,
		fields=[
			"status",
			{"COUNT": "name", "as": "request_count"},
			{"SUM": "duration_hours", "as": "duration_hours"},
		],
		group_by="status",
		limit=0,
	)
	summary = {"pending": 0, "approved": 0, "rejected": 0, "approved_hours": 0.0}
	for row in grouped:
		key = str(row.status).lower()
		if key in summary:
			summary[key] = cint(row.request_count)
		if row.status == "Approved":
			summary["approved_hours"] = flt(row.duration_hours, 2)
	pending_filters = {**summary_filters, "status": "Pending"}
	selected_company = summary_filters.get("company")
	if selected_company and selected_company not in scope.enabled_companies:
		pending_filters["name"] = "__no_actionable_permission_request__"
	elif not selected_company:
		pending_filters["company"] = ["in", scope.enabled_companies]
	pending_rows = frappe.get_list(
		"Attendance Permission Request",
		filters=pending_filters,
		fields=[{"COUNT": "name", "as": "request_count"}],
		limit=1,
	)
	summary["pending"] = cint(pending_rows[0].request_count) if pending_rows else 0
	total_rows = frappe.get_list(
		"Attendance Permission Request",
		filters=filters,
		fields=[{"COUNT": "name", "as": "request_count"}],
		limit=1,
	)
	return {
		"visible": True,
		"rows": rows,
		"summary": summary,
		"total": cint(total_rows[0].request_count) if total_rows else 0,
		"page": page,
		"page_length": page_length,
	}


@frappe.whitelist()
def get_short_permission_details(name: str) -> dict:
	_require_access("Attendance Permission Request", "Attendance")
	scope = _permission_scope()
	doc = frappe.get_doc("Attendance Permission Request", name)
	doc.check_permission("read")
	if not scope.is_admin and doc.approver != frappe.session.user:
		frappe.throw(_("You are not authorized to view this permission request."), frappe.PermissionError)
	start = datetime.combine(getdate(doc.permission_date), get_time(doc.from_time))
	shift = _shift_window(doc.employee, start)
	attendance = frappe.get_list(
		"Attendance",
		filters={"employee": doc.employee, "attendance_date": doc.permission_date, "docstatus": 1},
		fields=[
			"name",
			"status",
			"shift",
			"in_time",
			"out_time",
			"working_hours",
			"late_entry",
			"early_exit",
		],
		limit=1,
	)
	request_fields = [
		"name",
		"employee",
		"employee_name",
		"company",
		"department",
		"permission_date",
		"permission_type",
		"from_time",
		"to_time",
		"duration_hours",
		"reason",
		"approver",
		"status",
		"manager_comment",
		"decision_by",
		"decision_on",
	]
	return {
		"request": {
			**{field: doc.get(field) for field in request_fields},
			"can_action": _can_manage_permission(doc, scope),
		},
		"shift": {
			"shift_type": getattr(shift.shift_type, "name", shift.shift_type),
			"start_datetime": shift.start_datetime,
			"end_datetime": shift.end_datetime,
		}
		if shift
		else None,
		"attendance": attendance[0] if attendance else None,
	}


def _attendance_code(status: str) -> str:
	return {
		"Present": "P",
		"Late": "P",
		"Absent": "A",
		"On Leave": "L",
		"Half Day": "HD",
		"Holiday": "H",
		"Weekly Off": "WO",
		"Work From Home": "WFH",
		"Not Checked In": "—",
	}.get(status, "—")


@frappe.whitelist()
def get_monthly_attendance(
	year: int | str,
	month: int | str,
	employee: str | None = None,
	department: str | None = None,
):
	_require_access("Attendance", "Employee Checkin", "Leave Application")
	year, month = cint(year), cint(month)
	if not (2000 <= year <= 2100 and 1 <= month <= 12):
		frappe.throw(_("Please select a valid month and year."))
	start = date(year, month, 1)
	end = date(year, month, calendar.monthrange(year, month)[1])
	employees = _employees(employee, department, attendance_period=(start, end))
	names = [row.name for row in employees]
	if not names:
		return {"year": year, "month": month, "days": [], "employees": [], "charts": {}}

	attendances = _get_rows(
		"Attendance",
		{"employee": ["in", names], "attendance_date": ["between", [start, end]], "docstatus": 1},
		ATTENDANCE_FIELDS,
	)
	leaves = _get_rows(
		"Leave Application",
		{
			"employee": ["in", names],
			"from_date": ["<=", end],
			"to_date": [">=", start],
			"status": "Approved",
			"docstatus": 1,
		},
		["name", "employee", "leave_type", "from_date", "to_date"],
	)
	checkins = _get_rows(
		"Employee Checkin",
		{"employee": ["in", names], "time": ["between", [*_day_bounds(start)[:1], _day_bounds(end)[1]]]},
		["name", "employee", "time", "log_type", "shift"],
		"time asc",
	)
	attendance_map = {(row.employee, str(row.attendance_date)): row for row in attendances}
	leave_map = {}
	for row in leaves:
		cursor = max(getdate(row.from_date), start)
		while cursor <= min(getdate(row.to_date), end):
			leave_map[(row.employee, str(cursor))] = row
			cursor = add_days(cursor, 1)
	logs_map = defaultdict(list)
	for row in checkins:
		logs_map[(row.employee, str(getdate(row.time)))].append(row)
	holidays = _holiday_map(employees, start, end)

	days = [
		{
			"day": day,
			"date": str(date(year, month, day)),
			"weekday": calendar.day_abbr[date(year, month, day).weekday()],
		}
		for day in range(1, end.day + 1)
	]
	rows = []
	trend = [0] * end.day
	late_by_employee = []
	breakdown = defaultdict(int)
	for employee_row in employees:
		cells = []
		counts = defaultdict(int)
		total_hours = 0.0
		in_times, out_times = [], []
		for day in days:
			value = getdate(day["date"])
			attendance = attendance_map.get((employee_row.name, day["date"]))
			leave = leave_map.get((employee_row.name, day["date"]))
			logs = logs_map[(employee_row.name, day["date"])]
			holiday = holidays.get(employee_row.name, {}).get(day["date"])
			shift = (
				attendance.shift if attendance else (logs[0].shift if logs else employee_row.default_shift)
			)
			if value > getdate(today()) and not attendance and not leave:
				status, detail, late = "Future", None, False
			else:
				status, detail, late = _resolve_status(attendance, leave, holiday, logs, shift, value)
			working_hours = flt(attendance.working_hours) if attendance else _live_hours(logs)
			first = attendance.in_time if attendance else (logs[0].time if logs else None)
			out_logs = [log for log in logs if log.log_type == "OUT"]
			last = attendance.out_time if attendance else (out_logs[-1].time if out_logs else None)
			cells.append(
				{
					"date": day["date"],
					"status": status,
					"code": _attendance_code(status),
					"detail": detail,
					"in_time": _format_time(first),
					"out_time": _format_time(last),
					"working_hours": working_hours,
					"working_hours_label": _format_duration(working_hours),
					"late": late,
					"early_exit": bool(attendance.early_exit) if attendance else False,
				}
			)
			if status != "Future":
				counts[status] += 1
				breakdown[status] += 1
			if status in {"Present", "Late", "Half Day", "Work From Home"}:
				trend[value.day - 1] += 1
			if late:
				counts["Late Days"] += 1
			total_hours += working_hours
			if first:
				in_times.append(get_datetime(first))
			if last:
				out_times.append(get_datetime(last))
		working_days = sum(1 for cell in cells if cell["status"] not in {"Holiday", "Weekly Off", "Future"})
		summary = {
			"working_days": working_days,
			"present": sum(counts[s] for s in ("Present", "Late", "Work From Home")),
			"absent": counts["Absent"],
			"leave": counts["On Leave"],
			"half_day": counts["Half Day"],
			"late": counts["Late Days"],
			"working_hours": round(total_hours, 2),
			"working_hours_label": _format_duration(total_hours),
			"average_in": _average_time(in_times),
			"average_out": _average_time(out_times),
		}
		late_by_employee.append({"employee": employee_row.employee_name, "value": summary["late"]})
		rows.append({**employee_row, "days": cells, "summary": summary})
	return {
		"year": year,
		"month": month,
		"days": days,
		"employees": rows,
		"charts": {
			"breakdown": {
				"present": sum(breakdown[s] for s in ("Present", "Late", "Half Day", "Work From Home")),
				"leave": breakdown["On Leave"],
				"absent": breakdown["Absent"],
			},
			"trend": trend,
			"late": late_by_employee,
		},
	}


def _average_time(values: list[datetime]) -> str | None:
	if not values:
		return None
	minutes = round(sum(value.hour * 60 + value.minute for value in values) / len(values))
	return f"{minutes // 60:02d}:{minutes % 60:02d}"


@frappe.whitelist()
def get_leave_dashboard(
	date: str | None = None,
	employee: str | None = None,
	department: str | None = None,
):
	_require_access("Leave Application")
	value = getdate(date or today())
	employee_filter = {}
	if employee or department:
		names = [row.name for row in _employees(employee, department)]
		employee_filter["employee"] = ["in", names]
	base_fields = [
		"name",
		"employee",
		"employee_name",
		"leave_type",
		"from_date",
		"to_date",
		"total_leave_days",
		"description",
		"status",
		"docstatus",
		"owner",
	]
	on_leave = _get_rows(
		"Leave Application",
		{
			**employee_filter,
			"from_date": ["<=", value],
			"to_date": [">=", value],
			"status": "Approved",
			"docstatus": 1,
		},
		base_fields,
		"from_date asc",
	)
	upcoming = _get_rows(
		"Leave Application",
		{**employee_filter, "from_date": [">", value], "status": "Approved", "docstatus": 1},
		base_fields,
		"from_date asc",
	)[:20]
	# Reporting filters scope the calendars, not the manager's approval inbox.
	# Keep this list aligned with the unfiltered actionable notification count.
	pending = _pending_leave_requests()
	return {"date": str(value), "on_leave": on_leave, "upcoming": upcoming, "pending": pending}


def _pending_leave_requests() -> list:
	filters = {
		"status": "Open",
		"docstatus": 0,
		"leave_approver": frappe.session.user,
	}
	rows = _get_rows(
		"Leave Application",
		filters,
		[
			"name", "employee", "employee_name", "company", "leave_type", "from_date", "to_date",
			"total_leave_days", "description", "status", "docstatus", "modified",
		],
		"from_date asc",
	)
	pending = []
	for row in rows:
		row["actions"] = _workflow_actions(row.name)
		if row.actions:
			pending.append(row)
	return pending


def _workflow_actions(name: str) -> list[str]:
	try:
		return leave_actions(frappe.get_doc("Leave Application", name))
	except frappe.DoesNotExistError:
		return []


def _is_assigned_leave_approver(doc) -> bool:
	return is_assigned_approver(doc)


@frappe.whitelist()
def get_leave_details(name: str) -> dict:
	_require_access("Leave Application")
	doc = frappe.get_doc("Leave Application", name)
	check_leave_scope(doc)
	# Open approval requests belong to the assigned manager's inbox.
	if doc.status == "Open" and not is_assigned_approver(doc):
		frappe.throw(_("You are not authorized to access this leave request."), frappe.PermissionError)
	fields = [
		"name", "employee", "employee_name", "company", "leave_type", "from_date", "to_date",
		"total_leave_days", "half_day", "half_day_date", "description", "status", "docstatus",
		"leave_approver", "leave_approver_name", "modified",
	]
	request = {key: doc.get(key) for key in fields}
	request["department"] = frappe.db.get_value("Employee", doc.employee, "department")
	workflow = get_workflow_name("Leave Application")
	if workflow:
		state_field = frappe.get_cached_value("Workflow", workflow, "workflow_state_field")
		request["workflow_state"] = doc.get(state_field)
	balance = None
	if not frappe.db.get_value("Leave Type", doc.leave_type, "is_lwp"):
		from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

		try:
			balance = get_leave_balance_on(
				doc.employee, doc.leave_type, doc.from_date,
				to_date=doc.to_date, leave_application=doc.name,
			)
		except frappe.PermissionError:
			# HRMS decides whether this user may see balances; never invent one.
			pass
	return {"request": request, "actions": leave_actions(doc), "leave_balance": balance}


@frappe.whitelist()
def get_manager_pending_context() -> dict:
	_require_access()
	permissions = {"visible": False, "pending_count": 0, "filters": {}}
	if frappe.has_permission("Attendance Permission Request", "read"):
		permissions = get_short_permission_context()
	leave_count = 0
	if frappe.has_permission("Leave Application", "read"):
		leave_count = len({row.name for row in _pending_leave_requests()})
	short_count = permissions["pending_count"]
	return {
		"leave_count": leave_count,
		"short_permission_count": short_count,
		"total_pending": leave_count + short_count,
		"short_permissions": permissions,
	}


@frappe.whitelist(methods=["POST"])
def apply_leave_action(name: str, action: str, modified: str | None = None):
	_require_access("Leave Application")
	return decide_leave(name, action, modified)


@frappe.whitelist()
def get_employee_details(
	employee: str, date: str | None = None, year: int | None = None, month: int | None = None
):
	_require_access("Attendance", "Employee Checkin", "Leave Application")
	value = getdate(date or today())
	if not frappe.has_permission("Employee", "read", employee):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	today_data = _today_data(value, employee=employee)
	monthly = get_monthly_attendance(year or value.year, month or value.month, employee=employee)
	upcoming = _get_rows(
		"Leave Application",
		{"employee": employee, "from_date": [">", value], "status": "Approved", "docstatus": 1},
		["name", "leave_type", "from_date", "to_date", "total_leave_days"],
		"from_date asc",
	)[:5]
	return {
		"employee": today_data["employees"][0] if today_data["employees"] else None,
		"month": monthly["employees"][0]["summary"] if monthly["employees"] else {},
		"upcoming_leave": upcoming,
	}
