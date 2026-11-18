# Ecommerce Dashboard

A single, provider-neutral dashboard page (`ecommerce-dashboard`, linked from the Ecommerce Core
workspace) that shows what is happening across every ecommerce integration — Unicommerce,
Shopify, Medusa, or any connector built on Ecommerce Core.

## What you see

| Widget | Shows | Data source |
| --- | --- | --- |
| Provider tabs | All Integrations (combined) or one connector at a time | dashboard provider registry |
| Stat tiles | Enabled/registered integrations, mapped items, inventory synced in 24h, failed syncs in the last 7 days, pending payments, and clearly labelled inventory alerts. A tile opens the matching section tab with its filter applied | Ecommerce Item + Ecommerce Integration Log (owned by Ecommerce Core), adapters for pending totals |
| Latest Orders | Paginated, searchable orders: platform, order ID, customer, amount, status, invoice and exact creation date/time — the order and invoice open their ERPNext documents, and connectors can add platform columns (channel, facility code, tracking number, package status…) plus extra filters (e.g. Channel and Facility Code) | each connector's dashboard adapter |
| Pending Payments | Paginated, searchable unpaid / partly paid / overdue / COD-not-collected invoices, newest first | each connector's dashboard adapter |
| Sync Logs | All sync logs with success/failure/status filters, title search and pagination; each title opens the full log | Ecommerce Integration Log |
| Items & Inventory | Every mapped sellable item with on-hand, reserved-for-orders and available-to-sell quantities in the connector's mapped warehouses, clear inventory status filters, exact last-sync date/time and a Push stock action | Ecommerce Item + Bin + Item Reorder (owned by Ecommerce Core / ERPNext) |

The page auto-refreshes every 30 seconds (pause/resume from the page header) and is System
Manager only, like the other shared Ecommerce Core tooling.

## The page itself

`ecommerce-dashboard` is a Frappe UI page (a Vue island built by the framework): the page
folder holds `ecommerce_dashboard.island.js` (the mount entry) and `ecommerce_dashboard.vue`
(the whole UI, written with frappe-ui components). It talks only to the whitelisted
`ecommerce_core.dashboard.api` methods, so the backend is unchanged by the frontend choice.

Building it needs the framework's island toolchain, once per bench:

```sh
yarn install --cwd apps/frappe/ui/vite/island/toolchain
bench build
```

## How connectors plug in

A connector registers itself through the `ecommerce_dashboard_providers` hook. Nothing
provider-specific ever goes into Ecommerce Core.

```python
# <provider_connector>/<provider_connector>/hooks.py
ecommerce_dashboard_providers = [
	{
		"integration": "Medusa Connector",  # Module Def / Ecommerce Item.integration value
		"label": "Medusa",
		"settings_doctype": "Medusa Settings",
		"adapter": "medusa_connector.dashboard.MedusaDashboardAdapter",
	}
]
```

The adapter is a small class instantiated per request (subclass
`ecommerce_core.dashboard.adapter.DashboardAdapter`):

| Method | Required | Returns |
| --- | --- | --- |
| `is_enabled()` | ✔ | whether the connector is configured and switched on |
| `get_recent_orders(limit, search, status, filters)` | optional | latest orders: `{id, docname, doctype, customer, amount, currency, status, indicator, created, invoice?, details?}` — `details` is `[{label, value}]` connector facts with provider-neutral labels, shown under the order; `filters` carries the selected values of the extra order filters |
| `count_orders(search, status, filters)` | optional | total matching orders, for exact pagination |
| `get_order_filter_options()` | optional | extra dropdown filters for the orders widget: `[{key, label, options: [(value, label)]}]` (Unicommerce declares Channel and Facility Code filters); providers that don't declare an active key are skipped while it's selected |
| `get_order_columns()` | optional | extra columns for the orders widget: `[{key, label, width?}]`, `key` matching a `details` key (Unicommerce declares channel, facility code, platform invoice, package, shipping provider/method, tracking number and package status) |
| `get_pending_payments(limit, search, status)` | optional | pending money: `{docname, doctype, party, amount, currency, status, indicator, note, created, total?}` |
| `count_pending_payments(search, status)` | optional | total matching pending payments |
| `get_pending_summary()` | optional | `[{currency, amount, count}]` for the Pending payments tile |
| `push_inventory(ecommerce_items)` | optional | queues a stock push for the given Ecommerce Items, returns a message |

Connectors that tag Sales Orders / Sales Invoices with an order-ID custom field can implement the
order and payment methods in a few lines with the helpers in `ecommerce_core.dashboard.queries`.
`recent_sales_orders` also takes `extra_fields` / `invoice_fields` — `(fieldname, label)` pairs
read from the Sales Order and its latest Sales Invoice — and returns them per order as
provider-neutral `details` (Unicommerce uses this for channel, facility, platform invoice,
package, shipping provider/method, tracking number and package status).

Adapters that don't implement the optional methods simply don't feed those widgets — the stat
tiles, items and sync logs still work for every connector, registered or not, because they read
Ecommerce Core's own data. Stock is read from the warehouses returned by the connector settings'
`get_erpnext_warehouses()` (group warehouses include their children); without settings, all
warehouses are used. A broken or missing adapter never takes the page down; it is skipped and
reported in a notice at the top of the page.
