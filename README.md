## Ecommerce Core

Shared foundation for standalone ERPNext ecommerce integration apps.

Provides the common building blocks each integration (Unicommerce, Shopify, Amazon, ...) depends on:

- **DocTypes:** `Ecommerce Item` (product↔integration mapping), `Ecommerce Integration Log` (sync log + retry).
- **controllers/** — `SettingController` base class, inventory sync helpers, scheduling helper.
- **utils/** — dummy tax-template / price-list guards, test bootstrap, naming series.
- Common client JS for Sales Order / Sales Invoice.

Install this first, then install any integration app on top of it:

```bash
bench --site <site> install-app ecommerce_core
bench --site <site> install-app unicommerce
```
