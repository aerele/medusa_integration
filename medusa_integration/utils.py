import frappe,json,requests,random,string
from frappe import _
from medusa_integration.constants import get_headers


def generate_random_string(length=26):
	characters = string.ascii_uppercase + string.digits
	random_string = ''.join(random.choice(characters) for _ in range(length))
	return random_string


def create_response_log(log_details):
	log = frappe.get_doc({
					"doctype": "Medusa Request Log",
					"status": log_details.status,
					"payload": json.dumps(log_details.get("payload"), indent=4) or "",
					"voucher_type": log_details.get("voucher_type"),
					"voucher_name": log_details.get("voucher_name"),
					"response": json.dumps(log_details.get("response"), indent=4) if isinstance(log_details.get("response"), dict) else json.dumps({"response":log_details.get("response")}),
	}).insert(ignore_permissions=True)
	frappe.db.commit()
	return log.name

def send_request(args):
	response = requests.request(args.method, args.url, headers=args.headers, data=args.payload)
	if response.ok:
		data = frappe._dict(json.loads(response.text))
	if response.text == "Unauthorized":
		response = requests.request(args.method, args.url, headers=get_headers(with_token=True,expired=True), data=args.payload)
		if response.ok:
			data = frappe._dict(json.loads(response.text))
	create_response_log(frappe._dict({
							"status": "Success" if response.ok else "Failure",
							"payload": args.payload,
							"voucher_type": args.get("voucher_type") or "",
							"voucher_name": args.get("voucher_name") or "",
							"response": json.loads(response.text) if response.ok else response.text,
	}))

	if response.ok:
		return data

	else:
		frappe.throw(args.get("throw_message") or response.text)

@frappe.whitelist()
def link_medusa_lead(customer, lead):
	customer_doc = frappe.get_doc("Customer", customer)

	original_name = customer_doc.customer_name

	lead_doc = frappe.get_doc("Lead", lead)
	if not lead_doc:
		frappe.throw(_("Lead does not exist"))

	if not lead_doc.medusa_id:
		frappe.throw(_("Selected Lead does not have a Medusa ID"))

	medusa_id = lead_doc.medusa_id

	exists = frappe.db.exists(
		"Customer",
		{"medusa_id": medusa_id, "name": ("!=", customer)}
	)

	if exists:
		frappe.throw(
			_("This Medusa Lead is already linked to another Customer: {0}")
			.format(exists)
		)

	customer_doc.medusa_id = medusa_id
	customer_doc.lead_name = lead

	customer_doc.customer_name = original_name

	customer_doc.save(ignore_permissions=True)

	return {"status": "success"}
