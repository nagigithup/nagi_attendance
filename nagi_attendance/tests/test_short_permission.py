from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils import get_datetime

from nagi_attendance.api import (
	get_short_permission_context,
	get_short_permission_dashboard,
	get_short_permission_details,
)
from nagi_attendance.company import get_company_settings
from nagi_attendance.nagi_attendance.report.short_permission_register.short_permission_register import (
	execute as permission_report,
)
from nagi_attendance.overrides.shift_type import CompanyAttendancePolicyMixin
from nagi_attendance.short_permission import (
	apply_permission_action,
	approved_permission_hours,
	cancel_permission_request,
	create_permission_request,
	worked_intervals_from_logs,
)


class _NativeAttendanceStub:
	def get_attendance(self, logs, absent, half_day):
		return "Half Day", 7.0, True, True, logs[0].time, logs[-1].time


class _ShiftWithPermission(CompanyAttendancePolicyMixin, _NativeAttendanceStub):
	determine_check_in_and_check_out = "Strictly based on Log Type in Employee Checkin"
	working_hours_calculation_based_on = "Every Valid Check-in and Check-out"


class TestShortPermissionFeatureGate(UnitTestCase):
	def test_missing_company_settings_disable_feature(self):
		with patch("nagi_attendance.company.frappe.db.exists", return_value=False):
			settings = get_company_settings("Company A")
		self.assertEqual(settings.enable_short_permission, 0)

	def test_disabled_company_rejects_submission_before_insert(self):
		employee = frappe._dict(name="EMP-A", company="Company A")
		with (
			patch("nagi_attendance.short_permission.get_current_employee", return_value=employee),
			patch(
				"nagi_attendance.short_permission.get_company_settings",
				return_value=frappe._dict(enable_short_permission=0),
			),
			patch("nagi_attendance.short_permission.frappe.get_doc") as get_doc,
			self.assertRaises(frappe.PermissionError),
		):
			create_permission_request(
				"2026-10-14", "Late Arrival", "08:00", "09:00", "Appointment", "Company A"
			)
		get_doc.assert_not_called()

	def test_disabled_company_does_not_query_or_change_attendance(self):
		settings = frappe._dict(enable_short_permission=0, permission_counted_as_authorized_working_time=1)
		with (
			patch("nagi_attendance.short_permission.frappe.db.get_value", return_value="Company A"),
			patch("nagi_attendance.short_permission.get_company_settings", return_value=settings),
			patch("nagi_attendance.short_permission.frappe.get_all") as get_all,
		):
			result = approved_permission_hours("EMP-A", datetime(2026, 10, 14, 8), datetime(2026, 10, 14, 17))
		self.assertEqual(result.hours, 0)
		get_all.assert_not_called()


class TestShortPermissionAttendance(UnitTestCase):
	def test_approved_hours_are_separate_but_restore_status_and_flags(self):
		logs = [
			frappe._dict(
				employee="EMP-A",
				shift_start=datetime(2026, 10, 14, 8),
				shift_end=datetime(2026, 10, 14, 17),
				time=datetime(2026, 10, 14, 9),
			),
			frappe._dict(
				employee="EMP-A",
				shift_start=datetime(2026, 10, 14, 8),
				shift_end=datetime(2026, 10, 14, 17),
				time=datetime(2026, 10, 14, 16),
			),
		]
		with patch(
			"nagi_attendance.overrides.shift_type.approved_permission_hours",
			return_value=frappe._dict(hours=2, covers_start=True, covers_end=True),
		):
			result = _ShiftWithPermission().get_attendance(logs, 4, 8)
		self.assertEqual(result, ("Present", 7.0, False, False, logs[0].time, logs[-1].time))

	def test_company_isolation_and_union_prevent_double_counting(self):
		settings = frappe._dict(enable_short_permission=1, permission_counted_as_authorized_working_time=1)
		rows = [
			frappe._dict(from_time="08:00", to_time="09:00"),
			frappe._dict(from_time="08:30", to_time="09:30"),
		]
		with (
			patch("nagi_attendance.short_permission.frappe.db.get_value", return_value="Company A"),
			patch("nagi_attendance.short_permission.get_company_settings", return_value=settings),
			patch("nagi_attendance.short_permission.frappe.get_all", return_value=rows) as get_all,
		):
			result = approved_permission_hours("EMP-A", datetime(2026, 10, 14, 8), datetime(2026, 10, 14, 17))
		self.assertEqual(result.hours, 1.5)
		self.assertTrue(result.covers_start)
		self.assertEqual(get_all.call_args.kwargs["filters"]["employee"], "EMP-A")

	def test_no_leave_document_is_created_by_attendance_integration(self):
		settings = frappe._dict(enable_short_permission=1, permission_counted_as_authorized_working_time=1)
		with (
			patch("nagi_attendance.short_permission.frappe.db.get_value", return_value="Company A"),
			patch("nagi_attendance.short_permission.get_company_settings", return_value=settings),
			patch("nagi_attendance.short_permission.frappe.get_all", return_value=[]),
			patch("nagi_attendance.short_permission.frappe.get_doc") as get_doc,
		):
			approved_permission_hours("EMP-A", datetime(2026, 10, 14, 8), datetime(2026, 10, 14, 17))
		get_doc.assert_not_called()

	def test_permission_overlap_with_actual_work_is_not_credited(self):
		settings = frappe._dict(enable_short_permission=1, permission_counted_as_authorized_working_time=1)
		rows = [frappe._dict(from_time="10:00", to_time="12:00")]
		with (
			patch("nagi_attendance.short_permission.frappe.db.get_value", return_value="Company A"),
			patch("nagi_attendance.short_permission.get_company_settings", return_value=settings),
			patch("nagi_attendance.short_permission.frappe.get_all", return_value=rows),
		):
			result = approved_permission_hours(
				"EMP-A",
				datetime(2026, 10, 14, 8),
				datetime(2026, 10, 14, 17),
				[(datetime(2026, 10, 14, 8), datetime(2026, 10, 14, 11))],
			)
		self.assertEqual(result.approved_hours, 2)
		self.assertEqual(result.hours, 1)

	def test_split_checkins_leave_only_the_real_gap_creditable(self):
		logs = [
			frappe._dict(time=datetime(2026, 10, 14, 8), log_type="IN"),
			frappe._dict(time=datetime(2026, 10, 14, 11), log_type="OUT"),
			frappe._dict(time=datetime(2026, 10, 14, 12), log_type="IN"),
			frappe._dict(time=datetime(2026, 10, 14, 17), log_type="OUT"),
		]
		intervals = worked_intervals_from_logs(
			logs, "Strictly based on Log Type in Employee Checkin", "Every Valid Check-in and Check-out"
		)
		self.assertEqual(
			intervals,
			[
				(datetime(2026, 10, 14, 8), datetime(2026, 10, 14, 11)),
				(datetime(2026, 10, 14, 12), datetime(2026, 10, 14, 17)),
			],
		)


class TestShortPermissionWorkflow(IntegrationTestCase):
	def setUp(self):
		self.original_user = frappe.session.user
		self.employee = frappe.db.get_value(
			"Employee",
			{"user_id": "a.mohsen@adanlawfirm.com"},
			["name", "company", "leave_approver"],
			as_dict=True,
		)
		self.original_feature_setting = frappe.db.get_value(
			"Nagi Attendance Settings", self.employee.company, "enable_short_permission"
		)
		frappe.db.set_value("Nagi Attendance Settings", self.employee.company, "enable_short_permission", 1)

	def tearDown(self):
		frappe.db.set_value(
			"Nagi Attendance Settings",
			self.employee.company,
			"enable_short_permission",
			self.original_feature_setting,
		)
		frappe.clear_cache(doctype="Nagi Attendance Settings")
		frappe.set_user(self.original_user)

	def test_employee_submission_manager_approval_and_leave_separation(self):
		leave_count = frappe.db.count("Leave Application", {"employee": self.employee.name})
		frappe.set_user("a.mohsen@adanlawfirm.com")
		result = create_permission_request(
			"2026-10-14", "Temporary Exit", "10:00", "11:00", "Official appointment", self.employee.company
		)
		self.assertEqual(result["status"], "Pending")
		frappe.set_user(self.employee.leave_approver)
		approved = apply_permission_action(result["name"], "Approve", "Approved")
		self.assertEqual(approved["status"], "Approved")
		self.assertEqual(frappe.db.count("Leave Application", {"employee": self.employee.name}), leave_count)
		self.assertEqual(
			frappe.db.get_value("Attendance Permission Request", result["name"], "duration_hours"), 1
		)
		self.assertTrue(
			frappe.db.exists(
				"Version",
				{
					"ref_doctype": "Attendance Permission Request",
					"docname": result["name"],
				},
			)
		)
		self.assertTrue(
			frappe.db.exists(
				"Notification Log",
				{
					"for_user": "a.mohsen@adanlawfirm.com",
					"document_name": result["name"],
				},
			)
		)
		_columns, rows = permission_report(
			{
				"employee": self.employee.name,
				"status": "Approved",
				"from_date": "2026-10-14",
				"to_date": "2026-10-14",
			}
		)
		row = next(value for value in rows if value.name == result["name"])
		self.assertEqual(row.actual_worked_hours, 0)
		self.assertEqual(row.creditable_authorized_hours, 1)
		self.assertEqual(row.compliance_hours, 1)

	def test_manager_dashboard_lists_details_and_refreshes_approval_history(self):
		frappe.set_user(self.employee.leave_approver)
		baseline_pending = get_short_permission_context()["pending_count"]
		frappe.set_user("a.mohsen@adanlawfirm.com")
		request = create_permission_request(
			"2026-10-15",
			"Temporary Exit",
			"10:00",
			"11:00",
			"Dashboard approval",
			self.employee.company,
		)

		frappe.set_user(self.employee.leave_approver)
		context = get_short_permission_context()
		self.assertTrue(context["visible"])
		self.assertEqual(context["pending_count"], baseline_pending + 1)
		pending = get_short_permission_dashboard(
			status="Pending", employee=self.employee.name, from_date="2026-10-15", to_date="2026-10-15"
		)
		self.assertEqual(pending["total"], 1)
		self.assertEqual(pending["summary"]["pending"], 1)
		self.assertEqual(pending["rows"][0]["name"], request["name"])
		self.assertTrue(pending["rows"][0]["can_action"])

		details = get_short_permission_details(request["name"])
		self.assertEqual(details["request"]["employee"], self.employee.name)
		self.assertTrue(details["request"]["can_action"])
		self.assertIn("attendance", details)

		apply_permission_action(request["name"], "Approve", "Approved in manager dashboard")
		self.assertEqual(get_short_permission_context()["pending_count"], baseline_pending)
		approved = get_short_permission_dashboard(
			status="Approved", employee=self.employee.name, from_date="2026-10-15", to_date="2026-10-15"
		)
		self.assertEqual(approved["total"], 1)
		self.assertEqual(approved["summary"]["approved"], 1)
		self.assertEqual(approved["summary"]["approved_hours"], 1)
		self.assertFalse(approved["rows"][0]["can_action"])

	def test_assigned_hr_user_manager_sees_and_approves_only_assigned_request(self):
		employee = frappe.db.get_value(
			"Employee",
			{"user_id": "osama@adanlawfirm.com"},
			["name", "company", "leave_approver"],
			as_dict=True,
		)
		self.assertEqual(employee.leave_approver, "abdulrahman@adanlawfirm.com")
		frappe.set_user(employee.leave_approver)
		baseline_pending = get_short_permission_context()["pending_count"]

		frappe.set_user("osama@adanlawfirm.com")
		request = create_permission_request(
			"2026-10-16", "Temporary Exit", "10:00", "11:00", "Assigned manager test", employee.company
		)
		frappe.set_user(employee.leave_approver)
		self.assertEqual(get_short_permission_context()["pending_count"], baseline_pending + 1)
		pending = get_short_permission_dashboard(
			status="Pending", employee=employee.name, from_date="2026-10-16", to_date="2026-10-16"
		)
		self.assertEqual([row.name for row in pending["rows"]], [request["name"]])
		self.assertTrue(pending["rows"][0]["can_action"])
		self.assertEqual(apply_permission_action(request["name"], "Approve")["status"], "Approved")

	def test_rejection_cancellation_and_unauthorized_access(self):
		frappe.set_user("a.mohsen@adanlawfirm.com")
		to_reject = create_permission_request(
			"2026-10-14", "Temporary Exit", "11:00", "12:00", "Personal appointment", self.employee.company
		)
		frappe.set_user(self.employee.leave_approver)
		self.assertEqual(
			apply_permission_action(to_reject["name"], "Reject", "Not approved")["status"], "Rejected"
		)

		frappe.set_user("a.mohsen@adanlawfirm.com")
		to_cancel = create_permission_request(
			"2026-10-14", "Temporary Exit", "12:00", "13:00", "No longer needed", self.employee.company
		)
		self.assertEqual(
			cancel_permission_request(to_cancel["name"], self.employee.company)["status"], "Cancelled"
		)
		pending = create_permission_request(
			"2026-10-14", "Temporary Exit", "14:00", "15:00", "Manager review", self.employee.company
		)

		frappe.set_user("mohammed@adanlawfirm.com")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Attendance Permission Request", to_reject["name"]).check_permission("read")
		with self.assertRaises(frappe.PermissionError):
			apply_permission_action(pending["name"], "Approve")
		with self.assertRaises(frappe.PermissionError):
			get_short_permission_details(pending["name"])

	def test_hr_and_system_administrators_can_view_history(self):
		frappe.set_user("a.mohsen@adanlawfirm.com")
		request = create_permission_request(
			"2026-10-14", "Temporary Exit", "13:00", "14:00", "Administrative visit", self.employee.company
		)
		for user in ("osama@adanlawfirm.com", "Administrator"):
			frappe.set_user(user)
			doc = frappe.get_doc("Attendance Permission Request", request["name"])
			self.assertTrue(doc.has_permission("read"))

	def test_late_approval_flags_review_without_rewriting_submitted_attendance(self):
		frappe.set_user("Administrator")
		attendance = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.employee.name,
				"company": self.employee.company,
				"attendance_date": "2026-10-14",
				"status": "Half Day",
				"working_hours": 4,
			}
		).insert(ignore_permissions=True)
		attendance.submit()
		attendance_modified = attendance.modified

		frappe.set_user("a.mohsen@adanlawfirm.com")
		request = create_permission_request(
			"2026-10-14", "Late Arrival", "09:00", "10:00", "Late-approved request", self.employee.company
		)
		frappe.set_user(self.employee.leave_approver)
		apply_permission_action(request["name"], "Approve", "Approved after attendance")

		_columns, rows = permission_report({"employee": self.employee.name, "status": "Approved"})
		row = next(value for value in rows if value.name == request["name"])
		self.assertEqual(row.late_approval_review, "Review Required")
		unchanged = frappe.get_doc("Attendance", attendance.name)
		self.assertEqual(unchanged.docstatus, 1)
		self.assertEqual(unchanged.status, "Half Day")
		self.assertEqual(unchanged.working_hours, 4)
		self.assertEqual(unchanged.modified, get_datetime(attendance_modified))
