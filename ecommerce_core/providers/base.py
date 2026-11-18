# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

"""Single adapter base shared by every Ecommerce Core connector contract.

A connector exposes one adapter class per feature (dashboard, product import),
but all of them share this base: ``is_enabled`` plus ``implements`` /
``overrides`` for detecting optional methods, so the registries and the pages
treat every adapter the same way.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseProviderAdapter(ABC):
	#: Hook entry this adapter was registered with; set by the registry after instantiation.
	provider: dict

	@abstractmethod
	def is_enabled(self) -> bool:
		"""Whether the connector is configured and switched on."""

	def implements(self, method: str) -> bool:
		"""True when the adapter overrides an optional method of its contract.

		Locates the nearest ``__contract__`` class defining ``method`` and compares
		implementations, so ABC stubs never count as "implemented".
		"""
		cls = type(self)
		contract = next(
			(c for c in cls.__mro__ if c.__dict__.get("__contract__") and method in vars(c)), None
		)
		if contract is None:
			return callable(getattr(self, method, None))
		return getattr(cls, method) is not getattr(contract, method)
