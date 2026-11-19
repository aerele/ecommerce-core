"""Whitelisted endpoints behind the Ecommerce Dashboard page (System Manager only)."""

import hashlib
import json
from datetime import date, datetime

import frappe
from frappe import _
from frappe.query_builder import DocType, Order
from frappe.query_builder.functions import Count, IfNull, Sum
from frappe.utils import add_days, cint, cstr, now_datetime
from frappe.utils.nestedset import get_descendants_of
from pypika import Case

from ecommerce_core.dashboard.queries import cache_key_for, like_pattern
from ecommerce_core.dashboard.registry import Provider, Registry, call_adapter, load_registry

MAX_PAGE_SIZE = 50
MAX_MERGE_ROWS = 500
ITEM_ROWS_TTL_SECONDS = 60
LOG_COUNTS_TTL_SECONDS = 30
IN_CHUNK_SIZE = 1000

LOG_GROUPS = {
	"success": ("Success",),
	"failed": ("Error", "Failure"),
	"partial": ("Partial Success",),
	"queued": ("Queued",),
}
STOCK_ORDER = {"out": 0, "low": 1, "in": 2, "na": 3}


@frappe.whitelist(methods=["GET"])
def get_summary(integration: str | None = None, filters: str | None = None) -> dict:
	"""Provider tabs, stat tiles and adapter problems for the selected view."""
	frappe.only_for("System Manager")
	registry = load_registry()
	integration = integration or None
	problems = list(registry.problems)
	problems += _warehouse_problems(registry, integration)
	scoped = registry.scoped(integration)
	problems += [p.problem for p in scoped if p.problem]

	tile_filters = _summary_tile_filters(registry, integration, filters)

	integrations = _integrations_in_scope(registry, integration)
	ecom_item = DocType("Ecommerce Item")
	item_scope = (ecom_item.integration.isin(integrations)) & (ecom_item.has_variants == 0)
	item_clause = _tile_filter_clause(registry, integration, tile_filters, "Ecommerce Item", ecom_item)
	if item_clause is not None:
		item_scope = item_scope & item_clause
	mapped = (
		frappe.qb.from_(ecom_item).select(Count("*")).where(item_scope).run()[0][0] if integrations else 0
	)
	synced = (
		frappe.qb.from_(ecom_item)
		.select(Count("*"))
		.where(item_scope & (ecom_item.inventory_synced_on >= add_days(now_datetime(), -1)))
		.run()[0][0]
		if integrations
		else 0
	)

	log = DocType("Ecommerce Integration Log")
	failed_query = (
		frappe.qb.from_(log)
		.select(Count("*"))
		.where(log.status.isin(LOG_GROUPS["failed"]) & (log.creation >= add_days(now_datetime(), -7)))
	)
	if integration:
		failed_query = failed_query.where(log.integration == integration)
	log_clause = _tile_filter_clause(registry, integration, tile_filters, "Ecommerce Integration Log", log)
	if log_clause is not None:
		failed_query = failed_query.where(log_clause)
	failed = failed_query.run()[0][0]

	pending: dict[str, dict] = {}
	pending_kwargs = {"filters": tile_filters} if tile_filters else {}
	for provider in registry.active(integration, "get_pending_summary"):
		for row in call_adapter(provider, "get_pending_summary", problems, [], **pending_kwargs):
			entry = pending.setdefault(
				row["currency"], {"currency": row["currency"], "amount": 0, "count": 0}
			)
			entry["amount"] += row["amount"] or 0
			entry["count"] += row["count"] or 0

	stock_counts = {"out": 0, "low": 0}
	for integ in integrations:
		counts = _items_counts_sql(integ, registry.get(integ), tile_filters)
		stock_counts["out"] += counts.get("out", 0)
		stock_counts["low"] += counts.get("low", 0)

	return {
		"providers": [p.as_dict() for p in registry.providers],
		"problems": problems,
		"tiles": {
			"registered": len(scoped),
			"enabled": sum(1 for p in scoped if p.enabled),
			"mapped_items": mapped,
			"synced_items": synced,
			"failed_syncs": failed,
			"pending": sorted(pending.values(), key=lambda d: -d["count"]),
			"stock_out": stock_counts["out"],
			"stock_low": stock_counts["low"],
		},
	}


@frappe.whitelist(methods=["GET"])
def get_section(
	section: str,
	integration: str | None = None,
	search: str | None = None,
	status: str | None = None,
	page: int = 1,
	page_size: int = 10,
	filters: str | None = None,
) -> dict:
	"""One paginated widget: orders, payments, items or logs."""
	frappe.only_for("System Manager")
	page = max(1, cint(page))
	page_size = min(max(1, cint(page_size)), MAX_PAGE_SIZE)
	integration = integration or None
	search = (search or "").strip()[:140] or None
	status = status or None
	extra_filters = _parse_filters(filters)

	if section not in ("orders", "payments", "items", "logs"):
		frappe.throw(_("Unknown dashboard section: {0}").format(section))

	registry = load_registry()
	if section == "orders":
		return _orders_section(registry, integration, search, status, page, page_size, extra_filters)
	handler = {"payments": _payments_section, "items": _items_section, "logs": _logs_section}[section]
	return handler(registry, integration, search, status, page, page_size, extra_filters)


@frappe.whitelist(methods=["POST"])
def push_stock(ecommerce_item: str) -> str:
	"""Ask the item's connector to push its current stock."""
	frappe.only_for("System Manager")
	integration = frappe.db.get_value("Ecommerce Item", ecommerce_item, "integration")
	if not integration:
		frappe.throw(_("Ecommerce Item {0} not found").format(ecommerce_item))

	provider = load_registry().get(integration)
	if not provider or not provider.enabled or not provider.adapter.implements("push_inventory"):
		frappe.throw(_("{0} does not support pushing stock from the dashboard.").format(integration))
	if _warehouses(provider) == []:
		frappe.throw(
			_("{0} has no valid warehouse configuration; fix it before pushing stock.").format(integration)
		)
	return provider.adapter.push_inventory([ecommerce_item])


# ----- sections -----


def _merged(
	registry: Registry,
	integration: str | None,
	fetch: str,
	count: str,
	search: str | None,
	status: str | None,
	page: int,
	page_size: int,
	problems: list[str],
	providers: list[Provider] | None = None,
	filters: dict[str, str] | None = None,
) -> tuple[list[dict], int]:
	"""Merge rows from every active adapter, newest first, and slice one page."""
	start = (page - 1) * page_size
	need = min(page * page_size, MAX_MERGE_ROWS)
	call_kwargs = {"search": search, "status": status}
	if filters:
		call_kwargs["filters"] = filters

	rows, total = [], 0
	active = providers if providers is not None else registry.active(integration, fetch)
	for provider in active:
		fetched = call_adapter(provider, fetch, problems, [], limit=need, **call_kwargs)
		for row in fetched:
			row["integration"] = provider.integration
			row["platform"] = provider.label
		rows += fetched
		if provider.adapter.implements(count):
			total += call_adapter(provider, count, problems, len(fetched), **call_kwargs)
		else:
			total += len(fetched)

	rows.sort(key=lambda r: _created_key(r.get("created")), reverse=True)
	if total > MAX_MERGE_ROWS:
		problems.append(
			_(
				"Combined view lists only the newest {0} records of {1}. Pick one integration or narrow the search to go deeper."
			).format(MAX_MERGE_ROWS, total)
		)
	return rows[start : min(start + page_size, MAX_MERGE_ROWS)], total


def _created_key(value) -> str:
	"""Sortable key for mixed datetime / ISO-string timestamps."""
	if not value:
		return ""
	if isinstance(value, datetime):
		return value.isoformat(sep=" ")
	if isinstance(value, date):
		return value.isoformat() + " 00:00:00"
	return str(value).replace("T", " ")


def _orders_section(registry, integration, search, status, page, page_size, filters=None):
	"""Merged recent-orders rows across providers, plus totals, problems, columns and filters."""
	problems = []
	provider_filters = _provider_order_filters(registry, integration, problems)
	active_integrations = [p.integration for p in registry.active(integration, "get_recent_orders")]
	provider_columns = _provider_order_columns(registry, integration, problems)
	options = _common_filter_options(provider_filters, active_integrations)
	filters = {k: v for k, v in (filters or {}).items() if any(f["key"] == k for f in options)} or None

	providers = registry.active(integration, "get_recent_orders")
	if filters:
		# Only providers that understand the active filters can return rows for them.
		declaring = {
			p.integration for p, opts in provider_filters if set(filters) <= {o.get("key") for o in opts}
		}
		providers = [p for p in providers if p.integration in declaring]

	rows, total = _merged(
		registry,
		integration,
		"get_recent_orders",
		"count_orders",
		search,
		status,
		page,
		page_size,
		problems,
		providers=providers,
		filters=filters,
	)
	unsupported = _unsupported(registry, integration, "get_recent_orders")
	return {
		"rows": rows,
		"total": total,
		"problems": problems,
		"unsupported": unsupported,
		"filter_options": options,
		"columns": _common_order_columns(provider_columns, active_integrations),
	}


def _provider_order_filters(
	registry: Registry, integration: str | None, problems: list[str]
) -> list[tuple[Provider, list[dict]]]:
	"""(provider, filter definitions) for every enabled provider in scope that declares some."""
	out = []
	for provider in registry.active(integration, "get_order_filter_options"):
		options = call_adapter(provider, "get_order_filter_options", problems, [])
		if options:
			out.append((provider, options))
	return out


def _provider_order_columns(
	registry: Registry, integration: str | None, problems: list[str]
) -> list[tuple[Provider, list[dict]]]:
	"""(provider, column definitions) for every enabled provider in scope that declares some."""
	return _provider_declarations(registry, integration, problems, "get_order_columns")


def _provider_declarations(
	registry: Registry, integration: str | None, problems: list[str], method: str
) -> list[tuple[Provider, list[dict]]]:
	"""(provider, definitions) for every enabled provider in scope that declares some via 'method'."""
	out = []
	for provider in registry.active(integration, method):
		definitions = call_adapter(provider, method, problems, [])
		if definitions:
			out.append((provider, definitions))
	return out


def _provider_filter_map(provider: Provider | None) -> dict[str, dict[str, str]]:
	"""The provider's filter field map: {filter key: {doctype: fieldname}}; empty when absent."""
	if not provider or not provider.adapter or not provider.adapter.implements("get_filter_field_map"):
		return {}
	try:
		return provider.adapter.get_filter_field_map() or {}
	except Exception:
		return {}


def _filter_labels(provider: Provider | None) -> dict[str, str]:
	"""Filter key -> label from the provider's order filter options."""
	if not provider or not provider.adapter or not provider.adapter.implements("get_order_filter_options"):
		return {}
	try:
		return {o.get("key"): o.get("label") for o in (provider.adapter.get_order_filter_options() or [])}
	except Exception:
		return {}


def _filter_map_columns(provider: Provider | None, doctype: str) -> list[dict]:
	"""Detail columns for a core-owned widget: the provider's mapped fields on 'doctype'."""
	field_map = _provider_filter_map(provider)
	if not field_map:
		return []
	labels = _filter_labels(provider)
	columns = []
	for key, fields in field_map.items():
		fieldname = (fields or {}).get(doctype)
		if not fieldname or not frappe.get_meta(doctype).has_field(fieldname):
			continue
		if any(column["key"] == fieldname for column in columns):
			continue
		columns.append({"key": fieldname, "label": labels.get(key) or key})
	return columns


def _log_detail_columns(registry: Registry, integration: str | None) -> list[dict]:
	"""Detail columns the sync-log table shows; shared by every enabled provider in scope."""
	provider_columns = []
	for provider in registry.scoped(integration):
		columns = _filter_map_columns(provider, "Ecommerce Integration Log")
		if columns:
			provider_columns.append((provider, columns))
	active = [p.integration for p in registry.scoped(integration) if p.enabled]
	return _common_order_columns(provider_columns, active)


def _item_filter_options(integ: str, provider) -> list[dict]:
	"""Dropdown filters for the items widget, options taken from the mapped items themselves."""
	field_map = _provider_filter_map(provider)
	if not field_map:
		return []
	labels = _filter_labels(provider)
	options = []
	for key, fields in field_map.items():
		fieldname = (fields or {}).get("Ecommerce Item")
		if not fieldname or not frappe.get_meta("Ecommerce Item").has_field(fieldname):
			continue
		values = sorted(
			{
				value
				for value in frappe.get_all(
					"Ecommerce Item",
					filters={"integration": integ, fieldname: ("is", "set")},
					pluck=fieldname,
				)
				if value
			}
		)
		if values:
			options.append({"key": key, "label": labels.get(key) or key, "options": [(v, v) for v in values]})
	return options


def _summary_tile_filters(
	registry: Registry, integration: str | None, filters: str | None
) -> dict[str, str] | None:
	"""Extra filters the stat tiles honour: keys the scope's order filters declare.

	Only meaningful with one integration selected; the combined view never
	shares a filter key across connectors, so filters drop to None there.
	"""
	parsed = _parse_filters(filters)
	if not parsed or not integration:
		return None
	problems: list[str] = []
	options = _common_filter_options(_provider_order_filters(registry, integration, problems), [integration])
	keys = {option["key"] for option in options}
	clean = {key: value for key, value in parsed.items() if key in keys}
	return clean or None


def _tile_filter_clause(registry: Registry, integration, tile_filters, doctype, table):
	"""WHERE clause applying the tile filters on one doctype the summary reads; None when N/A."""
	if not tile_filters or not integration:
		return None
	field_map = _provider_filter_map(registry.get(integration))
	clauses = [
		table[fieldname] == value
		for key, value in tile_filters.items()
		if (fieldname := (field_map.get(key) or {}).get(doctype))
		and frappe.get_meta(doctype).has_field(fieldname)
	]
	clause = clauses[0] if clauses else None
	for extra in clauses[1:]:
		clause = clause & extra
	return clause


def _merged_filter_options(provider_filters) -> list[dict]:
	"""Union of every provider's filter definitions, merged by key."""
	merged: dict[str, dict] = {}
	for _provider, options in provider_filters:
		for option in options:
			key = option.get("key")
			if not key:
				continue
			entry = merged.setdefault(key, {"key": key, "label": option.get("label") or key, "options": []})
			for pair in option.get("options") or []:
				if pair not in entry["options"]:
					entry["options"].append(pair)
	return list(merged.values())


def _common_filter_options(provider_filters, active_integrations: list[str]) -> list[dict]:
	"""Filter definitions shared by every active provider in scope."""
	if not active_integrations or len(active_integrations) == 1:
		return _merged_filter_options(provider_filters)

	declared = {p.integration: {o.get("key") for o in opts} for p, opts in provider_filters}
	common = set.intersection(*(declared.get(name, set()) for name in active_integrations))
	if not common:
		return []
	merged = {option["key"]: option for option in _merged_filter_options(provider_filters)}
	return [merged[key] for key in sorted(common & merged.keys())]


def _merged_order_columns(provider_columns) -> list[dict]:
	"""Union of every provider's extra order columns, merged by key."""
	merged: dict[str, dict] = {}
	for _provider, columns in provider_columns:
		for column in columns:
			key = column.get("key")
			if not key:
				continue
			merged.setdefault(
				key, {"key": key, "label": column.get("label") or key, "width": column.get("width")}
			)
	return list(merged.values())


def _common_order_columns(provider_columns, active_integrations: list[str]) -> list[dict]:
	"""Extra order columns shared by every active provider in scope."""
	if not active_integrations or len(active_integrations) == 1:
		return _merged_order_columns(provider_columns)

	declared = {
		provider.integration: {column.get("key") for column in columns}
		for provider, columns in provider_columns
	}
	common = set.intersection(*(declared.get(name, set()) for name in active_integrations))
	if not common:
		return []
	merged = {column["key"]: column for column in _merged_order_columns(provider_columns)}
	return [merged[key] for key in sorted(common & merged.keys())]


def _payments_section(registry, integration, search, status, page, page_size, filters=None):
	"""Merged pending-payment rows across providers; shape is {"rows", "total", "problems", "unsupported"}."""
	problems = []
	rows, total = _merged(
		registry,
		integration,
		"get_pending_payments",
		"count_pending_payments",
		search,
		status,
		page,
		page_size,
		problems,
	)
	provider_columns = _provider_declarations(registry, integration, problems, "get_payment_columns")
	active_integrations = [p.integration for p in registry.active(integration, "get_pending_payments")]
	unsupported = _unsupported(registry, integration, "get_pending_payments")
	return {
		"rows": rows,
		"total": total,
		"problems": problems,
		"unsupported": unsupported,
		"columns": _common_order_columns(provider_columns, active_integrations),
	}


def _items_section(registry, integration, search, status, page, page_size, filters=None):
	"""One page of item rows after stock-status filtering; "counts" cover the full unfiltered set."""
	problems = _warehouse_problems(registry, integration)
	integrations = _integrations_in_scope(registry, integration)
	if len(integrations) == 1:
		# Single connector: filter, sort and paginate in SQL; cache only compact counts.
		integ = integrations[0]
		provider = registry.get(integ)
		filter_options = _item_filter_options(integ, provider)
		filters = {
			k: v for k, v in (filters or {}).items() if any(f["key"] == k for f in filter_options)
		} or None
		counts = _items_counts_sql(integ, provider, filters)
		rows = _items_rows_sql(integ, provider, search, status, page, page_size, filters)
		total = counts[status] if status in STOCK_ORDER else counts["all"]
		columns = _filter_map_columns(provider, "Ecommerce Item")
		return {
			"rows": rows,
			"total": total,
			"counts": counts,
			"problems": problems,
			"columns": columns,
			"filter_options": filter_options,
		}

	rows = _item_rows(registry, integration, search)
	counts = _stock_counts(rows)
	if status in STOCK_ORDER:
		rows = [r for r in rows if r["stock_status"] == status]
	start = (page - 1) * page_size
	return {
		"rows": rows[start : start + page_size],
		"total": len(rows),
		"counts": counts,
		"problems": problems,
	}


def _logs_section(registry, integration, search, status, page, page_size, filters=None):
	"""Paged sync-log rows from ERPNext; status counts are cached per integration/search."""
	log = DocType("Ecommerce Integration Log")
	base = frappe.qb.from_(log)
	if integration:
		base = base.where(log.integration == integration)
	if search:
		like = like_pattern(search)
		base = base.where(log.name.like(like) | log.title.like(like))

	cache_key = cache_key_for("log_counts", integration, search)
	by_status = frappe.cache.get_value(cache_key)
	if by_status is None:
		by_status = dict(base.select(log.status, Count("*")).groupby(log.status).run())
		frappe.cache.set_value(cache_key, by_status, expires_in_sec=LOG_COUNTS_TTL_SECONDS)
	counts = {group: sum(by_status.get(s, 0) for s in statuses) for group, statuses in LOG_GROUPS.items()}
	counts["all"] = sum(by_status.values())

	query = base
	if status in LOG_GROUPS:
		query = query.where(log.status.isin(LOG_GROUPS[status]))

	problems = []
	columns = _log_detail_columns(registry, integration)
	rows = (
		query.select(
			log.name,
			log.title,
			log.status,
			log.integration,
			log.modified,
			*(log[c["key"]] for c in columns),
		)
		.orderby(log.modified, order=Order.desc)
		.limit(page_size)
		.offset((page - 1) * page_size)
		.run(as_dict=True)
	)
	labels = {p.integration: p.label for p in registry.providers}
	for row in rows:
		row.platform = labels.get(row.integration, row.integration or _("Unknown integration"))
		row.details = [
			{"key": c["key"], "label": c["label"], "value": row.get(c["key"])}
			for c in columns
			if row.get(c["key"]) not in (None, "")
		]

	total = counts[status] if status in LOG_GROUPS else counts["all"]
	return {"rows": rows, "total": total, "counts": counts, "problems": problems, "columns": columns}


# ----- items & inventory -----


def _integrations_in_scope(registry: Registry, integration: str | None) -> list[str]:
	"""Integrations the items view covers: the selected one, or every registered/mapped name."""
	if integration:
		return [integration]
	if (cached := getattr(frappe.local, "ecommerce_scope_integrations", None)) is not None:
		return cached
	mapped = frappe.get_all("Ecommerce Item", fields=["integration"], distinct=True, pluck="integration")
	scope = sorted({*(p.integration for p in registry.providers), *(m for m in mapped if m)})
	frappe.local.ecommerce_scope_integrations = scope
	return scope


def _warehouses(provider: Provider | None) -> list[str] | None:
	"""Leaf + group warehouses configured in the connector's settings.

	None means all warehouses on purpose (connector has no settings); an empty
	list means the warehouse configuration is broken and no stock is trusted.
	"""
	if not provider:
		return None
	if provider.adapter and provider.adapter.implements("get_erpnext_warehouses"):
		# Connectors with per-store settings (not a single doc) aggregate themselves.
		try:
			configured = provider.adapter.get_erpnext_warehouses()
		except Exception:
			return []
	elif provider.settings_doctype:
		try:
			configured = frappe.get_cached_doc(provider.settings_doctype).get_erpnext_warehouses()
		except Exception:
			return []
	else:
		return None
	if not configured:
		return []

	warehouses = set(configured)
	groups = frappe.get_all(
		"Warehouse", filters={"name": ["in", list(configured)], "is_group": 1}, pluck="name"
	)
	for warehouse in groups:
		warehouses.update(get_descendants_of("Warehouse", warehouse))
	return list(warehouses)


def _warehouse_problems(registry: Registry, integration: str | None) -> list[str]:
	"""Notices for connectors whose warehouse configuration cannot be trusted."""
	problems = []
	for provider in registry.scoped(integration):
		if provider.adapter and provider.adapter.implements("get_erpnext_warehouses"):
			try:
				configured = provider.adapter.get_erpnext_warehouses()
			except Exception:
				problems.append(
					_("{0}: warehouse configuration could not be read; stock and pushes are paused.").format(
						provider.label
					)
				)
				continue
		elif provider.settings_doctype:
			try:
				configured = frappe.get_cached_doc(provider.settings_doctype).get_erpnext_warehouses()
			except Exception:
				problems.append(
					_("{0}: warehouse settings could not be read; stock and pushes are paused.").format(
						provider.label
					)
				)
				continue
		else:
			continue
		if not configured:
			problems.append(
				_("{0}: no ERPNext warehouses configured; stock and pushes are paused.").format(
					provider.label
				)
			)
	return problems


ITEMS_COUNTS_TTL_SECONDS = 60


def _items_status_expr(bin_agg, reorder_agg, item):
	"""SQL stock-status expression matching the Python semantics."""
	available = IfNull(bin_agg.actual, 0) - IfNull(bin_agg.reserved, 0)
	return (
		Case()
		.when(IfNull(item.is_stock_item, 0) == 0, "na")
		.when(available <= 0, "out")
		.when((IfNull(reorder_agg.level, 0) > 0) & (available <= IfNull(reorder_agg.level, 0)), "low")
		.else_("in")
	)


def _items_order_expr(status_expr):
	"""Sort key matching STOCK_ORDER (out, low, in, na)."""
	return (
		Case()
		.when(status_expr == "out", 0)
		.when(status_expr == "low", 1)
		.when(status_expr == "in", 2)
		.else_(3)
	)


def _items_base(integration: str, provider, search: str | None, filters: dict[str, str] | None = None):
	"""Mapped items joined with their warehouse-scoped stock and reorder level."""
	ecom = DocType("Ecommerce Item")
	item = DocType("Item")
	bin_ = DocType("Bin")
	reorder = DocType("Item Reorder")
	warehouses = _warehouses(provider)

	bin_agg = (
		frappe.qb.from_(bin_)
		.select(
			bin_.item_code,
			Sum(bin_.actual_qty).as_("actual"),
			Sum(bin_.reserved_qty).as_("reserved"),
		)
		.groupby(bin_.item_code)
	)
	reorder_agg = (
		frappe.qb.from_(reorder)
		.select(reorder.parent, Sum(reorder.warehouse_reorder_level).as_("level"))
		.where(reorder.parenttype == "Item")
		.groupby(reorder.parent)
	)
	if warehouses is not None:
		# None: all warehouses on purpose; []: broken configuration, so no stock is trusted.
		# An empty isin() renders invalid SQL, so a broken config matches no warehouse.
		scope = warehouses or ["-"]
		bin_agg = bin_agg.where(bin_.warehouse.isin(scope))
		reorder_agg = reorder_agg.where(reorder.warehouse.isin(scope))

	query = (
		frappe.qb.from_(ecom)
		.left_join(item)
		.on(item.name == ecom.erpnext_item_code)
		.left_join(bin_agg)
		.on(bin_agg.item_code == ecom.erpnext_item_code)
		.left_join(reorder_agg)
		.on(reorder_agg.parent == ecom.erpnext_item_code)
		.where((ecom.integration == integration) & (ecom.has_variants == 0))
	)
	field_map = _provider_filter_map(provider)
	for key, value in (filters or {}).items():
		fieldname = (field_map.get(key) or {}).get("Ecommerce Item")
		if fieldname and frappe.get_meta("Ecommerce Item").has_field(fieldname):
			query = query.where(ecom[fieldname] == value)
	if search:
		like = like_pattern(search)
		query = query.where(
			ecom.erpnext_item_code.like(like)
			| item.item_name.like(like)
			| ecom.sku.like(like)
			| ecom.integration_item_code.like(like)
		)
	return query, bin_agg, reorder_agg, item


def _items_counts_sql(integration: str, provider, filters: dict[str, str] | None = None) -> dict:
	"""Stock-status counts for one integration; cached as compact totals only."""
	digest = hashlib.md5(json.dumps(filters or {}, sort_keys=True).encode()).hexdigest()[:8]
	cache_key = f"ecommerce_core:dashboard_item_counts:{integration}:{digest}"
	if (counts := frappe.cache.get_value(cache_key)) is not None:
		return counts
	query, bin_agg, reorder_agg, item = _items_base(integration, provider, None, filters)
	status_expr = _items_status_expr(bin_agg, reorder_agg, item)
	by_status = dict(query.select(status_expr.as_("status"), Count("*")).groupby(status_expr).run())
	counts = {"all": sum(by_status.values())}
	for key in ("in", "low", "out", "na"):
		counts[key] = by_status.get(key, 0)
	frappe.cache.set_value(cache_key, counts, expires_in_sec=ITEMS_COUNTS_TTL_SECONDS)
	return counts


def _items_rows_sql(
	integration: str, provider, search, status, page, page_size, filters: dict[str, str] | None = None
) -> list[dict]:
	"""One page of item rows with filtering, sorting and pagination done in SQL."""
	ecom = DocType("Ecommerce Item")
	query, bin_agg, reorder_agg, item = _items_base(integration, provider, search, filters)
	status_expr = _items_status_expr(bin_agg, reorder_agg, item)
	if status in STOCK_ORDER:
		query = query.where(status_expr == status)
	available = (IfNull(bin_agg.actual, 0) - IfNull(bin_agg.reserved, 0)).as_("available")
	columns = _filter_map_columns(provider, "Ecommerce Item")

	rows = (
		query.select(
			ecom.name,
			ecom.erpnext_item_code.as_("item_code"),
			ecom.integration_item_code,
			ecom.sku,
			ecom.inventory_synced_on,
			item.item_name,
			item.is_stock_item,
			IfNull(bin_agg.actual, 0).as_("actual"),
			IfNull(bin_agg.reserved, 0).as_("reserved"),
			available,
			IfNull(reorder_agg.level, 0).as_("reorder_level"),
			status_expr.as_("stock_status"),
			*(ecom[column["key"]].as_(column["key"]) for column in columns),
		)
		.orderby(_items_order_expr(status_expr), available, ecom.erpnext_item_code)
		.limit(page_size)
		.offset((page - 1) * page_size)
		.run(as_dict=True)
	)
	can_push = bool(provider and provider.enabled and provider.adapter.implements("push_inventory"))
	return [
		{
			"name": r.name,
			"integration": integration,
			"platform": provider.label if provider else integration,
			"item_code": r.item_code,
			"item_name": r.item_name,
			"sku": r.sku or r.integration_item_code,
			"actual": r.actual or 0,
			"reserved": r.reserved or 0,
			"available": r.available or 0,
			"reorder_level": r.reorder_level or 0,
			"stock_status": r.stock_status,
			"inventory_synced_on": r.inventory_synced_on,
			"can_push": can_push and bool(r.is_stock_item),
			"details": [
				{"key": c["key"], "label": c["label"], "value": r.get(c["key"])}
				for c in columns
				if r.get(c["key"]) not in (None, "")
			],
		}
		for r in rows
	]


def _item_rows(registry: Registry, integration: str | None, search: str | None) -> list[dict]:
	"""Short-lived cached wrapper: summary tiles and the items table share one computation."""
	key = cache_key_for("items", integration, search)
	rows = frappe.cache.get_value(key)
	if rows is None:
		rows = _build_item_rows(registry, integration, search)
		frappe.cache.set_value(key, rows, expires_in_sec=ITEM_ROWS_TTL_SECONDS)
	return rows


def _build_item_rows(registry: Registry, integration: str | None, search: str | None) -> list[dict]:
	"""Every mapped sellable item in scope with its stock in the connector's warehouses."""
	ecom_item = DocType("Ecommerce Item")
	item = DocType("Item")
	rows = []

	for integ in _integrations_in_scope(registry, integration):
		provider = registry.get(integ)
		query = (
			frappe.qb.from_(ecom_item)
			.left_join(item)
			.on(item.name == ecom_item.erpnext_item_code)
			.select(
				ecom_item.name,
				ecom_item.integration,
				ecom_item.erpnext_item_code.as_("item_code"),
				ecom_item.integration_item_code,
				ecom_item.sku,
				ecom_item.inventory_synced_on,
				item.item_name,
				item.is_stock_item,
			)
			.where((ecom_item.integration == integ) & (ecom_item.has_variants == 0))
		)
		if search:
			like = like_pattern(search)
			query = query.where(
				ecom_item.erpnext_item_code.like(like)
				| item.item_name.like(like)
				| ecom_item.sku.like(like)
				| ecom_item.integration_item_code.like(like)
			)
		items = query.run(as_dict=True)
		if not items:
			continue

		warehouses = _warehouses(provider)
		item_codes = list({r.item_code for r in items if r.item_code})
		stock = _stock_levels(item_codes, warehouses)
		reorder = _reorder_levels(item_codes, warehouses)
		can_push = bool(provider and provider.enabled and provider.adapter.implements("push_inventory"))

		for r in items:
			actual, reserved = stock.get(r.item_code, (0, 0))
			available = actual - reserved
			level = reorder.get(r.item_code, 0)
			if not r.is_stock_item:
				stock_status = "na"
			elif available <= 0:
				stock_status = "out"
			elif level and available <= level:
				stock_status = "low"
			else:
				stock_status = "in"

			rows.append(
				{
					"name": r.name,
					"integration": integ,
					"platform": provider.label if provider else integ,
					"item_code": r.item_code,
					"item_name": r.item_name,
					"sku": r.sku or r.integration_item_code,
					"actual": actual,
					"reserved": reserved,
					"available": available,
					"reorder_level": level,
					"stock_status": stock_status,
					"inventory_synced_on": r.inventory_synced_on,
					"can_push": can_push and bool(r.is_stock_item),
				}
			)

	rows.sort(key=lambda r: (STOCK_ORDER[r["stock_status"]], r["available"], r["item_code"] or ""))
	return rows


def _stock_levels(item_codes: list[str], warehouses: list[str] | None) -> dict[str, tuple[float, float]]:
	"""Actual and reserved quantity per item code, summed across the given warehouses."""
	if not item_codes:
		return {}
	bin_ = DocType("Bin")
	levels: dict[str, tuple[float, float]] = {}
	for chunk in _chunks(item_codes):
		query = (
			frappe.qb.from_(bin_)
			.select(bin_.item_code, Sum(bin_.actual_qty), Sum(bin_.reserved_qty))
			.where(bin_.item_code.isin(chunk))
			.groupby(bin_.item_code)
		)
		if warehouses:
			query = query.where(bin_.warehouse.isin(warehouses))
		levels.update({code: (actual or 0, reserved or 0) for code, actual, reserved in query.run()})
	return levels


def _reorder_levels(item_codes: list[str], warehouses: list[str] | None) -> dict[str, float]:
	"""Summed Item Reorder thresholds per item; 0 for items without a reorder level."""
	if not item_codes:
		return {}
	reorder = DocType("Item Reorder")
	levels: dict[str, float] = {}
	for chunk in _chunks(item_codes):
		query = (
			frappe.qb.from_(reorder)
			.select(reorder.parent, Sum(reorder.warehouse_reorder_level))
			.where((reorder.parenttype == "Item") & reorder.parent.isin(chunk))
			.groupby(reorder.parent)
		)
		if warehouses:
			query = query.where(reorder.warehouse.isin(warehouses))
		levels.update({code: level or 0 for code, level in query.run()})
	return levels


def _chunks(values: list[str]):
	"""Yield fixed-size slices so IN clauses stay under the query length limits."""
	for i in range(0, len(values), IN_CHUNK_SIZE):
		yield values[i : i + IN_CHUNK_SIZE]


def _stock_counts(rows: list[dict]) -> dict[str, int]:
	"""Row counts per stock status for the summary tiles; "all" is the unfiltered total."""
	counts = {"all": len(rows), "in": 0, "low": 0, "out": 0, "na": 0}
	for row in rows:
		counts[row["stock_status"]] += 1
	return counts


# ----- helpers -----


def _parse_filters(filters: str | None) -> dict[str, str] | None:
	"""Extra section filters arrive from the page as a JSON object: key -> selected value."""
	try:
		parsed = json.loads(filters) if filters else None
	except ValueError:
		return None
	if not isinstance(parsed, dict):
		return None
	clean = {str(key): cstr(value).strip()[:140] for key, value in parsed.items() if cstr(value).strip()}
	return clean or None


def _unsupported(registry: Registry, integration: str | None, method: str) -> list[str]:
	"""Labels of enabled providers in scope that don't feed this widget."""
	return [
		p.label
		for p in registry.scoped(integration)
		if p.enabled and p.adapter and not p.adapter.implements(method)
	]
