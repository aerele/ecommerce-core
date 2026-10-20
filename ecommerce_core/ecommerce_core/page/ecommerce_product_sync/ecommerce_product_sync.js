// Copyright (c) 2026, Aerele Technologies and contributors
// For license information, please see license.txt

// Shared Product Sync page. Providers register through the
// `ecommerce_product_sync_providers` hook; this page stays provider-agnostic.

const API = "ecommerce_core.product_sync.api";

frappe.pages["ecommerce-product-sync"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Product Sync"),
		single_column: true,
	});
	const syncPage = new ProductSyncPage(wrapper, page);
	wrapper.product_sync_page = syncPage;
};

class ProductSyncPage {
	constructor(wrapper, page) {
		this.wrapper = $(wrapper).find(".layout-main-section");
		this.page = page;
		this.providers = [];
		this.provider = null; // active provider dict from the registry
		this.limit = 20;
		this.cursorHistory = [null]; // cursors of visited pages; index == current page
		this.pageIndex = 0;
		this.nextCursor = null;
		this.total = null;
		this.allProducts = [];
		this.selectedIds = new Set();
		this.syncRunning = false;
		this._filterTimer = null;
		this._realtimeEvent = null;
		this.init();
	}

	async init() {
		this.addMarkup();
		this.bindActions();
		await this.loadProviders();
	}

	// ------------------------------------------------------------- markup

	addMarkup() {
		this.wrapper.addClass("eps-page-host");
		this.wrapper.closest(".layout-main-section-wrapper").addClass("eps-page-host-wrap");

		this.wrapper.append(`
			<style>
				.eps-page-host-wrap { display: flex; flex-direction: column; overflow: visible; }
				.eps-page-host { display: flex; flex-direction: column; }

				/* ---- Integration bar ---- */
				.eps-provider-bar {
					display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
					margin-bottom: 12px; padding: 10px 14px;
					background-color: var(--card-bg);
					border: 1px solid var(--border-color);
					border-radius: 8px;
				}
				.eps-provider-bar .eps-provider-label {
					flex: 0 0 auto; margin: 0; font-weight: 500;
					color: var(--text-muted); white-space: nowrap;
				}
				/* Frappe sets .form-control to width:100%, which broke the row */
				.eps-provider-bar select.form-control {
					flex: 0 0 auto; width: 260px; max-width: 100%; height: 28px;
				}
				.eps-provider-bar .eps-provider-state {
					flex: 0 0 auto; display: inline-flex; align-items: center;
				}
				.eps-provider-bar #eps-settings-link {
					margin-left: auto; flex: 0 0 auto;
					display: inline-flex; align-items: center; gap: 4px;
					padding: 4px 10px; border-radius: 6px;
					border: 1px solid var(--border-color);
					color: var(--text-color); text-decoration: none; white-space: nowrap;
					transition: background-color 0.15s;
				}
				.eps-provider-bar #eps-settings-link:hover {
					background-color: var(--control-bg, var(--bg-color));
				}
				@media (max-width: 576px) {
					.eps-provider-bar select.form-control { flex: 1 1 100%; width: 100%; }
					.eps-provider-bar #eps-settings-link { margin-left: 0; }
				}

				/* ---- Products grid ---- */
				.eps-page .row.eps-grid { display: flex; margin-left: 0; margin-right: 0; }
				.eps-page .row.eps-grid > [class*="col-"] { display: flex; flex-direction: column; min-height: 0; }
				.eps-page .eps-products-card { display: flex; flex-direction: column; }
				.eps-page .eps-products-card-header,
				.eps-page .eps-datatable-footer { flex: 0 0 auto; }
				.eps-page .eps-toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
				.eps-page .eps-toolbar .form-control { height: 28px; min-height: 28px; }
				.eps-page #eps-product-list { width: 100%; overflow-x: auto; }
				.eps-page #eps-product-list .dt-cell__content {
					align-items: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
				}
				.eps-page .eps-action-cell {
					display: flex; align-items: center; justify-content: center; width: 100%; min-height: 28px;
				}
				.eps-page .eps-action-cell .btn { min-width: 72px; margin: 0; line-height: 1.2; }
				.eps-side-col { gap: 12px; }
				.eps-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
				.eps-stats > div {
					display: flex; flex-direction: column; align-items: center; justify-content: center;
					padding: 8px 4px; border-radius: 6px; background-color: var(--bg-color);
				}
				.eps-stats h3 { margin-bottom: 0; }
				.eps-stats p { margin: 0; }
				#eps-sync-log-card { display: none; flex-direction: column; height: 420px; }
				#eps-sync-log-card.is-visible { display: flex !important; }
				#eps-sync-log { flex: 1; overflow-y: auto; min-height: 0; }
				.eps-banner {
					display: none; padding: 10px 12px; border-radius: 6px; margin-bottom: 12px;
					background: var(--bg-color); border: 1px solid var(--border-color);
				}
				.eps-variant-toggle { text-decoration: none; border: none; background: transparent; padding: 0; }
				.eps-variant-popover {
					background: var(--card-bg, #fff);
					border: 1px solid var(--border-color, #d1d8dd);
					border-radius: 6px;
					box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.15));
					min-width: 240px;
					max-width: 340px;
					max-height: 280px;
					overflow-y: auto;
					padding: 8px 0;
				}
				.eps-variant-popover-header {
					font-weight: 600; font-size: 12px; padding: 4px 12px 8px;
					border-bottom: 1px solid var(--border-color, #eee); margin-bottom: 4px;
				}
				.eps-variant-tree { padding: 0 4px; }
				.eps-variant-node { padding: 6px 10px; border-radius: 4px; }
				.eps-variant-node:hover { background: var(--bg-color, #f5f6f7); }
				.eps-variant-node-title { font-size: 13px; font-weight: 500; }
			</style>
			<div class="eps-page">
				<div class="eps-provider-bar">
					<label class="eps-provider-label" for="eps-provider-select">${__("Integration")}</label>
					<select class="form-control form-control-sm" id="eps-provider-select"></select>
					<span class="eps-provider-state" id="eps-provider-state"></span>
					<a id="eps-settings-link" class="small" style="display: none;" title="${__("Open integration settings")}"></a>
				</div>

				<div class="eps-banner" id="eps-banner"></div>

				<div class="row eps-grid">
					<div class="col-lg-8 d-flex flex-column">
						<div class="card border-0 shadow-sm p-3 w-100 rounded-sm eps-products-card" style="background-color: var(--card-bg)">
							<div class="d-flex justify-content-between align-items-center border-bottom pb-2 mb-2 flex-wrap eps-products-card-header" style="gap: 8px;">
								<h5 class="mb-0" id="eps-list-title">${__("Products")}</h5>
								<div class="eps-toolbar">
									<input type="text" class="form-control form-control-sm" id="eps-search"
										placeholder="${__("Search product / SKU / ID…")}" style="width: 200px;" autocomplete="off">
									<select class="form-control form-control-sm" id="eps-sync-filter" style="width: 150px;">
										<option value="">${__("All items")}</option>
										<option value="synced">${__("Synced")}</option>
										<option value="unsynced">${__("Not Synced")}</option>
										<option value="broken">${__("Broken Mapping")}</option>
									</select>
									<select class="form-control form-control-sm" id="eps-page-size" style="width: 80px;">
										<option value="20">${__("20 / page")}</option>
										<option value="50">${__("50 / page")}</option>
									</select>
									<label class="small text-muted" style="display: flex; align-items: center; gap: 4px; margin: 0;">
										<input type="checkbox" id="eps-select-all"> ${__("Select all")}
									</label>
									<button type="button" class="btn btn-sm btn-default" id="eps-sync-selected" disabled>
										${__("Sync Selected")}
									</button>
								</div>
							</div>
							<div id="eps-product-list"><div class="text-center text-muted py-4">${__("Loading…")}</div></div>
							<div class="eps-datatable-footer mt-2 pt-3 pb-2 border-top d-flex justify-content-between align-items-center" style="display: none;">
								<span class="text-muted small page-info"></span>
								<div class="btn-group">
									<button type="button" class="btn btn-sm btn-default btn-paginate btn-prev">${__("Prev")}</button>
									<button type="button" class="btn btn-sm btn-default btn-paginate btn-next">${__("Next")}</button>
								</div>
							</div>
						</div>
					</div>
					<div class="col-lg-4 d-flex flex-column eps-side-col">
						<div class="card border-0 shadow-sm p-3 rounded-sm" style="background-color: var(--card-bg)">
							<h5 class="border-bottom pb-2 mb-3">${__("Synchronization")}</h5>
							<button type="button" id="eps-sync-all" class="btn btn-primary w-100 font-weight-bold py-2 mb-3">
								${__("Sync All Items")}
							</button>
							<div class="eps-stats">
								<div><h3 class="mb-0" id="eps-stat-provider">-</h3><p class="text-muted small">${__("Provider")}</p></div>
								<div><h3 class="mb-0" id="eps-stat-mapped">-</h3><p class="text-muted small">${__("Mapped")}</p></div>
								<div><h3 class="mb-0" id="eps-stat-synced">-</h3><p class="text-muted small">${__("Synced")}</p></div>
							</div>
						</div>

						<div class="card border-0 shadow-sm p-3 rounded-sm" style="background-color: var(--card-bg)" id="eps-sync-log-card">
							<h5 class="border-bottom pb-2">${__("Sync Progress")}</h5>
							<div class="progress mb-2" style="height: 8px;">
								<div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 100%"></div>
							</div>
							<div class="control-value like-disabled-input for-description overflow-auto" id="eps-sync-log"></div>
						</div>
					</div>
				</div>
			</div>
		`);
	}

	// ------------------------------------------------------------- wiring

	bindActions() {
		this.wrapper.on("change", "#eps-provider-select", () => {
			const integration = this.wrapper.find("#eps-provider-select").val();
			const provider = this.providers.find((p) => p.integration === integration);
			if (provider) this.setProvider(provider);
		});

		this.wrapper.on("input", "#eps-search", () => {
			clearTimeout(this._filterTimer);
			this._filterTimer = setTimeout(() => this.resetAndFetch(), 350);
		});
		this.wrapper.on("keydown", "#eps-search", (e) => {
			if (e.key === "Enter") {
				e.preventDefault();
				clearTimeout(this._filterTimer);
				this.resetAndFetch();
			}
		});

		this.wrapper.on("change", "#eps-sync-filter", () => this.resetAndFetch());
		this.wrapper.on("change", "#eps-page-size", () => {
			this.limit = parseInt(this.wrapper.find("#eps-page-size").val(), 10) || 20;
			this.resetAndFetch();
		});

		this.wrapper.on("click", ".btn-prev", () => this.goPrev());
		this.wrapper.on("click", ".btn-next", () => this.goNext());

		this.wrapper.on("click", ".btn-sync-one", (e) => this.syncOne($(e.currentTarget)));
		this.wrapper.on("click", ".btn-resync-one", (e) => this.syncOne($(e.currentTarget)));
		this.wrapper.on("click", "#eps-sync-all", () => this.startBulk());
		this.wrapper.on("click", "#eps-sync-selected", () => this.syncSelected());

		this.wrapper.on("change", ".eps-row-select", (e) => {
			const id = $(e.currentTarget).attr("data-id");
			if (!id) return;
			if (e.currentTarget.checked) this.selectedIds.add(id);
			else this.selectedIds.delete(id);
			this.updateSelectionUI();
		});

		this.wrapper.on("change", "#eps-select-all", (e) => {
			const checked = e.currentTarget.checked;
			this.allProducts.forEach((p) => {
				if (!p.id) return;
				if (checked) this.selectedIds.add(p.id);
				else this.selectedIds.delete(p.id);
			});
			this.renderTable();
		});

		this.wrapper.on("mouseenter", ".eps-variant-toggle", (e) => this.showVariantDropdown(e.currentTarget));
		this.wrapper.on("mouseleave", ".eps-variant-toggle", () => this.scheduleVariantClose());
	}

	// ----------------------------------------------------------- providers

	async showDiagnostics() {
		const { message } = await frappe.call({ method: `${API}.get_provider_diagnostics` });
		if (!message || !message.length) return;
		const rows = message
			.map((r) => `<li><b>${frappe.utils.escape_html(r.integration)}</b>: ${frappe.utils.escape_html(r.reason)}</li>`)
			.join("");
		this.wrapper.find("#eps-diagnostics").remove();
		this.wrapper
			.find("#eps-provider-select")
			.closest(".form-group, div")
			.first()
			.before(
				`<div id="eps-diagnostics" class="alert alert-warning"><b>${__(
					"Some providers were not loaded"
				)}</b><ul class="mb-0">${rows}</ul></div>`
			);
	}

	async loadProviders() {
		const { message } = await frappe.call({ method: `${API}.get_providers` });
		this.providers = message || [];

		const select = this.wrapper.find("#eps-provider-select").empty();
		this.showDiagnostics();

		if (!this.providers.length) {
			this.wrapper.find("#eps-list-title").text(__("Products"));
			this.wrapper
				.find("#eps-product-list")
				.html(`<div class="text-center text-muted py-4">${__(
					"No ecommerce integrations registered. Add an ecommerce_product_sync_providers hook in a connector app."
				)}</div>`);
			select.prop("disabled", true);
			this.wrapper.find("#eps-sync-all").prop("disabled", true);
			return;
		}

		for (const provider of this.providers) {
			const label = provider.enabled ? provider.label : `${provider.label} (${__("disabled")})`;
			select.append($("<option>", { value: provider.integration, text: label }));
		}

		const wanted = this.preselectProvider();
		const provider = this.providers.find((p) => p.integration === wanted) || this.providers[0];
		select.val(provider.integration);
		this.setProvider(provider);
	}

	preselectProvider() {
		const params = new URLSearchParams(window.location.search);
		const wanted = params.get("provider") || "";
		if (!wanted) return null;
		return (
			this.providers.find(
				(p) => p.integration === wanted || p.slug === wanted || p.label === wanted
			) || {}
		).integration;
	}

	setProvider(provider) {
		this.provider = provider;
		this.closeVariantDropdown();
		this.selectedIds.clear();

		this.cursorHistory = [null];
		this.pageIndex = 0;
		this.nextCursor = null;
		this.total = null;
		this.wrapper.find("#eps-search").val("");
		this.wrapper.find("#eps-sync-filter").val("");

		this.wrapper.find("#eps-list-title").text(__("Products in {0}", [provider.label]));

		const $settings = this.wrapper.find("#eps-settings-link");
		if (provider.settings_doctype) {
			$settings
				.text(`${__(provider.settings_doctype)} →`)
				.attr("href", `/app/${frappe.router.slug(provider.settings_doctype)}`)
				.show();
		} else {
			$settings.hide();
		}

		const $state = this.wrapper.find("#eps-provider-state");
		const $banner = this.wrapper.find("#eps-banner");
		if (provider.enabled) {
			$state.html(`<span class="indicator-pill green">${__("Enabled")}</span>`);
			$banner.hide();
		} else {
			$state.html(`<span class="indicator-pill red">${__("Disabled")}</span>`);
			$banner
				.text(
					provider.settings_doctype
						? __("{0} is disabled. Enable it in {1} to sync products.", [
								provider.label,
								__(provider.settings_doctype),
							])
						: __("{0} is disabled. Enable it to sync products.", [provider.label])
				)
				.show();
		}

		this.toggleBulkButtons(false);
		this.subscribeRealtime();
		this.fetchStats();
		this.fetchProducts();
		this.checkSyncStatus();
	}

	subscribeRealtime() {
		if (this._realtimeEvent) frappe.realtime.off(this._realtimeEvent);
		this._realtimeEvent = this.provider.event_name;
		frappe.realtime.on(this._realtimeEvent, (payload) => this.onRealtime(payload));
	}

	// ------------------------------------------------------------ products

	resetAndFetch() {
		this.cursorHistory = [null];
		this.pageIndex = 0;
		this.fetchProducts();
	}

	async fetchProducts() {
		if (!this.provider) return;
		const list = this.wrapper.find("#eps-product-list");

		if (!this.provider.enabled) {
			list.html(`<div class="text-center text-muted py-4">${__("Integration is disabled.")}</div>`);
			this.wrapper.find(".eps-datatable-footer").hide();
			return;
		}

		list.html(`<div class="text-center text-muted py-4">${__("Loading…")}</div>`);
		try {
			const { message } = await frappe.call({
				method: `${API}.get_products`,
				args: {
					integration: this.provider.integration,
					limit: this.limit,
					cursor: this.cursorHistory[this.pageIndex],
					search: this.wrapper.find("#eps-search").val(),
					sync_filter: this.wrapper.find("#eps-sync-filter").val(),
				},
			});

			this.allProducts = message.products || [];
			this.total = message.total;
			this.nextCursor = message.next_cursor;
			this.renderTable();
		} catch (e) {
			list.html(`<div class="text-danger py-4">${__("Could not load products. Check the integration settings.")}</div>`);
			this.wrapper.find(".eps-datatable-footer").hide();
		}
	}

	renderTable() {
		this.closeVariantDropdown();
		const list = this.wrapper.find("#eps-product-list");
		const rows = this.allProducts;

		if (!rows.length) {
			list.html(`<div class="text-center text-muted py-4">${__("No products found")}</div>`);
			this.wrapper.find(".eps-datatable-footer").hide();
			return;
		}

		const data = rows.map((p, idx) => ({
			[__("Select")]: `<input type="checkbox" class="eps-row-select" data-id="${frappe.utils.escape_html(
				p.id || ""
			)}"${this.selectedIds.has(p.id) ? " checked" : ""}>`,
			[__("S.No")]: this.pageIndex * this.limit + idx + 1,
			[__("Product ID")]: frappe.utils.escape_html(p.id || ""),
			[__("Product Name")]: frappe.utils.escape_html(p.name || ""),
			[__("SKU")]: this.variantCell(p),
			[__("Sync Status")]: this.syncStatusPill(p.sync_state),
			[__("Actions")]: `<div class="eps-action-cell"><button type="button" class="btn btn-default btn-xs ${
				p.synced ? "btn-resync-one" : "btn-sync-one"
			}" data-id="${frappe.utils.escape_html(p.id || "")}">${p.synced ? __("Re-sync") : __("Sync")}</button></div>`,
		}));

		const columns = [
			{ name: __("Select"), editable: false, focusable: false, align: "center", width: 55 },
			{ name: __("S.No"), editable: false, focusable: false, align: "center", width: 60 },
			{ name: __("Product ID"), editable: false, focusable: false, width: 250 },
			{ name: __("Product Name"), editable: false, focusable: false, width: 230 },
			{ name: __("SKU"), editable: false, focusable: false, width: 190 },
			{ name: __("Sync Status"), editable: false, focusable: false, align: "center", width: 155 },
			{ name: __("Actions"), editable: false, focusable: false, align: "center", width: 115 },
		];

		let rendered = false;
		if (this.table && typeof this.table.refresh === "function") {
			try {
				this.table.refresh(data);
				rendered = true;
			} catch (e) {
				rendered = false;
			}
		}
		if (!rendered) {
			list.empty();
			if (this.table && typeof this.table.destroy === "function") {
				try {
					this.table.destroy();
				} catch (e) {
					/* ignore stale instance */
				}
				this.table = null;
			}
			this.table = new frappe.DataTable(list[0], {
				columns,
				data,
				layout: "fixed",
				serialNoColumn: false,
				checkboxColumn: false,
				inlineFilters: false,
				noDataMessage: __("No products found"),
			});
		}

		const knownTotal = this.total != null;
		const pageInfo = knownTotal
			? `${rows.length ? this.pageIndex * this.limit + 1 : 0}-${this.pageIndex * this.limit + rows.length} ${__("of")} ${this.total}`
			: `${__("Page")} ${this.pageIndex + 1}`;
		this.wrapper.find(".page-info").text(pageInfo);
		this.wrapper
			.find(".eps-datatable-footer")
			.css({ display: "flex", visibility: "visible" });
		this.wrapper.find(".btn-prev").prop("disabled", this.pageIndex === 0);
		const hasNext = knownTotal
			? (this.pageIndex + 1) * this.limit < this.total
			: !!this.nextCursor;
		this.wrapper.find(".btn-next").prop("disabled", !hasNext);
		this.updateSelectionUI();
	}

	updateSelectionUI() {
		if (!this.wrapper) return;
		const count = this.selectedIds.size;
		const $btn = this.wrapper.find("#eps-sync-selected");
		$btn.prop("disabled", count === 0 || this.syncRunning || !this.provider?.enabled);
		$btn.text(count ? `${__("Sync Selected")} (${count})` : __("Sync Selected"));

		const pageIds = this.allProducts.map((p) => p.id).filter(Boolean);
		const allChecked = pageIds.length > 0 && pageIds.every((id) => this.selectedIds.has(id));
		this.wrapper.find("#eps-select-all").prop("checked", allChecked);
	}

	variantCell(p) {
		const variants = p.variants || [];
		if (variants.length > 1) {
			return `<button type="button" class="eps-variant-toggle" data-id="${frappe.utils.escape_html(
				p.id || ""
			)}"><span class="indicator-pill blue">${__("{0} variants", [variants.length])}</span> <i class="fa fa-angle-down"></i></button>`;
		}
		return frappe.utils.escape_html(p.sku || "");
	}

	showVariantDropdown(btn) {
		const productId = $(btn).attr("data-id");
		const product = this.allProducts.find((p) => p.id === productId);
		if (!product || !(product.variants || []).length) return;

		clearTimeout(this._variantHideTimer);
		if (this._activeDropdownId === productId) return;
		this.closeVariantDropdown();

		const nodes = product.variants
			.map(
				(v) => `
				<li class="eps-variant-node">
					<div class="eps-variant-node-title">${frappe.utils.escape_html(v.title || v.sku || v.id)}</div>
					<div class="text-muted small">
						${v.sku ? `${__("SKU")}: ${frappe.utils.escape_html(v.sku)}` : ""}
						${v.options ? ` · ${frappe.utils.escape_html(v.options)}` : ""}
					</div>
				</li>`
			)
			.join("");

		const $pop = $(`
			<div class="eps-variant-popover">
				<div class="eps-variant-popover-header">${__("Variants")} (${product.variants.length})</div>
				<ul class="eps-variant-tree list-unstyled mb-0">${nodes}</ul>
			</div>
		`);
		$pop.on("mouseenter", () => clearTimeout(this._variantHideTimer));
		$pop.on("mouseleave", () => this.scheduleVariantClose());
		$("body").append($pop);

		const rect = btn.getBoundingClientRect();
		const popWidth = $pop[0].offsetWidth;
		let left = rect.left + window.scrollX;
		if (left + popWidth > window.innerWidth - 10) left = window.innerWidth - popWidth - 10;
		$pop.css({ position: "absolute", top: rect.bottom + window.scrollY + 4, left, zIndex: 1100 });

		this._activeDropdownId = productId;
		this._$activeDropdown = $pop;
	}

	scheduleVariantClose() {
		clearTimeout(this._variantHideTimer);
		this._variantHideTimer = setTimeout(() => this.closeVariantDropdown(), 200);
	}

	closeVariantDropdown() {
		clearTimeout(this._variantHideTimer);
		if (this._$activeDropdown) {
			this._$activeDropdown.remove();
			this._$activeDropdown = null;
		}
		this._activeDropdownId = null;
	}

	syncStatusPill(state) {
		if (state === "synced") return `<span class="indicator-pill green">${__("Synced")}</span>`;
		if (state === "broken") return `<span class="indicator-pill red">${__("Broken Mapping")}</span>`;
		return `<span class="indicator-pill orange">${__("Not Synced")}</span>`;
	}

	goPrev() {
		if (this.pageIndex === 0) return;
		this.pageIndex -= 1;
		this.fetchProducts();
	}

	goNext() {
		const knownTotal = this.total != null;
		if (knownTotal && (this.pageIndex + 1) * this.limit >= this.total) return;
		if (!knownTotal && !this.nextCursor) return;
		this.cursorHistory = this.cursorHistory.slice(0, this.pageIndex + 1);
		this.cursorHistory.push(this.nextCursor);
		this.pageIndex += 1;
		this.fetchProducts();
	}

	// --------------------------------------------------------------- sync

	async fetchStats() {
		if (!this.provider) return;
		try {
			const { message } = await frappe.call({
				method: `${API}.get_stats`,
				args: { integration: this.provider.integration },
			});
			this.wrapper.find("#eps-stat-provider").text(message.provider_count ?? "-");
			this.wrapper.find("#eps-stat-mapped").text(message.mapped ?? "-");
			this.wrapper.find("#eps-stat-synced").text(message.synced ?? "-");
		} catch (e) {
			console.error("Failed to fetch sync stats", e);
		}
	}

	async syncOne($btn) {
		if (!this.provider) return;
		const productId = $btn.attr("data-id");
		const wasSynced = $btn.hasClass("btn-resync-one");
		$btn.prop("disabled", true).text(__("Syncing…"));
		try {
			const { message } = await frappe.call({
				method: `${API}.sync_product`,
				args: { integration: this.provider.integration, product_id: productId },
			});
			if (message && message.ok) {
				frappe.show_alert({
					message: message.item_code
						? __("{0}: {1}", [message.action || __("Synced"), message.item_code])
						: __("Synced {0}", [productId]),
					indicator: "green",
				});
				this.markSynced(productId);
				this.fetchStats();
			} else {
				frappe.msgprint({ title: __("Sync failed"), message: message?.error || __("Sync failed"), indicator: "red" });
			}
		} catch (e) {
			frappe.msgprint({ title: __("Sync failed"), message: __("Sync failed"), indicator: "red" });
		} finally {
			$btn.prop("disabled", false).text(wasSynced ? __("Re-sync") : __("Sync"));
		}
	}

	// Update the synced row in place instead of re-fetching the catalog.
	markSynced(productId) {
		const product = this.allProducts.find((p) => p.id === productId);
		if (product) {
			product.synced = true;
			product.sync_state = "synced";
		}
		this.renderTable();
	}

	async startBulk() {
		if (!this.provider || this.syncRunning) {
			if (this.syncRunning) frappe.msgprint(__("A product sync is already running."));
			return;
		}

		this.showConsole();
		try {
			const { message } = await frappe.call({
				method: `${API}.sync_all`,
				args: {
					integration: this.provider.integration,
					search: this.wrapper.find("#eps-search").val(),
					sync_filter: this.wrapper.find("#eps-sync-filter").val(),
				},
			});
			if (message?.status === "Busy") {
				frappe.msgprint(message.message || __("A product sync is already running."));
				this.toggleBulkButtons(false);
				return;
			}
			this.toggleBulkButtons(true);
		} catch (e) {
			frappe.msgprint({ title: __("Sync failed"), message: __("Could not start the sync."), indicator: "red" });
			this.toggleBulkButtons(false);
		}
	}

	async syncSelected() {
		const ids = [...this.selectedIds];
		if (!this.provider || !ids.length) return;
		if (this.syncRunning) {
			frappe.msgprint(__("A product sync is already running."));
			return;
		}

		// Pass display names so the progress trail shows product names, not ids.
		const labels = {};
		ids.forEach((id) => {
			const product = this.allProducts.find((p) => p.id === id);
			if (product) labels[id] = product.name || id;
		});

		this.showConsole();
		try {
			const { message } = await frappe.call({
				method: `${API}.sync_selected`,
				args: { integration: this.provider.integration, product_ids: ids, labels },
			});
			if (message?.status === "Busy") {
				frappe.msgprint(message.message || __("A product sync is already running."));
				this.toggleBulkButtons(false);
				return;
			}
			this.toggleBulkButtons(true);
		} catch (e) {
			frappe.msgprint({ title: __("Sync failed"), message: __("Could not start the sync."), indicator: "red" });
			this.toggleBulkButtons(false);
		}
	}

	async checkSyncStatus() {
		if (!this.provider) return;
		try {
			const { message } = await frappe.call({
				method: `${API}.get_sync_status`,
				args: { integration: this.provider.integration },
			});
			if (message?.running) {
				this.toggleBulkButtons(true);
				this.showConsole();
			}
		} catch (e) {
			/* status is best-effort */
		}
	}

	onRealtime(payload) {
		const { message, done } = payload || {};
		if (message) {
			this.showConsole();
			const $log = this.wrapper.find("#eps-sync-log");
			// Cap the log so long syncs do not grow the DOM without bound.
			const $entries = $log.children();
			if ($entries.length >= 200) $entries.first().remove();
			$log.append(`<pre class="mb-0">${message}</pre>`);
			requestAnimationFrame(() => $log.scrollTop($log[0].scrollHeight));
		}
		if (done) {
			this.selectedIds.clear();
			this.toggleBulkButtons(false);
			this.fetchStats();
			this.fetchProducts();
		}
	}

	showConsole() {
		const $card = this.wrapper.find("#eps-sync-log-card");
		$card.addClass("is-visible").css("display", "flex");
	}

	toggleBulkButtons(running) {
		this.syncRunning = running;
		const $btn = this.wrapper.find("#eps-sync-all");
		$btn.prop("disabled", running || !this.provider?.enabled);
		$btn.text(running ? __("Syncing...") : __("Sync All Items"));
		this.updateSelectionUI();
	}
}
