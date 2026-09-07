# PCP Sugerencias Specification

## Purpose

Deliver the confirmed v1 intelligence features on top of the PCP module: a quantity-grouping
suggestion, a recent-price-reuse suggestion, and the phased feedback loop that closes the negotiation
back to the requesting Comercial user.

## Requirements

### Requirement: Quantity-Grouping Suggestion

The system MUST detect the same article appearing across multiple open PCPs nearing their requested
delivery date and MUST surface a suggestion to request a joint quote with the aggregated quantity,
without ever merging or restructuring the underlying PCP records automatically.

#### Scenario: Suggestion surfaces for a repeated article

- GIVEN the same article appears as an open renglón in two PCPs nearing their requested delivery date
- WHEN Compras views either renglón
- THEN the system surfaces a suggestion proposing a joint quote with the aggregated quantity

#### Scenario: Suggestion never auto-merges PCPs

- GIVEN a quantity-grouping suggestion is surfaced
- WHEN Compras ignores it
- THEN the underlying PCP records remain unmerged and unmodified
- AND Compras must act manually to request a joint quote

### Requirement: Recent-Price-Reuse Suggestion

The system MUST detect an already-negotiated, still-valid `precios_proveedor` row (`mantenimiento_hasta`
not expired, `activa = true`) for an article and surface it as a reference when a PCP renglón for that
article is opened.

#### Scenario: Valid recent price is surfaced as a reference

- GIVEN a `precios_proveedor` row for article A has `activa = true` and an unexpired
  `mantenimiento_hasta`
- WHEN a PCP renglón for article A is opened
- THEN the system surfaces that row's supplier, date, `mantenimiento_hasta`, and quantity band as a
  reference

#### Scenario: Expired price is not surfaced as valid

- GIVEN a `precios_proveedor` row for article A has an expired `mantenimiento_hasta`
- WHEN a PCP renglón for article A is opened
- THEN the system does not surface that row as a currently valid reference

### Requirement: Comercial Feedback Loop — Email Phase

The system MUST email the closed PCP's result PDF to the requesting Comercial user's mailbox when a
PCP transitions to `cerrada`, while the legacy system remains the system of record.

#### Scenario: Closing a PCP emails the result to the requesting user

- GIVEN a PCP originated from a presupuesto raised by Comercial user U
- WHEN the PCP transitions to `cerrada`
- THEN the system emails the closed PCP's result PDF to U's mailbox

### Requirement: Comercial Feedback Loop — Internal Notification and Auto-Repricing Phase

The system MUST support, once `presupuestacion` is the system of record, sending an internal
notification (via the existing `services/presupuestacion/notificaciones/` type system) that the PCP is
ready, AND MUST automatically trigger repricing of the still-open originating presupuesto for the
affected renglones, as a new automatic invocation path alongside the existing manual
`POST /procesos/{id}/generar-presupuesto` action.

#### Scenario: Closing a PCP notifies internally

- GIVEN `presupuestacion` is the system of record and a PCP originated from an open presupuesto
- WHEN the PCP transitions to `cerrada`
- THEN the system emits an internal notification that the PCP is ready

#### Scenario: Closing a PCP triggers automatic repricing

- GIVEN the originating presupuesto is still open when its PCP closes
- WHEN the PCP transitions to `cerrada`
- THEN the system automatically triggers repricing for the affected renglones
- AND this automatic trigger does not require a manual call to
  `POST /procesos/{id}/generar-presupuesto`

#### Scenario: Closing a PCP for an already-closed presupuesto skips repricing

- GIVEN the originating presupuesto is no longer open when its PCP closes
- WHEN the PCP transitions to `cerrada`
- THEN the system does not attempt automatic repricing
- AND the internal notification is still emitted
