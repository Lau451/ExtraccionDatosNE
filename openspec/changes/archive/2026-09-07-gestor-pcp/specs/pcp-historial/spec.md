# PCP Historial Specification

## Purpose

Provide a dedicated, append-only audit trail of PCP and renglón management actions, kept as its own
table rather than extending the existing closed 5-entity `historial_cambios` / `EntidadAuditable`
model.

## Requirements

### Requirement: Dedicated PCP History Table

The system MUST record PCP management actions in a history structure dedicated to the PCP module and
MUST NOT extend the existing `EntidadAuditable` Literal or write PCP events into `historial_cambios`.

#### Scenario: PCP event is not written to historial_cambios

- GIVEN a PCP state transition occurs
- WHEN the event is recorded
- THEN it is written to the PCP-dedicated history structure
- AND no row is added to `historial_cambios`

### Requirement: Recorded Action Coverage

The system MUST record, at minimum, PCP state changes, negotiation results recorded per renglón, and
supplier consultas sent, each with enough context to identify the affected PCP or renglón, the acting
user, and a timestamp.

#### Scenario: State change is recorded

- GIVEN a PCP transitions from `en_gestion` to `esperando_respuesta`
- WHEN the transition completes
- THEN a history entry records the PCP, the old and new state, the acting user, and the timestamp

#### Scenario: Negotiation result is recorded

- GIVEN Compras records a priced or `no_cotiza` outcome for a renglón
- WHEN the outcome is saved
- THEN a history entry records the renglón, the outcome, the acting user, and the timestamp

#### Scenario: Consulta send is recorded

- GIVEN a grouped consulta is sent to a proveedor
- WHEN the send completes
- THEN a history entry records the consulta, the proveedor, and the timestamp

### Requirement: Append-Only Immutability

The system MUST NOT allow editing or deleting an existing PCP history entry through the API.

#### Scenario: Reject editing a history entry

- GIVEN a PCP history entry already exists
- WHEN a request attempts to modify that entry
- THEN the system rejects the request
- AND the entry remains unchanged

#### Scenario: Reject deleting a history entry

- GIVEN a PCP history entry already exists
- WHEN a request attempts to delete that entry
- THEN the system rejects the request
