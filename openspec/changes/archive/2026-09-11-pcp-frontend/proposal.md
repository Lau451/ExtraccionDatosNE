# Proposal: PCP Frontend

## Intent

The `gestor-pcp` backend shipped and archived 7 HTTP routers under `services/pcp/`, but no UI consumes them: the whole purchase-consultation loop (create PCP → add renglones → pick suppliers → negotiate → group/send consultations → close) is only reachable via curl/Postman. This change builds the React frontend for that already-stable API, so the domain becomes usable by the compras/gerencia roles.

## Scope

### In Scope
- **Gestión**: PCP list (filters estado/fecha), create, detail (renglones summary shows a "Negociado" badge per renglón, see below), state transitions, close-PCP action (the only place it lives — see Modified Capabilities), role-gated nav item.
- **Renglones**: list/create renglones for a PCP, enriched renglón detail, supplier selection (1..N).
- **Catálogo**: ad-hoc producto↔proveedor association screen.
- **Negociación**: column-per-supplier comparison view, register `precio_obtenido`/`no_cotiza`, mark one or more suppliers per renglón as `seleccionado` (persisted, toggleable, non-exclusive — supports multi-brand sourcing). No close-PCP action here (moved to Gestión, see below).
- **Consultas**: group selected renglones into consultations, detail, PDF download button (`GET /pcp/consultas/{id}/pdf`), "Enviar consulta".
- **Sugerencias**: read-only agrupación + precios-recientes shown as a separate panel inside the renglón detail.
- **Import legado**: dedicated screen for `POST /pcp/imports/legacy`.
- Roles replicated as-is from `services/pcp/roles.py` (4 read / 3 write).

### Out of Scope
- `historial` timeline UI and any new backend endpoint (no backend file is touched).
- Fixing the `lider_comercial`/`comercial` role gap vs. archived `design.md` D11 (pre-existing, tracked separately).
- Any UI warning about the no-op `mensajeria` adapter (backend/ops concern).
- A dedicated `documentos` feature beyond the PDF download button.

## Capabilities

### New Capabilities
- `pcp-ui-gestion`: PCP list/create/detail/state, close action, nav + role gating.
- `pcp-ui-catalogo`: producto↔proveedor association UI.
- `pcp-ui-renglones`: renglón list/detail and supplier selection.
- `pcp-ui-negociacion`: comparison table and negotiation result capture.
- `pcp-ui-consultas`: consultation grouping, detail, PDF, send.
- `pcp-ui-sugerencias`: suggestions panel in renglón detail.
- `pcp-ui-legacy-import`: legacy bulk-import screen.

### Modified Capabilities
- `pcp-negociacion` (backend): adds a persisted, non-exclusive `seleccionado` boolean per renglón×proveedor result (`pcp_renglon_resultados.seleccionado`), toggleable at any time, plus a PATCH endpoint to set it. Decided mid-change: the earlier draft used a client-only "preferred" UI hint (design.md D9), but the user confirmed the selection must survive reloads and change as new supplier responses come in over time — that requires backend storage. This is the same category of gap as `historial` (needs a backend touch) but small enough, and requested explicitly, to fold into this change rather than defer.

## Approach

Follow existing `frontend/` conventions exactly, mirroring `features/terceros/`:

| Screen | Backend router | Key endpoints |
|---|---|---|
| Gestión | `gestion` | `POST/GET /pcp`, `GET /pcp/{id}`, `PATCH /pcp/{id}/estado` |
| Catálogo | `catalogo` | `GET/POST /pcp/catalogo/productos/{id}/proveedores` |
| Renglones | `renglones` | `POST/GET .../renglones`, `POST .../proveedores` |
| Negociación | `negociacion` | `POST/GET .../resultado`, `PATCH .../seleccion` (new) |
| Gestión (cierre) | `negociacion` | `POST /pcp/{id}/cerrar` (moved here from the Negociación endpoint table — same endpoint, now triggered only from the Detalle screen) |
| Consultas | `consultas` | `POST /pcp/consultas`, `GET .../{id}`, `.../pdf`, `.../enviar` |
| Sugerencias | `sugerencias` | `GET .../agrupacion`, `.../precios-recientes` |
| Import legado | `imports` | `POST /pcp/imports/legacy` |

Technical direction (from research):
- Comparison views use column-per-supplier / row-per-criterion tables with a highlighted selected column, plus explicit loading/empty/error states and a non-tabular mobile fallback.
- `estado` rendered as a discrete per-stage stepper, not free text.
- Nested TanStack Router segments `/pcp/$pcpId/renglones/$renglonId`, parent PCP context inherited; loaders are thin `ensureQueryData` triggers consumed via live `useQuery`.
- Close-PCP mutation merges the server response in `onSuccess` instead of blanket `invalidateQueries()` (avoids the documented stale-overwrite race).

### Suggested build order (for sdd-tasks)

`gestion → catalogo → renglones → negociacion → consultas → sugerencias → imports`

Adjusted from exploration: **catálogo moves ahead of renglones** because renglón supplier selection consumes catalogued producto↔proveedor rows, and the catalog endpoints are keyed by `producto_id` only, so that screen is buildable with no PCP dependency. `gestion` must be first (it establishes `lib/api/pcp.ts`, `roles.ts`, routes, nav). `sugerencias` is unblocked once renglón detail exists and may be reordered. `imports` depends only on the gestión foundation and can ship last or in parallel.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `frontend/src/lib/api/pcp.ts` | New | Typed client over `presupuestacionFetch` for the 7 routers |
| `frontend/src/features/pcp/` | New | `roles.ts`, gestión/detalle/dialogs/comparison components + colocated tests |
| `frontend/src/routes/_authenticated.pcp*.tsx` | New | Layout + index + nested `$pcpId` / `$renglonId` routes with `requireRole` |
| `frontend/src/features/shell/Sidebar.tsx` | Modified | One role-gated nav item (Usuarios/Empresas pattern) |
| `supabase/migrations/0014_*.sql` (+ `.down.sql`) | New | Adds `pcp_renglon_resultados.seleccionado BOOLEAN NOT NULL DEFAULT false` |
| `services/pcp/negociacion/{models,service,repository,router}.py` | Modified | New `seleccionado` field + PATCH endpoint |
| `services/pcp/negociacion/roles.py` reuse | Untouched | Same read/write roles as the rest of `negociacion` |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| PR review budget overflow (7 screens ≈ backend size) | High | sdd-tasks forecasts chained PRs, one per build-order unit |
| Stale-overwrite flash on close-PCP cascade | Med | `onSuccess` cache merge, no blanket invalidation |
| `POST .../renglones` uses `extra=forbid`; wrong payload shape → 422 | Med | Type the request from `PcpRenglonCreate` exactly; contract test |
| Nav item visible to roles that `requireRole` rejects | Med | Gate the nav item explicitly, do not rely on route guard alone |
| "Enviar consulta" appears to work but delivers nothing | Med | Accepted by decision; backend/ops concern, documented only here |
| New `seleccionado` column/endpoint regresses the archived `pcp-negociacion` backend spec | Med | Additive-only migration (new nullable-safe boolean, default `false`); new endpoint only, no existing endpoint signature changes; backend PR gets its own `sdd-apply`/`sdd-verify` pass before the frontend PR that consumes it |

## Rollback Plan

Frontend units are additive and isolated under `frontend/src/features/pcp/`, `lib/api/pcp.ts`, and `routes/_authenticated.pcp*.tsx` — reverting those PRs plus the `Sidebar.tsx` nav entry needs no data cleanup. The one exception is the `seleccionado` migration: rollback there is the paired `0014_*.down.sql` (drops the column), safe at any point since nothing else reads or writes it outside this change's own endpoint and UI.

## Dependencies

- `services/pcp` reachable through `VITE_PRESUPUESTACION_API_URL` (already mounted in `services/presupuestacion/main.py`).
- Existing Supabase JWT auth wrapper and `requireRole` route guard.
- Real `mensajeria` adapter (`PCP_MENSAJERIA_ADAPTER`) for actual delivery — external to this change.

## Success Criteria

- [ ] A compras/gerencia user completes the full loop in the UI: create PCP → add renglones → associate suppliers → select suppliers → register results → group and send a consultation → close the PCP.
- [ ] All 7 in-scope screens render, gated by the 4 read / 3 write roles from `services/pcp/roles.py`.
- [ ] The nav item is hidden for roles outside `READ_ROLES`.
- [ ] Consultation PDF downloads from the detail view.
- [ ] Marking a proveedor `seleccionado` on a renglón survives a page reload, and the renglón shows a "Negociado" badge in the Detalle summary once at least one proveedor is `seleccionado`.
- [ ] Multiple proveedores can be simultaneously `seleccionado` on the same renglón.
- [ ] "Cerrar PCP" is reachable only from the Detalle screen, nowhere else.
- [ ] Vitest + Testing Library tests colocated for every new screen, suite green.
- [ ] Backend changes limited to `services/pcp/negociacion/**` and one additive migration — no other `services/` files touched.
