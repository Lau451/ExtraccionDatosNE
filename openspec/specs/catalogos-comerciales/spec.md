# Catálogos Comerciales Specification

## Purpose

Provide droguería-scoped catalogs — `sectores_contacto`, `condiciones_pago`, `formas_pago` — managed
natively through CRUD endpoints, and expose a "habitual" (default) condición de pago and forma de pago
per cliente/proveedor via foreign key.

## Requirements

### Requirement: Catalog Scoping

The system MUST scope every catalog entry (`sectores_contacto`, `condiciones_pago`, `formas_pago`) by
`drogueria_id`, and MUST NOT expose or reference an entry belonging to a different `drogueria_id`.

#### Scenario: Cross-tenant catalog entry is invisible

- GIVEN a `condiciones_pago` entry C belongs to `drogueria_id` X
- WHEN a request authenticated for `drogueria_id` Y lists condiciones de pago
- THEN entry C does not appear in the response

### Requirement: Catalog CRUD

The system MUST allow creating, editing, and logically deactivating entries in each of
`sectores_contacto`, `condiciones_pago`, and `formas_pago` via API, independent of the legacy import.

#### Scenario: Create a condicion de pago

- GIVEN `drogueria_id` X has no condicion de pago named "Contado"
- WHEN the client creates a condicion de pago "Contado" for `drogueria_id` X
- THEN the system creates the catalog entry scoped to X
- AND the entry is retrievable by the same drogueria

#### Scenario: Deactivate a catalog entry instead of deleting it

- GIVEN an active `formas_pago` entry "Transferencia" for `drogueria_id` X
- WHEN the client deactivates that entry
- THEN the entry's `activo` becomes false
- AND the entry is excluded from default active-only listings
- AND the entry remains referenceable by existing FKs that already point to it

### Requirement: Condiciones de Pago as Multiple Terms

The system MUST store `condiciones_pago.plazos_dias` as an array of integers (for example
`{30,60,90}`), replacing the previous single integer `plazo_pago_dias` field, and MUST NOT restrict a
condición de pago to a single term.

#### Scenario: Create a condicion de pago with multiple terms

- GIVEN `drogueria_id` X exists
- WHEN the client creates a condicion de pago with `plazos_dias = {30,60,90}`
- THEN the system stores all three values in `plazos_dias`
- AND the entry is retrievable with the full array

#### Scenario: Create a condicion de pago with a single term

- GIVEN `drogueria_id` X exists
- WHEN the client creates a condicion de pago with `plazos_dias = {30}`
- THEN the system stores the single-element array
- AND the request succeeds

### Requirement: Habitual Condición and Forma de Pago on Roles

The system MUST expose a "habitual" (default) condición de pago and forma de pago on `clientes` and
`proveedores` as foreign keys into `condiciones_pago` and `formas_pago`, and MUST NOT retain the
previous `plazo_pago_dias` integer column or the previous free-text `condiciones_pago` column.

#### Scenario: Assign a habitual condicion de pago to a cliente

- GIVEN a cliente role row for tercero T and an existing `condiciones_pago` entry P for the same
  `drogueria_id`
- WHEN the client sets P as tercero T's habitual condicion de pago
- THEN the `clientes` row for T references P by foreign key
- AND no free-text condición de pago value is stored

#### Scenario: Reject a habitual condicion de pago from another drogueria

- GIVEN `condiciones_pago` entry P belongs to `drogueria_id` Y
- WHEN the client tries to set P as the habitual condicion de pago for a proveedor of `drogueria_id` X
- THEN the system rejects the request with a validation error

### Requirement: es_competidor and es_proveedor_compra Preserved As-Is

The system MUST carry `es_competidor` and `es_proveedor_compra` on `proveedores` with the same
semantics they had before this change, without redesigning their role model.

#### Scenario: Existing flag semantics are unchanged

- GIVEN a proveedor role row with `es_competidor = true`
- WHEN the client reads that proveedor
- THEN `es_competidor` is returned as true with no additional derived role behavior
