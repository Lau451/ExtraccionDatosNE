# Etapa 5 — roles y permisos centralizados (X-ARQ-005)

Stage 5 of docs/arquitectura/README.md: endpoints and screens check named capabilities declared once in `services/shared`, not role tuples written in each module. Behavior does not change: each current tuple becomes one capability with the same roles.
Branch `feat/roles-capacidades` from `dev` (`82a8fc7`). No migrations.

## Specs

- **S1** Matrix in code (L3 "vamos con la a"): new `services/shared/permisos.py` holds the only role → capability matrix (`MATRIZ: dict[str, frozenset[str]]`), plus `tiene_capacidad(rol, capacidad)` and `capacidades_de(rol)`. An unknown capability raises an error (never silently denies or allows). The DB-backed matrix (`rol_capacidades` table) is a later stage, recorded in the docs.
- **S2** One capability per action (L2 Q4 "Una capacidad por acción"): every current backend tuple and inline `require_roles(...)` becomes its own capability with exactly the same roles, even when two tuples are identical today. Frontend-only lists that differ from their API tuple (e.g. compromisos screen without `superadmin`) get their own capability.
- **S3** `require_capacidad("x.y")` dependency in `services/shared/auth.py`: 403 "No tenés permisos para esta acción" when the user's role lacks it — same message and status as `require_roles` today.
- **S4** Endpoint for the frontend (L2 Q2 "Endpoint /me/capacidades"): `GET /auth/capacidades` (presupuestacion) returns the sorted capabilities of the caller's role. Blocked with a pending password change like any endpoint (L5); the frontend treats that as no capabilities and reloads them after the change. Every endpoint still re-checks.
- **S5** Backend migration: no module outside `services/shared` calls `require_roles` or defines a role tuple used for authorization. `usuarios/service.py` uses `tiene_capacidad` for "who manages users". Out of scope, unchanged: tenancy checks `rol != "superadmin"` (cross-droguería access), the user-hierarchy rules of `usuarios/service.py` (`ROLES_GESTIONABLES_POR_GERENCIA`, who may assign which role), and notification recipients (`_ROLES_NOTIFICACION_REEMPLAZO`).
- **S6** Architecture test in `tests/arquitectura/` fails if a file outside `services/shared` calls `require_roles` or defines a module-level `*ROLES*` tuple passed to an authorization check.
- **S7** Frontend: `AuthContext` loads the capabilities with the profile and exposes `puede(capacidad)`; route guards use `requireCapacidad(...)`; the per-feature `roles.ts` lists are removed. Same visible behavior per role.
- **S8** RLS out of scope (L2 Q3 "Fuera de esta etapa"): `docs/schema/rls_final.sql` keeps its own role lists. Docs: README stage 5 done, X-ARQ-005 resolved, `plataforma-comun.md` notes the matrix lives in code for now.

## Tasks

- **T1** S1-S3: `services/shared/permisos.py` + `require_capacidad`, unit tests — inline — commit:
- **T2** S4: `GET /auth/capacidades` + test — inline — commit:
- **T3** S2, S5: migrate pcp, terceros, productos, integracion_progress, extraccion — inline — commit:
- **T4** S2, S5: migrate presupuestacion routers and usuarios service — inline — commit:
- **T5** S6: architecture test — inline — commit:
- **T6** S7: frontend capabilities — inline — commit:
- **T7** S8: docs — inline — commit:

## Log

- **L1** (user, 2026-11-08): "vamos con la 5"
- **L2** (user, 2026-11-08) answers: Q1 matrix location "decime ventajas y desventajas de cada uno"; Q2 "Endpoint /me/capacidades (Recomendado)"; Q3 RLS "Fuera de esta etapa (Recomendado)"; Q4 "Una capacidad por acción (Recomendado)".
- **L3** (user, 2026-11-08): "vamos con la a" (matrix in code, `services/shared`).
- **L4** (evidence): explore found 48 named tuples + 6 inline `require_roles` in 27 backend files, 10 frontend `roles.ts`; no `plataforma/` package — the platform layer is `services/shared/` (D-ARQ-003).
- **L5** (decision, 2026-11-08): `GET /auth/capacidades` is not a new exit of the pending-password lock (S3 of login-usuario-alta-admin; `tests/auth/test_flag_sweep.py` pins the only exits). While pending, the frontend already sends the user to `/cambiar-password`.
