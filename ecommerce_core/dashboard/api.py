"""Whitelisted endpoints behind the Ecommerce Dashboard page (System Manager only)."""

import json

import frappe
from frappe import _
from frappe.query_builder import DocType, Order
from frappe.query_builder.functions import Count, Sum
from frappe.utils import add_days, cint, cstr, now_datetime
from frappe.utils.nestedset import get_descendants_of

from ecommerce_core.dashboard.queries import like_pattern
from ecommerce_core.dashboard.registry import Provider, Registry, call_adapter, load_registry
from ecommerce_core.ecommerce_core.doctype.ecommerce_integration_log.ecommerce_integration_log import (
	_retry_job,
)

MAX_PAGE_SIZE = 50
MAX_MERGE_ROWS = 500

LOG_GROUPS = {
	"success": ("Success",),
	"failed": ("Error", "Failure"),
	"partial": ("Partial Success",),
	"queued": ("Queued",),
}
STOCK_ORDER = {"out": 0, "low": 1, "in": 2, "na": 3}


@frappe.whitelist()
def get_summary(integration: str | None = None) -> dict:
	"""Provider tabs, stat tiles and adapter problems for the selected view."""
	frappe.only_for("System Manager")
	registry = load_registry()
	integration = integration or None
	problems = list(registry.problems)
	scoped = registry.scoped(integration)
	problems += [p.problem for p in scoped if p.problem]

	integrations = _integrations_in_scope(registry, integration)
	ecom_item = DocType("Ecommerce Item")
	item_scope = (ecom_item.integration.isin(integrations)) & (ecom_item.has_variants == 0)
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
	failed = failed_query.run()[0][0]

	pending: dict[str, dict] = {}
	for provider in registry.active(integration, "get_pending_summary"):
		for row in call_adapter(provider, "get_pending_summary", problems, []):
			entry = pending.setdefault(
				row["currency"], {"currency": row["currency"], "amount": 0, "count": 0}
			)
			entry["amount"] += row["amount"] or 0
			entry["count"] += row["count"] or 0

	stock_counts = _stock_counts(_item_rows(registry, integration, None))

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


@frappe.whitelist()
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

	handlers = {
		"orders": _orders_section,
		"payments": _payments_section,
		"items": _items_section,
		"logs": _logs_section,
	}
	if section not in handlers:
		frappe.throw(_("Unknown dashboard section: {0}").format(section))

	registry = load_registry()
	if section == "orders":
		return _orders_section(registry, integration, search, status, page, page_size, extra_filters)
	return handlers[section](registry, integration, search, status, page, page_size)


@frappe.whitelist(methods=["POST"])
def retry_log(name: str) -> dict:
	"""Retry a failed log with the same idempotent path as the log form's Retry button."""
	frappe.only_for("System Manager")
	status = frappe.db.get_value("Ecommerce Integration Log", name, "status")
	if status != "Error":
		frappe.throw(_("Only logs in Error status can be retried."))
	_retry_job(name)
	return {"status": frappe.db.get_value("Ecommerce Integration Log", name, "status")}


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
	return provider.adapter.push_inventory([ecommerce_item])


@frappe.whitelist(methods=["POST"])
def create_payment_link(sales_invoice: str) -> dict:
	"""Create and submit a Payment Request for an outstanding Sales Invoice."""
	frappe.only_for("System Manager")
	frappe.has_permission("Payment Request", "create", throw=True)
	from erpnext.accounts.doctype.payment_request.payment_request import make_payment_request

	existing = _open_payment_requests([sales_invoice]).get(sales_invoice)
	if existing:
		return existing

	pr = make_payment_request(dt="Sales Invoice", dn=sales_invoice, submit_doc=1, mute_email=1, return_doc=1)
	name = pr.get("name")
	return {"name": name, "url": frappe.db.get_value("Payment Request", name, "payment_url")}


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

	rows.sort(key=lambda r: str(r.get("created") or ""), reverse=True)
	start = (page - 1) * page_size
	return rows[start : start + page_size], total


def _orders_section(registry, integration, search, status, page, page_size, filters=None):
	problems = []
	provider_filters = _provider_order_filters(registry, integration, problems)
	options = _merged_filter_options(provider_filters)
	filters = {k: v for k, v in (filters or {}).items() if any(f["key"] == k for f in options)} or None

	providers = registry.active(integration, "get_recent_orders")
	if filters:
		# Providers that don't declare the active keys can't apply them; querying them
		# anyway would mix filtered and unfiltered rows, so they're left out.
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
		"columns": _merged_order_columns(registry, integration, problems),
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


def _merged_order_columns(registry: Registry, integration: str | None, problems: list[str]) -> list[dict]:
	"""Union of every provider's extra order columns, merged by key."""
	merged: dict[str, dict] = {}
	for provider in registry.active(integration, "get_order_columns"):
		for column in call_adapter(provider, "get_order_columns", problems, []) or []:
			key = column.get("key")
			if not key:
				continue
			merged.setdefault(
				key, {"key": key, "label": column.get("label") or key, "width": column.get("width")}
			)
	return list(merged.values())


def _payments_section(registry, integration, search, status, page, page_size):
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
	unsupported = _unsupported(registry, integration, "get_pending_payments")
	return {"rows": rows, "total": total, "problems": problems, "unsupported": unsupported}


def _items_section(registry, integration, search, status, page, page_size):
	rows = _item_rows(registry, integration, search)
	counts = _stock_counts(rows)
	if status in STOCK_ORDER:
		rows = [r for r in rows if r["stock_status"] == status]
	start = (page - 1) * page_size
	return {"rows": rows[start : start + page_size], "total": len(rows), "counts": counts, "problems": []}


def _logs_section(registry, integration, search, status, page, page_size):
	log = DocType("Ecommerce Integration Log")
	base = frappe.qb.from_(log)
	if integration:
		base = base.where(log.integration == integration)
	if search:
		like = like_pattern(search)
		base = base.where(log.name.like(like) | log.title.like(like))

	by_status = dict(base.select(log.status, Count("*")).groupby(log.status).run())
	counts = {group: sum(by_status.get(s, 0) for s in statuses) for group, statuses in LOG_GROUPS.items()}
	counts["all"] = sum(by_status.values())

	query = base
	if status in LOG_GROUPS:
		query = query.where(log.status.isin(LOG_GROUPS[status]))

	rows = (
		query.select(log.name, log.title, log.status, log.integration, log.modified)
		.orderby(log.modified, order=Order.desc)
		.limit(page_size)
		.offset((page - 1) * page_size)
		.run(as_dict=True)
	)
	labels = {p.integration: p.label for p in registry.providers}
	for row in rows:
		row.platform = labels.get(row.integration, row.integration or _("Unknown integration"))

	total = counts[status] if status in LOG_GROUPS else counts["all"]
	return {"rows": rows, "total": total, "counts": counts, "problems": []}


# ----- items & inventory -----


def _integrations_in_scope(registry: Registry, integration: str | None) -> list[str]:
	if integration:
		return [integration]
	mapped = frappe.get_all("Ecommerce Item", fields=["integration"], distinct=True, pluck="integration")
	return sorted({*(p.integration for p in registry.providers), *(m for m in mapped if m)})


def _warehouses(provider: Provider | None) -> list[str] | None:
	"""Leaf + group warehouses configured in the connector's settings; None means all warehouses."""
	if not provider or not provider.settings_doctype:
		return None
	try:
		configured = frappe.get_cached_doc(provider.settings_doctype).get_erpnext_warehouses()
	except Exception:
		return None
	if not configured:
		return None

	warehouses = set(configured)
	for warehouse in configured:
		if frappe.db.get_value("Warehouse", warehouse, "is_group"):
			warehouses.update(get_descendants_of("Warehouse", warehouse))
	return list(warehouses)


def _item_rows(registry: Registry, integration: str | None, search: str | None) -> list[dict]:
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
	if not item_codes:
		return {}
	bin_ = DocType("Bin")
	query = (
		frappe.qb.from_(bin_)
		.select(bin_.item_code, Sum(bin_.actual_qty), Sum(bin_.reserved_qty))
		.where(bin_.item_code.isin(item_codes))
		.groupby(bin_.item_code)
	)
	if warehouses:
		query = query.where(bin_.warehouse.isin(warehouses))
	return {code: (actual or 0, reserved or 0) for code, actual, reserved in query.run()}


def _reorder_levels(item_codes: list[str], warehouses: list[str] | None) -> dict[str, float]:
	if not item_codes:
		return {}
	reorder = DocType("Item Reorder")
	query = (
		frappe.qb.from_(reorder)
		.select(reorder.parent, Sum(reorder.warehouse_reorder_level))
		.where((reorder.parenttype == "Item") & reorder.parent.isin(item_codes))
		.groupby(reorder.parent)
	)
	if warehouses:
		query = query.where(reorder.warehouse.isin(warehouses))
	return {code: level or 0 for code, level in query.run()}


def _stock_counts(rows: list[dict]) -> dict[str, int]:
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


def _open_payment_requests(invoices: list[str]) -> dict[str, dict]:
	"""Latest open (submitted, unpaid) Payment Request per Sales Invoice."""
	if not invoices:
		return {}
	pr = DocType("Payment Request")
	rows = (
		frappe.qb.from_(pr)
		.select(pr.name, pr.reference_name, pr.payment_url)
		.where(
			(pr.reference_doctype == "Sales Invoice")
			& pr.reference_name.isin(invoices)
			& (pr.docstatus == 1)
			& pr.status.notin(("Paid", "Cancelled"))
		)
		.orderby(pr.creation)
		.run(as_dict=True)
	)
	return {r.reference_name: {"name": r.name, "url": r.payment_url} for r in rows}
