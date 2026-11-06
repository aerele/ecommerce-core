import { useCall } from "frappe-ui"

const API = "ecommerce_core.product_sync.api"

// Registered Product Sync providers (read once on page load).
export const providersResource = useCall({ url: `/api/v2/method/${API}.get_providers` })

// Hook entries that were rejected at load time (shown as a diagnostics banner).
export const diagnosticsResource = useCall({ url: `/api/v2/method/${API}.get_provider_diagnostics` })

// One page of products (cursor pagination handled by the caller).
export const productsResource = useCall({
  url: `/api/v2/method/${API}.get_products`,
  immediate: false,
})

// Sync statistics for one integration.
export const statsResource = useCall({
  url: `/api/v2/method/${API}.get_stats`,
  immediate: false,
})

// Running / enabled / event-name state for one integration.
export const syncStatusResource = useCall({
  url: `/api/v2/method/${API}.get_sync_status`,
  immediate: false,
})

// Single product sync (write shape).
export const syncProductResource = useCall({
  url: `/api/v2/method/${API}.sync_product`,
  method: "POST",
  immediate: false,
})

// Bulk sync: full catalog or the current filter.
export const syncAllResource = useCall({
  url: `/api/v2/method/${API}.sync_all`,
  method: "POST",
  immediate: false,
})

// Bulk sync restricted to selected product ids.
export const syncSelectedResource = useCall({
  url: `/api/v2/method/${API}.sync_selected`,
  method: "POST",
  immediate: false,
})
