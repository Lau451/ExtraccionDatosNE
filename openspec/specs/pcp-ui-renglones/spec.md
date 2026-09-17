# PCP UI Renglones Specification

## Purpose

Provide screens to list and create renglones for a PCP, view an enriched renglón detail (product +
catalogued suppliers), and select suppliers for negotiation, backed by the `renglones` router.

## Requirements

### Requirement: Renglón List and Creation Gated by Write Role

The system MUST list a PCP's renglones for every read-role user and MUST let only a write-role
user create a renglón, submitting exactly the `PcpRenglonCreate` payload shape (`item_proceso_id`,
`origen`, `regla_pcp_id`).

#### Scenario: Create a renglón with a valid payload

- GIVEN a write-role user on a PCP's renglones screen
- WHEN they submit a valid `item_proceso_id`
- THEN the system calls `POST .../renglones` and the new renglón appears in the list

#### Scenario: Reject a payload with an unexpected field

- GIVEN the `renglones` API rejects any field outside `PcpRenglonCreate` (`extra=forbid`)
- WHEN the create form submits a payload containing an extra or renamed field
- THEN the system receives a 422 response
- AND the screen surfaces a validation error instead of silently dropping the field

#### Scenario: Read-only role cannot create a renglón

- GIVEN a read-only-role user views a PCP's renglones screen
- WHEN the screen renders
- THEN no create-renglón action is shown

### Requirement: Enriched Renglón Detail

The system MUST show, for a renglón, the associated product's identifying data and the suppliers
currently catalogued for that product, visible to every read-role user.

#### Scenario: Open renglón detail

- GIVEN a renglón for a known product
- WHEN the user opens its detail
- THEN the product's identifying data and its catalogued suppliers are shown

### Requirement: Supplier Selection for Negotiation Gated by Write Role

The system MUST let a write-role user select one, several, or all catalogued suppliers as
negotiation targets for a renglón, and MUST NOT allow selection by a read-only role.

#### Scenario: Select multiple suppliers

- GIVEN a renglón with three catalogued suppliers
- WHEN a write-role user selects two of them and confirms
- THEN the system records both as negotiation targets via `POST .../proveedores`

#### Scenario: Read-only role cannot select suppliers

- GIVEN a read-only-role user views a renglón detail
- WHEN the screen renders
- THEN the supplier-selection controls are not shown
