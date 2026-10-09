from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from nagi_attendance.api import (
	_attendance_code,
	get_today_dashboard,
	_is_assigned_leave_approver,
	_live_hours,
	_resolve_status,
	_workflow_actions,
)


class TestAttendanceLogic(IntegrationTestCase):
	def test_manager_api_access_matches_configured_roles(self):
		original_user = frappe.session.user
		try:
			frappe.set_user("osama@adanlawfirm.com")
			self.assertIn("summary", get_today_dashboard("2026-10-07"))

			frappe.set_user("a.mohsen@adanlawfirm.com")
			with self.assertRaises(frappe.PermissionError):
				get_today_dashboard("2026-10-07")
		finally:
			frappe.set_user(original_user)

	def test_approved_leave_has_highest_priority(self):
		attendance = frappe._dict(status="Absent", leave_type=None, late_entry=0)
		leave = frappe._dict(leave_type="Annual Leave")
		status, detail, late = _resolve_status(
			attendance, leave, "Holiday", [], None, datetime(2026, 10, 4).date()
		)
		self.assertEqual(status, "On Leave")
		self.assertEqual(detail, "Annual Leave")
		self.assertFalse(late)

	def test_holiday_precedes_attendance(self):
		attendance = frappe._dict(status="Absent", leave_type=None, late_entry=0)
		status, detail, _ = _resolve_status(
			attendance, None, "Weekly Off", [], None, datetime(2026, 10, 4).date()
		)
		self.assertEqual(status, "Weekly Off")
		self.assertEqual(detail, "Weekly Off")

	def test_checkin_is_realtime_present(self):
		log = frappe._dict(time=datetime(2026, 10, 4, 8), log_type="IN", shift=None)
		with patch("nagi_attendance.api._late_from_checkin", return_value=False):
			status, _, _ = _resolve_status(None, None, None, [log], None, datetime(2026, 10, 4).date())
		self.assertEqual(status, "Present")

	def test_live_hours_pairs_in_and_out(self):
		logs = [
			frappe._dict(time=datetime(2026, 10, 4, 8), log_type="IN"),
			frappe._dict(time=datetime(2026, 10, 4, 12), log_type="OUT"),
			frappe._dict(time=datetime(2026, 10, 4, 13), log_type="IN"),
		]
		self.assertEqual(_live_hours(logs, datetime(2026, 10, 4, 15, 30)), 6.5)

	def test_monthly_status_codes(self):
		self.assertEqual(_attendance_code("Present"), "P")
		self.assertEqual(_attendance_code("Half Day"), "HD")
		self.assertEqual(_attendance_code("Weekly Off"), "WO")

	def test_native_leave_actions_are_available_to_assigned_approver(self):
		doc = frappe._dict(
			employee="HR-EMP-0001",
			leave_approver=frappe.session.user,
			docstatus=0,
			status="Open",
		)
		with (
			patch("nagi_attendance.api.frappe.get_doc", return_value=doc),
			patch("nagi_attendance.api.frappe.db.get_value", return_value="another.user@example.com"),
			patch("nagi_attendance.api.get_workflow_name", return_value=None),
		):
			self.assertEqual(_workflow_actions("LEAVE-TEST"), ["Approve", "Reject"])

	def test_leave_approver_cannot_approve_own_request(self):
		doc = frappe._dict(employee="HR-EMP-0001", leave_approver=frappe.session.user)
		with patch("nagi_attendance.api.frappe.db.get_value", return_value=frappe.session.user):
			self.assertFalse(_is_assigned_leave_approver(doc))
