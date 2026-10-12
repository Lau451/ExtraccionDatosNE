# OC matching export warning: review follow-ups

## Objective

Close the non-blocking findings of RDD review `review-cc07581d41a90d6f` (PR #91). User approved
2026-10-12. Finding "partial export mark -> 500" discarded: `ck_oc_exportacion` (migration 0032)
forces the three `exportado_*` columns to be all null or all set (TEST: 2 exported, 0 partial).

## Tasks

- [ ] T1 Backend: `MatchingOut.exportacion` without default, so a constructor that forgets it fails.
- [ ] T2 Frontend: tests for the undo/discard gate, dialog close on success, error kept on failure,
  stale error reset; share `fechaLegible` between ExportarProgress.tsx and OcMatchingDetalle.tsx.

## Evidence

(per task: commit, checks observed)
