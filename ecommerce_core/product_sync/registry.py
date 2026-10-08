# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

"""Provider registry for the shared Product Sync page.

Connector apps register a provider adapter through the
``ecommerce_product_sync_providers`` hook::

	# <provider_connector>/hooks.py
	ecommerce_product_sync_providers = [
		{
			"integration": "Medusa Connector",  # Ecommerce Item.integration value
			"label": "Medusa",
			"settings_doctype": "Medusa Settings",
			"adapter": "medusa_connector.product_sync.MedusaProductSyncAdapter",
		}
	]

An adapter is a plain class instantiated once per request. Contract:

	Required:
		is_enabled() -> bool
		sync_product(product_id) -> dict  # {"action": "created"|"updated"|"skipped", ...}

	Optional:
		get_products(limit, cursor=None, search=None) -> dict
			# {"products": [{id, name, sku, variants?, ...}], "total": int|None,
			#  "next_cursor": str|None}
			# When absent, the page falls back to the generic mapped-items view.
		get_provider_count() -> int
		sync_all(search=None) -> dict  # custom bulk job; returns {"status": "Queued", ...}
		get_sync_status() -> dict  # {"running": bool}

The registry never raises for one broken provider — it logs and skips it so a
single misconfigured connector cannot take the page down.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr

from ecommerce_core.product_sync.constants import (
	EVENT_NAME_PREFIX,
	HOOK_NAME,
	JOB_NAME_PREFIX,
)

REQUIRED_ADAPTER_METHODS = ("is_enabled", "sync_product")
OPTIONAL_ADAPTER_METHODS = ("get_products", "get_provider_count", "sync_all", "get_sync_status")

LOGGER = "ecommerce_core.product_sync"


def get_slug(integration: str) -> str:
	"""URL/job-safe slug for an integration name, e.g. "Medusa Connector" -> "medusa-connector"."""
	return re.sub(r"[^a-z0-9]+", "-", (integration or "").lower()).strip("-")


@dataclass
class ProductSyncProvider:
	integration: str
	label: str
	adapter_path: str
	adapter: Any
	settings_doctype: str | None = None

	@property
	def slug(self) -> str:
		return get_slug(self.integration)

	@property
	def job_name(self) -> str:
		return f"{JOB_NAME_PREFIX}.{self.slug}"

	@property
	def event_name(self) -> str:
		return f"{EVENT_NAME_PREFIX}.{self.slug}"

	@property
	def enabled(self) -> bool:
		try:
			return bool(self.adapter.is_enabled())
		except Exception:
			frappe.logger(LOGGER).error(
				f"is_enabled() failed for provider {self.integration}: {frappe.get_traceback()}"
			)
			return False

	@property
	def can_list_products(self) -> bool:
		return callable(getattr(self.adapter, "get_products", None))

	@property
	def has_custom_bulk_sync(self) -> bool:
		return callable(getattr(self.adapter, "sync_all", None))

	def as_dict(self) -> dict:
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
		}


def get_providers() -> list[ProductSyncProvider]:
	"""All validated providers registered through the hook, memoized per request."""
	providers = getattr(frappe.local, "_product_sync_providers", None)
	if providers is None:
		providers = frappe.local._product_sync_providers = _load_providers()
	return providers


def get_provider(integration: str) -> ProductSyncProvider:
	integration = cstr(integration).strip()
	for provider in get_providers():
		if provider.integration == integration:
			return provider
	frappe.throw(_("No Product Sync provider registered for integration {0}").format(integration))


def _load_providers() -> list[ProductSyncProvider]:
	providers: list[ProductSyncProvider] = []
	seen: set[str] = set()

	for entry in frappe.get_hooks(HOOK_NAME):
		provider = _build_provider(entry)
		if not provider:
			continue
		if provider.integration in seen:
			frappe.logger(LOGGER).warning(
				f"Duplicate Product Sync provider registration for {provider.integration}; skipping"
			)
			continue
		seen.add(provider.integration)
		providers.append(provider)

	providers.sort(key=lambda p: p.label.lower())
	return providers


def _build_provider(entry) -> ProductSyncProvider | None:
	if not isinstance(entry, dict):
		frappe.logger(LOGGER).warning(f"Ignoring malformed {HOOK_NAME} entry: {entry!r}")
		return None

	integration = cstr(entry.get("integration")).strip()
	label = cstr(entry.get("label")).strip() or integration
	adapter_path = cstr(entry.get("adapter")).strip()
	settings_doctype = cstr(entry.get("settings_doctype")).strip() or None

	if not integration or not adapter_path:
		frappe.logger(LOGGER).warning(
			f"Ignoring incomplete {HOOK_NAME} entry: 'integration' and 'adapter' are required"
		)
		return None

	if not frappe.db.exists("Module Def", integration):
		frappe.logger(LOGGER).warning(
			f"Ignoring Product Sync provider {integration}: not a Module Def"
		)
		return None

	if settings_doctype and not frappe.db.exists("DocType", settings_doctype):
		frappe.logger(LOGGER).warning(
			f"Ignoring Product Sync provider {integration}: settings DocType {settings_doctype} not found"
		)
		return None

	try:
		adapter_cls = frappe.get_attr(adapter_path)
		adapter = adapter_cls()
	except Exception:
		frappe.logger(LOGGER).warning(
			f"Product Sync adapter {adapter_path} failed to load: {frappe.get_traceback()}"
		)
		return None

	missing = [m for m in REQUIRED_ADAPTER_METHODS if not callable(getattr(adapter, m, None))]
	if missing:
		frappe.logger(LOGGER).warning(
			f"Product Sync adapter {adapter_path} is missing required method(s): {', '.join(missing)}"
		)
		return None

	return ProductSyncProvider(
		integration=integration,
		label=label,
		adapter_path=adapter_path,
		adapter=adapter,
		settings_doctype=settings_doctype,
	)
