# PCP Legacy Import Specification

## Purpose

Import PCPs from the legacy system on `codigo_legacy`, mirroring the `upsert_terceros_legacy` +
`terceros_legacy_map` idempotency pattern, so the module has real data from day one and re-running the
same import never creates duplicates.

## Requirements

### Requirement: Idempotent Import by codigo_legacy

The system MUST upsert PCPs during legacy import keyed by `codigo_legacy`, and MUST NOT create a
duplicate PCP when the same source record is imported more than once.

#### Scenario: Re-importing the same PCP does not duplicate it

- GIVEN a legacy import already created a PCP with `codigo_legacy` "PCP-2001" for `drogueria_id` X
- WHEN the same source record is imported again for `drogueria_id` X
- THEN the system updates the existing PCP instead of creating a new one
- AND exactly one PCP with `codigo_legacy` "PCP-2001" exists for `drogueria_id` X

#### Scenario: Re-importing does not duplicate renglones

- GIVEN a legacy-imported PCP already has a renglón sourced from the legacy record
- WHEN the same source record is imported again
- THEN the system does not insert a duplicate renglón for the same source line

### Requirement: Legacy Traceability

The system MUST record, for every PCP originated from the legacy import, a link capturing the legacy
system's identifier, mirroring the `terceros_legacy_map` pattern.

#### Scenario: Legacy map entry created on first import

- GIVEN no PCP exists yet for `codigo_legacy` "PCP-3001" in `drogueria_id` X
- WHEN the legacy import creates that PCP
- THEN the system creates a mapping entry linking the new PCP to its legacy identifier

#### Scenario: Legacy map entry is not duplicated on re-import

- GIVEN a mapping entry already links PCP T to its legacy identifier
- WHEN the same source record is imported again
- THEN no additional mapping entry is created for PCP T

### Requirement: Imported Renglones Tagged as import_legado

The system MUST tag every renglón created through the legacy import with `origen = 'import_legado'`.

#### Scenario: Legacy-imported renglón carries the correct origen

- GIVEN a PCP renglón is created by the legacy import
- WHEN the renglón is persisted
- THEN its `origen` is `import_legado`

### Requirement: Native and Import Coexistence

The system MUST allow a PCP created natively through the API to later be matched and updated by the
legacy import when its `codigo_legacy` appears in a source record, without creating a duplicate.

#### Scenario: Import updates a natively created PCP

- GIVEN a PCP was created through the API and later assigned `codigo_legacy` "PCP-4001"
- WHEN a legacy import for the same drogueria includes a record with `codigo_legacy` "PCP-4001"
- THEN the system updates the existing PCP instead of creating a new one
