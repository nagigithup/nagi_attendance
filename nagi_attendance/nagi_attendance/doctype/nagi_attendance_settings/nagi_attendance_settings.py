from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.model.document import Document

HEX_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")


class NagiAttendanceSettings(Document):
	def autoname(self):
		self.name = self.company

	def validate(self):
		if self.brand_primary_color and not HEX_COLOUR.match(self.brand_primary_color):
			frappe.throw(_("Brand Primary Color must be a six-digit hex color, for example #176B5B."))
		if self.default_geofence_radius and self.default_geofence_radius <= 0:
			frappe.throw(_("Default Geofence Radius must be greater than zero."))
		for fieldname in ("maximum_permission_hours_per_request", "maximum_permission_hours_per_month"):
			if self.get(fieldname) and self.get(fieldname) < 0:
				frappe.throw(_("Permission hour limits cannot be negative."))
		if self.default_reporting_department:
			department_company = frappe.db.get_value(
				"Department", self.default_reporting_department, "company"
			)
			if department_company != self.company:
				frappe.throw(_("Default Reporting Department must belong to the selected company."))
