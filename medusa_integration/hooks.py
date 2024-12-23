app_name = "medusa_integration"
app_title = "Medusa Integration"
app_publisher = "Aerele Technologies"
app_description = "Medusa Integration with ERP"
app_email = "hello@aerele.in"
app_license = "mit"
# required_apps = []

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/medusa_integration/css/medusa_integration.css"
# app_include_js = "/assets/medusa_integration/js/medusa_integration.js"

# include js, css files in header of web template
# web_include_css = "/assets/medusa_integration/css/medusa_integration.css"
# web_include_js = "/assets/medusa_integration/js/medusa_integration.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "medusa_integration/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {"Customer" : "public/js/customer.js"}

# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "medusa_integration/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "medusa_integration.utils.jinja_methods",
# 	"filters": "medusa_integration.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "medusa_integration.install.before_install"
# after_install = "medusa_integration.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "medusa_integration.uninstall.before_uninstall"
# after_uninstall = "medusa_integration.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "medusa_integration.utils.before_app_install"
# after_app_install = "medusa_integration.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "medusa_integration.utils.before_app_uninstall"
# after_app_uninstall = "medusa_integration.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "medusa_integration.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	# "Item": {
	# 	"validate": "medusa_integration.api.export_item"
	# },
	# "Item Group": {
	# 	"validate": "medusa_integration.api.create_medusa_collection"
	# },
	"Item Price": {
		"validate": "medusa_integration.api.create_medusa_price_list"
	},
	# "Customer": {
	# 	"validate": "medusa_integration.api.create_medusa_customer"
	# },
	"Website Item": {
		"validate": "medusa_integration.api.export_website_item"
	},
 	# "Brand": {
	# 	"validate": "medusa_integration.api.export_brand"
	# },
	"Quotation": {
        "on_update": "medusa_integration.api.export_quotation_on_update"
    },
	"Sales Order": {
        "on_update": "medusa_integration.api.export_sales_order_on_update"
    },
	# "File": {
	# 	"after_insert": "medusa_integration.api.file_validation_wrapper"
	# }
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"medusa_integration.tasks.all"
# 	],
# 	"daily": [
# 		"medusa_integration.tasks.daily"
# 	],
# 	"hourly": [
# 		"medusa_integration.tasks.hourly"
# 	],
# 	"weekly": [
# 		"medusa_integration.tasks.weekly"
# 	],
# 	"monthly": [
# 		"medusa_integration.tasks.monthly"
# 	],
# }

scheduler_events = {
    "cron": {
        "* * * * *": ["medusa_integration.api.send_quotation_emails",],
    }
}

# Testing
# -------

# before_tests = "medusa_integration.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "medusa_integration.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "medusa_integration.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["medusa_integration.utils.before_request"]
# after_request = ["medusa_integration.utils.after_request"]

# Job Events
# ----------
# before_job = ["medusa_integration.utils.before_job"]
# after_job = ["medusa_integration.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"medusa_integration.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

