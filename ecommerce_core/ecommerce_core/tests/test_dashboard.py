# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

"""Tests for the shared Ecommerce Dashboard API and query helpers."""

import frappe
from frappe.tests import IntegrationTestCase

from ecommerce_core.dashboard import api, queries


class TestDashboardQueries(IntegrationTestCase):
	def test_like_pattern_escapes_wildcards(self):
		self.assertEqual(queries.like_pattern("50%_off"), "%50\\%\\_off%")

	def test_existing_fields_skip_unknown_columns(self):
		self.assertEqual(queries._existing_fields("Sales Order", [("no_such_field", "Label")]), [])
		self.assertIn(
			("customer_name", "Customer"),
			queries._existing_fields("Sales Order", [("customer_name", "Customer")]),
		)

	def test_row_details_carry_keys_and_drop_empty_values(self):
		order = frappe._dict(customer_name="Ravi", blank="")
		details = queries._row_details(order, [("customer_name", "Customer"), ("blank", "Blank")], None, [])
		self.assertEqual(details, [{"key": "customer_name", "label": "Customer", "value": "Ravi"}])

	def test_detail_facts_carry_keys_and_drop_empty_values(self):
		row = frappe._dict(customer_name="Ravi", blank="")
		facts = queries._detail_facts(row, [("customer_name", "Customer"), ("blank", "Blank")])
		self.assertEqual(facts, [{"key": "customer_name", "label": "Customer", "value": "Ravi"}])


class TestDashboardAPI(IntegrationTestCase):
	def test_parse_filters(self):
		self.assertIsNone(api._parse_filters(None))
		self.assertIsNone(api._parse_filters("not json"))
		self.assertEqual(api._parse_filters('{"channel": "CUSTOM"}'), {"channel": "CUSTOM"})
		self.assertIsNone(api._parse_filters('{"channel": ""}'))

	def test_get_summary_shape(self):
		summary = api.get_summary()
		self.assertIn("providers", summary)
		self.assertIn("problems", summary)
		for key in ("registered", "enabled", "mapped_items", "failed_syncs"):
			self.assertIn(key, summary["tiles"])

	def test_get_section_shapes(self):
		for section in ("orders", "payments", "items", "logs"):
			data = api.get_section(section)
			self.assertIsInstance(data["rows"], list)
			self.assertIsInstance(data["total"], int)

	def test_orders_section_declares_connector_columns_and_filters(self):
		data = api.get_section("orders")
		self.assertIn("columns", data)
		self.assertIn("filter_options", data)
		for column in data["columns"]:
			self.assertTrue(column.get("key"))
			self.assertTrue(column.get("label"))

	def test_unknown_section_is_rejected(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			api.get_section("no-such-section")

	def _mapping_provider(self, integration="acme", item_field="no_such_field"):
		from ecommerce_core.dashboard.adapter import DashboardAdapter
		from ecommerce_core.dashboard.registry import Provider

		class Mapping(DashboardAdapter):
			def is_enabled(self):
				return True

			def get_order_filter_options(self):
				return [{"key": "shop", "label": "Shop", "options": [("a", "a")]}]

			def get_filter_field_map(self):
				return {"shop": {"Sales Order": "customer_name", "Ecommerce Item": item_field}}

		provider = Provider(integration=integration, label="Acme", settings_doctype=None)
		provider.adapter = Mapping()
		provider.enabled = True
		return provider

	def test_filter_map_columns_skip_fields_the_doctype_lacks(self):
		provider = self._mapping_provider()
		self.assertEqual(
			api._filter_map_columns(provider, "Sales Order"),
			[{"key": "customer_name", "label": "Shop"}],
		)
		self.assertEqual(api._filter_map_columns(provider, "Ecommerce Item"), [])

	def test_summary_tile_filters_and_clause_follow_the_field_map(self):
		from ecommerce_core.dashboard.registry import Registry

		provider = self._mapping_provider(item_field="integration")
		registry = Registry(providers=[provider])

		self.assertEqual(api._summary_tile_filters(registry, "acme", '{"shop": "a"}'), {"shop": "a"})
		# Undeclared keys and the combined view carry no tile filters.
		self.assertIsNone(api._summary_tile_filters(registry, "acme", '{"other": "x"}'))
		self.assertIsNone(api._summary_tile_filters(registry, None, '{"shop": "a"}'))

		ecom = frappe.qb.DocType("Ecommerce Item")
		clause = api._tile_filter_clause(registry, "acme", {"shop": "a"}, "Ecommerce Item", ecom)
		self.assertIsNotNone(clause)
		# A doctype the map doesn't cover gets no clause.
		self.assertIsNone(
			api._tile_filter_clause(registry, "acme", {"shop": "a"}, "Item", frappe.qb.DocType("Item"))
		)

	def test_broken_warehouse_config_is_reported_not_hidden(self):
		from ecommerce_core.dashboard.registry import Provider, Registry

		broken = Provider(
			integration="brokenco",
			label="BrokenCo",
			settings_doctype="DocType That Does Not Exist",
		)
		registry = Registry(providers=[broken])

		# Unreadable settings: no warehouses are trusted (empty list, not all warehouses).
		self.assertEqual(api._warehouses(broken), [])
		problems = api._warehouse_problems(registry, None)
		self.assertTrue(any("BrokenCo" in problem for problem in problems))

		# A provider without settings still means all warehouses on purpose.
		plain = Provider(integration="plainco", label="PlainCo", settings_doctype=None)
		self.assertIsNone(api._warehouses(plain))

	def test_combined_view_keeps_only_filters_common_to_every_provider(self):
		from ecommerce_core.dashboard.registry import Provider

		unicommerce = Provider(integration="unicommerce", label="Unicommerce", settings_doctype=None)
		shopify = Provider(integration="shopify", label="Shopify", settings_doctype=None)
		channel_filter = [{"key": "channel", "label": "Channel", "options": [("CUSTOM", "CUSTOM")]}]

		declared = [(unicommerce, channel_filter)]
		# A provider that declares nothing makes nothing common in the combined view.
		self.assertEqual(api._common_filter_options(declared, ["unicommerce", "shopify"]), [])
		# A single-provider scope keeps that provider's own filters.
		options = api._common_filter_options(declared, ["unicommerce"])
		self.assertEqual([option["key"] for option in options], ["channel"])
		# When both declare the same key it stays common, with merged option values.
		declared = [
			(unicommerce, channel_filter),
			(shopify, [{"key": "channel", "label": "Channel", "options": [("WEB", "WEB")]}]),
		]
		options = api._common_filter_options(declared, ["unicommerce", "shopify"])
		self.assertEqual([option["key"] for option in options], ["channel"])
		self.assertEqual(options[0]["options"], [("CUSTOM", "CUSTOM"), ("WEB", "WEB")])

	def test_combined_view_keeps_only_columns_common_to_every_provider(self):
		from ecommerce_core.dashboard.registry import Provider

		unicommerce = Provider(integration="unicommerce", label="Unicommerce", settings_doctype=None)
		shopify = Provider(integration="shopify", label="Shopify", settings_doctype=None)
		uni_columns = [
			{"key": "channel", "label": "Channel"},
			{"key": "tracking", "label": "Tracking Number"},
		]

		declared = [(unicommerce, uni_columns)]
		# A provider that declares nothing leaves no common column in the combined view.
		self.assertEqual(api._common_order_columns(declared, ["unicommerce", "shopify"]), [])
		# A single-provider scope keeps that provider's own columns.
		self.assertEqual(
			[key["key"] for key in api._common_order_columns(declared, ["unicommerce"])],
			["channel", "tracking"],
		)
		# A key both providers declare stays common.
		declared = [
			(unicommerce, uni_columns),
			(shopify, [{"key": "channel", "label": "Channel"}]),
		]
		self.assertEqual(
			[key["key"] for key in api._common_order_columns(declared, ["unicommerce", "shopify"])],
			["channel"],
		)
