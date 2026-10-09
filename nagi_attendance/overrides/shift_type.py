from __future__ import annotations

import frappe

from nagi_attendance.setup.adan_law_firm import COMPANY


def is_adan_employee(employee: str) -> bool:
	return frappe.db.get_value("Employee", employee, "company", cache=True) == COMPANY


class AdanPresentOnlyAutoAttendanceMixin:
	"""Disable automatic absence creation only for Adan employees.

	Native HRMS processing of real Employee Checkin logs remains unchanged, so
	Present attendance, working hours, and late-entry flags continue to use the
	standard Shift Type implementation.
	"""

	def mark_absent_for_dates_with_no_attendance(self, employee: str):
		if is_adan_employee(employee):
			return None
		return super().mark_absent_for_dates_with_no_attendance(employee)

	def mark_absent_for_half_day_dates(self, employee: str):
		if is_adan_employee(employee):
			return None
		return super().mark_absent_for_half_day_dates(employee)
