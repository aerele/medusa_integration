import requests
import frappe
import json
from frappe import _
from medusa_integration.constants import get_headers, get_url
from medusa_integration.utils import send_request
import datetime

# @frappe.whitelist()
# def greet(name=None):
#     return f"Hello, {name}"

# @frappe.whitelist(allow_guest=True)
# def create_customer():
#     data = json.loads(frappe.request.data)
#     customer = frappe.get_doc({
#         "doctype": "Customer",
#         "medusa_id": data.get("id"),
#         "customer_name": data.get("first_name") + " " + data.get("last_name"),
#         "customer_type": data.get("business_type"),
#         "email_id": data.get("email"),
#         "is_business": data.get("is_business"),
#         "t_c_acceptance": data.get("t_c_acceptance"),
#         "offers_agreement": data.get("offers_agreement"),
#     })
#     customer.insert(ignore_permissions=True)
#     return {"message": _("Customer created successfully"), "customer_id": customer.name}

def export_item(self):
	item_group = frappe.get_doc("Item Group", self.item_group)

	if not item_group.medusa_id:
		export_item_group(item_group)

	payload = {
					"title": self.item_name, #self.item_code,
					"discountable": False,
					"is_giftcard": False,
					"collection_id": item_group.medusa_id,
					"description": self.description,
					"status": "published",
					"brand_name": self.brand
	}

	if get_url()[1] and not self.medusa_id:
		args = frappe._dict({
						"method" : "POST",
						"url" : f"{get_url()[0]}/admin/products",
						"headers": get_headers(with_token=True),
						"payload": json.dumps(payload),
						"throw_message": f"Error while exporting Item {self.name} to Medusa"
		})

		self.db_set("medusa_id", send_request(args).get("product").get("id"))
		medusa_var_id = create_medusa_variant(self.medusa_id)
		self.db_set("medusa_variant_id", medusa_var_id)

	elif self.medusa_id and self.get_doc_before_save():
		payload.pop("is_giftcard")
		payload.pop("brand_name")
		args = frappe._dict({
						"method" : "POST",
						"url" : f"{get_url()[0]}/admin/products/{self.medusa_id}",
						"headers": get_headers(with_token=True),
						"payload": json.dumps(payload),
						"throw_message": f"Error while updating Item {self.name} in Medusa"
		})
		send_request(args)

def export_website_item(self):    
	item_group = frappe.get_doc("Item Group", self.item_group)

	if not item_group.medusa_id:
		export_item_group(item_group)

	origin_country = frappe.get_value("Item", {"item_code": self.item_code}, "country_of_origin")
	if origin_country:
		country_of_origin = frappe.get_value("Country", {"name": origin_country}, "code")
	country_code = country_of_origin.upper() if origin_country else None
	
	payload = {
		"title": self.web_item_name,
		"discountable": False,
		"is_giftcard": False,
		"collection_id": item_group.medusa_id,
		"description": self.web_long_description,
		"status": "published" if self.published else "draft",
		"brand_name": self.brand,
		"origin_country": country_code,
		"metadata": {"UOM": self.stock_uom} 
	}

	try:
		if get_url()[1] and not self.medusa_id:
			args = frappe._dict({
				"method": "POST",
				"url": f"{get_url()[0]}/admin/products",
				"headers": get_headers(with_token=True),
				"payload": json.dumps(payload),
				"throw_message": f"Error while exporting Website Item {self.name} to Medusa"
			})
			self.db_set("medusa_id", send_request(args).get("product").get("id"))
			medusa_var_id = create_medusa_variant(self.medusa_id, self.item_code, self.on_backorder, country_code)
			self.db_set("medusa_variant_id", medusa_var_id)
			print(self.name, " exported successfully")

		if self.medusa_id and self.get_doc_before_save():
			payload.pop("is_giftcard")
			payload.pop("brand_name")
			args = frappe._dict({
				"method": "POST",
				"url": f"{get_url()[0]}/admin/products/{self.medusa_id}",
				"headers": get_headers(with_token=True),
				"payload": json.dumps(payload),
				"throw_message": f"Error while updating Website Item {self.name} in Medusa"
			})
			send_request(args)
	
	except frappe.ValidationError as e:
		if "Product with handle" in str(e) and "already exists" in str(e):
			print(f"Duplicate error for {self.name}: {str(e)}")
		else:
			raise e
	except Exception as e:
		print(f"Unexpected error while exporting {self.name}: {str(e)}")
		raise e

def create_medusa_variant(product_id, item_code, backorder = False, country_code = None):	
	inventory_quantity = frappe.get_list('Bin', filters={'item_code': item_code}, fields='actual_qty', pluck='actual_qty')
	qty = int(sum(inventory_quantity))
	
	option_id = create_medusa_option(product_id)
	payload = json.dumps({
							"title": "Default",
							"material": None,
							"mid_code": None,
							"hs_code": None,
							"origin_country": country_code,
							"sku": None,
							"ean": None,
							"upc": None,
							"barcode": None,
							"inventory_quantity": qty, # Needs to be updated
							"manage_inventory": True,
							"allow_backorder": True if backorder else False,
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
							"throw_message": f"Error while creating Item Variant for {product_id} in Medusa"
	})
	
	return send_request(args).get("product").get("variants")[0].get("id")

# def update_medusa_variant(product_id, variant_id, option_id):
# 	payload = json.dumps({
# 							"title": "Default",
# 							"material": None,
# 							"mid_code": None,
# 							"hs_code": None,
# 							"origin_country": "IN", # item.country_of_origin
# 							"sku": None,
# 							"ean": None,
# 							"upc": None,
# 							"barcode": None,
# 							"inventory_quantity": 0,
# 							"manage_inventory": True,
# 							"allow_backorder": True,
# 							"weight": None,
# 							"width": None,
# 							"height": None,
# 							"length": None,
# 							"prices": [],
# 							"metadata": {},
# 							"options": [
# 								{
# 								"option_id": option_id,
# 								"value": "Default"
# 								}
# 							]
# 	})
# 	args = frappe._dict({
# 							"method" : "POST",
# 							"url" : f"{get_url()[0]}/admin/products/{product_id}/variants/{variant_id}",
# 							"headers": get_headers(with_token=True),
# 							"payload": payload,
# 							"throw_message": "Error while updating Item Variant in Medusa"
# 	})

def create_medusa_option(product_id):
	payload = json.dumps({
			"title": "Default",
		})
	args = frappe._dict({
					"method" : "POST",
					"url" : f"{get_url()[0]}/admin/products/{product_id}/options",
					"headers": get_headers(with_token=True),
					"payload": payload,
					"throw_message": f"Error while creating Item Option for {product_id} in Medusa"
	})
	
	return send_request(args).get("product").get("options")[0].get("id")

def export_item_group(self):
	if get_url()[1] and not self.medusa_id:
		payload = json.dumps({
					"title": self.name,
					"metadata": {"parent_item_group": self.parent_item_group, "is_group": self.is_group}
		})
		args = frappe._dict({
		"method" : "POST",
		"url" : f"{get_url()[0]}/admin/collections",
		"headers": get_headers(with_token=True),
		"payload": payload,
		"throw_message": f"Error while exporting Item Group {self.name} to Medusa"
		})

		self.db_set("medusa_id", send_request(args).get("collection").get("id"))
		print(self.name, " exported successfully")
	
def create_medusa_price_list(self, called_manually=False):	
	medusa_variant_id = frappe.db.get_value("Website Item", {"item_code": self.item_code}, "medusa_variant_id")

	if not medusa_variant_id:
		print("No Website Item found for item code: ", self.item_code)
		return
	
	item_price = 0
	
	if called_manually:
		recent_item_price = frappe.db.sql("""
			SELECT 
				name, price_list_rate
			FROM 
				`tabItem Price`
			WHERE 
				item_code = %s
			ORDER BY 
				valid_from DESC
			LIMIT 1
		""", (self.item_code,), as_dict=True)

		if recent_item_price[0]['name'] != self.name:
			print(f"Skipping {self.name} as it is not the most recent Item Price of {self.item_code}")
			return

		item_price = recent_item_price[0]['price_list_rate']

	else:
		item_price = self.price_list_rate

	item_price = int(item_price * 1000)
	print("Item Price: ", item_price)
	sendable_item_price = item_price/1000
	print ("Sendable Item Price: ", sendable_item_price)

	web_item_name = frappe.db.get_value("Website Item", {"item_code": self.item_code}, "web_item_name")

	if called_manually:
		starts_at = self.valid_from.isoformat() if self.valid_from else None
		ends_at = self.valid_upto.isoformat() if self.valid_upto else None
	else:
		starts_at = datetime.datetime.strptime(self.valid_from, "%Y-%m-%d").isoformat() if self.valid_from else None
		ends_at = datetime.datetime.strptime(self.valid_upto, "%Y-%m-%d").isoformat() if self.valid_upto else None

	
	payload = json.dumps({
		"name": web_item_name,
		"description": self.price_list,
		"type": "override",  # or "sale"
		"customer_groups": [],
		"status": "active",
		"starts_at": starts_at,
		"ends_at": ends_at,
		"prices": [
			{
				"amount": item_price,
				"variant_id": medusa_variant_id,
				"currency_code": self.currency.lower(),
			}
		]
	})
	
	if get_url()[1] and not self.medusa_id:
		args = frappe._dict({	
			"method" : "POST",
			"url" : f"{get_url()[0]}/admin/price-lists",
			"headers": get_headers(with_token=True),
			"payload": payload,
			"throw_message": f"Error while exporting Item Price {self.name} to Medusa"
		})
		response = send_request(args).get("price_list")
		self.db_set("medusa_id", response.get("id"))

		prices = response.get("prices", [])
		self.db_set("medusa_price_id", prices[0].get("id"))
		print(self.name, "exported successfully")
	
	if self.medusa_id and self.get_doc_before_save():
		payload = json.dumps({
			"prices": [
				{
					"id": self.medusa_price_id,
					"amount": item_price,
					"variant_id": medusa_variant_id,
					"currency_code": self.currency.lower(),
				}
			]
		})
		args = frappe._dict({	
			"method" : "POST",
			"url" : f"{get_url()[0]}/admin/price-lists/{self.medusa_id}",
			"headers": get_headers(with_token=True),
			"payload": payload,
			"throw_message": f"Error while updating Item Price {self.name} in Medusa"
		})
		send_request(args)

def export_brand(self):
	payload = {
		"brand_name": self.brand_name,
		"description": self.description,
		"image": self.image_url,
	}

	try:
		if not self.medusa_id:
			args = frappe._dict({
				"method": "POST",
				"url": f"{get_url()[0]}/store/brand-create",
				"headers": get_headers(with_token=True),
				"payload": json.dumps(payload),
				"throw_message": f"Error while exporting Brand {self.name} to Medusa"
			})
			self.db_set("medusa_id", send_request(args).get("brand").get("id"))
			print(self.name, " exported successfully")

		if self.medusa_id and self.get_doc_before_save():
			args = frappe._dict({
				"method": "POST",
				"url": f"{get_url()[0]}/store/brand-create/{self.medusa_id}",
				"headers": get_headers(with_token=True),
				"payload": json.dumps(payload),
				"throw_message": f"Error while updating Brand {self.name} in Medusa"
			})
			send_request(args)
			print(self.name, "updated successfully")

	except frappe.ValidationError as e:
		if "Brand with handle" in str(e) and "already exists" in str(e):
			print(f"Duplicate error for {self.name}: {str(e)}")
		else:
			raise e
	except Exception as e:
		print(f"Unexpected error while exporting {self.name}: {str(e)}")
		raise e


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
			"throw_message": f"Error while exporting Customer {self.name} to Medusa"
		})
		self.db_set("medusa_id", send_request(args).get("customer").get("id"))

def file_validation_wrapper(self):
	namecheck(self)
	print("Namecheck done")
	
	upload_image_to_medusa(self)
	print("Images uploaded")	

def upload_image_to_medusa(self):
	print("Entered Image upload")
	print("Name: ", self.attached_to_name)
	print("Doctype: ", self.attached_to_doctype) # Website item atteched to name check in FILE
	web_item = ""
	if self.attached_to_doctype == "Website Item":
		medusa_id = frappe.get_value("Website Item", {"name": self.attached_to_name}, "medusa_id")
		print("Website item Medusa ID: ", medusa_id)
		web_item = frappe.get_value("Website Item", {"name": self.attached_to_name}, "web_item_name")
		print("Web Item Name: ", web_item)
	elif self.attached_to_doctype == "Item":
		medusa_id = frappe.get_value("Item", {"item_name": self.attached_to_name}, "medusa_id")
		print("item Medusa ID: ", medusa_id)

	if medusa_id and self.attached_to_field not in ["image", "website_image"]:
		print("Web Item Name inside image getter: ", self.attached_to_doctype)
		images = frappe.get_all("File", filters={
						"attached_to_doctype": self.attached_to_doctype,
						"attached_to_name": self.attached_to_name,
						"attached_to_field": ["not in", ["image", "website_image"]]
				})
		print(images)
		image_urls = []

		for image in images:
			doc = frappe.get_doc("File", image)
			image_path = doc.get_full_path()
			print("Image path: ", image_path)
			url = f"{get_url()[0]}/admin/uploads"
			print("Upload URL: ", url)
			headers = get_headers(with_token=True)
			headers.pop('Content-Type', None)  # Remove the Content-Type header to let requests set it
			payload = {}
			print(1)
			with open(image_path, 'rb') as image_file:
				print(2)
				files = {'files': (image_path, image_file, 'image/jpeg')}
				print(3)
				response = requests.post(url, headers=headers, data=payload, files=files)
				print(4)
				print(response)
				print(response.text)
				if response.status_code == 200:
					uploaded_image_url = response.json().get('uploads')[0].get('url')
					print("Image uploaded")
					print("Image URL: ",uploaded_image_url)
					image_urls.append(uploaded_image_url)
				else:
					frappe.throw("Failed to upload image to Medusa")

		attach_image_to_product(image_urls, medusa_id)
				
	elif medusa_id and self.attached_to_field in ["image", "website_image"]:
		image_url = ""
		image_path = self.get_full_path()
		print("Image path: ", image_path)
		url = f"{get_url()[0]}/admin/uploads"
		print("Upload URL: ", url)
		headers = get_headers(with_token=True)
		headers.pop('Content-Type', None)  # Remove the Content-Type header to let requests set it
		payload = {}
		print(1)
		with open(image_path, 'rb') as image_file:
			print(2)
			files = {'files': (image_path, image_file, 'image/jpeg')}
			print(3)
			response = requests.post(url, headers=headers, data=payload, files=files)
			print(4)
			print(response)
			print(response.text)
			if response.status_code == 200:
				uploaded_image_url = response.json().get('uploads')[0].get('url')
				print("Image uploaded")
				print("Image URL: ",uploaded_image_url)
				image_url = uploaded_image_url
				print("2nd Image URL: ", image_url)
			else:
				frappe.throw("Failed to upload image to Medusa")

		attach_thumbnail_to_product(image_url, medusa_id)

def attach_thumbnail_to_product(image_url, product_id):
	print("Image URLs: ", image_url)
	print("Product ID: ", product_id)
	url = f"{get_url()[0]}/admin/products/{product_id}"
	print("Product URL: ",url)
	headers = get_headers(with_token=True)
	payload = json.dumps({"thumbnail": image_url})

	args = frappe._dict({
		"method": "POST",
		"url": url,
		"headers": headers,
		"payload": payload,
		"throw_message": f"Error while attaching thumbnail {image_url} to the Medusa product {product_id}"
	})
	send_request(args)

def attach_image_to_product(image_url, product_id):
	print ("Entered attach image")
	url = f"{get_url()[0]}/admin/products/{product_id}"
	headers = get_headers(with_token=True)
	payload = json.dumps({"images": image_url})

	args = frappe._dict({
		"method": "POST",
		"url": url,
		"headers": headers,
		"payload": payload,
		"throw_message": "Error while attaching image to the Medusa product"
	})
	send_request(args)
 
def export_image_to_medusa(self):
	medusa_id = frappe.get_value("Website Item", {"name": self.attached_to_name}, "medusa_id")

	if medusa_id:
		print("Entered IF Condition")
		image_path = self.get_full_path()
		print("Image path: ", image_path)
		url = f"{get_url()[0]}/admin/uploads"
		print("Upload URL: ", url)
		headers = get_headers(with_token=True)
		headers.pop('Content-Type', None)
		payload = {}
		image_url = []

		with open(image_path, 'rb') as image_file:
			files = {'files': (image_path, image_file, 'image/jpeg')}
			response = requests.post(url, headers=headers, data=payload, files=files)
			print(response)
			print(response.text)

			if response.status_code == 200:
				uploaded_image_url = response.json().get('uploads')[0].get('url')
				print("Image uploaded")
				print("uploaded_image_url: ", uploaded_image_url)
				image_url.append(uploaded_image_url)

			else:
				frappe.throw("Failed to upload image to Medusa")

		print("Uploaded image")
		attach_image_to_product(image_url, medusa_id)
		print("Completed image attach")
		self.db_set("medusa_id", medusa_id)

def get_medusa_products_by_brand(brand_name):
	# Query Medusa API to fetch all products by brand_name
	url = f"http://localhost:9000/store/product-listing-with-filters"
	params = {
		"parent" : "Products",	 
		"brand": brand_name
	}
 
#  Want to change here

	response = requests.get(url, params=params)
	if response.status_code == 200:
		data = response.json()
		product_ids = [product["id"] for product in data["products"]]
		
		if product_ids:
			print(f"Found {len(product_ids)} products for brand {brand_name}")
			return product_ids
		else:
			print(f"No products found for brand {brand_name}")
			return []
	else:
		print(f"Failed to fetch products from Medusa for brand {brand_name}. Status code: {response.status_code}")
		return []

def attach_image_to_products(image_url, product_ids):
	# Attach the uploaded image to all products of the brand
	for product_id in product_ids:
		print(f"Attaching image to product: {product_id}")
		url = f"http://localhost:9000/admin/products/{product_id}"
		headers = get_headers(with_token=True)
		payload = json.dumps({"images": image_url})

		args = frappe._dict({
			"method": "POST",
			"url": url,
			"headers": headers,
			"payload": payload,
			"throw_message": "Error while attaching image to Medusa product"
		})
		send_request(args)

def export_image_to_medusa_by_brand(doc):
	# Get the brand name from the file's attached_to_name
	brand_name = doc.attached_to_name
	
	# Fetch all products with the matching brand name from Medusa
	product_ids = get_medusa_products_by_brand(brand_name)
	
	if product_ids:
		# Proceed with image export
		image_path = doc.get_full_path()
		print(f"Exporting image: {doc.name}, Image path: {image_path}")
		url = f"http://localhost:9000/admin/uploads"
		headers = get_headers(with_token=True)
		headers.pop('Content-Type', None)
		payload = {}
		image_url = []
		
		with open(image_path, 'rb') as image_file:
			files = {'files': (image_path, image_file, 'image/jpeg')}
			response = requests.post(url, headers=headers, data=payload, files=files)
			print(response)
			print(response.text)

			if response.status_code == 200:
				uploaded_image_url = response.json().get('uploads')[0].get('url')
				print(f"Image uploaded, URL: {uploaded_image_url}")
				image_url.append(uploaded_image_url)
			else:
				frappe.throw("Failed to upload image to Medusa")

		# Attach the uploaded image to all matching products
		attach_image_to_products(image_url, product_ids)
		print(f"Completed attaching image to {len(product_ids)} products")

def export_all_brand_images():
	doctype = "File"
	images = frappe.get_all(doctype, filters={
						"attached_to_doctype": "Brand",
						"attached_to_field": "image"
				})
	for image in images:
		doc = frappe.get_doc(doctype, image)
		if not doc.medusa_id:
			try:
				print(f"Starting export for: {doc.name}")
				export_image_to_medusa_by_brand(doc)
			except frappe.ValidationError as e:
				print(f"Skipping {doc.name} due to error: {str(e)}")
			except Exception as e:
				print(f"Unexpected error while exporting {doc.name}: {str(e)}")
				raise e


def namecheck(self):
	if ' ' in self.file_name:
		frappe.throw("Invalid name format!<br>File name cannot contain spaces")

def export_all_website_item():
	print("Exporting all website items to Medusa...")
	doctype = "Website Item"
	record = frappe.get_all(doctype)  # frappe.get_all(doctype, limit = 5)
	for r in record:
		doc = frappe.get_doc(doctype, r)
		if doc.published and not doc.medusa_id:
			try:
				print("Beginning to export: ", doc.name)
				export_website_item(doc)
			except frappe.ValidationError as e:
				print(f"Skipping {doc.name} due to error: {str(e)}")
			except Exception as e:
				print(f"Unexpected error while exporting {doc.name}: {str(e)}")
				raise e

def export_all_item_groups():
	print("Exporting all item groups to Medusa...")
	doctype = "Item Group"
	groups = frappe.get_all(doctype)  # frappe.get_all(doctype, limit = 5)
	for group in groups:
		doc = frappe.get_doc(doctype, group)
		if not doc.medusa_id:
			try:
				print("Beginning to export: ", doc.name)
				export_item_group(doc)
			except frappe.ValidationError as e:
				print(f"Skipping {doc.name} due to error: {str(e)}")
			except Exception as e:
				print(f"Unexpected error while exporting {doc.name}: {str(e)}")
				raise e

def export_all_website_images():
	doctype = "File"
	images = frappe.get_all(doctype, filters={
						"attached_to_doctype": "Website Item",
						"attached_to_field": ["in", ["image", "website_image"]]
				})
	for image in images:
		doc = frappe.get_doc(doctype, image)
		if not doc.medusa_id:
			try:
				print("Beginning to export: ", doc.name)
				export_image_to_medusa(doc)
			except frappe.ValidationError as e:
				print(f"Skipping {doc.name} due to error: {str(e)}")
			except Exception as e:
				print(f"Unexpected error while exporting {doc.name}: {str(e)}")
				raise e

def export_all_medusa_price_list():
	doctype = "Item Price"
	record = frappe.get_all(doctype)
	for r in record:
		doc = frappe.get_doc(doctype, r)
		is_diabled = frappe.get_value("Item", {"item_code": doc.item_code}, "disabled")
		if is_diabled:
			print(f"skipping {doc.name} due to disabled item {doc.item_code}")
			continue
		if not doc.medusa_id:
			try:
				print("Beginning to export: ", doc.name)
				create_medusa_price_list(doc, called_manually=True)
			except frappe.ValidationError as e:
				print(f"Skipping {doc.name} due to error: {str(e)}")
			except Exception as e:
				print(f"Unexpected error while exporting {doc.name}: {str(e)}")
				raise e

def clear_all_item_group_id(): #For Item Group
	# Get all documents in the "Item Group" doctype
	item_groups = frappe.get_all("Item Group", filters={"medusa_id": ["!=", ""]}, fields=["name"])
	print(item_groups)
	
	# Iterate through each document and set the medusa_id to an empty string
	for item_group in item_groups:
		frappe.db.set_value("Item Group", item_group.name, "medusa_id", "")

	# Commit the changes to the database
	frappe.db.commit()

def clear_all_website_item_id(): #For website items
	# Get all documents in the "Website Item" doctype
	items = frappe.get_all("Website Item", filters={"medusa_id": ["!=", ""]}, fields=["name"])
	print(items)

	# Iterate through each document and set the medusa_id and medusa_variant_id to an empty string
	for item in items:
		frappe.db.set_value("Website Item", item.name, {"medusa_id": "", "medusa_variant_id": ""})

	# Commit the changes to the database
	frappe.db.commit()

def clear_all_website_image_id(): #For website images
	# Get all documents in the "File" doctype
	images = frappe.get_all("File", filters={"medusa_id": ["!=", ""]}, fields=["name"])
	print(images)

	# Iterate through each document and set the medusa_id to an empty string
	for image in images:
		frappe.db.set_value("File", image.name, {"medusa_id": ""})

	# Commit the changes to the database
	frappe.db.commit()
 
def clear_all_item_price_id(): #For item price
	# Get all documents in the "Item Price" doctype
	item_prices = frappe.get_all("Item Price", filters={"medusa_id": ["!=", ""]}, fields=["name"])
	print(item_prices)

	# Iterate through each document and set the medusa_id and medusa_price_id to an empty string
	for item_price in item_prices:
		frappe.db.set_value("Item Price", item_price.name, {"medusa_id": "", "medusa_price_id": ""})

	# Commit the changes to the database
	frappe.db.commit()
