import frappe


def get_url():
	doc = frappe.get_doc("Medusa Configuration", "Medusa Configuration")
	return doc.url, doc.enable

def get_headers(with_token=False):
	doc = frappe.get_doc("Medusa Configuration", "Medusa Configuration")
	if with_token and doc.access_token:
		return {
					'Authorization': 'Bearer '+ doc.access_token,
					'Content-Type': 'application/json',
				}

	else:
		return {
					'Content-Type': 'application/json',
		}