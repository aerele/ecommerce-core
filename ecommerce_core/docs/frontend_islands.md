# Frontend islands — house rules

Every shared Desk page in Ecommerce Core is a **Frappe UI page** (a Vue island): a `Page`
doc with `"type": "Frappe UI"`, an `<page>.island.js` mount entry and the page's `.vue`
sources beside it in the page folder. Frappe's island build (one build for the whole bench)
compiles them, so apps carry no bundler config and no `app_include_js`. Existing pages:
`ecommerce-dashboard`, `ecommerce-product-import`.

## Page folder layout

```
ecommerce_core/ecommerce_core/page/<page>/
	<page>.json          # Page doc, "type": "Frappe UI"
	<page>.island.js     # the one mount export (see an existing page; keep it 4 lines)
	<page>.vue           # the page component
	components/          # page-private subcomponents
```

Link the page from `workspace/ecommerce_core/ecommerce_core.json` and
`workspace_sidebar/ecommerce_core.json` (`link_type: "Page"`) — never from `hooks.py`.

## Component contract

- The page component takes `route` (Array) and `query` (Object) props and emits `title`
  and `actions` — desk renders them as breadcrumb and page menu. No `usePageMeta`, no
  router of your own.
- Call `mirrorCsrfToken()` once in `<script setup>` (frappe-ui posts need
  `window.csrf_token`, which v17 desk no longer sets).
- Mount frappe-ui's `<ToastProvider />` in the page template — `toast` is a no-op in an
  island without a mounted Toaster.
- Realtime progress rides desk's `frappe.realtime` via `onRealtimeEvent(event, handler)`.
  Never open a socket.io client of your own.
- Navigate with plain `/app/...` URLs from `formLink()` / `doctypeRoute()`. Never link
  into an SPA route; never call `window.open` on `/desk/...` paths.
- Overlays (Dialog, Select menus, popovers) portal inside the island automatically; build
  confirmations as inline `<Dialog>` components, not imperative helpers that mount to
  `document.body` outside the shadow root.
- Styling is Tailwind via the frappe-ui preset, scanned from the bundle — no style imports,
  no global CSS.

## Shared code lives in `ecommerce_core/ui/`

Anything two pages need belongs here, not in a page folder:

```
ui/
	island/csrf.js           # mirrorCsrfToken()
	island/realtime.js       # onRealtimeEvent()
	island/desk_links.js     # formLink(), doctypeRoute()
	components/NoticeBanner.vue
	components/EmptyState.vue
```

The bench-wide island build shares vue and frappe-ui chunks across all islands, and modules
imported by several pages (like this kit) are emitted as one shared chunk — so sharing here
is also how the frontend stays light. Import from page code with a relative path
(`../../../ui/island/csrf.js` from a page folder, one level more from `components/`).

Do not force-unify genuinely different UI into the kit (the dashboard's provider tabs vs
the product sync page's provider select, numbered vs cursor pagination). The kit is for
contract helpers (csrf, realtime, links) and identical visual blocks (banners, empty
states).

## Building

Once per bench:

```sh
yarn install --cwd apps/frappe/ui/vite/island/toolchain
bench build
```

`bench migrate` registers new Page docs and workspace links.
