# Copyright (c) 2026, Frappe and Contributors
# See LICENSE

import unittest

import frappe
from frappe.utils import get_datetime

from ecommerce_core.controllers.scheduling import need_to_run

ACCOUNT = "sched-test.myshopify.com"


class TestNeedToRunPerDocument(unittest.TestCase):
	def setUp(self):
		if not frappe.db.exists("DocType", "Shopify Account"):
			raise unittest.SkipTest("needs the Shopify Account doctype")

		frappe.get_doc(
			{
				"doctype": "Shopify Account",
				"name": ACCOUNT,
				"shopify_url": ACCOUNT,
				"enable_shopify": 0,
				"is_old_data_migrated": 1,
				"inventory_sync_frequency": "60",
				"last_inventory_sync": get_datetime("1970-01-01"),
			}
		).db_insert()

	def tearDown(self):
		frappe.db.delete("Shopify Account", ACCOUNT)

	def test_need_to_run_reads_the_documents_own_interval(self):
		self.assertTrue(
			need_to_run(
				"Shopify Account", "inventory_sync_frequency", "last_inventory_sync", doc_name=ACCOUNT
			)
		)
		# the run above set the timestamp, so the interval has not elapsed yet
		self.assertFalse(
			need_to_run(
				"Shopify Account", "inventory_sync_frequency", "last_inventory_sync", doc_name=ACCOUNT
			)
		)
