// frappe-ui's frappeRequest reads the CSRF token from `window.csrf_token`,
// which the v17 desk no longer sets (it keeps it on `frappe.csrf_token`).
// Without this mirror, every authenticated POST from an island fails with
// "Invalid Request". Call it once in each island page's `<script setup>`.
export function mirrorCsrfToken() {
	if (typeof window === "undefined") return;
	if (window.csrf_token && window.csrf_token !== "{{ csrf_token }}") return;
	const token = window.frappe?.csrf_token;
	if (token) window.csrf_token = token;
}
