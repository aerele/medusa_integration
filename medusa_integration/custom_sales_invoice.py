import frappe
from frappe import _, bold, throw
from frappe.utils import flt, get_link_to_form

from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

class CustomSalesInvoice(SalesInvoice):	
	def validate_selling_price(self):
		if self.from_ecommerce:
			return

		def throw_message(idx, item_name, rate, ref_rate_field):
			throw(
				_(
					"""Row #{0}: Selling rate for item {1} is lower than its {2}.
					Selling {3} should be atleast {4}.<br><br>Alternatively,
					you can disable selling price validation in {5} to bypass
					this validation."""
				).format(
					idx,
					bold(item_name),
					bold(ref_rate_field),
					bold("net rate"),
					bold(rate),
					get_link_to_form("Selling Settings", "Selling Settings"),
				),
				title=_("Invalid Selling Price"),
			)

		if self.get("is_return") or not frappe.db.get_single_value(
			"Selling Settings", "validate_selling_price"
		):
			return

		is_internal_customer = self.get("is_internal_customer")
		valuation_rate_map = {}

		for item in self.items:
			if not item.item_code or item.is_free_item:
				continue

			last_purchase_rate, is_stock_item = frappe.get_cached_value(
				"Item", item.item_code, ("last_purchase_rate", "is_stock_item")
			)

			last_purchase_rate_in_sales_uom = last_purchase_rate * (item.conversion_factor or 1)

			if flt(item.base_net_rate) < flt(last_purchase_rate_in_sales_uom):
				throw_message(item.idx, item.item_name, last_purchase_rate_in_sales_uom, "last purchase rate")

			if is_internal_customer or not is_stock_item:
				continue

			valuation_rate_map[(item.item_code, item.warehouse)] = None

		if not valuation_rate_map:
			return

		or_conditions = (
			f"""(item_code = {frappe.db.escape(valuation_rate[0])}
			and warehouse = {frappe.db.escape(valuation_rate[1])})"""
			for valuation_rate in valuation_rate_map
		)

		valuation_rates = frappe.db.sql(
			f"""
			select
				item_code, warehouse, valuation_rate
			from
				`tabBin`
			where
				({" or ".join(or_conditions)})
				and valuation_rate > 0
		""",
			as_dict=True,
		)

		for rate in valuation_rates:
			valuation_rate_map[(rate.item_code, rate.warehouse)] = rate.valuation_rate

		for item in self.items:
			if not item.item_code or item.is_free_item:
				continue

			last_valuation_rate = valuation_rate_map.get((item.item_code, item.warehouse))

			if not last_valuation_rate:
				continue

			last_valuation_rate_in_sales_uom = last_valuation_rate * (item.conversion_factor or 1)

			if flt(item.base_net_rate) < flt(last_valuation_rate_in_sales_uom):
				throw_message(
					item.idx,
					item.item_name,
					last_valuation_rate_in_sales_uom,
					"valuation rate (Moving Average)",
				)
