from . import __version__ as app_version

app_name = "ecommerce_core"
app_title = "Ecommerce Core"
app_publisher = "Aerele"
app_description = "Shared core for ERPNext ecommerce integration apps (Unicommerce, Shopify, ...)"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "developers@aerele.in"
app_license = "GNU GPL v3.0"
required_apps = ["frappe/erpnext"]
app_logo_url = "/assets/ecommerce_core/images/ecommerce-core.png"
app_home = "/desk/ecommerce-core"

# Shown on Desk home (same pattern as ERPNext / India Compliance)
add_to_apps_screen = [
	{
		"name": app_name,
		"logo": app_logo_url,
		"title": app_title,
		"route": app_home,
		"has_permission": "ecommerce_core.check_app_permission",
	}
]

# Includes in <head>
# ------------------

# generic ecommerce transaction helpers, shown on any integration's Sales Order / Invoice
doctype_js = {
	"Sales Order": "public/js/common/ecommerce_transactions.js",
	"Sales Invoice": "public/js/common/ecommerce_transactions.js",
}

# Installation
# ------------

before_uninstall = "ecommerce_core.uninstall.before_uninstall"

# Document Events
# ---------------
# Common guards used by every integration (ignore dummy tax template / price list).

doc_events = {
	"Item": {
		"validate": "ecommerce_core.utils.taxation.validate_tax_template",
	},
	"Item Price": {"on_change": "ecommerce_core.utils.price_list.discard_item_prices"},
}

# Testing
# -------

before_tests = "ecommerce_core.utils.before_test.before_tests"

# Log clearing
# ------------

default_log_clearing_doctypes = {
	"Ecommerce Integration Log": 120,
}
