<div align="center">
	<a href="https://github.com/aerele/ecommerce-core">
		<img src="ecommerce_core/public/images/ecommerce-core.png" height="80px" width="80px" alt="Ecommerce Core Logo">
	</a>
	<h2>Ecommerce Core</h2>
	<p align="center">Shared foundation for standalone ERPNext ecommerce integrations</p>

[![CI](https://github.com/aerele/ecommerce-core/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/aerele/ecommerce-core/actions/workflows/ci.yml)
[![Linters](https://github.com/aerele/ecommerce-core/actions/workflows/linters.yml/badge.svg?branch=develop)](https://github.com/aerele/ecommerce-core/actions/workflows/linters.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](license.txt)
</div>

<div align="center">
	<a href="https://github.com/aerele/ecommerce-core">Repository</a>
	-
	<a href="https://github.com/aerele/ecommerce-core/blob/develop/AGENTS.md">Connector Guide</a>
</div>

## Ecommerce Core

Ecommerce Core is the shared foundation on which standalone ERPNext ecommerce connector apps are built. Each connector (Unicommerce, Shopify) is a separate, focused app, and everything they share lives here: product matching between ERPNext and your sales channels, sync records, stock updates, schedules and channel settings.

Install it alongside ERPNext, then install any connector built on top of it to get a working storefront integration for that provider.

### Motivation

All ecommerce integrations for ERPNext previously lived in a single monolithic app, [ecommerce_integrations](https://github.com/frappe/ecommerce_integrations). Adding a new provider meant touching one large codebase, and every integration carried the weight of all the others.

From Frappe/ERPNext v16 onwards, each provider ships as its own connector app, and only the parts every channel needs (product matching, sync records, stock updates, schedules and shared screens) live here. This keeps each connector small and independently improvable, while every integration behaves consistently because it reuses the same core.

### Key Features

- **Ecommerce Item**: Map platform products and variants to ERPNext items, look them up by platform ID, variant or SKU, create a missing item together with its mapping in one step, and keep template and variant links intact across every channel.
- **Ecommerce Integration Log**: Record every sync job with its request data, response and error details, retry failed jobs straight from the log, individually or in bulk, capture scheduler errors per integration, and clear old successful logs automatically.
- **Warehouse Mapping**: Keep each channel's location-to-warehouse mapping in its settings with lookups in both directions, so stock updates and orders always post against the right warehouse.
- **Inventory Sync**: Find exactly the items whose stock changed since the last update, cover plain and group warehouses alike, and keep a per-item record of the last successful sync.
- **Sync Schedules**: Configure how often each channel syncs orders and stock, and change intervals from the channel's settings without adding new server jobs.
- **Customer Sync**: Create or reuse the customer for each channel order, add billing and shipping addresses, save contact details, and file channel customers under your chosen customer group.
- **Address Mapping**: Convert platform country and state codes into ERPNext country and state names, with Indian states covered out of the box, so imported addresses validate cleanly.
- **Tax and Price Guards**: Maintain a reserved ignore tax category and a reserved price list for integration use, stop the ignore tax category from being used in real item tax templates, and automatically discard any price saved into the reserved price list.
- **Amendment Safety**: Warn anyone amending a synced Sales Order or Sales Invoice that taxes will not be recomputed, so amended documents get checked before submission.

<details>
<summary>Under the Hood</summary>

- [**Frappe Framework**](https://github.com/frappe/frappe): A full-stack web application framework written in Python and JavaScript. The framework provides a robust foundation for building web applications, including a database abstraction layer, user authentication, and a REST API.

- [**ERPNext**](https://github.com/frappe/erpnext): The open-source ERP that remains the source of truth for items, stock, accounting and sales documents. Ecommerce Core maps provider data onto ERPNext masters and transactions.

</details>

### Compatibility

| Frappe Version | ERPNext Version | Python Version |
| --------------------- | --------------------- | -------------- |
| Version 16, Develop | Version 16, Develop | 3.10+ |

## Production Setup

### Self Hosting

Install on an existing bench with ERPNext already set up:

```bash
bench get-app https://github.com/aerele/ecommerce-core --branch develop
bench --site <site> install-app ecommerce_core
```

Ecommerce Core requires ERPNext and must be installed **before** any connector app. Once it's installed, install the connector you need:

```bash
bench --site <site> install-app unicommerce
```

## Development Setup

### Local

1. Set up bench by following the [Installation Steps](https://docs.frappe.io/framework/user/en/installation) and keep the server running
	```sh
	$ bench start
	```
2. In a separate terminal window, run the following commands:
	```sh
	# create a new local site to install everything on
	$ bench new-site ecommerce.localhost

	# fetch ERPNext (v16 development branch)
	$ bench get-app erpnext

	# install ERPNext on the new site
	$ bench --site ecommerce.localhost install-app erpnext

	# fetch Ecommerce Core from this repository
	$ bench get-app https://github.com/aerele/ecommerce-core

	# install Ecommerce Core on the site (required before any connector app)
	$ bench --site ecommerce.localhost install-app ecommerce_core

	# map the site name to localhost so it's reachable in the browser
	$ bench --site ecommerce.localhost add-to-hosts
	```
3. Access the site at `http://ecommerce.localhost:8000/app`

## Building a Connector

To build a new ecommerce connector on top of Ecommerce Core, read [AGENTS.md](AGENTS.md). It specifies the full contract: app layout, settings inheritance, product and order workflows, inventory, payments, fulfillment, webhooks, logging and testing requirements.

## Learning and Community

1. [Frappe School](https://frappe.school) - Learn Frappe Framework and ERPNext from the various courses by the maintainers or from the community.
2. [Official documentation](https://docs.frappe.io/framework) - Extensive documentation for Frappe Framework.
3. [Discussion Forum](https://discuss.frappe.io/) - Engage with the community of ERPNext users and service providers.

## Contributing

1. [Contributing Guide](.github/CONTRIBUTING.md)
2. [Issue Guidelines](https://github.com/frappe/erpnext/wiki/Issue-Guidelines)
3. [Pull Request Requirements](https://github.com/frappe/erpnext/wiki/Contribution-Guidelines)
4. Send pull requests to the `develop` branch only.

## License

GNU GPL v3.0. See [license.txt](license.txt).

<br>
<br>
<div align="center">
  <a href="https://aerele.in">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="./ecommerce_core/public/images/aerele-dark.png">
      <img src="./ecommerce_core/public/images/aerele.png" alt="Aerele Technologies" height="32"/>
    </picture>
  </a>
</div>