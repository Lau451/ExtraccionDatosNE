# PCP UI Gestión Specification

## Purpose

Provide the frontend list, creation, detail, and state-transition screens for PCP headers, backed
by the `gestion` router, gated by the roles in `services/pcp/roles.py`, expose the nav item that is
this domain's entry point, and host the only close-PCP action in the whole frontend.

## Requirements

### Requirement: Role-Gated Navigation Item

The system MUST show the "PCP" nav item only to users whose role is in `superadmin`, `admin`,
`gerencia`, or `compras`, and MUST NOT render it for any other role, following the same pattern as
the existing Usuarios/Empresas nav items.

#### Scenario: Nav item visible to a read role

- GIVEN a user with role `compras`
- WHEN the shell renders the sidebar
- THEN the "PCP" nav item is shown and links to the PCP list

#### Scenario: Nav item hidden for an unauthorized role

- GIVEN a user with a role outside `superadmin`, `admin`, `gerencia`, `compras`
- WHEN the shell renders the sidebar
- THEN the "PCP" nav item is not rendered
- AND navigating directly to a PCP route redirects the user away

### Requirement: PCP List with Filters

The system MUST list PCPs with filters by `estado` and requested delivery date range, visible to
every read-role user.

#### Scenario: Filter the list by estado

- GIVEN PCPs exist in multiple states
- WHEN the user filters by `en_gestion`
- THEN only PCPs in `en_gestion` are shown

### Requirement: PCP Creation and Detail Gated by Write Role

The system MUST let write-role users create a PCP from an eligible presupuesto and view its detail
with header, renglones summary, and current state, and MUST NOT render create actions for a
read-only role.

#### Scenario: Write role creates a PCP

- GIVEN a write-role user (`admin`, `gerencia`, or `compras`) selects an eligible presupuesto
- WHEN they submit the create-PCP form
- THEN the system calls `POST /pcp` and navigates to the new PCP's detail

#### Scenario: Read-only role cannot see create actions

- GIVEN a user with role `superadmin` (read-only for PCP, per `roles.py`)
- WHEN they view the PCP list or detail
- THEN no create action is rendered

### Requirement: State Transition Control

The system MUST render the current `estado` as a discrete per-stage stepper and MUST let a
write-role user trigger only the next sequential transition
(`nueva` → `en_gestion` → `esperando_respuesta` → `cerrada`).

#### Scenario: Advance to the next state

- GIVEN a PCP in `nueva` viewed by a write-role user
- WHEN they trigger the transition action
- THEN the system calls `PATCH /pcp/{id}/estado` and the stepper updates to `en_gestion`

#### Scenario: Skipping a state is not offered

- GIVEN a PCP in `nueva`
- WHEN the write-role user views transition controls
- THEN only the `en_gestion` transition is offered, never `esperando_respuesta` or `cerrada`
  directly

#### Scenario: Read-only role cannot trigger a transition

- GIVEN a read-only-role user views a PCP detail
- WHEN the screen renders
- THEN no transition control is shown, only the current state

### Requirement: Close-PCP Cascade with Non-Destructive Cache Merge

The system MUST let a write-role user trigger `POST /pcp/{id}/cerrar` only from the PCP Detalle
screen, whose response cascades server-side to PDF, email, historial, and repricing, and MUST
merge the server's returned PCP into the local cache in `onSuccess` rather than invalidating and
refetching all PCP queries, to avoid a stale-overwrite flash. No other screen in the frontend
(including Negociación) MUST render a close-PCP action.

#### Scenario: Close a PCP after negotiation results are captured

- GIVEN a PCP with negotiation results recorded for its renglones, viewed on its Detalle screen
- WHEN the write-role user triggers the close action
- THEN the system calls `POST /pcp/{id}/cerrar`
- AND on success merges the returned PCP into the cache directly, without a blanket
  `invalidateQueries()` refetch

#### Scenario: Close action hidden from read-only role

- GIVEN a read-only-role user views a PCP eligible for closing on its Detalle screen
- WHEN the screen renders
- THEN no close action is shown

#### Scenario: Close action not offered outside Detalle

- GIVEN a write-role user is on the Negociación screen for a PCP eligible for closing
- WHEN the screen renders
- THEN no close-PCP action is shown there; the user must navigate to the Detalle screen to close it

### Requirement: Negociado Badge in Renglones Summary

The system MUST show a "Negociado" badge next to a renglón in the PCP Detalle's renglones summary
once at least one of its suppliers has `seleccionado=true`, and MUST otherwise show that renglón as
pending/not-yet-negotiated.

#### Scenario: Renglón shows Negociado after a supplier is selected

- GIVEN a renglón with no supplier marked `seleccionado`
- WHEN a write-role user marks at least one supplier as `seleccionado` on that renglón in
  Negociación
- THEN the renglones summary on the Detalle screen shows a "Negociado" badge for that renglón

#### Scenario: Renglón without any seleccionado supplier stays pending

- GIVEN a renglón with recorded negotiation results but no supplier marked `seleccionado`
- WHEN the Detalle screen's renglones summary renders
- THEN that renglón shows a pending/not-yet-negotiated indicator, not the "Negociado" badge
