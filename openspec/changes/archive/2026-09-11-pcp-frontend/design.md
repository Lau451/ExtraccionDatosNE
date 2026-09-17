# Design: PCP Frontend

## Technical Approach

Mostly-consumer React feature mirroring `features/terceros/`: one typed client (`lib/api/pcp.ts`) over `presupuestacionFetch`, one `roles.ts`, screen components under `features/pcp/`, file-based routes under `routes/_authenticated.pcp*.tsx`, plus one `Sidebar.tsx` nav entry. No loaders, no shared-file refactor beyond the nav item.

**Capability ownership of "Cerrar PCP"**: the close action belongs to the Gestión capability alone. `POST /pcp/{id}/cerrar` is called from exactly one place — `CerrarPcpDialog.tsx`, mounted by `PcpDetalle.tsx`. The Negociación capability (`ComparacionProveedoresTable.tsx`, `RegistrarResultadoDialog.tsx`) renders no close control and never calls `cerrarPcp`, even though the endpoint is served by the backend `negociacion` router. Backend router ownership and frontend capability ownership deliberately differ here.

One backend slice is in scope (proposal, Modified Capabilities): a persisted, non-exclusive `pcp_renglon_resultados.seleccionado` flag, its PATCH endpoint, and one aggregate read for the "Negociado" badge. It is confined to `supabase/migrations/0014_*` and `services/pcp/negociacion/**` — no other `services/` file is touched — and ships as its own PR before the frontend that consumes it.

## Component / File Tree

| File | Action | Capability |
|---|---|---|
| `frontend/src/lib/api/pcp.ts` | Create | all 7 |
| `features/pcp/roles.ts` | Create | all |
| `features/pcp/queryKeys.ts` | Create | all |
| `features/pcp/GestionPcp.tsx` (+`.test.tsx`) | Create | gestion |
| `features/pcp/CrearPcpDialog.tsx` | Create | gestion |
| `features/pcp/PcpDetalle.tsx` (+`.test.tsx`) | Create | gestion, renglones |
| `features/pcp/EstadoPcpStepper.tsx` | Create | gestion |
| `features/pcp/CerrarPcpDialog.tsx` | Create | gestion |
| `features/pcp/GestionCatalogoProveedores.tsx` (+`.test.tsx`) | Create | catalogo |
| `features/pcp/AgregarProveedorProductoDialog.tsx` | Create | catalogo |
| `features/pcp/CrearRenglonDialog.tsx` | Create | renglones |
| `features/pcp/RenglonDetalle.tsx` (+`.test.tsx`) | Create | renglones |
| `features/pcp/SeleccionProveedoresSection.tsx` | Create | renglones |
| `features/pcp/ComparacionProveedoresTable.tsx` (+`.test.tsx`) | Create | negociacion |
| `features/pcp/RegistrarResultadoDialog.tsx` | Create | negociacion |
| `features/pcp/AgruparConsultaDialog.tsx` | Create | consultas |
| `features/pcp/ConsultaDetalle.tsx` (+`.test.tsx`) | Create | consultas |
| `features/pcp/SugerenciasPanel.tsx` (+`.test.tsx`) | Create | sugerencias |
| `features/pcp/ImportLegacyPcp.tsx` (+`.test.tsx`) | Create | legacy-import |
| `routes/_authenticated.pcp.tsx` | Create | layout `beforeLoad: requireRole(...PCP_READ_ROLES)` + `Outlet` |
| `routes/_authenticated.pcp.index.tsx` | Create | `GestionPcp` |
| `routes/_authenticated.pcp.catalogo.tsx` | Create | `GestionCatalogoProveedores` |
| `routes/_authenticated.pcp.imports.tsx` | Create | `ImportLegacyPcp` |
| `routes/_authenticated.pcp.$pcpId.tsx` | Create | `PcpDetalle` |
| `routes/_authenticated.pcp.$pcpId.renglones.$renglonId.tsx` | Create | `RenglonDetalle` |
| `routes/_authenticated.pcp.consultas.$consultaId.tsx` | Create | `ConsultaDetalle` |
| `features/shell/Sidebar.tsx` | Modify | role-gated "PCP" item |
| `supabase/migrations/0014_pcp_renglon_resultado_seleccionado.sql` (+`.down.sql`) | Create | backend slice |
| `services/pcp/negociacion/models.py` | Modify | backend slice |
| `services/pcp/negociacion/repository.py` | Modify | backend slice |
| `services/pcp/negociacion/service.py` | Modify | backend slice |
| `services/pcp/negociacion/router.py` | Modify | backend slice |

## `lib/api/pcp.ts` Contract

Types mirror the Pydantic `*Out`/`*Create` models 1:1. `Decimal` → `number` (FastAPI JSON-encodes Decimal as float). Signatures:

```ts
listarPcp(f?: {estado?: EstadoPcp; fecha_desde?: string; fecha_hasta?: string}): Promise<Pcp[]>
crearPcp(p: PcpCreatePayload): Promise<Pcp>            // POST /pcp
obtenerPcp(id): Promise<Pcp>                            // GET /pcp/{id}
cambiarEstadoPcp(id, estado: EstadoPcp): Promise<Pcp>   // PATCH /pcp/{id}/estado
cerrarPcp(id): Promise<Pcp>                             // POST /pcp/{id}/cerrar
listarProveedoresProducto(productoId): Promise<ProductoProveedor[]>
agregarProveedorProducto(productoId, p: ProductoProveedorCreatePayload): Promise<ProductoProveedor>
listarRenglones(pcpId): Promise<PcpRenglon[]>
crearRenglon(pcpId, p: PcpRenglonCreatePayload): Promise<PcpRenglon>
obtenerDetalleRenglon(pcpId, renglonId): Promise<RenglonDetalle>
seleccionarProveedores(pcpId, renglonId, proveedor_ids: string[]): Promise<ResultadoNegociacion[]>
obtenerResultado(pcpId, renglonId, proveedorId): Promise<ResultadoNegociacion>   // 404 when none
registrarResultado(pcpId, renglonId, proveedorId, p: RegistrarResultadoPayload): Promise<ResultadoNegociacion>
actualizarSeleccion(pcpId, renglonId, proveedorId, seleccionado: boolean): Promise<ResultadoNegociacion>
listarRenglonesSeleccionados(pcpId): Promise<string[]>   // GET /pcp/{id}/seleccion
agruparConsultas(p: AgruparConsultaPayload): Promise<Consulta[]>   // one per distinct proveedor
obtenerConsulta(id): Promise<Consulta>
descargarPdfConsulta(id): Promise<Blob>
enviarConsulta(id): Promise<Consulta>
importarPcpLegacy(filas: FilaImportPcpLegacy[]): Promise<ImportPcpLegacyResultado[]>
```

`PcpRenglonCreatePayload` is exactly `{item_proceso_id: string; origen?: OrigenRenglon; regla_pcp_id?: string}` — the backend model sets `extra="forbid"`, so the type carries no extra key and callers must never spread a form object into it. The 422 body is FastAPI's validation shape (`detail` is an array), so `presupuestacionFetch` produces `ApiError` with a non-string `message`; `crearRenglon` normalizes it into a single readable message before rethrowing, and `CrearRenglonDialog` renders it inline.

`descargarPdfConsulta` cannot use `presupuestacionFetch` (it calls `response.json()`); it duplicates the auth-header fetch and returns `response.blob()`.

## Query Keys and Cache Strategy

`features/pcp/queryKeys.ts` centralizes keys (new vs. the ad-hoc inline arrays in `terceros`, justified by cross-component cache merging):

```
['pcp']                                            list (filters appended)
['pcp', pcpId]                                     one PCP
['pcp', pcpId, 'seleccion']                        renglón ids with >=1 seleccionado (Negociado badge)
['pcp', pcpId, 'renglones']                        renglón list
['pcp', pcpId, 'renglones', renglonId]             renglón detail
['pcp', pcpId, 'renglones', renglonId, 'resultado', proveedorId]
['pcp', 'sugerencias', renglonId, 'agrupacion' | 'precios-recientes']
['pcp', 'catalogo', 'productos', productoId, 'proveedores']
['pcp', 'consultas', consultaId]
```

Ordinary mutations invalidate (terceros pattern). Two mutations deviate.

**`cerrarPcp` merges instead of invalidating.** It is owned by the Gestión capability and is triggered from `CerrarPcpDialog` only (mounted by `PcpDetalle`); no negociación component holds this mutation. Its `onSuccess(pcpActualizado)` writes `setQueryData(['pcp', pcpId], pcpActualizado)` and patches the matching row inside `['pcp']` via `setQueriesData`, so the authoritative closed state cannot be reverted by an already-in-flight stale GET. Cascaded resources it does not return are handled separately: renglón/negociación keys under `['pcp', pcpId, 'renglones']` are marked stale with `invalidateQueries({refetchType: 'none'})` (refetch on next mount, never racing the merge), and the read-only `['pcp','sugerencias']` subtree is invalidated normally since a stale suggestion is harmless. Because `CerrarPcpDialog` unmounts with `PcpDetalle`, this merge never has to reconcile with a mounted comparison table.

**`actualizarSeleccion` merges the returned row and invalidates only the aggregate.** `onSuccess(resultadoActualizado)` writes `setQueryData(['pcp', pcpId, 'renglones', renglonId, 'resultado', proveedorId], resultadoActualizado)` — the exact key the comparison table's `useQueries` fan-out already reads (D4), never a parallel one — and then `invalidateQueries({queryKey: ['pcp', pcpId, 'seleccion']})` with a normal refetch, because that aggregate is derived server-side and would otherwise render a stale "Negociado" badge. The refetch is one flat request, not a fan-out, so D3's race concern does not apply. No `onMutate` optimistic write (D11).

## Routing and Data Ownership

```
_authenticated.pcp  (requireRole PCP_READ_ROLES, Outlet)
├── .index                     GestionPcp        → useQuery ['pcp', filtros]
├── .catalogo                  Catálogo          → productos + ['pcp','catalogo',...]
├── .imports                   ImportLegacyPcp   → mutation only
├── .$pcpId                    PcpDetalle        → ['pcp',id] + [...,'renglones'] + [...,'seleccion']
│   └── .renglones.$renglonId  RenglonDetalle    → detalle + resultados + sugerencias
└── .consultas.$consultaId     ConsultaDetalle   → ['pcp','consultas',id]
```

No route exposes a `loader`: every route component reads `Route.useParams()` (child routes receive `pcpId` and `renglonId` merged) and every byte of data is fetched by a live `useQuery` in the component. `RenglonDetalle` takes `pcpId`/`renglonId` as props from its route component, exactly like `TerceroDetalle`.

## Comparison Table

`ComparacionProveedoresTable({pcpId, renglonId, proveedores, puedeEscribir})` renders **one column per proveedor, one row per criterion** (proveedor, resultado, precio unitario, cantidad mín./máx., mantenimiento hasta, condición/forma de pago, motivo, acción). Columns come from `RenglonDetalle.proveedores_catalogados` (the `ProductoProveedor` rows); each column's cell values come from that proveedor's `ResultadoNegociacion`. Since the backend exposes results only one proveedor at a time, the component fans out with `useQueries` — one query per proveedor — and treats `ApiError.status === 404` as "not selected yet / no result" rather than an error. `no_cotiza` columns render the motivo and no price.

**Selection is persisted, non-exclusive, and server-backed (D9').** A write-role user clicks a column header to toggle that proveedor's `seleccionado` flag; the control calls `actualizarSeleccion` (real PATCH), never `useState`. Current state is read from each column's already-fetched `ResultadoNegociacion.seleccionado` — no extra query. Visual treatment stays as before (accent-tinted column plus a tag) but the vocabulary drops "preferido"/"ganador": the tag reads **"Seleccionado"** and the control is labelled **"Seleccionar proveedor" / "Quitar selección"**, because N columns can be tinted at once and the flag is a sourcing decision, not a score or a winner. While the PATCH is in flight the toggle is disabled and shows a pending state (D11). A 404 column (no `pcp_renglon_resultados` row yet) renders no toggle at all — selection requires a row created by `seleccionar_proveedores`.

Explicit loading, empty (no catalogued proveedor), and error states are required. Below the `md` breakpoint the table is replaced by a stacked card list, one card per proveedor, each carrying the same toggle. **This component renders no close-PCP control** and does not import `cerrarPcp`; closing lives only in `CerrarPcpDialog` under Gestión.

## Persisted `seleccionado` — Backend Slice

**Migration `0014_pcp_renglon_resultado_seleccionado.sql`** (in-file comments in Spanish, matching 0011–0013). Structure: the same `DO $$ ... server_version_num < 150000 ... RAISE EXCEPTION` PG15 guard as 0011/0013; then

```sql
ALTER TABLE pcp_renglon_resultados
  ADD COLUMN IF NOT EXISTS seleccionado BOOLEAN NOT NULL DEFAULT false;
COMMENT ON COLUMN pcp_renglon_resultados.seleccionado IS '...multimarca: NO exclusivo...';
CREATE INDEX IF NOT EXISTS idx_ppr_renglon_seleccionado
    ON pcp_renglon_resultados (pcp_renglon_id) WHERE seleccionado;
NOTIFY pgrst, 'reload schema';
```

Deliberately a **plain partial index, not a `UNIQUE` one** — the contrast with `uq_ppv_preferido` in 0011 (`producto_proveedores.preferido`, unique per producto) is the whole point: that flag is exclusive, this one is not. No new `GRANT` and no new policy: the column inherits table-level grants, and `ppr_upd` (0011 M5) already allows UPDATE for `admin`/`gerencia`/`compras`. `.down.sql` drops the index then the column, plus `NOTIFY pgrst`.

**Backend (`services/pcp/negociacion/`)**

| Layer | Change |
|---|---|
| `models.py` | New `ActualizarSeleccionNegociacion(BaseModel)` with `model_config = ConfigDict(extra="forbid")` and one field `seleccionado: bool`. `ResultadoNegociacionOut` gains `seleccionado: bool` (the frontend reads current state from it). `RegistrarResultadoNegociacion` is untouched — its `_validar_campos_segun_resultado` never sees this field. |
| `repository.py` | `actualizar_seleccion(client, *, pcp_renglon_id, proveedor_id, seleccionado) -> dict \| None` — a `.update({"seleccionado": ...}).eq(...).eq(...)`, **not** an upsert: `drogueria_id` is `NOT NULL` and `ck_ppr_resultado` must hold, so a partial upsert would fail; a row always pre-exists from `seleccionar_proveedores`. Plus `listar_pcp_renglon_ids_seleccionados(client, *, pcp_renglon_ids) -> list[str]` (`select("pcp_renglon_id").in_(...).eq("seleccionado", True)`). |
| `service.py` | `actualizar_seleccion(client, *, drogueria_id, pcp_renglon_id, proveedor_id, seleccionado, usuario_id)` — validates tenant/existence via `renglones_service.obtener_renglon` (same reuse as `registrar_resultado`), raises `NotFoundError` when the repo returns `None` (same message shape as `obtener_resultado`), writes one `historial_service.agregar_evento` (D12). `listar_renglones_seleccionados(client, *, pcp_id, drogueria_id, es_superadmin)` calls `renglones_service.listar_renglones` then the repo `in_` query — two flat round trips regardless of renglón count. Both get `*_para_endpoint` service_role wrappers, per the module convention. |
| `router.py` | `PATCH /pcp/{pcp_id}/renglones/{renglon_id}/proveedores/{proveedor_id}/seleccion` → `ResultadoNegociacionOut`, `require_roles(*ROLES_ESCRITURA_PCP)`, via the `*_para_endpoint` wrapper (mirrors `registrar_resultado_endpoint`). `GET /pcp/{pcp_id}/seleccion` → `list[str]`, `require_roles(*ROLES_LECTURA_PCP)` + `Depends(get_user_client)` + `_es_superadmin(usuario)` (mirrors `obtener_resultado_endpoint` / `listar_renglones_endpoint`). |

**Negociado badge data flow**

```
PcpDetalle ──useQuery ['pcp',id,'renglones']──→ GET /pcp/{id}/renglones      (N rows)
           └─useQuery ['pcp',id,'seleccion']──→ GET /pcp/{id}/seleccion      (string[])
                                                   │
                     badge = seleccion.includes(renglon.id)   ← O(1) per row, 1 request

ComparacionProveedoresTable ─toggle→ PATCH .../seleccion ─┬→ setQueryData(resultado key)
                                                          └→ invalidate ['pcp',id,'seleccion']
```

## Role Gating

`features/pcp/roles.ts` replicates `services/pcp/roles.py` verbatim: `PCP_READ_ROLES = ['superadmin','admin','gerencia','compras']`, `PCP_WRITE_ROLES = ['admin','gerencia','compras']`, plus the local `puedeRol` helper (copied, per the terceros/productos precedent). Three independent layers: the `Sidebar.tsx` item is appended only when `puedeRol(perfil?.rol, PCP_READ_ROLES)` (it must not sit in the unconditional `NAV_ITEMS`, unlike Productos/Terceros, because PCP excludes `lider_comercial`/`comercial`); the `_authenticated.pcp.tsx` layout applies `beforeLoad: requireRole(...PCP_READ_ROLES)` and each nested route repeats it (the `terceros.$terceroId` precedent); and every write control receives `puedeEscribir = puedeRol(perfil?.rol, PCP_WRITE_ROLES)` and is not rendered when false.

## Architecture Decisions

| # | Decision | Alternative rejected | Rationale |
|---|---|---|---|
| D1 | No route loaders; `useQuery` only | `ensureQueryData` loaders (research S4) | Router context holds only `auth`; adding `queryClient` means editing `__root.tsx` + router creation — shared-file risk for zero benefit. Zero loaders exist today, and S4's real warning (never consume via `useLoaderData` alone) is satisfied by construction. |
| D2 | `cerrarPcp` merges response, no blanket invalidate | `invalidateQueries(['pcp'])` | Documented stale-overwrite race (S5); server returns the authoritative `PcpOut`. |
| D3 | Cascaded keys invalidated with `refetchType: 'none'` | Full invalidation / ignoring them | Closes the research gap: server cascades touch resources the response omits, but an immediate refetch reintroduces D2's race. |
| D4 | Comparison results via `useQueries` fan-out, 404 = empty | Adding a backend list-results endpoint | N is bounded by catalogued proveedores for one renglón, and the fan-out is confined to a single mounted renglón screen. The backend budget in this change is spent on D9'/D10, which are load-bearing for the badge across N renglones; this one is not. |
| D5 | Shared `queryKeys.ts` (deviates from terceros) | Inline literal arrays | D2/D3 require the exact same key from mutation and component; a typo would silently no-op the merge. |
| D6 | Consultas reachable only by id from renglón/PCP flow | A consultas index screen | No list endpoint exists in `services/pcp/consultas/router.py`. |
| D7 | Catálogo screen sources productos/proveedores from existing clients | New PCP-side lookup | `lib/api/productos.ts` and `listarTerceros` already cover it; catálogo endpoints are keyed by `producto_id` only. |
| D8 | `PCP_*_ROLES` duplicated in TS, not generated | Codegen from Python | Matches the documented `Rol` duplication in `AuthContext.tsx`. |
| ~~D9~~ | **Superseded by D9'.** Originally: winner selection as component-local, non-persisted state. | — | Overturned after mockup review: the user requires the selection to survive reload and to be re-toggled as supplier answers arrive over days, neither of which component state can do. |
| D9' | Persisted, non-exclusive `pcp_renglon_resultados.seleccionado BOOLEAN NOT NULL DEFAULT false` + PATCH endpoint | (a) client-only state (old D9); (b) a new `pcp_renglon_seleccion` table; (c) an exclusive `ganador_proveedor_id` on `pcp_renglones` | (a) cannot survive reload. (b) `pcp_renglon_resultados` already has exactly one row per `(pcp_renglon_id, proveedor_id)` under `uq_ppr_renglon_prov`, so a boolean there is already per-pair and independently togglable — a second table would duplicate that key for one bit. (c) a single FK column is structurally exclusive, which contradicts the multi-brand/assurance requirement. Still **not** a score or a winner: no ranking rule exists, and this flag does not gate `cerrar_pcp`. |
| D10 | "Negociado" badge fed by a new flat `GET /pcp/{pcp_id}/seleccion` returning `string[]` of renglón ids | (a) add an aggregated boolean to `listar_renglones`; (b) compute client-side from per-renglón resultado queries | Verified: `renglones/repository.py::listar_renglones` is a bare `select("*")` on `pcp_renglones` with no join to resultados, so (a) is a real change to `services/pcp/renglones/**` — outside the proposal's "negociacion only" boundary — and would push a negociación concern into the renglones read model. (b) is an N×M fan-out on every Detalle mount. The new endpoint is 2 flat queries, lives in `negociacion`, and adds no field to any existing response. Path is `/pcp/{id}/seleccion`, **not** `/pcp/{id}/renglones/seleccionados`: `renglones_router` is mounted before `negociacion_router` in `services/pcp/router.py`, so the latter would be shadowed by `GET /pcp/{pcp_id}/renglones/{renglon_id}`. |
| D11 | Selection toggle merges the PATCH response on success; no `onMutate` optimistic flip | Optimistic update with rollback | The request is a single fast PATCH, and an optimistic flip that later fails would briefly assert a sourcing commitment that was never persisted. Disabling the toggle during `isPending` gives the same perceived responsiveness without that failure mode, and the merge reuses D2's already-justified pattern. |
| D12 | Selection toggle logs `tipo_evento='resultado_registrado'` with payload `{proveedor_id, seleccionado}` | (a) a new `proveedor_seleccionado` event type; (b) no historial event | (a) `ck_pcph_tipo_evento` (0012 M-historial) is a closed CHECK; widening it needs a second DROP+ADD CONSTRAINT migration, beyond this change's one-additive-column budget. (b) would leave a real negotiation decision untracked in an append-only log. The payload key distinguishes it from a price/`no_cotiza` record (which carries `resultado`), and D6's "never a raw cost/price field in the payload" invariant still holds. |

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit | `puedeRol` on the 6 roles; `no_cotiza` cell rendering; 422 message normalization | Vitest, pure functions |
| Component | Each screen's loading/empty/error/rendered states; write controls absent for read-only roles; toggling a column calls `actualizarSeleccion` (not local state); **two** columns tinted simultaneously; `ComparacionProveedoresTable` renders no close-PCP control | Testing Library, mocked `lib/api/pcp` (`GestionTerceros.test.tsx` pattern) |
| Contract | `crearRenglon` sends exactly the 3 `extra=forbid` keys; `actualizarSeleccion` sends exactly `{seleccionado}` | Assert `fetch` body |
| Cache | `cerrarPcp` `onSuccess` writes `['pcp', id]` and does not refetch renglón keys; selection `onSuccess` writes the existing `resultado` key and invalidates `['pcp', id, 'seleccion']` | `QueryClient` in test, inspect cache |
| Backend (pytest) | PATCH sets/clears `seleccionado`; two proveedores selected at once on one renglón; toggling a `no_cotiza` row needs no price field; unknown pair → 404; read-only role → 403; `GET /pcp/{id}/seleccion` returns only renglones with ≥1 selection | Existing `tests/pcp/` router+service patterns |
| Migration | `.sql` then `.down.sql` applied in sequence leave the schema unchanged; default is `false` for pre-existing rows | Applied against the test project |
| E2E | Full loop | Out of scope — no E2E harness in `frontend/` |

## Threat Matrix

N/A — no shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. "Routing" here is client-side TanStack Router registration, not process or repository routing.

## Migration / Rollout

One additive migration, `0014_pcp_renglon_resultado_seleccionado.sql`. It adds a column with a non-null default and one partial index; it drops nothing, rewrites no existing value, and changes no existing endpoint signature, so the archived `pcp-negociacion` contract keeps holding unchanged while it is applied.

Ordering is a hard dependency: **the backend PR (migration + `services/pcp/negociacion/**`) merges and the migration is applied before** the frontend PR that consumes `actualizarSeleccion` / `listarRenglonesSeleccionados`. Applied with the same MCP `apply_migration` path as 0011–0013. Rollback of the backend slice is `0014_*.down.sql` (drop index, drop column), safe at any point because nothing outside this change's own endpoint and UI reads or writes the column. Frontend rollback stays a plain PR revert plus the single `Sidebar.tsx` entry.

## Open Questions

- [ ] Confirm that `useQueries` fan-out width stays acceptable for renglones with many catalogued proveedores; if it does not, a backend list endpoint becomes a separate change.
- [ ] Whether `cerrar_pcp` should eventually require or report on `seleccionado` (today it does neither, per D9'); that is a business rule for a later change, not this one.

Closed by this revision: whether the "preferred supplier" highlight needed persistence (yes — D9', backed by a real column and endpoint), and how the "Negociado" badge is sourced without a per-renglón fan-out (D10).
