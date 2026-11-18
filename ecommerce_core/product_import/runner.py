# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

"""Bulk product sync runner for the shared Product Sync page."""

from __future__ import annotations

import random
from datetime import timezone
from itertools import count
from time import monotonic, sleep

import frappe
import requests
from frappe import _
from frappe.utils import escape_html, get_datetime
from frappe.utils.data import convert_utc_to_system_timezone

from ecommerce_core.dashboard.queries import invalidate_dashboard_cache
from ecommerce_core.product_import import status
from ecommerce_core.product_import.constants import (
	BULK_PAGE_SIZE,
	BULK_SYNC_QUEUE,
	BULK_SYNC_TIMEOUT,
	MAX_FAILED_IDS,
	PROGRESS_THROTTLE_SECONDS,
	SYNC_FILTERS,
)
from ecommerce_core.product_import.registry import ProductImportProvider, get_provider
from ecommerce_core.utils.integration_log import create_integration_log

_savepoint_counter = count()


class ProgressPublisher:
	"""Publishes realtime progress lines to the triggering user's console."""

	def __init__(self, event: str, user: str | None = None) -> None:
		"""Bind the publisher to a realtime event, optionally scoped to one user."""
		self.event = event
		self.user = user
		self._last_sent = 0.0
		self._suppressed = 0

	def immediate(self, message: str, **flags) -> None:
		"""Publish right away (errors, start/summary lines), flushing any throttled backlog first."""
		self._flush_suppressed()
		publish(self.event, message, user=self.user, **flags)
		self._last_sent = monotonic()

	def throttled(self, message: str, **flags) -> None:
		"""Publish per-product lines, but drop ones within PROGRESS_THROTTLE_SECONDS of the last."""
		if monotonic() - self._last_sent < PROGRESS_THROTTLE_SECONDS:
			self._suppressed += 1
			return
		self.immediate(message, **flags)

	def _flush_suppressed(self) -> None:
		"""Send one "... N more products processed" line summarizing throttled messages."""
		if not self._suppressed:
			return
		count_ = self._suppressed
		self._suppressed = 0
		publish(self.event, _("… {0} more products processed").format(count_), user=self.user)


def publish(event: str, message: str, *, user: str | None = None, **flags) -> None:
	"""Publish one realtime progress line, HTML-escaping the message."""
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


LOCK_TTL_SECONDS = 180
LOCK_QUEUED_TTL_SECONDS = 300  # grace for a job waiting in the queue


def _lock_key(provider: ProductImportProvider) -> str:
	"""Redis cache key of the per-provider bulk-run lock (one per job name)."""
	return f"ecommerce_product_import_lock:{provider.job_name}"


def _acquire_lock(provider: ProductImportProvider) -> str | None:
	"""Atomically claim the per-provider bulk run slot (SET NX with expiry)."""
	token = frappe.generate_hash(length=16)
	key = frappe.cache.make_key(_lock_key(provider))
	if frappe.cache.set(  # nosemgrep: frappe-semgrep-rules.rules.frappe-cache-breaks-multitenancy
		name=key, value=token, nx=True, ex=LOCK_QUEUED_TTL_SECONDS
	):
		return token
	return None


def _lock_owner(provider: ProductImportProvider) -> str | None:
	"""Current owner token of the provider's lock, or None when free/expired."""
	value = frappe.cache.get(  # nosemgrep: frappe-semgrep-rules.rules.frappe-cache-breaks-multitenancy
		frappe.cache.make_key(_lock_key(provider))
	)
	if isinstance(value, bytes):
		value = value.decode()
	return value


def _refresh_lock(provider: ProductImportProvider, token: str | None = None) -> None:
	"""Heartbeat: keep the lock alive while the job runs. A killed worker stops
	refreshing, so its lock expires within LOCK_TTL_SECONDS instead of ~1 hour."""
	if token is None:
		return
	owner = _lock_owner(provider)
	# An expired key (owner None) is restored so a long queue wait or slow adapter call
	# does not let a second run start; a key held by someone else is never touched.
	if owner not in (token, None):
		return
	key = frappe.cache.make_key(_lock_key(provider))
	frappe.cache.set(  # nosemgrep: frappe-semgrep-rules.rules.frappe-cache-breaks-multitenancy
		name=key, value=token, ex=LOCK_TTL_SECONDS
	)


def _release_lock(provider: ProductImportProvider, token: str | None = None) -> None:
	"""Delete the lock; only the token's owner (or an absent owner) may do so."""
	# Only the owner may release; an expired lock re-claimed by another run stays.
	if token is not None and _lock_owner(provider) not in (token, None):
		return
	frappe.cache.delete_value(_lock_key(provider))
	# A finished run changes mappings and logs the dashboard aggregates are built from.
	invalidate_dashboard_cache()


def is_sync_running(provider: ProductImportProvider) -> bool:
	"""True when a bulk sync is in flight: the adapter's own status if it manages one, else our lock."""
	if provider.implements("get_sync_status"):
		return bool((provider.adapter.get_sync_status() or {}).get("running"))

	return bool(frappe.cache.exists(frappe.cache.make_key(_lock_key(provider))))


def enqueue_sync_all(
	provider: ProductImportProvider,
	search: str | None = None,
	sync_filter: str | None = None,
	force_full: bool = False,
) -> dict:
	"""Start a full-catalog bulk sync; returns job metadata for the page."""
	sync_filter = sync_filter if sync_filter in SYNC_FILTERS else None

	if provider.has_custom_bulk_sync:
		if is_sync_running(provider):
			return {"status": "Busy", "message": _("A product sync is already running.")}
		result = provider.adapter.sync_all(search=search) or {}
		return {"event": provider.event_name, **result}

	return _enqueue_bulk(
		provider,
		log_message=_("Bulk product sync queued"),
		request_data={"search": search, "sync_filter": sync_filter, "force_full": force_full},
		search=search,
		sync_filter=sync_filter,
		force_full=force_full,
		user=frappe.session.user,
	)


def enqueue_sync_selected(
	provider: ProductImportProvider, product_ids: list[str], labels: dict[str, str] | None = None
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
	provider: ProductImportProvider,
	*,
	log_message: str,
	request_data,
	search: str | None = None,
	sync_filter: str | None = None,
	product_ids: list[str] | None = None,
	labels: dict[str, str] | None = None,
	user: str | None = None,
	force_full: bool = False,
) -> dict:
	"""Claim the lock, create the Queued log and enqueue the bulk job."""
	if is_sync_running(provider):
		return {"status": "Busy", "message": _("A product sync is already running.")}
	lock_token = _acquire_lock(provider)
	if not lock_token:
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
			force_full=force_full,
			lock_token=lock_token,
		)
	except Exception:
		_release_lock(provider, lock_token)
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
	force_full: bool = False,
	lock_token: str | None = None,
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

	counts = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "unchanged": 0}
	failed_ids: list[str] = []
	start = monotonic()

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
					lock_token,
				)
		else:
			cursor = None
			incremental = provider.supports_incremental and not force_full
			while True:
				_refresh_lock(provider, lock_token)
				page = _fetch_products_page_with_retry(provider, cursor, search)
				products = page.get("products") or []
				products = _select_products(provider, products, sync_filter, incremental, counts)

				for index, product in enumerate(products):
					product_id = product.get("id") if isinstance(product, dict) else product
					if not product_id:
						counts["skipped"] += 1
						continue

					label = product.get("name") or product_id if isinstance(product, dict) else product_id
					_sync_single_product(
						provider, publisher, product_id, label, index, counts, failed_ids, lock_token
					)

				cursor = page.get("next_cursor")
				if not cursor:
					break

				# Commit between catalog pages so a long sync does not hold one
				# transaction open for the whole catalog (same pattern as the
				# connector runners this page replaces).
				frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit

		elapsed = monotonic() - start
		summary = {
			"created": counts["created"],
			"updated": counts["updated"],
			"skipped": counts["skipped"],
			"failed": counts["failed"],
			"unchanged": counts["unchanged"],
			"failed_ids": failed_ids[:MAX_FAILED_IDS],
		}
		status_label = (
			"Success"
			if counts["failed"] == 0
			else ("Partial Success" if counts["created"] + counts["updated"] else "Failed")
		)
		message = _(
			"Bulk sync completed in {0}s (Created={1}, Updated={2}, Skipped={3}, Unchanged={5}, Failed={4})"
		).format(
			f"{elapsed:.1f}",
			counts["created"],
			counts["updated"],
			counts["skipped"],
			counts["failed"],
			counts["unchanged"],
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
			f"Unchanged: {counts['unchanged']}\n"
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
		_release_lock(provider, lock_token)


def _sync_single_product(
	provider: ProductImportProvider,
	publisher: ProgressPublisher,
	product_id: str,
	label: str,
	index: int,
	counts: dict,
	failed_ids: list[str],
	lock_token: str | None = None,
) -> None:
	"""Sync one product inside a savepoint and log the outcome per product."""
	savepoint = f"ecommerce_product_import_{next(_savepoint_counter)}"
	_refresh_lock(provider, lock_token)
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
		if len(failed_ids) < MAX_FAILED_IDS:
			failed_ids.append(product_id)
		publisher.immediate(f"✗ {label}: {exc}", error=True)


FETCH_RETRIES = 3
FETCH_BACKOFF_SECONDS = 2.0


def _retry_delay(exc: Exception, attempt: int) -> float:
	"""Honour Retry-After on 429s, otherwise exponential backoff with jitter."""
	response = getattr(exc, "response", None)
	headers = getattr(response, "headers", None) or {}
	try:
		retry_after = float(headers.get("Retry-After"))
	except (TypeError, ValueError):
		retry_after = 0.0
	return min(max(retry_after, FETCH_BACKOFF_SECONDS * (2**attempt)) + random.random(), 60.0)


def _is_transient(exc: Exception) -> bool:
	"""True for failures worth retrying: network trouble, 429 and 5xx. Programming and
	validation errors (and other 4xx) are deterministic, so they surface immediately."""
	status_code = getattr(getattr(exc, "response", None), "status_code", None)
	if status_code:
		return status_code == 429 or status_code >= 500
	return isinstance(
		exc,
		requests.exceptions.ConnectionError | requests.exceptions.Timeout | ConnectionError | TimeoutError,
	)


def _fetch_products_page_with_retry(
	provider: ProductImportProvider, cursor: str | None = None, search: str | None = None
) -> dict:
	"""Fetch one catalog page, retrying transient remote failures with backoff so a
	single 429/5xx does not abort an hours-long run."""
	for attempt in range(FETCH_RETRIES + 1):
		try:
			return _fetch_products_page(provider, cursor=cursor, search=search)
		except Exception as exc:
			if attempt >= FETCH_RETRIES or not _is_transient(exc):
				raise
			sleep(_retry_delay(exc, attempt))
	return {}


def _fetch_products_page(
	provider: ProductImportProvider, cursor: str | None = None, search: str | None = None
) -> dict:
	"""One catalog page via the adapter, or the mapped-items fallback when it cannot list."""
	if provider.can_list_products:
		return provider.adapter.get_products(limit=BULK_PAGE_SIZE, cursor=cursor, search=search) or {}

	# No provider listing: iterate the generic mapped-items view instead.
	return status.list_mapped_products(
		provider.integration, limit=BULK_PAGE_SIZE, cursor=cursor, search=search
	)


def _select_products(
	provider: ProductImportProvider,
	products: list,
	sync_filter: str | None,
	incremental: bool,
	counts: dict,
) -> list:
	"""Apply the page's sync filter and the incremental skip with one status lookup."""
	if not (sync_filter or incremental) or not products:
		return products

	rows = status.attach_sync_status(provider.integration, [p for p in products if isinstance(p, dict)])
	selected = []
	for product in rows:
		if sync_filter and product.get("sync_state") != sync_filter:
			continue
		if incremental and _is_unchanged(provider, product):
			counts["unchanged"] += 1
			continue
		selected.append(product)
	return selected


def _is_unchanged(provider: ProductImportProvider, product: dict) -> bool:
	"""True when the product was synced and the remote has not changed since."""
	synced_on = product.get("item_synced_on")
	if product.get("sync_state") != "synced" or not synced_on:
		return False
	try:
		remote = provider.adapter.get_product_updated_at(product)
	except Exception:
		return False  # unknown remote time: sync to be safe
	if not remote:
		return False
	remote_dt = get_datetime(remote)
	if remote_dt.tzinfo:
		# item_synced_on is stored naive in the system timezone
		remote_dt = convert_utc_to_system_timezone(remote_dt.astimezone(timezone.utc)).replace(tzinfo=None)
	return remote_dt <= get_datetime(synced_on)
