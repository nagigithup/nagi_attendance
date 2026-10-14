import frappe
from frappe import _
from frappe.utils import flt, get_datetime

from nagi_attendance.short_permission import (
	_interval,
	_shift_window,
	approved_permission_hours,
	worked_intervals_from_logs,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	query_filters = {}
	for field in ("company", "department", "employee", "status"):
		if filters.get(field):
			query_filters[field] = filters[field]
	if filters.from_date and filters.to_date:
		query_filters["permission_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.from_date:
		query_filters["permission_date"] = [">=", filters.from_date]
	elif filters.to_date:
		query_filters["permission_date"] = ["<=", filters.to_date]
	columns = [
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 130,
		},
		{"fieldname": "employee_name", "label": _("Employee Name"), "width": 160},
		{
			"fieldname": "company",
			"label": _("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"width": 150,
		},
		{
			"fieldname": "department",
			"label": _("Department"),
			"fieldtype": "Link",
			"options": "Department",
			"width": 150,
		},
		{"fieldname": "permission_date", "label": _("Permission Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "permission_type", "label": _("Permission Type"), "width": 130},
		{
			"fieldname": "duration_hours",
			"label": _("Authorized Duration"),
			"fieldtype": "Float",
			"width": 130,
		},
		{
			"fieldname": "creditable_authorized_hours",
			"label": _("Creditable Authorized Hours"),
			"fieldtype": "Float",
			"width": 160,
		},
		{
			"fieldname": "actual_worked_hours",
			"label": _("Actual Worked Hours"),
			"fieldtype": "Float",
			"width": 130,
		},
		{"fieldname": "compliance_hours", "label": _("Compliance Hours"), "fieldtype": "Float", "width": 120},
		{"fieldname": "late_approval_review", "label": _("Late Approval Review"), "width": 140},
		{
			"fieldname": "monthly_permission_hours",
			"label": _("Monthly Permission Total"),
			"fieldtype": "Float",
			"width": 150,
		},
		{
			"fieldname": "approver",
			"label": _("Approver"),
			"fieldtype": "Link",
			"options": "User",
			"width": 180,
		},
		{"fieldname": "decision_on", "label": _("Decision On"), "fieldtype": "Datetime", "width": 140},
		{"fieldname": "status", "label": _("Status"), "width": 90},
	]
	computed = {
		"creditable_authorized_hours",
		"actual_worked_hours",
		"compliance_hours",
		"late_approval_review",
		"monthly_permission_hours",
	}
	db_fields = [column["fieldname"] for column in columns if column["fieldname"] not in computed]
	db_fields.extend(["name", "from_time", "to_time"])
	data = frappe.get_list(
		"Attendance Permission Request",
		filters=query_filters,
		fields=db_fields,
		order_by="permission_date desc",
		limit=0,
	)
	for row in data:
		attendance = (
			frappe.db.get_value(
				"Attendance",
				{
					"employee": row.employee,
					"attendance_date": row.permission_date,
					"docstatus": 1,
				},
				["name", "working_hours", "modified"],
				as_dict=True,
			)
			or frappe._dict()
		)
		row.actual_worked_hours = flt(attendance.working_hours)
		permission_start, _permission_end = _interval(row.permission_date, row.from_time, row.to_time)
		shift = _shift_window(row.employee, permission_start)
		creditable = 0.0
		if shift:
			logs = frappe.get_all(
				"Employee Checkin",
				filters={
					"employee": row.employee,
					"time": ["between", [shift.actual_start, shift.actual_end]],
				},
				fields=["time", "log_type"],
				order_by="time asc",
			)
			if logs or not row.actual_worked_hours:
				worked = worked_intervals_from_logs(
					logs,
					shift.shift_type.determine_check_in_and_check_out,
					shift.shift_type.working_hours_calculation_based_on,
				)
				creditable = approved_permission_hours(
					row.employee, shift.start_datetime, shift.end_datetime, worked
				).hours
		row.creditable_authorized_hours = creditable
		row.compliance_hours = row.actual_worked_hours + creditable
		row.late_approval_review = (
			_("Review Required")
			if row.status == "Approved"
			and attendance.name
			and row.decision_on
			and get_datetime(row.decision_on) > get_datetime(attendance.modified)
			else ""
		)
		permission_date = frappe.utils.getdate(row.permission_date)
		month_start = permission_date.replace(day=1)
		row.monthly_permission_hours = (
			frappe.db.get_value(
				"Attendance Permission Request",
				{
					"employee": row.employee,
					"permission_date": ["between", [month_start, frappe.utils.get_last_day(permission_date)]],
					"status": "Approved",
				},
				[{"SUM": "duration_hours"}],
			)
			or 0
		)
	return columns, data
