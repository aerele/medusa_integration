import frappe
import json
from medusa_integration.constants import get_headers,get_url
from medusa_integration.utils import send_request,generate_random_string

def create_medusa_product(self, method):
	if get_url()[1] and not self.get_doc_before_save() and not self.variant_of:
		# item_group = frappe.get_doc("Item Group", self.item_group)
		# if not item_group.custom_collection_id:
		# 	create_medusa_collection(self=item_group,method=None)
		custom_collection_id = frappe.get_value("Item Group", {"item_group_name": self.item_group}, "custom_collection_id")

		if not custom_collection_id:
			custom_collection_id = create_medusa_collection(self,method=None)
			
		payload = json.dumps({
						"title": self.item_code,
						"handle": "",
						"discountable": False,
						"is_giftcard": False,
						"collection_id": custom_collection_id,
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

def create_medusa_collection(self, method):
	if get_url()[1] and not self.get_doc_before_save():
		payload = json.dumps({
						"title": self.name,
						"handle": "",
						"metadata": {}
		})
		args = frappe._dict({
			"method" : "POST",
			"url" : f"{get_url()[0]}/admin/collections",
			"headers": get_headers(with_token=True),
			"payload": payload,
			"throw_message": "We are unable to fetch access token please check your admin credentials"
		})

		self.db_set("custom_collection_id", send_request(args).get("collection").get("id"))
	return self.custom_collection_id

def create_medusa_price_list(self, method):
	if get_url()[1] and not self.get_doc_before_save():
		payload = json.dumps({
			"name":self.item_code,
			"description":self.item_description,
			"type":self.price_list,
			"customer_groups":[],
			"status":"active",
			"ends_at":"2024-06-30T18:30:00.000Z",
			"starts_at":"2024-05-30T18:30:00.000Z",
			"prices":[
			{
				"amount":2200,
				"variant_id":"variant_01HYFJ4SYSBDJJPERRFP5RP69E",
				"currency_code":"usd"
			},
			{
				"amount":2200,
				"variant_id":"variant_01HYFJ4SYSBDJJPERRFP5RP69E",
				"currency_code":"eur"
			}
			]
			})
		args = frappe._dict({
			"method" : "POST",
			"url" : f"{get_url()[0]}/admin/price-lists",
			"headers": get_headers(with_token=True),
			"payload": payload,
			"throw_message": "We are unable to fetch access token please check your admin credentials"
		})

		custom_medusa_pricelist_id = send_request(args).get("price_list").get("id")
