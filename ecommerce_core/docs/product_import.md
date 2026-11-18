# Product Sync

A single, provider-neutral page (`ecommerce-product-import`, linked from the Ecommerce Core workspace) to
sync every connector's remote catalog into ERPNext Items and Ecommerce Item mappings —
Unicommerce, Shopify, Medusa, or any connector built on Ecommerce Core.

## What you see

| Widget | Shows | Data source |
| --- | --- | --- |
| Provider selector | All Integrations (combined list) or one connector at a time | product sync provider registry |
| Product list | Paginated, searchable provider products with SKU and sync state (Synced / Not Synced), with per-product Sync/Re-sync, item link and variant list | each connector's product sync adapter, enriched with Ecommerce Core status |
| Sync panel | Sync All (honours the active search/filter), connector settings link, and provider/mapped/synced stat tiles | adapter + Ecommerce Item |
| Progress panel | Realtime per-product trail of a bulk run (created / updated / skipped / failed) and the final summary | `frappe.publish_realtime` events |
| Selection sync | Bulk sync of up to 100 picked products; in All Integrations mode the selection is grouped per provider automatically | runner |

The page is System Manager only, like the other shared Ecommerce Core tooling.

## The page itself

`ecommerce-product-import` is a Frappe UI page (a Vue island built by the framework), exactly like
`ecommerce-dashboard`: the page folder holds `ecommerce_product_import.island.js` (the mount entry) and
`ecommerce_product_import.vue` (the whole UI, written with frappe-ui components). It talks only to the
whitelisted `ecommerce_core.product_import.api` methods, and realtime progress rides desk's own
`frappe.realtime` connection — no socket.io client of its own. Building it needs the
framework's island toolchain, once per bench:

```sh
yarn install --cwd apps/frappe/ui/vite/island/toolchain
bench build
```

Unlike the standalone `/ecommerce-core` SPA this page replaces, it renders inside the desk
shell, so the workspace sidebar, desk theme (including dark mode), breadcrumbs and CSRF
handling all come from the desk itself. The SPA's `frontend/`, `www` page and
`website_route_rules` are gone; `/ecommerce-core/ecommerce-product-import` no longer exists.

## How connectors plug in

A connector registers itself through the `ecommerce_product_import_providers` hook. Nothing
provider-specific ever goes into Ecommerce Core; the full adapter contract lives in
`docs/product_import_adapter.md`.

```python
# <provider_connector>/<provider_connector>/hooks.py
ecommerce_product_import_providers = [
	{
		"integration": "Medusa Connector",  # Module Def / Ecommerce Item.integration value
		"label": "Medusa",
		"settings_doctype": "Medusa Settings",
		"adapter": "medusa_connector.product_import.MedusaProductImportAdapter",
	}
]
```

Only `is_enabled()` and `sync_product(product_id)` are mandatory. Optional methods unlock
more of the page: `get_products(...)` (real catalog listing with cursor pagination and
search), `get_provider_count()`, `sync_all(search=None)` (custom bulk job), `get_sync_status()`
and `get_product_updated_at()` (incremental skip). Without `get_products`, the page falls back
to the generic mapped-items view built from Ecommerce Item, so every registered connector is
still usable. Adapters are validated at load; a broken one is skipped and reported in the
page's "Ignored integrations" banner instead of taking the page down.

## Incremental sync

Providers whose adapter implements `get_product_updated_at` (Shopify, Medusa)
only re-sync changed products on *Sync All*; tick "Full re-sync" to force all.
Unicommerce does not expose an item modified time, so it always syncs fully.
