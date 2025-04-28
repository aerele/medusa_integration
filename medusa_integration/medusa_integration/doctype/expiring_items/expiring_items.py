# Copyright (c) 2025, Aerele Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class ExpiringItems(Document):
	def validate(self):
		homepage_doc = frappe.get_doc("Homepage Landing", "Active Homepage Landing")
		
		selected_items = {row.website_item for row in self.expiring_items if row.show}

		existing_clearance_items = {row.website_item: row for row in homepage_doc.clearance_items}

		homepage_doc.clearance_items = [
			row for row in homepage_doc.clearance_items if row.website_item in selected_items
		]

		homepage_existing_items_set = {row.website_item for row in homepage_doc.clearance_items}

		for item in selected_items:
			if item not in homepage_existing_items_set:
				homepage_doc.append("clearance_items", {"website_item": item})

		homepage_doc.save()
