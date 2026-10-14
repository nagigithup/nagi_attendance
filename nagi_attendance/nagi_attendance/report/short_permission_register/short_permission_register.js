frappe.query_reports["Short Permission Register"] = {
	filters: [
		{fieldname:"company", label:__("Company"), fieldtype:"Link", options:"Company"},
		{fieldname:"department", label:__("Department"), fieldtype:"Link", options:"Department"},
		{fieldname:"employee", label:__("Employee"), fieldtype:"Link", options:"Employee"},
		{fieldname:"from_date", label:__("From Date"), fieldtype:"Date"},
		{fieldname:"to_date", label:__("To Date"), fieldtype:"Date"},
		{fieldname:"status", label:__("Status"), fieldtype:"Select", options:"\nPending\nApproved\nRejected\nCancelled"},
	]
}
