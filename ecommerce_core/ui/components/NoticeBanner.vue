<script setup>
// The notice banner both shared pages use for provider problems: rejected
// hook entries, unreachable connectors, switched-off integrations.
defineProps({
	// "warning" (amber) for informational skips, "danger" (red) for failures.
	tone: { type: String, default: "warning" },
});
</script>

<template>
	<div
		role="status"
		class="rounded-lg border border-outline-gray-2 px-3.5 py-3 text-sm"
		:class="tone === 'danger' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-900'"
	>
		<slot />
	</div>
</template>
