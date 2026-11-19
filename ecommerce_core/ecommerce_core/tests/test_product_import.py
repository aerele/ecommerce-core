# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

"""Regression tests for the shared Product Import engine."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from ecommerce_core.product_import import api as import_api
from ecommerce_core.product_import import runner
from ecommerce_core.product_import.registry import ProductImportProvider


def _stub_provider(integration="Stub", label="Stub", adapter=None):
	"""Real provider wrapper around a bare adapter, so per-account helpers behave as in production."""
	return ProductImportProvider(
		integration=integration, label=label, adapter_path="", adapter=adapter or object()
	)


class TestFilteredPagination(IntegrationTestCase):
	"""Filtered product listing must page through every match."""

	def test_envelope_keeps_positive_skip_without_adapter_cursor(self):
		"""A cursor-less adapter must not end pagination while matches remain."""
		token = import_api._encode_envelope(None, 7)
		self.assertIsNotNone(token)
		self.assertEqual(import_api._decode_envelope(token), (None, 7))
		self.assertIsNone(import_api._encode_envelope(None, 0))

	def test_first_provider_page_with_more_matches_than_limit(self):
		"""Filtering on the first page of a cursor-less adapter must offer a next page."""
		provider = _stub_provider("stub")
		page = {
			"total": 30,
			"products": [{"id": str(i)} for i in range(30)],
			"next_cursor": None,
		}
		with (
			patch.object(
				import_api.status,
				"attach_sync_status",
				side_effect=lambda integ, products, *_args, **_kw: [
					dict(p, sync_state="unsynced") for p in products
				],
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
	"""A sync run must stop once it no longer owns the lock."""

	def test_run_stops_when_the_lock_was_taken_over(self):
		"""A lost lock must stop the run instead of double-syncing."""
		provider = _stub_provider("stub")
		with patch.object(runner, "_refresh_lock", return_value=False):
			with self.assertRaises(frappe.exceptions.ValidationError):
				runner._require_lock(provider, "token")


class TestRetryWrapper(IntegrationTestCase):
	"""Input validation for the retry entry point."""

	def test_retry_rejects_payloads_without_integration(self):
		"""A retry payload without an integration must be rejected."""
		with self.assertRaises(frappe.exceptions.ValidationError):
			runner.retry_bulk_sync_job(payload=None, request_id="LOG-1")
		with self.assertRaises(frappe.exceptions.ValidationError):
			runner.retry_bulk_sync_job(payload={"search": None})


class TestLockRelease(IntegrationTestCase):
	"""Releasing the lock must only remove a lock owned by the caller."""

	def _provider(self):
		"""Stub provider with a unique lock key for this test."""
		return _stub_provider("Test Release Lock")

	def tearDown(self):
		"""Remove any lock left behind by the test."""
		frappe.cache.delete_value(runner._lock_key(self._provider()))

	def test_release_keeps_a_lock_owned_by_another_run(self):
		"""Releasing with a foreign token must keep the lock; the owner's token removes it."""
		provider = self._provider()
		token = runner._acquire_lock(provider)
		self.assertTrue(token)
		runner._release_lock(provider, "someone-else")
		self.assertTrue(frappe.cache.exists(runner._lock_key(provider)))
		runner._release_lock(provider, token)
		self.assertFalse(frappe.cache.exists(runner._lock_key(provider)))


class _EnabledAdapter:
	"""Enabled adapter stub; ``accounts`` makes it a multi-store provider."""

	def __init__(self, enabled=True, accounts=None):
		self._enabled = enabled
		self._accounts = accounts

	def is_enabled(self):
		return self._enabled

	def __getattr__(self, name):
		if name == "get_accounts" and self._accounts is not None:
			return lambda: [{"name": a, "label": a} for a in self._accounts]
		raise AttributeError(name)


class TestRetryReusesLog(IntegrationTestCase):
	"""Retry must reuse the original log and never leave it stuck in Queued."""

	def _make_log(self):
		"""Create a failed sync log to retry and return its name."""
		from ecommerce_core.utils.integration_log import create_integration_log

		log = create_integration_log(
			"Ecommerce Core",
			status="Error",
			message="boom",
			method=f"{runner.__name__}.retry_bulk_sync_job",
			make_new=True,
		)
		return log.name

	def test_retry_requeues_the_same_log(self):
		"""A successful retry must enqueue on the same log and mark it Queued."""
		log_name = self._make_log()
		provider = _stub_provider("Ecommerce Core", adapter=_EnabledAdapter())
		with (
			patch.object(runner, "get_provider", return_value=provider),
			patch.object(runner, "is_sync_running", return_value=False),
			patch.object(runner, "_acquire_lock", return_value="tok"),
			patch.object(runner.frappe, "enqueue") as enqueue,
		):
			runner.retry_bulk_sync_job(payload={"integration": "Ecommerce Core"}, request_id=log_name)

		self.assertEqual(enqueue.call_args.kwargs["log_name"], log_name)
		self.assertEqual(frappe.db.get_value("Ecommerce Integration Log", log_name, "status"), "Queued")

	def test_retry_while_busy_marks_log_error(self):
		"""A retry while a sync is running must mark the log as Error."""
		log_name = self._make_log()
		frappe.db.set_value("Ecommerce Integration Log", log_name, "status", "Queued")
		provider = _stub_provider("Ecommerce Core", adapter=_EnabledAdapter())
		with (
			patch.object(runner, "get_provider", return_value=provider),
			patch.object(runner, "is_sync_running", return_value=True),
		):
			runner.retry_bulk_sync_job(payload={"integration": "Ecommerce Core"}, request_id=log_name)

		status, message = frappe.db.get_value("Ecommerce Integration Log", log_name, ["status", "message"])
		self.assertEqual(status, "Error")
		self.assertIn("already running", message)

	def _retry_should_fail(self, provider, payload, expected):
		"""Assert the retry raises, enqueues nothing, and marks the log Error with ``expected``."""
		log_name = self._make_log()
		frappe.db.set_value("Ecommerce Integration Log", log_name, "status", "Queued")
		with (
			patch.object(runner, "get_provider", return_value=provider),
			patch.object(runner, "is_sync_running", return_value=False),
			patch.object(runner, "_acquire_lock", return_value="tok"),
			patch.object(runner.frappe, "enqueue") as enqueue,
		):
			with self.assertRaises(frappe.exceptions.ValidationError):
				runner.retry_bulk_sync_job(payload=payload, request_id=log_name)

		enqueue.assert_not_called()
		status, message = frappe.db.get_value("Ecommerce Integration Log", log_name, ["status", "message"])
		self.assertEqual(status, "Error")
		self.assertIn(expected, message)

	def test_retry_of_disabled_integration_marks_log_error(self):
		"""Retrying a disabled integration must fail and mark the log Error."""
		provider = _stub_provider("Ecommerce Core", adapter=_EnabledAdapter(enabled=False))
		self._retry_should_fail(provider, {"integration": "Ecommerce Core"}, "disabled")

	def test_retry_for_removed_store_marks_log_error(self):
		"""Retrying for a store that is no longer enabled must fail and mark the log Error."""
		provider = _stub_provider("Ecommerce Core", adapter=_EnabledAdapter(accounts=["a.example"]))
		payload = {"integration": "Ecommerce Core", "account": "gone.example"}
		self._retry_should_fail(provider, payload, "not an enabled")

	def test_retry_without_account_on_multi_store_marks_log_error(self):
		"""Retrying without a store when several stores exist must fail and mark the log Error."""
		provider = _stub_provider(
			"Ecommerce Core", adapter=_EnabledAdapter(accounts=["a.example", "b.example"])
		)
		self._retry_should_fail(provider, {"integration": "Ecommerce Core"}, "several stores")

	def test_retry_without_account_on_single_store_uses_that_store(self):
		"""Retrying without a store when only one store exists must use that store."""
		log_name = self._make_log()
		provider = _stub_provider("Ecommerce Core", adapter=_EnabledAdapter(accounts=["a.example"]))
		with (
			patch.object(runner, "get_provider", return_value=provider),
			patch.object(runner, "enqueue_sync_all", return_value={"log": log_name}) as sync_all,
		):
			runner.retry_bulk_sync_job(payload={"integration": "Ecommerce Core"}, request_id=log_name)

		self.assertEqual(sync_all.call_args.kwargs["account"], "a.example")
