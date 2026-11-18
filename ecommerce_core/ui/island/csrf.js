// frappe-ui reads the CSRF token from window.csrf_token; desk keeps it on
// frappe.csrf_token. Call this once per island page.
export function mirrorCsrfToken() {
	if (typeof window === "undefined") return;
	if (window.csrf_token && window.csrf_token !== "{{ csrf_token }}") return;
	const token = window.frappe?.csrf_token;
	if (token) window.csrf_token = token;
}
