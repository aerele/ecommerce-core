<script setup>
import { computed } from "vue"
import { Button, Badge } from "frappe-ui"

const props = defineProps({
  provider: { type: Object, required: true },
  stats: { type: Object, default: null },
  busy: { type: Boolean, default: false },
  syncingAll: { type: Boolean, default: false },
})

defineEmits(["sync-all"])

// Desk routes in Frappe v16 live under /desk; plain navigation keeps the
// SPA router (base /ecommerce-core/) from rewriting the path.
const settingsRoute = computed(() => {
  const doctype = props.provider?.settings_doctype
  return doctype
    ? `/desk/${String(doctype).toLowerCase().replaceAll(" ", "-")}`
    : null
})

function openSettings() {
  if (settingsRoute.value) window.location.href = settingsRoute.value
}
</script>

<template>
  <div class="rounded-6 border border-outline-gray-1 bg-surface-base p-4">
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-medium text-ink-gray-8">Synchronization</h3>
      <Badge
        :label="provider?.enabled ? 'Enabled' : 'Disabled'"
        :theme="provider?.enabled ? 'green' : 'gray'"
        variant="subtle"
        size="sm"
      />
    </div>

    <div class="mt-3 flex items-center gap-2">
      <Button
        variant="solid"
        theme="gray"
        label="Sync All Items"
        icon-left="lucide-refresh-cw"
        :loading="syncingAll"
        :disabled="busy"
        @click="$emit('sync-all')"
      />
      <Button
        v-if="settingsRoute"
        variant="ghost"
        size="sm"
        label="Settings"
        icon-left="lucide-settings"
        @click="openSettings"
      />
    </div>

    <div v-if="stats" class="mt-4 grid grid-cols-3 gap-2">
      <div class="rounded-4 bg-surface-gray-1 p-2.5">
        <div class="text-lg font-semibold text-ink-gray-8">
          {{ stats.provider_count ?? "—" }}
        </div>
        <div class="text-xs text-ink-gray-5">Products</div>
      </div>
      <div class="rounded-4 bg-surface-gray-1 p-2.5">
        <div class="text-lg font-semibold text-ink-gray-8">
          {{ stats.mapped ?? "—" }}
        </div>
        <div class="text-xs text-ink-gray-5">Mapped</div>
      </div>
      <div class="rounded-4 bg-surface-gray-1 p-2.5">
        <div class="text-lg font-semibold text-ink-gray-8">
          {{ stats.synced ?? "—" }}
        </div>
        <div class="text-xs text-ink-gray-5">Synced</div>
      </div>
    </div>
  </div>
</template>
