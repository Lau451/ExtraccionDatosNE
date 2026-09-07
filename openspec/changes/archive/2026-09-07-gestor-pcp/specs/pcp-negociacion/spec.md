# PCP Negociación Specification

## Purpose

Record the outcome of a supplier negotiation for a PCP renglón into `precios_proveedor`, its first
real writer, covering both a priced outcome and the explicit "cannot quote" outcome, while guaranteeing
that recording never leaks into other renglones or into product costing.

## Requirements

### Requirement: Negotiation Result Recording

The system MUST allow recording a negotiation result for a renglón-supplier pair, capturing price,
supplier, conditions, `mantenimiento_hasta`, payment terms, and notes, scoped to that renglón's
`item_proceso_id`.

#### Scenario: Record a priced negotiation result

- GIVEN a renglón with proveedor P selected for negotiation
- WHEN Compras records a price, `mantenimiento_hasta` date, payment terms, and notes for P on that
  renglón
- THEN the system writes one `precios_proveedor` row scoped to that renglón's `item_proceso_id`
- AND the row reflects proveedor P, the price, and all captured conditions

#### Scenario: Record payment terms via catalog FKs

- GIVEN existing `condiciones_pago` and `formas_pago` entries for the drogueria
- WHEN Compras records payment terms for a negotiation result
- THEN the result references those entries via `condicion_pago_id` and `forma_pago_id`
- AND no free-text or raw-integer payment term is stored

### Requirement: no_cotiza as a First-Class Outcome

The system MUST support recording `no_cotiza` (supplier out of stock or unable to quote) as a distinct
outcome type, separate from and not requiring a price value.

#### Scenario: Record a no_cotiza outcome

- GIVEN a renglón with proveedor P selected for negotiation
- WHEN Compras records that P responded `no_cotiza`
- THEN the system stores the outcome as `no_cotiza` for that renglón-proveedor pair
- AND no price value is required or stored

#### Scenario: no_cotiza does not block other suppliers on the same renglón

- GIVEN a renglón has proveedores P and Q selected
- WHEN P's outcome is recorded as `no_cotiza`
- THEN Compras can still record a priced outcome for Q on the same renglón

### Requirement: Negotiation Result Isolation Invariant

The system MUST NOT modify `costos_productos`, or the `precios_proveedor` rows of any other renglón,
when recording a negotiation result for a given `item_proceso_id`.

#### Scenario: Recording a result leaves product costing untouched

- GIVEN a product's `costos_productos` row has a stable cost value
- WHEN Compras records a negotiation result for a PCP renglón of that product
- THEN the `costos_productos` row remains unchanged

#### Scenario: Recording a result leaves other renglones untouched

- GIVEN two renglones, A and B, referencing the same product but different `item_proceso_id` values
- WHEN a negotiation result is recorded for renglón A
- THEN renglón B's `precios_proveedor` rows are unaffected

### Requirement: Validity Window via mantenimiento_hasta

The system MUST treat a recorded price as valid only while `mantenimiento_hasta` has not elapsed and
the row is marked `activa`.

#### Scenario: Expired maintenance window is not considered valid

- GIVEN a `precios_proveedor` row with `mantenimiento_hasta` in the past
- WHEN the row's validity is evaluated
- THEN the system treats it as expired, not as a currently valid price
