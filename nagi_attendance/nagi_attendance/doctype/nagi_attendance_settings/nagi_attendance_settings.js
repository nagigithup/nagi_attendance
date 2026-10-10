frappe.ui.form.on("Nagi Attendance Settings", {
	setup(frm) {
		frm.set_query("default_reporting_department", () => ({
			filters: { company: frm.doc.company },
		}));
	},

	refresh(frm) {
		frm.set_intro(
			__("Shift schedules and holidays remain in HRMS. Assign Shift Locations to employees to enforce location-specific attendance."),
			"blue"
		);
	},
});
