import frappe
from frappe.tests import IntegrationTestCase

from nagi_attendance.overrides.shift_type import AdanPresentOnlyAutoAttendanceMixin


class TestAdanAutoAttendanceIntegration(IntegrationTestCase):
	def test_real_logs_create_late_present_without_no_log_absences(self):
		shift = frappe.get_doc("Shift Type", "دوام المكتب 09:00-15:00")
		self.assertIsInstance(shift, AdanPresentOnlyAutoAttendanceMixin)

		# Processing with no logs must not fabricate an Absent record.
		shift.process_auto_attendance()
		self.assertEqual(frappe.db.count("Attendance"), 0)

		checkins = []
		for log_type, timestamp in (
			("IN", "2026-10-07 09:11:00"),
			("OUT", "2026-10-07 15:00:00"),
		):
			checkins.append(
				frappe.get_doc(
					{
						"doctype": "Employee Checkin",
						"employee": "HR-EMP-00003",
						"log_type": log_type,
						"time": timestamp,
						"latitude": 24.7870341,
						"longitude": 46.8051581,
					}
				).insert(ignore_permissions=True)
			)

		shift.process_auto_attendance()
		attendance = frappe.get_doc(
			"Attendance",
			frappe.db.get_value(
				"Attendance",
				{"employee": "HR-EMP-00003", "attendance_date": "2026-10-07"},
				"name",
			),
		)
		self.assertEqual(attendance.status, "Present")
		self.assertEqual(attendance.late_entry, 1)
		self.assertEqual(str(attendance.in_time), "2026-10-07 09:11:00")
		self.assertEqual(str(attendance.out_time), "2026-10-07 15:00:00")
		self.assertTrue(all(checkin.reload().attendance == attendance.name for checkin in checkins))
		self.assertEqual(frappe.db.count("Attendance", {"status": "Absent"}), 0)
