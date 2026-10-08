# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

"""Generic sync-status enrichment and statistics for the Product Sync page.

Sync state is derived entirely from Ecommerce Core data (the ``Ecommerce Item``
mapping joined against ``Item``), so every provider gets identical semantics:

- ``synced``   — a mapping exists and the mapped ERPNext Item exists
- ``broken``   — a mapping exists but the mapped ERPNext Item is gone
- ``unsynced`` — no mapping for the provider product
"""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Count
from frappe.utils import cint


def get_sync_status_map(integration: str, product_ids: list[str]) -> dict[str, dict]:
	"""Map provider product ids to their sync state in one batched query."""
	ids = [pid for pid in product_ids if pid]
	if not ids:
		return {}

	rows = frappe.get_all(
		"Ecommerce Item",
		filters={"integration": integration, "integration_item_code": ["in", ids]},
		fields=["integration_item_code", "erpnext_item_code", "has_variants", "item_synced_on"],
		order_by="has_variants desc, creation asc",
	)

	status_map: dict[str, dict] = {}
	item_codes: set[str] = set()
	for row in rows:
		entry = status_map.setdefault(
			row.integration_item_code,
			{"erpnext_item_code": row.erpnext_item_code, "item_synced_on": row.item_synced_on},
		)
		item_codes.add(entry["erpnext_item_code"])

	existing_items = set()
	if item_codes:
		existing_items = set(
			frappe.get_all("Item", filters={"name": ["in", list(item_codes)]}, pluck="name")
		)

	for product_id, entry in status_map.items():
		mapped = entry["erpnext_item_code"] in existing_items
		entry.update(
			{
				"synced": mapped,
				"sync_state": "synced" if mapped else "broken",
			}
		)
	return status_map


def attach_sync_status(integration: str, products: list[dict]) -> list[dict]:
	"""Attach synced/sync_state/erpnext_item_code/item_synced_on to provider rows."""
	products = products or []
	status_map = get_sync_status_map(integration, [p.get("id") for p in products])

	for product in products:
		entry = status_map.get(product.get("id"))
		if entry:
			product.update(entry)
		else:
			product.update(
				{"synced": False, "sync_state": "unsynced", "erpnext_item_code": None, "item_synced_on": None}
			)
	return products


def get_stats(integration: str, provider_count: int | None = None) -> dict:
	"""Generic Product Sync statistics for one integration."""
	mapped = _count_distinct_mapped(integration)
	broken = _count_distinct_broken(integration)

	return {
		"provider_count": provider_count,
		"mapped": mapped,
		"synced": max(mapped - broken, 0),
	}


def list_mapped_products(
	integration: str, limit: int = 20, cursor: str | None = None, search: str | None = None
) -> dict:
	"""Fallback product listing built from Ecommerce Item mappings.

	Used when a provider adapter does not implement ``get_products``. Cursors are
	opaque ``o:<offset>`` tokens, matching the adapter contract's cursor semantics.
	"""
	limit = cint(limit) or 20
	offset = _decode_offset_cursor(cursor)

	or_filters = []
	if search:
		term = f"%{search.strip()}%"
		or_filters = [
			["Ecommerce Item", "integration_item_code", "like", term],
			["Ecommerce Item", "sku", "like", term],
			["Ecommerce Item", "erpnext_item_code", "like", term],
		]

	filters = {"integration": integration}
	rows = frappe.get_all(
		"Ecommerce Item",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "integration_item_code", "erpnext_item_code", "sku"],
		order_by="creation asc",
	)

	# De-duplicate provider products: variants share integration_item_code rows.
	by_product: dict[str, dict] = {}
	for row in rows:
		by_product.setdefault(row.integration_item_code, row)

	products = list(by_product.values())
	total = len(products)
	page = products[offset : offset + limit]

	items = frappe.get_all(
		"Item",
		filters={"name": ["in", [p.erpnext_item_code for p in page] or [""]]},
		fields=["name", "item_name"],
	)
	item_names = {item.name: item.item_name for item in items}

	return {
		"products": [
			{
				"id": p.integration_item_code,
				"name": item_names.get(p.erpnext_item_code) or p.erpnext_item_code,
				"sku": p.sku or "",
			}
			for p in page
		],
		"total": total,
		"next_cursor": f"o:{offset + limit}" if offset + limit < total else None,
	}


def _decode_offset_cursor(cursor: str | None) -> int:
	if not cursor or not str(cursor).startswith("o:"):
		return 0
	try:
		return max(int(str(cursor)[2:]), 0)
	except ValueError:
		return 0


def _count_distinct_mapped(integration: str) -> int:
	ei = frappe.qb.DocType("Ecommerce Item")
	query = (
		frappe.qb.from_(ei)
		.where(ei.integration == integration)
		.select(Count(ei.integration_item_code).distinct())
	)
	return _run_count(query)


def _count_distinct_broken(integration: str) -> int:
	ei = frappe.qb.DocType("Ecommerce Item")
	item = frappe.qb.DocType("Item")
	query = (
		frappe.qb.from_(ei)
		.left_join(item)
		.on(ei.erpnext_item_code == item.name)
		.where((ei.integration == integration) & (item.name.isnull()))
		.select(Count(ei.integration_item_code).distinct())
	)
	return _run_count(query)


def _run_count(query) -> int:
	result = query.run()
	return cint(result[0][0]) if result else 0
