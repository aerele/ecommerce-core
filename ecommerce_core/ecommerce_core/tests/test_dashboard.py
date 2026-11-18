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
