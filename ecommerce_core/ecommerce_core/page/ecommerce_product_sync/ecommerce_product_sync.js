// Copyright (c) 2026, Aerele Technologies and contributors
// For license information, please see license.txt

// Shared Product Sync page. Providers register through the
// `ecommerce_product_sync_providers` hook; this page stays provider-agnostic.

const API = "ecommerce_core.product_sync.api";

// Page sizes offered in the bottom paging bar, list-view style.
const PAGE_SIZES = [20, 50, 100, 500, 2500];

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
		this.allMode = true; // blank integration = all connectors combined
		this.limit = 20;
		this.cursorHistory = [null]; // cursors of visited pages; index == current page
		this.pageIndex = 0;
		this.nextCursor = null;
		this.total = null;
		this.allProducts = [];
		this.selectedIds = new Set();
		this.selectedInfo = {}; // id -> {integration, label}, so selections from other pages still sync
		this.providerErrors = []; // per-provider listing failures in All mode
		this.syncRunning = false;
		this._filterTimer = null;
		this._realtimeEvents = [];
		this._applyingChecks = false;
		this._tableMode = null;
		this.init();
	}

	async init() {
		this.addMarkup();
		this.bindActions();
		this.setupPageSizeBar();
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

				/* ---- Products grid ---- */
				.eps-page .row.eps-grid { display: flex; margin-left: 0; margin-right: 0; }
				.eps-page .row.eps-grid > [class*="col-"] { display: flex; flex-direction: column; min-height: 0; }
				.eps-page .eps-products-card { display: flex; flex-direction: column; }
				.eps-page .eps-products-card-header,
				.eps-page .eps-list-footer { flex: 0 0 auto; }
				.eps-page .eps-toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
				.eps-page .eps-toolbar .form-control { height: 28px; min-height: 28px; }
				/* Frappe sets .form-control to width:100%, so fix the filter widths */
				.eps-toolbar select.form-control { width: 200px; }
				.eps-toolbar #eps-sync-filter { width: 130px; }
				.eps-toolbar .eps-provider-state { display: inline-flex; align-items: center; }
				.eps-toolbar #eps-settings-link {
					display: inline-flex; align-items: center; gap: 4px;
					padding: 4px 10px; border-radius: 6px;
					border: 1px solid var(--border-color);
					color: var(--text-color); text-decoration: none; white-space: nowrap;
					transition: background-color 0.15s;
				}
				.eps-toolbar #eps-settings-link:hover {
					background-color: var(--control-bg, var(--bg-color));
				}
				@media (max-width: 576px) {
					.eps-toolbar select.form-control { width: 100%; }
				}
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

				/* ---- Paging bar (list-view style) ---- */
				.eps-list-footer { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-color); }
				.eps-list-footer .level {
					display: flex; align-items: center; justify-content: space-between;
					flex-wrap: wrap; gap: 8px; width: 100%;
				}
				.eps-list-footer .level-left,
				.eps-list-footer .level-right { display: flex; align-items: center; }
				.eps-list-footer .eps-paging { gap: 12px; flex-wrap: wrap; }

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
				<div class="eps-banner" id="eps-banner"></div>

				<div class="row eps-grid">
					<div class="col-lg-8 d-flex flex-column">
						<div class="card border-0 shadow-sm p-3 w-100 rounded-sm eps-products-card" style="background-color: var(--card-bg)">
							<div class="d-flex justify-content-between align-items-center border-bottom pb-2 mb-2 flex-wrap eps-products-card-header" style="gap: 8px;">
								<h5 class="mb-0" id="eps-list-title">${__("Products")}</h5>
								<div class="eps-toolbar">
									<select class="form-control form-control-sm" id="eps-provider-select"></select>
									<span class="eps-provider-state" id="eps-provider-state"></span>
									<a id="eps-settings-link" class="small" style="display: none;" title="${__("Open integration settings")}"></a>
									<input type="text" class="form-control form-control-sm" id="eps-search"
										placeholder="${__("Search product / SKU / ID…")}" style="width: 200px;" autocomplete="off">
									<select class="form-control form-control-sm" id="eps-sync-filter" style="width: 150px;">
										<option value="">${__("All items")}</option>
										<option value="synced">${__("Synced")}</option>
										<option value="unsynced">${__("Not Synced")}</option>
									</select>
									<button type="button" class="btn btn-sm btn-default" id="eps-sync-selected" disabled>
										${__("Sync Selected")}
									</button>
								</div>
							</div>
							<div id="eps-product-list"><div class="text-center text-muted py-4">${__("Loading…")}</div></div>
							<div class="eps-list-footer" style="display: none;">
								<div class="level">
									<div class="level-left">
										<span class="text-muted small page-info"></span>
									</div>
									<div class="level-right eps-paging">
										<div class="btn-group">
											<button type="button" class="btn btn-sm btn-default btn-prev" title="${__("Previous page")}">
												<i class="fa fa-angle-left"></i>
											</button>
											<button type="button" class="btn btn-sm btn-default btn-next" title="${__("Next page")}">
												<i class="fa fa-angle-right"></i>
											</button>
										</div>
										<div class="eps-page-size"></div>
									</div>
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
								<div><h3 class="mb-0" id="eps-stat-provider">-</h3><p class="text-muted small" id="eps-stat-provider-label">${__("Total Products")}</p></div>
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
		// Blank integration = all connectors, like an empty list-view filter.
		this.wrapper.on("change", "#eps-provider-select", () => {
			this.setIntegration(this.wrapper.find("#eps-provider-select").val() || "");
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

		this.wrapper.on("click", ".btn-prev", () => this.goPrev());
		this.wrapper.on("click", ".btn-next", () => this.goNext());

		this.wrapper.on("click", ".btn-sync-one", (e) => this.syncOne($(e.currentTarget)));
		this.wrapper.on("click", ".btn-resync-one", (e) => this.syncOne($(e.currentTarget)));
		this.wrapper.on("click", "#eps-sync-all", () => this.startBulk());
		this.wrapper.on("click", "#eps-sync-selected", () => this.syncSelected());

		this.wrapper.on("mouseenter", ".eps-variant-toggle", (e) => this.showVariantDropdown(e.currentTarget));
		this.wrapper.on("mouseleave", ".eps-variant-toggle", () => this.scheduleVariantClose());
	}

	setupPageSizeBar() {
		// Same segmented pill control the list view uses for its paging bar.
		this.pageSizeButtons = new frappe.ui.TabButtons({
			label: __("Page Size"),
			options: PAGE_SIZES.map((value) => ({ label: String(value), value })),
			value: this.limit,
			on_change: (value) => {
				this.limit = cint(value) || this.limit;
				this.resetAndFetch();
			},
		});
		this.wrapper.find(".eps-page-size").append(this.pageSizeButtons.$el);
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

		// Leading blank entry, like a list-view filter: blank shows every integration.
		select.append($("<option>", { value: "", text: "" }));

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
		this.setIntegration(wanted || "");
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

	enabledProviders() {
		return this.providers.filter((p) => p.enabled);
	}

	canSync() {
		return this.allMode ? this.enabledProviders().length > 0 : !!this.provider?.enabled;
	}

	setIntegration(integration) {
		const provider = this.providers.find((p) => p.integration === integration) || null;
		this.allMode = !provider;
		this.provider = provider;
		this.providerErrors = [];
		this.closeVariantDropdown();
		this.selectedIds.clear();
		this.selectedInfo = {};

		this.wrapper.find("#eps-provider-select").val(provider ? provider.integration : "");

		this.cursorHistory = [null];
		this.pageIndex = 0;
		this.nextCursor = null;
		this.total = null;
		this.wrapper.find("#eps-search").val("");
		this.wrapper.find("#eps-sync-filter").val("");

		this.renderProviderBar();

		this.toggleBulkButtons(false);
		this.subscribeRealtime();
		this.fetchStats();
		this.fetchProducts();
		this.checkSyncStatus();
	}

	renderProviderBar() {
		const $state = this.wrapper.find("#eps-provider-state");
		const $settings = this.wrapper.find("#eps-settings-link");
		const $banner = this.wrapper.find("#eps-banner").hide();

		if (this.allMode) {
			// Combined view: per-integration state pill and settings shortcut
			// would point nowhere in particular, so they stay hidden.
			this.wrapper.find("#eps-list-title").text(__("All Integrations"));
			$state.empty();
			$settings.hide();
			return;
		}

		const provider = this.provider;
		this.wrapper.find("#eps-list-title").text(__("Products in {0}", [provider.label]));

		if (provider.settings_doctype) {
			$settings
				.text(`${__(provider.settings_doctype)} →`)
				.attr("href", `/app/${frappe.router.slug(provider.settings_doctype)}`)
				.show();
		} else {
			$settings.hide();
		}

		if (provider.enabled) {
			$state.html(`<span class="indicator-pill green">${__("Enabled")}</span>`);
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
	}

	subscribeRealtime() {
		this._realtimeEvents.forEach((event) => frappe.realtime.off(event));
		this._realtimeEvents = this.allMode
			? this.enabledProviders().map((p) => p.event_name)
			: this.provider
				? [this.provider.event_name]
				: [];
		this._realtimeEvents.forEach((event) =>
			frappe.realtime.on(event, (payload) => this.onRealtime(payload))
		);
	}

	// ------------------------------------------------------------ products

	resetAndFetch() {
		this.cursorHistory = [null];
		this.pageIndex = 0;
		this.fetchProducts();
	}

	async fetchProducts() {
		if (!this.allMode && !this.provider) return;
		const list = this.wrapper.find("#eps-product-list");

		if (!this.allMode && !this.provider.enabled) {
			this.destroyTable();
			list.html(`<div class="text-center text-muted py-4">${__("Integration is disabled.")}</div>`);
			this.wrapper.find(".eps-list-footer").hide();
			return;
		}
		if (this.allMode && !this.enabledProviders().length) {
			this.destroyTable();
			list.html(`<div class="text-center text-muted py-4">${__(
				"No enabled ecommerce integrations. Enable one from its settings to list products."
			)}</div>`);
			this.wrapper.find(".eps-list-footer").hide();
			return;
		}

		// The loading placeholder replaces the DataTable's DOM, so only show it
		// when there is no live table to keep rendered while fetching.
		const hasLiveTable = this.table && list.children(".datatable").length > 0;
		if (!hasLiveTable || !this.allProducts.length) {
			list.html(`<div class="text-center text-muted py-4">${__("Loading…")}</div>`);
		}
		try {
			const { message } = await frappe.call({
				method: `${API}.get_products`,
				args: {
					integration: this.allMode ? "" : this.provider.integration,
					limit: this.limit,
					cursor: this.cursorHistory[this.pageIndex],
					search: this.wrapper.find("#eps-search").val(),
					sync_filter: this.wrapper.find("#eps-sync-filter").val(),
				},
			});

			this.allProducts = message.products || [];
			this.total = message.total;
			this.nextCursor = message.next_cursor;
			this.providerErrors = message.errors || [];
			this.renderErrorsBanner();
			this.renderTable();
		} catch (e) {
			this.providerErrors = [];
			this.destroyTable();
			list.html(`<div class="text-danger py-4">${__("Could not load products. Check the integration settings.")}</div>`);
			this.wrapper.find(".eps-list-footer").hide();
		}
	}

	renderErrorsBanner() {
		const $banner = this.wrapper.find("#eps-banner");
		if (!this.allMode || !this.providerErrors.length) {
			if (this.allMode) $banner.hide();
			return;
		}
		const rows = this.providerErrors
			.map(
				(e) =>
					`<li><b>${frappe.utils.escape_html(e.label || e.integration)}</b>: ${frappe.utils.escape_html(
						e.error || __("unreachable")
					)}</li>`
			)
			.join("");
		$banner
			.html(`<b>${__("Some integrations could not be listed")}</b><ul class="mb-0">${rows}</ul>`)
			.show();
	}

	renderTable() {
		this.closeVariantDropdown();
		const list = this.wrapper.find("#eps-product-list");
		const rows = this.allProducts;
		const mode = this.allMode ? "all" : "provider";

		if (!rows.length) {
			this.destroyTable();
			list.html(`<div class="text-center text-muted py-4">${__("No products found")}</div>`);
			this.wrapper.find(".eps-list-footer").hide();
			return;
		}

		const data = rows.map((p, idx) => {
			const row = {
				[__("S.No")]: this.pageIndex * this.limit + idx + 1,
			};
			if (this.allMode) {
				row[__("Integration")] = frappe.utils.escape_html(p.provider_label || p.integration || "");
			}
			row[__("Product ID")] = frappe.utils.escape_html(p.id || "");
			row[__("Product Name")] = frappe.utils.escape_html(p.name || "");
			row[__("SKU")] = this.variantCell(p);
			row[__("Sync Status")] = this.syncStatusPill(p.sync_state);
			row[__("Actions")] = `<div class="eps-action-cell"><button type="button" class="btn btn-default btn-xs ${
				p.synced ? "btn-resync-one" : "btn-sync-one"
			}" data-id="${frappe.utils.escape_html(
				p.id || ""
			)}" data-integration="${frappe.utils.escape_html(p.integration || "")}">${
				p.synced ? __("Re-sync") : __("Sync")
			}</button></div>`;
			return row;
		});

		const columns = [{ name: __("S.No"), editable: false, focusable: false, align: "center", width: 60 }];
		if (this.allMode) {
			columns.push({ name: __("Integration"), editable: false, focusable: false, width: 140 });
		}
		columns.push(
			{ name: __("Product ID"), editable: false, focusable: false, width: 250 },
			{ name: __("Product Name"), editable: false, focusable: false, width: 230 },
			{ name: __("SKU"), editable: false, focusable: false, width: 190 },
			{ name: __("Sync Status"), editable: false, focusable: false, align: "center", width: 155 },
			{ name: __("Actions"), editable: false, focusable: false, align: "center", width: 115 }
		);

		// Rebuild when the mode's column set changes or the previous DOM was
		// replaced (loading/error placeholders detach the table); otherwise
		// refresh in place.
		let canRefresh =
			mode === this._tableMode &&
			this.table &&
			typeof this.table.refresh === "function" &&
			list.children(".datatable").length > 0;
		if (canRefresh) {
			try {
				this.table.refresh(data);
			} catch (e) {
				canRefresh = false;
			}
		}
		if (!canRefresh) {
			this.destroyTable();
			// The DataTable's own checkbox column: the header checkbox selects
			// every row on the page, exactly like the list view's selector.
			this.table = new frappe.DataTable(list[0], {
				columns,
				data,
				layout: "fixed",
				serialNoColumn: false,
				checkboxColumn: true,
				checkedRowStatus: false,
				inlineFilters: false,
				noDataMessage: __("No products found"),
				events: {
					onCheckRow: () => this.onTableCheck(),
				},
			});
			this._tableMode = mode;
		}
		this.applyChecks();

		const knownTotal = this.total != null;
		const pageInfo = knownTotal
			? `${rows.length ? this.pageIndex * this.limit + 1 : 0}-${this.pageIndex * this.limit + rows.length} ${__("of")} ${this.total}`
			: `${__("Page")} ${this.pageIndex + 1}`;
		this.wrapper.find(".page-info").text(pageInfo);
		this.wrapper.find(".eps-list-footer").show();
		this.wrapper.find(".btn-prev").prop("disabled", this.pageIndex === 0);
		const hasNext = knownTotal
			? (this.pageIndex + 1) * this.limit < this.total
			: !!this.nextCursor;
		this.wrapper.find(".btn-next").prop("disabled", !hasNext);
		this.updateSelectionUI();
	}

	destroyTable() {
		if (this.table && typeof this.table.destroy === "function") {
			try {
				this.table.destroy();
			} catch (e) {
				/* ignore stale instance */
			}
		}
		this.table = null;
		this._tableMode = null;
	}

	onTableCheck() {
		if (this._applyingChecks || !this.table) return;
		const checked = new Set(
			(this.table.rowmanager.getCheckedRows() || [])
				.map((rowIndex) => this.allProducts[rowIndex]?.id)
				.filter(Boolean)
		);
		// Selection is kept across pages: only this page's ids follow the
		// checkboxes; ids selected on other pages stay in the set. selectedInfo
		// remembers each id's integration and name so bulk actions work even
		// when the row is not on the current page.
		this.allProducts.forEach((p) => {
			if (!p.id) return;
			if (checked.has(p.id)) {
				this.selectedIds.add(p.id);
				this.selectedInfo[p.id] = {
					integration: this.allMode ? p.integration : this.provider?.integration,
					label: p.name || p.id,
				};
			} else {
				this.selectedIds.delete(p.id);
				delete this.selectedInfo[p.id];
			}
		});
		this.updateSelectionUI();
	}

	applyChecks() {
		const rowmanager = this.table?.rowmanager;
		if (!rowmanager) return;
		this._applyingChecks = true;
		// DataTable.refresh() replays the previous checkMap onto the new rows
		// (restoreState -> highlightCheckedRows), so clearing the map alone
		// leaves stale checkboxes on shifted rows. Set every row's checkbox
		// explicitly, unchecking as well as checking.
		rowmanager.checkMap = [];
		this.allProducts.forEach((p, rowIndex) => {
			rowmanager.checkRow(rowIndex, !!(p.id && this.selectedIds.has(p.id)));
		});
		this._applyingChecks = false;

		// Header checkbox mirrors the current page: checked when every row is
		// selected, indeterminate when only some are (list-view behaviour).
		const ids = this.allProducts.map((p) => p.id).filter(Boolean);
		const selectedCount = ids.filter((id) => this.selectedIds.has(id)).length;
		const $check = this.wrapper.find("#eps-product-list .dt-header .dt-cell--header-0 [type='checkbox']");
		$check.prop("checked", ids.length > 0 && selectedCount === ids.length);
		$check.prop("indeterminate", selectedCount > 0 && selectedCount < ids.length);
	}

	updateSelectionUI() {
		if (!this.wrapper) return;
		const count = this.selectedIds.size;
		const $btn = this.wrapper.find("#eps-sync-selected");
		$btn.prop("disabled", count === 0 || this.syncRunning || !this.canSync());
		$btn.text(count ? `${__("Sync Selected")} (${count})` : __("Sync Selected"));
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
		const $provider = this.wrapper.find("#eps-stat-provider");
		const $mapped = this.wrapper.find("#eps-stat-mapped");
		const $synced = this.wrapper.find("#eps-stat-synced");
		const $providerLabel = this.wrapper.find("#eps-stat-provider-label");

		if (!this.canSync()) {
			$provider.text("-");
			$mapped.text("-");
			$synced.text("-");
			return;
		}

		if (!this.allMode) {
			$providerLabel.text(__("Total Products"));
			try {
				const { message } = await frappe.call({
					method: `${API}.get_stats`,
					args: { integration: this.provider.integration },
				});
				$provider.text(message.provider_count ?? "-");
				$mapped.text(message.mapped ?? "-");
				$synced.text(message.synced ?? "-");
			} catch (e) {
				console.error("Failed to fetch sync stats", e);
			}
			return;
		}

		// Combined view: per-integration provider counts don't add up to one
		// number worth showing, so the first stat becomes the integrations
		// count and the rest are summed across enabled integrations.
		$providerLabel.text(__("Integrations"));
		$provider.text(this.enabledProviders().length);
		$mapped.text("-");
		$synced.text("-");
		const results = await Promise.allSettled(
			this.enabledProviders().map((p) =>
				frappe.call({ method: `${API}.get_stats`, args: { integration: p.integration } })
			)
		);
		let mapped = 0;
		let synced = 0;
		let any = false;
		for (const result of results) {
			if (result.status !== "fulfilled") continue;
			const stats = result.value.message || {};
			mapped += stats.mapped || 0;
			synced += stats.synced || 0;
			any = true;
		}
		$mapped.text(any ? mapped : "-");
		$synced.text(any ? synced : "-");
	}

	async syncOne($btn) {
		const productId = $btn.attr("data-id");
		const integration = $btn.attr("data-integration") || this.provider?.integration;
		if (!integration) return;
		const wasSynced = $btn.hasClass("btn-resync-one");
		$btn.prop("disabled", true).text(__("Syncing…"));
		try {
			const { message } = await frappe.call({
				method: `${API}.sync_product`,
				args: { integration, product_id: productId },
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
		if (!this.canSync()) return;
		if (this.syncRunning) {
			frappe.msgprint(__("A product sync is already running."));
			return;
		}

		// In All mode every enabled integration gets its own bulk job.
		const targets = this.allMode ? this.enabledProviders() : [this.provider];
		const search = this.wrapper.find("#eps-search").val();
		const syncFilter = this.wrapper.find("#eps-sync-filter").val();

		this.showConsole();
		let queued = false;
		try {
			for (const provider of targets) {
				const { message } = await frappe.call({
					method: `${API}.sync_all`,
					args: { integration: provider.integration, search, sync_filter: syncFilter },
				});
				if (message?.status === "Busy") {
					frappe.msgprint(message.message || __("A product sync is already running."));
					continue;
				}
				queued = true;
			}
			this.toggleBulkButtons(queued);
		} catch (e) {
			frappe.msgprint({ title: __("Sync failed"), message: __("Could not start the sync."), indicator: "red" });
			this.toggleBulkButtons(false);
		}
	}

	async syncSelected() {
		const ids = [...this.selectedIds];
		if (!this.canSync() || !ids.length) return;
		if (this.syncRunning) {
			frappe.msgprint(__("A product sync is already running."));
			return;
		}

		// Group the selection by integration. selectedInfo remembers each id's
		// integration and display name, so rows selected on other pages of the
		// combined view still sync correctly.
		const byIntegration = {};
		ids.forEach((id) => {
			const info = this.selectedInfo[id] || {};
			const integration = info.integration || (this.allMode ? null : this.provider.integration);
			if (!integration) return;
			(byIntegration[integration] = byIntegration[integration] || []).push(id);
		});

		this.showConsole();
		let queued = false;
		try {
			for (const [integration, productIds] of Object.entries(byIntegration)) {
				// Pass display names so the progress trail shows product names, not ids.
				const labels = {};
				productIds.forEach((id) => {
					const label = this.selectedInfo[id]?.label;
					if (label) labels[id] = label;
				});
				const { message } = await frappe.call({
					method: `${API}.sync_selected`,
					args: { integration, product_ids: productIds, labels },
				});
				if (message?.status === "Busy") {
					frappe.msgprint(message.message || __("A product sync is already running."));
					continue;
				}
				queued = true;
			}
			this.toggleBulkButtons(queued);
		} catch (e) {
			frappe.msgprint({ title: __("Sync failed"), message: __("Could not start the sync."), indicator: "red" });
			this.toggleBulkButtons(false);
		}
	}

	async checkSyncStatus() {
		const targets = this.allMode
			? this.enabledProviders()
			: this.provider
				? [this.provider]
				: [];
		if (!targets.length) return;
		const results = await Promise.allSettled(
			targets.map((p) =>
				frappe.call({ method: `${API}.get_sync_status`, args: { integration: p.integration } })
			)
		);
		if (results.some((r) => r.status === "fulfilled" && r.value.message?.running)) {
			this.toggleBulkButtons(true);
			this.showConsole();
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
			this.selectedInfo = {};
			// Rows may drop out of the list (e.g. "Not Synced" filter), and
			// DataTable keeps checks by row position, so rebuild the table
			// instead of refreshing it in place to avoid stale checkboxes.
			this.destroyTable();
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
		$btn.prop("disabled", running || !this.canSync());
		$btn.text(running ? __("Syncing...") : __("Sync All Items"));
		this.updateSelectionUI();
	}
}
