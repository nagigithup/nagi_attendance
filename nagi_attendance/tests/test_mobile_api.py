import frappe
from frappe.tests import IntegrationTestCase

from nagi_attendance.company import get_current_employee
from nagi_attendance.mobile_api import _approval_actions, bootstrap


class TestMobileSecurity(IntegrationTestCase):
	def setUp(self):
		self.original_user = frappe.session.user

	def tearDown(self):
		frappe.set_user(self.original_user)

	def test_guest_cannot_resolve_employee(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_current_employee()

	def test_employee_cannot_select_unlinked_company(self):
		frappe.set_user("a.mohsen@adanlawfirm.com")
		with self.assertRaises(frappe.PermissionError):
			get_current_employee("Unauthorized Company")

	def test_bootstrap_uses_employee_company_branding(self):
		frappe.set_user("a.mohsen@adanlawfirm.com")
		data = bootstrap()
		self.assertEqual(data["employee"].company, data["company"]["name"])
		self.assertEqual(data["settings"]["attendance_start_date"], "2026-10-07")
		self.assertTrue(data["settings"]["enable_gps_validation"])

	def test_self_approval_is_never_offered(self):
		frappe.set_user("a.mohsen@adanlawfirm.com")
		doc = frappe._dict(employee="HR-EMP-00003", leave_approver=frappe.session.user)
		self.assertEqual(_approval_actions(doc), [])
