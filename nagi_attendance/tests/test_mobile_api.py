from datetime import datetime, time
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils import get_datetime, now_datetime

from nagi_attendance.company import get_company_settings, get_current_employee
from nagi_attendance.mobile_api import (
	_approval_actions,
	_attendance_state,
	_attendance_window,
	_today_summary,
	bootstrap,
	create_checkin,
)


class TestMobileCheckinState(UnitTestCase):
	def setUp(self):
		self.employee = frappe._dict(name="EMP-STATE-TEST", company="Company A")
		self.settings = frappe._dict(
			enable_mobile_attendance=1,
			enable_gps_validation=0,
			attendance_start_date=None,
		)
		self.server_time = datetime(2026, 10, 10, 0, 5)
		self.latest = None
		self.historical = None
		self.hr_gps_required = 0
		self.inserted = []
		self.db_calls = []
		self.latest_filters = None

	def _db_get_value(self, doctype, filters=None, fieldname="name", **kwargs):
		self.db_calls.append((doctype, filters, fieldname, kwargs))
		if doctype == "Employee":
			return self.employee.name
		if doctype == "Employee Checkin":
			self.latest_filters = filters
			return self.latest if "time" in filters else self.historical
		raise AssertionError(f"Unexpected get_value call for {doctype}")

	def _get_single_value(self, doctype, fieldname):
		self.assertEqual(doctype, "HR Settings")
		if fieldname == "allow_employee_checkin_from_mobile_app":
			return 1
		if fieldname == "allow_geolocation_tracking":
			return self.hr_gps_required
		raise AssertionError(f"Unexpected HR Settings field {fieldname}")

	def _get_doc(self, values):
		doc = frappe._dict(values)

		def insert():
			doc.time = doc.time.replace(microsecond=0)
			doc.name = f"CHECKIN-{len(self.inserted) + 1}"
			self.inserted.append(doc)
			self.latest = frappe._dict(name=doc.name, log_type=doc.log_type, time=doc.time)
			return doc

		doc.insert = insert
		return doc

	def create(self, log_type, _window=None, **kwargs):
		window = _window or frappe._dict(
			start=datetime.combine(self.server_time.date(), time.min),
			end=datetime.combine(self.server_time.date(), time.max),
			attendance_date=self.server_time.date(),
		)
		with (
			patch("nagi_attendance.mobile_api.get_current_employee", return_value=self.employee) as employee_lookup,
			patch("nagi_attendance.mobile_api.get_company_settings", return_value=self.settings),
			patch("nagi_attendance.mobile_api.now_datetime", return_value=self.server_time),
			patch("nagi_attendance.mobile_api._attendance_window", return_value=window),
			patch("nagi_attendance.mobile_api._attendance_state", wraps=_attendance_state) as attendance_state,
			patch("nagi_attendance.mobile_api.frappe.db.get_single_value", side_effect=self._get_single_value),
			patch("nagi_attendance.mobile_api.frappe.db.get_value", side_effect=self._db_get_value),
			patch("nagi_attendance.mobile_api.frappe.get_doc", side_effect=self._get_doc),
		):
			result = create_checkin(log_type, company="Company A", **kwargs)
		employee_lookup.assert_called_once_with("Company A")
		self.state_calls = attendance_state.call_args_list
		return result

	def test_valid_first_checkin_ignores_previous_day_history(self):
		self.historical = frappe._dict(
			name="YESTERDAY-IN", log_type="IN", time=datetime(2026, 10, 9, 17)
		)

		result = self.create("IN")

		self.assertEqual(result["log_type"], "IN")
		self.assertEqual(len(self.inserted), 1)
		self.assertEqual(self.inserted[0].employee, self.employee.name)
		self.assertIn("time", self.latest_filters)

	def test_valid_checkout_after_checkin(self):
		self.latest = frappe._dict(name="TODAY-IN", log_type="IN", time=self.server_time)

		result = self.create(" out ")

		self.assertEqual(result["log_type"], "OUT")
		self.assertEqual(len(self.inserted), 1)
		self.assertEqual(self.inserted[0].log_type, "OUT")

	def test_stale_frontend_state_is_rejected_without_insert(self):
		self.latest = frappe._dict(name="TODAY-IN", log_type="IN", time=self.server_time)

		with self.assertRaisesRegex(frappe.ValidationError, "attendance changed"):
			self.create("IN")

		self.assertEqual(self.inserted, [])

	def test_repeated_click_creates_exactly_one_checkin(self):
		self.create("IN")

		with self.assertRaises(frappe.ValidationError):
			self.create("IN")

		self.assertEqual(len(self.inserted), 1)
		self.assertEqual(self.inserted[0].log_type, "IN")

	def test_concurrent_duplicate_is_guarded_by_locked_current_read(self):
		self.latest = frappe._dict(name="CONCURRENT-IN", log_type="IN", time=self.server_time)

		with self.assertRaises(frappe.ValidationError):
			self.create("IN")

		lock_calls = [call for call in self.db_calls if call[0] in {"Employee", "Employee Checkin"}]
		self.assertEqual([call[0] for call in lock_calls], ["Employee", "Employee Checkin"])
		self.assertTrue(all(call[3].get("for_update") for call in lock_calls))
		self.assertEqual(self.inserted, [])

	def test_invalid_event_transition_is_rejected_before_insert(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Invalid attendance action"):
			self.create("BREAK")

		self.assertEqual(self.db_calls, [])
		self.assertEqual(self.inserted, [])

	def test_employee_and_company_are_server_resolved(self):
		self.create("IN")

		self.assertEqual(self.inserted[0].employee, "EMP-STATE-TEST")
		self.assertNotIn("company", self.inserted[0])

	def test_valid_gps_is_preserved_for_geofence_validation(self):
		self.settings.enable_gps_validation = 1

		self.create("IN", latitude="24.7870341", longitude="46.8051581", accuracy="8")

		self.assertEqual(self.inserted[0].latitude, 24.7870341)
		self.assertEqual(self.inserted[0].longitude, 46.8051581)

	def test_missing_required_gps_is_rejected_without_insert(self):
		self.settings.enable_gps_validation = 1

		with self.assertRaisesRegex(frappe.ValidationError, "Location permission is required"):
			self.create("IN")

		self.assertEqual(self.inserted, [])

	def test_system_timezone_day_and_recorded_time_are_used(self):
		result = self.create("IN")
		start, end = self.latest_filters["time"][1]

		self.assertEqual(start, datetime.combine(self.server_time.date(), time.min))
		self.assertEqual(end, datetime.combine(self.server_time.date(), time.max))
		self.assertEqual(result["time"], "2026-10-10 00:05:00")
		self.assertEqual(str(self.inserted[0].time), result["time"])

	def test_exact_midnight_starts_new_unshifted_attendance_day(self):
		self.server_time = datetime(2026, 10, 10, 0, 0)
		self.historical = frappe._dict(
			name="PREVIOUS-DAY-IN", log_type="IN", time=datetime(2026, 10, 9, 23, 59, 59)
		)

		result = self.create("IN")

		start, end = self.latest_filters["time"][1]
		self.assertEqual(start, datetime(2026, 10, 10, 0, 0))
		self.assertEqual(end, datetime(2026, 10, 10, 23, 59, 59, 999999))
		self.assertEqual(result["log_type"], "IN")
		self.assertEqual(len(self.inserted), 1)

	def test_overnight_checkout_uses_prior_date_checkin(self):
		self.server_time = datetime(2026, 10, 10, 1, 0)
		self.latest = frappe._dict(name="OVERNIGHT-IN", log_type="IN", time=datetime(2026, 10, 9, 22, 0))
		window = frappe._dict(
			start=datetime(2026, 10, 9, 21, 0),
			end=datetime(2026, 10, 10, 7, 0),
			attendance_date=datetime(2026, 10, 9).date(),
		)

		result = self.create("OUT", _window=window)

		start, end = self.latest_filters["time"][1]
		self.assertEqual(start, window.start)
		self.assertEqual(end, window.end)
		self.assertEqual(result["log_type"], "OUT")

	def test_exact_midnight_overnight_checkout_keeps_prior_shift_state(self):
		self.server_time = datetime(2026, 10, 10, 0, 0)
		self.latest = frappe._dict(name="OVERNIGHT-IN", log_type="IN", time=datetime(2026, 10, 9, 22, 0))
		window = frappe._dict(
			start=datetime(2026, 10, 9, 21, 0),
			end=datetime(2026, 10, 10, 7, 0),
			attendance_date=datetime(2026, 10, 9).date(),
		)

		result = self.create("OUT", _window=window)

		self.assertEqual(self.latest_filters["time"][1], [window.start, window.end])
		self.assertEqual(result["log_type"], "OUT")
		self.assertEqual(len(self.inserted), 1)

	def test_dashboard_uses_normalized_latest_log_and_deterministic_order(self):
		last = frappe._dict(
			name="TODAY-IN", log_type=" in ", time=self.server_time, shift=None, latitude=None, longitude=None
		)
		state = frappe._dict(
			window=frappe._dict(
				start=datetime.combine(self.server_time.date(), time.min),
				end=datetime.combine(self.server_time.date(), time.max),
				attendance_date=self.server_time.date(),
			),
			last=last,
			next_action="OUT",
		)
		with (
			patch("nagi_attendance.mobile_api.frappe.get_list", side_effect=[[], [last]]) as get_list,
			patch("nagi_attendance.mobile_api._active_shift", return_value=None),
			patch("nagi_attendance.mobile_api._attendance_state", return_value=state) as attendance_state,
			patch("nagi_attendance.mobile_api.now_datetime", return_value=self.server_time),
		):
			summary = _today_summary(self.employee)

		attendance_state.assert_called_once_with(self.employee.name, self.server_time)
		self.assertEqual(summary["next_action"], "OUT")
		self.assertEqual(summary["last_log"].time, self.server_time)
		self.assertEqual(get_list.call_args_list[1].kwargs["order_by"], "time asc, creation asc, name asc")

	def test_hrms_overnight_shift_window_spans_midnight(self):
		server_time = datetime(2026, 10, 10, 1, 0)
		shift = frappe._dict(
			actual_start=datetime(2026, 10, 9, 21, 0),
			start_datetime=datetime(2026, 10, 9, 22, 0),
			actual_end=datetime(2026, 10, 10, 7, 0),
		)
		with patch(
			"hrms.hr.doctype.shift_assignment.shift_assignment.get_actual_start_end_datetime_of_shift",
			return_value=shift,
		) as get_shift:
			window = _attendance_window(self.employee.name, server_time)

		get_shift.assert_called_once_with(self.employee.name, server_time, consider_default_shift=True)
		self.assertEqual(window.start, shift.actual_start)
		self.assertEqual(window.end, shift.actual_end)
		self.assertEqual(window.attendance_date, datetime(2026, 10, 9).date())

	def test_site_local_datetime_is_not_converted_by_host_timezone(self):
		server_time = datetime(2026, 10, 10, 0, 5)
		with patch(
			"hrms.hr.doctype.shift_assignment.shift_assignment.get_actual_start_end_datetime_of_shift",
			return_value={},
		) as get_shift:
			window = _attendance_window(self.employee.name, server_time)

		get_shift.assert_called_once_with(self.employee.name, server_time, consider_default_shift=True)
		self.assertEqual(window.start, datetime(2026, 10, 10, 0, 0))
		self.assertEqual(window.end, datetime(2026, 10, 10, 23, 59, 59, 999999))

	def test_post_uses_shared_state_resolver_with_locked_read(self):
		self.create("IN")

		self.assertEqual(len(self.state_calls), 1)
		self.assertEqual(self.state_calls[0].args, (self.employee.name, self.server_time))
		self.assertTrue(self.state_calls[0].kwargs["for_update"])


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
		self.assertEqual(data["company"]["timezone"], frappe.utils.get_system_timezone())
		self.assertEqual(data["company"]["timezone"], "Asia/Riyadh")
		self.assertEqual(data["settings"]["attendance_start_date"], "2026-10-07")
		settings = get_company_settings(data["employee"].company)
		expected_gps = bool(
			settings.enable_gps_validation
			or frappe.db.get_single_value("HR Settings", "allow_geolocation_tracking")
		)
		self.assertEqual(data["settings"]["enable_gps_validation"], expected_gps)

	def test_self_approval_is_never_offered(self):
		frappe.set_user("a.mohsen@adanlawfirm.com")
		doc = frappe._dict(employee="HR-EMP-00003", leave_approver=frappe.session.user)
		self.assertEqual(_approval_actions(doc), [])

	def test_installed_hrms_resolves_real_overnight_shift_across_midnight(self):
		frappe.set_user("Administrator")
		shift = frappe.get_doc(
			{
				"doctype": "Shift Type",
				"name": "_Test Nagi Overnight State",
				"start_time": "22:00:00",
				"end_time": "06:00:00",
				"begin_check_in_before_shift_start_time": 60,
				"allow_check_out_after_shift_end_time": 60,
			}
		).insert()
		frappe.db.set_value("Employee", "HR-EMP-00003", "default_shift", shift.name)

		window = _attendance_window("HR-EMP-00003", datetime(2026, 10, 6, 1, 0))

		self.assertEqual(window.start, datetime(2026, 10, 5, 21, 0))
		self.assertEqual(window.end, datetime(2026, 10, 6, 7, 0))
		self.assertEqual(window.attendance_date, datetime(2026, 10, 5).date())

	def test_valid_in_out_create_exactly_one_document_each(self):
		frappe.set_user("a.mohsen@adanlawfirm.com")
		company = frappe.db.get_value("Employee", "HR-EMP-00003", "company")
		started_at = now_datetime().replace(microsecond=0)
		checkin = create_checkin(
			"IN", latitude=24.7870341, longitude=46.8051581, accuracy=8, company=company
		)
		checkout = create_checkin(
			"OUT", latitude=24.7870341, longitude=46.8051581, accuracy=8, company=company
		)
		finished_at = now_datetime().replace(microsecond=0)

		rows = frappe.get_all(
			"Employee Checkin",
			filters={"name": ("in", [checkin["name"], checkout["name"]])},
			fields=["name", "employee", "log_type", "time"],
		)
		self.assertEqual(len(rows), 2)
		rows_by_name = {row.name: row for row in rows}
		self.assertEqual(rows_by_name[checkin["name"]].log_type, "IN")
		self.assertEqual(rows_by_name[checkout["name"]].log_type, "OUT")
		self.assertTrue(all(row.employee == "HR-EMP-00003" for row in rows))
		self.assertEqual(str(rows_by_name[checkin["name"]].time), checkin["time"])
		self.assertEqual(str(rows_by_name[checkout["name"]].time), checkout["time"])
		self.assertTrue(started_at <= get_datetime(checkin["time"]) <= finished_at)
		self.assertTrue(started_at <= get_datetime(checkout["time"]) <= finished_at)
		summary = _today_summary(get_current_employee(company))
		self.assertEqual(summary["last_log"].name, checkout["name"])
		self.assertEqual(str(summary["last_log"].time), checkout["time"])
		self.assertEqual(summary["next_action"], "IN")
