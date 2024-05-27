# Copyright (c) 2024, Aerele Technologies and contributors
# For license information, please see license.txt

import frappe
import json
from frappe.model.document import Document
from medusa_integration.constants import get_headers
from medusa_integration.utils import send_request


class MedusaConfiguration(Document):
	def validate(self):
		if self.enable:
			self.get_access_token()
		else:
			self.access_token = ""



	def get_access_token(self):
		try:
			args = frappe._dict({
					"method" : "POST",
					"url" : f"{self.url}/admin/auth/token",
					"headers": get_headers(),
					"payload": json.dumps({
									"email": self.admin_email,
									"password": self.get_password("admin_password")
					}),
					"voucher_type": self.doctype,
					"voucher_name": self.name,
					"throw_message": "We are unable to fetch access token please check your admin credentials"
				})

			access_token = send_request(args).get("access_token")
			self.db_set("access_token", access_token)

		except Exception as e:
			frappe.log_error("Access Token", frappe.get_traceback())
