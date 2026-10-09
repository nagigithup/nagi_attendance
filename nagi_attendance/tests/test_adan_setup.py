from datetime import date

from frappe.tests import UnitTestCase

from nagi_attendance.setup.adan_law_firm import (
	ATTENDANCE_GO_LIVE_DATE,
	CONFIRMED_GENDER,
	EMPLOYEES,
	LEGAL_DEPARTMENT,
	MANAGEMENT_DEPARTMENT,
	OFFICE_ADDRESS,
	OFFICE_LATITUDE,
	OFFICE_LONGITUDE,
	OFFICE_MAP_URL,
	SHIFT_TYPES,
	TEST_GEOFENCE_RADIUS_METERS,
	_holiday_rows,
)


class TestAdanSetup(UnitTestCase):
	def test_2026_holidays_include_weekends_and_confirmed_fixed_holidays(self):
		holidays = _holiday_rows()
		dates = {str(row["holiday_date"]) for row in holidays}

		self.assertEqual(len(holidays), 106)
		self.assertIn("2026-02-22", dates)
		self.assertIn("2026-09-23", dates)
		self.assertTrue(
			all(
				row.get("weekly_off") or str(row["holiday_date"]) in {"2026-02-22", "2026-09-23"}
				for row in holidays
			)
		)
		self.assertTrue(
			all(
				date.fromisoformat(str(row["holiday_date"])).weekday() in (4, 5)
				for row in holidays
				if row.get("weekly_off")
			)
		)

	def test_shift_assignments_match_confirmed_employee_schedule(self):
		self.assertEqual(ATTENDANCE_GO_LIVE_DATE.isoformat(), "2026-10-07")
		shifts = {row["name"]: (row["start_time"], row["end_time"]) for row in SHIFT_TYPES}
		self.assertEqual(shifts["دوام المكتب 09:00-15:00"], ("09:00:00", "15:00:00"))
		self.assertEqual(shifts["دوام المكتب 09:00-16:00"], ("09:00:00", "16:00:00"))
		self.assertIsNone(EMPLOYEES[0]["shift"])
		self.assertIsNone(EMPLOYEES[1]["shift"])
		self.assertEqual(
			[row["shift"] for row in EMPLOYEES[2:]],
			[
				"دوام المكتب 09:00-15:00",
				"دوام المكتب 09:00-15:00",
				"دوام المكتب 09:00-16:00",
			],
		)

	def test_confirmed_employee_identity_and_approval_mappings(self):
		self.assertEqual(CONFIRMED_GENDER, "Male")
		self.assertEqual([row["department"] for row in EMPLOYEES[:2]], [MANAGEMENT_DEPARTMENT] * 2)
		self.assertEqual([row["department"] for row in EMPLOYEES[2:]], [LEGAL_DEPARTMENT] * 3)
		self.assertEqual(EMPLOYEES[0]["leave_approver"], "abdulrahman@adanlawfirm.com")
		self.assertTrue(
			all(row["leave_approver"] == "osama@adanlawfirm.com" for row in EMPLOYEES[1:])
		)
		self.assertIn("Leave Approver", EMPLOYEES[1]["roles"])

	def test_office_geofence_uses_verified_coordinates_and_test_radius(self):
		self.assertEqual((OFFICE_LATITUDE, OFFICE_LONGITUDE), (24.7870341, 46.8051581))
		self.assertEqual(TEST_GEOFENCE_RADIUS_METERS, 100)
		self.assertEqual(
			OFFICE_ADDRESS,
			"شارع بحر العرب، الخليج، الرياض 13224، المملكة العربية السعودية",
		)
		self.assertEqual(
			OFFICE_MAP_URL,
			"https://maps.app.goo.gl/HuDpLxp7xA95nw889?g_st=ic",
		)
