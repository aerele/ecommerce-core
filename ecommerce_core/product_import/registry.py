# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

"""Provider registry for the shared Product Sync page."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr

from ecommerce_core.product_import.adapter import ProductImportAdapter
from ecommerce_core.product_import.constants import (
	EVENT_NAME_PREFIX,
	HOOK_NAME,
	JOB_NAME_PREFIX,
)
from ecommerce_core.providers.base import BaseProviderAdapter
from ecommerce_core.providers.registry import load_hook_providers

REQUIRED_ADAPTER_METHODS = ("is_enabled", "sync_product")
OPTIONAL_ADAPTER_METHODS = (
	"get_products",
	"get_provider_count",
	"sync_all",
	"get_sync_status",
	"get_accounts",
)

LOGGER = "ecommerce_core.product_import"


def get_slug(integration: str) -> str:
	"""URL/job-safe slug for an integration name, e.g. "Medusa Connector" -> "medusa-connector"."""
	return re.sub(r"[^a-z0-9]+", "-", (integration or "").lower()).strip("-")


@dataclass
class ProductImportProvider:
	integration: str
	label: str
	adapter_path: str
	adapter: Any
	settings_doctype: str | None = None

	@property
	def slug(self) -> str:
		"""URL/job-safe slug of the integration name."""
		return get_slug(self.integration)

	@property
	def job_name(self) -> str:
		"""Frappe job name for bulk syncs; doubles as the per-provider lock identity."""
		return f"{JOB_NAME_PREFIX}.{self.slug}"

	@property
	def event_name(self) -> str:
		"""Realtime event name the page subscribes to for this provider's progress."""
		return f"{EVENT_NAME_PREFIX}.{self.slug}"

	@property
	def account_field(self) -> str | None:
		"""Ecommerce Item field holding the store account, when the connector is multi-store."""
		return getattr(self.adapter, "account_field", None)

	def get_accounts(self) -> list[dict]:
		"""Enabled store accounts ``[{"name", "label"}]``; empty for single-store connectors."""
		if not self.implements("get_accounts"):
			return []
		try:
			return list(self.adapter.get_accounts() or [])
		except Exception:
			frappe.logger(LOGGER).error(
				f"get_accounts() failed for provider {self.integration}: {frappe.get_traceback()}"
			)
			return []

	def job_name_for(self, account: str | None = None) -> str:
		"""Bulk job name (and lock identity) scoped to one store account when given."""
		return f"{self.job_name}.{get_slug(account)}" if account else self.job_name

	def event_name_for(self, account: str | None = None) -> str:
		"""Realtime progress event scoped to one store account when given."""
		return f"{self.event_name}.{get_slug(account)}" if account else self.event_name

	def account_filter(self, account: str | None = None) -> tuple[str, str] | None:
		"""``(fieldname, value)`` Ecommerce Item condition for an account, else None."""
		if account and self.account_field:
			return (self.account_field, account)
		return None

	@property
	def enabled(self) -> bool:
		"""Adapter's ``is_enabled()``, false (with an error log) if it raises."""
		try:
			return bool(self.adapter.is_enabled())
		except Exception:
			frappe.logger(LOGGER).error(
				f"is_enabled() failed for provider {self.integration}: {frappe.get_traceback()}"
			)
			return False

	@property
	def can_list_products(self) -> bool:
		"""Whether the page can page through the remote catalog (else it falls back to mappings)."""
		return self._supports("supports_listing", "get_products")

	@property
	def has_custom_bulk_sync(self) -> bool:
		"""True when the adapter manages its own ``sync_all`` job end to end."""
		return self._supports("supports_bulk", "sync_all")

	@property
	def supports_incremental(self) -> bool:
		"""True when the adapter can report a remote ``updated_at``, enabling incremental skip."""
		return self.implements("get_product_updated_at")

	def implements(self, method: str) -> bool:
		"""True when the adapter really provides an optional method (not the ABC stub)."""
		if isinstance(self.adapter, BaseProviderAdapter):
			return self.adapter.implements(method)
		return callable(getattr(self.adapter, method, None))

	def _supports(self, flag: str, method: str) -> bool:
		"""Capability by flag on ABC subclasses, else by presence of the duck-typed method."""
		if isinstance(self.adapter, ProductImportAdapter):
			return bool(getattr(self.adapter, flag))
		return callable(getattr(self.adapter, method, None))

	def as_dict(self) -> dict:
		"""JSON-safe provider descriptor for the Product Sync page's provider selector."""
		return {
			"integration": self.integration,
			"label": self.label,
			"slug": self.slug,
			"settings_doctype": self.settings_doctype,
			"enabled": self.enabled,
			"job_name": self.job_name,
			"event_name": self.event_name,
			"custom_bulk_sync": self.has_custom_bulk_sync,
			"can_list_products": self.can_list_products,
			"supports_incremental": self.supports_incremental,
			"supports_search": self._supports("supports_search", "get_products"),
			"accounts": self.get_accounts(),
		}


def get_rejected_providers() -> list[dict]:
	"""Hook entries that failed validation, as ``{"integration", "reason"}`` (for diagnostics)."""
	get_providers()
	return list(getattr(frappe.local, "_product_import_rejected", []))


def get_providers() -> list[ProductImportProvider]:
	"""All validated providers registered through the hook, memoized per request."""
	providers = getattr(frappe.local, "_product_import_providers", None)
	if providers is None:
		frappe.local._product_import_rejected = []
		frappe.local._product_import_providers = providers = _load_providers()
	return providers


def get_provider(integration: str) -> ProductImportProvider:
	"""Provider for an integration name; throws when no hook entry matches."""
	integration = cstr(integration).strip()
	for provider in get_providers():
		if provider.integration == integration:
			return provider
	frappe.throw(_("No Product Sync provider registered for integration {0}").format(integration))


def _load_providers() -> list[ProductImportProvider]:
	"""Build providers from hook entries, recording rejects and sorting by label."""
	providers: list[ProductImportProvider] = []

	for loaded in load_hook_providers(
		HOOK_NAME,
		required_methods=REQUIRED_ADAPTER_METHODS,
	):
		if not loaded.accepted:
			frappe.local._product_import_rejected.append(
				{"integration": loaded.integration or "?", "reason": loaded.reason}
			)
			continue

		entry = loaded.entry
		providers.append(
			ProductImportProvider(
				integration=cstr(entry.get("integration")).strip(),
				label=cstr(entry.get("label")).strip() or cstr(entry.get("integration")).strip(),
				adapter_path=cstr(entry.get("adapter")).strip(),
				adapter=loaded.adapter,
				settings_doctype=cstr(entry.get("settings_doctype")).strip() or None,
			)
		)

	providers.sort(key=lambda p: p.label.lower())
	return providers
