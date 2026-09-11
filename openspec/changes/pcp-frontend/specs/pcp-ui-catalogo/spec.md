# PCP UI Catálogo Specification

## Purpose

Provide an ad-hoc screen to view and add producto↔proveedor associations, keyed only by
`producto_id`, independent of any PCP context, backed by the `catalogo` router.

## Requirements

### Requirement: Supplier List by Product

The system MUST list the proveedores associated with a given `producto_id`, including the empty
state.

#### Scenario: List associated suppliers

- GIVEN a product has two associated proveedores
- WHEN the user opens the catálogo screen for that product
- THEN both proveedores are displayed

#### Scenario: Empty catalog for a product

- GIVEN a product has no associated proveedor
- WHEN the user opens the catálogo screen for that product
- THEN the screen shows an empty state and still offers the add action to a write-role user

### Requirement: Ad-Hoc Association Creation Gated by Write Role

The system MUST let write-role users add a new producto↔proveedor association via `POST` and MUST
NOT render the add action for read-only roles.

#### Scenario: Write role adds a supplier

- GIVEN a write-role user viewing the catálogo screen for a product
- WHEN they submit a new proveedor association
- THEN the system creates the association and it appears in the list without a page reload

#### Scenario: Read-only role cannot add

- GIVEN a read-only-role user (e.g. `superadmin`) viewing the catálogo screen
- WHEN the screen renders
- THEN no add-association action is shown

#### Scenario: Reject a duplicate association

- GIVEN a product already has proveedor P associated
- WHEN a write-role user attempts to add P again
- THEN the system surfaces the conflict error returned by the API and does not add a duplicate row
