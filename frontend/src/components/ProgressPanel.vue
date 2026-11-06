<script setup>
import { computed, ref, watch, nextTick } from "vue"
import { Progress, Button } from "frappe-ui"

const props = defineProps({
  visible: { type: Boolean, default: false },
  running: { type: Boolean, default: false },
  lines: { type: Array, default: () => [] },
  progressValue: { type: Number, default: null },
})

const consoleEl = ref(null)

const errorLines = computed(() => props.lines.filter((l) => l.error).length)

// Keep the console pinned to the newest line.
watch(
  () => props.lines.length,
  async () => {
    await nextTick()
    if (consoleEl.value) {
      consoleEl.value.scrollTop = consoleEl.value.scrollHeight
    }
  },
)
</script>

<template>
  <div v-if="visible" class="rounded-6 border border-outline-gray-1 bg-surface-base p-4">
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-medium text-ink-gray-8">Sync Progress</h3>
      <div class="flex items-center gap-2 text-xs text-ink-gray-5">
        <span v-if="errorLines" class="text-ink-red-5">{{ errorLines }} failed</span>
        <span v-if="running" class="flex items-center gap-1">
          <span class="size-1.5 animate-pulse rounded-full bg-surface-amber-3" />
          running
        </span>
      </div>
    </div>

    <Progress
      v-if="progressValue !== null"
      class="mt-3"
      :value="progressValue"
      size="sm"
      :hint="running ? 'Processing…' : 'Done'"
    />

    <div
      ref="consoleEl"
      class="mt-3 max-h-56 overflow-y-auto rounded-4 bg-surface-gray-2 p-2.5 font-mono text-xs leading-5 text-ink-gray-7"
    >
      <div
        v-for="(line, i) in lines"
        :key="i"
        class="whitespace-pre-wrap"
        :class="{
          'text-ink-red-5': line.error,
          'text-ink-green-6': line.done,
        }"
      >
        {{ line.text }}
      </div>
      <div v-if="!lines.length" class="text-ink-gray-4">Waiting for progress…</div>
    </div>

    <Button
      v-if="!running && lines.length"
      class="mt-2"
      variant="ghost"
      size="xs"
      label="Clear log"
      icon-left="lucide-eraser"
      @click="$emit('clear')"
    />
  </div>
</template>
