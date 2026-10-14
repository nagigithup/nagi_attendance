import frappe

LEGACY_NAME = "Nagi Attendance"
MODULE = "Nagi Attendance"


def execute():
	"""Remove only the app-owned landing records replaced by the direct Desk Page shell."""
	_delete_owned_doc("Workspace", public=1)
	_delete_owned_doc("Workspace Sidebar", standard=1)
	_delete_generated_sidebar()


def _delete_owned_doc(doctype: str, **expected) -> None:
	if not frappe.db.exists(doctype, LEGACY_NAME):
		return

	row = frappe.db.get_value(doctype, LEGACY_NAME, ["module", *expected], as_dict=True)
	if not row or row.module != MODULE or any(row.get(field) != value for field, value in expected.items()):
		return

	frappe.delete_doc(
		doctype,
		LEGACY_NAME,
		force=True,
		ignore_permissions=True,
	)


def _delete_generated_sidebar() -> None:
	if not frappe.db.exists("Sidebar", LEGACY_NAME):
		return

	row = frappe.db.get_value("Sidebar", LEGACY_NAME, ["module", "standard", "app"], as_dict=True)
	items = frappe.get_all(
		"Sidebar Item",
		filters={"parent": LEGACY_NAME, "parenttype": "Sidebar"},
		fields=["link_type", "link_to"],
	)
	generated_only = items and all(
		item.link_type == "Page" and item.link_to == "manager-attendance" for item in items
	)
	if not row or row.module != MODULE or row.standard or row.app or not generated_only:
		return

	frappe.delete_doc(
		"Sidebar",
		LEGACY_NAME,
		force=True,
		ignore_permissions=True,
	)
