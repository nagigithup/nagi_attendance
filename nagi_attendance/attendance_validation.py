from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate
from hrms.hr.doctype.employee_checkin.employee_checkin import CheckinRadiusExceededError
from hrms.hr.utils import get_distance_between_coordinates


def validate_mandatory_employee_checkin_location(doc, method=None) -> None:
	"""Enforce active Shift Assignment locations even when a log is off-shift.

	HRMS validates a Shift Location only after it resolves ``doc.shift``. Outside
	the configured check-in/out window an otherwise assigned employee is marked
	off-shift, which would skip the native radius check. Partners have no Shift
	Assignment and therefore remain intentionally exempt.
	"""
	if not frappe.db.get_single_value("HR Settings", "allow_geolocation_tracking"):
		return
	if not doc.employee or not doc.time:
		return

	checkin_date = getdate(doc.time)
	assignments = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": doc.employee,
			"start_date": ["<=", checkin_date],
			"shift_location": ["is", "set"],
			"docstatus": 1,
			"status": "Active",
		},
		or_filters=[["end_date", ">=", checkin_date], ["end_date", "is", "not set"]],
		fields=["shift_type", "shift_location"],
	)
	if not assignments:
		return

	# Prefer the assignment resolved by HRMS when available. If the check-in is
	# off-shift, every active assigned location remains an allowed location.
	if doc.shift:
		matching = [row for row in assignments if row.shift_type == doc.shift]
		if matching:
			assignments = matching

	if doc.latitude in (None, "") or doc.longitude in (None, ""):
		frappe.throw(_("Latitude and longitude values are required for checking in."))

	try:
		latitude = float(doc.latitude)
		longitude = float(doc.longitude)
	except (TypeError, ValueError):
		frappe.throw(_("Latitude and longitude values are required for checking in."))

	configured_locations = []
	for location_name in dict.fromkeys(row.shift_location for row in assignments):
		location = frappe.db.get_value(
			"Shift Location",
			location_name,
			["checkin_radius", "latitude", "longitude"],
			as_dict=True,
		)
		if not location or flt(location.checkin_radius) <= 0:
			continue
		if location.latitude is None or location.longitude is None:
			frappe.throw(_("Shift Location {0} does not have valid coordinates.").format(location_name))
		configured_locations.append(location)

	if not configured_locations:
		return

	for location in configured_locations:
		distance = get_distance_between_coordinates(
			flt(location.latitude),
			flt(location.longitude),
			latitude,
			longitude,
		)
		if distance <= flt(location.checkin_radius):
			return

	radius = min(flt(location.checkin_radius) for location in configured_locations)
	frappe.throw(
		_("You must be within {0} meters of your shift location to check in.").format(radius),
		exc=CheckinRadiusExceededError,
	)
