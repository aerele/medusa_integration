frappe.ui.form.on('Customer', {
	refresh(frm) {
        frm.set_query("customer_primary_contact", function (doc) {
            console.log("yes");
			return {
				filters: {
					first_name: ["!=", ""]
				},
			};
		});
	}
})