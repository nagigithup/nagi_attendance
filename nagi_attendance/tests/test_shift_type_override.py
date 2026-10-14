from unittest.mock import patch

from frappe.tests import UnitTestCase

from nagi_attendance.overrides.shift_type import CompanyAttendancePolicyMixin


class _NativeShiftTypeStub:
	def __init__(self):
		self.no_log_absence_calls = []
		self.half_day_absence_calls = []

	def mark_absent_for_dates_with_no_attendance(self, employee):
		self.no_log_absence_calls.append(employee)
		return "native-no-log"

	def mark_absent_for_half_day_dates(self, employee):
		self.half_day_absence_calls.append(employee)
		return "native-half-day"


class _ShiftTypeUnderTest(CompanyAttendancePolicyMixin, _NativeShiftTypeStub):
	pass


class TestCompanyAttendancePolicy(UnitTestCase):
	def test_configured_company_does_not_generate_absence_without_checkins(self):
		shift = _ShiftTypeUnderTest()
		with (
			patch("nagi_attendance.overrides.shift_type.frappe.db.get_value", return_value="Company A"),
			patch("nagi_attendance.overrides.shift_type.get_company_settings") as settings,
		):
			settings.return_value.prevent_automatic_absence = 1
			self.assertIsNone(shift.mark_absent_for_dates_with_no_attendance("HR-EMP-00003"))
			self.assertIsNone(shift.mark_absent_for_half_day_dates("HR-EMP-00003"))

		self.assertEqual(shift.no_log_absence_calls, [])
		self.assertEqual(shift.half_day_absence_calls, [])

	def test_other_companies_keep_native_hrms_absence_processing(self):
		shift = _ShiftTypeUnderTest()
		with (
			patch("nagi_attendance.overrides.shift_type.frappe.db.get_value", return_value="Company B"),
			patch("nagi_attendance.overrides.shift_type.get_company_settings") as settings,
		):
			settings.return_value.prevent_automatic_absence = 0
			self.assertEqual(shift.mark_absent_for_dates_with_no_attendance("HR-EMP-OTHER"), "native-no-log")
			self.assertEqual(shift.mark_absent_for_half_day_dates("HR-EMP-OTHER"), "native-half-day")

		self.assertEqual(shift.no_log_absence_calls, ["HR-EMP-OTHER"])
		self.assertEqual(shift.half_day_absence_calls, ["HR-EMP-OTHER"])
