<script setup>
import { computed, ref } from "vue";
import { Button, Dialog, Tooltip } from "frappe-ui";
import { formLink } from "../../../../ui/island/desk_links.js";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps({
	product: { type: Object, required: true },
	syncing: { type: Boolean, default: false },
	busy: { type: Boolean, default: false },
});

defineEmits(["sync"]);

const isSynced = computed(() => props.product.sync_state === "synced");
const variants = computed(() => props.product.variants || []);

const variantNames = computed(() =>
	variants.value
		.map((v) => (typeof v === "string" ? v : v.sku || v.id || v.name))
		.filter(Boolean),
);

const showVariants = ref(false);

// The island fills a desk page, so ERPNext form routes resolve under /app like
// everywhere else in the desk; the item opens in a new tab to keep the sync
// filters and selection alive.
function openItem() {
	window.open(formLink("Item", props.product.erpnext_item_code), "_blank", "noopener");
}
</script>

<template>
	<div class="flex items-center justify-end gap-1.5 whitespace-nowrap">
		<Button
			v-if="variantNames.length"
			variant="ghost"
			size="xs"
			:label="`${variants.length} variant${variants.length > 1 ? 's' : ''}`"
			@click="showVariants = true"
		/>
		<Tooltip v-if="product.erpnext_item_code" :text="product.erpnext_item_code">
			<Button variant="ghost" size="xs" icon-left="lucide-box" @click="openItem" />
		</Tooltip>
		<Button
			size="xs"
			:variant="isSynced ? 'subtle' : 'solid'"
			theme="gray"
			:label="isSynced ? 'Re-sync' : 'Sync'"
			:loading="syncing"
			:disabled="busy"
			@click="$emit('sync', product)"
		/>
		<Dialog v-model="showVariants" :title="`Variants (${variantNames.length})`">
			<ul class="max-h-72 space-y-1.5 overflow-y-auto text-p-sm text-ink-gray-7">
				<li
					v-for="name in variantNames"
					:key="name"
					class="rounded border border-outline-gray-1 bg-surface-gray-1 px-2.5 py-1.5"
				>
					{{ name }}
				</li>
			</ul>
		</Dialog>
	</div>
</template>
