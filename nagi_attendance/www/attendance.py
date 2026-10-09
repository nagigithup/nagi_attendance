import json

import frappe
from frappe.boot import load_translations


no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/attendance"
		raise frappe.Redirect
	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()  # nosempgrep
	boot = frappe._dict(lang=frappe.local.lang)
	load_translations(boot)
	context.no_cache = 1
	context.csrf_token = csrf_token
	context.boot_json = json.dumps(boot, default=str)
	return context
