frappe.ui.form.on('Customer', {
	refresh: function (frm) {
		frm.set_query("customer_primary_contact", function (doc) {
			console.log("yes");
			return {
				filters: {
					first_name: ["!=", ""]
				},
			};
		});
		if (!frm.is_new() && !frm.doc.medusa_id) {
			frm.add_custom_button(__("Link Medusa Lead"), function () {
				open_link_medusa_lead_dialog(frm);
			});
		}
	}
})

function open_link_medusa_lead_dialog(frm) {
	let d = new frappe.ui.Dialog({
		title: __("Link Medusa Lead"),
		fields: [
			{
				label: __("Lead"),
				fieldname: "lead",
				fieldtype: "Link",
				options: "Lead",
				reqd: 1,
				get_query: function () {
					return {
						filters: [["medusa_id", "!=", ""]]
					};
				}
			}
		],
		primary_action_label: __("Link"),
		primary_action: function (data) {
			if (!data.lead) {
				frappe.msgprint(__("Please select a lead"));
				return;
			}

			frappe.db.get_value("Lead", data.lead, "medusa_id")
				.then(r => {
					let medusa_id = r.message.medusa_id;
					if (!medusa_id) {
						frappe.msgprint(__("Selected Lead does not have a Medusa ID"));
						return;
					}

					frappe.db.get_list("Customer", {
						filters: {
							medusa_id: medusa_id,
							name: ["!=", frm.doc.name]
						},
						fields: ["name"],
						limit: 1
					}).then(customers => {
						if (customers.length > 0) {
							frappe.throw(__("This Medusa Lead is already linked to another Customer: {0}", [customers[0].name]));
						} else {
							frm.set_value("medusa_id", medusa_id);
							frm.set_value("lead_name", data.lead);
							frm.save();
							frappe.msgprint(__("Medusa Lead linked successfully"));
							d.hide();
						}
					});
				});
		}
	});

	d.show();
}
