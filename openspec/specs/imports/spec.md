# Terceros Legacy Import Specification

## Purpose

Keep the legacy CSV import path (`services/presupuestacion/imports/`) working against the new
`terceros`/`clientes`/`proveedores` schema, splitting upserts across `terceros` and the role tables
while preserving idempotency, and recording traceability to the legacy system of origin.

## Requirements

### Requirement: Idempotent Import by (drogueria_id, codigo_interno)

The system MUST upsert terceros during CSV import keyed by the combination of `drogueria_id` and
`codigo_interno`, and MUST NOT create a duplicate `terceros` row when the same CSV is imported more
than once.

#### Scenario: Re-importing the same CSV does not duplicate terceros

- GIVEN a CSV import already created a tercero with `codigo_interno` "2001" for `drogueria_id` X
- WHEN the same CSV is imported again for `drogueria_id` X
- THEN the system updates the existing tercero row instead of creating a new one
- AND exactly one row with `codigo_interno` "2001" exists in `terceros` for `drogueria_id` X

#### Scenario: Re-importing does not duplicate role rows

- GIVEN a CSV import already created a `clientes` role row for tercero T
- WHEN the same CSV is imported again and still marks T as a cliente
- THEN the system updates the existing `clientes` row instead of inserting a new one
- AND exactly one `clientes` row exists with `id` = T

### Requirement: Split Insert Across Identity and Role

The system MUST split each imported record's data between the `terceros` table (identity fields) and
the corresponding role table (`clientes` and/or `proveedores`, role-specific fields), consistent with
the shared primary key model.

#### Scenario: Import a record present in both legacy clientes and proveedores sources

- GIVEN a legacy CSV row identifies the same `codigo_interno` as both a cliente and a proveedor for
  `drogueria_id` X
- WHEN the import runs
- THEN the system creates or updates a single `terceros` row for that `codigo_interno`
- AND creates or updates both a `clientes` row and a `proveedores` row sharing that tercero's `id`

#### Scenario: Import a cliente-only record

- GIVEN a legacy CSV row identifies a party as a cliente only
- WHEN the import runs
- THEN the system creates or updates the `terceros` row and the `clientes` row
- AND does not create a `proveedores` row for that tercero

### Requirement: Legacy Traceability

The system MUST record, for every tercero originated from the legacy import, a link in
`terceros_legacy_map` capturing the legacy system of origin and the external identifier used in that
system.

#### Scenario: Legacy map entry created on first import

- GIVEN a tercero does not yet exist for `codigo_interno` "3001" in `drogueria_id` X
- WHEN the CSV import creates that tercero
- THEN the system creates a `terceros_legacy_map` row linking the new tercero to its legacy system
  identifier

#### Scenario: Legacy map entry is not duplicated on re-import

- GIVEN a `terceros_legacy_map` row already links tercero T to its legacy identifier
- WHEN the same CSV is imported again
- THEN no additional `terceros_legacy_map` row is created for tercero T

### Requirement: Deactivation via Import

The system MUST support logically deactivating a tercero or role when the import detects it is no
longer present in the legacy source, consistent with the deactivate-not-delete rule used by native
CRUD.

#### Scenario: Import deactivates a tercero missing from the latest CSV

- GIVEN tercero T was created by a previous import and is active
- WHEN the latest CSV import no longer includes tercero T's `codigo_interno`
- THEN the system marks tercero T as inactive
- AND does not delete the `terceros` row

### Requirement: Native and Import Coexistence

The system MUST allow a tercero created natively through the API to later be matched and updated by
the legacy import when its `codigo_interno` appears in a CSV, without creating a duplicate.

#### Scenario: Import updates a natively created tercero

- GIVEN a tercero was created through the API with `codigo_interno` "4001" for `drogueria_id` X
- WHEN a CSV import for `drogueria_id` X includes a row with `codigo_interno` "4001"
- THEN the system updates the existing tercero instead of creating a new one
- AND links it in `terceros_legacy_map` if not already linked
