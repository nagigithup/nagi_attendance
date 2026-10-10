from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests import UnitTestCase

from nagi_attendance.api import (
	_attendance_code,
	_employees,
	get_today_dashboard,
	get_dashboard_defaults,
	get_leave_dashboard,
	_is_assigned_leave_approver,
	_live_hours,
	_resolve_status,
	_workflow_actions,
)


class TestReportingConfiguration(UnitTestCase):
	def test_assignment_exemption_is_company_scoped_and_not_title_based(self):
		employees = [
			frappe._dict(name="A-REQUIRED", employee_name="Required", company="Company A", designation="Partner"),
			frappe._dict(name="A-EXEMPT", employee_name="Exempt", company="Company A", designation="Employee"),
			frappe._dict(name="B-UNCHANGED", employee_name="Existing", company="Company B", designation="Partner"),
		]
		settings = {
			"Company A": frappe._dict(prevent_automatic_absence=1),
			"Company B": frappe._dict(prevent_automatic_absence=0),
		}
		with (
			patch("nagi_attendance.api.frappe.get_list", return_value=employees) as get_list,
			patch("nagi_attendance.api.frappe.get_all", return_value=["A-REQUIRED"]) as get_all,
			patch("nagi_attendance.api.get_company_settings", side_effect=lambda company: settings[company]),
		):
			rows = _employees(
				department="Legal - A",
				attendance_period=(datetime(2026, 10, 1).date(), datetime(2026, 10, 31).date()),
			)

		self.assertEqual([row.name for row in rows], ["A-REQUIRED", "B-UNCHANGED"])
		self.assertEqual(get_list.call_args.kwargs["filters"]["department"], "Legal - A")
		self.assertEqual(get_all.call_args.kwargs["filters"]["docstatus"], 1)
		self.assertNotIn("status", get_all.call_args.kwargs["filters"])

	def test_existing_behavior_is_unchanged_without_exemption_policy(self):
		employees = [frappe._dict(name="EMP-1", company="Company A")]
		with (
			patch("nagi_attendance.api.frappe.get_list", return_value=employees),
			patch("nagi_attendance.api.frappe.get_all") as get_all,
			patch(
				"nagi_attendance.api.get_company_settings",
				return_value=frappe._dict(prevent_automatic_absence=0),
			),
		):
			rows = _employees(attendance_period=(datetime(2026, 10, 1).date(), datetime(2026, 10, 1).date()))

		self.assertEqual(rows, employees)
		get_all.assert_not_called()

	def test_default_reporting_department_is_independent_per_company(self):
		settings = {
			"Company A": frappe._dict(default_reporting_department="Legal - A"),
			"Company B": frappe._dict(default_reporting_department="Legal - B"),
		}

		def permitted_rows(doctype, **kwargs):
			if doctype == "Company":
				return [kwargs["filters"]["name"]]
			if doctype == "Department":
				return [kwargs["filters"]["name"]]
			return []

		with (
			patch("nagi_attendance.api._require_access"),
			patch("nagi_attendance.api.frappe.get_list", side_effect=permitted_rows),
			patch("nagi_attendance.api.get_company_settings", side_effect=lambda company: settings[company]),
		):
			self.assertEqual(get_dashboard_defaults("Company A")["default_reporting_department"], "Legal - A")
			self.assertEqual(get_dashboard_defaults("Company B")["default_reporting_department"], "Legal - B")

	def test_empty_default_preserves_existing_dashboard_behavior(self):
		with (
			patch("nagi_attendance.api._require_access"),
			patch("nagi_attendance.api.frappe.get_list", return_value=["Company A"]),
			patch(
				"nagi_attendance.api.get_company_settings",
				return_value=frappe._dict(default_reporting_department=None),
			),
		):
			self.assertIsNone(get_dashboard_defaults("Company A")["default_reporting_department"])

	def test_leave_lists_use_the_selected_department_employee_scope(self):
		with (
			patch("nagi_attendance.api._require_access"),
			patch("nagi_attendance.api._employees", return_value=[frappe._dict(name="EMP-LEGAL")]),
			patch("nagi_attendance.api._get_rows", return_value=[]) as get_rows,
		):
			data = get_leave_dashboard("2026-10-10", department="Legal - A")

		self.assertEqual(data["on_leave"], [])
		self.assertEqual(len(get_rows.call_args_list), 3)
		for call in get_rows.call_args_list:
			self.assertEqual(call.args[1]["employee"], ["in", ["EMP-LEGAL"]])


class TestAttendanceLogic(IntegrationTestCase):
	def test_adan_shift_assignments_define_dashboard_attendance_scope(self):
		period = (datetime(2026, 10, 10).date(), datetime(2026, 10, 10).date())
		legal = _employees(department="الإدارة القانونية - ADAN", attendance_period=period)
		management = _employees(department="الإدارة - ADAN", attendance_period=period)
		management_hr_records = _employees(department="الإدارة - ADAN")

		self.assertEqual(len(legal), 3)
		self.assertTrue(all(row.department == "الإدارة القانونية - ADAN" for row in legal))
		self.assertEqual(management, [])
		self.assertEqual(len(management_hr_records), 2)

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
