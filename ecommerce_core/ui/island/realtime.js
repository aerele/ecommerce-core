// Desk owns the socket.io connection and exposes it as `frappe.realtime`, so
// progress events published with frappe.publish_realtime reach an island
// without a socket.io client of its own.
//
// Returns an unsubscribe function, mirroring the old SPA socket helper's
// contract so page logic does not care where the events come from.
export function onRealtimeEvent(event, handler) {
	const realtime = window.frappe?.realtime;
	if (!realtime?.on) return () => {};
	realtime.on(event, handler);
	return () => {
		try {
			realtime.off(event, handler);
		} catch {
			// the client may already be torn down during page unload
		}
	};
}
