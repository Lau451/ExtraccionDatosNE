# OC line number as printed on the document

## Objective

Show each purchase-order line with the number printed on the client's document (e.g. 7, 38, 41). Fall back to the positional number (1..N) when the extraction did not detect one.

## Problem

`oc_items.numero_renglon` is a positional ordinal 1..N assigned in `_materializar_orden_compra` (D13.1). `FilaOrdenCompraIn.numero_renglon_documento` is discarded. The matching screen shows no line number in the OC column. The budget column's button says "Vincular al renglón N de la OC" using the positional number, which does not match the paper OC.

## Why D13.1 stays

An OC can be materialized from a group of extractions whose documents repeat line numbers. `numero_renglon` must stay the unique positional key. `tests/.../test_filas_con_mismo_numero_renglon_documento_no_generan_conflicto` protects it. The document number is stored separately, for display only, with no uniqueness.

## Scope

1. Migration `0030_oc_items_numero_renglon_documento`: nullable `TEXT` column on `oc_items`, plus a `.down.sql`.
2. `_materializar_orden_compra` (`services/presupuestacion/extraccion/service.py`) persists `fila.numero_renglon_documento`: trimmed, empty → NULL.
3. OC matching API: `oc_presupuesto` repository selects the column; `RenglonOrdenCompra.numero_renglon_documento: str | None`.
4. Frontend: mirror type. `RenglonOcFila` shows "Renglón {documento ?? numero_renglon}". The `ColumnaPresupuesto` manual-link button uses the same label.
5. Out of scope: backfilling already materialized OCs (they fall back to position).

## Constraints

- TDD: strict. Backend runner: `venv/Scripts/python -m pytest <tests> -q`. Frontend: `npm test` in `frontend/`.
- Keep `numero_renglon` semantics and all D13.1 tests unchanged.
- The parent applies the migration to the TEST Supabase project (the writer only writes the SQL files).

## Tasks

- [x] T0 — Budget column shows "Renglón N" (commit 8a1f923, direct inline).
- [x] T1 — Migration + persist `numero_renglon_documento` at materialization + tests.
  - Commit `baa7638`. Migration `supabase/migrations/0030_oc_items_numero_renglon_documento.sql` (+`.down.sql`), `docs/schema/extractor_final.sql` mirrored. `_materializar_orden_compra` persists `(fila.numero_renglon_documento or "").strip() or None`. Comments in `models.py`/`service.py` updated (no longer "NO se persiste").
  - RED: 4 failures (`KeyError: 'numero_renglon_documento'`) in `tests/extraccion/test_orden_compra.py` before the service.py change. GREEN after: `venv/Scripts/python -m pytest tests/extraccion/test_orden_compra.py -q` → 57 passed.
  - Pending-migration note: `tests/extraccion/test_service.py` has 5 integration tests (`test_validar_orden_compra_*`) that hit the real TEST Supabase project and fail with `PGRST204: Could not find the 'numero_renglon_documento' column of 'oc_items' in the schema cache` until the parent applies 0030 there. Confirmed this is the ONLY failure cause (not a regression).
- [x] T2 — OC matching API returns the field + tests.
  - Commit `4248468`. `oc_presupuesto/repository.py` (`listar_oc_items_completos`, `buscar_oc_item`) select `numero_renglon_documento`; `models.py::RenglonOrdenCompra.numero_renglon_documento: str | None = None`; `service.py::_armar_renglon_oc` passes `item.get("numero_renglon_documento")`.
  - RED: `AttributeError: 'RenglonOrdenCompra' object has no attribute 'numero_renglon_documento'` in the new test before the models.py/service.py change. GREEN after: `venv/Scripts/python -m pytest tests/oc_presupuesto/test_service.py -q` → 69 passed, 2 failed.
  - Same pending-migration cause for the 2 failures: `test_matching_integracion_samco_rafaela_...` / `test_sesion_completa_...` hit the real TEST DB with `column oc_items.numero_renglon_documento does not exist` (42703) — expected until 0030 is applied there.
- [x] T3 — Frontend label with fallback in OC column and manual-link button + tests.
  - `frontend/src/lib/api/ocMatching.ts::RenglonOrdenCompra.numero_renglon_documento: string | null`. New shared helper `frontend/src/features/oc-matching/etiquetaRenglonOc.ts` (+ `.test.ts`). `RenglonOcFila.tsx` shows "Renglón {etiqueta}" above the description. `ColumnaPresupuesto.tsx` manual-link button uses the same helper instead of the positional `numero_renglon`. Updated the three `RenglonOrdenCompra` test fixtures (`RenglonOcFila.test.tsx`, `ColumnaPresupuesto.test.tsx`, `OcMatchingDetalle.test.tsx`) with `numero_renglon_documento: null` so `tsc` passes.
  - RED: `etiquetaRenglonOc.test.ts` failed to resolve the not-yet-created module; `RenglonOcFila.test.tsx`/`ColumnaPresupuesto.test.tsx` new tests failed (`getByText('Renglón 4')` not found / wrong button label) before the component changes. GREEN after: `npx vitest run src/features/oc-matching` → 6 files, 33 passed.

## Acceptance criteria

- Materializing an OC whose rows carry "38" stores `numero_renglon_documento = '38'` while `numero_renglon` stays 1..N.
- Rows without a document number store NULL, and the screen shows the positional number.
- Two grouped documents with the same printed number still materialize without conflict.

## Checks

- `venv/Scripts/python -m pytest tests/oc_presupuesto -q` and the extraction/orden_compra test files
- `npm test`, `npx tsc --noEmit -p .`, `npx oxlint src/features/oc-matching` in `frontend/`

## Route

- T1–T3: delegated direct (writer trigger: migration + backend + frontend, 2+ non-trivial files).

## Progress

- Branch `feat/oc-matching-numero-renglon` from `dev` @ c2cadef.

## Parent verification

- Migration 0030 applied to the TEST project (`grnamollopxdlstcpxhc`) via Supabase MCP `apply_migration`.
- `pytest tests/oc_presupuesto tests/extraccion/test_orden_compra.py tests/extraccion/test_service.py -q` → 199 passed (the integration failures reported as pending-migration are gone).
- Browser on OC 986: without document numbers → "Renglón 1..7", button "Vincular al renglón 5". After setting OC 986's document numbers from its extraction CSV (TEST DB, data-only) → "Renglón 7, 16, 27, 4 (fallback, extraction had none), 38, 40, 41", button "Vincular al renglón 38 de la OC".
- RDD assess `c2cadef..HEAD`: medium, `under_budget` → no review due.
