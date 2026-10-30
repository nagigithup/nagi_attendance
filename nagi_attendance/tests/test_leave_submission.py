from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from nagi_attendance.mobile_api import create_leave_application


class TestLeaveSubmission(UnitTestCase):
	def test_employee_request_stays_open_for_native_approval(self):
		employee = frappe._dict(name="EMP-SELF", company="Company A")
		doc = Mock(name="native_leave")
		doc.name, doc.status, doc.docstatus = "LEAVE-SELF", "Open", 0
		with (
			patch("nagi_attendance.mobile_api.get_current_employee", return_value=employee) as resolve,
			patch("nagi_attendance.mobile_api.get_company_settings", return_value=frappe._dict(enable_mobile_leave=1)),
			patch("hrms.api.get_leave_types", return_value=["Sick Leave"]),
			patch("hrms.api.get_leave_approval_details", return_value={"leave_approver": "manager@example.com"}),
			patch("nagi_attendance.mobile_api.frappe.get_doc", return_value=doc) as get_doc,
		):
			result = create_leave_application("Sick Leave", "2026-11-08", "2026-11-08", company="Company A")
		resolve.assert_called_once_with("Company A")
		self.assertEqual(get_doc.call_args.args[0]["employee"], "EMP-SELF")
		self.assertEqual(get_doc.call_args.args[0]["company"], "Company A")
		self.assertEqual(get_doc.call_args.args[0]["status"], "Open")
		self.assertEqual(get_doc.call_args.args[0]["leave_approver"], "manager@example.com")
		doc.insert.assert_called_once_with()
		doc.submit.assert_not_called()
		self.assertEqual(result, {"name": "LEAVE-SELF", "status": "Open", "docstatus": 0})

	def test_unavailable_leave_is_rejected_before_insertion(self):
		with (
			patch("nagi_attendance.mobile_api.get_current_employee", return_value=frappe._dict(name="EMP-SELF", company="Company A")),
			patch("nagi_attendance.mobile_api.get_company_settings", return_value=frappe._dict(enable_mobile_leave=1)),
			patch("hrms.api.get_leave_types", return_value=[]),
			patch("nagi_attendance.mobile_api.frappe.get_doc") as get_doc,
			self.assertRaises(frappe.ValidationError),
		):
			create_leave_application("Unallocated Leave", "2026-11-08", "2026-11-08")
		get_doc.assert_not_called()

	def test_native_insert_validation_is_preserved(self):
		doc = Mock()
		doc.insert.side_effect = frappe.ValidationError("Native balance validation")
		with (
			patch("nagi_attendance.mobile_api.get_current_employee", return_value=frappe._dict(name="EMP-SELF", company="Company A")),
			patch("nagi_attendance.mobile_api.get_company_settings", return_value=frappe._dict(enable_mobile_leave=1)),
			patch("hrms.api.get_leave_types", return_value=["Sick Leave"]),
			patch("hrms.api.get_leave_approval_details", return_value={}),
			patch("nagi_attendance.mobile_api.frappe.get_doc", return_value=doc),
			self.assertRaisesRegex(frappe.ValidationError, "Native balance validation"),
		):
			create_leave_application("Sick Leave", "2026-11-08", "2026-11-08")
		doc.submit.assert_not_called()
