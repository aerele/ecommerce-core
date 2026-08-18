# E-Commerce Connector Agent Specification

## Purpose

This document tells an AI coding agent how to build, extend, or maintain e-commerce connectors on top of the Ecommerce Core framework (Frappe v16 / ERPNext v16).

The person using this agent may be a first-time developer with little or no prior knowledge of ERPNext, Ecommerce Core, or the target provider. The agent's job is not just to write correct code — it is to **research thoroughly, explain clearly, propose a plan, and only build after the user approves it.**

Read this whole file before doing anything else.

---

## Core Rules (apply at every step)

1. **Research before recommending.** Never guess how a provider, ERPNext, or Ecommerce Core behaves. Look it up.
2. **Explain like the user is new to this.** Avoid assuming the user knows Frappe/ERPNext/provider jargon. When you introduce a concept (webhooks, OAuth, warehouses, idempotency, etc.), give a one-line plain-language explanation before using it in a recommendation.
3. **Recommend, don't just list.** When more than one valid approach exists, name the one you recommend and say why, and only then mention the alternatives. If only one approach exists, just say so — don't manufacture false choices.
4. **Look beyond this file.** This document lists required behavior, but it cannot anticipate every provider. If your research shows something is necessary for the connector to actually work end-to-end (a feature, setting, safeguard, or edge case not mentioned here), flag it to the user as a recommended addition to scope — do not silently add it, and do not silently skip it either.
5. **Never build without approval.** Nothing gets implemented — no app scaffolding, no code, no DocTypes — until the user has explicitly approved a final scope. See "Approval Gate" below.
6. **No tests during partial development.** Do not write automated tests while a feature is still being built or scope is still partial. Tests are written only after the full approved scope has been implemented and manually verified — or earlier only if the user explicitly asks for tests at that point.
7. **Keep the plan legible.** Don't overwhelm the user with the entire capability universe at once. Present findings and options in short, scannable form (tables, checklists) rather than long prose walls.

---

## Workflow

### Phase 1 — Understand the request and the repository

- Read what the user is asking for in plain terms.
- Inspect the repository: installed `frappe`, `erpnext`, and `ecommerce_core` versions and whether they're compatible with this spec; existing connector apps; whether the requested connector already exists; reusable Ecommerce Core controllers/services/DocTypes/utilities; existing project conventions.
- If a connector for this provider already exists, tell the user and ask whether to extend it or create a new one — don't assume.
- Confirm the two-site setup required for this project — see "Site Policy" below — before any implementation work begins.

### Phase 2 — Research the provider

Before proposing anything, study the provider's **official** documentation and determine, for each of: authentication, SDK availability, REST/GraphQL APIs, webhooks, polling, pagination, rate limits, products/variants, inventory, warehouses/locations, customers, orders, payments, fulfillment, refunds, returns, taxes, discounts, shipping, idempotency support, retry guidance, deprecated/legacy/beta APIs, and the provider's own recommended production setup.

Do not assume one provider behaves like another you've seen before. Every provider is researched independently, from its own docs.

### Phase 3 — Gap analysis (beyond this file)

Compare three things:

- what this AGENTS.md describes as available capabilities,
- what the provider actually supports (from Phase 2), and
- what your research shows is genuinely needed for a working, user-friendly connector end-to-end for this provider (even if it isn't explicitly listed in this file — e.g. a provider-specific safeguard, a settings field, a reconciliation step, a required mapping).

Anything in that third category is a **proposed addition**, not a silent decision. It goes into the scope proposal in Phase 4, clearly marked as "not in AGENTS.md, recommended because...".

### Phase 4 — Present the scope and get approval (hard gate)

Present a single, clear, beginner-friendly summary containing:

- **What this connector will do**, in plain language.
- **Capability table** — for each capability: provider support (yes/no/partial), whether it's in AGENTS.md, your recommendation (include/exclude), and why.
- **Additions beyond AGENTS.md** (if any) — clearly labeled, with your reasoning, and why the connector wouldn't work well without them.
- **Where multiple valid implementations exist** (e.g. REST vs GraphQL, webhooks vs polling, OAuth vs API key) — your recommended option first, alternatives only if they're genuinely valid, one or two lines of trade-off each. Skip this entirely for capabilities with only one valid approach.
- **Which site is which** — confirm the developer site and the testing site per "Site Policy" below (existing sites to reuse, or new ones to create).
- **Open questions only you can't answer from research** — business/customer-specific decisions (company, warehouse mapping, price list, customer group, etc.). Ask only what genuinely can't be determined from AGENTS.md, Ecommerce Core, the provider docs, or the repo.
- **A final scope checklist** (✔ included / ✖ excluded) covering both AGENTS.md capabilities and any proposed additions, with the selected workflow for each included capability.
- End with a direct approval question: *"Does this scope look right to you? Reply to approve, or tell me what to change."*

**The agent must not write any code, scaffold any app, or run any implementation commands until the user replies with approval of this scope.** If the user changes something, restate the updated final scope before proceeding.

If the user later asks for something new mid-project, treat it as a new mini version of this same phase (research → propose → approve) rather than silently expanding scope.

### Phase 5 — Implement the approved scope

Build only what was approved. For unsupported or intentionally excluded capabilities, don't write placeholder/stub code — document why they're excluded in the README instead.

Reuse Ecommerce Core wherever it already provides the functionality (see "Ecommerce Core Contracts" below); provider-specific logic stays inside the connector app.

`ecommerce_core` itself is read-only. If the approved scope truly cannot be built without changing it, stop, explain the limitation and the exact change needed, and get explicit user approval before touching it — this is a separate decision from the scope approval in Phase 4.

### Phase 6 — Manual verification

Before writing any automated tests:

- Install the app on the **testing site** (never the developer site — see "Site Policy" below) and run `bench --site <testing-site> migrate`.
- Manually exercise the implemented flows (using sandbox/test credentials where possible) and confirm behavior matches the approved scope.
- Fix anything broken back on the developer site, then re-deploy to the testing site and re-verify.

### Phase 7 — Automated tests (only now, or on request)

Write automated tests only once the full approved scope has been implemented and manually verified, or immediately if the user explicitly asks for tests before that point. Cover the capabilities actually in scope; skip tests for anything excluded from scope (document the reason instead — see "Testing Requirements" below for what "done" looks like).

### Phase 8 — Deliver

Give the user a plain-language summary: what was built, the final capability matrix (included / excluded / why), key implementation decisions, any manual setup they still need to do (credentials, webhook registration, etc.), and what was tested.

---

## When to ask vs. decide independently

Decide independently — without asking — whenever the answer is determinable from: this AGENTS.md, Ecommerce Core, the provider's official docs, or the existing repository. Don't ask the user things you can look up.

Stop and ask only when:
- multiple valid approaches remain even after research, and none is clearly preferred by the sources above (present it in the Phase 4 scope proposal, not as a random mid-build interruption);
- a decision is customer/business-specific (Company, Warehouse mapping, Price List, Customer Group, target site, etc.);
- the official docs simply don't define the needed behavior;
- the work would require changing Ecommerce Core or ERPNext core behavior.

---

## Application Naming Policy

- Provider has an official SDK you'll use → `<provider>_connector` (e.g. `shopify_connector`).
- No SDK, direct API calls → use the provider name itself (e.g. `shopline`, `zohocommerce`).

Determine SDK availability during Phase 2 research before finalizing the name.

---

## Site Policy

Every connector project uses **two separate Frappe sites** — never build and verify on the same one:

- **Developer site** — where the agent actively works: scaffolding the app (`bench new-app`), writing and editing code, running frequent `bench --site <dev-site> migrate` cycles, and iterating during Phase 5 (Implementation). This site is expected to be reset, broken, and rebuilt repeatedly while development is in progress — that's normal and fine.
- **Testing site** — a separate site used only for Phase 6 (Manual verification) and Phase 7 (Automated tests). It should be as close to a clean, realistic environment as possible, ideally connected to the provider's sandbox/test credentials rather than production ones. Nothing half-finished from the developer site should ever be installed here — only code that's considered ready to verify.

**Why two sites:** verifying against the same site you're actively coding on makes it easy to mistake "the code I'm mid-edit on happens to work" for "the connector actually works." A separate testing site catches migration issues, install/uninstall problems, and config that only exists by accident on the dev site.

**What the agent must do:**

1. During Phase 1, ask the user to identify both sites — for each one, whether it already exists (site name) or needs to be created fresh (`bench new-site`). Don't assume the user has both set up already; a first-time developer may only have one site running.
2. Record which site is which in the Phase 4 scope summary, so the user can confirm before anything is installed.
3. Do all Phase 5 implementation work — app creation, code changes, dev-cycle migrations — only on the developer site.
4. Do all Phase 6 manual verification and Phase 7 automated test runs only on the testing site. If something fails there, fix it on the developer site and re-deploy to testing rather than patching the testing site directly.
5. If the user only has one site available and doesn't want to create a second, tell them plainly what they're trading off (verification results may be unreliable, and a broken dev-cycle change could look like a verified feature) and get their explicit confirmation before proceeding with just one site.

---

## Compatibility

```toml
[tool.bench.frappe-dependencies]
frappe = ">=16.0.0-dev,<=17.0.0-dev"
erpnext = ">=16.0.0-dev,<=17.0.0-dev"
```

---

## Reuse Policy

- Framework-level functionality belongs in Ecommerce Core; provider-specific logic belongs in the connector app.
- Don't duplicate reusable controllers, utilities, mappings, logging, scheduling, or inventory handling.
- Don't add provider-specific modules to ERPNext or Ecommerce Core.

## Ecommerce Core Modification Policy

`ecommerce_core` is shared by multiple connectors and is treated as read-only unless the user explicitly approves a change to it.

Never add provider-specific logic to it, change its behavior for one provider's sake, or patch it "temporarily" to make something work locally.

If the approved scope genuinely can't be implemented without an Ecommerce Core change: stop, explain the limitation, describe the exact change needed, note that it should ship as its own Ecommerce Core change (a local-only edit won't reach production or other environments), and wait for explicit approval before touching it.

---

## Authoritative References (priority order)

1. Explicit decisions the user has approved for this project.
2. This AGENTS.md.
3. Ecommerce Core.
4. The provider's official documentation.
5. Official Frappe documentation.
6. Official ERPNext documentation.
7. Mature open-source ERPNext connector repos — architecture/testing-pattern reference only, never a source of provider-specific business logic; prefer the upstream repo.

If sources conflict: resolve using this priority order for technical questions; user decisions win for customer-specific business behavior. If the user's request conflicts with the provider's API or with Frappe/ERPNext constraints, explain the conflict, recommend the compliant approach, and wait for confirmation before proceeding.

---

## Required Standalone App Layout

Baseline structure — adapt only when the provider, approved scope, or existing project requires it. Omit modules for capabilities that are unsupported or excluded from scope; don't include them as placeholders.

```plaintext
apps/<provider_connector>/
├── .github/workflows/
│   ├── ci.yml
│   └── linters.yml
├── .gitignore
├── .pre-commit-config.yaml
├── README.md
├── license.txt
├── pyproject.toml
└── <provider_connector>/
    ├── __init__.py
    ├── hooks.py
    ├── install.py
    ├── uninstall.py
    ├── modules.txt
    ├── patches.txt
    ├── config/
    │   ├── __init__.py
    │   └── desktop.py
    ├── page/
    │   └── <provider>_sync_products/
    │       ├── __init__.py
    │       ├── <provider>_sync_products.py
    │       ├── <provider>_sync_products.js
    │       └── <provider>_sync_products.json
    ├── public/
    │   ├── images/<provider>.svg
    │   └── js/<provider>/
    │       ├── item.js
    │       ├── sales_order.js
    │       └── sales_invoice.js
    └── <provider_connector>/
        ├── __init__.py
        ├── api_client.py
        ├── constants.py
        ├── customer.py
        ├── order.py
        ├── product.py
        ├── inventory.py
        ├── payment.py
        ├── fulfillment.py
        ├── refund.py
        ├── webhook.py
        ├── utils.py
        ├── doctype/
        │   ├── <provider>_settings/
        │   │   ├── <provider>_settings.json
        │   │   ├── <provider>_settings.py
        │   │   ├── <provider>_settings.js
        │   │   └── test_<provider>_settings.py
        │   └── <provider>_warehouse_mapping/
        │       ├── <provider>_warehouse_mapping.json
        │       └── <provider>_warehouse_mapping.py
        ├── tests/
        │   ├── __init__.py
        │   ├── utils.py
        │   ├── test_client.py
        │   ├── test_product.py
        │   ├── test_order.py
        │   ├── test_inventory.py
        │   ├── test_payment.py
        │   ├── test_fulfillment.py
        │   ├── test_webhook.py
        │   └── fixtures/*.json
        └── workspace/<provider>/<provider>.json
```

Provider-specific operational DocTypes (Channel, Webhook Registration, Shipping Method, Tax Account Mapping, etc.) are fine when they represent real configuration or traceability — don't duplicate shared Ecommerce Core DocTypes.

Keep provider transport code in `api_client.py`, provider→ERPNext transformation in domain modules, and Frappe persistence/orchestration at explicit service boundaries. Don't scatter raw HTTP calls through DocType controllers.

---

## Frappe Conventions

**Python** — tabs, double quotes, 110-char line limit, type hints, Ruff config consistent with the project. Use `frappe._()` for user-facing text. Use the ORM/Query Builder, never string-interpolated SQL. Use `frappe.get_cached_doc` for stable settings reads, `frappe.get_doc` when you need current mutable state. Use constants for DocType names, Module Def name, custom fieldnames, provider statuses, queue names, and API limits. Keep whitelisted functions small; validate types/permissions/ownership before enqueueing. Don't use `ignore_permissions` unless there's a documented reason and no alternative. Use `frappe.set_user()` only for background/scheduler contexts that need a specific permission context, always restoring the original user in `finally`. Don't manually commit/rollback without a documented reason. Don't swallow exceptions — convert expected provider failures to typed exceptions/explicit results, log unexpected ones with context. Never log secrets, tokens, cookies, auth headers, payment credentials, or full personal data.

**DocTypes** — every directory has `__init__.py`, schema JSON, controller, optional form JS, tests. Child tables set `istable: 1`. Settings is a Single DocType. Use System Manager permission for connector config/logs; operational actions also enforce the target ERPNext DocType's permissions. Secrets use Password fields, read via `get_password()`. All generated custom fields are created by one idempotent setup function called from both `after_install` and `after_migrate`, with deterministic provider-slug-prefixed fieldnames. External IDs are read-only, searchable, and unique where the provider guarantees global uniqueness (otherwise paired with store/account identity). Never edit ERPNext core files — use custom fields, `doc_events`, provider DocTypes, and client scripts. Uninstall removes only connector-owned customizations, checking links and preserving business documents.

**JavaScript** — use `frappe.ui.form.on`, `frappe.call`, `frm.call`, `__()`, supported Desk APIs. Keep accounting/sync logic server-side. Show buttons only when settings/state/permissions/provider IDs make the action valid. Freeze long actions, show translated feedback, enqueue bulk work instead of blocking a request. Reuse Ecommerce Core's shared transaction scripts; add only provider-specific UI behavior.

---

## Ecommerce Core Contracts

### Settings inheritance

There is no `EcommerceBaseConnector` class — don't invent or import one. Inherit `SettingController`:

```python
from ecommerce_core.controllers.setting import (
    ERPNextWarehouse,
    IntegrationWarehouse,
    SettingController,
)


class ProviderSettings(SettingController):
    def is_enabled(self) -> bool: ...
    def get_erpnext_warehouses(self) -> list[ERPNextWarehouse]: ...
    def get_erpnext_to_integration_wh_mapping(
        self,
    ) -> dict[ERPNextWarehouse, IntegrationWarehouse]: ...
    def get_integration_to_erpnext_wh_mapping(
        self,
    ) -> dict[IntegrationWarehouse, ERPNextWarehouse]: ...
```

Warehouse mappings must be non-empty when inventory/fulfillment sync is enabled; validate duplicates and provider requirements. Prefer one-to-one mappings; model and test many-to-one/group warehouses explicitly if the provider supports them.

### Ecommerce Item

The authoritative mapping between ERPNext Items and provider products/variants. Key fields: `integration`, `erpnext_item_code`, `integration_item_code`, `sku`, `has_variants`/`variant_id`/`variant_of`, `inventory_synced_on`, `item_synced_on`. Use helpers from `ecommerce_core.ecommerce_core.doctype.ecommerce_item.ecommerce_item` (`is_synced`, `get_erpnext_item_code`, `create_ecommerce_item`).

Determine the provider's canonical product identity from its official docs — never assume SKU is mandatory or unique:

- SKU mandatory and unique per the provider → may be used as the deterministic matching key.
- SKU optional/duplicated/not guaranteed unique → use the provider's canonical ID (Product ID / Variant ID) as `integration_item_code`, and never rely on SKU alone.
- Never match by name, title, description, or fuzzy logic.

When no deterministic matching rule exists, create a new ERPNext Item and its `Ecommerce Item` mapping transactionally, keyed by the provider's canonical identifier. For variant products, map the template and every sellable variant, preserving Product ID, Variant ID, SKU (if present), option attributes, and the template/variant relationship. Inventory sync always targets the mapped sellable variant/inventory item, never only the template.

### Inventory helpers

```python
from ecommerce_core.controllers.inventory import (
    get_inventory_levels,
    get_inventory_levels_of_group_warehouse,
    update_inventory_sync_status,
)
from ecommerce_core.controllers.scheduling import need_to_run
```

`get_inventory_levels` selects mappings whose Bin changed after `inventory_synced_on`; use the group-warehouse helper for mapped group warehouses. Advance `inventory_synced_on` only after the provider confirms success for that Ecommerce Item across all attempted mapped locations — never advance for failed/unattempted records.

### Integration log bindings

Use Ecommerce Integration Log; don't create a second sync-log DocType.

```python
from ecommerce_core.utils.integration_log import (
    integration_log_wrapper,
    make_scheduler_error_logger,
    run_integration_job,
)

create_provider_log = integration_log_wrapper(MODULE_NAME)
log_scheduler_errors = make_scheduler_error_logger(MODULE_NAME)
```

Use `run_integration_job` (or the equivalent shared request-ID context) for retryable operations, storing a fully-qualified retryable method and sanitized `request_data`. Statuses: Queued, Success, Partial Success, Failure, Error, with summary counts/identifiers. Because retry re-enqueues the recorded method, retryable entrypoints must accept `payload`/`request_id`, be idempotent, and clear `frappe.flags.request_id` in `finally`.

---

## Settings and Configuration

`<Provider> Settings` (Single DocType) includes capability-appropriate fields from this baseline, per the approved scope: enable connector; provider store/account/base URL and API version; auth config and encrypted secrets; read-only connection/token-expiry state; catalog import/export toggle and defaults (e.g. Item Group); order sync toggle/interval/last-sync/overlap window/Customer Group/Company/Price List/naming series; inventory sync toggle/interval/last-sync/quantity policy/warehouse mapping table; payment account/mode mapping and invoice/payment toggles; fulfillment/shipping/return settings; webhook secret/callback URL/registration state/event subscriptions/last sync, when supported.

Possible credential fields depending on the provider's auth scheme: Base URL, Store URL, Account ID, API Key, API Secret, Access Token, Refresh Token, OAuth Client ID/Secret, Webhook Secret, Store/Organization Identifier. Sensitive values use Password fields, read only via `get_password()`.

Validate the provider connection automatically whenever the connector is enabled/re-enabled; if validation fails, the settings can't be enabled and the error is shown to the user.

Disabling the connector must never clear, reset, regenerate, or otherwise modify stored credentials, identifiers, secrets, URLs, mappings, or tokens — some providers only expose secrets once. Provide permission-checked buttons for explicit actions (refresh provider locations, reconcile webhooks, force-sync), never bulk sync inside settings validation.

Keep the form compact and task-oriented. For connectors with broad scope, prefer domain tabs (Details, Inbound Webhooks, Products, Inventory, Customers, Orders) with clearly labeled Section Breaks, balanced Column Breaks, and `depends_on` for progressive visibility. Place actions next to the config they affect (e.g. Test Connection in Connection, webhook reconciliation in Inbound Webhooks) — avoid duplicating an action in both a section and the toolbar.

When channels/locations/product types/currencies etc. are discoverable via the provider API, provide one consolidated fetch action that pulls them all, populates provider-owned fields as read-only, and preserves existing ERPNext-side mappings by stable provider ID/slug — only split into multiple fetch actions when they genuinely differ in permissions, latency, failure domain, or intent.

`validate()` normalizes the base URL, validates dependent settings, verifies one-to-one constraints where required, initializes watermarks safely, and validates the provider connection when enabling. Disabling stops scheduled jobs and unregisters connector-owned webhooks where supported, but never touches mappings, business records, or stored configuration.

---

## UI and UX Standards

Group related functionality into tabs/sections rather than one crowded page. Insert custom fields with the correct `insert_after` so they land in the right place on existing ERPNext forms. Use meaningful labels/descriptions/field types. Reuse existing ERPNext/Ecommerce Core UI patterns for consistency. Before calling anything done, check that pages, tabs, fields, and actions are positioned intuitively enough that a new user could find them without extra guidance.

---

## HTTP Client and Authentication

All outbound calls go through one provider client abstraction, implementing the provider's officially documented, production-recommended integration mechanism (auth method, REST/GraphQL/SDK, OAuth flow, versioning, webhook registration, pagination, rate limits, idempotency support). Never invent auth flows or undocumented APIs. Prefer the provider's recommended auth method; if the user wants a different officially-supported one, use that; if their request conflicts with provider docs, explain the difference and recommend the documented approach before proceeding.

The client must: normalize/allowlist the configured HTTPS origin and reject embedded credentials/unsafe schemes; use explicit connect/read timeouts with TLS verification; add required version/content headers; serialize/parse payloads in one place; support pagination fully (no silent truncation); expose typed provider operations rather than leaking generic requests into business modules; convert malformed JSON, GraphQL top-level errors, HTTP errors, and provider `successful:false` responses into explicit failures; redact secrets/tokens/cookies from logs; allow test injection of base URL/credentials/session/clock without bypassing production validation.

API keys: Password fields, sent only in the provider-documented header. OAuth: authorization/callback with state validation when interactive, encrypted token storage, refresh before expiry, on 401 refresh once then replay only a replay-safe request, coordinate refreshes to avoid concurrent invalidation.

Rate limiting: honor `Retry-After` and documented throttle metadata; bounded exponential backoff with jitter for 429/transient 5xx/network failures; never retry validation/auth failures; retry writes only with documented idempotency or a stable idempotency key whose result can be reconciled; never retry a streamed upload after its body is consumed.

---

## Product and SKU Workflow

**Identity** — see "Ecommerce Item" above for the canonical-identity rule; never fuzzy-match.

**Provider → ERPNext** — fetch the complete product/variant set, following pagination. Validate the canonical identifier per the provider's docs; reuse an existing `Ecommerce Item` mapping if present; otherwise create the ERPNext Item(s) and mapping. Create only the master data the provider actually supplies or ERPNext requires — never invent placeholder values for missing data (e.g. don't assume region-specific fields like HSN/SAC exist unless supplied or user-configured). Create/update the `Ecommerce Item` mapping only after the ERPNext Item is successfully saved. Log success/failure without exposing the full catalog.

**ERPNext → Provider** — configurable. Automatic sync fires only when ERPNext→Provider sync is enabled in Settings **and** the Item's export checkbox is enabled **and** the item passes provider validation (see Item Export Control below). Build payloads with a dedicated mapper; decide create-vs-update via the existing mapping, not name matching; update `item_synced_on` only after provider confirmation; handle validation errors per-product/variant, never marking failures as synced. Guard against sync loops — imported changes must never trigger another outbound sync for the same operation (use scoped flags/origin metadata, test it). Manual sync from the Product Synchronization page may sync any selected Item regardless of the auto-sync checkbox.

### Item Export Control

Two levels of control, both required together for automatic ERPNext→Provider sync:

- **Global** — a toggle in `<Provider> Settings`. Off = no automatic sync of any kind (scheduled or on-save), manual sync from the Product Synchronization page still works.
- **Per-item** — a provider-specific checkbox on the ERPNext Item. It only makes an item *eligible*; it does nothing unless the global toggle is also on.

Automatic sync requires all three: global toggle on, item checkbox on, and the item passes provider validation (log/error if it fails validation).

### Product Synchronization Page

When Products are in scope, provide a dedicated Desk page/Workspace (entirely within the connector app, no `ecommerce_core` changes) supporting: list/search/filter provider products, view sync status, sync one / selected / all products, show progress, show and retry failures. Manual sync is independent of the auto-sync setting and export checkbox unless the user asks for extra restrictions.

---

## Order Workflow

Webhook and polling ingestion both call the same idempotent order service.

**Inbound sequence:** validate store/event/payload → extract the stable provider order ID and look it up on the indexed custom field on Sales Order → if found, reconcile and return the existing order (never duplicate) → if the webhook is a summary, fetch the full order → reject/quarantine orders from disabled or unmapped channels/stores/currencies/locations per settings → ensure every line has a valid Ecommerce Item mapping (import the exact missing SKU if configured to, otherwise fail the whole order atomically with actionable logging) → create/reuse Customer and Address by stable provider ID first, then documented email/address keys, mapping country/state via Ecommerce Core helpers, without destructively overwriting unrelated master data → resolve Company, Price List, currency/exchange rate, warehouse, taxes, shipping/discount lines, Customer Group, naming series, dates → build the Sales Order preserving provider totals/rounding without double-applying discounts or taxes → save/submit per settings → reconcile invoices/payments/fulfillment per the rules below, when in scope → mark the integration log successful only after commit.

**Currency:** when the order currency differs from the company currency, keep the order currency as the transaction currency and resolve a positive dated exchange rate via ERPNext's standard service; set `conversion_rate` transaction→company and `price_list_currency`/`plc_conversion_rate` independently from the Price List currency. Never hardcode `1`, never just check that a Currency Exchange record exists without using its rate, never convert line amounts twice. If no positive rate resolves, fail the order atomically with an actionable error. Downstream invoices/payments/refunds inherit the same currency semantics.

**Polling:** overlap window larger than the schedule interval, fetch by updated-since watermark, follow all pages, rely on idempotency to tolerate overlap; don't advance a global watermark past failed pages without a recoverable cursor/range.

**Updates are reconciliation, not replacement.** Submitted documents change only through supported amendment/cancellation/return flows — never `db_set` on ledger-impacting submitted fields.

**Financial data:** taxes, discounts, promotions, shipping, duties, fees, gift cards, inclusive/exclusive tax handling, and rounding follow the provider's documented calculation rules exactly — preserve provider totals, never double-apply, never flip inclusive/exclusive semantics, never introduce undocumented rounding drift. Cover edge cases with tests once you reach the testing phase.

### Historical Order Sync ("Sync Old Orders")

A manual action to import/reconcile orders from before the connector existed or before auto-sync was on: pick a date range → fetch candidate orders (following pagination) → run every order through the same idempotent order service used by webhooks/polling → identify existing ERPNext documents by provider order ID (safe to re-run) → fully reconcile each order's *current* state (Sales Order, Invoice, Payment Entry, Delivery Note, cancellation, refund, return — whatever's in scope), not just create missing Sales Orders → run as a background job with an Ecommerce Integration Log for progress/retry → report processed/created/updated/skipped/failed counts.

---

## Inventory Workflow

**Source of truth:** ERPNext, for inventory, stock, warehouses, accounting, GL, sales/purchase documents — unless the provider explicitly requires otherwise and the README documents the exception. Never fabricate accounting values or stock movements.

**Settings (when in scope):** enable toggle, sync frequency (minutes), last-successful timestamp, warehouse/location mapping, permission-checked refresh-locations and manual-sync actions. The scheduler can run on a fixed short interval, but actual sync frequency is gated by `need_to_run()` against the configured interval. Manual sync uses `force=True` to bypass only the interval check — enablement/security checks still apply.

**Sync rules:** exit early if disabled; respect `need_to_run()` unless forced; validate all enabled warehouse↔location mappings before syncing; fetch changed inventory via the Ecommerce Core helpers; determine synced quantity per the provider's documented semantics (don't assume `actual_qty` is always right — some providers need `actual_qty - reserved_qty`); batch by provider location per documented limits; send absolute quantities where supported, not deltas; evaluate each item/location's result independently (a 200 response doesn't mean every line succeeded); advance `inventory_synced_on` only for items that actually succeeded; log a summary (processed/succeeded/failed/skipped/errored); prevent overlapping sync jobs with a lock or unique job ID.

---

## Payment and Invoice Workflow

Document the provider→ERPNext payment state mapping in code and README. Keep provider payment status in provider-specific custom fields — don't overload `docstatus`. All payment sync is idempotent; reprocessing an event never duplicates documents.

**Sales Invoice** — created only when invoice creation is enabled, the provider has reached the configured invoice state, and the financial data is finalized. Build it from the Sales Order via ERPNext's standard mapping, preserving quantities/taxes/discounts/shipping/rounding; validate currency/company/warehouse/accounts; dedupe by provider invoice ID (or order ID + invoice ID); reconcile rather than duplicate.

**Payment Entry** — created only when enabled and the provider reports captured/settled payment, using configured Company/Mode of Payment/Account mappings, deduped by provider transaction ID, supporting partial payments without exceeding the invoice total. Never create one for pending, authorized-only, failed, cancelled, or voided payments. COD orders wait for the configured "payment collected" event.

**Refunds (when in scope and supported)** — create a Return Sales Invoice (Credit Note), a Refund Payment Entry when applicable, process once per refund ID+amount, validate currency/allocation/account/rounding. Never fabricate accounting data to force a submission; partial payments/refunds reconcile cumulatively without exceeding totals.

**Manual sync actions** for every in-scope payment capability: sync payment status, sync invoice status, sync historical payment updates.

**Historical sync** reconciles the full financial lifecycle (invoices, payment entries, refunds, payment status) for the in-scope capabilities, not just the initial order.

---

## Fulfillment, Cancellation, and Returns

Document the provider→ERPNext fulfillment mapping in code and README. Idempotent — reprocessing never duplicates.

**Fulfillment** — Delivery Notes created only from submitted Sales Orders, only for fulfilled quantities, never over-delivering; supports multiple/partial fulfillments; deduped by shipment/fulfillment ID; maps provider location to the configured ERPNext Warehouse before any stock transaction. Preserve shipment ID, package ID, fulfillment ID, tracking number, carrier, tracking URL, warehouse, status. Stock documents submit/cancel only per ERPNext lifecycle rules.

**Cancellation** — reconciles Sales Orders/Invoices/Delivery Notes/Payment Entries per ERPNext lifecycle rules when permitted. If submitted downstream documents block automatic cancellation, log a reconciliation action instead of forcing a change. Partial line cancellations go through amendment/closure flows, never a direct quantity edit on a submitted document.

**Returns (when in scope and supported)** — Return Delivery Notes, Return Sales Invoices/Credit Notes where applicable, refunds via the payment workflow, deduped by return/refund ID, supports partial returns.

**Manual sync actions** for every in-scope fulfillment capability: sync fulfillment status, sync tracking, sync cancellations, sync returns.

**Historical sync** reconciles the full fulfillment lifecycle (Delivery Notes, tracking, status, cancellations, returns) for in-scope capabilities against current provider state.

---

## Webhooks

Use webhooks when the provider supports the needed event reliably and Webhooks are in scope. Register only connector-owned subscriptions; reconcile on setup, settings changes, and migration where safe.

Narrow whitelisted receiver:

```python
@frappe.whitelist(allow_guest=True)
def receive():
    ...
```

`allow_guest=True` is fine here only because signature auth replaces session auth. The receiver must: accept POST only with a body-size limit; read raw bytes before any JSON normalization; get the secret via `get_password()` and reject missing settings/disabled integration/missing signature/unknown store; compute the provider-documented HMAC/signature over the exact required bytes and compare with `hmac.compare_digest`; validate the signed timestamp and reject stale events where supported; extract a stable event ID and dedupe atomically (or use a bounded hash-based replay key of store+topic+object ID+raw body if there's no event ID); validate the topic against an allowlist — never import/execute a dotted method from the request; write a sanitized Queued log and enqueue the handler with `enqueue_after_commit=True`; return fast 2xx for accepted/already-processed events, 4xx for invalid auth/schema without enqueueing.

Never put secrets in callback URLs, never trust a signature computed after JSON reserialization, never do full sync work inline in the web worker. Test exact valid/invalid/missing/malformed/stale/duplicate/cross-store signatures once you reach the testing phase.

---

## Hooks and Background Jobs

`hooks.py` contains only real, importable dotted paths — no unused scaffolding. Baseline:

```python
required_apps = ["erpnext", "ecommerce_core"]

after_install = "<provider_connector>.install.after_install"
after_migrate = "<provider_connector>.install.after_migrate"
before_uninstall = "<provider_connector>.uninstall.before_uninstall"

before_tests = "ecommerce_core.utils.before_test.before_tests"

scheduler_events = {
    "hourly_long": [
        "<provider_connector>.<provider_connector>.product.sync_products",
        "<provider_connector>.<provider_connector>.order.reconcile_order_statuses",
    ],
    "cron": {
        "*/5 * * * *": [
            "<provider_connector>.<provider_connector>.order.sync_orders",
            "<provider_connector>.<provider_connector>.inventory.sync_inventory",
        ]
    },
}
```

Adapt entries to the approved capability matrix — omit anything out of scope. Use a frequent cron dispatcher plus `need_to_run` for admin-configurable intervals. `short` queue for small bounded actions, `long` for catalog/historical/bulk/reconciliation jobs. Realistic timeouts, stable job names, no duplicate concurrent jobs. `enqueue_after_commit=True` for work depending on the current transaction. Scheduler entrypoints accept injectable clients and `force=False`, exit cleanly when disabled, use the shared scheduler error logger, paginate/batch, and are independently retryable. Run site migration after changing scheduler hooks.

Use `doc_events` only for provider-specific behavior, keep handlers lightweight, enqueue outbound calls after commit, check `has_value_changed`/document state to avoid unnecessary calls or recursion.

---

## Whitelisted Administrative APIs

`frappe.only_for("System Manager")` for connector-wide sync/config operations; target-DocType permissions for document-level actions (invoice/fulfillment generation, etc.). Validate JSON types and max batch sizes before enqueueing. Map user-facing action names through a fixed server-side dictionary — never accept arbitrary dotted method paths from the client. Run small bounded work synchronously; queue bulk work and return a log/job ID. Never return credentials, unredacted provider responses, or internal tracebacks.

---

## Testing Requirements

**When to write tests:** only after the full approved scope is implemented and manually verified (Phase 6), or immediately if the user explicitly asks for tests earlier. Don't write tests against half-built features.

Use Frappe `IntegrationTestCase`, `unittest.mock`, and `responses` (or the provider SDK's transport mock). Build sanitized, committed fixtures from the provider's actual API/webhook documentation.

Cover every in-scope capability; capabilities that are unsupported or excluded don't need tests — document why in the README instead.

Suite coverage, where the capability is in scope:

- **Settings/install** — idempotent install and repeated `after_migrate`; custom fields/workspace/mappings load correctly; enabling requires credentials+mappings; secrets retrievable but never logged; connection test and OAuth refresh success/failure; disabling stops scheduling and handles webhook deregistration safely.
- **Client** — auth headers/API version/payloads; multi-page pagination; timeouts/malformed JSON/GraphQL errors/provider-declared failures; single 401-refresh-and-replay; 429 Retry-After, transient retry, retry exhaustion, non-retryable 4xx; idempotency headers on writes; log redaction.
- **Product identity** — no-SKU provider; duplicated/missing SKU; Product-ID-based and Variant-ID-based matching.
- **Products/inventory** — simple and variant imports; deterministic matching vs ambiguous-SKU rejection; mapping creation and repeat-sync idempotency; export loop prevention; per-variant partial failure; leaf and group warehouse behavior; quantity semantics/batches/multi-location/partial responses; watermark advances only on success.
- **Financial mapping** — inclusive/exclusive/multi-line taxes; product/order discounts; shipping; promotions; gift cards; partial refunds; rounding.
- **Product Synchronization page** — single/bulk/sync-all; failed retry; opt-in export.
- **Orders/accounting** — realistic fixture-based creation; duplicate webhook/poll replay returns the same order; missing-SKU import and atomic failure; customer/address reuse and channel/company/warehouse/currency/tax mapping; repeated lines, discounts, shipping, rounding, cancelled lines; full/partial cancellation; paid/pending/failed/COD/partial/refund/duplicate payment events; invoice/payment/return documents balance and reference correctly.
- **Fulfillment/webhooks** — partial and multiple fulfillments without over-delivery; tracking updates, cancellation, return, return-to-origin; valid signature accepted, invalid/missing/stale/malformed/wrong-store rejected; duplicate events acknowledged but not re-enqueued; receiver queues work rather than executing inline.
- **Jobs/logs** — disabled/interval gating are no-ops; `force=True` bypasses only the interval, never enablement/security; correct queue/timeout/`enqueue_after_commit` args; queued/success/partial/error logs carry retryable methods and sanitized payloads; retrying a log is idempotent.

Tests restore settings/defaults/users/created records, don't depend on order, use no real credentials or live network, and rely on Frappe's transaction isolation (explicit commits only where a tested background boundary genuinely requires them).

---

## Logging and Observability

One Ecommerce Integration Log per logical inbound event, manual bulk request, scheduled batch, or retry, correlated by request ID. Record: provider/store and operation; provider object/event IDs; start/end state and attempted/succeeded/failed/skipped counts; retryable method and sanitized payload; concise provider errors, plus traceback for unexpected failures.

Never log auth material or unnecessary personal/order payloads — redact recursively by key (authorization, token, secret, password, cookie, card, signature, and variants). Store only the minimum normalized data needed for retry.

Use `frappe.logger("<provider_connector>")` for diagnostic runtime messages and Ecommerce Integration Log for operator-visible business execution — don't rely on filesystem logs alone.

---

## Acceptance Criteria (before calling it done)

- Standalone Frappe v16 app depending on `erpnext` and `ecommerce_core`; Settings inherits `SettingController` with every required method implemented.
- Every capability in the approved scope (AGENTS.md-listed or user-approved addition) is implemented; unsupported/excluded capabilities are documented, not stubbed.
- Every user-approved business decision is implemented — no in-scope workflow left as a stub.
- Products/SKUs, orders, inventory, payments, fulfillment, cancellation/refunds/returns, webhooks/polling follow this document's contracts for everything in scope.
- Inbound sync never triggers unintended outbound sync; retries never duplicate documents.
- ERPNext accounting/inventory stay consistent; ERPNext remains the source of truth per the Inventory Workflow section.
- Secrets, endpoints, and webhook handling follow the security rules above.
- Ecommerce Item and Ecommerce Integration Log are used correctly — no duplicate sync-log DocType.
- Hooks, scheduler jobs, custom fields, install/migrate/uninstall, workspace, and README are complete for the approved scope; install/migrate/uninstall all succeed.
- All mandatory tests plus Ruff/formatting/pre-commit checks pass, covering happy paths, partial failures, security, idempotency, retries, and accounting/stock side effects for everything in scope.
- No unfinished stubs, bare `pass`, placeholder mappings, live-test dependencies, or unexplained TODOs.
- README documents every required configuration step (auth, webhooks, scheduler, warehouse/account mappings) for the approved scope only.
- If Products are in scope: the Product Synchronization page supports manual single/bulk sync, and automatic export respects the Item-level opt-in field.
- Public connector repos were used only as architectural references, never as the source of provider-specific behavior.

If provider credentials aren't available, complete and pass all mocked tests and clearly list the sandbox smoke test that still needs to be run manually — missing credentials never justify incomplete workflows or untested code.