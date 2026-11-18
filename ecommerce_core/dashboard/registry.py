"""Discovers connectors registered through the ``ecommerce_dashboard_providers`` hook.

Loading rules (validation, Module Def check, broken-adapter isolation, request
memoization) live in ``ecommerce_core.providers.registry``; this module maps
the results onto the dashboard's ``Provider`` objects and calls adapters
through :func:`call_adapter`, which turns one failing widget into a reported
problem instead of a broken page.
"""

import hashlib
from dataclasses import dataclass, field

import frappe
from frappe import _

from ecommerce_core.dashboard.adapter import DashboardAdapter
from ecommerce_core.providers.registry import load_hook_providers

HOOK_NAME = "ecommerce_dashboard_providers"
REQUIRED_METHODS = ("is_enabled",)


@dataclass
class Provider:
	integration: str
	label: str
	settings_doctype: str | None
	adapter: DashboardAdapter | None = None
	enabled: bool = False
	problem: str | None = None

	def as_dict(self) -> dict:
		"""JSON-safe view of the provider, without the adapter object reference."""
		return {
			"integration": self.integration,
			"label": self.label,
			"settings_doctype": self.settings_doctype,
			"enabled": self.enabled,
			"problem": self.problem,
		}


@dataclass
class Registry:
	providers: list[Provider] = field(default_factory=list)
	problems: list[str] = field(default_factory=list)

	def get(self, integration: str | None) -> Provider | None:
		"""Look up a provider by integration name; None when unknown."""
		return next((p for p in self.providers if p.integration == integration), None)

	def scoped(self, integration: str | None) -> list[Provider]:
		"""All providers for the combined view, or just the selected one."""
		if not integration:
			return self.providers
		provider = self.get(integration)
		return [provider] if provider else []

	def active(self, integration: str | None, method: str) -> list[Provider]:
		"""Enabled providers in scope whose adapter implements ``method``."""
		return [
			p for p in self.scoped(integration) if p.enabled and p.adapter and p.adapter.implements(method)
		]


def load_registry() -> Registry:
	"""Instantiate every registered adapter. A broken adapter is skipped and reported, never raised."""
	registry = Registry()

	for loaded in load_hook_providers(
		HOOK_NAME, adapter_base=DashboardAdapter, required_methods=REQUIRED_METHODS
	):
		if not loaded.accepted:
			registry.problems.append(
				_("Ignored a {0} entry for {1}: {2}").format(
					HOOK_NAME, loaded.integration or "?", loaded.reason
				)
			)
			continue

		entry = loaded.entry
		provider = Provider(
			integration=entry["integration"],
			label=entry["label"],
			settings_doctype=entry.get("settings_doctype"),
		)
		registry.providers.append(provider)

		adapter = loaded.adapter
		adapter.provider = entry
		provider.adapter = adapter
		try:
			provider.enabled = bool(adapter.is_enabled())
		except Exception as e:
			provider.problem = _("{0} adapter skipped: {1}").format(provider.label, e)
			frappe.log_error(title=_("Ecommerce Dashboard adapter failed"))

	return registry


ERROR_LOG_THROTTLE_SECONDS = 300


def call_adapter(provider: Provider, method: str, problems: list[str], default, **kwargs):
	"""Call an optional adapter method; failures are logged and reported instead of raised.

	The client only sees a generic message (no raw exception text), and the Error Log entry
	is throttled per provider/method so a failing provider cannot flood the table.
	"""
	try:
		return getattr(provider.adapter, method)(**kwargs)
	except Exception as exc:
		problems.append(_("{0}: {1} failed. See Error Log for details.").format(provider.label, method))
		# Throttle repeats of the *same* error; a different failure is still logged.
		signature = hashlib.md5(f"{type(exc).__name__}:{str(exc)[:200]}".encode()).hexdigest()[:12]
		key = f"ecommerce_core:dashboard_error:{provider.integration}:{method}:{signature}"
		if not frappe.cache.get_value(key):
			frappe.cache.set_value(key, 1, expires_in_sec=ERROR_LOG_THROTTLE_SECONDS)
			frappe.log_error(title=_("Ecommerce Dashboard: {0}.{1} failed").format(provider.label, method))
		return default
