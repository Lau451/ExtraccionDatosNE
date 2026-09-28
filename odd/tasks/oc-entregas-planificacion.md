# OC deliveries: planning after matching (parts 1–3)

## Objective

After OC matching, let the user split a purchase order into N deliveries (`entregas_oc` / `entregas_oc_items`). The number of deliveries is suggested from the document, the user sets the quantity per delivery and line, and the system warns and suggests a quantity divisible by the product's presentation.

## Problem

- Delivery splitting was removed from OC validation (`odd/tasks/orden-compra-tramo2-sin-entregas.md`) and deferred to "after matching". Nothing creates deliveries today: `crear_entrega_oc` / `insertar_entregas_oc_items` (`services/presupuestacion/extraccion/repository.py`), `EntregaPlanIn` / `repartir_cantidad` and `EntregasEditor.tsx` are unused.
- The OC robot extracts `cantidad_entregas` (`services/extraccion/robot_orden_compra.py:86`), but `_materializar_orden_compra` does not persist it, so `ordenes_compra.cantidad_entregas` stays at its default 1.
- `productos.presentacion` is free text. In the TEST DB, 7037/7144 products match `Presentación x N`, 97 use other formats and 10 are NULL. There is no numeric pack size to check divisibility.
- OC matching has no "finish" action. Lines can stay `pendiente`.

## Why

This follows the user's product decisions from 2026-09-27 (Engram `odd/entregas-oc/decisions`):

- Follow `openspec/changes/orden-compra/design.md` (D1 plan and actual share a row via `cantidad_planificada`; D8 split), but after matching.
- Only matching-confirmed lines enter deliveries. Discarded lines stay out. Any `pendiente` line blocks planning, which acts as the matching completion gate.
- A non-multiple quantity only warns and suggests a divisible one. It never blocks. The remainder goes to the last delivery.
- The system does not manage stock yet. Nothing in this stage calls `entregar_stock_producto`.

## Scope

1. Numeric presentation: `productos.unidades_por_presentacion INTEGER NULL CHECK (> 0)`, backfilled from `presentacion` when it matches `Presentación x N`. Other formats stay NULL (no divisibility check). The product import path fills it too, if it writes `presentacion`.
2. Persist the extracted `cantidad_entregas` when materializing an OC. A positive integer is stored. Empty or invalid stores 1.
3. Delivery planning:
   - Backend: get the planning context (confirmed lines with product, pack size, suggested N) and create a plan.
   - Gate: reject when any line is `pendiente`.
   - Validate that per-line sums equal the line quantity.
   - Return non-blocking divisibility warnings with a suggested quantity.
   - Allow re-planning only while every delivery is still `pendiente`.
   - Frontend: planning screen reachable from OC matching, reusing `EntregasEditor` where it fits.

Out of scope: NP CSV export, Progress return/devolución import, renuncia PDF and OC closing (parts 4–6, which need a real Progress CSV sample and a storage bucket).

## Constraints

- Strict TDD. Backend: `venv/Scripts/python -m pytest <tests> -q`. Frontend: `npm test`, `npx tsc --noEmit -p .`, `npx oxlint <path>` in `frontend/`.
- The parent applies migrations to the TEST Supabase project (`grnamollopxdlstcpxhc`). Writers only write the SQL files (+ `.down.sql`) and mirror `docs/schema/extractor_final.sql`.
- Never touch stock. Keep D13.1 `numero_renglon` semantics.
- Commits: Conventional Commits, no AI attribution line.
- About 400 authored changed lines per task is a planning heuristic only, not a cap.

## Tasks

- [x] T1 — Migration 0031 `productos.unidades_por_presentacion` + backfill + import-path parsing + tests.
  - Commit `2bda960`. Migration `0031_productos_unidades_por_presentacion.sql` (+`.down.sql`), schema doc mirrored. Pure parser `services/productos/domain.py::parsear_unidades_por_presentacion`, wired into `crear_producto`/`actualizar_producto` (`services/productos/service.py`) and `importar_productos` (`services/presupuestacion/imports/service.py`).
  - RED: `ModuleNotFoundError: No module named 'services.productos.domain'`. GREEN: `tests/productos/test_domain.py` 7 passed.
- [x] T2 — Persist `cantidad_entregas` at OC materialization + tests.
  - Commit `e0da0ad`. `OrdenCompraOverride.cantidad_entregas: str | None`; `_parsear_cantidad_entregas` (positive int, else 1) used in `_materializar_orden_compra`. Frontend computes the header value with the same most-frequent rule as other header fields (read-only, no new input) and sends it in `construirOrdenCompraOverride`.
  - RED: `KeyError: 'cantidad_entregas'` (backend) and missing-value assertions (frontend). GREEN: `tests/extraccion -m "not integration"` 150 passed; frontend `npm test` 382 passed; `tsc` clean.
- [ ] T3 — Backend planning API (context, gate, create/replace plan, divisibility warnings) + tests.
- [ ] T4 — Frontend planning screen + entry from OC matching + tests.

## Acceptance criteria

- A product `Presentación x 25` gets `unidades_por_presentacion = 25`. A product `Pres x 1(cajax100)` gets NULL.
- An OC materialized from a document stating 3 deliveries stores `cantidad_entregas = 3`.
- Planning an OC with a `pendiente` line is rejected with a clear message.
- A plan with 2 deliveries over confirmed lines creates `entregas_oc` rows 1..2 and `entregas_oc_items.cantidad_planificada` per line. Discarded lines are absent.
- A quantity of 30 for a `x 25` product returns a warning suggesting 25, and the plan is still created.
- No stock rows change.

## Checks

- `venv/Scripts/python -m pytest tests/extraccion tests/oc_presupuesto -q` plus any new test module
- `npm test`, `npx tsc --noEmit -p .`, `npx oxlint src/features` in `frontend/`

## Route

- T1–T2: delegated direct, one writer (migration + service + tests, 2+ non-trivial files).
- T3: delegated direct (writer trigger).
- T4: delegated direct (writer trigger).

## Delivery

- Strategy: `ask-on-risk`. Forecast about 900 authored changed lines across T1–T4.
- Chain strategy (user, 2026-09-27): `stacked-to-main`, with `dev` as the base. Planned slices: PR1 = T1+T2 → `dev`, PR2 = T3 → PR1, PR3 = T4 → PR2.

## Progress

- Branch `feat/oc-entregas-planificacion` from `dev` @ 069bfed.
- RDD: on (global). Last reviewed boundary: 069bfed.

## Parent verification

- Migration 0031 applied to the TEST project (`grnamollopxdlstcpxhc`) via Supabase MCP `apply_migration`: 7037 products backfilled, 107 NULL.
- `venv/Scripts/python -m pytest tests/productos tests/imports tests/extraccion tests/oc_presupuesto -q` → 336 passed (integration included).

## Next step

RDD assess of T1+T2, then T3.
