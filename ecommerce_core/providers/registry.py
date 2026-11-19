# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

"""Shared loader for connector provider registries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import frappe
from frappe.utils import cstr


@dataclass
class LoadedProvider:
	"""One hook entry's outcome: its raw entry, its adapter, or why it was skipped."""

	entry: dict
	adapter: Any | None = None
	reason: str | None = None  # set when the entry was rejected

	@property
	def accepted(self) -> bool:
		"""True when the hook entry passed validation and carries an adapter."""
		return self.reason is None

	@property
	def integration(self) -> str:
		"""Integration name from the raw hook entry (empty for malformed entries)."""
		return cstr(self.entry.get("integration")).strip() if isinstance(self.entry, dict) else ""


def load_hook_providers(
	hook_name: str,
	*,
	adapter_base: type | None = None,
	required_methods: tuple[str, ...] = (),
) -> list[LoadedProvider]:
	"""Resolve every hook entry into a LoadedProvider, memoized per request."""
	cache_key = f"_ecommerce_providers_{hook_name}"
	loaded = getattr(frappe.local, cache_key, None)
	if loaded is not None:
		return loaded

	loaded = _load(hook_name, adapter_base, required_methods)
	setattr(frappe.local, cache_key, loaded)
	return loaded


def _load(hook_name: str, adapter_base: type | None, required_methods: tuple[str, ...]) -> list:
	"""Build every hook entry, rejecting duplicate registrations and logging rejects."""
	out: list[LoadedProvider] = []
	seen: set[str] = set()

	for entry in frappe.get_hooks(hook_name) or []:
		provider = _build(entry, hook_name, adapter_base, required_methods)
		if provider.accepted and provider.integration in seen:
			provider = LoadedProvider(
				entry=provider.entry, reason=f"duplicate registration for {provider.integration}"
			)
		if provider.reason:
			frappe.logger(hook_name).warning(f"Ignoring {hook_name} provider: {provider.reason}")
		else:
			seen.add(provider.integration)
		out.append(provider)

	return out


def _build(
	entry, hook_name: str, adapter_base: type | None, required_methods: tuple[str, ...]
) -> LoadedProvider:
	"""Validate one hook entry and instantiate its adapter."""
	if not isinstance(entry, dict):
		return LoadedProvider(entry={}, reason=f"malformed hook entry (expected a dict): {entry}")

	integration = cstr(entry.get("integration")).strip()
	adapter_path = cstr(entry.get("adapter")).strip()
	settings_doctype = cstr(entry.get("settings_doctype")).strip() or None

	if not integration or not adapter_path:
		return LoadedProvider(entry=entry, reason="'integration' and 'adapter' are required")

	if not frappe.db.exists("Module Def", integration):
		return LoadedProvider(
			entry=entry,
			reason=f"integration must equal an existing Module Def name, got {integration!r}",
		)

	if settings_doctype and not frappe.db.exists("DocType", settings_doctype):
		return LoadedProvider(entry=entry, reason=f"settings DocType {settings_doctype} not found")

	try:
		adapter_cls = frappe.get_attr(adapter_path)
		adapter = adapter_cls()
	except Exception:
		frappe.logger(hook_name).warning(f"Adapter {adapter_path} failed to load: {frappe.get_traceback()}")
		return LoadedProvider(entry=entry, reason=f"adapter {adapter_path} failed to load (see logs)")

	if adapter_base is not None and not isinstance(adapter, adapter_base):
		return LoadedProvider(entry=entry, reason=f"{adapter_path} must subclass {adapter_base.__name__}")

	missing = [m for m in required_methods if not callable(getattr(adapter, m, None))]
	if missing:
		return LoadedProvider(
			entry=entry, reason=f"adapter is missing required method(s): {', '.join(missing)}"
		)

	return LoadedProvider(entry=entry, adapter=adapter)
