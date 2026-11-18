"""Base class for connector adapters that feed the Ecommerce Dashboard.

A connector registers its adapter through the ``ecommerce_dashboard_providers`` hook:

	ecommerce_dashboard_providers = [
		{
			"integration": "Medusa Connector",  # Module Def / Ecommerce Item.integration value
			"label": "Medusa",
			"settings_doctype": "Medusa Settings",
			"adapter": "medusa_connector.dashboard.MedusaDashboardAdapter",
		}
	]

The adapter is instantiated once per request. Only ``is_enabled`` is required; every other
method is optional and simply leaves its widget empty for that connector when not overridden.
"""

from ecommerce_core.providers.base import BaseProviderAdapter


class DashboardAdapter(BaseProviderAdapter):
	__contract__ = True

	def get_recent_orders(
		self,
		limit: int,
		search: str | None = None,
		status: str | None = None,
		filters: dict[str, str] | None = None,
	) -> list[dict]:
		"""Latest orders, newest first.

		Each row: {id, docname, doctype, customer, amount, currency, status, indicator, created}
		plus optional ``invoice`` (Sales Invoice name billed for the order) and ``details``
		([{key, label, value}, ...] connector-specific facts, with provider-neutral labels,
		rendered as the columns declared by ``get_order_columns``). ``filters`` carries the
		selected values of the extra order filters declared by ``get_order_filter_options``.
		"""
		raise NotImplementedError

	def count_orders(
		self, search: str | None = None, status: str | None = None, filters: dict[str, str] | None = None
	) -> int:
		"""Total orders matching the filters, used for pagination."""
		raise NotImplementedError

	def get_order_columns(self) -> list[dict]:
		"""Extra columns for the orders widget: [{key, label, width?}].

		``key`` must match a ``details`` key returned by ``get_recent_orders``. Connectors
		that don't implement this get no extra columns.
		"""
		raise NotImplementedError

	def get_order_filter_options(self) -> list[dict]:
		"""Extra dropdown filters for the orders widget.

		Returns [{key, label, options: [(value, label), ...]}]. Connectors that don't
		implement this simply get no extra filter; ``key`` must match the ``filters``
		keys understood by ``get_recent_orders`` / ``count_orders``.
		"""
		raise NotImplementedError

	def get_pending_payments(
		self, limit: int, search: str | None = None, status: str | None = None
	) -> list[dict]:
		"""Money still to be collected, newest first.

		Each row: {docname, doctype, party, amount, currency, status, indicator, note, created}
		plus optional ``total`` (document grand total).
		"""
		raise NotImplementedError

	def count_pending_payments(self, search: str | None = None, status: str | None = None) -> int:
		"""Total pending payments matching the filters, used for pagination."""
		raise NotImplementedError

	def get_pending_summary(self) -> list[dict]:
		"""Outstanding totals grouped by currency: [{currency, amount, count}]."""
		raise NotImplementedError

	def push_inventory(self, ecommerce_items: list[str]) -> str:
		"""Queue a stock push for the given Ecommerce Item names; returns a user-facing message."""
		raise NotImplementedError
