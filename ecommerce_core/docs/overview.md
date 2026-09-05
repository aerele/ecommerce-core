# Ecommerce Core Overview

**Ecommerce Core** provides the foundational architecture for ERPNext ecommerce integrations. It delivers a robust, unified framework for mapping ERPNext master data to external ecommerce platforms, implementing comprehensive synchronization workflows, and providing enterprise-grade logging and retry mechanisms.

Currently powering integrations for **Unicommerce** and **Shopify**, with extensibility for future platforms, Ecommerce Core embodies a plugin-based architecture that separates platform-agnostic concerns from platform-specific implementations.

> **Module**: `ecommerce_core`  
> **License**: GNU GPL v3.0  
> **Publisher**: Aerele (developers@aerele.in)

## Architecture Overview

Ecommerce Core implements a layered architecture that abstracts common integration patterns while providing extensibility for platform-specific requirements:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Ecommerce Integrations                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐   │
│  │ Unicommerce  │  │   Shopify    │  │    Future Providers          │   │
│  └──────────────┘  └──────────────┘  └──────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────────────┘
                                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Ecommerce Core                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐       │
│  │ Data Mapping     │──│ Sync Framework   │──│ Controllers &    │       │
│  │ Layer            │  │                  │  │ Utilities        │       │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘       │
│                                                                         │
│  ┌──────────────────┐                                                   │
│  │ Logging & Retry  │◄──────────────────────────────────────────────────│
│  └──────────────────┘                                                   │
└────────────────────────────┬────────────────────────────────────────────┘
                                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            ERPNext                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐   │
│  │ Item Master  │  │  Customer    │  │  Warehouse   │  │Tax &       │   │
│  │              │  │              │  │              │  │Pricing     │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘   │
│                                                                         │
│  ┌──────────────┐                                                       │
│  │Sales Orders  │◄──────────────────────────────────────────────────────│
│  └──────────────┘                                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

## How It Works

**1. Integration Layer** (Blue): Provider-specific integrations like Unicommerce, Shopify, and Medusa connect to Ecommerce Core.

**2. Core Layer** (Green): The middleware that handles:
- **Data Mapping**: Links ERPNext items to platform items
- **Synchronization**: Manages data flow between systems
- **Controllers**: Provides reusable business logic
- **Logging**: Tracks all operations and enables retries

**3. ERPNext Layer** (Orange): Your ERPNext instance where the actual business data lives.

## Core Components

### 1. Data Mapping Layer

The mapping layer maintains referential integrity between ERPNext entities and their external platform counterparts through a sophisticated linking table architecture.

#### Ecommerce Item Doctype

The `Ecommerce Item` doctype serves as the primary mapping table, establishing bidirectional relationships between ERPNext items and platform entities:

| Field | Type | Purpose |
|-------|------|---------|
| `erpnext_item_code` | Link (Item) | References ERPNext item master |
| `integration` | Link (Module Def) | Identifies the integration provider |
| `integration_item_code` | Data | Platform-specific item identifier |
| `sku` | Data | Stock Keeping Unit from platform |
| `has_variants` | Check | Indicates variant item support |
| `variant_id` | Data | Platform variant identifier |
| `variant_of` | Link (Item) | Template item for variants |
| `inventory_synced_on` | DateTime | Last inventory synchronization timestamp |
| `item_synced_on` | DateTime | Last item metadata synchronization timestamp |

**Technical Implementation:**
- Indexed on `erpnext_item_code`, `integration`, and `integration_item_code` for optimized lookup performance
- Supports variant item hierarchies with parent-child relationships
- Tracks synchronization timestamps to enable incremental updates
- Enforces referential integrity through database constraints

### 2. Synchronization Framework

The synchronization framework provides robust, fault-tolerant data exchange with comprehensive error handling and retry capabilities.

#### Ecommerce Integration Log

The `Ecommerce Integration Log` doctype implements a centralized logging mechanism for all integration operations:

| Field | Type | Description |
|-------|------|-------------|
| `integration` | Link (Module Def) | Target integration provider |
| `status` | Data | Operation state (Queued, Success, Failed) |
| `method` | Small Text | Executed method/function name |
| `message` | Code | Status or error message |
| `traceback` | Code | Exception stack trace (if applicable) |
| `request_data` | Code | Serialized request payload |
| `response_data` | Code | Serialized response payload |

**Features:**
- Automatic log retention management (120-day default)
- Retry mechanism integration with UI controls
- Request/response debugging capabilities
- Status tracking for scheduled operations
- Multi-provider log segregation

### 3. Base Controllers & Abstractions

The framework provides abstract base classes that define integration contracts while encapsulating common functionality.

#### SettingController

Abstract base class for provider-specific settings doctypes:

```python
class SettingController(Document):
    def is_enabled(self) -> bool:
        """Check if integration is enabled or not."""
        raise NotImplementedError()
    
    def get_erpnext_warehouses(self) -> list[ERPNextWarehouse]:
        """Get configured ERPNext warehouses for integration."""
        raise NotImplementedError()
    
    def get_erpnext_to_integration_wh_mapping(self) -> dict[ERPNextWarehouse, IntegrationWarehouse]:
        """Map ERPNext warehouses to platform warehouse identifiers."""
        raise NotImplementedError()
    
    def get_integration_to_erpnext_wh_mapping(self) -> dict[IntegrationWarehouse, ERPNextWarehouse]:
        """Reverse mapping for platform warehouse identifiers."""
        raise NotImplementedError()
```

**Provider Implementation Pattern:**
1. Extend `SettingController` in provider-specific settings doctype
2. Implement warehouse mapping configuration
3. Enable/disable integration functionality
4. Configure synchronization intervals

#### EcommerceCustomer

Comprehensive customer synchronization controller:

```python
class EcommerceCustomer:
    def __init__(self, customer_id: str, customer_id_field: str, integration: str):
        """Initialize with platform customer ID and target integration."""
    
    def is_synced(self) -> bool:
        """Check if customer exists in ERPNext."""
    
    def get_customer_doc(self):
        """Retrieve ERPNext customer document."""
    
    def sync_customer(self, customer_name: str, customer_group: str) -> None:
        """Create customer in ERPNext if not exists."""
    
    def create_customer_address(self, address: dict[str, str]) -> None:
        """Create address linked to customer."""
    
    def create_customer_contact(self, contact: dict[str, str]) -> None:
        """Create contact linked to customer."""
```

**Synchronization Workflow:**
1. Check for existing customer using `is_synced()`
2. Create new customer if not exists using `sync_customer()`
3. Synchronize address information with `create_customer_address()`
4. Synchronize contact details with `create_customer_contact()`

### 4. Inventory Management

The inventory management subsystem provides real-time stock synchronization with support for warehouse hierarchies and delta updates.

#### Core Inventory Functions

**`get_inventory_levels(warehouses: tuple[str], integration: str)`**

Retrieves items requiring inventory updates based on bin modification timestamps:

```python
def get_inventory_levels(warehouses: tuple[str], integration: str) -> list[_dict]:
    """
    Returns items where Bin.modified > EcommerceItem.inventory_synced_on
    for specified warehouses and integration.
    
    Returns: list of _dict containing:
        - ecom_item: Ecommerce Item name
        - item_code: ERPNext item code
        - integration_item_code: Platform item identifier
        - variant_id: Platform variant identifier
        - actual_qty: Current stock quantity
        - warehouse: Warehouse location
        - reserved_qty: Reserved quantity
    """
```

**`get_inventory_levels_of_group_warehouse(warehouse: str, integration: str)`**

Consolidates inventory from child warehouses for group warehouse mappings:

```python
def get_inventory_levels_of_group_warehouse(warehouse: str, integration: str):
    """
    Aggregates inventory from warehouse hierarchy.
    Consolidates all child warehouse quantities for parent warehouse.
    """
```

**`update_inventory_sync_status(ecommerce_item, time=None)`**

Updates synchronization timestamp to prevent duplicate processing:

```python
def update_inventory_sync_status(ecommerce_item, time=None):
    """Marks inventory as synchronized to specified or current time."""
```

**Performance Optimization:**
- Query builder implementation for efficient database operations
- Incremental updates based on modification timestamps
- Support for high-volume inventory sync operations
- Warehouse hierarchy traversal for group warehouses

### 5. Scheduling Engine

The scheduling framework enables configurable, interval-based synchronization tasks with automatic timestamp management.

#### `need_to_run(setting, interval_field, timestamp_field)`

Implements configurable scheduled event gating:

```python
def need_to_run(setting, interval_field, timestamp_field) -> bool:
    """
    Determines if scheduled task should execute based on:
    - Configured interval (in minutes)
    - Last execution timestamp
    - Current time
    
    Returns True if task should run and updates timestamp to now().
    Returns False if interval has not elapsed.
    
    Assumptions:
        - interval_field stores interval in minutes
        - timestamp_field is DateTime field
        - Called from scheduled job with frequency < lowest interval
    """
```

**Usage Pattern:**
```python
# In scheduled job
if need_to_run("Unicommerce Settings", "inventory_sync_frequency", "last_inventory_sync"):
    sync_inventory()
```

**Scheduling Configuration:**
- Provider-specific settings define intervals in minutes
- Automatic timestamp management prevents duplicate execution
- Supports multiple concurrent scheduled tasks
- Flexible interval configuration per integration

### 6. Utility Modules

The framework provides comprehensive utility functions for common integration challenges.

#### Taxation Management

**`taxation.py`** - Manages tax category handling for integration transactions:

```python
DUMMY_TAX_CATEGORY = "Ecommerce Integrations - Ignore"

def get_dummy_tax_category() -> str:
    """Retrieves or creates tax category for tax-exempt integration transactions."""

def validate_tax_template(doc, method=None):
    """Prevents usage of dummy tax category in item tax templates."""
```

**Purpose:** Integrations often handle taxation at the platform level. This dummy category prevents ERPNext from applying additional tax templates to integration-generated transactions.

#### Price List Management

**`price_list.py`** - Manages price list isolation:

```python
DUMMY_PRICE_LIST = "Ecommerce Integrations - Ignore"

def get_dummy_price_list() -> str:
    """Retrieves or creates price list for integration transaction pricing."""

def discard_item_prices(doc, method=None):
    """Removes item prices added to dummy price list."""
```

**Purpose:** Platform-managed pricing requires isolation from ERPNext price lists. The dummy price list prevents manual price configuration from affecting integration transactions.

#### Address Mapping

**`address_mapping.py`** - Comprehensive address field transformation:

Provides mapping between platform address formats and ERPNext address doctypes, handling:
- International address formats
- Country/state code mapping
- Field name transformations
- Validation requirements

#### Naming Series

**`naming_series.py`** - Naming series generation utilities:

Generates unique identifiers for integration-generated documents following configured naming patterns.

## Integration Lifecycle

### Phase 1: Configuration

1. **Provider Setup**
   - Install provider integration app (extends ecommerce_core)
   - Configure provider-specific settings (API credentials, endpoints)
   - Define warehouse mappings in provider settings doctype

2. **Warehouse Mapping**
   ```python
   # In provider settings
   def get_erpnext_to_integration_wh_mapping(self):
       return {
           "Stores - ERPNext": "warehouse_001",
           "Default Warehouse": "warehouse_main"
       }
   ```

3. **Scheduling Configuration**
   - Configure sync intervals in provider settings
   - Enable/disable specific synchronization streams
   - Set log retention policies

### Phase 2: Initial Synchronization

1. **Item Mapping**
   ```python
   create_ecommerce_item(
       integration="Unicommerce",
       erpnext_item_code="ITEM-001",
       integration_item_code="SKU-001",
       has_variants=False,
       variant_of=None
   )
   ```

2. **Customer Synchronization**
   ```python
   customer = EcommerceCustomer("CUST-001", "unicommerce_customer_id", "Unicommerce")
   if not customer.is_synced():
       customer.sync_customer("John Doe", "Individual")
       customer.create_customer_address({...})
       customer.create_customer_contact({...})
   ```

3. **Geographic Mapping**
   ```python
   map_country_and_state("US", "NY")  # Maps to ISO codes
   ```

### Phase 3: Operational Synchronization

1. **Inventory Sync**
   ```python
   # In scheduled job
   if need_to_run(settings, "inventory_interval", "last_inventory_sync"):
       warehouses = settings.get_erpnext_warehouses()
       inventory = get_inventory_levels(warehouses, integration)
       
       for item in inventory:
           update_platform_inventory(item)
           update_inventory_sync_status(item.ecom_item)
   ```

2. **Order Processing**
   - Fetch orders from platform
   - Create ERPNext Sales Order
   - Apply dummy tax category and price list
   - Reserve stock if applicable

3. **Logging & Monitoring**
   ```python
   create_log(
       integration="Unicommerce",
       method="sync_inventory",
       status="Success",
       request_data={...},
       response_data={...}
   )
   ```

### Phase 4: Error Handling & Retry

1. **Automatic Logging**
   - All operations logged to `Ecommerce Integration Log`
   - Exception capture with full stack traces
   - Request/response payload preservation

2. **Manual Retry**
   - Failed operations accessible from UI
   - Individual record retry capability
   - Bulk retry operations

## Global Hooks & Events

Ecommerce Core installs framework-wide hooks that enforce integration data integrity:

### Document Events

```python
doc_events = {
    "Item": {
        "validate": "ecommerce_core.utils.taxation.validate_tax_template"
    },
    "Item Price": {
        "on_change": "ecommerce_core.utils.price_list.discard_item_prices"
    }
}
```

**Purpose:** Prevents manual configuration from interfering with integration-managed data.

### Client-Side Integration

```python
doctype_js = {
    "Sales Order": "public/js/common/ecommerce_transactions.js",
    "Sales Invoice": "public/js/common/ecommerce_transactions.js"
}
```

**Purpose:** Warns users that amending integration-generated documents won't recalculate integration-specific tax rows.

### Log Management

```python
default_log_clearing_doctypes = {
    "Ecommerce Integration Log": 120
}
```

**Purpose:** Automatic cleanup of logs older than 120 days to manage database growth.

## Building a New Provider

### 1. App Structure

```
provider_integration/
├── provider_integration/
│   ├── hooks.py
│   ├── controllers/
│   │   ├── __init__.py
│   │   ├── setting.py          # Extend SettingController
│   │   ├── inventory.py       # Inventory sync logic
│   │   └── orders.py          # Order processing
│   ├── doctype/
│   │   └── provider_settings/ # Settings doctype
│   └── utils/
│       ├── api.py             # Platform API client
│       └── mapping.py         # Field mapping utilities
```

### 2. Settings Doctype

Create `Provider Settings` doctype extending `SettingController`:

```python
from ecommerce_core.controllers.setting import SettingController

class ProviderSettings(SettingController):
    def is_enabled(self) -> bool:
        return self.enable_integration
    
    def get_erpnext_warehouses(self) -> list[ERPNextWarehouse]:
        return [wh.warehouse for wh in self.warehouse_mapping]
    
    def get_erpnext_to_integration_wh_mapping(self) -> dict:
        return {wh.warehouse: wh.integration_warehouse for wh in self.warehouse_mapping}
```

### 3. API Integration

Implement platform-specific API client:

```python
import requests

class ProviderAPI:
    def __init__(self, settings):
        self.base_url = settings.api_endpoint
        self.auth_token = settings.get_password("api_token")
    
    def get_items(self):
        """Fetch items from platform."""
        response = requests.get(
            f"{self.base_url}/items",
            headers={"Authorization": f"Bearer {self.auth_token}"}
        )
        return response.json()
    
    def update_inventory(self, sku, quantity):
        """Update inventory on platform."""
        requests.post(
            f"{self.base_url}/inventory",
            json={"sku": sku, "quantity": quantity},
            headers={"Authorization": f"Bearer {self.auth_token}"}
        )
```

### 4. Scheduled Jobs

Create scheduled tasks in `hooks.py`:

```python
# In provider_integration/hooks.py
scheduler_events = {
    "cron": {
        "*/5 * * * *": "provider_integration.tasks.sync_inventory",
        "0 */2 * * *": "provider_integration.tasks.fetch_orders"
    }
}
```

### 5. Utility Integration

Leverage core utilities for common operations:

```python
from ecommerce_core.utils.taxation import get_dummy_tax_category
from ecommerce_core.utils.price_list import get_dummy_price_list
from ecommerce_core.utils.address_mapping import map_address
from ecommerce_core.utils.naming_series import generate_name
```

## Technical Specifications

### Database Requirements

- **ERPNext**: v13.0 or higher
- **Frappe Framework**: v13.0 or higher
- **MySQL**: 5.6 or higher
- **Python**: 3.6 or higher

### Performance Considerations

- **Inventory Sync**: O(n) where n = number of modified items
- **Customer Sync**: O(1) per customer with indexed lookups
- **Log Queries**: Optimized with compound indexes on integration + status
- **Scheduling**: Minimal overhead with timestamp-based gating

### Security Features

- Credential storage through Frappe's password manager
- API token encryption at rest
- Role-based access control on logs
- Audit trail for all configuration changes

### Scalability

- Support for high-volume item catalogs (100,000+ items)
- Batch processing for inventory updates
- Queue-based job execution for long-running tasks
- Horizontal scaling for multi-instance deployments

## Best Practices

### Error Handling

```python
try:
    result = api_call()
    create_log(
        integration="Provider",
        method="api_call",
        status="Success",
        response_data=result
    )
except Exception as e:
    create_log(
        integration="Provider",
        method="api_call",
        status="Failed",
        message=str(e),
        traceback=frappe.get_traceback()
    )
```

### Configuration Validation

```python
def validate_settings(settings):
    if not settings.is_enabled():
        raise Exception("Integration is disabled")
    
    if not settings.get_erpnext_warehouses():
        raise Exception("No warehouses configured")
    
    if not settings.api_endpoint:
        raise Exception("API endpoint not configured")
```

### Testing Strategy

```python
# In provider_integration/tests/test_provider.py
from ecommerce_core.utils.before_test import before_tests

def test_inventory_sync():
    before_tests()  # Sets up test environment
    
    settings = get_test_settings()
    inventory = get_inventory_levels(
        settings.get_erpnext_warehouses(),
        "Provider"
    )
    
    assert len(inventory) > 0
    assert inventory[0].actual_qty >= 0
```

## Reference Documentation

- **API Reference**: Detailed API documentation for all controllers and utilities
- **Shared Entities**: Complete doctype specifications and field mappings
- **Building Providers**: Comprehensive provider development guide

---

*This documentation covers the foundational architecture of Ecommerce Core. For implementation details, API references, or provider-specific guides, see the complete documentation suite.*
