# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

"""Bulk product sync runner for the shared Product Sync page.

Sync All and Sync Selected share one runner and one job name per provider, so
only one bulk operation can run at a time:

- Sync All — walks the provider catalog page by page (or the mapped-items view
  when the adapter cannot list) and syncs every product.
- Sync Selected — syncs exactly the product ids the user picked.
- Custom — the adapter implements ``sync_all(search=None)`` and manages its own
  job and log; the runner only guards against duplicate runs and passes through.

Every run calls ``adapter.sync_product()`` per product inside a savepoint,
counts outcomes, records one Ecommerce Integration Log, and streams a
per-product trail over realtime events (one line per product, matching the
Medusa connector's progress format).
"""

from __future__ import annotations

from itertools import count
from time import monotonic, process_time

import frappe
from frappe import _
from frappe.utils import escape_html

from ecommerce_core.product_sync import status
from ecommerce_core.product_sync.constants import (
	BULK_PAGE_SIZE,
	BULK_SYNC_QUEUE,
	BULK_SYNC_TIMEOUT,
	PROGRESS_THROTTLE_SECONDS,
	SYNC_FILTERS,
)
from ecommerce_core.product_sync.registry import ProductSyncProvider, get_provider
from ecommerce_core.utils.integration_log import create_integration_log


_savepoint_counter = count()


class ProgressPublisher:
	"""Publishes realtime progress lines to the triggering user's console.

	Per-product lines are throttled so a large catalog does not flood the socket;
	errors, the start line and the final summary are always sent immediately.
	"""

	def __init__(self, event: str, user: str | None = None) -> None:
		self.event = event
		self.user = user
		self._last_sent = 0.0
		self._suppressed = 0

	def immediate(self, message: str, **flags) -> None:
		self._flush_suppressed()
		publish(self.event, message, user=self.user, **flags)
		self._last_sent = monotonic()

	def throttled(self, message: str, **flags) -> None:
		if monotonic() - self._last_sent < PROGRESS_THROTTLE_SECONDS:
			self._suppressed += 1
			return
		self.immediate(message, **flags)

	def _flush_suppressed(self) -> None:
		if not self._suppressed:
			return
		count_ = self._suppressed
		self._suppressed = 0
		publish(self.event, _("… {0} more products processed").format(count_), user=self.user)


def publish(event: str, message: str, *, user: str | None = None, **flags) -> None:
	# Messages carry remote product names and exception text, so escape them
	# before the page renders them as HTML.
	frappe.publish_realtime(
		event,
		{
			"message": escape_html(message) + ("<br /><br />" if flags.pop("br", True) else "<br />"),
			**flags,
		},
		user=user,
	)


def _lock_key(provider: ProductSyncProvider) -> str:
	return f"ecommerce_product_sync_lock:{provider.job_name}"


def _acquire_lock(provider: ProductSyncProvider) -> bool:
	"""Atomically claim the per-provider bulk run slot (SET NX with expiry)."""
	key = frappe.cache.make_key(_lock_key(provider))
	return bool(frappe.cache.set(name=key, value=1, nx=True, ex=BULK_SYNC_TIMEOUT + 60))


def _release_lock(provider: ProductSyncProvider) -> None:
	frappe.cache.delete_value(_lock_key(provider))


def is_sync_running(provider: ProductSyncProvider) -> bool:
	if provider.implements("get_sync_status"):
		return bool((provider.adapter.get_sync_status() or {}).get("running"))

	return bool(frappe.cache.exists(frappe.cache.make_key(_lock_key(provider))))


def enqueue_sync_all(
	provider: ProductSyncProvider, search: str | None = None, sync_filter: str | None = None
) -> dict:
	"""Start a full-catalog bulk sync; returns job metadata for the page.

	``sync_filter`` (synced/unsynced/broken) restricts the run to products in that
	state, matching the filter active on the page.
	"""
	sync_filter = sync_filter if sync_filter in SYNC_FILTERS else None

	if provider.has_custom_bulk_sync:
		if is_sync_running(provider):
			return {"status": "Busy", "message": _("A product sync is already running.")}
		result = provider.adapter.sync_all(search=search) or {}
		return {"event": provider.event_name, **result}

	return _enqueue_bulk(
		provider,
		log_message=_("Bulk product sync queued"),
		request_data={"search": search, "sync_filter": sync_filter},
		search=search,
		sync_filter=sync_filter,
		user=frappe.session.user,
	)


def enqueue_sync_selected(
	provider: ProductSyncProvider, product_ids: list[str], labels: dict[str, str] | None = None
) -> dict:
	"""Start a bulk sync restricted to the given product ids."""
	return _enqueue_bulk(
		provider,
		log_message=_("Selected product sync queued"),
		request_data={"product_ids": product_ids},
		product_ids=product_ids,
		labels=labels,
		user=frappe.session.user,
	)


def _enqueue_bulk(
	provider: ProductSyncProvider,
	*,
	log_message: str,
	request_data,
	search: str | None = None,
	sync_filter: str | None = None,
	product_ids: list[str] | None = None,
	labels: dict[str, str] | None = None,
	user: str | None = None,
) -> dict:
	if is_sync_running(provider) or not _acquire_lock(provider):
		return {"status": "Busy", "message": _("A product sync is already running.")}

	try:
		log = create_integration_log(
			provider.integration,
			status="Queued",
			method=f"{__name__}.run_bulk_sync_job",
			message=log_message,
			request_data=request_data,
		)

		frappe.enqueue(
			run_bulk_sync_job,
			queue=BULK_SYNC_QUEUE,
			timeout=BULK_SYNC_TIMEOUT,
			job_name=provider.job_name,
			enqueue_after_commit=True,
			integration=provider.integration,
			log_name=log.name,
			search=search,
			sync_filter=sync_filter,
			product_ids=product_ids,
			labels=labels,
			user=user,
		)
	except Exception:
		_release_lock(provider)
		raise

	return {"status": "Queued", "log": log.name, "event": provider.event_name, "job_name": provider.job_name}


def run_bulk_sync_job(
	integration: str,
	log_name: str | None = None,
	search: str | None = None,
	product_ids: list[str] | None = None,
	labels: dict[str, str] | None = None,
	user: str | None = None,
	sync_filter: str | None = None,
) -> dict:
	"""Background worker: sync either the selected products or the full catalog."""
	provider = get_provider(integration)
	publisher = ProgressPublisher(provider.event_name, user=user)
	selected = [pid for pid in (product_ids or []) if pid]
	labels = labels or {}

	previous_request_id = getattr(frappe.flags, "request_id", None)
	if log_name:
		# Bind create_integration_log calls to the log created at enqueue time.
		frappe.flags.request_id = log_name

	counts = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}
	failed_ids: list[str] = []
	start = process_time()

	try:
		start_message = (
			_("Selected product sync started ({0} products)").format(len(selected))
			if selected
			else _("Bulk product sync started")
		)
		create_integration_log(provider.integration, status="Running", message=start_message)
		publisher.immediate(_("Starting synchronization..."))

		if selected:
			for index, product_id in enumerate(selected):
				_sync_single_product(
					provider,
					publisher,
					product_id,
					labels.get(product_id) or product_id,
					index,
					counts,
					failed_ids,
				)
		else:
			cursor = None
			while True:
				page = _fetch_products_page(provider, cursor=cursor, search=search)
				products = page.get("products") or []
				if sync_filter:
					products = [
						p
						for p in status.attach_sync_status(provider.integration, products)
						if p.get("sync_state") == sync_filter
					]

				for index, product in enumerate(products):
					product_id = product.get("id") if isinstance(product, dict) else product
					if not product_id:
						counts["skipped"] += 1
						continue

					label = product.get("name") or product_id if isinstance(product, dict) else product_id
					_sync_single_product(provider, publisher, product_id, label, index, counts, failed_ids)

				cursor = page.get("next_cursor")
				if not cursor:
					break

				# Commit between catalog pages so a long sync does not hold one
				# transaction open for the whole catalog (same pattern as the
				# connector runners this page replaces).
				frappe.db.commit()  # nosemgrep: frappe-no-commit

		elapsed = process_time() - start
		summary = {
			"created": counts["created"],
			"updated": counts["updated"],
			"skipped": counts["skipped"],
			"failed": counts["failed"],
			"failed_ids": failed_ids,
		}
		status_label = "Success" if counts["failed"] == 0 else (
			"Partial Success" if counts["created"] + counts["updated"] else "Failed"
		)
		message = _("Bulk sync completed in {0}s (Created={1}, Updated={2}, Skipped={3}, Failed={4})").format(
			f"{elapsed:.1f}",
			counts["created"],
			counts["updated"],
			counts["skipped"],
			counts["failed"],
		)

		create_integration_log(
			provider.integration,
			status=status_label,
			message=message,
			response_data=summary,
		)
		publisher.immediate(
			"Synchronization completed\n\n"
			f"Duration : {elapsed:.1f}s\n"
			f"Created  : {counts['created']}\n"
			f"Updated  : {counts['updated']}\n"
			f"Skipped  : {counts['skipped']}\n"
			f"Failed   : {counts['failed']}",
			done=True,
		)
		return {"status": status_label, **summary}

	except Exception as exc:
		create_integration_log(
			provider.integration,
			status="Failed",
			message=str(exc),
			exception=exc,
		)
		publisher.immediate(f"✗ Sync aborted: {exc}", error=True, done=True)
		raise
	finally:
		frappe.flags.request_id = previous_request_id
		_release_lock(provider)


def _sync_single_product(
	provider: ProductSyncProvider,
	publisher: ProgressPublisher,
	product_id: str,
	label: str,
	index: int,
	counts: dict,
	failed_ids: list[str],
) -> None:
	"""Sync one product inside a savepoint and log the outcome per product."""
	savepoint = f"ecommerce_product_sync_{next(_savepoint_counter)}"
	try:
		frappe.db.savepoint(savepoint)
		result = provider.adapter.sync_product(product_id)
		action = result.get("action") if isinstance(result, dict) else None
		item_code = result.get("item_code") if isinstance(result, dict) else None
		suffix = f" (Item: {item_code})" if item_code else ""

		if action == "created":
			counts["created"] += 1
			publisher.throttled(f"✓ {label} — created{suffix}")
		elif action == "updated":
			counts["updated"] += 1
			publisher.throttled(f"✓ {label} — updated{suffix}")
		else:
			counts["skipped"] += 1
			publisher.throttled(f"– {label} — skipped")
		frappe.db.release_savepoint(savepoint)
	except Exception as exc:
		frappe.db.rollback(save_point=savepoint)
		counts["failed"] += 1
		failed_ids.append(product_id)
		publisher.immediate(f"✗ {label}: {exc}", error=True)


def _fetch_products_page(
	provider: ProductSyncProvider, cursor: str | None = None, search: str | None = None
) -> dict:
	if provider.can_list_products:
		return provider.adapter.get_products(limit=BULK_PAGE_SIZE, cursor=cursor, search=search) or {}

	# No provider listing: iterate the generic mapped-items view instead.
	return status.list_mapped_products(provider.integration, limit=BULK_PAGE_SIZE, cursor=cursor, search=search)
