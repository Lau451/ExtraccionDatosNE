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
- [ ] T1 — Migration + persist `numero_renglon_documento` at materialization + tests.
- [ ] T2 — OC matching API returns the field + tests.
- [ ] T3 — Frontend label with fallback in OC column and manual-link button + tests.

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
