"""Move the pilot site's established policy into company configuration.

This one-time data migration is intentionally pilot-specific. Runtime product
code has no customer-name checks. No operational HR records are edited.
"""

import frappe

from nagi_attendance.setup.adan_law_firm import (
	ATTENDANCE_GO_LIVE_DATE,
	COMPANY,
	OFFICE_LOCATION,
	TEST_GEOFENCE_RADIUS_METERS,
)


def execute():
	if not frappe.db.exists("Company", COMPANY) or frappe.db.exists("Nagi Attendance Settings", COMPANY):
		return
	locations = []
	if frappe.db.exists("Shift Location", OFFICE_LOCATION):
		locations.append(
			{"shift_location": OFFICE_LOCATION, "radius_override": TEST_GEOFENCE_RADIUS_METERS}
		)
	frappe.get_doc(
		{
			"doctype": "Nagi Attendance Settings",
			"company": COMPANY,
			"enable_mobile_attendance": 1,
			"enable_mobile_leave": 1,
			"allow_attendance_history": 1,
			"enable_gps_validation": 1,
			"default_geofence_radius": TEST_GEOFENCE_RADIUS_METERS,
			"attendance_start_date": ATTENDANCE_GO_LIVE_DATE,
			"prevent_automatic_absence": 1,
			"default_language": "ar",
			"brand_primary_color": "#176B5B",
			"allowed_locations": locations,
		}
	).insert(ignore_permissions=True)
