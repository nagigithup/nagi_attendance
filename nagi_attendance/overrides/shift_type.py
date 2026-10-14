from __future__ import annotations

import frappe
from frappe.utils import flt

from nagi_attendance.company import get_company_settings
from nagi_attendance.short_permission import approved_permission_hours, worked_intervals_from_logs


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

	def get_attendance(self, logs, working_hours_threshold_for_absent, working_hours_threshold_for_half_day):
		result = super().get_attendance(
			logs, working_hours_threshold_for_absent, working_hours_threshold_for_half_day
		)
		status, actual_hours, late_entry, early_exit, in_time, out_time = result
		if not logs:
			return result
		worked_intervals = worked_intervals_from_logs(
			logs, self.determine_check_in_and_check_out, self.working_hours_calculation_based_on
		)
		permission = approved_permission_hours(
			logs[0].employee, logs[0].shift_start, logs[0].shift_end, worked_intervals
		)
		if not permission.hours:
			return result
		effective_hours = flt(actual_hours) + flt(permission.hours)
		if working_hours_threshold_for_absent and effective_hours < working_hours_threshold_for_absent:
			status = "Absent"
		elif working_hours_threshold_for_half_day and effective_hours < working_hours_threshold_for_half_day:
			status = "Half Day"
		else:
			status = "Present"
		# Keep native actual worked hours unchanged. Authorized hours live on the
		# permission record/report and only affect thresholds and covered flags.
		if permission.covers_start:
			late_entry = False
		if permission.covers_end:
			early_exit = False
		return status, actual_hours, late_entry, early_exit, in_time, out_time


# Backward-compatible import for downstream code and old tests.
AdanPresentOnlyAutoAttendanceMixin = CompanyAttendancePolicyMixin
