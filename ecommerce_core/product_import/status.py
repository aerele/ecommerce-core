# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

"""Generic sync-status enrichment and statistics for the Product Sync page."""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Count, Min
from frappe.utils import cint

from ecommerce_core.dashboard.queries import like_pattern


def get_sync_status_map(
	integration: str, product_ids: list[str], account_filter: tuple[str, str] | None = None
) -> dict[str, dict]:
	"""Map provider product ids to their sync state in one batched query."""
	ids = [pid for pid in product_ids if pid]
	if not ids:
		return {}

	rows = frappe.get_all(
		"Ecommerce Item",
		filters=_with_account(
			{"integration": integration, "integration_item_code": ["in", ids]}, account_filter
		),
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
		existing_items = set(frappe.get_all("Item", filters={"name": ["in", list(item_codes)]}, pluck="name"))

	for entry in status_map.values():
		mapped = entry["erpnext_item_code"] in existing_items
		entry.update(
			{
				"synced": mapped,
				"sync_state": "synced" if mapped else "unsynced",
			}
		)
	return status_map


def attach_sync_status(
	integration: str, products: list[dict], account_filter: tuple[str, str] | None = None
) -> list[dict]:
	"""Attach synced/sync_state/erpnext_item_code/item_synced_on to provider rows."""
	products = products or []
	status_map = get_sync_status_map(integration, [p.get("id") for p in products], account_filter)

	for product in products:
		entry = status_map.get(product.get("id"))
		if entry:
			product.update(entry)
		else:
			product.update(
				{"synced": False, "sync_state": "unsynced", "erpnext_item_code": None, "item_synced_on": None}
			)
	return products


def get_stats(
	integration: str, provider_count: int | None = None, account_filter: tuple[str, str] | None = None
) -> dict:
	"""Generic Product Sync statistics for one integration."""
	mapped = _count_distinct_mapped(integration, account_filter)
	synced = _count_distinct_synced(integration, account_filter)

	return {
		"provider_count": provider_count,
		"mapped": mapped,
		"synced": synced,
	}


def list_mapped_products(
	integration: str,
	limit: int = 20,
	cursor: str | None = None,
	search: str | None = None,
	synced_only: bool = False,
	account_filter: tuple[str, str] | None = None,
) -> dict:
	"""Product listing built from Ecommerce Item mappings (no remote call)."""
	limit = cint(limit) or 20
	offset = _decode_offset_cursor(cursor)

	ei = frappe.qb.DocType("Ecommerce Item")
	item_dt = frappe.qb.DocType("Item")
	where = _account_where(ei, ei.integration == integration, account_filter)
	if synced_only:
		where = where & ei.erpnext_item_code.isin(frappe.qb.from_(item_dt).select(item_dt.name))
	if search:
		term = like_pattern(search)
		where = where & (
			ei.integration_item_code.like(term) | ei.sku.like(term) | ei.erpnext_item_code.like(term)
		)

	# One row per provider product (variants share integration_item_code), paged in SQL.
	total = _run_count(frappe.qb.from_(ei).where(where).select(Count(ei.integration_item_code).distinct()))
	page = (
		frappe.qb.from_(ei)
		.where(where)
		.groupby(ei.integration_item_code)
		.select(
			ei.integration_item_code,
			Min(ei.erpnext_item_code).as_("erpnext_item_code"),
			Min(ei.sku).as_("sku"),
		)
		.orderby(Min(ei.creation))
		.orderby(ei.integration_item_code)
		.limit(limit)
		.offset(offset)
		.run(as_dict=True)
	)

	items = frappe.get_all(
		"Item",
		filters={"name": ["in", [p.erpnext_item_code for p in page] or [""]]},
		fields=["name", "item_name"],
	)
	item_names = {item.name: item.item_name for item in items}

	# Variants share integration_item_code; list their SKUs for the popover.
	variant_rows = frappe.get_all(
		"Ecommerce Item",
		filters=_with_account(
			{
				"integration": integration,
				"integration_item_code": ["in", [p.integration_item_code for p in page] or [""]],
			},
			account_filter,
		),
		fields=["integration_item_code", "sku"],
	)
	variants: dict[str, list[dict]] = {}
	for row in variant_rows:
		if row.sku:
			variants.setdefault(row.integration_item_code, []).append({"sku": row.sku})

	return {
		"products": [
			{
				"id": p.integration_item_code,
				"name": item_names.get(p.erpnext_item_code) or p.erpnext_item_code,
				"sku": p.sku or "",
				"variants": variants.get(p.integration_item_code, []),
			}
			for p in page
		],
		"total": total,
		"next_cursor": f"o:{offset + limit}" if offset + limit < total else None,
	}


def _decode_offset_cursor(cursor: str | None) -> int:
	"""Decode an ``o:<offset>`` cursor into its offset; anything else means 0."""
	if not cursor or not str(cursor).startswith("o:"):
		return 0
	try:
		return max(int(str(cursor)[2:]), 0)
	except ValueError:
		return 0


def _with_account(filters: dict, account_filter: tuple[str, str] | None) -> dict:
	"""Add the ``(fieldname, value)`` store-account condition to a get_all filter dict."""
	if account_filter:
		filters[account_filter[0]] = account_filter[1]
	return filters


def _account_where(ei, where, account_filter: tuple[str, str] | None):
	"""AND the ``(fieldname, value)`` store-account condition onto a query-builder criterion."""
	if account_filter:
		where = where & (ei[account_filter[0]] == account_filter[1])
	return where


def _count_distinct_mapped(integration: str, account_filter: tuple[str, str] | None = None) -> int:
	"""Distinct provider products with an Ecommerce Item mapping (variants share one id)."""
	ei = frappe.qb.DocType("Ecommerce Item")
	query = (
		frappe.qb.from_(ei)
		.where(_account_where(ei, ei.integration == integration, account_filter))
		.select(Count(ei.integration_item_code).distinct())
	)
	return _run_count(query)


def _count_distinct_synced(integration: str, account_filter: tuple[str, str] | None = None) -> int:
	"""Distinct mapped provider products whose ERPNext Item exists."""
	ei = frappe.qb.DocType("Ecommerce Item")
	item = frappe.qb.DocType("Item")
	query = (
		frappe.qb.from_(ei)
		.join(item)
		.on(ei.erpnext_item_code == item.name)
		.where(_account_where(ei, ei.integration == integration, account_filter))
		.select(Count(ei.integration_item_code).distinct())
	)
	return _run_count(query)


def _run_count(query) -> int:
	"""Execute a pypika count query and return its first cell as an int (0 when empty)."""
	result = query.run()
	return cint(result[0][0]) if result else 0
