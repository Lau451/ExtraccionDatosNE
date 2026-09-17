# Delta for PCP Negociación

## ADDED Requirements

### Requirement: Persisted Non-Exclusive Supplier Selection

The system MUST support a persisted `seleccionado` boolean on a renglón's negotiation result row
(`pcp_renglon_resultados.seleccionado`, default `false`), scoped per renglón×proveedor pair, MUST
let a write-role user toggle it via a `PATCH` endpoint at any time, and MUST NOT treat it as
exclusive: multiple proveedores on the same renglón MAY simultaneously hold `seleccionado=true`.
Toggling `seleccionado` MUST NOT read, require, or alter the `resultado` field or its existing
`precio_obtenido`/`no_cotiza` validation.

#### Scenario: Mark a proveedor as seleccionado

- GIVEN a renglón-proveedor pair with a recorded negotiation result
- WHEN Compras sets `seleccionado=true` for that pair via the PATCH endpoint
- THEN the system persists `seleccionado=true` on that result row
- AND the value is read back unchanged on a subsequent `GET`

#### Scenario: Toggle seleccionado off and back on

- GIVEN a renglón-proveedor pair currently `seleccionado=true`
- WHEN Compras sets `seleccionado=false`, and later sets it back to `true`
- THEN each change persists independently and the latest value is the one read back

#### Scenario: Multiple proveedores seleccionado on the same renglón

- GIVEN a renglón with proveedores P and Q, each holding a recorded negotiation result
- WHEN Compras sets `seleccionado=true` for both P and Q
- THEN both result rows persist `seleccionado=true` at the same time for that renglón

#### Scenario: Selection is independent of resultado validation

- GIVEN a renglón-proveedor pair recorded with `resultado=no_cotiza`
- WHEN Compras sets `seleccionado=true` for that pair
- THEN the update succeeds without requiring `precio_unitario`, `mantenimiento_hasta`, or any other
  `precio_obtenido`-only field

#### Scenario: New renglones default to not seleccionado

- GIVEN a new negotiation result row is created for a renglón-proveedor pair
- WHEN the row is read before any selection PATCH is sent
- THEN `seleccionado` is `false`
