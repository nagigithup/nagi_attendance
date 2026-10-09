from __future__ import annotations

import frappe

from nagi_attendance.company import get_company_settings


def prevents_automatic_absence(employee: str) -> bool:
	company = frappe.db.get_value("Employee", employee, "company", cache=True)
	return bool(company and get_company_settings(company).prevent_automatic_absence)


class CompanyAttendancePolicyMixin:
	"""Apply the company-scoped no-log absence policy.

	Native HRMS processing of real Employee Checkin logs remains unchanged, so
	Present attendance, working hours, and late-entry flags continue to use the
	standard Shift Type implementation.
	"""

	def mark_absent_for_dates_with_no_attendance(self, employee: str):
		if prevents_automatic_absence(employee):
			return None
		return super().mark_absent_for_dates_with_no_attendance(employee)

	def mark_absent_for_half_day_dates(self, employee: str):
		if prevents_automatic_absence(employee):
			return None
		return super().mark_absent_for_half_day_dates(employee)


# Backward-compatible import for downstream code and old tests.
AdanPresentOnlyAutoAttendanceMixin = CompanyAttendancePolicyMixin
