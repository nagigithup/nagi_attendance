from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint


PRODUCT_NAME = "Nagi Attendance & Leave"
DEFAULT_BRAND_COLOR = "#176B5B"


def require_authenticated_user() -> str:
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Please sign in to continue."), frappe.PermissionError)
	return user


def get_user_employees(user: str | None = None) -> list[frappe._dict]:
	user = user or require_authenticated_user()
	return frappe.get_all(
		"Employee",
		filters={"user_id": user, "status": "Active"},
		fields=[
			"name", "employee_name", "first_name", "image", "designation", "department",
			"company", "default_shift", "holiday_list", "reports_to", "leave_approver", "user_id",
		],
		order_by="company asc, modified desc",
	)


def get_current_employee(company: str | None = None) -> frappe._dict:
	employees = get_user_employees()
	if company:
		employees = [row for row in employees if row.company == company]
	if not employees:
		frappe.throw(_("No active employee record is linked to your user for this company."), frappe.PermissionError)
	if len(employees) > 1 and not company:
		# A deterministic default is safe; all selectable companies are returned by bootstrap.
		return employees[0]
	return employees[0]


def get_company_settings(company: str) -> frappe._dict:
	if frappe.db.exists("Nagi Attendance Settings", company):
		doc = frappe.get_cached_doc("Nagi Attendance Settings", company)
		return frappe._dict(doc.as_dict())
	return frappe._dict(
		company=company,
		enable_mobile_attendance=1,
		enable_mobile_leave=1,
		allow_attendance_history=1,
		enable_gps_validation=0,
		default_geofence_radius=0,
		attendance_start_date=None,
		prevent_automatic_absence=0,
		default_language="ar",
		brand_primary_color=DEFAULT_BRAND_COLOR,
		allowed_locations=[],
	)


def is_feature_enabled(company: str, fieldname: str, default: bool = True) -> bool:
	settings = get_company_settings(company)
	value = settings.get(fieldname)
	return default if value is None else bool(cint(value))


def company_brand(company: str) -> dict:
	settings = get_company_settings(company)
	company_doc = frappe.db.get_value(
		"Company",
		company,
		["name", "abbr", "company_logo", "default_currency"],
		as_dict=True,
	) or frappe._dict(name=company)
	return {
		"name": company_doc.name,
		"abbr": company_doc.abbr,
		"logo": company_doc.company_logo,
		"currency": company_doc.default_currency,
		"timezone": frappe.utils.get_system_timezone(),
		"primary_color": settings.brand_primary_color or DEFAULT_BRAND_COLOR,
		"default_language": settings.default_language or "ar",
		"product_name": PRODUCT_NAME,
	}
