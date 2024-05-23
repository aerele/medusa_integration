import frappe
import requests
import json
from medusa_integration.constants import get_headers,get_url
from medusa_integration.utils import send_request

def create_medusa_product(self, method):
	if get_url()[1] and not self.get_doc_before_save():
		payload = json.dumps({
								"title": self.item_code,
								"handle": "",
								"discountable": False,
								"is_giftcard": False,
								"description": self.description,
								"options": [],
								"variants": [],
								"status": "published",
								"sales_channels": []
		})
		args = frappe._dict({
			"method" : "POST",
			"url" : f"{get_url()[0]}/admin/products",
			"headers": get_headers(with_token=True),
			"payload": payload,
			"throw_message": "We are unable to fetch access token please check your admin credentials"
		})

		self.medusa_id = send_request(args).get("product").get("id")
