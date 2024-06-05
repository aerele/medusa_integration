import requests
import frappe
import json
from medusa_integration.constants import get_headers,get_url
from medusa_integration.utils import send_request,generate_random_string
from urllib.parse import urlparse, quote

def create_medusa_product(self, method):
	item_group = frappe.get_doc("Item Group", self.item_group)
	payload = {
					"title": self.item_code,
					"discountable": False,
					"is_giftcard": False,
					"collection_id": item_group.medusa_id,
					"description": self.description,
					"status": "published"
	}

	if not item_group.medusa_id:
		create_medusa_collection(self=item_group,method=None)

	if get_url()[1] and not self.get_doc_before_save():
		args = frappe._dict({
						"method" : "POST",
						"url" : f"{get_url()[0]}/admin/products",
						"headers": get_headers(with_token=True),
						"payload": json.dumps(payload),
						"throw_message": "We are unable to fetch access token please check your admin credentials"
		})

		self.medusa_id = send_request(args).get("product").get("id")
		self.medusa_variant_id = create_medusa_variant(self.medusa_id)

	if self.medusa_id and self.get_doc_before_save():
		payload.pop("is_giftcard")
		args = frappe._dict({
						"method" : "POST",
						"url" : f"{get_url()[0]}/admin/products/{self.medusa_id}",
						"headers": get_headers(with_token=True),
						"payload": json.dumps(payload),
						"throw_message": "We are unable to fetch access token please check your admin credentials"
		})
		send_request(args)

def upload_image_to_medusa(self, method):
	if self.medusa_id: #and self.get_doc_before_save():
		# image_path = frappe.get_value(
		# 	"File",
		# 	{"attached_to_doctype": self.doctype, "attached_to_name": self.item_name},
		# 	"file_url")		
		print("image uploaded")
		doc = frappe.get_doc("File", {"attached_to_doctype": self.doctype, "attached_to_name": self.item_name})
		image_path = doc.get_full_path()
		# Parse the URL
		parsed_url = urlparse(image_path)

		# Assign the path to a variable
		path = parsed_url.path
		image_path = quote(path)
		print("Image path: ",image_path)
		print(self.item_name)
		url = f"{get_url()[0]}/admin/uploads"
		print("Upload URL",url)
		headers = get_headers(with_token=True)
		headers.pop('Content-Type', None)  # Remove the Content-Type header to let requests set it
		payload = {}
		print(1)
		# image_path = "/home/chethank1407/Pictures/Screenshots/Screenshot.png"
		with open(image_path, 'rb') as image_file:
			print(2)
			files = {'files': (image_path, image_file, 'image/jpeg')}
			print(3)
			response = requests.post(url, headers=headers, data=payload, files=files)
			print(4)
		
		print(response)
		print(response.text)
		
		if response.status_code == 200:
			image_url = response.json().get('uploads')[0].get('url')
			print(image_url)
			attach_image_to_product(image_url, self.medusa_id)
		else:
			frappe.throw("Failed to upload image to Medusa")

def attach_image_to_product(image_url, product_id):
	print(product_id)
	url = f"{get_url()[0]}/admin/products/{product_id}"
	print("Product URL",url)
	# url = "http://localhost:9000/admin/products/prod_01HYWJPAZ3539AEXZ29EPJ4CZ5/images"
	headers = get_headers(with_token=True)
	payload = json.dumps({"images": [image_url]})

	args = frappe._dict({
		"method": "POST",
		"url": url,
		"headers": headers,
		"payload": payload,
		"throw_message": "Failed to attach image to Medusa product"
	})
	send_request(args)

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
  
  return send_request(args).get("product").get("variants")[0].get("id")

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
		})
		args = frappe._dict({
		"method" : "POST",
		"url" : f"{get_url()[0]}/admin/collections",
		"headers": get_headers(with_token=True),
		"payload": payload,
		"throw_message": "We are unable to fetch access token please check your admin credentials"
		})

		self.db_set("medusa_id", send_request(args).get("collection").get("id"))
	
def create_medusa_price_list(self, method):
	doc = frappe.get_doc("Item", self.item_code)
	payload = json.dumps({
		"name": self.item_code,
		"description": self.item_description,
		"type": "override", # or "sale"
		"customer_groups": [],
		"status": "active",
		"starts_at": self.valid_from,
		"ends_at": self.valid_upto,
		"prices": [
			{
				"amount": self.price_list_rate * 100,
				"variant_id": doc.medusa_variant_id,
				"currency_code": "usd"
			}
		]
	})
	
	if get_url()[1] and not self.get_doc_before_save():
		args = frappe._dict({	
			"method" : "POST",
			"url" : f"{get_url()[0]}/admin/price-lists",
			"headers": get_headers(with_token=True),
			"payload": payload,
			"throw_message": "We are unable to fetch access token please check your admin credentials"
		})
		response = send_request(args).get("price_list")
		self.db_set("medusa_id", response.get("id"))

		prices = response.get("prices", [])
		self.db_set("medusa_price_id", prices[0].get("id"))

		# self.db_set("medusa_id", send_request(args).get("price_list").get("id"))
	
	if self.medusa_id and self.get_doc_before_save():
		payload = json.dumps({
			"prices": [
				{
					"id": self.medusa_price_id,
					"amount": self.price_list_rate * 100,
					"variant_id": doc.medusa_variant_id,
					"currency_code": "usd"
				}
			]
		})
		args = frappe._dict({	
			"method" : "POST",
			"url" : f"{get_url()[0]}/admin/price-lists/{self.medusa_id}",
			"headers": get_headers(with_token=True),
			"payload": payload,
			"throw_message": "We are unable to fetch access token please check your admin credentials"
		})
		send_request(args)

def create_medusa_customer(self, method):
	if get_url()[1] and not self.get_doc_before_save():
		def split_name(full_name):
			full_name = full_name.strip()
			if " " not in full_name:
				return full_name, "" 

			last_space_index = full_name.rfind(" ")
			first_name = full_name[:last_space_index]
			last_name = full_name[last_space_index + 1:]
			return first_name, last_name

		first_name, last_name = split_name(self.customer_name)
		payload = json.dumps({
			"first_name": first_name, # frappe.get_value("Contact", {"mobile_no": self.mobile_no}, "first_name"),
			"last_name": str(last_name),
			"email": self.email_id,
			"phone": self.mobile_no,
			"password": str(self.email_id) + str(self.mobile_no),
			})
		args = frappe._dict({
			"method" : "POST",
			"url" : f"{get_url()[0]}/admin/customers",
			"headers": get_headers(with_token=True),
			"payload": payload,
			"throw_message": "We are unable to fetch access token please check your admin credentials"
		})
		self.db_set("medusa_id", send_request(args).get("customer").get("id"))
