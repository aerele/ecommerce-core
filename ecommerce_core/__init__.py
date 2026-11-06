__version__ = "0.0.1"

import frappe


def check_app_permission():
	# Matches the Product Sync API, which is System Manager only.
	return "System Manager" in frappe.get_roles()
