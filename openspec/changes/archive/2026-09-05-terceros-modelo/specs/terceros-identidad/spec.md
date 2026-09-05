# Terceros Identidad Specification

## Purpose

Manage the identity of a `tercero` (any external party the system deals with) as a single row shared
by the client and provider roles, replacing the current independent `clientes`/`proveedores` tables.

## Requirements

### Requirement: Tercero Creation

The system MUST allow creating a `tercero` scoped to a `drogueria_id`, capturing at minimum a
`codigo_interno`, `nombre`, and CUIT, independent of any legacy import.

#### Scenario: Create a tercero via API

- GIVEN an authenticated request for `drogueria_id` X
- WHEN the client submits a valid tercero payload with `codigo_interno` and `nombre`
- THEN the system creates one row in `terceros` scoped to `drogueria_id` X
- AND returns the created tercero including its generated `id`

#### Scenario: Reject duplicate codigo_interno within the same drogueria

- GIVEN a tercero with `codigo_interno` "1001" already exists for `drogueria_id` X
- WHEN a new tercero is submitted with `codigo_interno` "1001" for `drogueria_id` X
- THEN the system rejects the request with a conflict error
- AND no new row is created

### Requirement: Dual-Role Assignment

The system MUST allow a single `tercero` to hold the cliente role, the proveedor role, or both
simultaneously, represented as independent rows in `clientes` and `proveedores` sharing the tercero's
`id` as their primary key (`id = tercero_id`).

#### Scenario: Assign both roles to the same tercero

- GIVEN an existing tercero with `id` T for `drogueria_id` X
- WHEN the client requests role "cliente" and role "proveedor" for tercero T
- THEN the system creates one row in `clientes` with `id` = T
- AND creates one row in `proveedores` with `id` = T
- AND both rows resolve to the same tercero identity when queried

#### Scenario: Assign a single role

- GIVEN an existing tercero with `id` T
- WHEN the client requests only the role "cliente" for tercero T
- THEN the system creates a row in `clientes` with `id` = T
- AND does not create a row in `proveedores`

#### Scenario: Reject duplicate role assignment

- GIVEN a tercero T already has the "cliente" role assigned
- WHEN the client requests the "cliente" role again for tercero T
- THEN the system rejects the request with a conflict error
- AND the existing `clientes` row is unchanged

### Requirement: Role-Specific Fields Preserved

The system MUST preserve `es_competidor` and `es_proveedor_compra` as boolean fields on the
`proveedores` role table, unchanged in meaning from the current schema.

#### Scenario: Set proveedor-specific flags

- GIVEN a tercero T has the "proveedor" role assigned
- WHEN the client updates `es_competidor` to true and `es_proveedor_compra` to true on tercero T
- THEN the `proveedores` row for T stores both flags as true
- AND the `clientes` row for T, if any, is unaffected

### Requirement: Tercero and Role Update

The system MUST allow editing tercero identity fields and role-specific fields independently, without
requiring the other role's data.

#### Scenario: Update tercero identity fields

- GIVEN an existing tercero T with `nombre` "Droguería A"
- WHEN the client updates `nombre` to "Droguería A S.A."
- THEN the tercero row reflects the new `nombre`
- AND any assigned role rows are unchanged

### Requirement: Logical Deactivation

The system MUST support logical deactivation (`activo = false`) of a tercero and MUST NOT physically
delete rows in `terceros`, `clientes`, or `proveedores` through the API.

#### Scenario: Deactivate a tercero

- GIVEN an active tercero T with both roles assigned
- WHEN the client deactivates tercero T
- THEN `terceros.activo` becomes false for T
- AND the tercero and its roles are excluded from default active-only listings
- AND the rows remain queryable by id

#### Scenario: Deactivation semantics apply consistently

- GIVEN a tercero T is deactivated
- WHEN a client lists active clientes or proveedores for the drogueria
- THEN tercero T does not appear in either listing regardless of its assigned roles

### Requirement: Multi-Tenant Isolation

The system MUST scope every tercero, role, and role-specific query by `drogueria_id` and MUST NOT
return or modify a tercero belonging to a different `drogueria_id`.

#### Scenario: Cross-tenant read is blocked

- GIVEN a tercero T belongs to `drogueria_id` X
- WHEN a request authenticated for `drogueria_id` Y requests tercero T
- THEN the system returns a not-found response
- AND no data about tercero T is disclosed

### Requirement: Referential Compatibility

The system MUST keep all existing foreign keys that reference `clientes.id` or `proveedores.id`
resolvable without modification, because the shared primary key preserves row identity across the
schema rewrite.

#### Scenario: Preexisting FK resolves unchanged

- GIVEN a row in `procesos_comerciales` referencing `cliente_id` = T
- WHEN the terceros-modelo migration is applied
- THEN the row in `procesos_comerciales` still resolves to a valid `clientes.id` = T
- AND no data migration of `procesos_comerciales` is required
