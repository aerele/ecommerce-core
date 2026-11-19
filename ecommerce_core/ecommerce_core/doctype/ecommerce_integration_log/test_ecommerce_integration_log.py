# Copyright (c) 2021, Frappe and Contributors
# See LICENSE

from unittest.mock import patch

import frappe

try:
	from frappe.tests import IntegrationTestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from ecommerce_core.ecommerce_core.doctype.ecommerce_integration_log.ecommerce_integration_log import (
	create_log,
)


class TestEcommerceIntegrationLog(IntegrationTestCase):
	def test_create_log_sets_extra_fields(self):
		# create_log commits; keep the log inside the test transaction
		with patch.object(frappe.db, "commit"):
			log = create_log(
				module_def="Ecommerce Core",
				status="Success",
				make_new=True,
				fields={"method": "custom.method"},
			)

		self.assertEqual(log.method, "custom.method")
