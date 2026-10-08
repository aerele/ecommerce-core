# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

"""Desk page: shared Product Sync across ecommerce integrations.

The page is generic — providers register themselves through the
``ecommerce_product_sync_providers`` hook and all endpoints live in
``ecommerce_core.product_sync.api``. This module only exists because Frappe
Pages expect a sibling Python file.
"""
