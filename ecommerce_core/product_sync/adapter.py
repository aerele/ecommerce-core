# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

"""Base class for Product Sync adapters.

Connector apps subclass :class:`ProductSyncAdapter` and register it through the
``ecommerce_product_sync_providers`` hook (see ``docs/product_sync_adapter.md``).
Only ``is_enabled`` and ``sync_product`` are mandatory; every other method is
opt-in and advertised through a capability flag.

Capability flags default to "True when the subclass overrides the matching
method", so a connector rarely needs to set them by hand. Override the property
to force a value (for example to hide search for a store that cannot filter).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ProductSyncAdapter(ABC):
	"""Contract between a connector and the shared Product Sync page."""

	@abstractmethod
	def is_enabled(self) -> bool:
		"""Whether the integration is configured and switched on."""

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
		return self._overrides("get_products")

	@property
	def supports_search(self) -> bool:
		return self.supports_listing

	@property
	def supports_bulk(self) -> bool:
		return self._overrides("sync_all")

	@property
	def supports_incremental(self) -> bool:
		return self._overrides("get_product_updated_at")

	def _overrides(self, method: str) -> bool:
		return getattr(type(self), method) is not getattr(ProductSyncAdapter, method)
