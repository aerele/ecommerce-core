<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import {
	Button,
	FormControl,
	TabButtons,
	toast,
	Badge,
	Skeleton,
	ErrorMessage,
	Dialog,
	ToastProvider,
	createResource,
	frappeRequest,
} from "frappe-ui";

import NoticeBanner from "../../../ui/components/NoticeBanner.vue";
import EmptyState from "../../../ui/components/EmptyState.vue";
import { doctypeRoute } from "../../../ui/island/desk_links.js";
import { mirrorCsrfToken } from "../../../ui/island/csrf.js";
import { onRealtimeEvent } from "../../../ui/island/realtime.js";
import ProductRowActions from "./components/ProductRowActions.vue";
import ProgressPanel from "./components/ProgressPanel.vue";
import StatusBadge from "./components/StatusBadge.vue";
import SyncPanel from "./components/SyncPanel.vue";

// Desk hands these down and updates them in place. `route` is the URL segments
// after the page name, and `query` its parameters (e.g. ?integration=shopify).
const props = defineProps({
	route: { type: Array, default: () => [] },
	query: { type: Object, default: () => ({}) },
});

// Desk writes `title` into the breadcrumb and turns each action into a page
// menu row; an action is { label, onClick }.
const emit = defineEmits(["title", "actions"]);

mirrorCsrfToken();

const API = "ecommerce_core.product_import.api";

const PAGE_SIZES = [20, 50, 100, 500, 2500];
const FILTER_OPTIONS = [
	{ value: "", label: "All" },
	{ value: "synced", label: "Synced" },
	{ value: "unsynced", label: "Not Synced" },
];

// ---------------------------------------------------------------- resources

const providersResource = createResource({
	url: `${API}.get_providers`,
	method: "GET",
	resourceFetcher: frappeRequest,
});
const diagnosticsResource = createResource({
	url: `${API}.get_provider_diagnostics`,
	method: "GET",
	resourceFetcher: frappeRequest,
});
const statsResource = createResource({
	url: `${API}.get_stats`,
	method: "GET",
	resourceFetcher: frappeRequest,
});
const syncStatusResource = createResource({
	url: `${API}.get_sync_status`,
	method: "GET",
	resourceFetcher: frappeRequest,
});
const syncProductResource = createResource({
	url: `${API}.sync_product`,
	resourceFetcher: frappeRequest,
});
const syncAllResource = createResource({
	url: `${API}.sync_all`,
	resourceFetcher: frappeRequest,
});
const syncSelectedResource = createResource({
	url: `${API}.sync_selected`,
	resourceFetcher: frappeRequest,
});

// ---------------------------------------------------------------- filters

const integration = ref(
	typeof props.query.integration === "string" ? props.query.integration : "",
);
const searchInput = ref("");
const search = ref("");
const syncFilter = ref("");
const forceFull = ref(false);
const pageSize = ref(20);

let searchTimer = null;
watch(searchInput, (value) => {
	clearTimeout(searchTimer);
	searchTimer = setTimeout(() => {
		search.value = value.trim();
	}, 300);
});
onBeforeUnmount(() => clearTimeout(searchTimer));

const providers = computed(() => providersResource.data || []);
const currentProvider = computed(
	() => providers.value.find((p) => p.integration === integration.value) || null,
);
const providerOptions = computed(() => [
	{ label: "All Integrations", value: "" },
	...providers.value.map((p) => ({ label: p.label, value: p.integration })),
]);

// ERPNext form routes resolve under /app inside the desk shell, so the
// connector's settings open as a normal desk navigation.
function settingsRoute(provider) {
	return doctypeRoute(provider?.settings_doctype);
}

function openSettings() {
	const route = settingsRoute(currentProvider.value);
	if (route) window.location.href = route;
}

// ---------------------------------------------------------------- rows

const cursorStack = ref([null]);
const pageIndex = ref(0);
const rows = ref([]);
const rowsTotal = ref(null);
const nextCursor = ref(null);
const mergedErrors = ref([]);
// Product ids are unique per provider, so state keys combine integration and id.
const rowKey = (item) => `${item.integration || integration.value || ""}:${item.id}`;
const selection = ref([]);

const listLoading = ref(false);
const listError = ref("");

const canGoPrev = computed(() => pageIndex.value > 0);
const canGoNext = computed(() => Boolean(nextCursor.value) && !listLoading.value);
const pageLabel = computed(() => {
	if (!rows.value.length) return "No products";
	const start = pageIndex.value * Number(pageSize.value) + 1;
	const end = start + rows.value.length - 1;
	return rowsTotal.value
		? `${start} – ${end} of ${rowsTotal.value}`
		: `Page ${pageIndex.value + 1} (${start} – ${end})`;
});

// Keep scanning (bounded) while a status filter finds no matches on this page.
const MAX_EMPTY_SCAN_HOPS = 5;
async function fetchRows(hop = 0) {
	listLoading.value = true;
	listError.value = "";
	try {
		const params = new URLSearchParams({
			integration: integration.value || "",
			limit: pageSize.value,
			cursor: cursorStack.value[pageIndex.value] || "",
			search: search.value || "",
			sync_filter: syncFilter.value || "",
		});
		const response = await fetch(`/api/method/${API}.get_products?${params}`, {
			method: "GET",
			headers: { Accept: "application/json" },
		});
		let body = null;
		try {
			body = await response.json();
		} catch (e) {
			/* non-JSON body; handled below */
		}
		if (!response.ok || body === null) {
			let message = "";
			try {
				message = JSON.parse(body._server_messages || "[]")
					.map((m) => JSON.parse(m).message)
					.join("\n");
			} catch (e) {
				/* fall through */
			}
			throw new Error(
				message ||
					body?.exception ||
					`Request failed (${response.status} ${response.statusText})`,
			);
		}
		const data = body.message;
		rows.value = data?.products || [];
		rowsTotal.value = data?.total ?? null;
		nextCursor.value = data?.next_cursor || null;
		mergedErrors.value = data?.errors || [];
		selection.value = [];
		if (
			!rows.value.length &&
			nextCursor.value &&
			syncFilter.value &&
			hop < MAX_EMPTY_SCAN_HOPS
		) {
			cursorStack.value[pageIndex.value] = nextCursor.value;
			return fetchRows(hop + 1);
		}
	} catch (err) {
		rows.value = [];
		rowsTotal.value = null;
		nextCursor.value = null;
		listError.value = errMessage(err);
		toast.error(listError.value);
	} finally {
		listLoading.value = false;
	}
}

function resetRows() {
	cursorStack.value = [null];
	pageIndex.value = 0;
	fetchRows();
}

function resetAndFetch() {
	resetRows();
	fetchStats();
	fetchSyncStatus();
}

// Stats and sync status depend only on the integration; search, status filter
// and page size just re-list rows.
watch(integration, resetAndFetch);
watch([search, syncFilter, pageSize], resetRows);

watch(
	() => props.query.integration,
	(value) => {
		if (typeof value === "string" && value !== integration.value) {
			integration.value = value;
		}
	},
);

function goPrev() {
	if (!canGoPrev.value) return;
	pageIndex.value -= 1;
	fetchRows();
}
function goNext() {
	if (!canGoNext.value) return;
	if (pageIndex.value === cursorStack.value.length - 1) {
		cursorStack.value.push(nextCursor.value);
	}
	pageIndex.value += 1;
	fetchRows();
}

// ---------------------------------------------------------------- stats

const stats = ref(null);

async function fetchStats() {
	if (!integration.value) {
		stats.value = null;
		return;
	}
	try {
		stats.value = await statsResource.submit({ integration: integration.value });
	} catch (err) {
		stats.value = null;
	}
}

// ---------------------------------------------------------------- bulk sync

const busy = ref(false);
const progressVisible = ref(false);
const progressRunning = ref(false);
const progressLines = reactive([]);
const progressUnsubscribers = [];
let progressDoneCount = 0;
let progressQueuedCount = 0;

function resetProgress() {
	while (progressUnsubscribers.length) progressUnsubscribers.pop()?.();
	progressLines.splice(0, progressLines.length);
	progressDoneCount = 0;
	progressQueuedCount = 0;
}

let progressStartedAt = 0;
let statusPoll = null;

function stopStatusPoll() {
	if (statusPoll) clearInterval(statusPoll);
	statusPoll = null;
}

function startStatusPoll() {
	stopStatusPoll();
	// The worker may be killed without ever publishing `done`; poll the server
	// so the UI cannot wait forever.
	statusPoll = setInterval(fetchSyncStatus, 2000);
}

function onProgressDone() {
	progressDoneCount += 1;
	if (progressDoneCount >= progressQueuedCount) {
		progressRunning.value = false;
		busy.value = false;
		stopStatusPoll();
		fetchRows();
		fetchStats();
		fetchSyncStatus();
		if (progressLines.some((l) => l.error))
			toast.warning("Synchronization finished with errors");
		else toast.success("Synchronization completed");
	}
}

function listenProgress(eventName) {
	progressQueuedCount += 1;
	progressUnsubscribers.push(
		onRealtimeEvent(eventName, (data) => {
			const text = String(data?.message || "")
				.replace(/<br\s*\/?>(\s*<br\s*\/?>)*/gi, "\n")
				.replace(/<[^>]+>/g, "")
				.trim();
			if (text)
				progressLines.push({
					text,
					error: Boolean(data?.error),
					done: Boolean(data?.done),
				});
			if (data?.done) onProgressDone();
		}),
	);
}

function startProgressListener(eventName) {
	resetProgress();
	progressStartedAt = Date.now();
	startStatusPoll();
	listenProgress(eventName);
}

async function fetchSyncStatus() {
	if (!integration.value) return;
	try {
		const status = await syncStatusResource.submit({ integration: integration.value });
		if (status?.running && !progressRunning.value) {
			// Resume an in-flight bulk sync after a page reload.
			busy.value = true;
			progressVisible.value = true;
			progressRunning.value = true;
			startProgressListener(status.event);
		} else if (
			!status?.running &&
			progressRunning.value &&
			Date.now() - progressStartedAt > 3000
		) {
			// Server says nothing is running (worker stopped/killed): stop waiting.
			busy.value = false;
			progressRunning.value = false;
			stopStatusPoll();
			progressLines.push({
				text: "Sync finished. If no progress was shown, check the Integration Log for the result.",
				error: false,
				done: true,
			});
			fetchRows();
			fetchStats();
			toast.success("Synchronization finished");
		}
		return status;
	} catch (err) {
		return null;
	}
}

function handleBulkQueued(result) {
	if (!result || result.status === "Busy") {
		toast.warning(result?.message || "A product sync is already running.");
		return;
	}
	busy.value = true;
	progressVisible.value = true;
	progressRunning.value = true;
	startProgressListener(result.event);
}

const showSyncAllDialog = ref(false);

function confirmSyncAll() {
	if (!integration.value) return;
	showSyncAllDialog.value = true;
}

async function syncAllItems() {
	showSyncAllDialog.value = false;
	try {
		const result = await syncAllResource.submit({
			integration: integration.value,
			search: search.value || null,
			sync_filter: syncFilter.value || null,
			force_full: forceFull.value ? 1 : 0,
		});
		handleBulkQueued(result);
	} catch (err) {
		toast.error(errMessage(err));
	}
}

async function syncSelected() {
	if (!selection.value.length) return;
	// Group the selection by each row's own integration so "All Integrations"
	// mode can sync across providers (the API takes one integration per call).
	const labels = {};
	const idsByIntegration = {};
	for (const row of rows.value) {
		if (!selection.value.includes(rowKey(row))) continue;
		labels[row.id] = row.name || row.id;
		const target = row.integration || integration.value;
		if (target) (idsByIntegration[target] ||= []).push(row.id);
	}
	const groups = Object.entries(idsByIntegration);
	if (!groups.length) return;
	resetProgress();
	try {
		for (const [target, productIds] of groups) {
			const result = await syncSelectedResource.submit({
				integration: target,
				product_ids: productIds,
				labels,
			});
			if (!result || result.status === "Busy") {
				toast.warning(
					result?.message || `A product sync is already running for ${target}.`,
				);
				continue;
			}
			progressVisible.value = true;
			progressRunning.value = true;
			listenProgress(result.event);
		}
		if (!progressQueuedCount) return;
		busy.value = true;
		selection.value = [];
	} catch (err) {
		toast.error(errMessage(err));
	}
}

const rowSyncing = ref(null);

async function syncSingle(product) {
	const target = product.integration || integration.value;
	if (!target) return;
	rowSyncing.value = rowKey(product);
	try {
		const result = await syncProductResource.submit({
			integration: target,
			product_id: product.id,
		});
		if (result?.ok) {
			toast.success(`Synced ${product.name || product.id}`);
		} else {
			toast.error(result?.error || `Could not sync ${product.name || product.id}`);
		}
		fetchRows();
		fetchStats();
	} catch (err) {
		toast.error(errMessage(err));
	} finally {
		rowSyncing.value = null;
	}
}

// ---------------------------------------------------------------- lifecycle

function emitActions() {
	emit("actions", [{ label: "Refresh", onClick: resetAndFetch }]);
}

onMounted(() => {
	emit("title", "Ecommerce Product Import");
	emitActions();
	providersResource.submit().catch(() => {});
	diagnosticsResource.submit().catch(() => {});
	fetchRows();
	fetchStats();
	fetchSyncStatus();
});

onBeforeUnmount(() => {
	stopStatusPoll();
	while (progressUnsubscribers.length) progressUnsubscribers.pop()?.();
});

function errMessage(err) {
	if (typeof err === "string") return err;
	return err?.messages?.[0] || err?.message || err?.exc || "Something went wrong";
}

// ---------------------------------------------------------------- list config

const gridCols = computed(() =>
	integration.value
		? "1.25rem 2rem minmax(0,2fr) minmax(0,1.2fr) 6.5rem 12rem"
		: "1.25rem 2rem 8rem minmax(0,2fr) minmax(0,1.2fr) 6.5rem 12rem",
);
const allSelected = computed(
	() => rows.value.length > 0 && selection.value.length === Math.min(rows.value.length, 100),
);
function toggleAll(e) {
	selection.value = e.target.checked ? rows.value.slice(0, 100).map(rowKey) : [];
	if (e.target.checked && rows.value.length > 100)
		toast.warning("Selected the first 100 products (the maximum per sync).");
}

const listColumns = computed(() => {
	const header = ["S.No", "Product", "SKU", "Status", ""];
	return integration.value ? header : ["S.No", "Integration", "Product", "SKU", "Status", ""];
});
</script>

<template>
	<ToastProvider />
	<div class="h-full overflow-y-auto">
		<div class="mx-auto flex max-w-10xl flex-col gap-5 p-5">
			<!-- Header -->
			<div class="flex items-center justify-between gap-3">
				<p class="text-p-sm text-ink-gray-5">
					Sync provider products into ERPNext Items and Ecommerce Item mappings.
				</p>
				<Button
					variant="solid"
					theme="gray"
					label="Sync Selected"
					icon-left="lucide-cloud-upload"
					:disabled="!selection.length || busy"
					:loading="syncSelectedResource.loading"
					@click="syncSelected"
				/>
			</div>

			<!-- Diagnostics: providers rejected at load time -->
			<NoticeBanner v-if="diagnosticsResource.data && diagnosticsResource.data.length">
				<span class="font-medium">Ignored integrations:</span>
				{{
					diagnosticsResource.data
						.map((d) => `${d.integration} (${d.reason})`)
						.join("; ")
				}}
			</NoticeBanner>

			<!-- Merged-mode provider errors -->
			<NoticeBanner v-if="mergedErrors.length" tone="danger">
				<span class="font-medium">Some integrations could not be listed:</span>
				{{ mergedErrors.map((e) => `${e.label}: ${e.error}`).join("; ") }}
			</NoticeBanner>

			<div class="grid grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
				<!-- Left: products -->
				<div
					class="flex min-w-0 flex-col rounded-xl border border-outline-gray-2 bg-surface-white"
				>
					<!-- Toolbar -->
					<div
						class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 p-3"
					>
						<div class="flex items-center gap-2">
							<div class="w-52">
								<FormControl
									v-model="integration"
									type="select"
									:options="providerOptions"
								/>
							</div>
							<Badge
								v-if="currentProvider"
								:label="currentProvider.enabled ? 'Enabled' : 'Disabled'"
								:theme="currentProvider.enabled ? 'green' : 'gray'"
								variant="subtle"
								size="sm"
							/>
							<Button
								v-if="settingsRoute(currentProvider)"
								variant="ghost"
								size="sm"
								icon="lucide-settings"
								@click="openSettings"
							/>
						</div>
						<div class="min-w-48 flex-1">
							<FormControl
								v-model="searchInput"
								type="search"
								placeholder="Product, SKU or ID"
							/>
						</div>
						<TabButtons v-model="syncFilter" :options="FILTER_OPTIONS" />
						<div class="w-32">
							<FormControl
								v-model="pageSize"
								type="select"
								:options="
									PAGE_SIZES.map((s) => ({ label: `${s} / page`, value: s }))
								"
							/>
						</div>
					</div>

					<!-- Table -->
					<Skeleton
						v-if="listLoading && !rows.length"
						class="h-64 w-full rounded-none"
					/>
					<ErrorMessage v-else-if="listError" :message="listError" />
					<EmptyState
						v-else-if="!rows.length"
						icon="lucide-package-search"
						title="No products found"
						hint="Adjust the filters, or enable and connect an integration."
					/>
					<div v-else class="overflow-x-auto">
						<div class="min-w-[44rem]">
							<div
								class="grid items-center gap-x-3 border-b border-outline-gray-2 px-4 py-2 text-p-sm text-ink-gray-5"
								:style="{ gridTemplateColumns: gridCols }"
							>
								<div>
									<input
										type="checkbox"
										class="size-3.5 cursor-pointer rounded-[4px]"
										:checked="allSelected"
										@change="toggleAll"
									/>
								</div>
								<div v-for="col in listColumns" :key="col">{{ col }}</div>
							</div>
							<div
								v-for="(item, index) in rows"
								:key="rowKey(item)"
								class="grid h-12 items-center gap-x-3 border-b border-outline-gray-2 px-4 text-p-sm last:border-b-0 hover:bg-surface-gray-1"
								:style="{ gridTemplateColumns: gridCols }"
							>
								<div>
									<input
										type="checkbox"
										class="size-3.5 cursor-pointer rounded-[4px]"
										:value="rowKey(item)"
										v-model="selection"
									/>
								</div>
								<div class="text-ink-gray-5">
									{{ pageIndex * Number(pageSize) + index + 1 }}
								</div>
								<div v-if="!integration" class="truncate text-ink-gray-6">
									{{ item.provider_label || item.integration }}
								</div>
								<div class="min-w-0">
									<div
										class="truncate font-medium text-ink-gray-8"
										:title="item.name || item.id"
									>
										{{ item.name || item.id }}
									</div>
									<div class="truncate text-p-xs text-ink-gray-4">
										{{ item.id }}
									</div>
								</div>
								<div class="truncate text-ink-gray-6" :title="item.sku">
									{{ item.sku || "—" }}
								</div>
								<div><StatusBadge :state="item.sync_state" /></div>
								<ProductRowActions
									:product="item"
									:busy="busy"
									:syncing="rowSyncing === rowKey(item)"
									@sync="syncSingle"
								/>
							</div>
						</div>
					</div>

					<!-- Pagination -->
					<div
						class="flex items-center justify-between border-t border-outline-gray-2 p-2.5 text-p-sm text-ink-gray-5"
					>
						<span>{{ pageLabel }}</span>
						<div class="flex items-center gap-1.5">
							<Button
								variant="ghost"
								size="sm"
								icon="lucide-chevron-left"
								:disabled="!canGoPrev || listLoading"
								@click="goPrev"
							/>
							<Button
								variant="ghost"
								size="sm"
								icon="lucide-chevron-right"
								:disabled="!canGoNext"
								@click="goNext"
							/>
						</div>
					</div>
				</div>

				<!-- Right: sync panel + progress -->
				<div class="space-y-5">
					<div v-if="integration">
						<SyncPanel
							:provider="currentProvider"
							:stats="stats"
							:busy="busy"
							:syncing-all="syncAllResource.loading"
							@sync-all="confirmSyncAll"
						/>
					</div>
					<div
						v-else
						class="rounded-xl border border-outline-gray-2 bg-surface-white p-4 text-p-sm text-ink-gray-5"
					>
						Select an integration to run a full sync and see statistics.
					</div>

					<ProgressPanel
						:visible="progressVisible"
						:running="progressRunning"
						:lines="progressLines"
						:progress-value="null"
						@clear="
							resetProgress();
							progressVisible = false;
						"
					/>
				</div>
			</div>
		</div>

		<!-- Sync All confirmation (inline Dialog, so it portals inside the island) -->
		<Dialog v-model="showSyncAllDialog" title="Sync all items?">
			<p class="text-p-base text-ink-gray-7">
				Every product from {{ currentProvider?.label || integration }} matching the current
				filters will be queued for synchronization.
				<template v-if="currentProvider?.supports_incremental">
					Products unchanged since their last sync are skipped.
				</template>
			</p>
			<FormControl
				v-if="currentProvider?.supports_incremental"
				v-model="forceFull"
				type="checkbox"
				label="Force full sync (re-sync unchanged products too)"
				class="mt-3"
			/>
			<template #actions>
				<Button variant="ghost" label="Cancel" @click="showSyncAllDialog = false" />
				<Button variant="solid" theme="gray" label="Sync All" @click="syncAllItems" />
			</template>
		</Dialog>
	</div>
</template>
