# OC export to Progress + delivery commitments

## Objective

Export a planned purchase order (OC) with its delivery schedule as a CSV file into the server folder shared with Progress 9.1D, record the export, lock the plan, and show exported pending deliveries in a read-only commitments agenda for Compras.

## Source of truth

- `openspec/changes/oc-export-progress/proposal.md` (approved 2026-10-10, commit `4c25a22`)
- `openspec/changes/oc-export-progress/design.md` and `tasks.md` (approved, commit `028d0ae`)

## Constraints

- Strict TDD where a runnable test applies. Backend: `venv/Scripts/python -m pytest <tests> -q`. Frontend: `npx vitest run`, `npx tsc -b --noEmit` in `frontend/`.
- The parent applies migrations to the TEST Supabase project (`grnamollopxdlstcpxhc`) after verifying the MCP project URL matches `.env` `SUPABASE_URL`. Writers only write SQL files and mirror `docs/schema/extractor_final.sql`.
- feature-branch-chain: tracker `feat/oc-export-progress` → `dev`; one branch per phase. Push/PR/merge are the user's decisions.

## Tasks

- [x] T1 Phase 1 — Schema: migration 0032 (export columns, partial index, `v_compromisos_entregas`) + down + snapshot; applied and verified in TEST.
- [ ] T2 Phase 2 — Backend: config + `filas.py` + `escritor.py` (unit tests).
- [ ] T3 Phase 3 — Backend: export service/router + plan lock (D7) + integration tests.
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
