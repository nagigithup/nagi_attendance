frappe.pages["manager-attendance"].on_page_load = (wrapper) => {
	frappe.nagi_attendance = wrapper.nagi_attendance = new NagiAttendance(wrapper);
};

frappe.pages["manager-attendance"].on_page_show = (wrapper) => {
	if (wrapper.nagi_attendance?.initialized) wrapper.nagi_attendance.refresh();
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
			permission_company: "",
			permission_from: "",
			permission_to: "",
			permission_status: "Pending",
			permission_type: "",
			permission_page: 1,
		};
		this.restore_state();
		this.render_shell();
		this.bind_events();
		this.bind_pending_updates();
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
		await this.refresh_permission_context();
		await this.load_active();
		this.initialized = true;
	}

	async refresh() {
		await this.refresh_permission_context();
		await this.load_active();
	}


	bind_pending_updates() {
		const previous = frappe.nagi_attendance;
		if (previous?.leave_invalidation_handler) {
			frappe.realtime?.off("hrms:refetch_resource", previous.leave_invalidation_handler);
			frappe.realtime?.off("notification", previous.notification_handler);
			clearTimeout(previous.pending_update_timer);
		}
		this.leave_invalidation_handler = (data) => {
			const keys = Array.isArray(data?.cache_key) ? data.cache_key : [data?.cache_key];
			if (keys.includes("hrms:team_leaves")) this.schedule_pending_refresh();
		};
		this.notification_handler = () => this.schedule_pending_refresh();
		frappe.realtime?.on("hrms:refetch_resource", this.leave_invalidation_handler);
		frappe.realtime?.on("notification", this.notification_handler);
		// A standalone development server may have no Socket.IO connection.
		$(window).off("focus.nagi_pending").on("focus.nagi_pending", this.notification_handler);
		$(document).off("visibilitychange.nagi_pending").on("visibilitychange.nagi_pending", this.notification_handler);
	}

	schedule_pending_refresh() {
		if (!this.initialized || document.visibilityState === "hidden" || !this.$root.is(":visible")) return;
		clearTimeout(this.pending_update_timer);
		this.pending_update_timer = setTimeout(async () => {
			if (document.visibilityState === "hidden" || !this.$root.is(":visible")) return;
			if (this.leave_actions_busy?.size || this.permission_actions_busy?.size) return;
			await this.refresh_permission_context();
			if (this.state.tab === "leave") await this.load_leave();
			else if (this.state.tab === "permissions") await this.load_permissions();
		}, 250);
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
					<div class="na-hero-actions"><span class="na-pending-notification" data-pending-notification hidden aria-live="polite"><span>${__("Pending My Approval")}</span><strong data-total-pending>0</strong></span><button class="btn btn-default btn-sm" data-action="refresh">${frappe.utils.icon("refresh-cw", "sm")} ${__("Refresh")}</button></div>
				</section>
				<nav class="na-tabs" aria-label="${__("Dashboard views")}">
					<button class="${this.state.tab === "today" ? "active" : ""}" data-tab="today">${__("Today")}</button>
					<button class="${this.state.tab === "monthly" ? "active" : ""}" data-tab="monthly">${__("Monthly Attendance")}</button>
					<button class="${this.state.tab === "leave" ? "active" : ""}" data-tab="leave"><span>${__("Leave")}</span><span class="na-tab-count" data-leave-count hidden>0</span></button>
					<button class="${this.state.tab === "permissions" ? "active" : ""}" data-tab="permissions" hidden><span>${__("Short Permissions")}</span><span class="na-tab-count" data-permission-count hidden>0</span></button>
				</nav>
				<section class="na-filters"></section>
				<div class="na-view" aria-live="polite"></div>
			</div>`
		).appendTo(this.page.main);
		this.render_filters();
	}

	render_filters() {
		this.$root.find(".na-filters").toggleClass("na-permission-filters", this.state.tab === "permissions");
		if (this.state.tab === "permissions") {
			const context = this.permission_context?.filters || { companies: [], departments: [], employees: [] };
			this.$root.find(".na-filters").html(`
				<label>${__("Company")}<select data-filter="permission_company"><option value="">${__("All companies")}</option>${context.companies.map((name) => `<option value="${this.esc(name)}" ${this.state.permission_company === name ? "selected" : ""}>${this.esc(name)}</option>`).join("")}</select></label>
				<label>${__("Department")}<select data-filter="department"><option value="">${__("All departments")}</option>${context.departments.map((name) => `<option value="${this.esc(name)}" ${this.state.department === name ? "selected" : ""}>${this.esc(name)}</option>`).join("")}</select></label>
				<label>${__("Employee")}<select data-filter="employee"><option value="">${__("All employees")}</option>${context.employees.filter((row) => !this.state.permission_company || row.company === this.state.permission_company).map((row) => `<option value="${this.esc(row.name)}" ${this.state.employee === row.name ? "selected" : ""}>${this.esc(row.employee_name)}</option>`).join("")}</select></label>
				<label>${__("From Date")}<input type="date" data-filter="permission_from" value="${this.esc(this.state.permission_from)}"></label>
				<label>${__("To Date")}<input type="date" data-filter="permission_to" value="${this.esc(this.state.permission_to)}"></label>
				<label>${__("Status")}<select data-filter="permission_status"><option value="">${__("All authorized requests")}</option>${["Pending", "Approved", "Rejected", "Cancelled"].map((value) => `<option value="${value}" ${this.state.permission_status === value ? "selected" : ""}>${this.permission_status_label(value)}</option>`).join("")}</select></label>
				<label>${__("Permission Type")}<select data-filter="permission_type"><option value="">${__("All permission types")}</option>${["Late Arrival", "Early Departure", "Temporary Exit"].map((value) => `<option value="${value}" ${this.state.permission_type === value ? "selected" : ""}>${__(value)}</option>`).join("")}</select></label>`);
			return;
		}
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
		this.$root.on("click", "[data-tab]", async (event) => {
			this.state.tab = event.currentTarget.dataset.tab;
			this.$root.find("[data-tab]").removeClass("active");
			$(event.currentTarget).addClass("active");
			if (["leave", "permissions"].includes(this.state.tab)) await this.refresh_permission_context();
			this.render_filters();
			this.persist_state();
			this.load_active();
		});
		this.$root.on("change", "[data-filter]", (event) => {
			const key = event.currentTarget.dataset.filter;
			this.state[key] = ["month", "year"].includes(key) ? Number(event.currentTarget.value) : event.currentTarget.value;
			if (this.state.tab === "permissions") this.state.permission_page = 1;
			this.persist_state();
			if (key === "status") this.apply_status_filter();
			else {
				if (key === "permission_company") this.render_filters();
				this.load_active();
			}
		});
		this.$root.on("click", '[data-action="refresh"]', () => this.refresh());
		this.$root.on("click", "[data-summary-status]", (event) => {
			this.state.status = event.currentTarget.dataset.summaryStatus;
			this.$root.find('[data-filter="status"]').val(this.state.status);
			this.apply_status_filter();
		});
		this.$root.on("click", "[data-employee]", (event) => this.open_employee(event.currentTarget.dataset.employee));
		this.$root.on("click", "[data-leave-action]", (event) => this.apply_leave_action(event.currentTarget));
		this.$root.on("click", "[data-leave-view]", (event) => this.open_leave(event.currentTarget.dataset.leaveView));
		this.$root.on("click", "[data-permission-action]", (event) => {
			event.stopPropagation();
			this.apply_permission_action(event.currentTarget);
		});
		this.$root.on("click", "[data-permission-view]", (event) => {
			event.stopPropagation();
			this.open_permission(event.currentTarget.dataset.permissionView);
		});
		this.$root.on("click", "[data-permission-name]", (event) => {
			if (!$(event.target).closest("button").length) this.open_permission(event.currentTarget.dataset.permissionName);
		});
		this.$root.on("click", "[data-permission-page]", (event) => {
			this.state.permission_page = Number(event.currentTarget.dataset.permissionPage);
			this.persist_state();
			this.load_permissions();
		});
		this.$root.on("click", "[data-clear-permission-filters]", () => this.clear_permission_filters());
	}

	load_active() {
		if (this.state.tab === "today") return this.load_today();
		if (this.state.tab === "monthly") return this.load_monthly();
		if (this.state.tab === "leave") return this.load_leave();
		return this.load_permissions();
	}

	loading() {
		this.$root.find(".na-view").html(`<div class="na-loading"><span></span><p>${__("Loading attendance…")}</p></div>`);
	}

	async call(method, args = {}) {
		return (await frappe.call({ method: `nagi_attendance.api.${method}`, args, freeze: false })).message;
	}

	async refresh_permission_context() {
		const refresh_id = this.pending_refresh_id = (this.pending_refresh_id || 0) + 1;
		try {
			const context = await this.call("get_manager_pending_context");
			if (refresh_id !== this.pending_refresh_id) return;
			this.permission_context = context.short_permissions;
			this.pending_context = context;
		} catch (_) {
			if (refresh_id !== this.pending_refresh_id) return;
			this.permission_context = { visible: false, pending_count: 0, filters: {} };
			this.pending_context = { leave_count: 0, short_permission_count: 0, total_pending: 0 };
		}
		const pending = this.pending_context;
		this.$root.find("[data-leave-count]").text(this.format_number(pending.leave_count)).prop("hidden", !pending.leave_count);
		this.$root.find("[data-total-pending]").text(this.format_number(pending.total_pending));
		this.$root.find("[data-pending-notification]").prop("hidden", !pending.total_pending);
		const tab = this.$root.find('[data-tab="permissions"]');
		tab.prop("hidden", !this.permission_context.visible);
		const count = tab.find("[data-permission-count]");
		count.text(this.format_number(this.permission_context.pending_count || 0)).prop("hidden", !this.permission_context.pending_count);
		if (!this.permission_context.visible && this.state.tab === "permissions") {
			this.state.tab = "today";
			this.$root.find("[data-tab]").removeClass("active");
			this.$root.find('[data-tab="today"]').addClass("active");
			this.render_filters();
			this.persist_state();
		}
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
		return `<div class="na-leave-list">${rows.map((row) => `<article><div><button data-employee="${this.esc(row.employee)}">${this.esc(row.employee_name)}</button><span class="na-badge status-on-leave">${this.esc(__(row.leave_type))}${row.status ? ` · ${this.esc(__(row.status))}` : ""}</span></div><p>${frappe.datetime.str_to_user(row.from_date)} → ${frappe.datetime.str_to_user(row.to_date)} · ${this.format_number(row.total_leave_days)} ${__("days")}</p>${row.description ? `<small>${this.esc(row.description)}</small>` : ""}<div class="na-leave-actions">${pending ? this.leave_action_buttons(row, row.actions || []) : ""}<button class="btn btn-default btn-xs" data-leave-view="${this.esc(row.name)}">${__("View Request")}</button></div></article>`).join("")}</div>`;
	}

	leave_action_buttons(row, actions) {
		return actions.map((action) => `<button class="btn btn-${action.toLowerCase().includes("reject") ? "default" : "primary"} btn-sm" data-leave-action="${this.esc(action)}" data-leave-name="${this.esc(row.name)}" data-leave-modified="${this.esc(row.modified || "")}">${this.esc(__(action))}</button>`).join("");
	}

	async open_leave(name) {
		if (this.state.tab !== "leave") {
			this.state.tab = "leave";
			this.$root.find("[data-tab]").removeClass("active");
			this.$root.find('[data-tab="leave"]').addClass("active");
			this.render_filters();
			this.persist_state();
			await this.load_leave();
		}
		this.leave_dialog?.dialog.hide();
		const dialog = new frappe.ui.Dialog({ title: __("Leave Request Details"), size: "large", fields: [{ fieldtype: "HTML", fieldname: "content" }] });
		this.leave_dialog = { name, dialog };
		dialog.fields_dict.content.$wrapper.html(`<div class="na-loading"><span></span><p>${__("Loading leave request…")}</p></div>`);
		dialog.$wrapper.on("click", "[data-leave-action]", (event) => this.apply_leave_action(event.currentTarget));
		dialog.show();
		try {
			this.render_leave_details(dialog, await this.call("get_leave_details", { name }));
		} catch (error) {
			dialog.fields_dict.content.$wrapper.html(this.error_html(error));
		}
	}

	render_leave_details(dialog, data) {
		const row = data.request;
		const fields = [
			["Employee ID", row.employee], ["Leave Type", __(row.leave_type)],
			["From Date", frappe.datetime.str_to_user(row.from_date)], ["To Date", frappe.datetime.str_to_user(row.to_date)],
			["Total Leave Days", this.format_number(row.total_leave_days)], ["Half Day", __(row.half_day ? "Yes" : "No")],
			["Approver", row.leave_approver_name || row.leave_approver], ["Status", __(row.status)],
		];
		if (row.half_day && row.half_day_date) fields.push(["Half Day Date", frappe.datetime.str_to_user(row.half_day_date)]);
		if (data.leave_balance != null) fields.push(["Leave Balance on From Date", this.format_number(data.leave_balance)]);
		if (row.workflow_state) fields.push(["Workflow State", __(row.workflow_state)]);
		dialog.set_title(`${__("Leave Request Details")} · ${this.esc(row.name)}`);
		dialog.fields_dict.content.$wrapper.html(`<div class="na-permission-detail na-leave-detail" dir="${this.is_arabic ? "rtl" : "ltr"}">
			<div class="na-drawer-profile"><span class="na-avatar">${this.esc((row.employee_name || "?").slice(0, 1))}</span><div><h3>${this.esc(row.employee_name)}</h3><p>${this.esc([row.company, row.department].filter(Boolean).join(" · "))}</p><span class="na-badge status-${frappe.scrub(row.status)}">${this.esc(__(row.status))}</span></div></div>
			<div class="na-permission-detail-grid">${fields.map(([label, value]) => `<div><span>${__(label)}</span><strong>${this.esc(value ?? "—")}</strong></div>`).join("")}</div>
			<section class="na-permission-reason"><span>${__("Reason")}</span><p>${this.esc(row.description || "—")}</p></section>
			<div class="na-leave-actions">${this.leave_action_buttons(row, data.actions || [])}</div>
		</div>`);
	}

	async apply_leave_action(button) {
		const name = button.dataset.leaveName, action = button.dataset.leaveAction;
		this.leave_actions_busy ||= new Set();
		if (this.leave_actions_busy.has(name)) return;
		this.leave_actions_busy.add(name);
		const $buttons = this.$root.add(this.leave_dialog?.dialog.$wrapper || []).find("[data-leave-action]").filter((_index, node) => node.dataset.leaveName === name);
		const original_label = button.innerHTML;
		$buttons.prop("disabled", true);
		button.innerHTML = `${frappe.utils.icon("loader", "xs")} ${__("Processing…")}`;
		try {
			await this.call("apply_leave_action", { name, action, modified: button.dataset.leaveModified || undefined });
			frappe.show_alert({ message: __("Leave request updated"), indicator: "green" });
			await this.refresh();
			if (this.leave_dialog?.name === name) this.render_leave_details(this.leave_dialog.dialog, await this.call("get_leave_details", { name }));
		} catch (error) {
			frappe.msgprint({ title: __("Unable to update leave request"), message: this.esc(error?.message || error), indicator: "red" });
		} finally {
			this.leave_actions_busy.delete(name);
			if (button.isConnected) {
				button.innerHTML = original_label;
				$buttons.prop("disabled", false);
			}
		}
	}

	async load_permissions() {
		if (!this.permission_context?.visible) return;
		this.loading();
		try {
			this.permissions = await this.call("get_short_permission_dashboard", {
				company: this.state.permission_company,
				department: this.state.department,
				employee: this.state.employee,
				from_date: this.state.permission_from,
				to_date: this.state.permission_to,
				status: this.state.permission_status,
				permission_type: this.state.permission_type,
				page: this.state.permission_page,
				page_length: 20,
			});
			this.render_permissions();
		} catch (error) {
			this.render_error(error);
		}
	}

	render_permissions() {
		const data = this.permissions;
		const summary = data.summary || {};
		const cards = [
			["pending", __("Pending My Approval"), "clock-3"],
			["approved", __("Approved Requests"), "circle-check"],
			["rejected", __("Rejected Requests"), "circle-x"],
			["approved_hours", __("Total Approved Permission Hours"), "timer"],
		].map(([key, label, icon]) => `<article class="na-permission-stat na-permission-stat-${key}"><span class="na-permission-stat-icon" aria-hidden="true">${frappe.utils.icon(icon, "md")}</span><div><span>${label}</span><strong>${key === "approved_hours" ? this.format_permission_duration(summary[key] ?? 0) : this.format_number(summary[key] ?? 0)}</strong></div></article>`).join("");
		const rows = data.rows.map((row) => `<tr class="na-permission-row" data-permission-name="${this.esc(row.name)}" tabindex="0">
			<td><button class="na-permission-person" data-employee="${this.esc(row.employee)}"><strong>${this.esc(row.employee_name)}</strong><small>${this.esc(row.employee)}</small></button></td>
			<td><div class="na-permission-company"><strong>${this.esc(row.company)}</strong><small>${this.esc(row.department || "—")}</small></div></td>
			<td>${frappe.datetime.str_to_user(row.permission_date)}</td><td>${this.esc(__(row.permission_type))}</td>
			<td class="na-time">${this.format_time(row.from_time)} <span aria-hidden="true">–</span> ${this.format_time(row.to_time)}</td>
			<td>${this.format_permission_duration(row.duration_hours)}</td><td><span class="na-reason" tabindex="0" title="${this.esc(row.reason || "")}" aria-label="${this.esc(row.reason || __("No reason provided"))}">${this.esc(row.reason || "—")}</span></td>
			<td><span class="na-badge status-${frappe.scrub(row.status)}">${this.esc(this.permission_status_label(row.status))}</span>${!row.feature_enabled ? `<small class="na-disabled-feature">${__("Feature disabled")}</small>` : ""}</td>
			<td><div class="na-permission-actions">${row.can_action ? `<button class="btn btn-primary btn-xs" data-permission-action="Approve" data-permission-name="${this.esc(row.name)}">${__("Approve")}</button><button class="btn btn-default btn-xs" data-permission-action="Reject" data-permission-name="${this.esc(row.name)}">${__("Reject")}</button>` : `<button class="btn btn-default btn-xs" data-permission-view="${this.esc(row.name)}">${__("View Details")}</button>`}</div></td>
		</tr>`).join("");
		const pages = Math.max(1, Math.ceil(data.total / data.page_length));
		const pagination = pages > 1 ? `<div class="na-pagination"><button class="btn btn-default btn-sm" data-permission-page="${data.page - 1}" ${data.page <= 1 ? "disabled" : ""}>${__("Previous")}</button><span>${__("Page {0} of {1}", [data.page, pages])}</span><button class="btn btn-default btn-sm" data-permission-page="${data.page + 1}" ${data.page >= pages ? "disabled" : ""}>${__("Next")}</button></div>` : "";
		const content = data.rows.length ? `<div class="na-permission-table-wrap" role="region" aria-label="${__("Permission Request History")}" tabindex="0"><table class="na-permission-table"><thead><tr>${["Employee", "Company / Department", "Permission Date", "Permission Type", "From – To", "Duration", "Reason", "Status", "Actions"].map((label) => `<th scope="col">${__(label)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>${pagination}` : `<div class="na-permission-empty">${frappe.utils.icon("inbox", "lg")}<h4>${__("No permission requests")}</h4><p>${__("No requests match the current filters.")}</p>${this.permission_filters_active() ? `<button class="btn btn-default btn-sm" data-clear-permission-filters>${__("Clear filters")}</button>` : ""}</div>`;
		this.$root.find(".na-view").html(`<div class="na-permission-stats">${cards}</div>
			<section class="na-panel na-permission-panel"><div class="na-panel-head"><div><span>${__("Short Permissions")}</span><h3>${__("Permission Request History")}</h3></div><small>${__("{0} requests", [this.format_number(data.total)])}</small></div>${content}</section>`);
	}

	permission_filters_active() {
		return Boolean(this.state.permission_company || this.state.department || this.state.employee || this.state.permission_from || this.state.permission_to || this.state.permission_type || !["", "Pending"].includes(this.state.permission_status));
	}

	clear_permission_filters() {
		Object.assign(this.state, {
			permission_company: "",
			department: "",
			employee: "",
			permission_from: "",
			permission_to: "",
			permission_status: "Pending",
			permission_type: "",
			permission_page: 1,
		});
		this.render_filters();
		this.persist_state();
		this.load_permissions();
	}

	async open_permission(name) {
		const dialog = new frappe.ui.Dialog({
			title: __("Short Permission Details"),
			size: "large",
			fields: [{ fieldtype: "HTML", fieldname: "content" }],
		});
		dialog.fields_dict.content.$wrapper.html(`<div class="na-loading"><span></span><p>${__("Loading permission request…")}</p></div>`);
		dialog.show();
		try {
			const data = await this.call("get_short_permission_details", { name });
			const row = data.request;
			dialog.set_title(`${__("Short Permission")} · ${this.esc(row.name)}`);
			const attendance = data.attendance;
			const shift = data.shift;
			dialog.fields_dict.content.$wrapper.html(`<div class="na-permission-detail" dir="${this.is_arabic ? "rtl" : "ltr"}">
				<div class="na-drawer-profile"><span class="na-avatar">${this.esc((row.employee_name || "?").slice(0, 1))}</span><div><h3>${this.esc(row.employee_name)}</h3><p>${this.esc([row.company, row.department].filter(Boolean).join(" · "))}</p><span class="na-badge status-${frappe.scrub(row.status)}">${this.esc(this.permission_status_label(row.status))}</span></div></div>
				<div class="na-permission-detail-grid">${[
					["Employee ID", row.employee], ["Permission Date", frappe.datetime.str_to_user(row.permission_date)], ["Permission Type", __(row.permission_type)], ["From Time", this.format_time(row.from_time)], ["To Time", this.format_time(row.to_time)], ["Duration", this.format_permission_duration(row.duration_hours)], ["Approver", row.approver], ["Shift", shift?.shift_type || "—"], ["Shift Interval", shift ? `${this.format_datetime(shift.start_datetime)} – ${this.format_datetime(shift.end_datetime)}` : "—"], ["Attendance Status", attendance ? __(attendance.status) : __("No submitted attendance")], ["Check In", attendance ? this.format_datetime(attendance.in_time) : "—"], ["Check Out", attendance ? this.format_datetime(attendance.out_time) : "—"], ["Actual Working Hours", attendance ? attendance.working_hours : "—"], ["Late", attendance ? __(attendance.late_entry ? "Yes" : "No") : "—"], ["Early exit", attendance ? __(attendance.early_exit ? "Yes" : "No") : "—"], ["Manager Comment", row.manager_comment || "—"], ["Decision By", row.decision_by || "—"], ["Decision On", this.format_datetime(row.decision_on)],
				].map(([label, value]) => `<div><span>${__(label)}</span><strong>${this.esc(value ?? "—")}</strong></div>`).join("")}</div>
				<section class="na-permission-reason"><span>${__("Reason")}</span><p>${this.esc(row.reason || "—")}</p></section>
			</div>`);
		} catch (error) {
			dialog.fields_dict.content.$wrapper.html(this.error_html(error));
		}
	}

	async apply_permission_action(button) {
		const name = button.dataset.permissionName;
		const action = button.dataset.permissionAction;
		this.permission_actions_busy ||= new Set();
		if (this.permission_actions_busy.has(name)) return;
		this.permission_actions_busy.add(name);
		const $actions = $(button).closest(".na-permission-actions");
		const $buttons = $actions.find("button");
		const original_label = button.innerHTML;
		$buttons.prop("disabled", true);
		button.innerHTML = `${frappe.utils.icon("loader", "xs")} ${__("Processing…")}`;
		try {
			await frappe.call({
				method: "nagi_attendance.short_permission.apply_permission_action",
				args: { name, action },
				freeze: false,
			});
			frappe.show_alert({ message: action === "Approve" ? __("Permission request approved") : __("Permission request rejected"), indicator: "green" });
			await this.refresh_permission_context();
			await this.load_permissions();
		} catch (error) {
			frappe.msgprint({ title: __("Unable to update permission request"), message: this.esc(error?.message || error), indicator: "red" });
		} finally {
			this.permission_actions_busy.delete(name);
			if (button.isConnected) {
				button.innerHTML = original_label;
				$buttons.prop("disabled", false);
			}
		}
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
			dialog.$wrapper.on("click", "[data-leave-view]", (event) => this.open_leave(event.currentTarget.dataset.leaveView));
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

	format_time(value) {
		return value ? String(value).slice(0, 5) : "—";
	}

	format_number(value) {
		return new Intl.NumberFormat(this.is_arabic ? "ar" : "en", { maximumFractionDigits: 2 }).format(Number(value) || 0);
	}

	format_permission_duration(value) {
		const amount = Number(value) || 0;
		return amount === 1 ? __("{0} hour", [this.format_number(amount)]) : __("{0} hours", [this.format_number(amount)]);
	}

	permission_status_label(status) {
		return __(status);
	}

	format_datetime(value) {
		return value ? this.localized_moment(value).format("YYYY-MM-DD HH:mm") : "—";
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
