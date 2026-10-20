# Copyright (c) 2026, Aerele Technologies and contributors
# For license information, please see license.txt

"""Constants for the shared Product Sync page."""

HOOK_NAME = "ecommerce_product_sync_providers"

JOB_NAME_PREFIX = "ecommerce_core.product_sync"
EVENT_NAME_PREFIX = "ecommerce_core.product_sync"

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
BULK_PAGE_SIZE = 100
BULK_SYNC_QUEUE = "long"
BULK_SYNC_TIMEOUT = 3600
MAX_SELECTED_SYNC = 100

# Adapter pages scanned per request when a sync-status filter is active, to
# bound request latency; pagination resumes the scan via envelope cursors.
FILTER_SCAN_PAGE_LIMIT = 50

# Core-side filters applied on the enriched rows, not on the provider catalog.
SYNC_FILTERS = ("synced", "unsynced", "broken")

# Normalized outcomes an adapter's sync_product() may report.
SYNC_ACTIONS = ("created", "updated", "skipped")

# Minimum seconds between per-product realtime progress lines in a bulk run.
PROGRESS_THROTTLE_SECONDS = 0.75
