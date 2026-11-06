<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import {
	Button,
	FormControl,
	TabButtons,
	toast,
	dialog,
	ErrorMessage,
	Skeleton,
	Badge,
} from "frappe-ui";
import { usePageMeta } from "frappe-ui";

import {
	providersResource,
	diagnosticsResource,
	productsResource,
	statsResource,
	syncStatusResource,
	syncProductResource,
	syncAllResource,
	syncSelectedResource,
} from "@/data/productSync";
import { onEvent } from "@/lib/socket";
import StatusBadge from "@/components/StatusBadge.vue";
import ProductRowActions from "@/components/ProductRowActions.vue";
import SyncPanel from "@/components/SyncPanel.vue";
import ProgressPanel from "@/components/ProgressPanel.vue";

usePageMeta({ title: "Product Sync" });

const PAGE_SIZES = [20, 50, 100, 500, 2500];
const FILTER_OPTIONS = [
	{ value: "", label: "All" },
	{ value: "synced", label: "Synced" },
	{ value: "unsynced", label: "Not Synced" },
];

// ---------------------------------------------------------------- filters
const integration = ref("");
const searchInput = ref("");
const search = ref("");
const syncFilter = ref("");
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

// Desk routes in Frappe v16 live under /desk; plain navigation keeps the
// SPA router (base /ecommerce-core/) from rewriting the path.
function deskRoute(doctype) {
	return doctype ? `/app/${String(doctype).toLowerCase().replaceAll(" ", "-")}` : null;
}

const settingsRoute = computed(() => deskRoute(currentProvider.value?.settings_doctype));

function openSettings() {
	if (settingsRoute.value) window.location.href = settingsRoute.value;
}

// ---------------------------------------------------------------- rows
const cursorStack = ref([null]);
const pageIndex = ref(0);
const rows = ref([]);
const rowsTotal = ref(null);
const nextCursor = ref(null);
const mergedErrors = ref([]);
const selection = ref([]);

const listLoading = computed(() => productsResource.loading);

const canGoPrev = computed(() => pageIndex.value > 0);
const canGoNext = computed(() => Boolean(nextCursor.value) && !listLoading.value);
const pageLabel = computed(() => {
	if (!rows.value.length) return "No products";
	const start = pageIndex.value * pageSize.value + 1;
	const end = start + rows.value.length - 1;
	return rowsTotal.value
		? `${start} – ${end} of ${rowsTotal.value}`
		: `Page ${pageIndex.value + 1} (${start} – ${end})`;
});

async function fetchRows() {
	try {
		const data = await productsResource.submit({
			integration: integration.value,
			limit: pageSize.value,
			cursor: cursorStack.value[pageIndex.value],
			search: search.value || null,
			sync_filter: syncFilter.value || null,
		});
		rows.value = data?.products || [];
		rowsTotal.value = data?.total ?? null;
		nextCursor.value = data?.next_cursor || null;
		mergedErrors.value = data?.errors || [];
		selection.value = [];
	} catch (err) {
		rows.value = [];
		rowsTotal.value = null;
		nextCursor.value = null;
		toast.error(errMessage(err));
	}
}

function resetAndFetch() {
	cursorStack.value = [null];
	pageIndex.value = 0;
	fetchRows();
}

watch([integration, search, syncFilter, pageSize], resetAndFetch);

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
const statsLoading = ref(false);

async function fetchStats() {
	if (!integration.value) {
		stats.value = null;
		return;
	}
	statsLoading.value = true;
	try {
		stats.value = await statsResource.submit({ integration: integration.value });
	} catch (err) {
		stats.value = null;
	} finally {
		statsLoading.value = false;
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

function onProgressDone() {
	progressDoneCount += 1;
	if (progressDoneCount >= progressQueuedCount) {
		progressRunning.value = false;
		busy.value = false;
		fetchRows();
		fetchStats();
		fetchSyncStatus();
		toast.success("Synchronization completed");
	}
}

function listenProgress(eventName) {
	progressQueuedCount += 1;
	progressUnsubscribers.push(
		onEvent(eventName, (data) => {
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
		} else if (!status?.running && progressRunning.value) {
			busy.value = false;
			progressRunning.value = false;
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

async function syncAllItems() {
	if (!integration.value) return;
	dialog.confirm({
		title: "Sync all items?",
		message: `Every product from ${
			currentProvider.value?.label || integration.value
		} matching the current filters will be queued for synchronization.`,
		confirmLabel: "Sync All",
		onConfirm: async ({ setError }) => {
			try {
				const result = await syncAllResource.submit({
					integration: integration.value,
					search: search.value || null,
					sync_filter: syncFilter.value || null,
				});
				handleBulkQueued(result);
			} catch (err) {
				setError(errMessage(err));
			}
		},
	});
}

async function syncSelected() {
	if (!selection.value.length) return;
	// Group the selection by each row's own integration so "All Integrations"
	// mode can sync across providers (the API takes one integration per call).
	const labels = {};
	const idsByIntegration = {};
	for (const row of rows.value) {
		if (!selection.value.includes(row.id)) continue;
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
	rowSyncing.value = product.id;
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
	} catch (err) {
		toast.error(errMessage(err));
	} finally {
		rowSyncing.value = null;
	}
}

// ---------------------------------------------------------------- lifecycle
onMounted(() => {
	fetchRows();
	fetchStats();
	fetchSyncStatus();
});

onBeforeUnmount(() => {
	while (progressUnsubscribers.length) progressUnsubscribers.pop()?.();
});

function errMessage(err) {
	if (typeof err === "string") return err;
	return err?.message || err?.exc || "Something went wrong";
}

// ---------------------------------------------------------------- list config
const gridCols = computed(() =>
	integration.value
		? "1.25rem 2rem minmax(0,2fr) minmax(0,1.2fr) 6.5rem 12rem"
		: "1.25rem 2rem 8rem minmax(0,2fr) minmax(0,1.2fr) 6.5rem 12rem",
);
const allSelected = computed(
	() => rows.value.length > 0 && selection.value.length === rows.value.length,
);
function toggleAll(e) {
	selection.value = e.target.checked ? rows.value.map((r) => r.id) : [];
}

const listColumns = computed(() => {
	const header = ["S.No", "Product", "SKU", "Status", ""];
	return integration.value ? header : ["S.No", "Integration", "Product", "SKU", "Status", ""];
});
</script>

<template>
	<div class="min-h-screen w-full bg-surface-gray-1 text-ink-gray-8">
		<div class="mx-auto max-w-7xl px-4 py-6">
			<!-- Header -->
			<div class="flex items-center justify-between">
				<div>
					<h1 class="text-xl font-semibold text-ink-gray-8">Product Sync</h1>
					<p class="text-p-sm text-ink-gray-5">
						Sync provider products into ERPNext Items and Ecommerce Item mappings.
					</p>
				</div>
				<Button
					variant="solid"
					theme="gray"
					label="Sync Selected"
					icon-left="lucide-upload-cloud"
					:disabled="!selection.length || busy"
					:loading="syncSelectedResource.loading"
					@click="syncSelected"
				/>
			</div>

			<!-- Diagnostics: providers rejected at load time -->
			<div
				v-if="diagnosticsResource.data && diagnosticsResource.data.length"
				class="mt-4 rounded-6 border border-outline-amber-2 bg-surface-amber-1 p-3 text-p-sm text-ink-amber-6"
			>
				<span class="font-medium">Ignored integrations:</span>
				{{
					diagnosticsResource.data
						.map((d) => `${d.integration} (${d.reason})`)
						.join("; ")
				}}
			</div>

			<!-- Merged-mode provider errors -->
			<div
				v-if="mergedErrors.length"
				class="mt-4 rounded-6 border border-outline-red-2 bg-surface-red-1 p-3 text-p-sm text-ink-red-6"
			>
				<span class="font-medium">Some integrations could not be listed:</span>
				{{ mergedErrors.map((e) => `${e.label}: ${e.error}`).join("; ") }}
			</div>

			<div
				class="mt-5 grid grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]"
			>
				<!-- Left: products -->
				<div class="rounded-6 border border-outline-gray-1 bg-surface-base">
					<!-- Toolbar -->
					<div
						class="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 p-3"
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
								v-if="settingsRoute"
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
					<ErrorMessage
						v-else-if="productsResource.error"
						:message="productsResource.error"
					/>
					<div
						v-else-if="!rows.length"
						class="flex flex-col items-center gap-3 py-16 text-center"
					>
						<div class="rounded-full bg-surface-gray-2 p-3 text-ink-gray-5">
							<span class="lucide-package-search size-6" aria-hidden="true" />
						</div>
						<p class="text-base text-ink-gray-7">No products found</p>
						<p class="text-sm text-ink-gray-5">
							Adjust the filters, or enable and connect an integration.
						</p>
					</div>
					<div v-else class="overflow-x-auto">
						<div class="min-w-[44rem]">
							<div
								class="grid items-center gap-x-3 border-b border-outline-gray-1 px-4 py-2 text-p-sm text-ink-gray-5"
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
								:key="item.id"
								class="grid h-12 items-center gap-x-3 border-b border-outline-gray-1 px-4 text-p-sm last:border-b-0 hover:bg-surface-gray-1"
								:style="{ gridTemplateColumns: gridCols }"
							>
								<div>
									<input
										type="checkbox"
										class="size-3.5 cursor-pointer rounded-[4px]"
										:value="item.id"
										v-model="selection"
									/>
								</div>
								<div class="text-ink-gray-5">{{ index + 1 }}</div>
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
									:syncing="rowSyncing === item.id"
									@sync="syncSingle"
								/>
							</div>
						</div>
					</div>

					<!-- Pagination -->
					<div
						class="flex items-center justify-between border-t border-outline-gray-1 p-2.5 text-p-sm text-ink-gray-5"
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
							@sync-all="syncAllItems"
						/>
					</div>
					<div
						v-else
						class="rounded-6 border border-outline-gray-1 bg-surface-base p-4 text-p-sm text-ink-gray-5"
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
	</div>
</template>
