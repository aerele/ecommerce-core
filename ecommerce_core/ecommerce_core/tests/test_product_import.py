# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

"""Regression tests for the shared Product Import engine."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from ecommerce_core.product_import import api as import_api
from ecommerce_core.product_import import runner


class TestFilteredPagination(IntegrationTestCase):
	def test_envelope_keeps_positive_skip_without_adapter_cursor(self):
		"""A cursor-less adapter must not end pagination while matches remain."""
		token = import_api._encode_envelope(None, 7)
		self.assertIsNotNone(token)
		self.assertEqual(import_api._decode_envelope(token), (None, 7))
		self.assertIsNone(import_api._encode_envelope(None, 0))

	def test_first_provider_page_with_more_matches_than_limit(self):
		"""Filtering on the first page of a cursor-less adapter must offer a next page."""
		from types import SimpleNamespace

		provider = SimpleNamespace(integration="stub")
		page = {
			"total": 30,
			"products": [{"id": str(i)} for i in range(30)],
			"next_cursor": None,
		}
		with (
			patch.object(
				import_api.status,
				"attach_sync_status",
				side_effect=lambda integ, products: [dict(p, sync_state="unsynced") for p in products],
			),
			patch.object(import_api, "_fetch_provider_page", return_value=page),
		):
			first = import_api._filtered_provider_page(provider, 10, None, None, "unsynced")
			second = import_api._filtered_provider_page(provider, 10, first["next_cursor"], None, "unsynced")
			third = import_api._filtered_provider_page(provider, 10, second["next_cursor"], None, "unsynced")

		self.assertEqual([p["id"] for p in first["products"]], [str(i) for i in range(0, 10)])
		self.assertIsNotNone(first["next_cursor"])
		self.assertEqual([p["id"] for p in second["products"]], [str(i) for i in range(10, 20)])
		self.assertEqual([p["id"] for p in third["products"]], [str(i) for i in range(20, 30)])
		self.assertIsNone(third["next_cursor"])


class TestLockOwnership(IntegrationTestCase):
	def test_run_stops_when_the_lock_was_taken_over(self):
		"""A lost lock must stop the run instead of double-syncing."""
		from types import SimpleNamespace

		provider = SimpleNamespace(label="Stub", integration="stub")
		with patch.object(runner, "_refresh_lock", return_value=False):
			with self.assertRaises(frappe.exceptions.ValidationError):
				runner._require_lock(provider, "token")


class TestRetryWrapper(IntegrationTestCase):
	def test_retry_rejects_payloads_without_integration(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			runner.retry_bulk_sync_job(payload=None, request_id="LOG-1")
		with self.assertRaises(frappe.exceptions.ValidationError):
			runner.retry_bulk_sync_job(payload={"search": None})
