frappe.pages["manager-attendance"].on_page_load = (wrapper) => {
	frappe.nagi_attendance = new NagiAttendance(wrapper);
};

class NagiAttendance {
	constructor(wrapper) {
		this.is_arabic = (frappe.boot?.lang || "").toLowerCase().startsWith("ar");
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Nagi Attendance"),
			single_column: true,
		});
		if (frappe.user.has_role(["System Manager", "HR Manager"])) {
			this.page.add_menu_item(__("Company Attendance Settings"), () =>
				frappe.set_route("List", "Nagi Attendance Settings")
			);
		}
		this.state = {
			tab: "today",
			date: frappe.datetime.get_today(),
			month: Number(frappe.datetime.get_today().slice(5, 7)),
			year: Number(frappe.datetime.get_today().slice(0, 4)),
			employee: "",
			department: "",
			status: "",
		};
		this.restore_state();
		this.render_shell();
		this.bind_events();
		this.initialize();
	}

	async initialize() {
		try {
			const defaults = await this.call("get_dashboard_defaults", {
				company: frappe.defaults.get_user_default("Company"),
			});
			if (defaults?.default_reporting_department) {
				this.state.department = defaults.default_reporting_department;
				this.persist_state();
				this.render_filters();
			}
		} catch (_) {
			// A reporting preference must never prevent the dashboard from loading.
		}
		this.load_active();
	}

	restore_state() {
		try {
			Object.assign(this.state, JSON.parse(sessionStorage.getItem("nagi-attendance-filters") || "{}"));
		} catch (_) {
			// Ignore stale browser state.
		}
	}

	persist_state() {
		sessionStorage.setItem("nagi-attendance-filters", JSON.stringify(this.state));
	}

	render_shell() {
		this.$root = $(
			`<div class="nagi-attendance" dir="${this.is_arabic ? "rtl" : "ltr"}" lang="${this.is_arabic ? "ar" : "en"}">
				<section class="na-hero">
					<div><span class="na-kicker">${__("Manager overview")}</span><h2>${__("Attendance & Leave")}</h2><p>${__("A clear view of your team, right now.")}</p></div>
					<button class="btn btn-default btn-sm" data-action="refresh">${frappe.utils.icon("refresh-cw", "sm")} ${__("Refresh")}</button>
				</section>
				<nav class="na-tabs" aria-label="${__("Dashboard views")}">
					<button class="active" data-tab="today">${__("Today")}</button>
					<button data-tab="monthly">${__("Monthly Attendance")}</button>
					<button data-tab="leave">${__("Leave")}</button>
				</nav>
				<section class="na-filters"></section>
				<div class="na-view" aria-live="polite"></div>
			</div>`
		).appendTo(this.page.main);
		this.render_filters();
	}

	render_filters() {
		const monthly = this.state.tab === "monthly";
		const html = monthly
			? `<label>${__("Month")}<select data-filter="month">${Array.from({ length: 12 }, (_, index) => `<option value="${index + 1}" ${this.state.month === index + 1 ? "selected" : ""}>${this.localized_moment().month(index).format("MMMM")}</option>`).join("")}</select></label>
			   <label>${__("Year")}<input type="number" data-filter="year" min="2000" max="2100" value="${this.state.year}"></label>`
			: `<label>${__("Date")}<input type="date" data-filter="date" value="${this.state.date}"></label>`;
		this.$root.find(".na-filters").html(`${html}
			<label>${__("Employee")}<select data-filter="employee"><option value="">${__("All employees")}</option></select></label>
			<label>${__("Department")}<select data-filter="department"><option value="">${__("All departments")}</option></select></label>
			${this.state.tab === "today" ? `<label>${__("Status")}<select data-filter="status"><option value="">${__("All statuses")}</option>${["Present", "Absent", "On Leave", "Late", "Half Day", "Work From Home", "Not Checked In", "Holiday", "Weekly Off"].map((value) => `<option value="${this.esc(value)}" ${this.state.status === value ? "selected" : ""}>${__(value)}</option>`).join("")}</select></label>` : ""}`);
		this.populate_filter_options();
	}

	populate_filter_options() {
		if (!this.filter_options) return;
		const employee = this.$root.find('[data-filter="employee"]');
		this.filter_options.employees.forEach((row) => employee.append(`<option value="${this.esc(row.name)}" ${this.state.employee === row.name ? "selected" : ""}>${this.esc(row.employee_name)}</option>`));
		const department = this.$root.find('[data-filter="department"]');
		this.filter_options.departments.forEach((name) => department.append(`<option value="${this.esc(name)}" ${this.state.department === name ? "selected" : ""}>${this.esc(name)}</option>`));
	}

	bind_events() {
		this.$root.on("click", "[data-tab]", (event) => {
			this.state.tab = event.currentTarget.dataset.tab;
			this.$root.find("[data-tab]").removeClass("active");
			$(event.currentTarget).addClass("active");
			this.render_filters();
			this.persist_state();
			this.load_active();
		});
		this.$root.on("change", "[data-filter]", (event) => {
			const key = event.currentTarget.dataset.filter;
			this.state[key] = ["month", "year"].includes(key) ? Number(event.currentTarget.value) : event.currentTarget.value;
			this.persist_state();
			if (key === "status") this.apply_status_filter();
			else this.load_active();
		});
		this.$root.on("click", '[data-action="refresh"]', () => this.load_active());
		this.$root.on("click", "[data-summary-status]", (event) => {
			this.state.status = event.currentTarget.dataset.summaryStatus;
			this.$root.find('[data-filter="status"]').val(this.state.status);
			this.apply_status_filter();
		});
		this.$root.on("click", "[data-employee]", (event) => this.open_employee(event.currentTarget.dataset.employee));
		this.$root.on("click", "[data-leave-action]", (event) => this.apply_leave_action(event.currentTarget));
	}

	load_active() {
		if (this.state.tab === "today") return this.load_today();
		if (this.state.tab === "monthly") return this.load_monthly();
		return this.load_leave();
	}

	loading() {
		this.$root.find(".na-view").html(`<div class="na-loading"><span></span><p>${__("Loading attendance…")}</p></div>`);
	}

	async call(method, args = {}) {
		return (await frappe.call({ method: `nagi_attendance.api.${method}`, args, freeze: false })).message;
	}

	async load_today() {
		this.loading();
		try {
			this.today = await this.call("get_today_dashboard", { date: this.state.date, employee: this.state.employee, department: this.state.department });
			this.filter_options = this.today.filters;
			this.populate_filter_options();
			this.render_today();
		} catch (error) {
			this.render_error(error);
		}
	}

	render_today() {
		const s = this.today.summary;
		const cards = [
			["total", __("Employees"), "users", ""],
			["present", __("Present"), "check-circle", "Present"],
			["absent", __("Absent"), "user-x", "Absent"],
			["leave", __("On Leave"), "calendar", "On Leave"],
			["late", __("Late"), "clock", "Late"],
			["not_checked_in", __("Not Checked In"), "log-in", "Not Checked In"],
		].map(([key, label, icon, status]) => `<button class="na-stat na-stat-${key}" data-summary-status="${status}">${frappe.utils.icon(icon, "md")}<span>${label}</span><strong>${s[key]}</strong></button>`).join("");
		const employees = this.today.employees.map((row) => this.employee_card(row)).join("") || this.empty(__("No active employees match these filters."));
		const timeline = this.today.timeline.length ? this.today.timeline.map((row) => `<li><time>${row.time_label}</time><span class="na-timeline-dot ${row.log_type === "OUT" ? "out" : ""}"></span><div>${this.timeline_activity(row)}${row.late ? ` <span class="na-inline-late">${__("Late")}</span>` : ""}</div></li>`).join("") : this.empty(__("No check-in activity for this date."));
		this.$root.find(".na-view").html(`
			<div class="na-stats">${cards}</div>
			<div class="na-today-grid">
				<section class="na-panel"><div class="na-panel-head"><div><span>${__("Team status")}</span><h3>${this.format_full_date(this.today.date)}</h3></div><small>${this.employee_count(s.total)}</small></div><div class="na-people">${employees}</div></section>
				<section class="na-panel na-timeline"><div class="na-panel-head"><div><span>${__("Live activity")}</span><h3>${__("Today's timeline")}</h3></div></div><ol>${timeline}</ol></section>
			</div>`);
		this.apply_status_filter();
	}

	employee_card(row) {
		const avatar = row.image ? `<img src="${this.esc(row.image)}" alt="">` : `<span>${this.esc((row.employee_name || "?").slice(0, 1))}</span>`;
		const detail = row.status === "On Leave" && row.status_detail ? `${__("On Leave")} · ${this.esc(__(row.status_detail))}` : __(row.status);
		return `<article class="na-person" data-person-status="${this.esc(row.status)}" data-is-late="${row.late ? 1 : 0}">
			<button class="na-person-main" data-employee="${this.esc(row.name)}"><span class="na-avatar">${avatar}</span><span><strong>${this.esc(row.employee_name)}</strong><small>${this.esc([row.designation, row.department].filter(Boolean).join(" · ") || __("Employee"))}</small></span></button>
			<div class="na-status"><span class="na-badge status-${frappe.scrub(row.status)}">${detail}</span>${row.late && row.status !== "Late" ? `<small>${__("Late arrival")}</small>` : ""}</div>
			<div class="na-person-metric"><span>${__("Check In")}</span><strong>${row.in_time_label || "—"}</strong></div>
			<div class="na-person-metric"><span>${__("Check Out")}</span><strong>${row.out_time_label || "—"}</strong></div>
			<div class="na-person-metric"><span>${__("Working Hours")}</span><strong>${this.localize_duration(row.working_hours_label)}</strong></div>
			<div class="na-person-metric"><span>${__("Shift")}</span><strong>${this.esc(row.shift || "—")}</strong></div>
		</article>`;
	}

	apply_status_filter() {
		if (!this.today) return;
		this.$root.find(".na-person").each((_, element) => {
			const status = element.dataset.personStatus;
			const matches = !this.state.status || status === this.state.status || (this.state.status === "Late" && element.dataset.isLate === "1");
			element.hidden = !matches;
		});
		this.persist_state();
	}

	async load_monthly() {
		this.loading();
		try {
			this.monthly = await this.call("get_monthly_attendance", { year: this.state.year, month: this.state.month, employee: this.state.employee, department: this.state.department });
			this.render_monthly();
		} catch (error) {
			this.render_error(error);
		}
	}

	render_monthly() {
		const data = this.monthly;
		const summaries = data.employees.map((row) => `<article class="na-month-summary"><button data-employee="${this.esc(row.name)}"><strong>${this.esc(row.employee_name)}</strong><small>${this.esc(row.designation || "")}</small></button>${[["working_days", "Working Days"], ["present", "Present Days"], ["absent", "Absent Days"], ["leave", "Leave Days"], ["late", "Late Days"], ["working_hours_label", "Total Working Hours"]].map(([key, label]) => `<div><span>${__(label)}</span><strong>${key === "working_hours_label" ? this.localize_duration(row.summary[key]) : (row.summary[key] ?? "—")}</strong></div>`).join("")}<div><span>${__("Average Check-In / Check-Out")}</span><strong>${row.summary.average_in || "—"} / ${row.summary.average_out || "—"}</strong></div></article>`).join("");
		const header = data.days.map((day) => `<th class="${["Fri", "Sat", "Sun"].includes(day.weekday) ? "weekend" : ""}"><span>${__(day.weekday)}</span>${day.day}</th>`).join("");
		const rows = data.employees.map((employee) => `<tr><th><button data-employee="${this.esc(employee.name)}">${this.esc(employee.employee_name)}</button></th>${employee.days.map((cell) => `<td><span class="na-day status-${frappe.scrub(cell.status)}" tabindex="0" data-toggle="tooltip" title="${this.esc(this.calendar_tooltip(cell))}">${__(cell.code)}</span></td>`).join("")}</tr>`).join("");
		this.$root.find(".na-view").html(`
			<section class="na-summary-list">${summaries || this.empty(__("No employees found."))}</section>
			<section class="na-panel"><div class="na-panel-head"><div><span>${__("Calendar")}</span><h3>${this.localized_moment({ year: data.year, month: data.month - 1 }).format("MMMM YYYY")}</h3></div><div class="na-legend"><span>${__("P")} ${__("Present")}</span><span>${__("A")} ${__("Absent")}</span><span>${__("L")} ${__("Leave")}</span><span>${__("HD")} ${__("Half Day")}</span><span>${__("WO")} ${__("Weekly Off")}</span></div></div><div class="na-calendar-scroll"><table class="na-calendar"><thead><tr><th>${__("Employee")}</th>${header}</tr></thead><tbody>${rows}</tbody></table></div></section>
			<section class="na-charts"><article class="na-panel"><h3>${__("Monthly Attendance Breakdown")}</h3><div id="na-breakdown-chart"></div></article><article class="na-panel"><h3>${__("Attendance Trend")}</h3><div id="na-trend-chart"></div></article><article class="na-panel"><h3>${__("Late Arrival")}</h3><div id="na-late-chart"></div></article></section>`);
		this.render_charts();
		this.$root.find('[data-toggle="tooltip"]').tooltip({ container: "body" });
	}

	render_charts() {
		if (!this.monthly.employees.length || typeof frappe.Chart !== "function") return;
		const charts = this.monthly.charts;
		new frappe.Chart("#na-breakdown-chart", { type: "donut", height: 210, colors: ["#2f7d65", "#a47b43", "#b7534f"], data: { labels: [__("Present"), __("Leave"), __("Absent")], datasets: [{ values: [charts.breakdown.present, charts.breakdown.leave, charts.breakdown.absent] }] } });
		new frappe.Chart("#na-trend-chart", { type: "line", height: 210, colors: ["#274c77"], data: { labels: this.monthly.days.map((day) => String(day.day)), datasets: [{ name: __("Present"), values: charts.trend }] } });
		new frappe.Chart("#na-late-chart", { type: "bar", height: 210, colors: ["#c58b3d"], data: { labels: charts.late.map((row) => row.employee), datasets: [{ name: __("Late"), values: charts.late.map((row) => row.value) }] } });
	}

	async load_leave() {
		this.loading();
		try {
			this.leave = await this.call("get_leave_dashboard", {
				date: this.state.date,
				employee: this.state.employee,
				department: this.state.department,
			});
			this.render_leave();
		} catch (error) {
			this.render_error(error);
		}
	}

	render_leave() {
		this.$root.find(".na-view").html(`<div class="na-leave-grid">
			<section class="na-panel"><div class="na-panel-head"><div><span>${__("Leave")}</span><h3>${__("On Leave Today")}</h3></div><strong class="na-count">${this.leave.on_leave.length}</strong></div>${this.leave_rows(this.leave.on_leave)}</section>
			<section class="na-panel"><div class="na-panel-head"><div><span>${__("Approved")}</span><h3>${__("Upcoming Leave")}</h3></div></div>${this.leave_rows(this.leave.upcoming)}</section>
			<section class="na-panel na-pending"><div class="na-panel-head"><div><span>${__("Needs attention")}</span><h3>${__("Pending Leave Requests")}</h3></div><strong class="na-count">${this.leave.pending.length}</strong></div>${this.leave_rows(this.leave.pending, true)}</section>
		</div>`);
	}

	leave_rows(rows, pending = false) {
		if (!rows.length) return this.empty(pending ? __("No pending leave requests.") : __("No leave scheduled."));
		return `<div class="na-leave-list">${rows.map((row) => `<article><div><button data-employee="${this.esc(row.employee)}">${this.esc(row.employee_name)}</button><span class="na-badge status-on-leave">${this.esc(__(row.leave_type))}</span></div><p>${frappe.datetime.str_to_user(row.from_date)} → ${frappe.datetime.str_to_user(row.to_date)} · ${row.total_leave_days} ${__("days")}</p>${row.description ? `<small>${this.esc(row.description)}</small>` : ""}<div class="na-leave-actions">${pending ? row.actions.map((action) => `<button class="btn btn-${action.toLowerCase().includes("reject") ? "default" : "primary"} btn-xs" data-leave-action="${this.esc(action)}" data-leave-name="${this.esc(row.name)}">${this.esc(__(action))}</button>`).join("") : ""}<button class="btn btn-default btn-xs" onclick="frappe.set_route('Form', 'Leave Application', '${this.esc(row.name)}')">${__("View Application")}</button></div></article>`).join("")}</div>`;
	}

	async apply_leave_action(button) {
		const action = button.dataset.leaveAction;
		frappe.confirm(__("Apply workflow action {0}?", [__(action)]), async () => {
			await this.call("apply_leave_action", { name: button.dataset.leaveName, action });
			frappe.show_alert({ message: __("Leave request updated"), indicator: "green" });
			this.load_leave();
		});
	}

	async open_employee(employee) {
		const dialog = new frappe.ui.Dialog({ title: __("Employee attendance"), size: "large", fields: [{ fieldtype: "HTML", fieldname: "content" }] });
		dialog.fields_dict.content.$wrapper.html(`<div class="na-loading"><span></span><p>${__("Loading employee…")}</p></div>`);
		dialog.show();
		try {
			const data = await this.call("get_employee_details", { employee, date: this.state.date, year: this.state.year, month: this.state.month });
			const row = data.employee;
			if (!row) return dialog.hide();
			dialog.set_title(row.employee_name);
			dialog.fields_dict.content.$wrapper.html(`<div class="na-drawer" dir="${this.is_arabic ? "rtl" : "ltr"}">
				<div class="na-drawer-profile"><span class="na-avatar">${row.image ? `<img src="${this.esc(row.image)}" alt="">` : this.esc(row.employee_name.slice(0, 1))}</span><div><h3>${this.esc(row.employee_name)}</h3><p>${this.esc(row.designation || __("Employee"))}</p><span class="na-badge status-${frappe.scrub(row.status)}">${this.esc(__(row.status))}</span></div></div>
				<div class="na-drawer-metrics">${[["Check In", row.in_time_label], ["Check Out", row.out_time_label], ["Working Today", this.localize_duration(row.working_hours_label)], ["Present This Month", data.month.present], ["Absent This Month", data.month.absent], ["Leave This Month", data.month.leave], ["Late This Month", data.month.late], ["Monthly Hours", this.localize_duration(data.month.working_hours_label)]].map(([label, value]) => `<div><span>${__(label)}</span><strong>${value ?? "—"}</strong></div>`).join("")}</div>
				<h4>${__("Upcoming Leave")}</h4>${this.leave_rows(data.upcoming_leave.map((leave) => ({ ...leave, employee: row.name, employee_name: row.employee_name })))}
				<div class="na-drawer-links"><button class="btn btn-default btn-sm" data-route="Employee">${__("View Employee")}</button><button class="btn btn-default btn-sm" data-route="Attendance">${__("View Attendance")}</button><button class="btn btn-default btn-sm" data-route="Employee Checkin">${__("View Check-ins")}</button><button class="btn btn-default btn-sm" data-route="Leave Application">${__("View Leave Applications")}</button></div>
			</div>`);
			dialog.$wrapper.on("click", "[data-route]", (event) => {
				const doctype = event.currentTarget.dataset.route;
				dialog.hide();
				if (doctype === "Employee") frappe.set_route("Form", "Employee", employee);
				else frappe.set_route("List", doctype, { employee });
			});
		} catch (error) {
			dialog.fields_dict.content.$wrapper.html(this.error_html(error));
		}
	}

	localized_moment(value) {
		const localized = value === undefined ? moment() : moment(value);
		return localized.locale(this.is_arabic ? "ar" : (frappe.boot?.lang || "en"));
	}

	format_full_date(value) {
		return this.localized_moment(value).format(this.is_arabic ? "dddd، D MMMM" : "dddd, D MMMM");
	}

	employee_count(count) {
		if (!this.is_arabic) return count === 1 ? __("One employee") : __("{0} employees", [count]);
		if (count === 1) return __("One employee");
		if (count === 2) return __("Two employees");
		if (count >= 3 && count <= 10) return __("{0} team members", [count]);
		return __("{0} employees total", [count]);
	}

	timeline_activity(row) {
		const employee = `<button data-employee="${this.esc(row.employee)}">${this.esc(row.employee_name)}</button>`;
		return row.log_type === "OUT" ? __("{0} checked out", [employee]) : __("{0} checked in", [employee]);
	}

	localize_duration(value) {
		if (!value) return value || "—";
		const match = String(value).match(/^(\d+)h\s+(\d+)m$/);
		return match ? __("{0} h {1} m", [match[1], match[2]]) : value;
	}

	calendar_tooltip(cell) {
		return [
			cell.date,
			__(cell.status),
			cell.detail ? __(cell.detail) : "",
			`${cell.in_time || "—"}–${cell.out_time || "—"}`,
			this.localize_duration(cell.working_hours_label),
			cell.late ? __("Late") : "",
			cell.early_exit ? __("Early exit") : "",
		].filter(Boolean).join(" · ");
	}

	empty(message) {
		return `<div class="na-empty">${frappe.utils.icon("inbox", "md")}<p>${this.esc(message)}</p></div>`;
	}

	esc(value) {
		return frappe.utils.escape_html(String(value ?? ""));
	}

	error_html(error) {
		return `<div class="na-empty na-error">${frappe.utils.icon("alert-circle", "md")}<p>${this.esc(error?.message || __("Unable to load attendance data."))}</p></div>`;
	}

	render_error(error) {
		this.$root.find(".na-view").html(this.error_html(error));
	}
}
