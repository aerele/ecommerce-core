# Copyright (c) 2021, Frappe and Contributors
# See LICENSE

import frappe

try:
	from frappe.tests import IntegrationTestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from ecommerce_core.ecommerce_core.doctype.ecommerce_item import ecommerce_item

# `integration` links to Module Def; use this app's own module so the tests
# stand alone (the monolith-era INTEGRATION module does not exist here).
INTEGRATION = "Ecommerce Core"


class TestEcommerceItem(IntegrationTestCase):
	def tearDown(self):
		for d in frappe.get_list("Ecommerce Item"):
			frappe.get_doc("Ecommerce Item", d.name).delete()

	def test_duplicate(self):
		self._create_doc()
		self.assertRaises(frappe.DuplicateEntryError, self._create_doc)

	def test_duplicate_variants(self):
		self._create_variant_doc()
		self.assertRaises(frappe.DuplicateEntryError, self._create_variant_doc)

	def test_duplicate_sku(self):
		self._create_doc_with_sku()
		self.assertRaises(frappe.DuplicateEntryError, self._create_doc_with_sku)

	def test_is_synced(self):
		self._create_doc()
		self.assertTrue(ecommerce_item.is_synced(INTEGRATION, "T-SHIRT"))
		self.assertFalse(ecommerce_item.is_synced(INTEGRATION, "UNKNOWN ITEM"))

	def test_is_synced_variant(self):
		self._create_variant_doc()
		self.assertTrue(ecommerce_item.is_synced(INTEGRATION, "T-SHIRT", "T-SHIRT-RED"))
		self.assertFalse(ecommerce_item.is_synced(INTEGRATION, "T-SHIRT", "Unknown variant"))

	def test_is_synced_sku(self):
		self._create_doc_with_sku()
		self.assertTrue(ecommerce_item.is_synced(INTEGRATION, "T-SHIRT", sku="TEST_ITEM_1"))
		self.assertFalse(ecommerce_item.is_synced(INTEGRATION, "T-SHIRTX", sku="UNKNOWNSKU"))

	def test_get_erpnext_item(self):
		self._create_doc()
		a = ecommerce_item.get_erpnext_item(INTEGRATION, "T-SHIRT")
		b = frappe.get_doc("Item", "_Test Item")
		self.assertEqual(a.name, b.name)
		self.assertEqual(a.item_code, b.item_code)

		unknown = ecommerce_item.get_erpnext_item(INTEGRATION, "Unknown item")
		self.assertEqual(unknown, None)

	def test_get_erpnext_item_variant(self):
		self._create_variant_doc()
		a = ecommerce_item.get_erpnext_item(INTEGRATION, "T-SHIRT", "T-SHIRT-RED")
		b = frappe.get_doc("Item", "_Test Item 2")
		self.assertEqual(a.name, b.name)
		self.assertEqual(a.item_code, b.item_code)

	def test_same_sku_is_allowed_for_different_accounts(self):
		self._create_doc_with_sku_for_account("one.myshopify.com", "P1", "_Test Item")
		# the same SKU on another store maps to a different item
		self._create_doc_with_sku_for_account("two.myshopify.com", "P2", "_Test Item 2")

	def test_duplicate_sku_within_same_account(self):
		self._create_doc_with_sku_for_account("one.myshopify.com", "P1", "_Test Item")
		self.assertRaises(
			frappe.DuplicateEntryError,
			self._create_doc_with_sku_for_account,
			"one.myshopify.com",
			"P2",
			"_Test Item 2",
		)

	def test_is_synced_with_account_filters(self):
		self._create_doc_with_sku_for_account("one.myshopify.com", "P1", "_Test Item")

		self.assertTrue(
			ecommerce_item.is_synced(INTEGRATION, "P1", filters={"shopify_account": "one.myshopify.com"})
		)
		self.assertFalse(
			ecommerce_item.is_synced(INTEGRATION, "P1", filters={"shopify_account": "two.myshopify.com"})
		)

	def test_get_erpnext_item_code_with_account_filters(self):
		self._create_doc_with_sku_for_account("one.myshopify.com", "P1", "_Test Item")

		item_code = ecommerce_item.get_erpnext_item_code(
			INTEGRATION, "P1", filters={"shopify_account": "one.myshopify.com"}
		)
		self.assertEqual(item_code, "_Test Item")

		item_code = ecommerce_item.get_erpnext_item_code(
			INTEGRATION, "P1", filters={"shopify_account": "two.myshopify.com"}
		)
		self.assertEqual(item_code, None)

	def test_get_erpnext_item_sku(self):
		self._create_doc_with_sku()
		a = ecommerce_item.get_erpnext_item(INTEGRATION, "T-SHIRT", sku="TEST_ITEM_1")
		b = frappe.get_doc("Item", "_Test Item")
		self.assertEqual(a.name, b.name)
		self.assertEqual(a.item_code, b.item_code)

	def _create_doc(self):
		"""basic test for creation of ecommerce item"""
		frappe.get_doc(
			{
				"doctype": "Ecommerce Item",
				"integration": INTEGRATION,
				"integration_item_code": "T-SHIRT",
				"erpnext_item_code": "_Test Item",
			}
		).insert()

	def _create_variant_doc(self):
		"""basic test for creation of ecommerce item"""
		frappe.get_doc(
			{
				"doctype": "Ecommerce Item",
				"integration": INTEGRATION,
				"integration_item_code": "T-SHIRT",
				"erpnext_item_code": "_Test Item 2",
				"has_variants": 0,
				"variant_id": "T-SHIRT-RED",
				"variant_of": "_Test Variant Item",
			}
		).insert()

	def _create_doc_with_sku(self):
		frappe.get_doc(
			{
				"doctype": "Ecommerce Item",
				"integration": INTEGRATION,
				"integration_item_code": "T-SHIRT",
				"erpnext_item_code": "_Test Item",
				"sku": "TEST_ITEM_1",
			}
		).insert()

	def _create_doc_with_sku_for_account(self, account, product_id, item_code):
		frappe.get_doc(
			{
				"doctype": "Ecommerce Item",
				"integration": INTEGRATION,
				"integration_item_code": product_id,
				"erpnext_item_code": item_code,
				"sku": "SHARED-SKU",
				"shopify_account": account,
			}
		).insert(ignore_links=True)
