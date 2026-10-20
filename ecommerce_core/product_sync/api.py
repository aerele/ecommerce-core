# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

"""Whitelisted API for the shared Product Sync Desk page.

All endpoints are System Manager only. Integration names map to adapters
exclusively through the server-side ``ecommerce_product_sync_providers`` hook
registry — no dotted paths are ever accepted from the client.
"""

from __future__ import annotations

import base64
import json

import frappe
from frappe import _
from frappe.utils import cint, cstr

from ecommerce_core.product_sync import runner, status
from ecommerce_core.product_sync.constants import (
	BULK_PAGE_SIZE,
	DEFAULT_PAGE_SIZE,
	FILTER_SCAN_PAGE_LIMIT,
	MAX_PAGE_SIZE,
	MAX_SELECTED_SYNC,
	SYNC_FILTERS,
)
from ecommerce_core.product_sync.registry import (
	ProductSyncProvider,
	get_provider,
	get_providers as get_registered_providers,
	get_rejected_providers,
)
from ecommerce_core.utils.integration_log import create_integration_log


@frappe.whitelist()
def get_providers() -> list[dict]:
	"""Registered Product Sync providers for the page's provider selector."""
	frappe.only_for("System Manager")
	return [provider.as_dict() for provider in get_registered_providers()]


@frappe.whitelist()
def get_provider_diagnostics() -> list[dict]:
	"""Hook entries that were rejected at load time, with the reason."""
	frappe.only_for("System Manager")
	return get_rejected_providers()


@frappe.whitelist()
def get_products(
	integration: str,
	limit: int = 20,
	cursor: str | None = None,
	search: str | None = None,
	sync_filter: str | None = None,
) -> dict:
	"""One page of provider products, enriched with generic sync status.

	``sync_filter`` (synced/unsynced/broken) is applied after enrichment, so it
	may shrink a page below ``limit``; the page size stays the provider's page.
	"""
	provider = _get_enabled_provider(integration)

	limit = cint(limit) or DEFAULT_PAGE_SIZE
	limit = min(max(limit, 1), MAX_PAGE_SIZE)

	if provider.can_list_products:
		if sync_filter in SYNC_FILTERS:
			# Sync-state filtering scans across catalog pages; total is the
			# provider's unfiltered count, so it is withheld in filtered mode.
			return _filtered_provider_page(provider, limit, cursor, search, sync_filter)
		result = _fetch_provider_page(provider, limit, cursor, search)
	else:
		result = status.list_mapped_products(provider.integration, limit=limit, cursor=cursor, search=search)

	products = status.attach_sync_status(provider.integration, result.get("products") or [])

	if sync_filter in SYNC_FILTERS:
		products = [p for p in products if p.get("sync_state") == sync_filter]

	return {
		"products": products,
		"total": result.get("total"),
		"next_cursor": result.get("next_cursor"),
		"limit": limit,
	}


def _fetch_provider_page(provider: ProductSyncProvider, limit: int, cursor: str | None, search: str | None) -> dict:
	"""Call the adapter listing, turning remote failures into a readable message."""
	try:
		return provider.adapter.get_products(limit=limit, cursor=cursor, search=search) or {}
	except Exception as e:
		frappe.log_error(title=f"Product Sync: {provider.label} listing failed")
		frappe.throw(
			_(
				"Could not fetch products from {0}. Check the connection settings and that the store is reachable. ({1})"
			).format(provider.label, _short_error(e)),
			title=_("{0} unreachable").format(provider.label),
		)


def _short_error(e: Exception) -> str:
	text = cstr(e).strip().splitlines()[0] if cstr(e).strip() else e.__class__.__name__
	return text[:160]


def _filtered_provider_page(
	provider: ProductSyncProvider, limit: int, cursor: str | None, search: str | None, sync_filter: str
) -> dict:
	"""Collect ``limit`` rows matching ``sync_filter`` across adapter pages.

	Without this, status filters would only apply within a single provider page
	and hide matches living on later pages. The returned cursor is an envelope
	wrapping the adapter cursor plus how many matches were already returned from
	that page, so pagination resumes exactly where the scan stopped.
	"""
	adapter_cursor, skip = _decode_envelope(cursor)
	collected: list[dict] = []
	total = None
	next_cursor = None

	for _ in range(FILTER_SCAN_PAGE_LIMIT):
		page = _fetch_provider_page(provider, BULK_PAGE_SIZE, adapter_cursor, search)
		if total is None:
			total = page.get("total")

		matches = [
			p
			for p in status.attach_sync_status(provider.integration, page.get("products") or [])
			if p.get("sync_state") == sync_filter
		]
		available = matches[skip:]
		take = available[: limit - len(collected)]
		collected.extend(take)

		if len(collected) >= limit:
			remaining_on_page = len(available) - len(take)
			if remaining_on_page > 0:
				# Page still has matches: resume on this very page.
				next_cursor = _encode_envelope(adapter_cursor, skip + len(take))
			else:
				next_cursor = _encode_envelope(page.get("next_cursor"), 0)
			break

		adapter_cursor = page.get("next_cursor")
		skip = 0
		if not adapter_cursor:
			break
	else:
		# Scan cap reached: continue scanning from the next unconsumed page.
		next_cursor = _encode_envelope(adapter_cursor, 0)

	return {"products": collected, "total": None, "next_cursor": next_cursor, "limit": limit}


def _encode_envelope(adapter_cursor: str | None, skip: int) -> str | None:
	if not adapter_cursor:
		return None
	payload = json.dumps({"c": adapter_cursor, "s": skip}, separators=(",", ":"))
	return "e:" + base64.b64encode(payload.encode()).decode()


def _decode_envelope(cursor: str | None) -> tuple[str | None, int]:
	if not cursor or not str(cursor).startswith("e:"):
		return cursor, 0
	try:
		data = json.loads(base64.b64decode(str(cursor)[2:]))
		return data.get("c"), max(int(data.get("s") or 0), 0)
	except Exception:
		return None, 0


@frappe.whitelist()
def get_stats(integration: str) -> dict:
	"""Generic sync statistics; provider count when the adapter can supply it."""
	provider = _get_provider(integration)

	provider_count = None
	if provider.enabled and provider.implements("get_provider_count"):
		try:
			provider_count = cint(provider.adapter.get_provider_count())
		except Exception:
			provider_count = None

	stats = status.get_stats(provider.integration, provider_count=provider_count)
	stats["enabled"] = provider.enabled
	return stats


@frappe.whitelist()
def sync_product(integration: str, product_id: str) -> dict:
	"""Sync or re-sync a single provider product through its adapter."""
	provider = _get_enabled_provider(integration)
	product_id = cstr(product_id).strip()
	if not product_id:
		frappe.throw(_("product_id is required"))

	try:
		result = provider.adapter.sync_product(product_id)
	except Exception as exc:
		create_integration_log(
			provider.integration,
			status="Failure",
			message=_("Product {0} sync failed").format(product_id),
			request_data={"product_id": product_id},
			exception=exc,
			rollback=True,
		)
		return {"ok": False, "error": str(exc)}

	return {"ok": True, **(result or {})}


@frappe.whitelist()
def sync_all(integration: str, search: str | None = None, sync_filter: str | None = None) -> dict:
	"""Queue a bulk product sync (generic runner or adapter-managed).

	``sync_filter`` limits the run to products in that sync state.
	"""
	provider = _get_enabled_provider(integration)
	return runner.enqueue_sync_all(
		provider, search=cstr(search).strip() or None, sync_filter=cstr(sync_filter).strip() or None
	)


@frappe.whitelist()
def sync_selected(integration: str, product_ids: str | list, labels: str | dict | None = None) -> dict:
	"""Queue a bulk sync restricted to the selected provider products."""
	provider = _get_enabled_provider(integration)

	if isinstance(product_ids, str):
		product_ids = json.loads(product_ids)
	if not isinstance(product_ids, list):
		frappe.throw(_("product_ids must be a list of product ids"))

	product_ids = [pid.strip() for pid in product_ids if cstr(pid).strip()]
	if not product_ids:
		frappe.throw(_("Select at least one product to sync."))
	if len(product_ids) > MAX_SELECTED_SYNC:
		frappe.throw(_("You can sync at most {0} products at a time.").format(MAX_SELECTED_SYNC))

	names = _validate_labels(labels, product_ids)

	return runner.enqueue_sync_selected(provider, product_ids, labels=names)


def _validate_labels(labels: str | dict | None, product_ids: list[str]) -> dict[str, str]:
	"""Keep only display names for the selected ids, length-capped."""
	if labels is None:
		return {}
	if isinstance(labels, str):
		labels = json.loads(labels)
	if not isinstance(labels, dict):
		frappe.throw(_("labels must be a map of product id to name"))

	names = {cstr(k).strip(): cstr(v).strip()[:140] for k, v in labels.items() if cstr(k).strip()}
	return {pid: names[pid] for pid in product_ids if pid in names}


@frappe.whitelist()
def get_sync_status(integration: str) -> dict:
	provider = _get_provider(integration)
	return {
		"running": runner.is_sync_running(provider),
		"enabled": provider.enabled,
		"event": provider.event_name,
	}


def _get_provider(integration: str) -> ProductSyncProvider:
	frappe.only_for("System Manager")
	return get_provider(integration)


def _get_enabled_provider(integration: str) -> ProductSyncProvider:
	provider = _get_provider(integration)
	if not provider.enabled:
		if provider.settings_doctype:
			frappe.throw(_("{0} is disabled. Enable it in {1}.").format(provider.label, _(provider.settings_doctype)))
		frappe.throw(_("{0} is disabled.").format(provider.label))
	return provider
