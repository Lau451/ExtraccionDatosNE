# Tasks: PCP Frontend

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 2,500–3,400 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | Backend selection persistence → Gestión → Catálogo → Renglones → Negociación → Consultas → Sugerencias → Imports |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

The forecast includes one migration and backend endpoint, the typed client and route/nav foundation, seven UI capabilities, colocated Vitest coverage, pytest integration coverage, and build/test validation. Under `ask-on-risk`, choose chained delivery or explicitly accept a size exception before apply; do not infer either choice.

## Work-Unit Boundaries

| Work unit | Start | Finish and verification | Rollback boundary |
|---|---|---|---|
| Backend prerequisite | Existing PCP negotiation API | Persisted selection PATCH and aggregate GET pass focused pytest | Revert `0014_*` migration pair and changes under `services/pcp/negociacion/` |
| Gestión | Backend prerequisite available | PCP list/detail/state/close, roles, routes, and nav pass Vitest | Revert PCP foundation, Gestión routes/components, and Sidebar entry |
| Catálogo | Gestión foundation available | Product-supplier association screen passes Vitest | Revert catalog screen/dialog/route only |
| Renglones | Catálogo API and Gestión detail available | Renglón create/detail/supplier selection passes Vitest | Revert renglón components and nested route only |
| Negociación | Backend prerequisite and renglón detail available | Comparison and persisted multi-select pass Vitest | Revert negotiation components only |
| Consultas | Renglón flow available | Grouping/detail/PDF/send flow passes Vitest | Revert consultation components and route only |
| Sugerencias | Renglón detail available | Read-only suggestions panel passes Vitest | Revert suggestions panel and its query usage only |
| Imports | Gestión foundation available | Idempotent import feedback passes Vitest | Revert import screen and route only |

## 1. Backend selection-persistence prerequisite

### 1.1 RED

- [x] Add failing focused service and router scenarios in `tests/pcp/negociacion/test_service.py` and `tests/pcp/negociacion/test_router.py` for default `seleccionado=false`, PATCH set/clear, two selected providers on one renglón, `no_cotiza` selection without price fields, unknown pair 404, write-role 403, and aggregate `GET /pcp/{pcp_id}/seleccion`; verify with `pytest tests/pcp/negociacion/test_service.py tests/pcp/negociacion/test_router.py`; rollback by reverting only these new scenarios. <!-- sdd-owner: implementation -->

### 1.2 GREEN

- [x] Create `supabase/migrations/0014_pcp_renglon_resultado_seleccionado.sql` and `.down.sql` with the established PostgreSQL-version guard, additive non-exclusive `seleccionado BOOLEAN NOT NULL DEFAULT false`, partial index, comments, and schema reload notification; verify the up/down pair leaves no column or index behind and pre-existing result rows read `false`; rollback with the paired down migration. <!-- sdd-owner: implementation -->
- [x] Implement the selection contract in `services/pcp/negociacion/models.py`, `repository.py`, `service.py`, and `router.py`: add the output field and strict PATCH body, update only an existing result row, preserve tenant checks and historial event shape, expose the write PATCH plus read-role aggregate GET, and use the module's service-role endpoint wrappers; verify the RED tests advance past their missing-contract failures; rollback only the four negotiation-module files. <!-- sdd-owner: implementation -->

### 1.3 TRIANGULATE and REFACTOR

- [x] Extend the focused backend cases to prove aggregate results include each renglón once when one or more providers are selected and exclude unselected rows, then run the two negotiation test modules against the integration test project; rollback by reverting the added edge-case tests. <!-- sdd-owner: implementation -->
- [x] Refactor the new negotiation helpers only after focused tests pass, retaining the two-flat-query aggregate and no-upsert rule; verify `pytest tests/pcp/negociacion/test_service.py tests/pcp/negociacion/test_router.py`; rollback by reverting the helper-only diff without changing the migration. <!-- sdd-owner: implementation -->

## 2. Gestión foundation and PCP lifecycle

### 2.1 RED

- [x] Create failing role, API-contract, sidebar, list, and detail/cache tests in `frontend/src/features/pcp/roles.test.ts`, `frontend/src/lib/api/pcp.test.ts`, `frontend/src/features/pcp/GestionPcp.test.tsx`, and `frontend/src/features/pcp/PcpDetalle.test.tsx` covering the four read roles, three write roles, nav/direct-route denial, filters, creation, sequential state changes, close-only-on-detail, and the Negociado/pending badge data contract; verify with `cd frontend && npm run test -- src/features/pcp/roles.test.ts src/lib/api/pcp.test.ts src/features/pcp/GestionPcp.test.tsx src/features/pcp/PcpDetalle.test.tsx`; rollback by reverting only the new tests. <!-- sdd-owner: implementation -->

### 2.2 GREEN

- [x] Create `frontend/src/lib/api/pcp.ts`, `frontend/src/features/pcp/roles.ts`, and `frontend/src/features/pcp/queryKeys.ts` with typed Gestion and shared PCP contracts, exact centralized keys, read/write role constants, and `puedeRol`; use the existing authenticated fetch convention and preserve the dedicated binary-fetch path for later PDF support; verify API and role RED tests pass; rollback the three additive files. <!-- sdd-owner: implementation -->
- [x] Create the Gestión routes `frontend/src/routes/_authenticated.pcp.tsx`, `_authenticated.pcp.index.tsx`, and `_authenticated.pcp.$pcpId.tsx`, add the role-gated PCP entry to `frontend/src/features/shell/Sidebar.tsx`, and repeat the PCP read-role guard on nested routes; verify unauthorized navigation is rejected and the sidebar is hidden outside PCP read roles; rollback the PCP route files and single Sidebar entry. <!-- sdd-owner: implementation -->
- [x] Implement `frontend/src/features/pcp/GestionPcp.tsx`, `CrearPcpDialog.tsx`, `PcpDetalle.tsx`, `EstadoPcpStepper.tsx`, and `CerrarPcpDialog.tsx` with loading/empty/error states, write-control absence, discrete next-only transitions, renglón summary links, and close action mounted only from `PcpDetalle`; verify the Gestion and detail component tests pass; rollback those Gestión components only. <!-- sdd-owner: implementation -->

### 2.3 TRIANGULATE and REFACTOR

- [x] Add cache-focused cases proving `cerrarPcp` merges its returned PCP into `['pcp', pcpId]` and list rows, marks renglón keys stale with `refetchType: 'none'`, normally invalidates suggestions, and never performs a blanket PCP refetch; verify with the Gestión/detail Vitest command; rollback the added cache cases. <!-- sdd-owner: implementation -->
- [x] Refactor Gestión query and mutation helpers to consume only `queryKeys.ts` and retain the one-location close control; verify focused Vitest plus `cd frontend && npm run build`; rollback the Gestión-only refactor. <!-- sdd-owner: implementation -->

## 3. Catálogo

### 3.1 RED

- [x] Create failing `frontend/src/features/pcp/GestionCatalogoProveedores.test.tsx` cases for populated and empty product catalogs, write-role association creation and refresh, hidden read-only control, and surfaced duplicate conflict; verify with `cd frontend && npm run test -- src/features/pcp/GestionCatalogoProveedores.test.tsx`; rollback the new test file. <!-- sdd-owner: implementation -->

### 3.2 GREEN

- [x] Extend `frontend/src/lib/api/pcp.ts` with typed catalog endpoints, then implement `frontend/src/features/pcp/GestionCatalogoProveedores.tsx`, `AgregarProveedorProductoDialog.tsx`, and `frontend/src/routes/_authenticated.pcp.catalogo.tsx` using existing product and tercero clients for lookups; invalidate the precise product-provider key after a successful association; verify the catalog RED cases pass; rollback the catalog components, route, and catalog-client additions. <!-- sdd-owner: implementation -->

### 3.3 TRIANGULATE and REFACTOR

- [x] Add catalog tests for changing the chosen product and for an API conflict that leaves the current list unchanged, then run the focused Vitest file and `cd frontend && npm run build`; rollback only the added catalog edge cases. <!-- sdd-owner: implementation -->
- [x] Refactor catalog form state and query use without broad invalidation or duplicated role checks; verify the focused catalog test command; rollback the catalog-only refactor. <!-- sdd-owner: implementation -->

## 4. Renglones

### 4.1 RED

- [x] Create failing `frontend/src/features/pcp/RenglonDetalle.test.tsx` and extend `frontend/src/lib/api/pcp.test.ts` for renglón creation with exactly `item_proceso_id`, optional `origen`, and optional `regla_pcp_id`, normalized FastAPI 422 feedback, enriched product/supplier detail, multi-provider selection, and absent read-only controls; verify with `cd frontend && npm run test -- src/features/pcp/RenglonDetalle.test.tsx src/lib/api/pcp.test.ts`; rollback the renglón test additions. <!-- sdd-owner: implementation -->

### 4.2 GREEN

- [x] Add typed renglón/detail/supplier-selection methods and 422-message normalization to `frontend/src/lib/api/pcp.ts`, ensuring no form-object spread can add a forbidden request key; verify the exact-body and validation RED cases pass; rollback the renglón API additions. <!-- sdd-owner: implementation -->
- [x] Implement `frontend/src/features/pcp/CrearRenglonDialog.tsx`, `RenglonDetalle.tsx`, `SeleccionProveedoresSection.tsx`, and `frontend/src/routes/_authenticated.pcp.$pcpId.renglones.$renglonId.tsx`; connect PCP detail to creation/listing and detail navigation, preserving read-only rendering and targeted query invalidation; verify the renglón component tests pass; rollback these components and nested route only. <!-- sdd-owner: implementation -->

### 4.3 TRIANGULATE and REFACTOR

- [x] Add renglón tests for zero catalogued suppliers, partial multi-selection, and server-validation errors rendered inline without silently dropping fields; verify with the focused renglón/API Vitest command; rollback the added edge-case tests. <!-- sdd-owner: implementation -->
- [x] Refactor renglón query ownership so parent detail keeps PCP summary data and child detail owns enriched renglón data; verify focused Vitest and `cd frontend && npm run build`; rollback the renglón-only refactor. <!-- sdd-owner: implementation -->

## 5. Negociación

### 5.1 RED

- [x] Create failing `frontend/src/features/pcp/ComparacionProveedoresTable.test.tsx` cases for loading, no catalogued providers, per-provider 404-as-no-result, `precio_obtenido`, `no_cotiza`, desktop columns, mobile cards, absent read-only mutations, no close control, and two simultaneous selected providers; verify with `cd frontend && npm run test -- src/features/pcp/ComparacionProveedoresTable.test.tsx`; rollback the new comparison test file. <!-- sdd-owner: implementation -->

### 5.2 GREEN

- [x] Extend `frontend/src/lib/api/pcp.ts` with typed result GET/POST and `actualizarSeleccion` PATCH methods, then implement `frontend/src/features/pcp/ComparacionProveedoresTable.tsx` and `RegistrarResultadoDialog.tsx` using a bounded `useQueries` fan-out over catalogued providers and treating only `ApiError.status === 404` as no result; verify comparison RED cases pass; rollback the negotiation components and API additions. <!-- sdd-owner: implementation -->
- [x] Wire `RenglonDetalle.tsx` to the comparison components so write users can register outcomes and toggle the persisted, non-exclusive selection while mutations are pending, with no local selection state and no `cerrarPcp` import; verify the selection-control cases pass; rollback the renglón-detail integration and negotiation components only. <!-- sdd-owner: implementation -->

### 5.3 TRIANGULATE and REFACTOR

- [x] Add QueryClient cases proving `actualizarSeleccion` writes the returned row to the exact existing result key and normally invalidates only `['pcp', pcpId, 'seleccion']`, allowing the Gestión Negociado badge to refresh after navigation; verify focused comparison and Gestión-detail Vitest tests; rollback the added cache tests. <!-- sdd-owner: implementation -->
- [x] Refactor comparison rendering into shared criterion data for table and mobile cards while retaining accessible selected labels and multi-select semantics; verify `cd frontend && npm run test -- src/features/pcp/ComparacionProveedoresTable.test.tsx src/features/pcp/PcpDetalle.test.tsx` and `cd frontend && npm run build`; rollback the comparison-only refactor. <!-- sdd-owner: implementation -->

## 6. Consultas

### 6.1 RED

- [x] Create failing `frontend/src/features/pcp/ConsultaDetalle.test.tsx` and extend `frontend/src/lib/api/pcp.test.ts` for grouping selected renglones into one consultation per provider, read-only hidden grouping/send actions, binary PDF download, and send success/failure feedback without messaging-adapter detail; verify with `cd frontend && npm run test -- src/features/pcp/ConsultaDetalle.test.tsx src/lib/api/pcp.test.ts`; rollback the consultation test additions. <!-- sdd-owner: implementation -->

### 6.2 GREEN

- [x] Add typed consultation grouping/detail/send methods and the auth-header blob download implementation to `frontend/src/lib/api/pcp.ts`, then implement `frontend/src/features/pcp/AgruparConsultaDialog.tsx`, `ConsultaDetalle.tsx`, and `frontend/src/routes/_authenticated.pcp.consultas.$consultaId.tsx`; expose the grouping entry only from eligible PCP/renglón flow and target cache updates to consultation keys; verify consultation RED cases pass; rollback consultation components, route, and API additions. <!-- sdd-owner: implementation -->

### 6.3 TRIANGULATE and REFACTOR

- [x] Add consultation tests for several providers yielding several returned consultations, a PDF fetch failure, and send failure recovery that keeps the action usable; verify focused Vitest and `cd frontend && npm run build`; rollback the added edge-case tests. <!-- sdd-owner: implementation -->
- [x] Refactor download cleanup and mutation feedback without exposing adapter internals or adding a nonexistent consultation index route; verify the focused consultation test command; rollback the consultation-only refactor. <!-- sdd-owner: implementation -->

## 7. Sugerencias

### 7.1 RED

- [x] Create failing `frontend/src/features/pcp/SugerenciasPanel.test.tsx` cases for grouping and recent-price display, no-data state, read-role visibility, and the absence of any PCP mutation control; verify with `cd frontend && npm run test -- src/features/pcp/SugerenciasPanel.test.tsx`; rollback the new suggestions test file. <!-- sdd-owner: implementation -->

### 7.2 GREEN

- [x] Add typed grouping and recent-price reads to `frontend/src/lib/api/pcp.ts`, implement `frontend/src/features/pcp/SugerenciasPanel.tsx`, and mount it in `frontend/src/features/pcp/RenglonDetalle.tsx` with its dedicated query keys and loading/error/empty states; verify the suggestions RED cases pass; rollback the panel and its API/detail integrations. <!-- sdd-owner: implementation -->

### 7.3 TRIANGULATE and REFACTOR

- [x] Add suggestions tests for a valid recent-price row and multiple open-renglón quantity aggregation, then run focused Vitest plus `cd frontend && npm run build`; rollback the added suggestions cases. <!-- sdd-owner: implementation -->
- [x] Refactor suggestions rendering to remain read-only and isolated from renglón mutations; verify the focused suggestions test command; rollback the suggestions-only refactor. <!-- sdd-owner: implementation -->

## 8. Legacy imports

### 8.1 RED

- [x] Create failing `frontend/src/features/pcp/ImportLegacyPcp.test.tsx` cases for write-role import submission, read-only route denial, human-readable result summary, and repeat-import updated-not-duplicated feedback; verify with `cd frontend && npm run test -- src/features/pcp/ImportLegacyPcp.test.tsx`; rollback the new import test file. <!-- sdd-owner: implementation -->

### 8.2 GREEN

- [x] Add the typed legacy-import method to `frontend/src/lib/api/pcp.ts`, implement `frontend/src/features/pcp/ImportLegacyPcp.tsx`, and create `frontend/src/routes/_authenticated.pcp.imports.tsx` with an explicit write-role guard; render result counts/statuses without raw API payloads; verify the import RED cases pass; rollback the import screen, route, and API addition. <!-- sdd-owner: implementation -->

### 8.3 TRIANGULATE and REFACTOR

- [x] Add import tests for mixed created/updated result rows and API failure recovery, then run focused Vitest plus `cd frontend && npm run build`; rollback the added import edge cases. <!-- sdd-owner: implementation -->
- [x] Refactor import result presentation without changing idempotency semantics or broadening route access; verify the focused import test command; rollback the import-only refactor. <!-- sdd-owner: implementation -->

## 9. Cross-unit validation

- [x] Run the frontend PCP suite and production build with `cd frontend && npm run test -- src/features/pcp src/lib/api/pcp.test.ts && npm run build`, resolving only PCP-change failures; rollback by reverting the failing unit at its documented work-unit boundary. <!-- sdd-owner: implementation -->
- [x] Run the backend selection prerequisite and repository-required suite with `pytest tests/pcp/negociacion/test_service.py tests/pcp/negociacion/test_router.py` followed by `pytest --cov=services --cov-report=html`; record any unrelated baseline failures separately rather than modifying unrelated untracked artifacts; rollback only PCP selection-persistence changes if regression is attributable to this change. <!-- sdd-owner: implementation -->

## Task Summary

- 9 dependency-ordered work units: one backend prerequisite followed by Gestión, Catálogo, Renglones, Negociación, Consultas, Sugerencias, Imports, and cross-unit validation.
- Each feature uses RED → GREEN → TRIANGULATE → REFACTOR and names its focused tests, implementation targets, verification command, and independent rollback boundary.
- The backend selection-persistence unit must complete before any frontend unit consumes `actualizarSeleccion` or `listarRenglonesSeleccionados`.
- High review-budget risk requires a human delivery decision under `ask-on-risk`; the proposed autonomous chain follows the requested build order.
