# Feature: Legacy presupuestos import (Progress) + PCP import lookup

## Objective
Load legacy presupuestos (budgets) from the old Progress system so that PCP and purchase-order matching work on real data, instead of manual loads. The import core is transport-agnostic: an endpoint receives parsed rows now; the future scheduled task (Windows Task Scheduler + Python script reading the folder where Progress drops the CSVs) will call the same use case.

## Why
OC matching searches `presupuesto_items` by price, and the PCP legacy import only creates an empty placeholder presupuesto with no `presupuesto_items`. Today presupuestos can only be loaded by hand.

## Agreed design (engram #647, 2026-09-12, confirmed 2026-09-24)
- Two legacy files: presupuesto = ALL quoted lines; PCP = the subset needing purchase negotiation, with the same line numbers.
- Import order is mandatory: presupuesto FIRST (creates proceso_comercial + presupuesto + items_proceso + presupuesto_items), PCP AFTER (finds the existing lines, never creates them).
- PCP row whose presupuesto was not imported yet → REJECT the row with a clear error ("no existe el presupuesto X, importalo primero"); no placeholder.
- `numero_presupuesto` becomes the real lookup key (`presupuesto_legacy_map.codigo_legacy`, migration 0015, idempotency).
- Columns (user, 2026-09-24): codigo_cliente, razon_social_cliente, numero_presupuesto, proceso_comercial, fecha_generacion, renglon, codigo_producto, descripcion_producto, cantidad_producto, precio_producto, importe_total. `subtotal_renglon` dropped by the user: `presupuesto_items.monto_total` is GENERATED.
- Mapping: presupuesto_items.precio_unitario/cantidad_ofertada = precio_producto/cantidad_producto; metodo_precio='manual'; pricing trace columns NULL. producto_id resolved from codigo_producto → productos.codigo_interno (NULL if not found). presupuestos.monto_total = importe_total (not generated); items_sin_precio = rows without precio; generado_at = fecha_generacion; estado='generado' always (ck_pre_aprobado). proceso_comercial "1"/"2" → `clase` via existing `_CLASE_POR_PROCESO_COMERCIAL`.
- `presupuesto_items` UNIQUE (presupuesto_id, item_proceso_id): insert only the first time the presupuesto is seen; reimport never duplicates.

## Scope / constraints
- No frontend screen in this feature (endpoint only).
- TDD strict. Backend runner: `venv/Scripts/python -m pytest tests/ -m "not integration"`.
- Branch `feat/presupuestos-legacy-import` from `dev` (3855ed2). Delivery: ask-on-risk.

## Tasks
- [x] T1 (delegated — writer + preparation triggers) Presupuesto legacy import: models, service, repository, router endpoint (`POST /pcp/imports/presupuestos-legacy` or sibling of the PCP legacy route), producto resolution, idempotency via `presupuesto_legacy_map`, tests.
- [x] T1b (delegated, same writer as T2) Review follow-ups on T1 (lineage review-48a39b194f35d786, approved, advisory): (a) `renglones_sin_producto` on reimport reads `items_sin_precio` — wrong metric; (b) mid-way failure test must assert presupuesto, proceso_comercial and items_proceso are gone; (c) router test `finally` NameError masking + assert 200; (d) guard each compensation step so the original error survives and proceso cleanup still runs; (e) test a batch with 2+ numero_presupuesto.
- [x] T2 (delegated) PCP legacy import: look up proceso/presupuesto by `numero_presupuesto` via `presupuesto_legacy_map`; reject rows without an imported presupuesto; find existing items_proceso by line number (never create); tests updated.
- [x] T3 (inline) Docs: module API/database docs for both imports.

## Progress / evidence
- T1 — commit `fbfbaa5` (6 files, +854/-3). `POST /pcp/imports/presupuestos-legacy` (ROLES_ESCRITURA_PCP), response per presupuesto `{codigo_legacy, presupuesto_id, accion: creado|existente, renglones_procesados, renglones_sin_producto}`. Reimport = no-op. datos_legacy = raw group rows. Compensation: delete presupuesto (cascades items + map) then proceso_comercial. RED: ImportError before impl; GREEN: 8 new tests. PCP import tests are `integration` against Supabase TEST: parent spot check `pytest tests/pcp/imports -m integration` 16 passed; `pytest tests/ -m "not integration"` 455 passed. Open note: producto lookup has no activo/deleted_at filter (same as existing precedent). Review assess (base 3855ed2): medium, 857 lines → slice_budget_reached; user granted consent → reliability lens approved (3 WARNING + 2 SUGGESTION advisory, tracked as T1b) → acknowledged, authority burned. Reviewed boundary: `fbfbaa5`.

- T1b — commit `e886322` (+254/-9): reimport metric fixed (`contar_presupuesto_items_sin_producto`), compensation steps guarded (original error preserved), stronger failure/router tests, multi-group batch test. RED→GREEN observed by writer.
- T2 — commit `0a5a2f4` (+446/-96): PCP import resolves presupuesto via `presupuesto_legacy_map`; rejects missing numero_presupuesto / non-imported presupuesto / missing renglón with NotFoundError (HTTP 404, all-or-nothing per request, same as client resolution). No placeholders. Existing PCP tests now import a presupuesto first.
- T2b (inline — 1 service fn + 1 test, understood) — commit `1225d5d`: writer flagged that a renglón rejection left a half-created pcp + pcp_legacy_map. Added `_prevalidar_lote_pcp`: whole batch validated before the first write. RED: test asserting no map row after rejection failed; GREEN: `pytest tests/pcp/imports -m integration` 23 passed; `pytest tests/ -m "not integration"` 455 passed.
- Frontend note (not in scope): `ImportLegacyPcp.tsx:70` shows a generic error and drops the backend detail — rejections are now routine, so the message should surface `detail`.
- Review assess (base fbfbaa5): medium, 862 lines → slice_budget_reached; START lineage `review-01f3f8fa9ad71154`; user granted → reliability approved → acknowledged. Advisory fixed in `d0a7f73` (server-side exact count; renglón error names the PCP); 23 import tests passed after. Not fixed (test-only suggestion): router test setup can leak a presupuesto into the TEST DB if the PCP import fails.
- T3 (inline) — commit `675dd0c`: `docs/modulos/pcp/README.md` documents both imports and the order.
- Branch total vs dev: 6 commits, 9 files, +1634/-111 (mostly tests). Over the ~400-line budget; slices were reviewed separately (fbfbaa5, then fbfbaa5..1225d5d).

- Delivery: user approved push + PR → PR #55 to `dev` (single PR; slices already reviewed).

## Next step
Merge PR #55 (user); follow-ups: frontend error detail in ImportLegacyPcp; scheduled Progress task once Sistemas confirms the folder.
