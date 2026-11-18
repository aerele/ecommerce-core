// Islands navigate with plain URLs; desk's router owns the shell.

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
