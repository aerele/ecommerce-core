// Copyright (c) 2026, Aerele Technologies and contributors
// For license information, please see license.txt

// Product Sync moved to the frappe-ui SPA at /ecommerce-core/product-sync.
// This Desk page only forwards existing bookmarks to the new UI.
frappe.pages["ecommerce-product-sync"].on_page_load = function (wrapper) {
	window.location.href = "/ecommerce-core/product-sync";
};
