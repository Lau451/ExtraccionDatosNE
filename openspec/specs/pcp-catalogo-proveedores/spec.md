# PCP Catálogo de Proveedores Specification

## Purpose

Provide a real producto↔proveedor association catalog that powers "available suppliers for this
product" in the PCP renglón view, starting empty and growing through ad-hoc additions made during PCP
management.

## Requirements

### Requirement: Producto↔Proveedor Association

The system MUST maintain an association between a product and the proveedores that can supply it,
scoped to `drogueria_id`, independent of any specific PCP.

#### Scenario: List suppliers associated with a product

- GIVEN a product has two proveedores associated with it for `drogueria_id` X
- WHEN the association list is queried for that product
- THEN both proveedores are returned

#### Scenario: Product with no associated suppliers

- GIVEN a product has no proveedor association yet
- WHEN the association list is queried for that product
- THEN the system returns an empty list without error

### Requirement: Ad-Hoc Supplier Addition During a PCP

The system MUST allow Compras to add a new producto↔proveedor association while managing a PCP
renglón, without requiring a separate maintenance screen.

#### Scenario: Add a supplier to a product from the renglón view

- GIVEN a renglón for a product with no associated proveedor P
- WHEN Compras adds proveedor P as available for that product from within the PCP
- THEN the system creates the producto↔proveedor association
- AND proveedor P becomes selectable for that renglón immediately

#### Scenario: Reject adding a duplicate association

- GIVEN a product already has proveedor P associated
- WHEN Compras attempts to add proveedor P again for the same product
- THEN the system rejects the request with a conflict error

### Requirement: Empty Catalog on Day One

The system MUST allow the catalog to start with zero associations and MUST NOT require pre-seeding
from historical data before the PCP module can be used.

#### Scenario: Use the module with an empty catalog

- GIVEN no producto↔proveedor associations exist yet for `drogueria_id` X
- WHEN Compras opens a PCP renglón for a product
- THEN the system shows zero available suppliers
- AND still allows adding one ad-hoc

### Requirement: Multi-Tenant Isolation

The system MUST scope every producto↔proveedor association by `drogueria_id` and MUST NOT expose or
modify an association belonging to a different `drogueria_id`.

#### Scenario: Cross-tenant association is invisible

- GIVEN a producto↔proveedor association belongs to `drogueria_id` X
- WHEN a request authenticated for `drogueria_id` Y queries suppliers for that product
- THEN the association from X is not returned
