frappe.ui.form.on('Website Item', {
	refresh: function (frm) {
		frm.set_query("custom_parent_website_item", function () {
			return {
				filters: {
					has_variants: 1
				}
			};
		});
	}
});
