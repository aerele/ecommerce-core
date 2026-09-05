# Contributing to Ecommerce Core

Thank you for considering contributing to Ecommerce Core!

Ecommerce Core is the shared foundation for all standalone ERPNext ecommerce connector apps, so changes here affect every integration built on top of it. Before proposing a change, please check whether the behaviour belongs here (shared across connectors) or in a specific connector app (provider-specific).

## Issues

1. **Search existing issues** before creating a new one. Duplicates will be closed and directed to the original.
2. **Report issues separately.** Do not combine multiple unrelated problems into a single report.
3. **Be concise.** Use bullet points and screenshots where possible.
4. **Include versions** for Frappe, ERPNext, Ecommerce Core and the connector app involved. Developers do not have access to your environment, so the more relevant information you provide, the faster the issue can be fixed.

The issue tracker is not the right place for general questions or discussions. Please use the [forum](https://discuss.frappe.io/) instead.

## Development Setup

Follow the [Development Setup](../README.md#development-setup) section in the README to get a local bench running with ERPNext, Ecommerce Core installed.

## Code Style

This app uses [`pre-commit`](https://pre-commit.com/) for linting and formatting. Please install and enable it so checks run locally before every commit:

```bash
cd apps/ecommerce_core
pre-commit install
```

Pre-commit runs ruff (lint + format), prettier, and several sanity checks (YAML/JSON/TOML validity, merge conflicts, trailing whitespace). The same checks run on every pull request via the Linters workflow.

Conventions:

- Tabs for indentation, double quotes, 110 character line limit (enforced by ruff).
- All business logic and validations belong on the server side.
- Use `frappe._()` for user-facing strings.

## Tests

Run the test suite before submitting a pull request:

```bash
bench --site <site> run-tests --app ecommerce_core
```

Add or update tests for every behaviour change. Bug fixes should include a test that fails without the fix.

## Pull Requests

1. Send pull requests to the `develop` branch only.
2. Follow the [Pull Request Checklist](https://github.com/frappe/erpnext/wiki/Pull-Request-Checklist) and [Contribution Guidelines](https://github.com/frappe/erpnext/wiki/Contribution-Guidelines).
3. Put `closes #XXXX` in your PR description to auto-close the issue it fixes.

## Security

Please do not report security vulnerabilities through public GitHub issues or pull requests. Report them privately to [developers@aerele.in](mailto:developers@aerele.in), including steps to reproduce and the affected app versions.
