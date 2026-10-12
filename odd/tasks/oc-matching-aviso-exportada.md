# OC matching: warn when the OC was already exported to Progress

## Objective

The matching screen keeps allowing edits after the OC was exported to Progress (design D7 of
`oc-export-progress` only locked the delivery plan). The exported CSV is built from each OC row's
`producto_id`, `precio_unitario` and link state, so any later matching change silently diverges from
Progress. User decision 2026-10-12: keep matching editable, but warn.

## Scope

- Backend: `MatchingOut` gains `exportacion: ExportacionOut | None` (same shape as the delivery plan
  GET, including `exportado_por_nombre`). Every endpoint returning `MatchingOut` carries it.
- Frontend: when `exportacion` is present, a persistent amber banner on the matching screen, and a
  `ConfirmDialog` before each confirm / undo / discard mutation. Nothing is blocked.

## Non-goals

- No DB guard, no 409, no audit row for post-export matching edits.
- No re-export flow.

## Tasks

- [x] T1 Backend: `exportacion` block in `MatchingOut` (oc_presupuesto) + tests.
- [x] T2 Frontend: banner + confirmation before mutations when exported + tests.

## Evidence

(per task: commit, checks observed)

- T1 — commit `2cffeda`. RED: 4 new tests in tests/oc_presupuesto/test_service.py failed with
  `AttributeError: 'MatchingOut' object has no attribute 'exportacion'`. GREEN: tests/oc_presupuesto 84
  passed, tests/oc_entregas 63 passed, tests/oc_export 61 passed (run per directory). `armar_exportacion`
  moved to `oc_entregas/models.py` (oc_entregas.service already imports oc_presupuesto.service).
  FK hint checked against TEST: OC 986 -> exportado_por_nombre 'Laureano Maidana'.
- T2 — commit `585b787`. RED: 3 of 4 new tests in OcMatchingDetalle.test.tsx failed (banner, dialog
  gates the API call, cancel does not call it); the null-exportacion test passed as expected (current
  behaviour). GREEN (verifier): vitest src/features/oc-matching src/lib/api 13 files / 91 tests passed;
  tsc -b --noEmit clean; oxlint clean. Parent fix: reset stale mutation errors before reopening the dialog.
  routeTree.gen.ts rewritten by tooling with EOL-only changes; restored.
