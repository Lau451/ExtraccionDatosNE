# OC matching export warning: review follow-ups

## Objective

Close the non-blocking findings of RDD review `review-cc07581d41a90d6f` (PR #91). User approved
2026-10-12. Finding "partial export mark -> 500" discarded: `ck_oc_exportacion` (migration 0032)
forces the three `exportado_*` columns to be all null or all set (TEST: 2 exported, 0 partial).

## Tasks

- [x] T1 Backend: `MatchingOut.exportacion` without default, so a constructor that forgets it fails.
- [x] T2 Frontend: tests for the undo/discard gate, dialog close on success, error kept on failure,
  stale error reset; share `fechaLegible` between ExportarProgress.tsx and OcMatchingDetalle.tsx.

## Evidence

(per task: commit, checks observed)

- T1 — commit `682ad8c`. Only two constructors (service.py:554, :606), both pass the field. No
  meaningful RED (refactor of a default). Verifier: tests/oc_presupuesto 84 passed, tests/oc_entregas 63
  passed.
- T2 — commit `4f2561a`. 5 new dialog tests + lib/fechas.test.ts; they test existing behaviour, so
  no RED. Mutation check instead: commenting out the `reset()` calls in `solicitar` first survived (the
  stale-error test reopened with a different mutation); fixed the test to repeat the same action, then the
  mutation fails 'un error de un intento anterior no reaparece al abrir el diálogo de nuevo'. Restored
  (sha256 match). vitest oc-matching + oc-entregas + lib: 16 files / 144 tests passed; tsc and oxlint clean.
