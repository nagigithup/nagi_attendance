app_name = "nagi_attendance"
# This is a translation key. English and Arabic display values are defined in
# translations/ so every Desk launcher surface uses the same requested label.
app_title = "Attendance & Leave App"
app_publisher = "Nagi"
app_description = "Manager-friendly attendance and leave dashboard for Frappe HR"
app_email = "admin@example.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["hrms"]

# Open the existing manager dashboard directly when Attendance & Leave is selected.
# Frappe v16 uses /desk as its canonical Desk route.
app_home = "/desk/manager-attendance"

# Register the app in Frappe's modern Apps screen. A matching standard Desktop Icon fixture
# supports sites that still use Frappe v16's legacy Desktop Icons mode.
add_to_apps_screen = [
	{
		"name": "nagi_attendance",
		# A distinct translation key keeps the dashboard heading unchanged while the
		# app tile displays the requested English and Arabic names.
		"title": "Attendance & Leave App",
		"logo": "/assets/nagi_attendance/images/attendance-app.svg",
		"route": "/desk/manager-attendance",
		"has_permission": "nagi_attendance.api.has_app_permission",
		"sequence_id": 30,
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = "/assets/nagi_attendance/css/nagi_attendance.css"
app_include_js = "/assets/nagi_attendance/js/nagi_attendance.js"

# include js, css files in header of web template
# web_include_css = "/assets/nagi_attendance/css/nagi_attendance.css"
# web_include_js = "/assets/nagi_attendance/js/nagi_attendance.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "nagi_attendance/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "nagi_attendance/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "nagi_attendance.utils.jinja_methods",
# 	"filters": "nagi_attendance.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "nagi_attendance.install.before_install"
# after_install = "nagi_attendance.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "nagi_attendance.uninstall.before_uninstall"
# after_uninstall = "nagi_attendance.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "nagi_attendance.utils.before_app_install"
# after_app_install = "nagi_attendance.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "nagi_attendance.utils.before_app_uninstall"
# after_app_uninstall = "nagi_attendance.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "nagi_attendance.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "nagi_attendance.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"nagi_attendance.tasks.all"
# 	],
# 	"daily": [
# 		"nagi_attendance.tasks.daily"
# 	],
# 	"hourly": [
# 		"nagi_attendance.tasks.hourly"
# 	],
# 	"weekly": [
# 		"nagi_attendance.tasks.weekly"
# 	],
# 	"monthly": [
# 		"nagi_attendance.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "nagi_attendance.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "nagi_attendance.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "nagi_attendance.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "nagi_attendance.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["nagi_attendance.utils.before_request"]
# after_request = ["nagi_attendance.utils.after_request"]

# Job Events
# ----------
# before_job = ["nagi_attendance.utils.before_job"]
# after_job = ["nagi_attendance.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"nagi_attendance.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
