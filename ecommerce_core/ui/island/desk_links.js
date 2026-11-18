// ERPNext form routes resolve under /app inside the desk shell. Islands must
// navigate with plain URLs (window.location, plain anchors) — never with a
// router of their own, because the island contract gives each page one URL
// and desk's own router owns the shell around it.

/** Form route for a document, e.g. `formLink("Sales Order", "SO-0001")`. */
export function formLink(doctype, name) {
	const route = slugged(doctype);
	return name ? `/app/${route}/${encodeURIComponent(name)}` : `/app/${route}`;
}

/** List / settings route for a DocType, e.g. `doctypeRoute("Medusa Settings")`. */
export function doctypeRoute(doctype) {
	return doctype ? `/app/${slugged(doctype)}` : null;
}

function slugged(doctype) {
	return String(doctype).toLowerCase().replaceAll(" ", "-");
}
