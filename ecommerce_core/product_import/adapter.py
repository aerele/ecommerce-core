# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

"""Base class for Product Sync adapters.

Connector apps subclass :class:`ProductImportAdapter` and register it through the
``ecommerce_product_import_providers`` hook (see ``docs/product_import_adapter.md``).
Only ``is_enabled`` and ``sync_product`` are mandatory; every other method is
opt-in and advertised through a capability flag.

Capability flags default to "True when the subclass overrides the matching
method", so a connector rarely needs to set them by hand. Override the property
to force a value (for example to hide search for a store that cannot filter).
"""

from __future__ import annotations

from abc import abstractmethod

from ecommerce_core.providers.base import BaseProviderAdapter


class ProductImportAdapter(BaseProviderAdapter):
	"""Contract between a connector and the shared Product Import page."""

	__contract__ = True

	@abstractmethod
	def sync_product(self, product_id: str) -> dict:
		"""Create or update the ERPNext Item(s) for one remote product.

		Return ``{"action": "created" | "updated" | "skipped", ...}``. Raise on failure.
		"""

	# -- optional -----------------------------------------------------------------

	def get_products(self, limit: int, cursor: str | None = None, search: str | None = None) -> dict:
		"""One page of the remote catalog.

		Return ``{"products": [{id, name, sku, variants?}], "total": int | None,
		"next_cursor": str | None}``. The cursor is opaque to core.
		"""
		raise NotImplementedError

	def get_provider_count(self) -> int:
		"""Total number of remote products (for the stats cards)."""
		raise NotImplementedError

	def sync_all(self, search: str | None = None) -> dict:
		"""Custom bulk job. Return ``{"status": "Queued", ...}``."""
		raise NotImplementedError

	def get_sync_status(self) -> dict:
		"""``{"running": bool}`` for adapters that manage their own bulk job."""
		raise NotImplementedError

	def get_product_updated_at(self, product: dict):
		"""Remote last-modified datetime of a listed product (enables incremental skip)."""
		raise NotImplementedError

	# -- capability flags ---------------------------------------------------------

	@property
	def supports_listing(self) -> bool:
		"""True when the subclass overrides ``get_products``."""
		return self.implements("get_products")

	@property
	def supports_search(self) -> bool:
		"""True when listing is supported and the store can filter remotely."""
		return self.supports_listing

	@property
	def supports_bulk(self) -> bool:
		"""True when the subclass overrides ``sync_all``."""
		return self.implements("sync_all")

	@property
	def supports_incremental(self) -> bool:
		"""True when the subclass overrides ``get_product_updated_at``."""
		return self.implements("get_product_updated_at")
