<script setup>
import { computed } from "vue";
import { Badge } from "frappe-ui";

const props = defineProps({
	state: { type: String, default: "unsynced" },
});

const THEMES = { synced: "green", unsynced: "amber" };
const LABELS = { synced: "Synced", unsynced: "Not Synced" };

const theme = computed(() => THEMES[props.state] || "gray");
const label = computed(() => LABELS[props.state] || props.state);
</script>

<template>
	<Badge :label="label" :theme="theme" variant="subtle" size="sm" />
</template>
