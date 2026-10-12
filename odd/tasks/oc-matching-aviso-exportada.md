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

- [ ] T1 Backend: `exportacion` block in `MatchingOut` (oc_presupuesto) + tests.
- [ ] T2 Frontend: banner + confirmation before mutations when exported + tests.

## Evidence

(per task: commit, checks observed)
