import { io } from "socket.io-client"

let socket = null

// Frappe's socketio server scopes every site to the namespace "/<site_name>",
// so events published with frappe.publish_realtime only reach clients that
// join it. Like Desk (socketio_client.js), the dev server talks to the
// socketio port directly; production goes through the web server's proxy on
// the same origin.
function socketUrl() {
  const site = window.site_name || window.location.hostname
  let host = window.location.origin
  if (import.meta.env.DEV) {
    const port = window.socketio_port ?? window.boot?.socketio_port ?? 9000
    host = `${window.location.protocol}//${window.location.hostname}:${port}`
  }
  return `${host}/${site}`
}

export function getSocket() {
  if (!socket) {
    socket = io(socketUrl(), { withCredentials: true, reconnectionAttempts: 5 })
  }
  return socket
}

/**
 * Listen to one realtime event for the lifetime of the handler.
 * Returns an unsubscribe function.
 */
export function onEvent(event, handler) {
  const socket = getSocket()
  socket.on(event, handler)
  return () => socket.off(event, handler)
}
