# Terceros Contactos Specification

## Purpose

Manage contact people belonging to a `tercero` directly — not to a "cliente" or "proveedor" role —
so the same contact model covers clients, providers, and dual-role terceros. Replaces
`cliente_contactos`.

## Requirements

### Requirement: Contact Belongs to a Tercero

The system MUST link every contact (`terceros_contactos`) to a `tercero` (not to a specific cliente or
proveedor role row), so a contact remains valid regardless of which roles the tercero holds.

#### Scenario: Create a contact for a tercero with only the proveedor role

- GIVEN a tercero T for `drogueria_id` X with only the "proveedor" role assigned
- WHEN the client creates a contact for tercero T
- THEN the system creates a row in `terceros_contactos` linked to T
- AND the contact is retrievable regardless of T's assigned roles

### Requirement: Contact Fields

The system MUST capture, per contact: `nombre` and `apellido` as separate fields, an optional
`sector_id` referencing `sectores_contacto`, `cargo`, `email`, `telefono`, `celular`, `es_principal`,
and `activo`.

#### Scenario: Create a full contact

- GIVEN tercero T exists for `drogueria_id` X
- WHEN the client creates a contact for T with `nombre`, `apellido`, `sector_id`, `cargo`, `email`,
  `telefono`, `celular`
- THEN the system stores all submitted fields on the new contact row
- AND `activo` defaults to true

#### Scenario: Create a contact without a sector

- GIVEN tercero T exists for `drogueria_id` X
- WHEN the client creates a contact for T without `sector_id`
- THEN the system creates the contact with `sector_id` null
- AND the request succeeds

#### Scenario: Reject a sector from another drogueria

- GIVEN `sector_id` S belongs to `drogueria_id` Y
- WHEN the client creates a contact for a tercero of `drogueria_id` X with `sector_id` S
- THEN the system rejects the request with a validation error
- AND no contact row is created

### Requirement: Single Active Principal Contact per Tercero

The system MUST allow at most one active contact per tercero with `es_principal = true` at any time.

#### Scenario: Mark a new contact as principal replaces the previous one

- GIVEN tercero T has an active contact C1 with `es_principal = true`
- WHEN the client creates a new active contact C2 for tercero T with `es_principal = true`
- THEN the system sets C1's `es_principal` to false
- AND C2's `es_principal` remains true
- AND only one active contact of tercero T has `es_principal = true`

#### Scenario: Deactivating the principal contact does not auto-promote another

- GIVEN tercero T has active contact C1 with `es_principal = true` and active contact C2 with
  `es_principal = false`
- WHEN the client deactivates contact C1
- THEN C1's `activo` becomes false
- AND no other contact of tercero T is automatically promoted to `es_principal = true`

### Requirement: Contact Edit and Deactivation

The system MUST allow editing a contact's fields and MUST support logical deactivation
(`activo = false`) instead of physical deletion.

#### Scenario: Deactivate a contact

- GIVEN an active contact C for tercero T
- WHEN the client deactivates contact C
- THEN `activo` becomes false for C
- AND C is excluded from default active-only contact listings for T

### Requirement: Multi-Tenant Isolation

The system MUST scope every contact by the owning tercero's `drogueria_id` and MUST NOT expose or
modify a contact belonging to a tercero of a different `drogueria_id`.

#### Scenario: Cross-tenant contact access is blocked

- GIVEN contact C belongs to a tercero of `drogueria_id` X
- WHEN a request authenticated for `drogueria_id` Y requests contact C
- THEN the system returns a not-found response
