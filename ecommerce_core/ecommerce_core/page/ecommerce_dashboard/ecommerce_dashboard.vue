<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { createResource, frappeRequest, Button, Select, Spinner, TextInput } from "frappe-ui";
import { useHost } from "@framework/ui/island";

// Desk hands these down and updates them in place. `route` is the URL segments
// after the page name, and `query` its parameters (e.g. ?integration=unicommerce).
const props = defineProps({
	route: { type: Array, default: () => [] },
	query: { type: Object, default: () => ({}) },
});

// Desk writes `title` into the breadcrumb and turns each action into a page
// menu row; an action is { label, onClick }.
const emit = defineEmits(["title", "actions"]);

// Desk's ambient context: locale, timezone, user, theme.
const host = useHost();

// frappe-ui's frappeRequest reads the CSRF token from `window.csrf_token`, which
// the v17 desk no longer sets (it keeps it on `frappe.csrf_token`). Without this
// mirror, every authenticated POST from the island fails with "Invalid Request".
if (
	typeof window !== "undefined" &&
	(!window.csrf_token || window.csrf_token === "{{ csrf_token }}")
) {
	const token = window.frappe?.csrf_token;
	if (token) window.csrf_token = token;
}

const API = "ecommerce_core.dashboard.api";
const REFRESH_SECONDS = 30;
const PLATFORM_COLORS = ["bg-violet-500", "bg-green-500", "bg-cyan-500", "bg-pink-500"];

const SECTIONS = {
	orders: {
		key: "orders",
		label: "Orders",
		searchPlaceholder: "Order ID, customer, order no…",
		filterType: "select",
		statusOptions: [
			"To Deliver and Bill",
			"To Bill",
			"To Deliver",
			"Completed",
			"On Hold",
			"Draft",
			"Closed",
			"Cancelled",
		],
		empty: "No ecommerce orders yet.",
	},
	payments: {
		key: "payments",
		label: "Pending Payments",
		searchPlaceholder: "Invoice or customer…",
		filterType: "select",
		statusOptions: ["Unpaid", "Partly Paid", "Overdue", "COD Not Collected"],
		empty: "Nothing outstanding.",
	},
	items: {
		key: "items",
		label: "Items & Inventory",
		searchPlaceholder: "Item code, name or SKU…",
		filterType: "chips",
		chips: [
			["", "All"],
			["in", "In stock"],
			["low", "Low stock"],
			["out", "Out of stock"],
		],
		empty: "No items are mapped to a connector yet.",
	},
	logs: {
		key: "logs",
		label: "Sync Logs",
		searchPlaceholder: "Log title…",
		filterType: "chips",
		chips: [
			["", "All"],
			["success", "Successful"],
			["failed", "Failed"],
			["partial", "Partial"],
			["queued", "Queued"],
		],
		empty: "No sync logs found.",
	},
};

// ----- state -----

const integration = ref(
	typeof props.query.integration === "string" ? props.query.integration : "",
);
const activeSection = ref("orders");
const sectionState = reactive(
	Object.fromEntries(
		Object.keys(SECTIONS).map((key) => [
			key,
			{ search: "", status: "", page: 1, filters: {} },
		]),
	),
);
const summary = ref(null);
const live = ref(true);
const countdown = ref(REFRESH_SECONDS);
const lastRefresh = ref(null);
const pushingItem = ref(null);
const pushedMessage = ref("");
const searchTimers = {};

// ----- resources -----

const summaryRes = createResource({ url: `${API}.get_summary`, resourceFetcher: frappeRequest });

const sectionRes = Object.fromEntries(
	Object.keys(SECTIONS).map((key) => [
		key,
		createResource({ url: `${API}.get_section`, resourceFetcher: frappeRequest }),
	]),
);

const pushStockRes = createResource({
	url: `${API}.push_stock`,
	resourceFetcher: frappeRequest,
	onSuccess: (message) => {
		pushedMessage.value = message || "Stock push queued";
		loadSection("items");
	},
	onError: () => {
		pushedMessage.value = "";
	},
});

// ----- data loading -----

function loadSummary() {
	return summaryRes
		.submit({ integration: integration.value })
		.then((data) => {
			summary.value = data;
			if (
				integration.value &&
				!(data.providers || []).some((p) => p.integration === integration.value)
			) {
				integration.value = "";
			}
		})
		.catch(() => {});
}

function loadSection(key) {
	const state = sectionState[key];
	return sectionRes[key]
		.submit({
			section: key,
			integration: integration.value,
			search: state.search,
			status: state.status,
			page: state.page,
			page_size: SECTIONS[key].pageSize || 10,
			filters: JSON.stringify(state.filters || {}),
		})
		.then((data) => {
			// Landing past the last page after a filter change: pull back and retry once.
			const pages = Math.max(
				1,
				Math.ceil((data.total || 0) / (SECTIONS[key].pageSize || 10)),
			);
			if (state.page > pages) {
				state.page = pages;
				return loadSection(key);
			}
		})
		.catch(() => {});
}

function refreshAll() {
	countdown.value = REFRESH_SECONDS;
	return Promise.allSettled([loadSummary(), ...Object.keys(SECTIONS).map(loadSection)]).then(
		() => {
			lastRefresh.value = Date.now();
		},
	);
}

// ----- header actions / auto refresh -----

function emitActions() {
	emit("actions", [
		{ label: live.value ? "Pause auto-refresh" : "Resume auto-refresh", onClick: toggleLive },
		{ label: "Refresh", onClick: refreshAll },
	]);
}

function toggleLive() {
	live.value = !live.value;
	countdown.value = REFRESH_SECONDS;
	emitActions();
}

let timer = null;

onMounted(() => {
	emit("title", "Ecommerce Dashboard");
	emitActions();
	refreshAll();
	timer = setInterval(() => {
		if (document.hidden || !live.value) return;
		countdown.value -= 1;
		if (countdown.value <= 0) refreshAll();
	}, 1000);
});

onUnmounted(() => clearInterval(timer));

watch(
	() => props.query.integration,
	(value) => {
		if (typeof value === "string" && value !== integration.value) {
			integration.value = value;
		}
	},
);

watch(integration, () => {
	Object.values(sectionState).forEach((state) => (state.page = 1));
	refreshAll();
});

// ----- computed: header, notices, tiles -----

const providers = computed(() => summary.value?.providers || []);

function providerColor(value) {
	const index = providers.value.findIndex((p) => p.integration === value);
	return index >= 0 ? PLATFORM_COLORS[index % PLATFORM_COLORS.length] : "bg-gray-400";
}

function providerLabel(value) {
	return providers.value.find((p) => p.integration === value)?.label || value;
}

const notices = computed(() => {
	const out = [...(summary.value?.problems || [])];
	const selected = providers.value.find((p) => p.integration === integration.value);
	if (selected && !selected.enabled && !selected.problem) {
		out.push(
			`${selected.label} is registered but switched off, so Orders and Pending Payments have no data. Items and Sync Logs still show, because they come from Ecommerce Core.`,
		);
	} else if (!integration.value) {
		providers.value
			.filter((p) => !p.enabled && !p.problem)
			.forEach((p) =>
				out.push(`${p.label} is switched off; its orders and payments are hidden.`),
			);
	}
	if (!providers.value.length) {
		out.push(
			"No connector has registered with the ecommerce_dashboard_providers hook yet. Stat tiles, items and sync logs still show Ecommerce Core data.",
		);
	}
	return out;
});

function formatMoney(amount, currency) {
	if (currency) {
		return new Intl.NumberFormat(host.locale || undefined, {
			style: "currency",
			currency,
		}).format(amount || 0);
	}
	return new Intl.NumberFormat(host.locale || undefined).format(amount || 0);
}

function formatCount(value) {
	return new Intl.NumberFormat(host.locale || undefined).format(value || 0);
}

const tiles = computed(() => {
	const t = summary.value?.tiles;
	if (!t) return [];
	const pending = t.pending || [];
	const main = pending[0];
	const extra = pending.slice(1).map((p) => formatMoney(p.amount, p.currency));
	const pendingCount = pending.reduce((sum, p) => sum + p.count, 0);
	const alerts = (t.stock_out || 0) + (t.stock_low || 0);
	return [
		{
			label: "Integrations enabled",
			value: formatCount(t.enabled),
			sub:
				t.registered === t.enabled
					? "All registered connectors are on"
					: `${t.registered - t.enabled} switched off`,
			section: "orders",
		},
		{
			label: "Total outstanding",
			value: main ? formatMoney(main.amount, main.currency) : formatMoney(0),
			sub:
				`${formatCount(pendingCount)} pending invoices` +
				(extra.length ? ` · + ${extra.join(", ")}` : ""),
			section: "payments",
			filter: "",
		},
		{
			label: "Mapped items",
			value: formatCount(t.mapped_items),
			sub: "Ecommerce Item records",
			section: "items",
			filter: "",
		},
		{
			label: "Inventory syncs · last 24h",
			value: formatCount(t.synced_items),
			sub: `${formatCount(
				Math.max(t.mapped_items - t.synced_items, 0),
			)} mapped items not synced in the last 24 hours`,
			section: "items",
			filter: "",
		},
		{
			label: "Inventory alerts",
			value: formatCount(alerts),
			sub: t.stock_out
				? `${t.stock_out} out-of-stock items${
						t.stock_low ? ` · ${t.stock_low} low-stock items` : ""
				  }`
				: t.stock_low
				  ? `${t.stock_low} low-stock items`
				  : "No inventory alerts",
			tone: t.stock_out ? "warning" : "",
			section: "items",
			filter: t.stock_out ? "out" : "low",
		},
		{
			label: "Failed syncs · 7d",
			value: formatCount(t.failed_syncs),
			sub: t.failed_syncs ? "Click to review failed logs" : "All clear",
			tone: t.failed_syncs ? "danger" : "",
			section: "logs",
			filter: "failed",
		},
	];
});

const updatedLabel = computed(() => {
	if (!live.value) return "Auto-refresh paused";
	const seconds = lastRefresh.value ? Math.round((Date.now() - lastRefresh.value) / 1000) : 0;
	const updated = seconds < 5 ? "Updated just now" : `Updated ${seconds}s ago`;
	return `${updated} · next in ${countdown.value}s`;
});

// ----- section helpers -----

function sectionData(key) {
	return sectionRes[key].data || {};
}

function sectionRows(key) {
	return sectionData(key).rows || [];
}

function sectionCount(key) {
	return sectionData(key).total || 0;
}

// Connector-declared extra columns (orders only; harmless for other sections).
function detailColumns(key) {
	return (sectionData(key).columns || []).map((c) => ({
		key: c.key,
		label: c.label,
		kind: "detail",
		width: c.width || "140px",
	}));
}

const ORDERS_BASE_COLUMNS = [
	{ key: "order", label: "Order", kind: "order" },
	{ key: "platform", label: "Platform", kind: "platform" },
	{ key: "customer", label: "Customer", kind: "customer" },
	{ key: "amount", label: "Amount", kind: "amount" },
	{ key: "status", label: "Status", kind: "status" },
];
const ORDERS_TAIL_COLUMNS = [
	{ key: "invoice", label: "Invoice", kind: "invoice" },
	{ key: "created", label: "Created on", kind: "created" },
];
const PAYMENTS_COLUMNS = [
	{ key: "invoice", label: "Invoice", kind: "payment-invoice" },
	{ key: "party", label: "Customer", kind: "party" },
	{ key: "outstanding", label: "Outstanding", kind: "amount" },
	{ key: "status", label: "Status", kind: "status" },
	{ key: "created", label: "Created on", kind: "created" },
];
const ITEMS_COLUMNS = [
	{ key: "item", label: "Item", kind: "item" },
	{ key: "platform", label: "Platform", kind: "platform" },
	{ key: "sku", label: "SKU", kind: "sku" },
	{ key: "actual", label: "On hand", kind: "qty", tone: "text-blue-700" },
	{ key: "reserved", label: "Reserved for orders", kind: "qty", tone: "text-orange-700" },
	{ key: "available", label: "Available to sell", kind: "qty" },
	{ key: "stock", label: "Inventory status", kind: "stock" },
	{ key: "synced", label: "Last inventory sync", kind: "synced" },
	{ key: "push", label: "", kind: "push" },
];
const LOGS_COLUMNS = [
	{ key: "title", label: "Title", kind: "log-title" },
	{ key: "status", label: "Status", kind: "log-status" },
	{ key: "integration", label: "Integration", kind: "platform" },
	{ key: "modified", label: "Updated on", kind: "created" },
];

function sectionColumns(key) {
	if (key === "orders")
		return [...ORDERS_BASE_COLUMNS, ...detailColumns(key), ...ORDERS_TAIL_COLUMNS];
	if (key === "payments") return PAYMENTS_COLUMNS;
	if (key === "items") return ITEMS_COLUMNS;
	return LOGS_COLUMNS;
}

function sectionCountLabel(key) {
	const total = sectionCount(key);
	if (key === "payments") return `${formatCount(total)} outstanding`;
	if (key === "items") return `${formatCount(sectionData(key).counts?.all || total)} mapped`;
	if (key === "logs") return `${formatCount(sectionData(key).counts?.all || total)} jobs`;
	return formatCount(total);
}

function chipCount(key, value) {
	const counts = sectionData(key).counts || {};
	return formatCount(counts[value || "all"] || 0);
}

function setSection(key) {
	activeSection.value = key;
}

function setStatus(key, value) {
	sectionState[key].status = value || "";
	sectionState[key].page = 1;
	loadSection(key);
}

function setFilter(key, filterKey, value) {
	sectionState[key].filters[filterKey] = value || "";
	sectionState[key].page = 1;
	loadSection(key);
}

function onSearch(key, value) {
	clearTimeout(searchTimers[key]);
	searchTimers[key] = setTimeout(() => {
		sectionState[key].search = value || "";
		sectionState[key].page = 1;
		loadSection(key);
	}, 300);
}

function setPage(key, page) {
	const pages = Math.max(1, Math.ceil(sectionCount(key) / (SECTIONS[key].pageSize || 10)));
	const next = Math.min(Math.max(1, page), pages);
	if (next !== sectionState[key].page) {
		sectionState[key].page = next;
		loadSection(key);
	}
}

function pageNumbers(key) {
	const pages = Math.max(1, Math.ceil(sectionCount(key) / (SECTIONS[key].pageSize || 10)));
	const current = sectionState[key].page;
	let lo = Math.max(1, current - 2);
	const hi = Math.min(pages, lo + 4);
	lo = Math.max(1, hi - 4);
	const out = [];
	for (let page = lo; page <= hi; page++) out.push(page);
	return out;
}

function pageRange(key) {
	const total = sectionCount(key);
	if (!total) return "";
	const pageSize = SECTIONS[key].pageSize || 10;
	const start = (sectionState[key].page - 1) * pageSize;
	return `${formatCount(start + 1)}–${formatCount(
		Math.min(start + pageSize, total),
	)} of ${formatCount(total)}`;
}

function tileClick(tile) {
	const state = sectionState[tile.section];
	if (tile.filter !== undefined) {
		if (SECTIONS[tile.section].filterType === "chips") setStatus(tile.section, tile.filter);
		else setStatus(tile.section, tile.filter);
	}
	setSection(tile.section);
}

function emptyText(key) {
	const data = sectionData(key);
	if ((data.unsupported || []).length && !data.total) {
		return `${data.unsupported.join(", ")} does not provide data for this widget.`;
	}
	const state = sectionState[key];
	if (state.search) return `Nothing matches “${state.search}”.`;
	if (state.status) return "Nothing with this status.";
	return SECTIONS[key].empty;
}

function extraFilterOptions(key) {
	return sectionData(key).filter_options || [];
}

function extraFilterValue(key, filterKey) {
	return sectionState[key].filters[filterKey] || "";
}

function statusOptions(key) {
	const config = SECTIONS[key];
	const options = [{ value: "", label: "All statuses" }];
	(config.statusOptions || []).forEach((option) =>
		options.push({ value: option, label: option }),
	);
	return options;
}

// ----- row rendering helpers -----

const BADGE_THEMES = {
	red: "red",
	orange: "amber",
	yellow: "amber",
	green: "green",
	blue: "blue",
	gray: "gray",
};
const LOG_STATUS_THEMES = {
	Success: "green",
	Error: "red",
	Failure: "red",
	"Partial Success": "amber",
	Queued: "blue",
};
const STOCK_LABELS = {
	in: "Available for sale",
	low: "Low stock — reorder soon",
	out: "Out of stock",
	na: "Inventory not tracked",
};
const STOCK_TEXT = {
	in: "text-green-700",
	low: "text-amber-700",
	out: "text-red-700",
	na: "text-ink-gray-5",
};
const STOCK_BAR = { in: "bg-green-500", low: "bg-amber-500", out: "bg-red-500" };

function formLink(doctype, name) {
	const routes = {
		"Sales Order": "sales-order",
		"Sales Invoice": "sales-invoice",
		Item: "item",
		"Ecommerce Item": "ecommerce-item",
		"Ecommerce Integration Log": "ecommerce-integration-log",
	};
	const route = routes[doctype] || doctype.replace(/\s+/g, "-").toLowerCase();
	return `/app/${route}/${encodeURIComponent(name)}`;
}

function formatDateTime(value, emptyLabel = "Not available") {
	if (!value || String(value).startsWith("1970-01-01")) return emptyLabel;
	const date = new Date(String(value).replace(" ", "T"));
	if (Number.isNaN(date.getTime())) return emptyLabel;
	return new Intl.DateTimeFormat(host.locale || undefined, {
		day: "2-digit",
		month: "short",
		year: "numeric",
		hour: "2-digit",
		minute: "2-digit",
	}).format(date);
}

function formatQty(value) {
	return new Intl.NumberFormat(host.locale || undefined, { maximumFractionDigits: 2 }).format(
		value || 0,
	);
}

function detailsMap(row) {
	return Object.fromEntries((row.details || []).map((d) => [d.key, d.value]));
}

function stockBarWidth(row) {
	const scale = Math.max((row.reorder_level || 0) * 4, 1);
	const width =
		row.available > 0
			? Math.max(4, Math.min(100, Math.round((row.available / scale) * 100)))
			: 0;
	return row.reorder_level ? width : row.available > 0 ? 100 : 0;
}

function pushStock(name) {
	pushingItem.value = name;
	pushedMessage.value = "";
	pushStockRes.submit({ ecommerce_item: name }).finally(() => {
		pushingItem.value = null;
	});
}
</script>

<template>
	<div class="h-full overflow-y-auto">
		<div class="mx-auto flex max-w-10xl flex-col gap-5 p-5">
			<!-- integration tabs -->
			<nav
				class="flex flex-wrap items-center gap-1 border-b border-outline-gray-2"
				aria-label="Integrations"
			>
				<button
					v-for="tab in [
						{ integration: '', label: 'All Integrations', enabled: true },
						...providers,
					]"
					:key="tab.integration"
					type="button"
					class="-mb-px inline-flex items-center gap-2 border-b-2 px-3.5 py-2.5 text-sm font-semibold"
					:class="
						integration === tab.integration
							? 'border-ink-gray-9 text-ink-gray-9'
							: 'border-transparent text-ink-gray-6 hover:text-ink-gray-8'
					"
					@click="integration = tab.integration"
				>
					<span
						class="h-2 w-2 rounded-full"
						:class="
							tab.integration && tab.enabled
								? providerColor(tab.integration)
								: 'bg-gray-400'
						"
					></span>
					{{ tab.label }}
					<span
						v-if="tab.integration && !tab.enabled"
						class="text-xs font-medium text-ink-gray-5"
					>
						off
					</span>
				</button>
			</nav>

			<!-- notices -->
			<div
				v-for="(notice, i) in notices"
				:key="i"
				role="status"
				class="rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3 text-sm text-amber-900"
			>
				{{ notice }}
			</div>

			<!-- stat tiles -->
			<div class="grid grid-cols-1 gap-3.5 sm:grid-cols-2 xl:grid-cols-3">
				<button
					v-for="tile in tiles"
					:key="tile.label"
					type="button"
					class="flex min-h-32 min-w-0 flex-col gap-2 rounded-xl border border-outline-gray-2 bg-surface-white p-5 text-left transition hover:border-ink-gray-4"
					@click="tileClick(tile)"
				>
					<span class="text-lg font-bold tracking-wide text-ink-gray-7 uppercase">{{
						tile.label
					}}</span>
					<span
						class="text-3xl font-extrabold tracking-tight"
						:class="{
							'text-red-600': tile.tone === 'danger',
							'text-orange-600': tile.tone === 'warning',
						}"
					>
						{{ tile.value }}
					</span>
					<span class="truncate text-sm text-ink-gray-6" :title="tile.sub">{{
						tile.sub
					}}</span>
				</button>
			</div>

			<!-- section tabs -->
			<nav
				class="flex flex-wrap gap-2 rounded-lg bg-surface-gray-2 p-1"
				aria-label="Dashboard sections"
			>
				<button
					v-for="(config, key) in SECTIONS"
					:key="key"
					type="button"
					class="rounded-md px-3.5 py-1.5 text-sm font-semibold"
					:class="
						activeSection === key
							? 'bg-surface-white text-ink-gray-9 shadow-sm'
							: 'text-ink-gray-6 hover:text-ink-gray-8'
					"
					@click="setSection(key)"
				>
					{{ config.label }}
				</button>
			</nav>

			<p class="text-xs text-ink-gray-5">{{ updatedLabel }}</p>

			<!-- section panels -->
			<section
				v-for="(config, key) in SECTIONS"
				:key="key"
				v-show="activeSection === key"
				class="flex min-w-0 flex-col rounded-xl border border-outline-gray-2 bg-surface-white"
			>
				<div
					class="flex flex-wrap items-center justify-between gap-3 border-b border-outline-gray-2 px-4 py-3.5"
				>
					<div class="flex items-baseline gap-2">
						<h4 class="text-base font-semibold text-ink-gray-9">{{ config.label }}</h4>
						<span class="text-sm text-ink-gray-6">{{ sectionCountLabel(key) }}</span>
					</div>
					<div class="flex flex-wrap items-center gap-2">
						<div v-if="config.filterType === 'chips'" class="flex flex-wrap gap-1.5">
							<button
								v-for="[value, label] in config.chips"
								:key="value"
								type="button"
								class="rounded-full border px-2.5 py-1 text-xs font-semibold"
								:class="
									(sectionState[key].status || '') === value
										? 'border-ink-gray-9 bg-ink-gray-9 text-ink-white'
										: 'border-outline-gray-2 text-ink-gray-7 hover:border-ink-gray-4'
								"
								@click="setStatus(key, value)"
							>
								{{ label }}
								<span class="ml-0.5 opacity-75">{{ chipCount(key, value) }}</span>
							</button>
						</div>
						<div v-for="filter in extraFilterOptions(key)" :key="filter.key">
							<Select
								:model-value="extraFilterValue(key, filter.key)"
								:options="[
									{ value: '', label: `All ${filter.label}` },
									...filter.options.map(([v, l]) => ({ value: v, label: l })),
								]"
								class="w-44"
								@update:model-value="(value) => setFilter(key, filter.key, value)"
							/>
						</div>
						<Select
							v-if="config.filterType === 'select'"
							:model-value="sectionState[key].status"
							:options="statusOptions(key)"
							class="w-44"
							@update:model-value="(value) => setStatus(key, value)"
						/>
						<div class="w-60 max-w-full">
							<TextInput
								type="search"
								:placeholder="config.searchPlaceholder"
								:model-value="sectionState[key].search"
								@update:model-value="(value) => onSearch(key, value)"
							/>
						</div>
					</div>
				</div>

				<p
					v-for="(problem, i) in sectionData(key).problems || []"
					:key="'problem-' + i"
					class="border-b border-outline-gray-2 bg-red-50 px-4 py-2 text-xs text-red-700"
				>
					{{ problem }}
				</p>
				<p
					v-if="sectionRes[key].error"
					class="border-b border-outline-gray-2 bg-red-50 px-4 py-2 text-xs text-red-700"
				>
					{{
						sectionRes[key].error?.messages?.[0] ||
						sectionRes[key].error?.message ||
						sectionRes[key].error
					}}
				</p>

				<div class="overflow-x-auto">
					<table class="w-full min-w-max border-collapse text-sm">
						<thead>
							<tr
								class="border-b border-outline-gray-2 bg-surface-gray-1 text-left text-xs font-semibold uppercase tracking-wide text-ink-gray-6"
							>
								<th
									v-for="col in sectionColumns(key)"
									:key="col.key"
									class="whitespace-nowrap px-4 py-2.5"
									:style="{ width: col.width || undefined }"
								>
									{{ col.label }}
								</th>
							</tr>
						</thead>
						<tbody>
							<tr
								v-for="row in sectionRows(key)"
								:key="row.docname || row.name"
								class="border-b border-outline-gray-2 align-middle hover:bg-surface-gray-1"
							>
								<td
									v-for="col in sectionColumns(key)"
									:key="col.key"
									class="max-w-xs px-4 py-2"
								>
									<!-- orders -->
									<div v-if="col.kind === 'order'" class="flex flex-col">
										<a
											:href="formLink(row.doctype, row.docname)"
											class="font-semibold text-blue-600"
										>
											{{ row.id }}
										</a>
										<span class="text-xs text-ink-gray-5">{{
											row.docname
										}}</span>
									</div>
									<!-- payments invoice -->
									<div
										v-else-if="col.kind === 'payment-invoice'"
										class="flex flex-col"
									>
										<a
											:href="formLink(row.doctype, row.docname)"
											class="font-semibold text-blue-600"
										>
											{{ row.docname }}
										</a>
										<span
											class="flex items-center gap-1.5 text-xs text-ink-gray-5"
										>
											<span
												class="h-1.5 w-1.5 rounded-full"
												:class="providerColor(row.integration)"
											></span>
											{{ row.platform }}
										</span>
									</div>
									<!-- platform pill -->
									<span
										v-else-if="col.kind === 'platform'"
										class="flex items-center gap-1.5 text-xs font-medium text-ink-gray-8"
									>
										<span
											class="h-1.5 w-1.5 rounded-full"
											:class="providerColor(row.integration)"
										></span>
										{{ row.platform || providerLabel(row.integration) }}
									</span>
									<!-- customer / party -->
									<div
										v-else-if="col.kind === 'customer'"
										class="truncate"
										:title="row.customer"
									>
										{{ row.customer }}
									</div>
									<div v-else-if="col.kind === 'party'" class="flex flex-col">
										<span class="truncate" :title="row.party">{{
											row.party
										}}</span>
										<span
											class="truncate text-xs text-ink-gray-5"
											:title="row.note"
											>{{ row.note }}</span
										>
									</div>
									<!-- amount / outstanding -->
									<div v-else-if="col.kind === 'amount'" class="text-right">
										<span class="font-semibold">{{
											formatMoney(row.amount, row.currency)
										}}</span>
										<span
											v-if="row.total"
											class="block text-xs text-ink-gray-5"
										>
											of {{ formatMoney(row.total, row.currency) }}
										</span>
									</div>
									<!-- status pill -->
									<span
										v-else-if="col.kind === 'status'"
										class="inline-flex max-w-full items-center rounded-full bg-surface-gray-3 px-2.5 py-0.5 text-xs font-medium whitespace-nowrap text-ink-gray-7"
									>
										<span
											class="mr-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
											:class="{
												'bg-red-500': row.indicator === 'red',
												'bg-amber-500':
													row.indicator === 'orange' ||
													row.indicator === 'yellow',
												'bg-green-500': row.indicator === 'green',
												'bg-blue-500': row.indicator === 'blue',
												'bg-gray-400': ![
													'red',
													'orange',
													'yellow',
													'green',
													'blue',
												].includes(row.indicator),
											}"
										>
										</span>
										{{ row.status }}
									</span>
									<!-- invoice link -->
									<template v-else-if="col.kind === 'invoice'">
										<a
											v-if="row.invoice"
											:href="formLink('Sales Invoice', row.invoice)"
											class="text-blue-600"
										>
											{{ row.invoice }}
										</a>
										<span v-else class="text-ink-gray-5">Not billed</span>
									</template>
									<!-- created / updated -->
									<span
										v-else-if="col.kind === 'created'"
										class="whitespace-nowrap text-xs text-ink-gray-5"
									>
										{{ formatDateTime(row.created || row.modified) }}
									</span>
									<!-- connector-declared detail column -->
									<span
										v-else-if="col.kind === 'detail'"
										class="block truncate"
										:title="detailsMap(row)[col.key] || ''"
									>
										{{ detailsMap(row)[col.key] || "—" }}
									</span>
									<!-- items -->
									<div v-else-if="col.kind === 'item'" class="flex flex-col">
										<a
											:href="formLink('Item', row.item_code)"
											class="font-semibold text-blue-600"
										>
											{{ row.item_code }}
										</a>
										<span
											class="truncate text-xs text-ink-gray-5"
											:title="row.item_name"
											>{{ row.item_name }}</span
										>
									</div>
									<a
										v-else-if="col.kind === 'sku'"
										:href="formLink('Ecommerce Item', row.name)"
										class="font-mono text-xs text-ink-gray-6"
										:title="row.sku"
									>
										{{ row.sku }}
									</a>
									<span
										v-else-if="col.kind === 'qty'"
										class="block text-right font-bold"
										:class="
											col.key === 'available'
												? STOCK_TEXT[row.stock_status]
												: col.tone || ''
										"
									>
										{{ formatQty(row[col.key]) }}
									</span>
									<div
										v-else-if="col.kind === 'stock'"
										class="flex min-w-40 flex-col gap-1"
									>
										<div
											class="flex items-center justify-between gap-2 text-xs"
										>
											<span
												class="font-semibold"
												:class="STOCK_TEXT[row.stock_status]"
											>
												{{ STOCK_LABELS[row.stock_status] }}
											</span>
											<span v-if="row.reorder_level" class="text-ink-gray-5">
												Reorder at {{ formatQty(row.reorder_level) }}
											</span>
										</div>
										<div
											class="h-1.5 overflow-hidden rounded-full bg-surface-gray-3"
										>
											<div
												class="h-full rounded-full"
												:class="STOCK_BAR[row.stock_status]"
												:style="{ width: stockBarWidth(row) + '%' }"
											></div>
										</div>
									</div>
									<span
										v-else-if="col.kind === 'synced'"
										class="whitespace-nowrap text-xs text-ink-gray-5"
									>
										{{
											formatDateTime(row.inventory_synced_on, "Never synced")
										}}
									</span>
									<div v-else-if="col.kind === 'push'">
										<Button
											v-if="row.can_push"
											size="xs"
											variant="outline"
											label="Push stock"
											:loading="pushingItem === row.name"
											@click="pushStock(row.name)"
										/>
									</div>
									<!-- logs -->
									<template v-else-if="col.kind === 'log-title'">
										<a
											:href="formLink('Ecommerce Integration Log', row.name)"
											class="block max-w-sm truncate font-semibold text-blue-600"
											:title="row.title || row.name"
										>
											{{ row.title || row.name }}
										</a>
									</template>
									<span
										v-else-if="col.kind === 'log-status'"
										class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap"
										:class="{
											'bg-green-50 text-green-700':
												LOG_STATUS_THEMES[row.status] === 'green',
											'bg-red-50 text-red-700':
												LOG_STATUS_THEMES[row.status] === 'red',
											'bg-amber-50 text-amber-700':
												LOG_STATUS_THEMES[row.status] === 'amber',
											'bg-blue-50 text-blue-700':
												LOG_STATUS_THEMES[row.status] === 'blue',
											'bg-surface-gray-2 text-ink-gray-6':
												!LOG_STATUS_THEMES[row.status],
										}"
									>
										{{ row.status || "Unknown" }}
									</span>
									<span v-else>{{ row[col.key] }}</span>
								</td>
							</tr>
						</tbody>
					</table>

					<div v-if="sectionRes[key].loading" class="flex justify-center p-8">
						<Spinner class="h-5 w-5 text-ink-gray-6" />
					</div>
					<div
						v-else-if="!sectionRows(key).length"
						class="p-10 text-center text-sm text-ink-gray-5"
					>
						{{ emptyText(key) }}
					</div>
					<p
						v-if="key === 'items' && pushedMessage"
						class="px-4 py-2 text-xs text-green-700"
					>
						{{ pushedMessage }}
					</p>
				</div>

				<div
					class="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 text-sm text-ink-gray-6"
				>
					<span>{{ pageRange(key) }}</span>
					<div v-if="pageNumbers(key).length > 1" class="flex gap-1">
						<Button
							size="xs"
							variant="subtle"
							label="‹"
							:disabled="sectionState[key].page <= 1"
							@click="setPage(key, sectionState[key].page - 1)"
						/>
						<Button
							v-for="page in pageNumbers(key)"
							:key="page"
							size="xs"
							:variant="page === sectionState[key].page ? 'solid' : 'subtle'"
							:label="String(page)"
							@click="setPage(key, page)"
						/>
						<Button
							size="xs"
							variant="subtle"
							label="›"
							:disabled="
								sectionState[key].page >= pageNumbers(key).at(-1) &&
								sectionState[key].page >=
									Math.max(
										1,
										Math.ceil(
											sectionCount(key) / (SECTIONS[key].pageSize || 10),
										),
									)
							"
							@click="setPage(key, sectionState[key].page + 1)"
						/>
					</div>
				</div>
			</section>
		</div>
	</div>
</template>
