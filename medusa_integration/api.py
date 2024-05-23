import frappe
import requests
import json
from medusa_integration.constants import get_headers,get_url
from medusa_integration.utils import send_request,generate_random_string

def create_medusa_product(self, method):
	if get_url()[1] and not self.get_doc_before_save() and not self.variant_of:
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
		create_medusa_variant(self.medusa_id)


def create_medusa_variant(product_id):
	option_id = create_medusa_option(product_id)
	payload = json.dumps({
			"title": "Default",
			"material": None,
			"mid_code": None,
			"hs_code": None,
			"origin_country": None,
			"sku": None,
			"ean": None,
			"upc": None,
			"barcode": None,
			"inventory_quantity": 0,
			"manage_inventory": True,
			"allow_backorder": False,
			"weight": None,
			"width": None,
			"height": None,
			"length": None,
			"prices": [],
			"metadata": {},
			"options": [
				{
					"option_id": option_id,
					"value": "Default"
				}
			]
	})
	args = frappe._dict({
		"method" : "POST",
		"url" : f"{get_url()[0]}/admin/products/{product_id}/variants",
		"headers": get_headers(with_token=True),
		"payload": payload,
		"throw_message": "We are unable to fetch access token please check your admin credentials"
	})
	
	send_request(args)

def create_medusa_option(product_id):
	payload = json.dumps({
					"title": "Default",
		})
	args = frappe._dict({
		"method" : "POST",
		"url" : f"{get_url()[0]}/admin/products/{product_id}/options",
		"headers": get_headers(with_token=True),
		"payload": payload,
		"throw_message": "We are unable to fetch access token please check your admin credentials"
	})

	return send_request(args).get("product").get("options")[0].get("id")