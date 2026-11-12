"""Discovers connectors registered through the ``ecommerce_dashboard_providers`` hook."""

from dataclasses import dataclass, field

import frappe
from frappe import _

from ecommerce_core.dashboard.adapter import DashboardAdapter

HOOK_NAME = "ecommerce_dashboard_providers"
REQUIRED_KEYS = ("integration", "label", "adapter")


@dataclass
class Provider:
	integration: str
	label: str
	settings_doctype: str | None
	adapter: DashboardAdapter | None = None
	enabled: bool = False
	problem: str | None = None

	def as_dict(self) -> dict:
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
	seen = set()

	for entry in frappe.get_hooks(HOOK_NAME) or []:
		if not isinstance(entry, dict) or any(not entry.get(k) for k in REQUIRED_KEYS):
			registry.problems.append(_("Ignored an invalid {0} hook entry: {1}").format(HOOK_NAME, entry))
			continue
		if entry["integration"] in seen:
			continue
		seen.add(entry["integration"])

		provider = Provider(
			integration=entry["integration"],
			label=entry["label"],
			settings_doctype=entry.get("settings_doctype"),
		)
		registry.providers.append(provider)

		try:
			adapter = frappe.get_attr(entry["adapter"])()
			if not isinstance(adapter, DashboardAdapter):
				raise TypeError(_("{0} must subclass DashboardAdapter").format(entry["adapter"]))
			adapter.provider = entry
			provider.adapter = adapter
			provider.enabled = bool(adapter.is_enabled())
		except Exception as e:
			provider.problem = _("{0} adapter skipped: {1}").format(provider.label, e)
			frappe.log_error(title=_("Ecommerce Dashboard adapter failed"))

	return registry


def call_adapter(provider: Provider, method: str, problems: list[str], default, **kwargs):
	"""Call an optional adapter method; failures are logged and reported instead of raised."""
	try:
		return getattr(provider.adapter, method)(**kwargs)
	except Exception as e:
		problems.append(_("{0}: {1} failed ({2})").format(provider.label, method, e))
		frappe.log_error(title=_("Ecommerce Dashboard: {0}.{1} failed").format(provider.label, method))
		return default
