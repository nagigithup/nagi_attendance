import hashlib
import json
from pathlib import Path

import frappe
from frappe.boot import load_translations

from nagi_attendance import __version__

no_cache = 1


def get_frontend_assets():
	asset_root = "/assets/nagi_attendance/attendance/"
	public_path = Path(frappe.get_app_path("nagi_attendance", "public", "attendance"))
	manifest_path = public_path / "asset-manifest.json"
	try:
		manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
		entry = next(value for value in manifest.values() if value.get("isEntry"))
		javascript = entry["file"]
		stylesheets = entry.get("css", [])
		version = Path(javascript).stem.removeprefix("app.")
		return frappe._dict(
			javascript=f"{asset_root}{javascript}",
			stylesheets=[f"{asset_root}{filename}" for filename in stylesheets],
			version=version,
		)
	except (OSError, ValueError, KeyError, StopIteration, TypeError):
		# Development fallback for a checkout that has not run the Vite build yet.
		legacy_files = [public_path / "app.js", public_path / "app.css"]
		digest = hashlib.sha256()
		try:
			for filename in legacy_files:
				digest.update(filename.read_bytes())
			version = digest.hexdigest()[:12]
		except OSError:
			version = __version__
		return frappe._dict(
			javascript=f"{asset_root}app.js?v={version}",
			stylesheets=[f"{asset_root}app.css?v={version}"],
			version=version,
		)


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
	context.frontend_assets = get_frontend_assets()
	return context
