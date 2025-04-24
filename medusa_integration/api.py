import requests
import frappe
import json
from frappe import _
from medusa_integration.constants import get_headers, get_url
from medusa_integration.utils import send_request
from datetime import datetime, timedelta
from alfarsi_erpnext.alfarsi_erpnext.customer import fetch_standard_price
from frappe.utils import now_datetime, add_to_date
import random

medusa_base_url = "https://medusa-be.aerele.in"


@frappe.whitelist(allow_guest=True)
def create_lead():
	data = json.loads(frappe.request.data)
	lead = frappe.get_doc(
		{
			"doctype": "Lead",
			"medusa_id": data.get("id"),
			"first_name": data.get("first_name"),
			"last_name": data.get("last_name"),
			"email_id": data.get("email"),
			"mobile_no": data.get("mobile"),
			"source": "Alfarsi Website",
			"status": "Lead",
			"company_name": data.get("organization_name"),
			"t_c_acceptance": data.get("t_c_acceptance"),
		}
	)
	lead.insert(ignore_permissions=True, ignore_mandatory=True)
	return {"message": ("Lead created successfully"), "Lead ID": lead.name}


@frappe.whitelist(allow_guest=True)
def update_existing_customer():
	try:
		data = json.loads(frappe.request.data)
		customer_id = data.get("erp_customer_id")

		customer = frappe.get_doc("Customer", customer_id)

		customer.medusa_id = data.get("id")
		customer.email_id = data.get("email_id")
		customer.mobile_no = data.get("mobile_no")
		customer.t_c_acceptance = data.get("t_c_acceptance")
		customer.offers_agreement = data.get("offers_agreement")

		customer.save(ignore_permissions=True)
		return "Customer updated successfully"
	except frappe.DoesNotExistError:
		return {"error": f"Customer with ID '{customer_id}' does not exist."}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Update Existing Customer Error")
		return {"error": str(e)}


@frappe.whitelist(allow_guest=True)
def banner_form():
	data = json.loads(frappe.request.data)
	medusa_id = data.get("customer_id")
	form = data.get("form")

	customer = frappe.db.get_value("Customer", {"medusa_id": medusa_id}, "name")

	if customer:
		opportunity_from = "Customer"
		party_name = customer
		print(party_name)
	else:
		lead = frappe.db.get_value("Lead", {"medusa_id": medusa_id}, "name")
		if lead:
			opportunity_from = "Lead"
			party_name = lead
		else:
			return {
				"status": "error",
				"message": "Customer ID not found in Customer or Lead",
			}

	opportunity_type = "Sales" if form == "Setup Clinic" else "Support"
	sales_stage = "Prospecting" if form == "Setup Clinic" else "Needs Analysis"
	expected_closing = datetime.today() + timedelta(days=30)

	opportunity = frappe.get_doc(
		{
			"doctype": "Opportunity",
			"opportunity_type": opportunity_type,
			"sales_stage": sales_stage,
			"opportunity_from": opportunity_from,
			"source": "Alfarsi Website",
			"expected_closing": expected_closing.date(),
			"party_name": party_name,
			"status": "Open",
		}
	)

	opportunity.insert(ignore_permissions=True)
	frappe.db.commit()

	return "Opportunity created successfully"


@frappe.whitelist(allow_guest=True)
def create_quotation():
	data = json.loads(frappe.request.data)
	medusa_id = data.get("customer_id")
	items = data.get("items", [])
	valid_till = datetime.today() + timedelta(days=30)

	customer_details = frappe.get_value(
		"Customer", {"medusa_id": medusa_id}, ["name", "customer_name"], as_dict=True
	)
	if customer_details:
		party_name = customer_details.name
		quotation_to = "Customer"
		title = customer_details.customer_name
	else:
		lead = frappe.get_value("Lead", {"medusa_id": medusa_id}, "name")
		if not lead:
			frappe.throw(f"Lead or Customer with medusa_id {medusa_id} not found.")
		party_name = lead
		quotation_to = "Lead"
		title = "Unapproved Lead"

	quote = frappe.get_doc(
		{
			"doctype": "Quotation",
			"title": title,
			"order_type": "Sales",
			"quotation_to": quotation_to,
			"party_name": party_name,
			"medusa_draft_order_id": data.get("draft_order_id"),
			"medusa_quotation_id": data.get("quotation_id"),
			"valid_till": valid_till.date(),
			"from_ecommerce": 1,
			"items": [],
			"taxes": [],
		}
	)

	tax_summary = set()

	for item in items:
		variant_id = item.get("variant_id")
		quantity = item.get("quantity", 1)

		item_code = frappe.get_value(
			"Website Item", {"medusa_variant_id": variant_id}, "item_code"
		)
		if not item_code:
			return {"error": "Item not found for variant ID: {}".format(variant_id)}

		quote.append(
			"items",
			{
				"item_code": item_code,
				"qty": quantity,
			},
		)

		item_doc = frappe.get_doc("Item", item_code)
		item_taxes = item_doc.taxes or []

		for tax in item_taxes:
			tax_template = tax.item_tax_template
			if tax_template:
				tax_template_doc = frappe.get_doc("Item Tax Template", tax_template)
				for template_tax in tax_template_doc.taxes:
					account_head = template_tax.tax_type
					if account_head not in tax_summary:
						tax_summary.add(account_head)
						quote.append(
							"taxes",
							{
								"charge_type": "On Net Total",
								"account_head": account_head,
								"description": account_head,
							},
						)

	quote.insert(ignore_permissions=True)

	serialized_items = json.dumps(
		[
			{
				k: (v.isoformat() if isinstance(v, datetime) else v)
				for k, v in item.as_dict().items()
			}
			for item in quote.items
		]
	)

	try:
		prices = fetch_standard_price(
			items=serialized_items,
			price_list=quote.selling_price_list,
			party=quote.party_name,
			quotation_to=quote.quotation_to,
		)

		for item in quote.items:
			item_code = item.item_code
			item.standard_price = prices.get(item_code, 0)
			item.rate = prices.get(f"{item_code}-negotiated", 0)

		quote.save(ignore_permissions=True)
	except Exception as e:
		return {"error": f"Failed to fetch and update standard prices: {str(e)}"}

	return {"message": "Quotation created successfully", "quotationId": quote.name}


@frappe.whitelist(allow_guest=True)
def create_sales_order():
	try:
		data = json.loads(frappe.request.data)
		items = data.get("items", [])
		delivery_date = datetime.today() + timedelta(days=1)

		customer = data.get("customer")

		company = data.get("company")

		sales_order = frappe.new_doc("Sales Order")
		sales_order.update(
			{
				"customer": customer,
				"delivery_date": delivery_date,
				"order_type": "Sales",
				"company": company,
				"workflow_state": "Draft",
				"from_ecommerce": 1,
				"items": [],
				"conversion_rate": 1.0,
			}
		)

		for item in items:
			item_code = item.get("item_code")
			qty = item.get("qty")
			rate = item.get("rate")
			amount = rate * qty

			sales_order.append(
				"items",
				{
					"item_code": item_code,
					"qty": qty,
					"rate": rate,
					"base_net_rate": rate,
					"amount": amount,
					"conversion_factor": 1.0,
				},
			)

		sales_order.insert(ignore_permissions=True)

		return {
			"message": "Sales Order created successfully",
			"Sales Order ID": sales_order.name,
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Sales Order Creation Error")
		return {"error": str(e)}

@frappe.whitelist(allow_guest=True)
def update_quotation():
	data = json.loads(frappe.request.data)
	medusa_quotation_id = data.get("quotation_id")
	quotation_id = frappe.get_value(
		"Quotation", {"medusa_quotation_id": medusa_quotation_id}, "name"
	)
	approval = data.get("approval")
	custom_is_courier_required = data.get("is_courier_required")
	custom_location_and_contact_no = data.get("location_and_contact_no")
	# items = data.get("items", [])
	# unapproved_items = data.get("unapproved_items", [])
	medusa_order_id = data.get("order_id")
	# custom_increased_items = data.get("increased_items", [])

	try:
		quote = frappe.get_doc("Quotation", quotation_id)
	except frappe.DoesNotExistError:
		return {"error": "Quotation not found for ID: {}".format(quotation_id)}

	# if (
	# 	approval == "Partially Approved"
	# 	or approval == "Partially Approved with Increased Deal"
	# ):
	# 	quote.status = "Open"
	# 	quote.workflow_state = approval
	# 	quote.order_type = "Sales"

	# 	tax_summary = set()

	# 	quote.items = []
	# 	quote.taxes = []
	# 	for item in items:
	# 		variant_id = item.get("variant_id")
	# 		item_code = frappe.get_value(
	# 			"Website Item", {"medusa_variant_id": variant_id}, "item_code"
	# 		)
	# 		if not item_code:
	# 			return {"error": "Item not found for variant ID: {}".format(variant_id)}

	# 		quote.append(
	# 			"items",
	# 			{
	# 				"item_code": item_code,
	# 				"qty": item.get("quantity"),
	# 				"rate": item.get("rate"),
	# 				"amount": item.get("amount"),
	# 			},
	# 		)

	# 		item_doc = frappe.get_doc("Item", item_code)
	# 		item_taxes = item_doc.taxes or []
	# 		for tax in item_taxes:
	# 			tax_template = tax.item_tax_template
	# 			if tax_template:
	# 				tax_template_doc = frappe.get_doc("Item Tax Template", tax_template)
	# 				for template_tax in tax_template_doc.taxes:
	# 					account_head = template_tax.tax_type
	# 					if account_head not in tax_summary:
	# 						tax_summary.add(account_head)
	# 						quote.append(
	# 							"taxes",
	# 							{
	# 								"charge_type": "On Net Total",
	# 								"account_head": account_head,
	# 								"description": account_head,
	# 							},
	# 						)

	# 	quote.unapproved_items = []
	# 	for item in unapproved_items:
	# 		variant_id = item.get("variant_id")
	# 		item_details = frappe.get_value(
	# 			"Website Item",
	# 			{"medusa_variant_id": variant_id},
	# 			["item_code", "stock_uom"],
	# 			as_dict=True,
	# 		)
	# 		quote.append(
	# 			"unapproved_items",
	# 			{
	# 				"item_code": item_details["item_code"],
	# 				"qty": item.get("quantity"),
	# 				"uom": item_details["stock_uom"],
	# 				"rate": item.get("rate"),
	# 				"amount": item.get("amount"),
	# 			},
	# 		)

	# 	quote.custom_increased_items = []
	# 	for item in custom_increased_items:
	# 		variant_id = item.get("variant_id")
	# 		item_details = frappe.get_value(
	# 			"Website Item",
	# 			{"medusa_variant_id": variant_id},
	# 			["item_code", "stock_uom"],
	# 			as_dict=True,
	# 		)
	# 		quote.append(
	# 			"custom_increased_items",
	# 			{
	# 				"item_code": item_details["item_code"],
	# 				"old_quantity": item.get("old_quantity"),
	# 				"new_quantity": item.get("new_quantity"),
	# 			},
	# 		)

	if approval == "Approved":
		quote.status = "Open"
		quote.workflow_state = "Approved"
		quote.order_type = "Sales"
		quote.medusa_order_id = medusa_order_id

		# tax_summary = set()

		# quote.items = []
		# quote.taxes = []
		# for item in items:
		# 	variant_id = item.get("variant_id")
		# 	item_code = frappe.get_value("Website Item", {"medusa_variant_id": variant_id}, "item_code")
		# 	if not item_code:
		# 		return {"error": "Item not found for variant ID: {}".format(variant_id)}

		# 	quote.append("items", {
		# 		"item_code": item_code,
		# 		"qty": item.get("quantity"),
		# 		"rate": item.get("rate"),
		# 		"amount": item.get("amount")
		# 	})

		# 	item_doc = frappe.get_doc("Item", item_code)
		# 	item_taxes = item_doc.taxes or []
		# 	for tax in item_taxes:
		# 		tax_template = tax.item_tax_template
		# 		if tax_template:
		# 			tax_template_doc = frappe.get_doc("Item Tax Template", tax_template)
		# 			for template_tax in tax_template_doc.taxes:
		# 				account_head = template_tax.tax_type
		# 				if account_head not in tax_summary:
		# 					tax_summary.add(account_head)
		# 					quote.append("taxes", {
		# 						"charge_type": "On Net Total",
		# 						"account_head": account_head,
		# 						"description": account_head
		# 					})

		# quote.unapproved_items = []
		# for item in unapproved_items:
		# 	variant_id = item.get("variant_id")
		# 	item_details = frappe.get_value("Website Item", {"medusa_variant_id": variant_id}, ["item_code", "stock_uom"], as_dict=True)
		# 	quote.append("unapproved_items", {
		# 		"item_code": item_details["item_code"],
		# 		"qty": item.get("quantity"),
		# 		"uom": item_details["stock_uom"],
		# 		"rate": item.get("rate"),
		# 		"amount": item.get("amount")
		# 	})
		
		# quote.custom_increased_items = []
		# for item in custom_increased_items:
		# 	variant_id = item.get("variant_id")
		# 	item_details = frappe.get_value("Website Item", {"medusa_variant_id": variant_id}, ["item_code", "stock_uom"], as_dict=True)
		# 	quote.append("custom_increased_items", {
		# 		"item_code": item_details["item_code"],
		# 		"old_quantity": item.get("old_quantity"),
		# 		"new_quantity": item.get("new_quantity")
		# 	})
		
		quote.submit()
		
		if quote.quotation_to == "Customer":
			try:
				sales_order = frappe.call(
					"erpnext.selling.doctype.quotation.quotation.make_sales_order",
					source_name=quotation_id,
				)

				sales_order.delivery_date = frappe.utils.add_days(
					frappe.utils.nowdate(), 1
				)
				if custom_is_courier_required:
					sales_order.custom_is_courier_required = custom_is_courier_required
					sales_order.custom_location_and_contact_no = (
						custom_location_and_contact_no
					)

				sales_order.flags.ignore_permissions = True
				sales_order.insert()
				sales_order.submit()
			except Exception as e:
				return {"error": "Failed to create Sales Order: {}".format(str(e))}
		quote.reload()

	if approval != "Rejected":
		quote.save(ignore_permissions=True)

	if approval == "Rejected":
		quote.status = "Open"
		quote.workflow_state = "Rejected"
		quote.submit()

	return {"message": "Quotation updated successfully", "Quotation ID": quote.name}

@frappe.whitelist(allow_guest=True)
def update_quotation_new():
	data = json.loads(frappe.request.data)

	medusa_quotation_id = data.get("quotation_id")
	quotation_id = frappe.get_value("Quotation", {"medusa_quotation_id": medusa_quotation_id}, "name")

	items = data.get("items", [])
	unapproved_items = data.get("unapproved_items", [])
	custom_increased_items = data.get("increased_items", [])

	try:
		quote = frappe.get_doc("Quotation", quotation_id)
	except frappe.DoesNotExistError:
		return {"error": "Quotation not found for ID: {}".format(quotation_id)}

	quote.status = "Open"
	quote.workflow_state = "Approved"
	quote.order_type = "Sales"

	tax_summary = set()

	quote.items = []
	quote.taxes = []
	for item in items:
		variant_id = item.get("variant_id")
		item_details = frappe.get_value("Website Item", {"medusa_variant_id": variant_id}, ["item_code", "item_name", "description", "stock_uom"], as_dict=True)
		
		item_code = item_details["item_code"]
		if not item_code:
			return {"error": "Item not found for variant ID: {}".format(variant_id)}

		quote.append("items", {
			"item_code": item_code,
			"item_name": item_details["item_name"],
			"qty": item.get("quantity"),
			"rate": item.get("rate"),
			"amount": item.get("amount"),
			"description": item_details["description"],
			"uom": item_details["stock_uom"],
			"conversion_factor": 1.0
		})

		item_doc = frappe.get_doc("Item", item_code)
		item_taxes = item_doc.taxes or []
		for tax in item_taxes:
			tax_template = tax.item_tax_template
			if tax_template:
				tax_template_doc = frappe.get_doc("Item Tax Template", tax_template)
				for template_tax in tax_template_doc.taxes:
					account_head = template_tax.tax_type
					if account_head not in tax_summary:
						tax_summary.add(account_head)
						quote.append("taxes", {
							"charge_type": "On Net Total",
							"account_head": account_head,
							"description": account_head
						})

	quote.unapproved_items = []
	for item in unapproved_items:
		variant_id = item.get("variant_id")
		item_details = frappe.get_value("Website Item", {"medusa_variant_id": variant_id}, ["item_code", "stock_uom"], as_dict=True)
		quote.append("unapproved_items", {
			"item_code": item_details["item_code"],
			"qty": item.get("quantity"),
			"uom": item_details["stock_uom"],
			"rate": item.get("rate"),
			"amount": item.get("amount")
		})
	
	quote.custom_increased_items = []
	for item in custom_increased_items:
		variant_id = item.get("variant_id")
		item_details = frappe.get_value("Website Item", {"medusa_variant_id": variant_id}, ["item_code", "stock_uom"], as_dict=True)
		quote.append("custom_increased_items", {
			"item_code": item_details["item_code"],
			"old_quantity": item.get("old_quantity"),
			"new_quantity": item.get("new_quantity")
		})
	
	quote.save()
	quote.reload()

	export_quotation(self=quote, method='')

	return {"message": "Quotation updated successfully", "Quotation ID": quote.name}

@frappe.whitelist(allow_guest=True)
def update_address():
	try:
		data = frappe._dict(json.loads(frappe.request.data))
		customer_id = data.get("customer_id")

		if not customer_id:
			return {"error": "Customer ID is required."}

		address_id = frappe.db.get_value(
			"Dynamic Link",
			{
				"link_name": customer_id,
				"link_doctype": "Customer",
				"parenttype": "Address",
			},
			"parent",
		)

		if not address_id:
			return {"error": f"No address found for customer ID '{customer_id}'"}

		address_doc = frappe.get_doc("Address", address_id)

		fields_to_update = [
			"address_line1",
			"address_line2",
			"city",
			"state",
			"country",
			"pincode",
		]
		for field in fields_to_update:
			if data.get(field) is not None:
				setattr(address_doc, field, data.get(field))

		address_doc.save(ignore_permissions=True)

		return "Address updated successfully"

	except frappe.DoesNotExistError:
		return {
			"error": f"Customer with ID '{customer_id}' or their address does not exist."
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Update Address Error")
		return {"error": str(e)}


def export_website_item(self, method):
	import html
	from frappe.utils import strip_html

	item_group = frappe.get_doc("Item Group", self.item_group)

	if not item_group.medusa_id:
		export_item_group(item_group)

	origin_country = frappe.get_value(
		"Item", {"item_code": self.item_code}, "country_of_origin"
	)
	if origin_country:
		country_of_origin = frappe.get_value(
			"Country", {"name": origin_country}, "code"
		)
	country_code = country_of_origin.upper() if origin_country else None
	web_long_description = self.web_long_description
	clean_description = ""
	final_description = ""
	if web_long_description:
		clean_description = strip_html(web_long_description)
		final_description = html.unescape(clean_description)

	specifications = []
	if self.website_specifications:
		for spec in self.website_specifications:
			specifications.append(
				{"label": spec.label, "description": spec.description}
			)

	payload = {
		"title": self.web_item_name,
		"item_code": self.item_code,
		"discountable": False,
		"is_giftcard": False,
		"collection_id": item_group.medusa_id,
		"short_description": self.short_description,
		"description": final_description,
		"ranking": self.ranking,
		"status": "published" if self.published else "draft",
		"brand_name": self.brand,
		"origin_country": country_code,
		"metadata": {"UOM": self.stock_uom},
		"specifications": specifications,
	}

	try:
		if get_url()[1] and not self.medusa_id:
			args = frappe._dict(
				{
					"method": "POST",
					"url": f"{get_url()[0]}/admin/products",
					"headers": get_headers(with_token=True),
					"payload": json.dumps(payload),
					"throw_message": f"Error while exporting Website Item {self.name} to Medusa",
				}
			)
			self.db_set("medusa_id", send_request(args).get("product").get("id"))
			medusa_var_id = create_medusa_variant(
				self.medusa_id, self.item_code, self.on_backorder, country_code
			)
			self.db_set("medusa_variant_id", medusa_var_id)
			print(self.name, " exported successfully")

	except frappe.ValidationError as e:
		if "Product with handle" in str(e) and "already exists" in str(e):
			print(f"Duplicate error for {self.name}: {str(e)}")
		else:
			raise e
	except Exception as e:
		print(f"Unexpected error while exporting {self.name}: {str(e)}")
		raise e


def update_website_item(self, method):
	def send_update_request(payload, throw_message):
		try:
			args = frappe._dict(
				{
					"method": "POST",
					"url": f"{get_url()[0]}/admin/products/{self.medusa_id}",
					"headers": get_headers(with_token=True),
					"payload": json.dumps(payload),
					"throw_message": throw_message,
				}
			)
			send_request(args)
			print(self.medusa_id, " updated successfully")
		except Exception as e:
			print(f"Unexpected error while updating {self.name}: {str(e)}")
			raise e

	if self.custom_skip_update_hook:
		frappe.db.set_value("Website Item", self.name, "custom_skip_update_hook", 0)
		return

	item_group = frappe.get_doc("Item Group", self.item_group)
	if not item_group.medusa_id:
		export_item_group(item_group)

	origin_country = frappe.get_value(
		"Item", {"item_code": self.item_code}, "country_of_origin"
	)
	if origin_country:
		country_of_origin = frappe.get_value(
			"Country", {"name": origin_country}, "code"
		)
	country_code = country_of_origin.upper() if origin_country else None

	specifications = []
	if self.website_specifications:
		for spec in self.website_specifications:
			if spec.label and spec.description:
				specifications.append(
					{"label": spec.label, "description": spec.description}
				)

	payload = {
		"title": self.web_item_name,
		"item_code": self.item_code,
		"discountable": False,
		"collection_id": item_group.medusa_id,
		"short_description": self.short_description,
		"description": self.web_long_description,
		"ranking": self.ranking,
		"status": "published" if self.published else "draft",
		"brand_name": self.brand,
		"origin_country": country_code,
		"metadata": {"UOM": self.stock_uom},
		"specifications": specifications,
	}
	send_update_request(
		payload, f"Error while updating Website Item {self.name} in Medusa"
	)


def website_item_validate(self, method):
	if not self.medusa_id:
		export_website_item(self, method)
	else:
		update_website_item(self, method)


def create_medusa_variant(product_id, item_code, backorder=False, country_code=None):
	inventory_quantity = frappe.get_list(
		"Bin", filters={"item_code": item_code}, fields="actual_qty", pluck="actual_qty"
	)
	qty = int(sum(inventory_quantity))

	option_id = create_medusa_option(product_id)
	payload = json.dumps(
		{
			"title": "Default",
			"material": None,
			"mid_code": None,
			"hs_code": None,
			"origin_country": country_code,
			"sku": None,
			"ean": None,
			"upc": None,
			"barcode": None,
			"inventory_quantity": qty,  # Needs to be updated
			"manage_inventory": True,
			"allow_backorder": True if backorder else False,
			"weight": None,
			"width": None,
			"height": None,
			"length": None,
			"prices": [],
			"metadata": {},
			"options": [{"option_id": option_id, "value": "Default"}],
		}
	)
	args = frappe._dict(
		{
			"method": "POST",
			"url": f"{get_url()[0]}/admin/products/{product_id}/variants",
			"headers": get_headers(with_token=True),
			"payload": payload,
			"throw_message": f"Error while creating Item Variant for {product_id} in Medusa",
		}
	)

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
	payload = json.dumps(
		{
			"title": "Default",
		}
	)
	args = frappe._dict(
		{
			"method": "POST",
			"url": f"{get_url()[0]}/admin/products/{product_id}/options",
			"headers": get_headers(with_token=True),
			"payload": payload,
			"throw_message": f"Error while creating Item Option for {product_id} in Medusa",
		}
	)

	return send_request(args).get("product").get("options")[0].get("id")


def export_item_group(self):
	if get_url()[1] and not self.medusa_id:
		payload = json.dumps(
			{
				"title": self.name,
				"metadata": {
					"parent_item_group": self.parent_item_group,
					"is_group": self.is_group,
				},
			}
		)
		args = frappe._dict(
			{
				"method": "POST",
				"url": f"{get_url()[0]}/admin/collections",
				"headers": get_headers(with_token=True),
				"payload": payload,
				"throw_message": f"Error while exporting Item Group {self.name} to Medusa",
			}
		)

		self.db_set("medusa_id", send_request(args).get("collection").get("id"))
		print(self.name, " exported successfully")


def create_medusa_price_list(self, called_manually=False):
	medusa_variant_id = frappe.db.get_value(
		"Website Item", {"item_code": self.item_code}, "medusa_variant_id"
	)

	if not medusa_variant_id:
		print("No Website Item found for item code: ", self.item_code)
		return

	item_price = 0

	if called_manually:
		recent_item_price = frappe.db.sql(
			"""
			SELECT 
				name, price_list_rate
			FROM 
				`tabItem Price`
			WHERE 
				item_code = %s 
				AND price_list = 'Standard Selling'
				AND (customer IS NULL OR customer = '')
			ORDER BY 
				valid_from DESC
			LIMIT 1
		""",
			(self.item_code,),
			as_dict=True,
		)

		if not recent_item_price:
			print(f"No Standard Selling price found for {self.item_code}")
			return

		if recent_item_price[0]["name"] != self.name:
			print(
				f"Skipping {self.name} as it is not the most recent Item Price of {self.item_code}"
			)
			return

		item_price = recent_item_price[0]["price_list_rate"]

	else:
		if self.price_list != "Standard Selling" or self.customer:
			print(
				f"Skipping {self.name} as it does not belong to common Standard Selling price list"
			)
			return
		item_price = self.price_list_rate

	item_price = int(item_price * 1000)

	web_item_name = frappe.db.get_value(
		"Website Item", {"item_code": self.item_code}, "web_item_name"
	)

	if called_manually:
		starts_at = self.valid_from.isoformat() if self.valid_from else None
		ends_at = self.valid_upto.isoformat() if self.valid_upto else None
	else:
		starts_at = (
			datetime.datetime.strptime(self.valid_from, "%Y-%m-%d").isoformat()
			if self.valid_from
			else None
		)
		ends_at = (
			datetime.datetime.strptime(self.valid_upto, "%Y-%m-%d").isoformat()
			if self.valid_upto
			else None
		)

	payload = json.dumps(
		{
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
			],
		}
	)

	if get_url()[1] and not self.medusa_id:
		args = frappe._dict(
			{
				"method": "POST",
				"url": f"{get_url()[0]}/admin/price-lists",
				"headers": get_headers(with_token=True),
				"payload": payload,
				"throw_message": f"Error while exporting Item Price {self.name} to Medusa",
			}
		)
		response = send_request(args).get("price_list")
		self.db_set("medusa_id", response.get("id"))

		prices = response.get("prices", [])
		self.db_set("medusa_price_id", prices[0].get("id"))
		print(self.name, "exported successfully")

	if self.medusa_id and self.get_doc_before_save():
		payload = json.dumps(
			{
				"prices": [
					{
						"id": self.medusa_price_id,
						"amount": item_price,
						"variant_id": medusa_variant_id,
						"currency_code": self.currency.lower(),
					}
				]
			}
		)
		args = frappe._dict(
			{
				"method": "POST",
				"url": f"{get_url()[0]}/admin/price-lists/{self.medusa_id}",
				"headers": get_headers(with_token=True),
				"payload": payload,
				"throw_message": f"Error while updating Item Price {self.name} in Medusa",
			}
		)
		send_request(args)


def create_medusa_customer(self, method):
	if get_url()[1] and not self.get_doc_before_save():

		def split_name(full_name):
			full_name = full_name.strip()
			if " " not in full_name:
				return full_name, ""

			last_space_index = full_name.rfind(" ")
			first_name = full_name[:last_space_index]
			last_name = full_name[last_space_index + 1 :]
			return first_name, last_name

		first_name, last_name = split_name(self.customer_name)
		payload = json.dumps(
			{
				"first_name": first_name,  # frappe.get_value("Contact", {"mobile_no": self.mobile_no}, "first_name"),
				"last_name": str(last_name),
				"email": self.email_id,
				"phone": self.mobile_no,
				"password": str(self.email_id) + str(self.mobile_no),
			}
		)
		args = frappe._dict(
			{
				"method": "POST",
				"url": f"{get_url()[0]}/admin/customers",
				"headers": get_headers(with_token=True),
				"payload": payload,
				"throw_message": f"Error while exporting Customer {self.name} to Medusa",
			}
		)
		self.db_set("medusa_id", send_request(args).get("customer").get("id"))


@frappe.whitelist(allow_guest=True)
def fetch_all_customers(name=None):
	base_query = """
		SELECT 
			name, customer_name, email_id, mobile_no
		FROM 
			`tabCustomer`
		WHERE 
			medusa_id IS NULL
	"""

	if name:
		name_parts = name.split()
		conditions = " AND ".join(
			[f"customer_name LIKE '%{part}%'" for part in name_parts]
		)
		base_query += f" AND ({conditions})"

	customers = frappe.db.sql(base_query, as_dict=True)

	if not customers:
		return "No relevant customers found"

	return customers


def file_validation_wrapper(self):
	namecheck(self)

	upload_image_to_medusa(self)


def upload_image_to_medusa(self):
	web_item = ""
	if self.attached_to_doctype == "Website Item":
		medusa_id = frappe.get_value(
			"Website Item", {"name": self.attached_to_name}, "medusa_id"
		)
		print("Website item Medusa ID: ", medusa_id)
		web_item = frappe.get_value(
			"Website Item", {"name": self.attached_to_name}, "web_item_name"
		)
		print("Web Item Name: ", web_item)
	elif self.attached_to_doctype == "Item":
		medusa_id = frappe.get_value(
			"Item", {"item_name": self.attached_to_name}, "medusa_id"
		)
		print("item Medusa ID: ", medusa_id)

	if medusa_id and self.attached_to_field not in ["image", "website_image"]:
		images = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": self.attached_to_doctype,
				"attached_to_name": self.attached_to_name,
				"attached_to_field": ["not in", ["image", "website_image"]],
			},
		)
		image_urls = []

		for image in images:
			doc = frappe.get_doc("File", image)
			image_path = doc.get_full_path()
			url = f"{get_url()[0]}/admin/uploads"
			headers = get_headers(with_token=True)
			headers.pop(
				"Content-Type", None
			)  # Remove the Content-Type header to let requests set it
			payload = {}
			with open(image_path, "rb") as image_file:
				files = {"files": (image_path, image_file, "image/jpeg")}
				response = requests.post(
					url, headers=headers, data=payload, files=files
				)
				if response.status_code == 200:
					uploaded_image_url = response.json().get("uploads")[0].get("url")
					print("Image uploaded")
					print("Image URL: ", uploaded_image_url)
					image_urls.append(uploaded_image_url)
				else:
					frappe.throw("Failed to upload image to Medusa")

		attach_image_to_product(image_urls, medusa_id)

	elif medusa_id and self.attached_to_field in ["image", "website_image"]:
		image_url = ""
		image_path = self.get_full_path()
		url = f"{get_url()[0]}/admin/uploads"
		headers = get_headers(with_token=True)
		headers.pop(
			"Content-Type", None
		)  # Remove the Content-Type header to let requests set it
		payload = {}
		with open(image_path, "rb") as image_file:
			files = {"files": (image_path, image_file, "image/jpeg")}
			response = requests.post(url, headers=headers, data=payload, files=files)
			if response.status_code == 200:
				uploaded_image_url = response.json().get("uploads")[0].get("url")
				print("Image uploaded")
				image_url = uploaded_image_url
			else:
				frappe.throw("Failed to upload image to Medusa")

		attach_thumbnail_to_product(image_url, medusa_id)


def attach_thumbnail_to_product(image_url, product_id):
	url = f"{get_url()[0]}/admin/products/{product_id}"
	headers = get_headers(with_token=True)
	payload = json.dumps({"thumbnail": image_url})

	args = frappe._dict(
		{
			"method": "POST",
			"url": url,
			"headers": headers,
			"payload": payload,
			"throw_message": f"Error while attaching thumbnail {image_url} to the Medusa product {product_id}",
		}
	)
	send_request(args)


def attach_image_to_product(image_url, product_id):
	url = f"{get_url()[0]}/admin/products/{product_id}"
	headers = get_headers(with_token=True)

	response = requests.get(url, headers=headers)

	existing_images = response.json().get("product", {}).get("images", [])
	existing_image_urls = [img.get("url") for img in existing_images if "url" in img]

	updated_image_urls = existing_image_urls + [image_url]

	updated_image_urls = list(set(updated_image_urls))

	payload = json.dumps({"images": updated_image_urls})

	args = frappe._dict(
		{
			"method": "POST",
			"url": url,
			"headers": headers,
			"payload": payload,
			"throw_message": "Error while attaching image to the Medusa product",
		}
	)
	send_request(args)


def export_image_to_medusa(self):
	medusa_id = frappe.get_value(
		"Website Item", {"name": self.attached_to_name}, "medusa_id"
	)

	if medusa_id:
		image_path = self.get_full_path()
		url = f"{get_url()[0]}/admin/uploads"
		headers = get_headers(with_token=True)
		headers.pop("Content-Type", None)
		payload = {}
		image_url = []

		with open(image_path, "rb") as image_file:
			files = {"files": (image_path, image_file, "image/jpeg")}
			response = requests.post(url, headers=headers, data=payload, files=files)

			if response.status_code == 200:
				uploaded_image_url = response.json().get("uploads")[0].get("url")
				print("Image uploaded")
				image_url.append(uploaded_image_url)

			else:
				frappe.throw("Failed to upload image to Medusa")

		attach_image_to_product(image_url, medusa_id)
		print("Completed image attach")
		self.db_set("medusa_id", medusa_id)


def namecheck(self):
	if " " in self.file_name:
		frappe.throw("Invalid name format!<br>File name cannot contain spaces")


def export_all_website_item():
	doctype = "Website Item"
	method = ""
	record = frappe.get_all(doctype)  # frappe.get_all(doctype, limit = 5)
	for r in record:
		doc = frappe.get_doc(doctype, r)
		if doc.published and not doc.medusa_id:
			try:
				print("Beginning to export: ", doc.name)
				export_website_item(doc, method)
			except frappe.ValidationError as e:
				print(f"Skipping {doc.name} due to error: {str(e)}")
			except Exception as e:
				print(f"Unexpected error while exporting {doc.name}: {str(e)}")
				raise e


def update_all_website_item(method=None):
	doctype = "Website Item"
	record = frappe.get_all(doctype)  # frappe.get_all(doctype, limit = 5)
	for r in record:
		doc = frappe.get_doc(doctype, r)
		if doc.medusa_id:
			try:
				print("Beginning to update: ", doc.name)
				update_website_item(doc, method)
			except frappe.ValidationError as e:
				print(f"Skipping {doc.name} due to error: {str(e)}")
			except Exception as e:
				print(f"Unexpected error while updating {doc.name}: {str(e)}")
				raise e


def export_all_item_groups():
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
	images = frappe.get_all(
		doctype,
		filters={
			"attached_to_doctype": "Website Item",
			"attached_to_field": ["in", ["image", "website_image"]],
		},
	)
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


def clear_all_item_group_id():  # For Item Group
	item_groups = frappe.get_all(
		"Item Group", filters={"medusa_id": ["!=", ""]}, fields=["name"]
	)
	print(item_groups)

	for item_group in item_groups:
		frappe.db.set_value("Item Group", item_group.name, "medusa_id", "")

	frappe.db.commit()


def clear_all_website_item_id():  # For website items
	items = frappe.get_all(
		"Website Item", filters={"medusa_id": ["!=", ""]}, fields=["name"]
	)
	print(items)

	for item in items:
		frappe.db.set_value(
			"Website Item", item.name, {"medusa_id": "", "medusa_variant_id": ""}
		)

	frappe.db.commit()


def clear_all_website_image_id():  # For website images
	images = frappe.get_all("File", filters={"medusa_id": ["!=", ""]}, fields=["name"])
	print(images)

	for image in images:
		frappe.db.set_value("File", image.name, {"medusa_id": ""})

	frappe.db.commit()


def clear_all_item_price_id():  # For item price
	item_prices = frappe.get_all(
		"Item Price", filters={"medusa_id": ["!=", ""]}, fields=["name"]
	)
	print(item_prices)

	for item_price in item_prices:
		frappe.db.set_value(
			"Item Price", item_price.name, {"medusa_id": "", "medusa_price_id": ""}
		)

	frappe.db.commit()


def export_quotation(self, method):
	from erpnext.controllers.taxes_and_totals import get_itemised_tax_breakup_data

	quotation = frappe.get_doc("Quotation", self)

	medusa_id = frappe.get_value(
		"Customer", {"name": quotation.party_name}, "medusa_id"
	)
	if not medusa_id:
		medusa_id = frappe.get_value(
			"Lead", {"name": quotation.party_name}, "medusa_id"
		)

	tax_breakup = get_itemised_tax_breakup_data(quotation)

	payload = {
		"customer_id": medusa_id,
		"draft_order_id": quotation.medusa_draft_order_id,
		"erp_status": "Price received",
		"erp_items": [],
		"erp_unaccepted_items": [],
		"erp_total_quantity": quotation.total_qty,
		"erp_total": quotation.total,
		"erp_net_total": quotation.net_total or 0,
		"erp_tax": [],
		"erp_total_taxes": quotation.total_taxes_and_charges or 0,
		"avail_delivery": quotation.get("delivery_available", False),
		"erp_delivery_charges": quotation.get("erp_delivery_charges", 2),
		"erp_grand_total": quotation.grand_total or 0,
		"erp_rounding_adjustments": quotation.rounding_adjustment or 0,
		"erp_discount_on": quotation.apply_discount_on,
		"erp_discount_percentage": quotation.additional_discount_percentage or 0,
		"erp_discount_amount": quotation.discount_amount or 0,
		"tax_breakup": tax_breakup,
	}

	for item in quotation.items:
		variant_id = frappe.get_value(
			"Website Item", {"item_name": item.item_name}, "medusa_variant_id"
		)
		payload["erp_items"].append(
			{
				"item": variant_id,
				"item_code": item.item_code,
				"price": item.rate,
				"quantity": item.qty,
				"uom": item.uom,
				"amount": item.amount,
				"item_tax_template": item.item_tax_template,
			}
		)

	if quotation.unapproved_items:
		for item in quotation.unapproved_items:
			variant_id = frappe.get_value(
				"Website Item",
				{"item_name": item.custom_item_name},
				"medusa_variant_id",
			)
			payload["erp_unaccepted_items"].append(
				{"item": variant_id, "price": item.rate, "quantity": item.qty}
			)

	for tax in quotation.taxes:
		payload["erp_tax"].append(
			{
				"account_head": tax.account_head,
				"tax_rate": tax.rate or 0,
				"tax_amount": tax.tax_amount or 0,
			}
		)

	try:
		if quotation.medusa_quotation_id and quotation.medusa_draft_order_id:
			args = frappe._dict(
				{
					"method": "POST",
					"url": f"{get_url()[0]}/store/quotation-update?quot_id={quotation.medusa_quotation_id}",
					"headers": get_headers(with_token=True),
					"payload": json.dumps(payload),
					"throw_message": f"Error while exporting Quotation {quotation.name} to Medusa",
				}
			)
			response = send_request(args)

			if response.message == "Quotation updated successfully":
				print(f"Quotation {quotation.name} exported to Medusa successfully")
			else:
				print(
					f"Error: Quotation export failed for {quotation.name}: {response.get('error')}"
				)

	except Exception as e:
		print(f"Error exporting Quotation {quotation.name}: {str(e)}")
		raise e


def export_quotation_on_update(doc, method):
	if doc.workflow_state == "Ready for Customer Review" and doc.from_ecommerce == 1:
		try:
			export_quotation(doc.name, "")
			frappe.msgprint(
				"Quotation price details sent to e-Commerce site successfully"
			)
		except Exception as e:
			frappe.log_error(
				f"Failed to export Quotation {doc.name}: {str(e)}",
				"Quotation Export Error",
			)
			print(f"Error exporting Quotation {doc.name}: {str(e)}")


@frappe.whitelist(allow_guest=True)
def export_sales_order(self, method):
	sales_order = frappe.get_doc("Sales Order", self)

	frappe.log_error(title="sales_order.status 1", message=sales_order.status)

	sales_order.reload()

	frappe.log_error(title="sales_order.status 2", message=sales_order.status)

	customer_id = frappe.get_value(
		"Customer", {"name": sales_order.customer}, "medusa_id"
	)
	if not customer_id:
		frappe.throw(
			f"Medusa Customer ID not found for Customer: {sales_order.customer}"
		)

	payment_status = "Unpaid"

	sales_invoice_name = frappe.db.sql(
		"""
		SELECT DISTINCT sii.parent 
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON sii.parent = si.name
		WHERE sii.sales_order = %s AND si.docstatus = 1
		LIMIT 1
	""",
		(sales_order.name),
		as_dict=True,
	)

	if sales_invoice_name:
		invoice_status = frappe.get_value(
			"Sales Invoice", sales_invoice_name[0].parent, "status"
		)
		payment_status = invoice_status if invoice_status else "Unpaid"

	payload = {
		"customer_id": customer_id,
		"order_status": "Pending"
		if sales_order.status == "Draft"
		else sales_order.status,
		"payment_status": payment_status,
	}

	try:
		if sales_order.medusa_order_id:
			args = frappe._dict(
				{
					"method": "POST",
					"url": f"{get_url()[0]}/store/order-update?order_id={sales_order.medusa_order_id}",
					"headers": get_headers(with_token=True),
					"payload": json.dumps(payload),
					"throw_message": f"Error while exporting Sales Order {sales_order.name} to Medusa",
				}
			)
			response = send_request(args)

			if response.message == "Order updated successfully":
				print(f"Sales Order {sales_order.name} exported to Medusa successfully")
			else:
				print(
					f"Error: Sales Order export failed for {sales_order.name}: {response.get('error')}"
				)
	except Exception as e:
		print(f"Error exporting Sales Order {sales_order.name}: {str(e)}")
		raise e


def export_sales_order_on_update(doc, method):
	if doc.from_ecommerce == 1:
		try:
			export_sales_order(doc.name, "")
			frappe.msgprint("Order details updated in Medusa site successfully")
		except Exception as e:
			frappe.log_error(
				f"Failed to export Sales Order {doc.name}: {str(e)}",
				"Sales Order Export Error",
			)
			print(f"Error exporting Sales Order {doc.name}: {str(e)}")


def export_sales_invoice_on_update(doc, method):
	try:
		sales_orders = frappe.db.sql(
			"""
			SELECT DISTINCT soi.sales_order 
			FROM `tabSales Invoice Item` soi
			WHERE soi.parent = %s
		""",
			(doc.name,),
			as_dict=True,
		)

		if not sales_orders:
			return

		sales_order_name = sales_orders[0].sales_order

		medusa_order_id = frappe.db.get_value("Sales Order", sales_order_name, "medusa_order_id")

		if not medusa_order_id:
			return

		export_sales_order(sales_order_name, "")
		frappe.msgprint(
			f"Invoice details updated in Medusa for Sales Order {sales_order_name} successfully."
		)

	except Exception as e:
		frappe.log_error(
			f"Failed to export Sales Invoice {doc.name}: {str(e)}",
			"Sales Invoice Export Error",
		)
		print(f"Error exporting Sales Invoice {doc.name}: {str(e)}")

def export_delivery_note_on_update(doc, method):
	try:
		sales_orders = frappe.db.sql(
			"""
			SELECT DISTINCT dni.against_sales_order 
			FROM `tabDelivery Note Item` dni
			WHERE dni.parent = %s AND dni.against_sales_order IS NOT NULL
			""",
			(doc.name,),
			as_dict=True,
		)

		if not sales_orders:
			return

		sales_order_name = sales_orders[0].against_sales_order

		medusa_order_id = frappe.db.get_value("Sales Order", sales_order_name, "medusa_order_id")

		if not medusa_order_id:
			return

		export_sales_order(sales_order_name, "")
		frappe.msgprint(
			f"Delivery Note details updated in Medusa for Sales Order {sales_order_name} successfully."
		)

	except Exception as e:
		frappe.log_error(
			f"Failed to export Delivery Note {doc.name}: {str(e)}",
			"Delivery Note Export Error",
		)
		print(f"Error exporting Delivery Note {doc.name}: {str(e)}")

def handle_payment_entry(doc, method):
	linked_invoices = frappe.db.sql(
		"""
		SELECT DISTINCT per.reference_name 
		FROM `tabPayment Entry Reference` per
		WHERE per.parent = %s AND per.reference_doctype = 'Sales Invoice'
	""",
		(doc.name,),
		as_dict=True,
	)

	if not linked_invoices:
		return

	for invoice in linked_invoices:
		sales_invoice = frappe.get_doc("Sales Invoice", invoice.reference_name)

		if sales_invoice.medusa_order_id:
			try:
				export_sales_invoice_on_update(sales_invoice, method)
				frappe.msgprint(
					f"Payment details updated in Medusa for Sales Invoice {sales_invoice.name}."
				)
			except Exception as e:
				frappe.log_error(
					f"Failed to export Payment Entry {doc.name}: {str(e)}",
					"Payment Entry Hook Error",
				)


def send_quotation_emails():
	email_queue = frappe.get_all(
		"Email Queue",
		filters={
			"status": "Not Sent",
			"reference_doctype": "Quotation",  # Need to update. Add sender email filter
		},
		pluck="name",
	)

	for email in email_queue:
		try:
			from frappe.email.doctype.email_queue.email_queue import send_now

			send_now(email)

		except Exception as e:
			frappe.log_error(message=str(e), title="Quotation Email Sending Failed")


@frappe.whitelist(allow_guest=True)
def get_website_items(url=None, customer_id=None):
	import re
	import math

	def fetch_items(filters, order_by, offset, page_size, customer_id):
		"""Fetch paginated website items with filters and sorting."""
		website_items = frappe.get_all(
			"Website Item",
			fields=[
				"name",
				"medusa_id",
				"medusa_variant_id",
				"web_item_name",
				"item_group",
				"custom_overall_rating",
				"has_variants",
			],
			filters=filters,
			order_by=order_by,
			start=offset,
			page_length=page_size,
		)

		base_url = frappe.utils.get_url()
		modified_items = []
		for item in website_items:
			image_url = frappe.db.get_value(
				"File",
				{
					"attached_to_doctype": "Website Item",
					"attached_to_name": item["name"],
				},
				"file_url",
			)
			if image_url:
				thumbnail = image_url if image_url.startswith("https") else f"{base_url}{image_url}"
			else:
				thumbnail = None

			is_wishlisted = 0
			if customer_id:
				is_wishlisted = frappe.db.exists(
					"Medusa Wishlist",
					{"parent": item["name"], "medusa_customer_id": customer_id},
				)
				is_wishlisted = 1 if is_wishlisted else 0
			
			specifications = frappe.db.get_all(
				"Item Website Specification",
				filters={"parent": item["name"]},
				fields=["label", "description"]
			)

			colour = ""
			shape = ""
			shade = ""

			for spec in specifications:
				if 'colo' in spec.get("label", "").lower():
					colour = spec.description
				
				elif 'shape' in spec.get("label", "").lower():
					shape = spec.description
				
				elif 'shade' in spec.get("label", "").lower():
					shade = spec.description

			modified_items.append(
				{
					"id": item["medusa_id"],
					"variant_id": item["medusa_variant_id"],
					"title": item["web_item_name"],
					"collection_title": item["item_group"],
					"thumbnail": thumbnail,
					"rating": item["custom_overall_rating"],
					"is_wishlisted": is_wishlisted,
					"has_variants": item["has_variants"],
					"colour": colour,
					"shape": shape,
					"shade": shade
				}
			)
		return modified_items
	
	def clean_entries(raw_list, skip_digit_check=False):
		result = []
		for entry in raw_list:
			entry = entry.strip()
			split_parts = re.split(r"[,/]", entry)
			
			for part in split_parts:
				value = part.strip()
				
				if len(value) < 2:
					continue

				if not skip_digit_check and re.search(r"\d", value):
					continue

				value = value.title()

				if value and value not in result:
					result.append(value)

		return sorted(result)

	try:
		data = frappe.request.get_json()

		collection_titles = data.get("collection_title")
		brands = data.get("brand")
		page = data.get("page", 1)
		availability = data.get("availability")
		sort_order = data.get("sort_order", "asc")
		page_size = 20
		offset = (int(page) - 1) * page_size
		shapes = data.get("shape")
		colors = data.get("colour")
		shades = data.get("shade")

		parts = url.strip("/").split("/")
		banner_url = "/".join(parts[:2]) if len(parts) > 1 else url

		url_second_part = parts[1].replace("-", "%") if len(parts) > 1 else None

		banner_item_group = (
			frappe.db.get_value(
				"Item Group",
				{"name": ["like", f"%{url_second_part}%"]}
				if "%" in url_second_part
				else {"name": url_second_part}
				if url_second_part
				else None,
				"name",
			)
			if url_second_part
			else None
		)

		last_part = parts[-1].replace("-", "%")
		second_part = set()

		item_group = frappe.db.get_value(
			"Item Group",
			{"name": ["like", f"%{last_part}%"]}
			if "%" in last_part
			else {"name": last_part},
			"name",
		)

		if not item_group:
			return {
				"status": "error",
				"message": f"No matching item group found for the URL: {url}",
			}

		if sort_order == "default":
			order_by = "ranking desc"
		elif sort_order == "asc":
			order_by = "item_name asc"
		else:
			order_by = "item_name desc"

		descendant_groups = frappe.db.get_descendants("Item Group", item_group)
		descendant_groups.append(item_group)

		filters = {"item_group": ["in", descendant_groups]}

		distinct_parent_item_groups = []
		distinct_collection_titles = []
		distinct_brands = []

		banner_details = get_product_details_banner(banner_item_group)

		distinct_collection_titles = frappe.db.sql(
			"""
			SELECT item_group AS name, COUNT(*) AS count
			FROM `tabWebsite Item`
			WHERE item_group IN %(descendant_groups)s
			GROUP BY item_group
			ORDER BY name
		""",
			{"descendant_groups": tuple(descendant_groups)}, as_dict=True)

		if collection_titles:
			if not isinstance(collection_titles, list):
				collection_titles = [collection_titles]

			collection_descendants = []
			for title in collection_titles:
				# descendants = frappe.db.get_descendants("Item Group", title)
				# collection_descendants.extend(descendants)
				collection_descendants.append(title)

			filters["item_group"] = ["in", list(set(collection_descendants))]

			distinct_brands = frappe.db.sql(
				"""
				SELECT brand AS name, COUNT(*) AS count
				FROM `tabWebsite Item`
				WHERE item_group IN %(collection_descendants)s AND brand IS NOT NULL AND brand != ''
				GROUP BY brand
				ORDER BY brand
			""",
				{"collection_descendants": tuple(collection_descendants)},
				as_dict=True,
			)

		else:
			distinct_brands = frappe.db.sql(
				"""
				SELECT brand AS name, COUNT(*) AS count
				FROM `tabWebsite Item`
				WHERE item_group IN %(descendant_groups)s AND brand IS NOT NULL AND brand != ''
				GROUP BY brand
				ORDER BY brand
			""",
				{"descendant_groups": tuple(descendant_groups)},
				as_dict=True,
			)

		if brands:
			if not isinstance(brands, list):
				brands = [brands]
			filters["brand"] = ["in", brands]

		if brands and not collection_titles:
			distinct_collection_titles = frappe.db.sql(
				"""
				SELECT item_group AS name, COUNT(*) AS count
				FROM `tabWebsite Item`
				WHERE item_group IN %(descendant_groups)s
				{brand_filter}
				GROUP BY item_group
				ORDER BY name
			""".format(brand_filter="AND brand IN %(brands)s" if brands else ""),
				{
					"descendant_groups": tuple(descendant_groups),
					"brands": tuple(brands) if brands else None,
				},
				as_dict=True,
			)

		if not (item_group == "Products" and brands and not collection_titles):
			immediate_descendants = frappe.get_all(
				"Item Group",
				fields=["name"],
				filters={"parent_item_group": item_group},
				order_by="name",
			)

			distinct_parent_item_groups = [
				{
					"title": group["name"],
					"handle": re.sub(r"[^a-z0-9]+", "-", group["name"].lower()).strip(
						"-"
					),
				}
				for group in immediate_descendants
			]
		else:
			for collection in distinct_collection_titles:
				route = frappe.db.get_value(
					"Item Group", {"name": collection.name}, "route"
				)
				parts = route.strip("/").split("/")
				if len(parts) > 1:
					second_part.add(parts[1].replace("-", "%"))

			second_part_list = list(second_part)
			parent_groups = []
			for part in second_part_list:
				parent_group = frappe.db.get_value(
					"Item Group",
					{"name": ["like", f"%{part}%"]} if "%" in part else {"name": part},
					"name",
				)
				if parent_group:
					parent_groups.append(parent_group)

			distinct_parent_item_groups = [
				{
					"title": group,
					"handle": re.sub(r"[^a-z0-9]+", "-", group.lower()).strip("-"),
				}
				for group in parent_groups
			]
		
		distinct_colours = distinct_shapes = distinct_shades = []
		if shapes or shades or colors:
			filters_clause = "1=1"
			params = {}

			if collection_titles:
				if not isinstance(collection_titles, list):
					collection_titles = [collection_titles]
				filters_clause += " AND item_group IN %(item_groups)s"
				params["item_groups"] = tuple(collection_titles)

			if brands:
				if not isinstance(brands, list):
					brands = [brands]
				filters_clause += " AND brand IN %(brands)s"
				params["brands"] = tuple(brands)

			website_items = frappe.db.sql(
				f"""
				SELECT name FROM `tabWebsite Item`
				WHERE {filters_clause}
				""",
				params,
				as_dict=True
			)

			item_names = [item["name"] for item in website_items]
			all_colours = all_shapes = all_shades = []

			if item_names:
				distinct_colours = frappe.db.sql(
					"""
					SELECT DISTINCT description
					FROM `tabItem Website Specification`
					WHERE parent IN %(item_names)s AND LOWER(label) LIKE '%%colo%%'
					""",
					{"item_names": tuple(item_names)},
					as_dict=True,
				)

				distinct_shapes = frappe.db.sql(
					"""
					SELECT DISTINCT description
					FROM `tabItem Website Specification`
					WHERE parent IN %(item_names)s AND LOWER(label) LIKE '%%shape%%'
					""",
					{"item_names": tuple(item_names)},
					as_dict=True,
				)

				distinct_shades = frappe.db.sql(
					"""
					SELECT DISTINCT description
					FROM `tabItem Website Specification`
					WHERE parent IN %(item_names)s AND LOWER(label) LIKE '%%shade%%'
					""",
					{"item_names": tuple(item_names)},
					as_dict=True,
				)

				all_colours = [d["description"] for d in distinct_colours if d["description"]]
				all_shapes = [d["description"] for d in distinct_shapes if d["description"]]
				all_shades = [d["description"] for d in distinct_shades if d["description"]]
			
			if all_colours:		
				distinct_colours = clean_entries(all_colours, skip_digit_check=False)
			
			if all_shapes:
				distinct_shapes = clean_entries(all_shapes, skip_digit_check=True)
			
			if all_shades:
				distinct_shades = clean_entries(all_shades, skip_digit_check=True)
		
		if availability:
			filters["custom_in_stock"] = ["=", 1]
		
		base_filters_count = frappe.db.count("Website Item", filters=filters)

		if shapes and not isinstance(shapes, list):
			shapes = [shapes]

		if colors and not isinstance(colors, list):
			colors = [colors]
		
		if shades and not isinstance(shades, list):
			shades = [shades]
		
		website_items_by_spec = []

		if colors:
			color_conditions = " OR ".join([
				f"LOWER(description) LIKE %(color_{i})s"
				for i in range(len(colors))
			])

			color_filters = {
				f"color_{i}": f"%{color.lower()}%"
				for i, color in enumerate(colors)
			}
			color_filters["label_pattern"] = "%colo%"

			color_items = frappe.db.sql(f"""
				SELECT parent FROM `tabItem Website Specification`
				WHERE LOWER(label) LIKE %(label_pattern)s AND ({color_conditions})
			""", color_filters, as_dict=True)

			website_items_by_spec.extend([d["parent"] for d in color_items])

		if shapes:
			conditions = " OR ".join([
				f"LOWER(description) LIKE %(shape_{i})s"
				for i in range(len(shapes))
			])

			filters = {
				f"shape_{i}": f"%{shape.lower()}%"
				for i, shape in enumerate(shapes)
			}
			filters["label_pattern"] = "%shape%"

			shape_items = frappe.db.sql(f"""
				SELECT parent FROM `tabItem Website Specification`
				WHERE LOWER(label) LIKE %(label_pattern)s AND ({conditions})
			""", filters, as_dict=True)

			website_items_by_spec.extend([d["parent"] for d in shape_items])
		
		if shades:
			conditions = " OR ".join([
				f"LOWER(description) LIKE %(shade_{i})s"
				for i in range(len(shades))
			])

			filters = {
				f"shade_{i}": f"%{shade.lower()}%"
				for i, shade in enumerate(shades)
			}
			filters["label_pattern"] = "%shade%"

			shade_items = frappe.db.sql(f"""
				SELECT parent FROM `tabItem Website Specification`
				WHERE LOWER(label) LIKE %(label_pattern)s AND ({conditions})
			""", filters, as_dict=True)

			website_items_by_spec.extend([d["parent"] for d in shade_items])
		
		if website_items_by_spec:
			filtered_item_names = list(set(website_items_by_spec))
			filters = {
				"name": ["in", filtered_item_names]
			}
			total_products = frappe.db.count("Website Item", filters=filters)
		else:
			total_products = base_filters_count

		modified_items = fetch_items(filters, order_by, offset, page_size, customer_id)

		return {
			"product_count": total_products,
			"total_pages": math.ceil(total_products / page_size),
			"current_page": int(page),
			"items_in_page": len(modified_items),
			"banner": banner_details,
			"banner_url": banner_url,
			"distinct_parent_item_groups": distinct_parent_item_groups,
			"distinct_collection_titles": distinct_collection_titles,
			"distinct_brands": distinct_brands,
			"distinct_colours": distinct_colours,
			"distinct_shapes": distinct_shapes,
			"distinct_shades": distinct_shades,
			"paginatedProducts": modified_items
		}

	except Exception as e:
		frappe.log_error(title="Fetch Website Items Failed", message=frappe.get_traceback())
		return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def get_website_variants(medusa_id, customer_id=None):
	try:
		parent_item = frappe.get_value("Website Item", {"medusa_id": medusa_id}, "name")

		if not parent_item:
			return ("No Website Item found with this medusa_id")

		variant_items = frappe.get_all(
			"Website Item",
			filters={"custom_parent_website_item": parent_item},
			fields=["name", "web_item_name", "medusa_id", "medusa_variant_id", "item_group", "custom_overall_rating"]
		)

		modified_items = []
		for item in variant_items:
			is_wishlisted = 0
			if customer_id:
				is_wishlisted = frappe.db.exists(
					"Medusa Wishlist",
					{"parent": item["name"], "medusa_customer_id": customer_id},
				)
				is_wishlisted = 1 if is_wishlisted else 0
			
			modified_items.append(
				{
					"id": item["medusa_id"],
					"variant_id": item["medusa_variant_id"],
					"title": item["web_item_name"],
					"collection_title": item["item_group"],
					"rating": item["custom_overall_rating"],
					"is_wishlisted": is_wishlisted
				}
			)

		return {
			"status": "success",
			"related_items": modified_items
		}

	except Exception as e:
		frappe.log_error(title= "get_website_variants error", message=frappe.get_traceback())
		return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def get_all_brands(item_group=None):
	try:
		base_url = frappe.utils.get_url()
		brands = []

		if item_group:
			descendant_groups = frappe.db.get_descendants("Item Group", item_group)
			descendant_groups.append(item_group)

			brands = frappe.db.sql(
				"""
				SELECT DISTINCT w.brand AS name
				FROM `tabWebsite Item` w
				WHERE w.item_group IN %(descendant_groups)s
				AND w.brand IS NOT NULL AND w.brand != ''
				ORDER BY w.brand ASC
			""",
				{"descendant_groups": tuple(descendant_groups)},
				as_dict=True,
			)

		else:
			brands = frappe.get_all("Brand", fields=["name"], order_by="name asc")

		brand_list = []
		top_categories = [
			"DENTAL",
			"MEDICAL",
			"Medical Laboratory IVD",
			"Infection Control",
		]
		for brand in brands:
			image_url = frappe.db.get_value(
				"File",
				{
					"attached_to_doctype": "Brand",
					"attached_to_name": brand.get("brand") or brand["name"],
				},
				"file_url",
			)
			if image_url:
				thumbnail = image_url if image_url.startswith("https") else f"{base_url}{image_url}"
			else:
				thumbnail = None

			brand_list.append(
				{"brand": brand.get("brand") or brand["name"], "image": thumbnail}
			)

		return {"top_categories": top_categories, "brand_list": brand_list}

	except Exception as e:
		frappe.log_error(message=str(e), title="Fetch Brands Failed")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def get_homepage_top_section():
	try:
		top_section = frappe.get_doc("Homepage Landing", "Active Homepage Landing")

		base_url = frappe.utils.get_url()

		def fetch_image_url(doctype, name):
			image_url = frappe.db.get_value(
				"File",
				{"attached_to_doctype": doctype, "attached_to_name": name},
				"file_url",
			)

			if image_url:
				thumbnail = image_url if image_url.startswith("https") else f"{base_url}{image_url}"
			else:
				thumbnail = None
			
			return thumbnail

		def fetch_first_layer_children(parent_group):
			children = frappe.get_all(
				"Item Group",
				fields=["name"],
				filters={"parent_item_group": parent_group},
				order_by="name",
			)

			enriched_children = []
			for child in children:
				route = frappe.db.get_value(
					"Item Group", child["name"], "custom_medusa_route"
				)

				enriched_children.append({"title": child["name"], "url": route})
			return enriched_children

		entries_data = []
		for entry in top_section.top_section:
			thumbnail = fetch_image_url(entry.link_doctype, entry.name1)

			if entry.link_doctype == "Item Group":
				url = frappe.db.get_value(
					"Item Group", entry.name1, "custom_medusa_route"
				)
				enriched_sub_categories = fetch_first_layer_children(entry.name1)

				entries_data.append(
					{
						"type": entry.link_doctype,
						"title": entry.name1,
						"thumbnail": thumbnail,
						"url": url,
						"sub_categories": enriched_sub_categories,
					}
				)
			elif entry.link_doctype == "Brand":
				item_groups = frappe.db.sql(
					"""
					SELECT DISTINCT w.item_group AS name
					FROM `tabWebsite Item` w
					WHERE w.brand = %(brand_name)s
					ORDER BY w.item_group ASC
				""",
					{"brand_name": entry.name1},
					as_dict=True,
				)

				categories = [
					{
						"name": group["name"],
						"url": frappe.db.get_value(
							"Item Group", group["name"], "custom_medusa_route"
						),
					}
					for group in item_groups
				]

				entries_data.append(
					{
						"type": entry.link_doctype,
						"title": entry.name1,
						"thumbnail": thumbnail,
						"categories": categories,
					}
				)

		return entries_data

	except Exception as e:
		frappe.log_error(message=str(e), title="Fetch Homepage Top Section Failed")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def get_homepage_menu_section():
	try:
		menu_section = frappe.get_doc("Homepage Landing", "Active Homepage Landing")

		entries_data = []
		for entry in menu_section.menu_section:
			if entry.link_doctype == "Item Group":
				url = frappe.db.get_value(
					"Item Group", entry.name1, "custom_medusa_route"
				)

				entries_data.append({"title": entry.name1, "url": url})

		return entries_data

	except Exception as e:
		frappe.log_error(message=str(e), title="Fetch Homepage Menu Section Failed")
		return {"status": "error", "message": str(e)}


def get_full_route(item_group):
	current_group = item_group
	route_parts = []

	while current_group and current_group != "Products":
		route_parts.append(slugify(current_group))
		current_group = frappe.db.get_value(
			"Item Group", current_group, "parent_item_group"
		)

	route_parts.append("products")
	return "/".join(reversed(route_parts))


def slugify(name):
	import re

	return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


@frappe.whitelist()
def update_all_item_groups():
	try:
		item_groups = frappe.get_all("Item Group", fields=["name"])

		for item_group in item_groups:
			route = get_full_route(item_group["name"])

			frappe.db.set_value(
				"Item Group", item_group["name"], "custom_medusa_route", route
			)

		frappe.db.commit()
		return {"status": "success", "message": "All item groups updated successfully."}

	except Exception as e:
		frappe.log_error(message=str(e), title="Update Item Groups Failed")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def get_menu(parent=None, mobile_view=0):
	def fetch_image(item_group_name):
		image_url = frappe.db.get_value(
			"File",
			{"attached_to_doctype": "Item Group", "attached_to_name": item_group_name},
			"file_url",
		)

		base_url = frappe.utils.get_url()

		if image_url:
			thumbnail = image_url if image_url.startswith("https") else f"{base_url}{image_url}"
		else:
			thumbnail = None
		
		return thumbnail

	def fetch_child_groups(parent_group, depth=0, max_depth=1):
		children = frappe.get_all(
			"Item Group",
			fields=["name", "custom_medusa_route"],
			filters={"parent_item_group": parent_group},
			order_by="name",
		)

		if not children:
			return []

		sub_child_counts = frappe.db.sql(
			"""
			SELECT parent_item_group, COUNT(name) AS child_count 
			FROM `tabItem Group` 
			WHERE parent_item_group IN %(parent_groups)s 
			GROUP BY parent_item_group
			""",
			{"parent_groups": tuple([child["name"] for child in children])},
			as_dict=True,
		)
		child_count_map = {
			row["parent_item_group"]: row["child_count"] for row in sub_child_counts
		}

		child_groups = []
		for child in children:
			sub_child_count = child_count_map.get(child["name"], 0)
			image = None
			route = None

			if mobile_view:
				route = child["custom_medusa_route"]
				image = fetch_image(child["name"])

			child_data = {
				"title": child["name"],
				"handle": slugify(child["name"]),
				"url": route,
				"thumbnail": image,
				"childCount": sub_child_count,
			}

			if sub_child_count > 0 and (mobile_view or depth < max_depth):
				child_data["children"] = fetch_child_groups(
					parent_group=child["name"], depth=depth + 1, max_depth=max_depth
				)

			child_groups.append(child_data)
		child_groups.sort(key=lambda x: x["childCount"], reverse=True)

		return child_groups

	try:
		mobile_view = bool(int(mobile_view))
		max_depth = 1 if not mobile_view else float("inf")

		parent_data = frappe.get_value(
			"Item Group",
			{"name": parent},
			["name", "custom_medusa_route"],
			as_dict=True,
		)

		if not parent_data:
			return {"status": "error", "message": "Parent item group not found"}

		parent_details = {
			"title": parent_data["name"],
			"handle": slugify(parent_data["name"]),
			"url": parent_data["custom_medusa_route"],
			"thumbnail": fetch_image(parent_data["name"]),
			"childCount": frappe.db.count("Item Group", {"parent_item_group": parent}),
			"children": fetch_child_groups(parent, max_depth=max_depth),
		}

		return parent_details

	except Exception as e:
		frappe.log_error(message=str(e), title="Fetch Child Item Groups Failed")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def add_review_to_website_item(
	item_code,
	customer_id,
	customer_name=None,
	review=None,
	review_id=0,
	rating=0,
	date=None,
	likes=0,
	dislikes=0,
):
	website_item = None
	try:
		web_item_code = frappe.db.get_value(
			"Website Item", {"medusa_id": item_code}, "name"
		)
		website_item = frappe.get_doc("Website Item", web_item_code)

		frappe.db.set_value(
			"Website Item", website_item.name, "custom_skip_update_hook", 1
		)

		if likes or dislikes:
			like_dislike_review = None
			for r in website_item.custom_review:
				if r.review_id == str(review_id):
					like_dislike_review = r
					break

			if likes:
				like_dislike_review.likes = likes
			if dislikes:
				like_dislike_review.dislikes = dislikes
			website_item.save(ignore_permissions=True)
			frappe.db.commit()

			return {
				"status": "success",
				"message": "Likes and dislikes updated successfully",
			}

		rating = max(1, rating)
		existing_review = None
		for r in website_item.custom_review:
			if r.medusa_id == customer_id:
				existing_review = r
				break

		if existing_review:
			if customer_name:
				existing_review.name1 = customer_name
			if review:
				existing_review.review = review
			if review_id:
				existing_review.review_id = review_id
			if rating:
				existing_review.rating = rating / 5
			if date:
				existing_review.date = date
			existing_review.likes = 0
			existing_review.dislikes = 0
		else:
			website_item.append(
				"custom_review",
				{
					"medusa_id": customer_id,
					"name1": customer_name,
					"review": review,
					"review_id": review_id,
					"rating": rating / 5,
					"date": date,
					"likes": likes,
					"dislikes": dislikes,
				},
			)

		reviews = website_item.get("custom_review")
		total_ratings = sum([r.rating * 5 for r in reviews])
		total_reviews = len(reviews)
		overall_rating = total_ratings / total_reviews if total_reviews > 0 else 0
		website_item.custom_overall_rating = overall_rating

		website_item.save(ignore_permissions=True)
		frappe.db.commit()

		return (
			"Review updated successfully"
			if existing_review
			else "Review added successfully"
		)

	except Exception as e:
		frappe.log_error(
			message=frappe.get_traceback(with_context=1),
			title="Add Review to Website Item",
		)
		return {"status": "error", "message": str(e)}

	finally:
		if website_item:
			frappe.db.set_value(
				"Website Item", website_item.name, "custom_skip_update_hook", 0
			)


@frappe.whitelist(allow_guest=True)
def handle_wishlist(item_codes, customer_id, is_add=0, is_remove=0):
	try:
		if not isinstance(item_codes, list):
			item_codes = [item_codes]

		is_add = int(is_add)
		is_remove = int(is_remove)

		if is_add == is_remove:
			return {
				"status": "error",
				"message": "Either is_add or is_remove must be 1, not both or none",
			}

		response = []

		for item_code in item_codes:
			website_item = None

			try:
				web_item_code = frappe.db.get_value(
					"Website Item", {"medusa_id": item_code}, "name"
				)
				if not web_item_code:
					response.append(
						{
							"item_code": item_code,
							"status": "error",
							"message": "Item not found",
						}
					)
					continue

				website_item = frappe.get_doc("Website Item", web_item_code)
				frappe.db.set_value(
					"Website Item", website_item.name, "custom_skip_update_hook", 1
				)
				website_item.reload()

				existing_wishlist_entry = None
				for entry in website_item.custom_medusa_wishlist:
					if entry.medusa_customer_id == customer_id:
						existing_wishlist_entry = entry
						break

				if is_add:
					if existing_wishlist_entry:
						response.append(
							{
								"item_code": item_code,
								"status": "skipped",
								"message": "Customer already in wishlist",
							}
						)
					else:
						website_item.append(
							"custom_medusa_wishlist",
							{"medusa_customer_id": customer_id},
						)
						website_item.save(ignore_permissions=True)
						frappe.db.commit()
						response.append(
							{
								"item_code": item_code,
								"status": "success",
								"message": "Customer added to wishlist",
							}
						)

				elif is_remove:
					if existing_wishlist_entry:
						website_item.custom_medusa_wishlist.remove(
							existing_wishlist_entry
						)
						website_item.save(ignore_permissions=True)
						frappe.db.commit()
						response.append(
							{
								"item_code": item_code,
								"status": "success",
								"message": "Customer removed from wishlist",
							}
						)
					else:
						response.append(
							{
								"item_code": item_code,
								"status": "skipped",
								"message": "Customer not in wishlist",
							}
						)

			except Exception as e:
				frappe.log_error(
					message=frappe.get_traceback(with_context=1), title="Wishlist Error"
				)
				response.append(
					{"item_code": item_code, "status": "error", "message": str(e)}
				)

			finally:
				if website_item:
					frappe.db.set_value(
						"Website Item", website_item.name, "custom_skip_update_hook", 0
					)

		return response

	except Exception as e:
		frappe.log_error(
			message=frappe.get_traceback(with_context=1), title="Wishlist API Failed"
		)
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def fetch_quotation_pdf_url():
	data = json.loads(frappe.request.data)
	quotation_id = data.get("quotation_id")

	if not frappe.db.exists("Quotation", quotation_id):
		return {"error": f"Quotation with ID {quotation_id} not found."}

	try:
		site_url = frappe.utils.get_url()

		pdf_url = f"{site_url}/printview?doctype=Quotation&name={quotation_id}&format=Alfarsi%20Quote%20Print&no_letterhead=0&_lang=en"

		return pdf_url

	except Exception as e:
		frappe.log_error(
			f"Error generating PDF URL for Quotation {quotation_id}: {str(e)}",
			"Quotation PDF URL Error",
		)
		return {"error": f"Failed to generate PDF URL: {str(e)}"}


@frappe.whitelist(allow_guest=True)
def fetch_relevant_collection_products(cus_id=None):
	try:
		data = json.loads(frappe.request.data)
		item_group = data.get("item_group")
		second_part = ""

		route = frappe.db.get_value("Item Group", {"name": item_group}, "route")
		parts = route.strip("/").split("/")
		if len(parts) > 1:
			second_part = parts[1].replace("-", "%")

		parent_group = frappe.db.get_value(
			"Item Group",
			{"name": ["like", f"%{second_part}%"]}
			if "%" in second_part
			else {"name": second_part},
			"name",
		)

		parent_route = frappe.db.get_value(
			"Item Group", {"name": parent_group}, "custom_medusa_route"
		)
		result = get_website_items(url=parent_route, customer_id=cus_id)
		return {
			"top_collection": parent_group,
			"products": result.get("paginatedProducts"),
		}
	except Exception as e:
		frappe.log_error(
			message=str(e), title="Fetch Relevant Collection Products Failed"
		)
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def fetch_relevant_items():
	recommended_items_data = []

	def get_recommended_items_data(relevant_items, cus_id):
		items_data = set()
		results = []

		for recommended_item in relevant_items:
			base_url = frappe.utils.get_url()
			website_item_name = recommended_item
			medusa_id = frappe.get_value(
				"Website Item", {"name": website_item_name}, "medusa_id"
			)

			if medusa_id in items_data:
				continue

			image_url = frappe.db.get_value(
				"File",
				{
					"attached_to_doctype": "Website Item",
					"attached_to_name": website_item_name,
				},
				"file_url",
			)
			if image_url:
				thumbnail = image_url if image_url.startswith("https") else f"{base_url}{image_url}"
			else:
				thumbnail = None

			item_data = frappe.get_doc("Website Item", website_item_name)

			is_wishlisted = 0
			if cus_id:
				is_wishlisted = frappe.db.exists(
					"Medusa Wishlist",
					{"parent": website_item_name, "medusa_customer_id": cus_id},
				)
				is_wishlisted = 1 if is_wishlisted else 0

			item_entry = {
				"id": medusa_id,
				"variant_id": item_data.medusa_variant_id,
				"title": item_data.web_item_name,
				"item_group": item_data.item_group,
				"thumbnail": thumbnail,
				"rating": item_data.custom_overall_rating,
				"isWishlisted": is_wishlisted,
			}

			results.append(item_entry)
			items_data.add(medusa_id)

		return results

	try:
		data = json.loads(frappe.request.data)
		item_code = data.get("item_code")
		cus_id = data.get("cus_id")

		website_item = frappe.get_doc("Website Item", {"item_code": item_code})
		parent_route = frappe.db.get_value(
			"Item Group", {"name": website_item.item_group}, "route"
		)

		relevant_items = [
			related_item.website_item for related_item in website_item.recommended_items
		]

		if relevant_items == []:
			frappe.local.response["http_status_code"] = 404
			return "No relevant items found"

		relevant_items_data = get_recommended_items_data(relevant_items, cus_id)
		recommended_items_data.extend(relevant_items_data)

		products = get_website_items(url=parent_route)
		paginated_products = [
			p
			for p in products["paginatedProducts"]
			if p["id"] != website_item.medusa_id
			and p["id"] not in {item["id"] for item in recommended_items_data}
		]
		recommended_items_data.extend(paginated_products)

		return recommended_items_data
	except Exception as e:
		frappe.log_error(message=str(e), title=_("Fetch relevant products failed"))
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def get_top_sellers(customer_id=None):
	return fetch_items_from_homepage("top_sellers", customer_id)


@frappe.whitelist(allow_guest=True)
def get_recommended_items(customer_id=None):
	return fetch_items_from_homepage("recommended_items", customer_id)


@frappe.whitelist(allow_guest=True)
def get_trending_items(customer_id=None):
	return fetch_items_from_homepage("trending_items", customer_id)


@frappe.whitelist(allow_guest=True)
def get_new_arrivals(customer_id=None):
	return fetch_items_from_homepage("new_arrivals", customer_id)


@frappe.whitelist(allow_guest=True)
def get_dental_items(customer_id=None):
	return fetch_items_from_homepage("dental_items", customer_id)


@frappe.whitelist(allow_guest=True)
def get_medical_items(customer_id=None):
	return fetch_items_from_homepage("medical_items", customer_id)


@frappe.whitelist(allow_guest=True)
def get_medical_laboratory_items(customer_id=None):
	return fetch_items_from_homepage("medical_laboratory_items", customer_id)


@frappe.whitelist(allow_guest=True)
def get_infection_control_items(customer_id=None):
	return fetch_items_from_homepage("infection_control_items", customer_id)

@frappe.whitelist(allow_guest=True)
def get_clearance_items(customer_id=None):
	return fetch_items_from_homepage("clearance_items", customer_id)

@frappe.whitelist(allow_guest=True)
def get_best_deals():
	try:
		active_best_deals = frappe.get_doc("Homepage Landing", "Active Homepage Landing")

		entries_data = []

		for entry in active_best_deals.best_deals:
			website_item_code = (
				entry.website_item if hasattr(entry, "website_item") else None
			)
			website_item_details = None
			image_url = None

			if website_item_code:
				website_item_details = frappe.db.get_value(
					"Website Item",
					{"name": website_item_code},
					["web_item_name", "medusa_id"],
					as_dict=True,
				)

			entry_data = {
				"url": entry.url,
				"title": website_item_details.web_item_name
				if website_item_details
				else None,
				"medusa_id": website_item_details.medusa_id,
			}

			entries_data.append(entry_data)

		return entries_data

	except Exception as e:
		frappe.log_error(
			message=str(e), title="Fetch Best Deals Failed"
		)
		return {"status": "error", "message": str(e)}

def fetch_items_from_homepage(item_field_name, customer_id=None):
	import random

	try:
		homepage_landing = frappe.get_doc("Homepage Landing", "Active Homepage Landing")
		all_items = getattr(homepage_landing, item_field_name, [])

		if len(all_items) <= 20:
			random_entries = random.sample(all_items, len(all_items))
		else:
			random_entries = random.sample(all_items, 20)

		base_url = frappe.utils.get_url()

		entries_data = []
		for entry in random_entries:
			website_item_code = entry.website_item

			image_url = frappe.db.get_value(
				"File",
				{
					"attached_to_doctype": "Website Item",
					"attached_to_name": website_item_code,
				},
				"file_url",
			)
			if image_url:
				thumbnail = image_url if image_url.startswith("https") else f"{base_url}{image_url}"
			else:
				thumbnail = None

			website_item_details = frappe.db.get_value(
				"Website Item",
				{"name": website_item_code},
				[
					"medusa_id",
					"medusa_variant_id",
					"web_item_name",
					"item_group",
					"custom_overall_rating",
					"has_variants"
				],
				as_dict=True,
			)

			is_wishlisted = 0
			if customer_id:
				is_wishlisted = frappe.db.exists(
					"Medusa Wishlist",
					{"parent": website_item_code, "medusa_customer_id": customer_id},
				)
				is_wishlisted = 1 if is_wishlisted else 0

			if website_item_details:
				entries_data.append(
					{
						"product_id": website_item_details.medusa_id,
						"variant_id": website_item_details.medusa_variant_id,
						"item_name": website_item_details.web_item_name,
						"item_group": website_item_details.item_group,
						"overall_rating": website_item_details.custom_overall_rating,
						"thumbnail": thumbnail,
						"is_wishlisted": is_wishlisted,
						"has_variants": website_item_details.has_variants
					}
				)

		return entries_data

	except Exception as e:
		frappe.log_error(message=str(e), title="Fetch Homepage Items Failed")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def get_homepage_order_list():
	try:
		active_order_list_name = "Active Homepage Landing"

		homepage_order_list = frappe.get_doc("Homepage Landing", active_order_list_name)

		order_data = []

		function_map = {
			"DENTAL": "get_dental_items",
			"MEDICAL": "get_medical_items",
			"INFECTION CONTROL": "get_infection_control_items",
			"MEDICAL LABORATORY IVD": "get_medical_laboratory_items",
		}

		for order in homepage_order_list.order:
			if order.label.upper() in function_map:
				order_data.append(
					{
						"title": order.label.title(),
						"function": function_map[order.label.upper()],
					}
				)

		return order_data

	except Exception as e:
		frappe.log_error(
			message=str(e), title="Fetch Active Homepage Order List Failed"
		)
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def get_yt_videos_list():
	try:
		active_yt_videos = "Active Homepage Landing"

		active_yt_videos_doc = frappe.get_doc("Homepage Landing", active_yt_videos)

		entries_data = []

		for entry in active_yt_videos_doc.urls:
			website_item_code = (
				entry.website_item if hasattr(entry, "website_item") else None
			)
			website_item_details = None
			image_url = None
			base_url = frappe.utils.get_url()

			if website_item_code:
				website_item_details = frappe.db.get_value(
					"Website Item",
					{"name": website_item_code},
					["web_item_name", "medusa_id", "has_variants"],
					as_dict=True,
				)

				image_url = frappe.db.get_value(
					"File",
					{
						"attached_to_doctype": "Website Item",
						"attached_to_name": website_item_code,
					},
					"file_url",
				)
				if image_url:
					thumbnail = image_url if image_url.startswith("https") else f"{base_url}{image_url}"
				else:
					thumbnail = None

			entry_data = {
				"url": entry.url,
				"title": website_item_details.web_item_name
				if website_item_details
				else None,
				"medusa_id": website_item_details.medusa_id
				if website_item_details
				else None,
				"has_variants": website_item_details.has_variants
				if website_item_details
				else None,
				"thumbnail": thumbnail
			}

			entries_data.append(entry_data)

		return entries_data

	except Exception as e:
		frappe.log_error(
			message=str(e), title="Fetch Active YouTube Videos List Failed"
		)
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def get_testimonials():
	try:
		homepage = frappe.get_doc("Homepage Landing", "Active Homepage Landing")

		testimonials_data = []
		for entry in homepage.testimonials:
			testimonials_data.append(
				{
					"thumbnail": entry.image_url,
					"review": entry.review,
					"review_by": entry.review_by,
					"designation": entry.designation,
				}
			)

		return testimonials_data

	except Exception as e:
		frappe.log_error(message=str(e), title="Fetch Testimonials Failed")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def get_product_details_banner(item_group):
	try:
		url = frappe.db.get_value(
			"Product details banner",
			{"parent": "Active Homepage Landing", "item_group": item_group},
			"url",
		)

		return url

	except Exception as e:
		frappe.log_error(message=str(e), title="Fetch URL by Item Group Failed")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def get_homepage_banners():
	try:
		homepage = frappe.get_doc("Homepage Landing", "Active Homepage Landing")

		banners_data = []

		for banner in homepage.banners:
			banner_data = {
				"banner_url": banner.url,
				"link_doctype": banner.link_doctype,
				"name1": banner.name1,
			}

			if banner.link_doctype == "Item Group":
				custom_route = frappe.db.get_value(
					"Item Group", banner.name1, "custom_medusa_route"
				)
				banner_data["item_group_url"] = custom_route

			banners_data.append(banner_data)

		return banners_data

	except Exception as e:
		frappe.log_error(message=str(e), title="Fetch Homepage Banners Failed")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def create_product_suggestion(
	product_name,
	suggested_by,
	contact_number,
	product_short_description=None,
	product_link=None,
	product_supplier=None,
	supplier_details=None,
):
	if not product_name or not suggested_by or not contact_number:
		return {
			"status": "error",
			"message": "Product Name, Suggested By, and Contact Number are mandatory fields.",
		}

	try:
		new_suggestion = frappe.get_doc(
			{
				"doctype": "Product Suggestions",
				"product_name": product_name,
				"suggested_by": suggested_by,
				"contact_number": contact_number,
				"product_short_description": product_short_description,
				"product_link": product_link,
				"product_supplier": product_supplier,
				"supplier_details": supplier_details,
			}
		)
		new_suggestion.insert(ignore_permissions=True)
		frappe.db.commit()

		return "Product suggestion created successfully"

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Product Suggestion Creation Failed")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def sign_up(
	email,
	first_name,
	last_name,
	t_c_acceptance,
	mobile,
	otp,
	organization_name,
	erp_customer_id=None,
):
	validate_otp = verify_otp(email=email, user_otp=otp)
	if validate_otp.get("otp_name"):
		otp_doc = frappe.get_doc("Email OTP", validate_otp.get("otp_name"))
		if otp_doc.logged_in:
			return "This Email is Registered kindly login"
		else:
			password = str(random.randrange(10**11, (10**12) - 1))
			otp_doc.password = password
			url = f"{medusa_base_url}/store/signup"
			payload = json.dumps(
				{
					"email": email,
					"first_name": first_name,
					"last_name": last_name,
					"password": password,
					"t_c_acceptance": t_c_acceptance,
					"organization_name": organization_name,
					"mobile": mobile,
					"erp_customer_id": erp_customer_id,
				}
			)
			headers = {"Content-Type": "application/json"}
			response = requests.request("POST", url, headers=headers, data=payload)
			return_data =response.json()
			if return_data.get("error"):
				return return_data.get("error")
			otp_doc.logged_in =1
			otp_doc.save(ignore_permissions=True)
			frappe.db.commit()
			return return_data
	else:
		return validate_otp.get("message")


@frappe.whitelist(allow_guest=True)
def login(email, password=None, otp=None):
	headers = {
		"Content-Type": "application/json",
	}
	url = f"{medusa_base_url}/store/login"
	if password:
		payload = json.dumps({"email": email, "password": password})
		response = requests.request("POST", url, headers=headers, data=payload)
		return response.json()
	elif otp:
		validate_otp = verify_otp(email=email, user_otp=otp)
		if validate_otp.get("otp_name"):
			otp_doc = frappe.get_doc("Email OTP", validate_otp.get("otp_name"))
			if otp_doc.logged_in and otp_doc.password:
				payload = json.dumps(
					{"email": email, "password": otp_doc.get_password("password")}
				)
				response = requests.request("POST", url, headers=headers, data=payload)
				return_data =response.json()
				if return_data.get("error"):
					return return_data.get("error")
				return return_data

			else:
				return "Please kindly register first"
		else:
			return validate_otp.get("message")
	else:
		return "Login Need Otp or Password"


@frappe.whitelist(allow_guest=True)
def send_otp(email,isLogin):
	otp = get_otp(email,isLogin)
	if otp in ["Please kindly register first", "Account with this mail already exists. Please login"]:
		return {"isSuccess": 0, "message": otp}
	
	subject = "Your OTP for Verification"
	message = (
		f"Your OTP for verification is: <b>{otp}</b>. This OTP is valid for 5 minutes."
	)

	try:
		frappe.sendmail(recipients=[email], subject=subject, message=message, now=True)
		frappe.db.commit()
		return {"message":"OTP sent successfully", "isSuccess": 1}
	except Exception as e:
		frappe.log_error(message=str(e), title="OTP Email Sending Failed")
		return {"message": "Failed to send OTP", "isSuccess": 0}


def get_otp(email,isLogin):

	existing_user = frappe.db.exists("Email OTP", {"email": email, "logged_in": 1})
	
	if existing_user and not isLogin:
		return "Account with this mail already exists. Please login"
	if not existing_user and isLogin:
		return "Please kindly register first"
	email_otp_name = frappe.db.get_value("Email OTP", {"email": email})
	expiration_time = add_to_date(now_datetime(), minutes=10)
	new_otp = random.randint(100000, 999999)
	otp = None
	
	if email_otp_name:
		otp = frappe.db.get_value(
			"Email OTP",
			{
				"name": email_otp_name,
				"status": "Pending",
				"expiration_time": [">", now_datetime()],
			},
			"otp",
		)
		if not otp:
			otp = new_otp
			frappe.db.set_value(
				"Email OTP",
				email_otp_name,
				{"expiration_time": expiration_time, "otp": otp, "status": "Pending"},
			)
	elif isLogin:
		return "Please kindly register first"
	else:
		otp = new_otp
		frappe.get_doc(
			{
				"doctype": "Email OTP",
				"email": email,
				"otp": otp,
				"expiration_time": expiration_time,
				"status": "Pending",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
	return otp


def verify_otp(email, user_otp):
	otp_record = (
		frappe.db.get_value(
			"Email OTP",
			{
				"email": email,
				"status": "Pending",
				"expiration_time": [">", now_datetime()],
				"otp": str(user_otp),
			},
		)
	) or None
	if not otp_record:
		return {"otp_name": None, "message": "Invalid OTP or email"}
	frappe.db.set_value("Email OTP",otp_record,"status","Verified")
	frappe.db.commit()
	return {"otp_name": otp_record, "message": "OTP verified successfully"}


def expire_otps():
	now = now_datetime()
	expired_otps = frappe.get_all(
		"Email OTP",
		filters={"status": "Pending", "expiration_time": ["<", now]},
		fields=["name"],
	)

	for otp in expired_otps:
		doc = frappe.get_doc("Email OTP", otp.name)
		doc.status = "Expired"
		doc.save(ignore_permissions=True)

def fetch_clearance_items():
	today = datetime.today().date()
	expiry_limit = today + timedelta(days=60)

	batches = frappe.get_all(
		"Batch",
		filters={
			"expiry_date": ["between", [today, expiry_limit]]
		},
		fields=["item"]
	)

	if not batches:
		return
	
	item_names = list(set(batch["item"] for batch in batches))

	website_items = frappe.get_all(
		"Website Item",
		filters={"item_code": ["in", item_names]},
		fields=["name"]
	)

	if not website_items:
		return
	
	doc = frappe.get_doc("Homepage Landing", "Active Homepage Landing")
	doc.clearance_items = []

	for item in website_items:
		doc.append("clearance_items", {"website_item": item.get("name")})
	
	doc.save()
	frappe.db.commit()
