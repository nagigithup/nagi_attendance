frappe.ui.form.on("Nagi Attendance Settings", {
	refresh(frm) {
		frm.set_intro(
			__("Shift schedules and holidays remain in HRMS. Assign Shift Locations to employees to enforce location-specific attendance."),
			"blue"
		);
	},
});
