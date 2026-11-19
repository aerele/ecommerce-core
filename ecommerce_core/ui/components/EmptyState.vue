<script setup>
// The empty-list block both shared pages show when a widget has no rows.
defineProps({
	icon: { type: String, default: "lucide-package-search" },
	title: { type: String, required: true },
	hint: { type: String, default: "" },
});
</script>

<template>
	<div class="flex flex-col items-center gap-3 py-16 text-center">
		<div class="rounded-full bg-surface-gray-2 p-3 text-ink-gray-5">
			<span :class="icon" class="size-6" aria-hidden="true" />
		</div>
		<p class="text-base text-ink-gray-7">{{ title }}</p>
		<p v-if="hint" class="text-sm text-ink-gray-5">{{ hint }}</p>
	</div>
</template>
