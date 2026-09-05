# Terceros Direcciones Specification

## Purpose

Manage postal/commercial addresses belonging to a `tercero`, where a single address can declare more
than one simultaneous use (billing, delivery, documentation, other) through an N:M relationship instead
of fixed boolean or single-purpose columns.

## Requirements

### Requirement: Address Creation

The system MUST allow creating an address (`tercero_direcciones`) linked to an existing `tercero` and
scoped to the tercero's `drogueria_id`.

#### Scenario: Create an address for a tercero

- GIVEN an existing tercero T for `drogueria_id` X
- WHEN the client submits a valid address payload for tercero T
- THEN the system creates a row in `tercero_direcciones` linked to T
- AND scopes the row to `drogueria_id` X

#### Scenario: Reject address for a nonexistent tercero

- GIVEN no tercero exists with `id` = 999 for `drogueria_id` X
- WHEN the client submits an address payload referencing tercero 999
- THEN the system rejects the request with a not-found error
- AND no address row is created

### Requirement: Multiple Simultaneous Uses per Address

The system MUST allow a single address to be associated with more than one use at the same time
(facturación, entrega, documentación, otra) through an N:M relationship, and MUST NOT model uses as
fixed single-value or boolean columns on the address row.

#### Scenario: Assign two uses to the same address

- GIVEN an existing address A for tercero T
- WHEN the client assigns uses "facturacion" and "entrega" to address A
- THEN both uses are recorded as active associations for address A
- AND querying address A returns both uses

#### Scenario: Remove one use without affecting others

- GIVEN address A has uses "facturacion" and "entrega" assigned
- WHEN the client removes the "entrega" use from address A
- THEN address A retains the "facturacion" use
- AND address A no longer appears when filtering by "entrega"

#### Scenario: Query addresses by use

- GIVEN tercero T has address A with use "documentacion" and address B without it
- WHEN the client requests tercero T's addresses filtered by use "documentacion"
- THEN the response includes address A
- AND the response excludes address B

### Requirement: Address Edit and Removal

The system MUST allow editing an address's fields and its use associations, and MUST allow removing an
address, without deleting the owning tercero.

#### Scenario: Edit address fields

- GIVEN an existing address A for tercero T
- WHEN the client updates address A's street and city fields
- THEN address A reflects the updated fields
- AND address A's use associations are unchanged

#### Scenario: Remove an address

- GIVEN tercero T has addresses A and B
- WHEN the client removes address A
- THEN address A and its use associations no longer exist
- AND address B and tercero T are unaffected

### Requirement: Multi-Tenant Isolation

The system MUST scope every address and use association by `drogueria_id` and MUST NOT expose or
modify an address belonging to a tercero of a different `drogueria_id`.

#### Scenario: Cross-tenant address access is blocked

- GIVEN address A belongs to a tercero of `drogueria_id` X
- WHEN a request authenticated for `drogueria_id` Y requests address A
- THEN the system returns a not-found response
