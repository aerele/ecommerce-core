"""Base class for connector adapters that feed the Ecommerce Dashboard."""

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
		"""Latest orders, newest first."""
		raise NotImplementedError

	def count_orders(
		self, search: str | None = None, status: str | None = None, filters: dict[str, str] | None = None
	) -> int:
		"""Total orders matching the filters, used for pagination."""
		raise NotImplementedError

	def get_order_columns(self) -> list[dict]:
		"""Extra columns for the orders widget: [{key, label, width?}]."""
		raise NotImplementedError

	def get_order_filter_options(self) -> list[dict]:
		"""Extra dropdown filters for the orders widget."""
		raise NotImplementedError

	def get_pending_payments(
		self, limit: int, search: str | None = None, status: str | None = None
	) -> list[dict]:
		"""Money still to be collected, newest first."""
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
