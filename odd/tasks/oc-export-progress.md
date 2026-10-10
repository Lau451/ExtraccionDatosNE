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

- [ ] T1 Phase 1 — Schema: migration 0032 (export columns, partial index, `v_compromisos_entregas`) + down + snapshot; applied and verified in TEST.
- [ ] T2 Phase 2 — Backend: config + `filas.py` + `escritor.py` (unit tests).
- [ ] T3 Phase 3 — Backend: export service/router + plan lock (D7) + integration tests.
- [ ] T4 Phase 4 — Backend: `GET /compromisos-entregas`.
- [ ] T5 Phase 5 — Frontend: export button.
- [ ] T6 Phase 6 — Frontend: commitments agenda.
- [ ] T7 Phase 7 — docker-compose + full verification + sample CSV for Sistemas.

## Evidence

(per task: branch, commit, checks observed)
