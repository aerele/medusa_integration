frappe.ui.form.on('Customer', {
	refresh(frm) {
		frm.set_query("customer_primary_contact", () => {
			return { filters: { first_name: ["!=", ""] } };
		});

		if (!frm.is_new() && !frm.doc.medusa_id) {
			frm.add_custom_button(__("Link Medusa Lead"), () => {
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
				get_query() {
					return {
						filters: [["medusa_id", "!=", ""]]
					};
				}
			}
		],
		primary_action_label: __("Link"),
		primary_action(data) {
			if (!data.lead) {
				frappe.msgprint("Please select a lead");
				return;
			}

			frappe.confirm(
				__("Once linked, this Lead cannot be unlinked. Do you want to proceed?"),
				() => {
					frappe.call({
						method: "medusa_integration.utils.link_medusa_lead",
						args: {
							customer: frm.doc.name,
							lead: data.lead
						},
						freeze: true,
						callback(r) {
							if (!r.exc) {
								frappe.msgprint("Medusa Lead linked successfully");
								frm.reload_doc();
								d.hide();
							}
						}
					});
				}
			);
		}
	});

	d.show();
}
