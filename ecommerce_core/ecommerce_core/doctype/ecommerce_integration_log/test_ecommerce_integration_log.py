# Copyright (c) 2021, Frappe and Contributors
# See LICENSE

# import frappe
try:
	from frappe.tests import IntegrationTestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase


class TestEcommerceIntegrationLog(IntegrationTestCase):
	pass
