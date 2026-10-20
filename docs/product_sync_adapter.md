# Product Sync adapters

The Product Sync page (`Ecommerce Product Sync`) in `ecommerce_core` is provider-agnostic.
A connector app plugs in with a hook entry and one adapter class.

## 1. Register the provider

```python
# <provider>_connector/hooks.py
ecommerce_product_sync_providers = [
	{
		"integration": "Shopify",  # must equal the connector's Module Def name and Ecommerce Item.integration
		"label": "Shopify",
		"settings_doctype": "Shopify Settings",
		"adapter": "shopify_integration.product_sync.ShopifyProductSyncAdapter",
	}
]
```

`integration` must match an existing **Module Def** name. Providers that fail validation are
skipped and listed in a warning banner on the page (System Manager only) and in the
`ecommerce_core.product_sync` log.

## 2. Write the adapter

Subclass `ecommerce_core.product_sync.adapter.ProductSyncAdapter`.

| Method | Required | Purpose |
| --- | --- | --- |
| `is_enabled()` | yes | integration configured and on |
| `sync_product(product_id)` | yes | create/update Item(s); return `{"action": "created"\|"updated"\|"skipped"}`; raise on failure |
| `get_products(limit, cursor, search)` | no | one catalog page: `{"products": [{id, name, sku, variants?}], "total": int\|None, "next_cursor": str\|None}` |
| `get_provider_count()` | no | remote total for the stats cards |
| `sync_all(search)` | no | replace the generic bulk runner with your own job |
| `get_sync_status()` | no | `{"running": bool}` for your own job |
| `get_product_updated_at(product)` | no | remote last-modified datetime, enables incremental skip |

Capability flags (`supports_listing`, `supports_search`, `supports_bulk`, `supports_incremental`)
are derived from which optional methods you override; override the property to force a value.

Cursors are opaque strings: use whatever your API gives you (Shopify `page_info`, Medusa `o:<offset>`).
Without `get_products` the page shows the generic "mapped items" view built from `Ecommerce Item`.

Keep `__init__` cheap: adapters are instantiated on every request. Create API clients lazily.

## 3. Example (Shopify)

```python
import frappe
from ecommerce_core.product_sync.adapter import ProductSyncAdapter


class ShopifyProductSyncAdapter(ProductSyncAdapter):
	def is_enabled(self) -> bool:
		return bool(frappe.db.get_single_value("Shopify Settings", "enable_shopify"))

	def get_products(self, limit, cursor=None, search=None):
		page = shopify_client().list_products(limit=limit, page_info=cursor, title=search)
		return {
			"products": [
				{"id": str(p["id"]), "name": p["title"], "sku": (p["variants"] or [{}])[0].get("sku")}
				for p in page["products"]
			],
			"total": None,
			"next_cursor": page.get("next_page_info"),
		}

	def sync_product(self, product_id):
		item = sync_shopify_product(product_id)
		return {"action": item.action, "item_code": item.item_code}
```

## Behaviour you get for free

Sync state (synced / unsynced / broken) from `Ecommerce Item`, search, filters, stats, single sync,
selected sync, Sync All (honouring search and sync-state filter), one Integration Log per run,
throttled realtime progress, and a cache lock preventing concurrent runs per provider.
