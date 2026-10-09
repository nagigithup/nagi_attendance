from __future__ import annotations

from datetime import date, timedelta

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import getdate


COMPANY = "أدن للمحاماة والاستشارات القانونية"
COMPANY_ABBR = "ADAN"
COUNTRY = "Saudi Arabia"
CURRENCY = "SAR"
TIME_ZONE = "Asia/Riyadh"
HOLIDAY_LIST = "أدن - عطلات السعودية 2026"
OFFICE_LOCATION = "شركة أدان للمحاماة | ADAN LAW FIRM"
OFFICE_ADDRESS = "شارع بحر العرب، الخليج، الرياض 13224، المملكة العربية السعودية"
OFFICE_MAP_URL = "https://maps.app.goo.gl/HuDpLxp7xA95nw889?g_st=ic"
OFFICE_LATITUDE = 24.7870341
OFFICE_LONGITUDE = 46.8051581
TEST_GEOFENCE_RADIUS_METERS = 100
ATTENDANCE_GO_LIVE_DATE = date(2026, 10, 7)
LEAVE_PERIOD = "فترة الإجازات 2026 - أدن"
LEAVE_POLICY = "سياسة الإجازات النظامية 2026 - تحتاج مراجعة"
MANAGEMENT_DEPARTMENT = "الإدارة"
LEGAL_DEPARTMENT = "الإدارة القانونية"
CONFIRMED_GENDER = "Male"

EMPLOYEES = (
	{
		"employee_name": "أسامة الزهراني",
		"email": "osama@adanlawfirm.com",
		"designation": "Partner",
		"roles": ("Employee", "HR User", "HR Manager", "Leave Approver"),
		"team_attendance_access": True,
		"department": MANAGEMENT_DEPARTMENT,
		"leave_approver": "abdulrahman@adanlawfirm.com",
		"shift": None,
	},
	{
		"employee_name": "عبدالرحمن السلمي",
		"email": "abdulrahman@adanlawfirm.com",
		"designation": "Partner",
		"roles": ("Employee", "HR User", "Leave Approver"),
		"team_attendance_access": True,
		"department": MANAGEMENT_DEPARTMENT,
		"leave_approver": "osama@adanlawfirm.com",
		"shift": None,
	},
	{
		"employee_name": "عبدالرحمن الحربي",
		"email": "a.mohsen@adanlawfirm.com",
		"designation": "Employee",
		"roles": ("Employee",),
		"team_attendance_access": False,
		"department": LEGAL_DEPARTMENT,
		"leave_approver": "osama@adanlawfirm.com",
		"shift": "دوام المكتب 09:00-15:00",
	},
	{
		"employee_name": "محمد الغامدي",
		"email": "mohammed@adanlawfirm.com",
		"designation": "Employee",
		"roles": ("Employee",),
		"team_attendance_access": False,
		"department": LEGAL_DEPARTMENT,
		"leave_approver": "osama@adanlawfirm.com",
		"shift": "دوام المكتب 09:00-15:00",
	},
	{
		"employee_name": "عثمان عمر",
		"email": "othman@adanlawfirm.com",
		"designation": "Employee",
		"roles": ("Employee",),
		"team_attendance_access": False,
		"department": LEGAL_DEPARTMENT,
		"leave_approver": "osama@adanlawfirm.com",
		"shift": "دوام المكتب 09:00-16:00",
	},
)

SHIFT_TYPES = (
	{"name": "دوام المكتب 09:00-15:00", "start_time": "09:00:00", "end_time": "15:00:00"},
	{"name": "دوام المكتب 09:00-16:00", "start_time": "09:00:00", "end_time": "16:00:00"},
)

LEAVE_TYPES = (
	{"name": "إجازة سنوية", "max_leaves_allowed": 30},
	{"name": "إجازة مرضية", "max_leaves_allowed": 120},
	{"name": "إجازة بدون راتب", "is_lwp": 1},
	{"name": "إجازة زواج", "max_leaves_allowed": 5},
	{"name": "إجازة وفاة", "max_leaves_allowed": 5},
	{"name": "إجازة وفاة أخ أو أخت", "max_leaves_allowed": 3},
	{"name": "إجازة مولود", "max_leaves_allowed": 3},
	{"name": "إجازة حج", "max_leaves_allowed": 15},
	{"name": "إجازة اختبارات", "max_leaves_allowed": 0},
	{"name": "إجازة أمومة", "max_leaves_allowed": 84},
)


def execute(genders: dict[str, str] | str | None = None) -> dict:
	"""Configure the confirmed Adan HR settings without creating duplicate records.

	All five employees are confirmed male in the final implementation instructions.
	`genders` remains available as an explicit, validated override for safe reuse.
	"""
	if isinstance(genders, str):
		genders = frappe.parse_json(genders)
	confirmed_genders = {row["email"]: CONFIRMED_GENDER for row in EMPLOYEES}
	confirmed_genders.update(genders or {})

	report = {"created": [], "updated": [], "skipped": [], "blockers": []}
	_ensure_company(report)
	_ensure_settings(report)
	_ensure_employee_flags(report)
	_ensure_designations(report)
	_ensure_gender(report)
	_ensure_departments(report)
	_ensure_holiday_list(report)
	_ensure_holiday_list_assignment(report)
	_ensure_shift_location(report)
	_ensure_shift_types(report)
	_ensure_leave_configuration(report)
	_ensure_users(report)
	_ensure_employees(confirmed_genders, report)
	_ensure_manager_user_permissions(report)
	_ensure_user_roles(report)
	frappe.db.commit()
	return report


def _record(report: dict, action: str, doctype: str, name: str) -> None:
	report[action].append(f"{doctype}: {name}")


def _ensure_company(report: dict) -> None:
	if frappe.db.exists("Company", COMPANY):
		_record(report, "skipped", "Company", COMPANY)
		return

	if frappe.db.count("Company"):
		frappe.throw("The isolated Adan site must not contain a different Company before setup.")

	from erpnext.setup.setup_wizard.setup_wizard import setup_complete

	setup_complete(
		frappe._dict(
			company_name=COMPANY,
			company_abbr=COMPANY_ABBR,
			country=COUNTRY,
			currency=CURRENCY,
			chart_of_accounts="Standard",
			domain=None,
			fy_start_date="2026-01-01",
			fy_end_date="2026-12-31",
			bank_account=None,
		)
	)
	_record(report, "created", "Company", COMPANY)


def _ensure_settings(report: dict) -> None:
	system_settings = frappe.get_single("System Settings")
	system_settings.update(
		{
			"country": COUNTRY,
			"language": "ar",
			"time_zone": TIME_ZONE,
			"date_format": "yyyy-mm-dd",
			"time_format": "HH:mm",
			"first_day_of_the_week": "Sunday",
		}
	)
	system_settings.save(ignore_permissions=True)

	global_defaults = frappe.get_single("Global Defaults")
	global_defaults.update(
		{"default_company": COMPANY, "default_currency": CURRENCY, "country": COUNTRY}
	)
	global_defaults.save(ignore_permissions=True)

	hr_settings = frappe.get_single("HR Settings")
	hr_settings.update(
		{
			"allow_employee_checkin_from_mobile_app": 1,
			"allow_geolocation_tracking": 1,
			"leave_approver_mandatory_in_leave_application": 1,
			"prevent_self_leave_approval": 1,
			"send_leave_notification": 0,
		}
	)
	hr_settings.save(ignore_permissions=True)

	company = frappe.get_doc("Company", COMPANY)
	company.default_holiday_list = HOLIDAY_LIST if frappe.db.exists("Holiday List", HOLIDAY_LIST) else None
	company.save(ignore_permissions=True)
	frappe.db.set_default("lang", "ar")
	frappe.db.set_default("company", COMPANY)
	_record(report, "updated", "Settings", "System, Global and HR")


def _ensure_employee_flags(report: dict) -> None:
	create_custom_fields(
		{
			"Employee": [
				{
					"fieldname": "custom_provisional_date_of_birth",
					"label": "تاريخ الميلاد مبدئي وغير موثق",
					"fieldtype": "Check",
					"insert_after": "date_of_birth",
					"default": "0",
					"description": "للاختبار المحلي فقط؛ يجب التحقق قبل الإنتاج أو أي استخدام نظامي.",
				},
				{
					"fieldname": "custom_joining_date_requires_confirmation",
					"label": "تاريخ الالتحاق يحتاج تأكيدًا",
					"fieldtype": "Check",
					"insert_after": "date_of_joining",
					"default": "0",
					"description": "يجب تأكيد التاريخ قبل احتساب الاستحقاقات المرتبطة بمدة الخدمة.",
				},
			]
		},
		update=True,
	)
	_record(report, "updated", "Custom Field", "Employee verification flags")


def _ensure_designations(report: dict) -> None:
	for designation in ("Partner", "Employee"):
		if not frappe.db.exists("Designation", designation):
			frappe.get_doc({"doctype": "Designation", "designation_name": designation}).insert(
				ignore_permissions=True
			)
			_record(report, "created", "Designation", designation)
		else:
			_record(report, "skipped", "Designation", designation)


def _ensure_gender(report: dict) -> None:
	if frappe.db.exists("Gender", CONFIRMED_GENDER):
		_record(report, "skipped", "Gender", CONFIRMED_GENDER)
		return
	frappe.get_doc({"doctype": "Gender", "gender": CONFIRMED_GENDER}).insert(ignore_permissions=True)
	_record(report, "created", "Gender", CONFIRMED_GENDER)


def _ensure_departments(report: dict) -> None:
	for department_name in (MANAGEMENT_DEPARTMENT, LEGAL_DEPARTMENT):
		name = frappe.db.get_value(
			"Department", {"department_name": department_name, "company": COMPANY}, "name"
		)
		if name:
			_record(report, "skipped", "Department", name)
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Department",
				"department_name": department_name,
				"company": COMPANY,
				"parent_department": "All Departments",
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		_record(report, "created", "Department", doc.name)


def _department_docname(department_name: str) -> str:
	name = frappe.db.get_value(
		"Department", {"department_name": department_name, "company": COMPANY}, "name"
	)
	if not name:
		frappe.throw(f"Department was not configured: {department_name}")
	return name


def _holiday_rows() -> list[dict]:
	rows = []
	day = date(2026, 1, 1)
	while day <= date(2026, 12, 31):
		if day.weekday() in (4, 5):
			rows.append(
				{
					"holiday_date": day,
					"description": "عطلة أسبوعية - الجمعة" if day.weekday() == 4 else "عطلة أسبوعية - السبت",
					"weekly_off": 1,
				}
			)
		day += timedelta(days=1)
	rows.extend(
		(
			{"holiday_date": "2026-02-22", "description": "يوم التأسيس السعودي"},
			{"holiday_date": "2026-09-23", "description": "اليوم الوطني السعودي"},
		)
	)
	return sorted(rows, key=lambda row: getdate(row["holiday_date"]))


def _ensure_holiday_list(report: dict) -> None:
	values = {
		"holiday_list_name": HOLIDAY_LIST,
		"from_date": "2026-01-01",
		"to_date": "2026-12-31",
		"country": COUNTRY,
		"holidays": _holiday_rows(),
	}
	if frappe.db.exists("Holiday List", HOLIDAY_LIST):
		doc = frappe.get_doc("Holiday List", HOLIDAY_LIST)
		doc.update(values)
		doc.set("holidays", values["holidays"])
		doc.save(ignore_permissions=True)
		_record(report, "updated", "Holiday List", HOLIDAY_LIST)
	else:
		doc = frappe.get_doc({"doctype": "Holiday List", **values})
		doc.insert(ignore_permissions=True)
		_record(report, "created", "Holiday List", HOLIDAY_LIST)

	frappe.db.set_value("Company", COMPANY, "default_holiday_list", HOLIDAY_LIST)


def _ensure_holiday_list_assignment(report: dict) -> None:
	"""Use HRMS v16's effective-dated assignment model for all company employees."""
	filters = {
		"applicable_for": "Company",
		"assigned_to": COMPANY,
		"from_date": "2026-01-01",
		"docstatus": 1,
	}
	name = frappe.db.get_value("Holiday List Assignment", filters, "name")
	if name:
		assignment = frappe.get_doc("Holiday List Assignment", name)
		if assignment.holiday_list != HOLIDAY_LIST:
			frappe.throw(f"A different Holiday List Assignment already exists for {COMPANY}: {name}")
		_record(report, "skipped", "Holiday List Assignment", name)
		return

	assignment = frappe.get_doc(
		{
			"doctype": "Holiday List Assignment",
			"applicable_for": "Company",
			"assigned_to": COMPANY,
			"holiday_list": HOLIDAY_LIST,
			"from_date": "2026-01-01",
		}
	)
	assignment.insert(ignore_permissions=True)
	assignment.submit()
	_record(report, "created", "Holiday List Assignment", assignment.name)


def _ensure_shift_location(report: dict) -> None:
	values = {
		"location_name": OFFICE_LOCATION,
		"latitude": OFFICE_LATITUDE,
		"longitude": OFFICE_LONGITUDE,
		"checkin_radius": TEST_GEOFENCE_RADIUS_METERS,
	}
	if frappe.db.exists("Shift Location", OFFICE_LOCATION):
		doc = frappe.get_doc("Shift Location", OFFICE_LOCATION)
		doc.update(values)
		doc.save(ignore_permissions=True)
		_record(report, "updated", "Shift Location", OFFICE_LOCATION)
	else:
		frappe.get_doc({"doctype": "Shift Location", **values}).insert(ignore_permissions=True)
		_record(report, "created", "Shift Location", OFFICE_LOCATION)


def _ensure_shift_types(report: dict) -> None:
	for definition in SHIFT_TYPES:
		values = {
			**definition,
			"holiday_list": HOLIDAY_LIST,
			"enable_auto_attendance": 1,
			"determine_check_in_and_check_out": "Strictly based on Log Type in Employee Checkin",
			"working_hours_calculation_based_on": "First Check-in and Last Check-out",
			"begin_check_in_before_shift_start_time": 30,
			"allow_check_out_after_shift_end_time": 30,
			"working_hours_threshold_for_half_day": 0,
			"working_hours_threshold_for_absent": 0,
			"enable_late_entry_marking": 1,
			"late_entry_grace_period": 10,
			"enable_early_exit_marking": 0,
			"mark_auto_attendance_on_holidays": 0,
			"process_attendance_after": ATTENDANCE_GO_LIVE_DATE,
			"auto_update_last_sync": 1,
		}
		if frappe.db.exists("Shift Type", definition["name"]):
			doc = frappe.get_doc("Shift Type", definition["name"])
			doc.update(values)
			doc.save(ignore_permissions=True)
			_record(report, "updated", "Shift Type", definition["name"])
		else:
			frappe.get_doc({"doctype": "Shift Type", **values}).insert(ignore_permissions=True)
			_record(report, "created", "Shift Type", definition["name"])


def _ensure_leave_configuration(report: dict) -> None:
	period_name = frappe.db.get_value(
		"Leave Period",
		{"company": COMPANY, "from_date": "2026-01-01", "to_date": "2026-12-31"},
		"name",
	)
	if not period_name:
		frappe.get_doc(
			{
				"doctype": "Leave Period",
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"company": COMPANY,
				"is_active": 1,
			}
		).insert(ignore_permissions=True)
		_record(report, "created", "Leave Period", LEAVE_PERIOD)
	else:
		_record(report, "skipped", "Leave Period", period_name)

	for definition in LEAVE_TYPES:
		values = {
			"leave_type_name": definition["name"],
			"is_lwp": definition.get("is_lwp", 0),
			"max_leaves_allowed": definition.get("max_leaves_allowed", 0),
			"allow_negative": 0,
			"allow_over_allocation": 0,
			"include_holiday": 0,
			"is_carry_forward": 0,
		}
		if frappe.db.exists("Leave Type", definition["name"]):
			doc = frappe.get_doc("Leave Type", definition["name"])
			doc.update(values)
			doc.save(ignore_permissions=True)
			_record(report, "updated", "Leave Type", definition["name"])
		else:
			frappe.get_doc({"doctype": "Leave Type", **values}).insert(ignore_permissions=True)
			_record(report, "created", "Leave Type", definition["name"])

	# Keep the policy in draft and do not allocate balances while joining dates are
	# provisional.  Only annual leave belongs in this annual allocation template:
	# sick leave has statutory pay tiers and event leave is granted when the event
	# occurs, so treating either as a reusable yearly balance would be misleading.
	details = [
		{"leave_type": "إجازة سنوية", "annual_allocation": 21},
	]
	policy_name = frappe.db.get_value("Leave Policy", {"title": LEAVE_POLICY}, "name")
	if policy_name:
		doc = frappe.get_doc("Leave Policy", policy_name)
		doc.set("leave_policy_details", details)
		doc.save(ignore_permissions=True)
		_record(report, "updated", "Leave Policy (Draft)", LEAVE_POLICY)
	else:
		frappe.get_doc(
			{"doctype": "Leave Policy", "title": LEAVE_POLICY, "leave_policy_details": details}
		).insert(ignore_permissions=True)
		_record(report, "created", "Leave Policy (Draft)", LEAVE_POLICY)


def _ensure_users(report: dict) -> None:
	for definition in EMPLOYEES:
		email = definition["email"]
		if frappe.db.exists("User", email):
			user = frappe.get_doc("User", email)
			user.enabled = 1
			user.language = "ar"
			user.time_zone = TIME_ZONE
			user.send_welcome_email = 0
			user.save(ignore_permissions=True)
			_record(report, "updated", "User", email)
		else:
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": definition["employee_name"],
					"full_name": definition["employee_name"],
					"enabled": 1,
					"language": "ar",
					"time_zone": TIME_ZONE,
					"user_type": "System User",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
			_record(report, "created", "User", email)


def _ensure_user_roles(report: dict) -> None:
	"""Assign employee-dependent roles only after the linked Employee exists."""
	for definition in EMPLOYEES:
		user = frappe.get_doc("User", definition["email"])
		for role in definition["roles"]:
			if role not in frappe.get_roles(definition["email"]):
				user.add_roles(role)
				_record(report, "updated", "User Role", f"{definition['email']} / {role}")


def _ensure_manager_user_permissions(report: dict) -> None:
	"""Let designated managers see the ADAN team while keeping company isolation."""
	from frappe.permissions import add_user_permission, remove_user_permission

	for definition in EMPLOYEES:
		if not definition["team_attendance_access"]:
			continue
		employee = frappe.db.get_value("Employee", {"user_id": definition["email"]}, "name")
		if frappe.db.exists(
			"User Permission",
			{"user": definition["email"], "allow": "Employee", "for_value": employee},
		):
			remove_user_permission("Employee", employee, definition["email"], ignore_permissions=True)
			_record(report, "updated", "User Permission", f"{definition['email']} / ADAN team access")
		if not frappe.db.exists(
			"User Permission",
			{"user": definition["email"], "allow": "Company", "for_value": COMPANY},
		):
			add_user_permission("Company", COMPANY, definition["email"], ignore_permissions=True)
			_record(report, "updated", "User Permission", f"{definition['email']} / {COMPANY}")


def _ensure_employees(genders: dict[str, str], report: dict) -> None:
	missing = [row["email"] for row in EMPLOYEES if not genders.get(row["email"])]
	if missing:
		report["blockers"].append(
			"Employee.gender is mandatory and was not supplied for: " + ", ".join(missing)
		)
		return

	for definition in EMPLOYEES:
		email = definition["email"]
		gender = genders[email]
		if not frappe.db.exists("Gender", gender):
			frappe.throw(f"Unknown Gender value for {email}: {gender}")
		values = {
			"first_name": definition["employee_name"],
			"employee_name": definition["employee_name"],
			"user_id": email,
			"company": COMPANY,
			"status": "Active",
			"gender": gender,
			"date_of_birth": "1990-01-01",
			"date_of_joining": "2026-01-01",
			"designation": definition["designation"],
			"department": _department_docname(definition["department"]),
			"holiday_list": HOLIDAY_LIST,
			"default_shift": definition["shift"],
			"leave_approver": definition["leave_approver"],
			"custom_provisional_date_of_birth": 1,
			"custom_joining_date_requires_confirmation": 1,
			"create_user_permission": 0 if definition["team_attendance_access"] else 1,
		}
		name = frappe.db.get_value("Employee", {"user_id": email}, "name")
		if name:
			employee = frappe.get_doc("Employee", name)
			employee.update(values)
			employee.save(ignore_permissions=True)
			_record(report, "updated", "Employee", name)
		else:
			employee = frappe.get_doc({"doctype": "Employee", **values})
			employee.insert(ignore_permissions=True)
			_record(report, "created", "Employee", employee.name)

		if definition["shift"]:
			_ensure_shift_assignment(employee.name, definition["shift"], report)


def _ensure_shift_assignment(employee: str, shift_type: str, report: dict) -> None:
	filters = {
		"employee": employee,
		"shift_type": shift_type,
		"docstatus": 1,
		"status": "Active",
	}
	assignment_name = frappe.db.get_value("Shift Assignment", filters, "name", order_by="start_date desc")
	if assignment_name:
		assignment = frappe.get_doc("Shift Assignment", assignment_name)
		if getdate(assignment.start_date) == ATTENDANCE_GO_LIVE_DATE:
			_record(report, "skipped", "Shift Assignment", f"{employee} / {shift_type}")
			return

		# Submitted start dates cannot be edited safely. Cancel and replace the
		# assignment so native HRMS link and overlap validations remain in force.
		assignment.cancel()
		_record(report, "updated", "Shift Assignment", f"{assignment.name} (cancelled)")

	assignment = frappe.get_doc(
		{
			"doctype": "Shift Assignment",
			"employee": employee,
			"shift_type": shift_type,
			"shift_location": OFFICE_LOCATION,
			"start_date": ATTENDANCE_GO_LIVE_DATE,
			"status": "Active",
		}
	)
	assignment.insert(ignore_permissions=True)
	assignment.submit()
	_record(report, "created", "Shift Assignment", assignment.name)
