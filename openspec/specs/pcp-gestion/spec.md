# PCP Gestión Specification

## Purpose

Manage the PCP (price-improvement request) header as a Compras-owned worklist entity: one PCP per
originating `presupuesto`, moving through a fixed state machine, listable and filterable primarily by
Comercial's requested delivery date, tenant-isolated, and writable only by authorized roles.

## Requirements

### Requirement: PCP Creation from Presupuesto

The system MUST create a PCP header linked 1:1 to a single originating `presupuesto`, scoped to that
presupuesto's `drogueria_id`.

#### Scenario: Create a PCP from an eligible presupuesto

- GIVEN a presupuesto P with renglones eligible for price improvement, for `drogueria_id` X
- WHEN a PCP is created for P
- THEN the system creates one PCP header linked to P
- AND the PCP is scoped to `drogueria_id` X

#### Scenario: Reject a second PCP for the same presupuesto

- GIVEN presupuesto P already has an open PCP
- WHEN a second PCP creation for P is requested
- THEN the system rejects the request with a conflict error

### Requirement: PCP State Machine

The system MUST enforce the state sequence `nueva` → `en_gestion` → `esperando_respuesta` → `cerrada`
and MUST NOT allow a transition that skips a state or moves backward.

#### Scenario: Valid sequential transition

- GIVEN a PCP in state `nueva`
- WHEN Compras begins managing it
- THEN the PCP moves to `en_gestion`

#### Scenario: Reject skipping a state

- GIVEN a PCP in state `nueva`
- WHEN a transition directly to `esperando_respuesta` or `cerrada` is requested
- THEN the system rejects the transition
- AND the PCP remains in `nueva`

#### Scenario: Reject backward transition

- GIVEN a PCP in state `esperando_respuesta`
- WHEN a transition back to `en_gestion` is requested
- THEN the system rejects the transition

### Requirement: Listing and Filtering by Requested Delivery Date

The system MUST list PCPs with filters, and MUST support filtering primarily by the requested delivery
date carried from the originating presupuesto.

#### Scenario: Filter PCPs nearing the requested delivery date

- GIVEN PCPs exist with different requested delivery dates for `drogueria_id` X
- WHEN Compras filters the list by a delivery date range
- THEN only PCPs whose requested delivery date falls in that range are returned

#### Scenario: List filtered by state

- GIVEN PCPs exist in multiple states for `drogueria_id` X
- WHEN Compras filters the list by state `en_gestion`
- THEN only PCPs currently in `en_gestion` are returned

### Requirement: Multi-Tenant Isolation

The system MUST scope every PCP by `drogueria_id` using `mismo_tenant()` and MUST NOT return or modify
a PCP belonging to a different `drogueria_id`.

#### Scenario: Cross-tenant PCP access is blocked

- GIVEN a PCP belongs to `drogueria_id` X
- WHEN a request authenticated for `drogueria_id` Y requests that PCP
- THEN the system returns a not-found response

### Requirement: Role-Restricted Write Access

The system MUST restrict PCP write operations (create, transition, edit) to the `admin`, `gerencia`,
and `compras` roles at both the router (`require_roles()`) and RLS (`get_rol()`) levels, matching the
existing `precios_proveedor` write policy exactly.

#### Scenario: Authorized role transitions a PCP

- GIVEN a user with role `compras` for `drogueria_id` X
- WHEN that user transitions a PCP of X from `nueva` to `en_gestion`
- THEN the transition succeeds

#### Scenario: Unauthorized role is rejected

- GIVEN a user with a role other than `admin`, `gerencia`, or `compras`
- WHEN that user attempts to create or transition a PCP
- THEN the system rejects the request at the router level
- AND no PCP row is created or modified
