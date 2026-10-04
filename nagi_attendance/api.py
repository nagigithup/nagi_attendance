from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, time, timedelta

import frappe
from frappe import _
from frappe.model.workflow import get_transitions, get_workflow_name
from frappe.utils import add_days, cint, flt, get_datetime, getdate, now_datetime, today


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


def _require_access(*doctypes: str) -> None:
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in to view Nagi Attendance."), frappe.PermissionError)
	if not frappe.has_permission("Employee", "read"):
		frappe.throw(_("You do not have permission to read employee attendance."), frappe.PermissionError)
	for doctype in doctypes:
		if not frappe.has_permission(doctype, "read"):
			frappe.throw(_("You do not have permission to read {0}.").format(doctype), frappe.PermissionError)


def _employees(employee: str | None = None, department: str | None = None) -> list[frappe._dict]:
	filters: dict = {"status": "Active"}
	if employee:
		filters["name"] = employee
	if department:
		filters["department"] = department
	return frappe.get_list(
		"Employee",
		filters=filters,
		fields=EMPLOYEE_FIELDS,
		order_by="employee_name asc",
		limit_page_length=0,
	)


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
	"""Resolve HRMS holiday assignments and return employee/date labels."""
	from hrms.utils.holiday_list import get_holiday_list_assignments, resolve_holiday_list_assignment

	assigned_to = [row.name for row in employees] + [row.company for row in employees if row.company]
	assignments = get_holiday_list_assignments(assigned_to)
	list_names = {
		assignment.holiday_list for rows in assignments.values() for assignment in rows
	} | {row.holiday_list for row in employees if row.holiday_list}
	if not list_names:
		return {}
	holiday_rows = frappe.db.get_all(
		"Holiday",
		filters={"parent": ["in", list(list_names)], "holiday_date": ["between", [start, end]]},
		fields=["parent", "holiday_date", "description", "weekly_off"],
	)
	by_list = defaultdict(dict)
	for row in holiday_rows:
		by_list[row.parent][str(row.holiday_date)] = "Weekly Off" if row.weekly_off else (row.description or "Holiday")
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
	employees = _employees(employee, department)
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
		working_hours = flt(attendance.working_hours) if attendance else _live_hours(
			logs, now_datetime() if value == getdate(today()) else None
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
				and _late_from_checkin(row, row.shift or next((e.default_shift for e in employees if e.name == row.employee), None))
			),
		}
		for row in checkins
	]
	return {"date": str(value), "summary": summary, "employees": result, "timeline": timeline}


def _empty_summary() -> dict[str, int]:
	return {"total": 0, "present": 0, "absent": 0, "leave": 0, "late": 0, "not_checked_in": 0}


@frappe.whitelist()
def get_today_dashboard(date: str | None = None, employee: str | None = None, department: str | None = None):
	_require_access("Attendance", "Employee Checkin", "Leave Application", "Holiday List")
	value = getdate(date or today())
	data = _today_data(value, employee, department)
	data["filters"] = {
		"employees": _employees(),
		"departments": frappe.get_list("Department", pluck="name", order_by="name asc", limit_page_length=0),
	}
	return data


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
	_require_access("Attendance", "Employee Checkin", "Leave Application", "Holiday List")
	year, month = cint(year), cint(month)
	if not (2000 <= year <= 2100 and 1 <= month <= 12):
		frappe.throw(_("Please select a valid month and year."))
	start = date(year, month, 1)
	end = date(year, month, calendar.monthrange(year, month)[1])
	employees = _employees(employee, department)
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

	days = [{"day": day, "date": str(date(year, month, day)), "weekday": calendar.day_abbr[date(year, month, day).weekday()]} for day in range(1, end.day + 1)]
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
			shift = attendance.shift if attendance else (logs[0].shift if logs else employee_row.default_shift)
			if value > getdate(today()) and not attendance and not leave:
				status, detail, late = "Future", None, False
			else:
				status, detail, late = _resolve_status(attendance, leave, holiday, logs, shift, value)
			working_hours = flt(attendance.working_hours) if attendance else _live_hours(logs)
			first = attendance.in_time if attendance else (logs[0].time if logs else None)
			out_logs = [log for log in logs if log.log_type == "OUT"]
			last = attendance.out_time if attendance else (out_logs[-1].time if out_logs else None)
			cells.append({
				"date": day["date"], "status": status, "code": _attendance_code(status),
				"detail": detail, "in_time": _format_time(first), "out_time": _format_time(last),
				"working_hours": working_hours, "working_hours_label": _format_duration(working_hours),
				"late": late, "early_exit": bool(attendance.early_exit) if attendance else False,
			})
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
			"breakdown": {"present": sum(breakdown[s] for s in ("Present", "Late", "Half Day", "Work From Home")), "leave": breakdown["On Leave"], "absent": breakdown["Absent"]},
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
def get_leave_dashboard(date: str | None = None):
	_require_access("Leave Application")
	value = getdate(date or today())
	base_fields = [
		"name", "employee", "employee_name", "leave_type", "from_date", "to_date",
		"total_leave_days", "description", "status", "docstatus", "owner",
	]
	on_leave = _get_rows(
		"Leave Application",
		{"from_date": ["<=", value], "to_date": [">=", value], "status": "Approved", "docstatus": 1},
		base_fields,
		"from_date asc",
	)
	upcoming = _get_rows(
		"Leave Application",
		{"from_date": [">", value], "status": "Approved", "docstatus": 1},
		base_fields,
		"from_date asc",
	)[:20]
	pending = _get_rows(
		"Leave Application", {"status": "Open", "docstatus": ["<", 2]}, base_fields, "from_date asc"
	)
	for row in pending:
		row["actions"] = _workflow_actions(row.name)
	return {"date": str(value), "on_leave": on_leave, "upcoming": upcoming, "pending": pending}


def _workflow_actions(name: str) -> list[str]:
	if not get_workflow_name("Leave Application"):
		return []
	try:
		doc = frappe.get_doc("Leave Application", name)
		return [row.action for row in get_transitions(doc)]
	except (frappe.PermissionError, frappe.ValidationError):
		return []


@frappe.whitelist()
def apply_leave_action(name: str, action: str):
	_require_access("Leave Application")
	from frappe.model.workflow import apply_workflow

	doc = frappe.get_doc("Leave Application", name)
	doc.check_permission("write")
	allowed = _workflow_actions(name)
	if action not in allowed:
		frappe.throw(_("Workflow action {0} is not available for this leave request.").format(action))
	updated = apply_workflow(doc, action)
	return {"name": updated.name, "status": updated.status}


@frappe.whitelist()
def get_employee_details(employee: str, date: str | None = None, year: int | None = None, month: int | None = None):
	_require_access("Attendance", "Employee Checkin", "Leave Application", "Holiday List")
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
