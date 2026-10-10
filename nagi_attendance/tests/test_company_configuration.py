from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from nagi_attendance.company import company_brand, get_current_employee
from nagi_attendance.nagi_attendance.doctype.nagi_attendance_settings.nagi_attendance_settings import (
	NagiAttendanceSettings,
)


class TestCompanyConfiguration(UnitTestCase):
	def test_default_reporting_department_must_match_company(self):
		doc = frappe._dict(
			company="Company A",
			brand_primary_color="#176B5B",
			default_geofence_radius=0,
			default_reporting_department="Legal - B",
		)
		with (
			patch("nagi_attendance.nagi_attendance.doctype.nagi_attendance_settings.nagi_attendance_settings.frappe.db.get_value", return_value="Company B"),
			self.assertRaises(frappe.ValidationError),
		):
			NagiAttendanceSettings.validate(doc)

	def test_two_companies_return_separate_branding(self):
		companies = {
			"Company A": frappe._dict(name="Company A", abbr="A", company_logo="/files/a.png", default_currency="AED"),
			"Company B": frappe._dict(name="Company B", abbr="B", company_logo=None, default_currency="USD"),
		}
		settings = {
			"Company A": frappe._dict(brand_primary_color="#112233", default_language="ar"),
			"Company B": frappe._dict(brand_primary_color="#445566", default_language="en"),
		}
		with (
			patch("nagi_attendance.company.frappe.db.get_value", side_effect=lambda _dt, name, *_a, **_k: companies[name]),
			patch("nagi_attendance.company.get_company_settings", side_effect=lambda company: settings[company]),
			patch("nagi_attendance.company.frappe.utils.get_system_timezone", return_value="Asia/Dubai"),
		):
			brand_a = company_brand("Company A")
			brand_b = company_brand("Company B")
		self.assertEqual(brand_a["logo"], "/files/a.png")
		self.assertEqual(brand_a["primary_color"], "#112233")
		self.assertIsNone(brand_b["logo"])
		self.assertEqual(brand_b["primary_color"], "#445566")
		self.assertEqual(brand_a["timezone"], "Asia/Dubai")
		self.assertEqual(brand_b["timezone"], "Asia/Dubai")

	def test_company_selector_rejects_unlinked_company(self):
		employees = [frappe._dict(name="EMP-A", company="Company A")]
		with patch("nagi_attendance.company.get_user_employees", return_value=employees):
			with self.assertRaises(frappe.PermissionError):
				get_current_employee("Company B")
