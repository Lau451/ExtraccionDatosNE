# PCP UI Negociación Specification

## Purpose

Provide the column-per-supplier / row-per-criterion comparison table for a renglón's selected
suppliers, let write-role users record `precio_obtenido` or `no_cotiza` per supplier, and let a
write-role user persist which supplier(s) are `seleccionado` for that renglón, backed by the
`negociacion` router. The close-PCP action is out of scope here — it lives only on the Gestión
detail screen.

## Requirements

### Requirement: Supplier Comparison Table

The system MUST render one column per selected supplier and one row per negotiation criterion
(price, conditions, `mantenimiento_hasta`, payment terms). No automatic multi-criterion ranking
(price × mantenimiento × payment terms) is in scope for this change — that scoring rule is
undefined and deferred to a future change.

#### Scenario: Comparison table on incomplete data

- GIVEN a renglón has suppliers with no recorded result yet
- WHEN the table renders
- THEN a loading, empty, or "no result yet" state is shown per cell instead of a blank or
  crashing table

### Requirement: Negotiation Result Capture Gated by Write Role

The system MUST let a write-role user record `precio_obtenido` or `no_cotiza` per supplier via
`POST`/`GET .../resultado`, and MUST NOT render recording controls for a read-only role.

#### Scenario: Record no_cotiza for a supplier

- GIVEN a supplier selected for negotiation on a renglón
- WHEN the write-role user marks that supplier as `no_cotiza`
- THEN the system records the outcome without requiring a price value

#### Scenario: Read-only role sees results but not the recording form

- GIVEN a read-only-role user viewing the comparison table
- WHEN the screen renders
- THEN recorded results are visible but no recording control is shown

### Requirement: Persisted Multi-Select Supplier Marking

The system MUST let a write-role user mark one or more suppliers per renglón as `seleccionado` via
the negotiation selection endpoint, MUST persist that state in the backend so it survives a page
reload, MUST allow it to be toggled on or off at any time, and MUST NOT treat it as exclusive —
multiple suppliers on the same renglón MAY be `seleccionado` simultaneously to support multi-brand
or assurance sourcing. The system MUST NOT render this control for a read-only role.

#### Scenario: Mark a supplier as seleccionado

- GIVEN a comparison table with a supplier column holding a recorded result
- WHEN the write-role user marks that supplier as `seleccionado`
- THEN the system persists the selection via the backend
- AND the column reflects the selected state

#### Scenario: Selection survives a page reload

- GIVEN a write-role user marked a supplier as `seleccionado`
- WHEN the page is reloaded
- THEN the same supplier is still shown as `seleccionado`, read back from the backend

#### Scenario: Toggle a selection off and select a different supplier later

- GIVEN a supplier previously marked `seleccionado` on a renglón
- WHEN the write-role user unmarks it, and later marks a different supplier as `seleccionado` on
  the same renglón as new quotes come in
- THEN both changes persist independently and reflect the latest state on reload

#### Scenario: Multiple suppliers seleccionado simultaneously

- GIVEN a renglón with two suppliers holding recorded results
- WHEN the write-role user marks both as `seleccionado`
- THEN both suppliers persist as `seleccionado=true` at the same time on that renglón

#### Scenario: Read-only role cannot toggle selection

- GIVEN a read-only-role user viewing the comparison table
- WHEN the screen renders
- THEN the `seleccionado` control is not shown, though the current selection state is visible
