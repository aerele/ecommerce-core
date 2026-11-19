"""Reusable ERPNext queries for dashboard adapters."""

import hashlib

import frappe
from frappe.query_builder import Order
from frappe.query_builder.functions import Count, Sum

ORDER_INDICATORS = {
	"Draft": "red",
	"On Hold": "orange",
	"To Deliver and Bill": "orange",
	"To Bill": "orange",
	"To Deliver": "orange",
	"Completed": "green",
	"Closed": "green",
	"Cancelled": "red",
}

COD_NOT_COLLECTED = "COD Not Collected"
PAYMENT_INDICATORS = {
	"Unpaid": "orange",
	"Partly Paid": "yellow",
	"Overdue": "red",
	COD_NOT_COLLECTED: "blue",
}


CACHE_PREFIX = "ecommerce_core:dashboard:"


def cache_key_for(kind: str, integration: str | None, search: str | None) -> str:
	"""Cache key scoped to the session user (permissions differ per user) and the
	integration; the search text is hashed so keys stay short and bounded in shape."""
	digest = hashlib.md5((search or "").strip().lower().encode()).hexdigest()[:12]
	return f"{CACHE_PREFIX}{kind}:{frappe.session.user}:{integration or '_all'}:{digest}"


def invalidate_dashboard_cache() -> None:
	"""Drop every cached dashboard aggregate; call after data they derive from changes."""
	frappe.cache.delete_keys(CACHE_PREFIX)


def like_pattern(search: str) -> str:
	"""Escape LIKE wildcards in user input and wrap it in a contains-pattern."""
	escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
	return f"%{escaped}%"


def _has_field(doctype: str, fieldname: str | None) -> bool:
	"""True only when the fieldname is given and exists on the doctype's meta."""
	return bool(fieldname) and frappe.get_meta(doctype).has_field(fieldname)


def _sales_order_query(
	id_field: str,
	search: str | None,
	status: str | None,
	filter_fields: dict[str, str] | None = None,
	filters: dict[str, str] | None = None,
):
	"""Shared Sales Order query: only rows tagged with 'id_field', filtered and searched."""
	so = frappe.qb.DocType("Sales Order")
	query = frappe.qb.from_(so).where(so[id_field].isnotnull() & (so[id_field] != ""))
	if status:
		query = query.where(so.status == status)
	for key, fieldname in (filter_fields or {}).items():
		if (filters or {}).get(key) and _has_field("Sales Order", fieldname):
			query = query.where(so[fieldname] == filters[key])
	if search and search.strip():
		like = like_pattern(search)
		query = query.where(so[id_field].like(like) | so.name.like(like) | so.customer_name.like(like))
	return so, query


def recent_sales_orders(
	id_field: str,
	limit: int,
	search: str | None = None,
	status: str | None = None,
	extra_fields: list[tuple[str, str]] | None = None,
	invoice_fields: list[tuple[str, str]] | None = None,
	filter_fields: dict[str, str] | None = None,
	filters: dict[str, str] | None = None,
) -> list[dict]:
	"""Sales Orders tagged with 'id_field', newest first, in the dashboard order-row shape."""
	if not _has_field("Sales Order", id_field):
		return []
	extra_fields = _existing_fields("Sales Order", extra_fields)
	invoice_fields = _existing_fields("Sales Invoice", invoice_fields)

	so, query = _sales_order_query(id_field, search, status, filter_fields, filters)
	rows = (
		query.select(
			so.name,
			so[id_field].as_("order_id"),
			so.customer_name,
			so.grand_total,
			so.currency,
			so.status,
			so.creation,
			*(so[fieldname].as_(fieldname) for fieldname, _label in extra_fields),
		)
		.orderby(so.creation, order=Order.desc)
		.limit(limit)
		.run(as_dict=True)
	)

	invoices = _latest_invoices(id_field, [r.order_id for r in rows], [f for f, _l in invoice_fields])
	return [
		{
			"id": r.order_id,
			"docname": r.name,
			"doctype": "Sales Order",
			"customer": r.customer_name,
			"amount": r.grand_total,
			"currency": r.currency,
			"status": r.status,
			"indicator": ORDER_INDICATORS.get(r.status, "gray"),
			"created": r.creation,
			"invoice": invoices.get(r.order_id, {}).get("name"),
			"details": _row_details(r, extra_fields, invoices.get(r.order_id), invoice_fields),
		}
		for r in rows
	]


def count_sales_orders(
	id_field: str,
	search: str | None = None,
	status: str | None = None,
	filter_fields: dict[str, str] | None = None,
	filters: dict[str, str] | None = None,
) -> int:
	"""Row count for :func:`recent_sales_orders`, matching its search/status/filter rules."""
	if not _has_field("Sales Order", id_field):
		return 0
	_so, query = _sales_order_query(id_field, search, status, filter_fields, filters)
	return query.select(Count("*")).run()[0][0]


def invoices_for_orders(id_field: str, order_ids: list[str]) -> dict[str, str]:
	"""Map provider order ID -> latest non-return, non-cancelled Sales Invoice."""
	return {order_id: row["name"] for order_id, row in _latest_invoices(id_field, order_ids).items()}


def _latest_invoices(id_field: str, order_ids: list[str], extra_fields=()) -> dict[str, dict]:
	"""Latest non-return, non-cancelled Sales Invoice per provider order ID."""
	if not order_ids or not _has_field("Sales Invoice", id_field):
		return {}
	extra_fields = [f for f in extra_fields if _has_field("Sales Invoice", f)]

	si = frappe.qb.DocType("Sales Invoice")
	rows = (
		frappe.qb.from_(si)
		.select(si[id_field].as_("order_id"), si.name, *(si[f].as_(f) for f in extra_fields))
		.where(si[id_field].isin(order_ids) & (si.docstatus < 2) & (si.is_return == 0))
		.orderby(si.creation)
		.run(as_dict=True)
	)
	# Oldest first, so the newest invoice wins.
	return {r.order_id: {"name": r.name, "fields": {f: r.get(f) for f in extra_fields}} for r in rows}


def _existing_fields(doctype: str, field_pairs) -> list[tuple[str, str]]:
	"""Drop (fieldname, label) pairs whose field is not on the doctype, so extras degrade quietly."""
	return [(f, label) for f, label in (field_pairs or []) if _has_field(doctype, f)]


def _row_details(order, extra_fields, invoice, invoice_fields) -> list[dict]:
	"""Non-empty facts for an order row: [{key, label, value}], extras first, then invoice fields."""
	values = [(fieldname, label, order.get(fieldname)) for fieldname, label in extra_fields]
	if invoice:
		values += [
			(fieldname, label, invoice["fields"].get(fieldname)) for fieldname, label in invoice_fields
		]
	return [
		{"key": fieldname, "label": label, "value": value}
		for fieldname, label, value in values
		if value not in (None, "")
	]


def _pending_invoice_query(
	id_field: str,
	cod_field: str | None,
	search: str | None,
	status: str | None,
	filter_fields: dict[str, str] | None = None,
	filters: dict[str, str] | None = None,
):
	"""Shared pending-payment query: submitted, non-return invoices with money outstanding."""
	si = frappe.qb.DocType("Sales Invoice")
	query = frappe.qb.from_(si).where(
		si[id_field].isnotnull()
		& (si[id_field] != "")
		& (si.docstatus == 1)
		& (si.is_return == 0)
		& (si.outstanding_amount > 0)
	)

	if status == COD_NOT_COLLECTED:
		if not cod_field:
			return si, None
		query = query.where(si[cod_field] == 1)
	elif status:
		query = query.where(si.status == status)
		if cod_field:
			query = query.where(si[cod_field] == 0)

	for key, fieldname in (filter_fields or {}).items():
		if (filters or {}).get(key) and _has_field("Sales Invoice", fieldname):
			query = query.where(si[fieldname] == filters[key])

	if search and search.strip():
		like = like_pattern(search)
		query = query.where(si.name.like(like) | si[id_field].like(like) | si.customer_name.like(like))
	return si, query


def pending_sales_invoices(
	id_field: str,
	limit: int,
	search: str | None = None,
	status: str | None = None,
	cod_field: str | None = None,
	extra_fields: list[tuple[str, str]] | None = None,
	filter_fields: dict[str, str] | None = None,
	filters: dict[str, str] | None = None,
) -> list[dict]:
	"""Submitted Sales Invoices with money outstanding, newest first, in the payment-row shape."""
	if not _has_field("Sales Invoice", id_field):
		return []
	cod_field = cod_field if _has_field("Sales Invoice", cod_field) else None
	extra_fields = _existing_fields("Sales Invoice", extra_fields)

	si, query = _pending_invoice_query(id_field, cod_field, search, status, filter_fields, filters)
	if query is None:
		return []

	fields = [
		si.name,
		si[id_field].as_("order_id"),
		si.customer_name,
		si.outstanding_amount,
		si.grand_total,
		si.currency,
		si.status,
		si.due_date,
		si.creation,
		*(si[fieldname].as_(fieldname) for fieldname, _label in extra_fields),
	]
	if cod_field:
		fields.append(si[cod_field].as_("is_cod"))

	rows = query.select(*fields).orderby(si.creation, order=Order.desc).limit(limit).run(as_dict=True)

	result = []
	for r in rows:
		cod = bool(r.get("is_cod"))
		status_label = COD_NOT_COLLECTED if cod else r.status
		if cod:
			note = frappe._("Cash on delivery · order {0}").format(r.order_id)
		elif r.outstanding_amount < r.grand_total:
			note = frappe._("{0} received").format(
				frappe.format_value(r.grand_total - r.outstanding_amount, "Currency", currency=r.currency)
			)
		else:
			note = frappe._("Due {0}").format(frappe.format_value(r.due_date, "Date")) if r.due_date else ""

		result.append(
			{
				"docname": r.name,
				"doctype": "Sales Invoice",
				"party": r.customer_name,
				"amount": r.outstanding_amount,
				"total": r.grand_total,
				"currency": r.currency,
				"status": status_label,
				"indicator": PAYMENT_INDICATORS.get(status_label, "orange"),
				"note": note,
				"created": r.creation,
				"details": _detail_facts(r, extra_fields),
			}
		)
	return result


def count_pending_sales_invoices(
	id_field: str,
	search: str | None = None,
	status: str | None = None,
	cod_field: str | None = None,
	filter_fields: dict[str, str] | None = None,
	filters: dict[str, str] | None = None,
) -> int:
	"""Row count for :func:`pending_sales_invoices`; 0 when the id/cod fields are missing."""
	if not _has_field("Sales Invoice", id_field):
		return 0
	cod_field = cod_field if _has_field("Sales Invoice", cod_field) else None
	_si, query = _pending_invoice_query(id_field, cod_field, search, status, filter_fields, filters)
	if query is None:
		return 0
	return query.select(Count("*")).run()[0][0]


def pending_sales_invoice_summary(
	id_field: str,
	filter_fields: dict[str, str] | None = None,
	filters: dict[str, str] | None = None,
) -> list[dict]:
	"""Outstanding amount and invoice count per currency."""
	if not _has_field("Sales Invoice", id_field):
		return []
	si, query = _pending_invoice_query(id_field, None, None, None, filter_fields, filters)
	return (
		query.select(si.currency, Sum(si.outstanding_amount).as_("amount"), Count("*").as_("count"))
		.groupby(si.currency)
		.run(as_dict=True)
	)


def _detail_facts(row, field_pairs) -> list[dict]:
	"""Non-empty extra facts for a row: [{key, label, value}]."""
	return [
		{"key": fieldname, "label": label, "value": row.get(fieldname)}
		for fieldname, label in field_pairs
		if row.get(fieldname) not in (None, "")
	]
