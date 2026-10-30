from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from nagi_attendance.api import get_manager_pending_context
from nagi_attendance.leave_approval import decide_leave, leave_actions


class TestManagerLeaveSecurity(UnitTestCase):
	def test_processed_and_self_requests_have_no_actions(self):
		for status, docstatus in (("Approved", 1), ("Rejected", 1), ("Cancelled", 2)):
			doc = frappe._dict(status=status, docstatus=docstatus)
			self.assertEqual(leave_actions(doc), [])
		with patch("nagi_attendance.leave_approval.is_assigned_approver", return_value=False):
			self.assertEqual(leave_actions(frappe._dict(status="Open", docstatus=0)), [])

	def test_native_permissions_are_required_for_actionable_requests(self):
		doc = Mock(docstatus=0, status="Open")
		doc.has_permission.side_effect = lambda ptype: ptype == "write"
		with (
			patch("nagi_attendance.leave_approval.is_assigned_approver", return_value=True),
			patch("nagi_attendance.leave_approval.check_leave_scope"),
			patch("nagi_attendance.leave_approval.get_workflow_name", return_value=""),
		):
			self.assertEqual(leave_actions(doc), [])

	def test_workflow_actions_keep_configured_names_and_are_deduplicated(self):
		doc = Mock(docstatus=0, status="Open")
		with (
			patch("nagi_attendance.leave_approval.is_assigned_approver", return_value=True),
			patch("nagi_attendance.leave_approval.check_leave_scope"),
			patch("nagi_attendance.leave_approval.get_workflow_name", return_value="Custom workflow"),
			patch("nagi_attendance.leave_approval.get_transitions", return_value=[frappe._dict(action="Authorize leave"), frappe._dict(action="Authorize leave"), frappe._dict(action="Decline leave")]),
		):
			self.assertEqual(leave_actions(doc), ["Authorize leave", "Decline leave"])

	def test_decision_locks_before_rechecking_actions(self):
		doc = Mock(name="LEAVE", status="Open", docstatus=0)
		doc.modified = "2026-11-08 10:00:00"
		with (
			patch("nagi_attendance.leave_approval.frappe.get_doc", return_value=doc) as load,
			patch("nagi_attendance.leave_approval.check_leave_scope"),
			patch("nagi_attendance.leave_approval.leave_actions", return_value=[]),
			self.assertRaises(frappe.PermissionError),
		):
			decide_leave("LEAVE", "Approve")
		load.assert_called_once_with("Leave Application", "LEAVE", for_update=True)
		doc.save.assert_not_called()
		doc.submit.assert_not_called()

	def test_stale_dialog_cannot_take_a_new_decision(self):
		doc = Mock(modified="2026-11-08 11:00:00")
		with (
			patch("nagi_attendance.leave_approval.frappe.get_doc", return_value=doc),
			patch("nagi_attendance.leave_approval.check_leave_scope"),
			self.assertRaises(frappe.TimestampMismatchError),
		):
			decide_leave("LEAVE", "Approve", "2026-11-08 10:00:00")
		doc.save.assert_not_called()

	def test_company_scope_failure_prevents_any_decision(self):
		doc = Mock()
		with (
			patch("nagi_attendance.leave_approval.frappe.get_doc", return_value=doc),
			patch("nagi_attendance.leave_approval.check_leave_scope", side_effect=frappe.PermissionError),
			self.assertRaises(frappe.PermissionError),
		):
			decide_leave("LEAVE", "Approve")
		doc.save.assert_not_called()

	def test_unified_counts_are_separate_manager_inboxes(self):
		with (
			patch("nagi_attendance.api._require_access"),
			patch("nagi_attendance.api.frappe.has_permission", return_value=True),
			patch("nagi_attendance.api.get_short_permission_context", return_value={"visible": True, "pending_count": 1, "filters": {}}),
			patch("nagi_attendance.api._pending_leave_requests", return_value=[frappe._dict(name="LEAVE-A"), frappe._dict(name="LEAVE-B"), frappe._dict(name="LEAVE-A")]),
		):
			counts = get_manager_pending_context()
		self.assertEqual((counts["leave_count"], counts["short_permission_count"], counts["total_pending"]), (2, 1, 3))

	def test_unreadable_request_modules_are_not_counted(self):
		with (
			patch("nagi_attendance.api._require_access"),
			patch("nagi_attendance.api.frappe.has_permission", return_value=False),
			patch("nagi_attendance.api._pending_leave_requests") as pending,
		):
			self.assertEqual(get_manager_pending_context()["total_pending"], 0)
		pending.assert_not_called()

	def test_employee_workflow_submission_is_not_an_approver_action(self):
		doc = Mock(docstatus=0, status="Open")
		with (
			patch("nagi_attendance.leave_approval.is_assigned_approver", return_value=True),
			patch("nagi_attendance.leave_approval.check_leave_scope"),
			patch("nagi_attendance.leave_approval.get_workflow_name", return_value="Draft workflow"),
			patch("nagi_attendance.leave_approval.get_transitions", return_value=[frappe._dict(action="Send for approval", allowed="Employee")]),
		):
			self.assertEqual(leave_actions(doc), [])
