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
- [~] T3 Phase 3 — Backend: export service/router + plan lock (D7) + integration tests.
- [ ] T4 Phase 4 — Backend: `GET /compromisos-entregas`.
- [ ] T5 Phase 5 — Frontend: export button.
- [ ] T6 Phase 6 — Frontend: commitments agenda.
- [ ] T7 Phase 7 — docker-compose + full verification + sample CSV for Sistemas.

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
