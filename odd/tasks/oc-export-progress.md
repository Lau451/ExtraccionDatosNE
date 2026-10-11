# OC export to Progress + delivery commitments

## Objective

Export a planned purchase order (OC) with its delivery schedule as a CSV file into the server folder shared with Progress 9.1D, record the export, lock the plan, and show exported pending deliveries in a read-only commitments agenda for Compras.

## Source of truth

- `openspec/changes/oc-export-progress/proposal.md` (approved 2026-10-10, commit `4c25a22`)
- `openspec/changes/oc-export-progress/design.md` and `tasks.md` (approved, commit `028d0ae`)

## Constraints

- Strict TDD where a runnable test applies. Backend: `venv/Scripts/python -m pytest <tests> -q`. Frontend: `npx vitest run`, `npx tsc -b --noEmit` in `frontend/`.
- The parent applies migrations to the TEST Supabase project (`grnamollopxdlstcpxhc`) after verifying the MCP project URL matches `.env` `SUPABASE_URL`. Writers only write SQL files and mirror `docs/schema/extractor_final.sql`.
- One branch per phase, each branched from `dev` and merged into `dev` via PR (user decision 2026-10-11; T1 merged as PR #82, `a4972ff`). Push/PR/merge are the user's decisions.

## Tasks

- [x] T1 Phase 1 — Schema: migration 0032 (export columns, partial index, `v_compromisos_entregas`) + down + snapshot; applied and verified in TEST.
- [x] T2 Phase 2 — Backend: config + `filas.py` + `escritor.py` (unit tests).
- [x] T3 Phase 3 — Backend: export service/router + plan lock (D7) + integration tests.
- [x] T4 Phase 4 — Backend: `GET /compromisos-entregas`.
- [x] T5 Phase 5 — Frontend: export button.
- [x] T6 Phase 6 — Frontend: commitments agenda (+ T4 follow-up: paginate the unbounded commitments read).
- [x] T7 Phase 7 — docker-compose + full verification + sample CSV for Sistemas.

## Evidence

(per task: branch, commit, checks observed)

### T1

- Branch `feat/oc-export-progress-01-esquema`; commits `c52bee3` (migration 0032 + down + snapshot), `d04679e` (view keeps `en_transito`/`parcial` deliveries, same criterion as `v_entregas_pendientes`; constraint guards scoped by `conrelid`).
- Supabase MCP is read-only (no `apply_migration`, writes fail with 25006), so the user ran the first version of 0032 in the SQL Editor. Verified by read: 3 columns, `ck_oc_exportacion`, `fk_oc_exportadopor`, `idx_oc_exportadas`, view with `security_invoker=true` and 15 columns, `SELECT` returns 0 rows.
- RDD review `review-8901da1eced74219` on `1e36bc4..d04679e`: approved and acknowledged. Advisory, non-blocking: no SQL tests for date boundary / estado filter / all-or-none CHECK (covered by T3/T4 integration tests); single-export invariant enforced in app layer (T3 CAS).
- User re-ran the final 0032 in the SQL Editor (idempotent second run succeeded) and registered it (`20261010120000`). Verified by read: view excludes only `entregada`/`rechazada`, 2 constraints scoped to `ordenes_compra`, 3 columns, index present, view returns 0 rows, migration registered.
- Down + reapply cycle in TEST (user ran both in the SQL Editor; 1 OC, 0 exported, so no data loss). After down, verified by read: 0 columns, 0 constraints, no index, no view. After reapply: 3 columns, 2 constraints, index present, view with 15 columns and `security_invoker=true`, 0 rows, migration `20261010120000` still registered.

### T2

- Branch `feat/oc-export-progress-02-csv-writer` (from `dev` after PR #82). Implemented by `gentle-ai-worker`, reviewed by the parent.
- 2.1 `progress_docs_dir`/`oc_export_encoding` in `services/shared/config.py`; `IntegracionNoConfigurada` mapped to 503 in `STATUS_MAP`.
- 2.2 `oc_export/models.py` + pure `filas.py` (`ENCABEZADOS`, 15 columns per the proposal; `construir_filas` returns data rows only, `ROUND_HALF_UP` to 2 decimals).
- 2.3 `escritor.py`: `carpeta_oc`, `construir_nombre` (injectable timestamp, Buenos Aires time), `escribir_csv` (temp + `os.replace`, temp removed on any failure, `ConflictError` if the target exists).
- RED: both test files failed at collection (modules missing). GREEN: `pytest tests/oc_export -q` 20 passed (re-run by the parent); `pytest tests/oc_entregas tests/shared -m "not integration"` 55 passed.
- Note for T7: with `QUOTE_MINIMAL` only amounts are quoted (`"1520,50"`); integer identifiers are unquoted (`3`). Design D4 accepts this; the proposal wording says "every number quoted". Confirm with Sistemas using the sample CSV.
- Open for T3: `RenglonExport.codigo_articulo` is optional; D2 preconditions should reject a missing article code before building rows.
- Merged into `dev` as PR #83 (`444ebf1`); branch deleted. Commit `06fbf58`. Native review `review-a4229674dfbc4262` on `a4972ff..06fbf58` (reliability lens): approved and acknowledged (authority burned). Advisory, non-blocking, for T3: deliveries whose `oc_item_id` matches no line item are dropped silently (`filas.py:65-68`; D2 should reject or count them); no test pins `ROUND_HALF_UP` (`test_filas.py:67-69`); no-overwrite TOCTOU window (accepted, D6 CAS); naive `ahora`, unvalidated encoding name, embedded newlines in text (suggestions).

### T3

- Branch `feat/oc-export-progress-03-export-service` (from `dev` at `444ebf1`). Implemented by `gentle-ai-worker`, reviewed by the parent.
- 3.1 `oc_export/repository.py` (service client + explicit `drogueria_id` filter, CAS update); `ResultadoExportacion` in `models.py`.
- 3.2 `oc_export/service.py` `exportar_orden_compra`: D2 preconditions accumulated in one 422; D3 with 0/1/2 client codes; D6 compensation deletes the written file when the CAS update fails or hits 0 rows; audit via `registrar_cambio` (an audit failure after the CAS is logged and swallowed, because the file is already handed to Progress); 503 when `progress_docs_dir` is unset.
- 3.3 `oc_export/router.py` `POST /ordenes-compra/{id}/exportar-progress` (`_ROLES_OC`), registered in `main.py`.
- 3.4 D7: planning `PUT` returns 409 once exported; planning `GET` adds the `exportacion` block (and `puede_planificar=False` with a reason).
- 3.5 Integration: `comercial` exports, `compras` 403, second export 409, planning `PUT` after export 409.
- Phase 2 advisories closed: orphan delivery items rejected in D2; line items without `producto_id` or `codigo_interno` rejected in D2 with their `numero_renglon`; `ROUND_HALF_UP` pinned (`0.125` → `0,13`, `2.675` → `2,68`).
- Bug caught in parent review: D2 required every line item to be fully planned, but planning only accepts confirmed line items, so an OC with a discarded line item could never be exported (the integration fixture had masked it by planning the discarded one). Fixed: the export reuses `_clasificar_renglones`/`_derivar_estado`; discarded items are excluded from D2 and the CSV, pending items fail D2, no confirmed items fails D2.
- RED: 21/21 service tests failed against a `NotImplementedError` stub; 3/3 D7 tests failed before the change; 3/3 discarded/pending tests failed before the fix. GREEN: `pytest tests/oc_export tests/oc_entregas -m "not integration"` 93 passed (re-run by the parent); `-m integration` 12 passed against TEST (worker run).
- Known red on `dev`, not caused by T3 alone: `tests/core/test_database.py::test_service_client_no_se_importa_en_ningun_router` fails since `oc_entregas/router.py` (`42a85b5`) and now also lists `oc_export/router.py`. Pending user decision (allowlist vs RLS user client).
- Commit `fd11bbe`. Native review `review-e9aff5918c8d2131` on `444ebf1..fd11bbe` (reliability lens): approved and acknowledged (authority burned). Advisory, non-blocking follow-ups:
  - Ambiguous CAS failure (`oc_export/service.py:271-277`): if the `UPDATE` commits but the response is lost, the file is deleted while the OC stays marked exported. Fix: on exception, re-read the OC and keep the file if it is marked with this `archivo_exportado`.
  - D7 guard is a read-then-write (`oc_entregas/service.py:371-376`): an export racing a re-plan can leave the CSV with the old plan. Needs a DB-level guard (conditional write or trigger).
  - Orphan delivery item message may misreport (`oc_export/service.py:163-167`); swallowed audit failure has no test; GET `exportacion` with null `exportado_por` name; HALF_UP test comment (suggestions).
- Follow-ups (user decisions 2026-10-11: allowlist for the service-client guard; fix both integrity warnings before the PR):
  - `8302643` `tests/core/test_database.py` is now an explicit allowlist (`oc_entregas`, `oc_export`, each justified by explicit `drogueria_id` filtering); stale entries also fail. The guard is green again (it was red on `dev` since `42a85b5`).
  - `6dd2973` migration 0033 (`hash_plan_oc`, `marcar_oc_exportada` RPC with plan-hash CAS returning `ok`/`ya_exportada`/`plan_cambiado`/`no_encontrada`, `trg_oc_exportada_congela_plan` + triggers on `entregas_oc`/`entregas_oc_items` raising `OC409` on plan changes only; real deliveries from `compras.crear_entrega` are not blocked). Ambiguous RPC failure re-reads the OC and keeps the file if already marked with it. Planning maps `OC409` to the D7 409.
  - User applied 0033 in the TEST SQL Editor and registered `20261011120000`. Verified by read: 3 functions, both triggers, trigger function `SECURITY DEFINER`, `authenticated` cannot execute `marcar_oc_exportada`, `service_role` can.
  - Checks (`gentle-ai-verify`): `-m integration` on `tests/oc_export tests/oc_entregas` 18 passed, 0 skipped (6 new `test_cas_plan.py` + 12 existing); `-m "not integration"` incl. `tests/core/test_database.py` 102 passed. Full suite without `tests/extraccion`: 539 passed (worker run).
  - 0033 down + reapply cycle in TEST (user ran both in the SQL Editor; 0 exported OCs). After down: 0 functions, 0 triggers, migration still registered. After reapply: 3 functions, 2 triggers, trigger function `SECURITY DEFINER`, `authenticated` cannot execute `marcar_oc_exportada`/`hash_plan_oc`, `service_role` can. Integration re-run: 18 passed, 0 skipped.
  - Native review `review-a8aa56e116bf04bd` on `d73c15f..130246e` (reliability lens): approved and acknowledged (authority burned). Advisory, non-blocking: planning's `OC409` path is not compensated (by design: the plan is frozen, and a partial plan cannot pass D2 and be exported without a hash mismatch); the trigger's plan/non-plan heuristic and `now()` vs Python timestamp in `marcar_oc_exportada`; integration tests cover INSERT/DELETE/UPDATE rejection but not the allowed real-delivery path; hash format and RPC error mapping suggestions.

### T4

- Branch `feat/oc-export-progress-04-compromisos` (from `dev` at `847b210`, after PR #84). Implemented by `gentle-ai-worker`, reviewed by the parent.
- `06816d8`: new module `services/presupuestacion/compromisos/` with `GET /compromisos-entregas?desde&hasta` (`_ROLES_LECTURA`). Default range: all overdue + today..today+6 months (Buenos Aires time); with only `desde`, `hasta` = `desde` + 6 months; `hasta < desde` or a range over 24 months → 422. Ordered vencida first, then date, OC, delivery, line item. Uses the per-user RLS client (view is `security_invoker`); the service-client allowlist was not extended.
- `7e27eb5`: migration 0034 recreates `v_compromisos_entregas` with `AND ei.cantidad_planificada > 0`, because real deliveries registered by `compras.crear_entrega` (`cantidad_planificada = 0`) showed up as commitments (found by the worker, confirmed by a test). A user without a droguería (superadmin) now gets 422 instead of a query with `drogueria_id = None` (no precedent in other list endpoints).
- RED: 11/13 service tests failed against a stub; the superadmin test failed before the fix; the real-delivery test failed against the 0032 view (`assert 4 not in {1, 2, 4}`).
- RLS verified in integration: admin, gerencia, lider_comercial, comercial and compras read their own droguería only; `sistema` gets 403.
- User applied 0034 in the TEST SQL Editor and registered `20261011130000`. Verified by read: filter present, `security_invoker=true`, 15 columns, `authenticated` can select.
- Checks (`gentle-ai-verify`): `-m integration` on `tests/compromisos tests/oc_export tests/oc_entregas` 31 passed, 0 skipped; `tests -m "not integration" --ignore=tests/extraccion` 553 passed.
- 0034 down + reapply cycle in TEST (user ran both in the SQL Editor; 0 exported OCs, 0 view rows, so no data at risk). After down, verified by read: `cantidad_planificada > 0` filter gone, `security_invoker=true`, 15 columns, `authenticated` can select, migration `20261011130000` still registered. After reapply: filter `(ei.cantidad_planificada > (0)::numeric)` present, same options, columns and grant, migration still registered. Integration re-run on `tests/compromisos tests/oc_export tests/oc_entregas`: 31 passed, 0 skipped.
- Native review `review-8121aeac7d3c5d18` on `dev..74fc801` (reliability lens, 16 files): approved and acknowledged (authority burned). Advisory, non-blocking follow-ups: `repository.py:12-20` reads the view unbounded and unordered (PostgREST `max_rows` could truncate silently before Python sorts); `repository.py:16` drops rows with a null `fecha_entrega_planificada` through the `lte` filter; `service.py:33` orders OC numbers lexically; `test_router.py:74-75` can split across midnight (suggestions).

### T5

- Branch `feat/oc-export-progress-05-boton-export` (from `dev` at `7664569`, after PR #85). Implemented by `gentle-ai-worker`, reviewed by the parent.
- Frontend: `lib/api/ocExport.ts` (`exportarAProgress`), `ExportacionOut` in `lib/api/ocEntregas.ts`, `features/oc-entregas/ExportarProgress.tsx` (button, `ConfirmDialog`, error list, success with file name and row count, exported banner). `PlanificacionEntregas.tsx`: export mutation, `sinGuardar` flag (button disabled with unsaved edits), read-only view when `exportacion` is present.
- Error mapping: 422 `detail` "prefix: err1; err2" shown as a list; 503 "Exportación no disponible"; 409 refetches planning and re-seeds the grid from fresh data (or switches to the exported view); 403 shows the backend message. The button is not hidden by role: the planning screen's roles equal the export roles.
- Backend (user decision: show the exporter's name, not the UUID): `oc_entregas` returns `exportacion.exportado_por_nombre`, resolved with the embed `usuarios!fk_oc_exportadopor(nombre, apellido)` (FK from 0032; hint required by PGRST201). The banner omits "por …" when the name is null; the UUID is never shown.
- RED: the new test suites failed to import (`./ocExport` missing); 5 backend tests (name cases + select string) and 3 frontend tests (409 re-seed, null-name banner, banner fixture) failed before their fixes.
- Checks (`gentle-ai-verify`): `tests -m "not integration" --ignore=tests/extraccion` 558 passed; `-m integration` on `tests/oc_entregas tests/oc_export tests/compromisos` 31 passed; full frontend vitest 45 files / 449 tests passed; `tsc -b` only the known error at `oc-matching/components/ColumnaPresupuesto.test.tsx:147`, confirmed present on `dev` at `7664569` (not caused by T5).
- Embed checked read-only against TEST: `buscar_orden_compra` resolves the hint (no PGRST200/201). The nested `nombre`/`apellido` payload was not observed: TEST has no exported OC.
- Commits: `19e3a96` (backend: exporter name), `8c67546` (frontend button + docs).
- Native review `review-ecc7b3131dc74a43` on `dev..8c67546` (reliability lens, 13 files): approved and acknowledged (authority burned). Advisory, non-blocking: 1 warning at `PlanificacionEntregas.tsx:385` (export button enablement); suggestions at `PlanificacionEntregas.tsx:145-150` and `:234`, `ExportarProgress.tsx:36-52`, `oc_entregas/repository.py:36-39`.

### T6

- Branch `feat/oc-export-progress-06-agenda` (from `dev` at `c04bcb3`, after PR #86). Implemented by `gentle-ai-worker`, reviewed by the parent.
- T4 follow-up (backend): `compromisos/repository.py` reads `v_compromisos_entregas` ordered by `fecha_entrega_planificada, orden_compra_id, numero_entrega, numero_renglon` in `.range()` pages of 500 (below PostgREST's usual `max_rows` of 1000) until a short page, building a fresh query per page. The service-level sort is unchanged.
- Frontend: `lib/api/compromisos.ts`; `features/compromisos/` with the pure `agruparCompromisos` (overdue list with `dias_atraso`, then month and date groups, line items grouped per `entrega_oc_id`, undated deliveries in a final "Sin fecha" group), `Compromisos.tsx` (loading, empty, error, data; OC number links to `/ordenes-compra/$ordenCompraId/entregas`), and `roles.ts`; route `_authenticated.compromisos.tsx` (`routeTree.gen.ts` regenerated, +22 lines); Sidebar item "Compromisos de entrega" for admin, gerencia, lider_comercial, comercial and compras (hidden for superadmin and `sistema`). Dates parsed from `YYYY-MM-DD` without timezone shift. No range control in v1 (backend default range). The disabled "Calendario" placeholder is untouched.
- RED: backend 5 failed / 12 passed (order and pagination tests); frontend new suites failed to import, Sidebar 5 failed ("Compromisos de entrega" link not found).
- Checks (`gentle-ai-verify`): `tests -m "not integration" --ignore=tests/extraccion` 561 passed; `-m integration` on `tests/compromisos tests/oc_export tests/oc_entregas` 31 passed (ordered + paginated read through real PostgREST); full frontend vitest 49 files / 467 tests passed; `tsc -b` only the known error at `ColumnaPresupuesto.test.tsx:147`.
- Commits: `b7518bc` (backend pagination), `2a08fcd` (agenda + docs).
- Native review `review-333296482c972b9a` on `dev..2a08fcd` (reliability lens, 15 files): approved and acknowledged (authority burned). Advisory, non-blocking:
  - Warning `repository.py:9`, the pagination sort key may not be unique. Checked against the TEST schema and not reproducible: `entregas_oc` has `UNIQUE (orden_compra_id, numero_entrega)`, `entregas_oc_items` has `UNIQUE (entrega_oc_id, oc_item_id)`, and `oc_items` has `UNIQUE (orden_compra_id, numero_renglon)` with `numero_renglon NOT NULL`, so `(orden_compra_id, numero_entrega, numero_renglon)` identifies one view row.
  - Suggestions: the generic error fallback is untested (`Compromisos.tsx:65`); the pagination test does not assert filters on every page (`test_repository.py:92-102`).

### T7

- Branch `feat/oc-export-progress-07-despliegue` (from `dev` at `07aa090`, after PR #87).
- 7.1 (parent, inline): `docker-compose.yml`, service `presupuestacion-api`, adds `PROGRESS_DOCS_DIR=C:/app/documentos_ia`, `OC_EXPORT_ENCODING=cp1252` and a writable bind mount `C:/SACPro/documentos_ia:C:/app/documentos_ia`, separate from the read-only output volume (D8). CSVs land in `C:\SACPro\documentos_ia\oc`, and the host folder must exist before `docker compose up`. `docker compose config --quiet` is valid; the `version` obsolete warning was already there. The rollback section in `tasks.md` now lists the downs in reverse order: 0034, 0033, 0032.
- 7.2 (`gentle-ai-verify`): `tests -m "not integration" --ignore=tests/extraccion` 561 passed; `-m integration` on `tests/oc_export tests/oc_entregas tests/compromisos` 31 passed.
- 7.3 (`gentle-ai-verify`): `tsc -b` only the known error at `oc-matching/components/ColumnaPresupuesto.test.tsx:147`; vitest 49 files / 467 tests passed; `npx vite build` succeeded (largest chunk `index` 301.96 kB, 94.98 kB gzip). `npm run build` (`tsc -b && vite build`) fails on that known error, which is on `dev` since `000b346`, not caused by this change. The build rewrote `routeTree.gen.ts` with line-ending changes only (no diff ignoring CR), so it was restored.
- 7.4 (`gentle-ai-worker`, user chose a disposable OC): `scripts/oc_export/generar_muestra.py` creates a synthetic droguería, client, products and OC in TEST (it aborts if `SUPABASE_URL` is not TEST), exports it with the real service, and has a `--limpiar <oc_id>` mode that only removes `MUESTRA-PROGRESS-*` data (it clears the export mark first because of the 0033 trigger). No TDD: throwaway tooling over a real database; verified with a real run plus a create/clean round trip on a second OC (nothing left).
  - Kept sample: OC `2815a5d2-4aeb-4e81-bb25-9353e10cb03c` (`MUESTRA-PROGRESS-008d7865`), droguería `90c8a361-80b3-4d93-8acc-6f0629a60998`, `exportado_at` set in TEST. Clean it with `--limpiar` once Sistemas validates.
  - CSV (outside the repo, synthetic data): `C:\Users\LAUREANO\OneDrive\Escritorio\muestra-progress\oc\OC_MUE008D7_MUESTRA-PROGRESS-008d7865_v1_20261011195648.csv`. 1116 bytes, header + 5 rows, CRLF, no BOM, decodes as cp1252, contains `ñ`, `ú` and an en dash (0x96, cp1252-only). Dates `dd/mm/yyyy`, decimals with comma. `fecha_emision` and `direccion_entrega` are empty in the synthetic OC.
- Native review `review-350da1f4f0ba5f18` on `dev..c78137a` (reliability lens, 5 files): approved and acknowledged (authority burned). Advisory findings:
  - Two warnings on the failure path of `generar_muestra.py`: ids were printed only after the export, and `--limpiar` deleted the user only when `exportado_por` was set. Both fixed in a follow-up commit: the OC id is printed before exporting, and `--limpiar` deletes every user of the synthetic droguería. Verified with a real round trip on a third disposable OC (`fae2a65e-…`): created, exported to a temp folder, cleaned; a read confirmed 0 OC, 0 droguería, 0 users left, and the kept sample is still exported.
  - Suggestion: the destructive guard has no test.
- Follow-up review `review-e0120f2199c36922` on `c78137a..0b8c3fc`: approved and acknowledged (authority burned). Advisory, non-blocking, left open for this throwaway tooling: a warning at `generar_muestra.py:188-193` (the per-user delete loop in `--limpiar`) and two suggestions (`generar_muestra.py:188-190`, `odd/tasks/oc-export-progress.md:120-122`).
