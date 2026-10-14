from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase
from hrms.hr.doctype.employee_checkin.employee_checkin import CheckinRadiusExceededError

from nagi_attendance.attendance_validation import validate_mandatory_employee_checkin_location


class TestMandatoryCheckinLocation(UnitTestCase):
	def setUp(self):
		self.doc = frappe._dict(
			employee="HR-EMP-TEST",
			time="2026-10-08 19:00:00",
			shift=None,
			latitude=24.7870341,
			longitude=46.8051581,
		)
		self.assignment = frappe._dict(
			shift_type="دوام المكتب 09:00-15:00",
			shift_location="ADAN TEST OFFICE",
		)
		self.location = frappe._dict(
			checkin_radius=100,
			latitude=24.7870341,
			longitude=46.8051581,
		)

	def validate(self):
		def get_value(doctype, name, fields, **kwargs):
			if doctype == "Employee":
				return "Test Company"
			return self.location

		with (
			patch("nagi_attendance.attendance_validation.frappe.db.get_single_value", return_value=1),
			patch("nagi_attendance.attendance_validation.frappe.get_all", return_value=[self.assignment]),
			patch("nagi_attendance.attendance_validation.frappe.db.get_value", side_effect=get_value),
			patch(
				"nagi_attendance.attendance_validation.get_company_settings",
				return_value=frappe._dict(allowed_locations=[]),
			),
		):
			validate_mandatory_employee_checkin_location(self.doc)

	def test_inside_location_is_accepted_for_offshift_log(self):
		self.validate()

	def test_missing_location_is_rejected(self):
		self.doc.latitude = None
		with self.assertRaises(frappe.ValidationError):
			self.validate()

	def test_outside_location_is_rejected_for_offshift_log(self):
		self.doc.latitude = 24.7970341
		with self.assertRaises(CheckinRadiusExceededError):
			self.validate()

	def test_employee_without_shift_assignment_is_exempt(self):
		with (
			patch("nagi_attendance.attendance_validation.frappe.db.get_single_value", return_value=1),
			patch("nagi_attendance.attendance_validation.frappe.get_all", return_value=[]),
		):
			validate_mandatory_employee_checkin_location(self.doc)

	def test_company_fallback_radius_is_used_when_location_radius_is_empty(self):
		self.doc.latitude = 24.7890
		location = frappe._dict(checkin_radius=0, latitude=24.7870341, longitude=46.8051581)

		def get_value(doctype, name, fields, **kwargs):
			return "Company B" if doctype == "Employee" else location

		settings = frappe._dict(
			enable_gps_validation=1,
			default_geofence_radius=500,
			allowed_locations=[],
		)
		with (
			patch("nagi_attendance.attendance_validation.frappe.db.get_single_value", return_value=0),
			patch("nagi_attendance.attendance_validation.frappe.get_all", return_value=[self.assignment]),
			patch("nagi_attendance.attendance_validation.frappe.db.get_value", side_effect=get_value),
			patch("nagi_attendance.attendance_validation.get_company_settings", return_value=settings),
		):
			validate_mandatory_employee_checkin_location(self.doc)
