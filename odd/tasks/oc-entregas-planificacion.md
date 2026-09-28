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
- [x] T3 — Backend planning API (context, gate, create/replace plan, divisibility warnings) + tests.
  - Commit `a44987d` (hardening from review advisories): strict ASCII `^[0-9]+$` + int4 cap in `_parsear_cantidad_entregas` and `parsear_unidades_por_presentacion`; 0031 constraint guarded and backfill bounded to `[0-9]{1,9}` (same end state as applied on TEST). RED: `ValueError: invalid literal for int() ... '--3'` / `'²'` plus boundary failures. GREEN: 16/16 and 10/10.
  - Commit `42a85b5`: new module `services/presupuestacion/oc_entregas/` with `GET`/`PUT /ordenes-compra/{orden_compra_id}/entregas/planificacion`, registered in `services/presupuestacion/main.py`.
    - Reuses `repartir_cantidad`, `crear_entrega_oc`/`insertar_entregas_oc_items` and `oc_presupuesto._derivar_estado`.
    - Pure `sugerir_plan_renglon` (whole packs, remainder on the last delivery).
    - Service client with explicit `drogueria_id` checks, because RLS limits `entregas_oc` DELETE to superadmin. Roles are the same as OC matching.
    - Replace = delete (cascade) + insert with delete-based compensation, the same pattern as `_materializar_orden_compra`.
    - No audit event (comparable writes don't record one). A test asserts stock is never touched.
  - TDD deviation (reported by the writer): the module and its tests were written together rather than strictly one RED per unit. The tests were then run against the TEST DB.
  - Writer cleaned 8 orphan test droguerias in the TEST DB left by a fixture bug during development.
  - Size: about 750 production lines and 1100 test lines (above the advisory 400; one coherent API).
- [x] T4 — Frontend planning screen + entry from OC matching + tests.
  - `02197bf`: API client `frontend/src/lib/api/ocEntregas.ts` + pure `features/oc-entregas/sugerirPlan.ts` (port of `sugerir_plan_renglon`). RED: unresolved import. GREEN: 11/11 incl. 100/25/3 → 50/25/25 and 110/25/3 → 50/25/35.
  - `33247d3`: `PlanificacionEntregas.tsx` + route `/ordenes-compra/:id/entregas` (`routes/_authenticated.ordenes-compra.$ordenCompraId.entregas.tsx`, `routeTree.gen.ts` regenerated).
    - The grid starts from `plan_actual` or `plan_sugerido`, and N (1–24) recomputes the suggestion.
    - Cells show non-blocking warnings with "usar N". Save is disabled on a row mismatch.
    - Locked plan → read-only. Blocked → `motivo` + back link.
    - RED: unresolved import. GREEN: 10/10.
  - `7bb7d7f`: "Planificar entregas" button in `OcMatchingDetalle.tsx`, disabled with a hint while any line is pending. RED: 2 failing. GREEN: 5/5.
  - `EntregasEditor.tsx` evaluated and not reused: it is keyed by position, with no dates or warnings. It stays unused, kept since tramo2 for a possible future reuse.
  - Writer: `npm test` 405 passed, `tsc --noEmit` clean, oxlint only pre-existing warnings. `npm run build` fails at `tsc -b` on a pre-existing error in `oc-matching/components/ColumnaPresupuesto.test.tsx:147` (`scrollIntoView` mock typing, file last changed in `000b346` on `dev`, untouched here). `vite build` alone succeeds.
  - Parent spot check: `npx vitest run src/features/oc-entregas src/features/oc-matching` → 56 passed; `npx tsc -b` reproduces only the pre-existing error.

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

- RDD T1+T2 (`069bfed..4ae48b7`): medium, `slice_budget_reached` → consent granted → lens `review-reliability` → approved, acknowledged (lineage `review-525d5cd426d7b862`, authority burned). Reviewed boundary is now `4ae48b7`.
  - Advisory (non-blocking) findings, folded into T3 as a hardening step: `_parsear_cantidad_entregas` can raise on `--3` or Unicode digits and has no int4 upper bound; `parsear_unidades_por_presentacion` and the 0031 backfill have no int4 upper bound; the 0031 `ADD CONSTRAINT` is not idempotent.

- T3 verification: writer `pytest tests/oc_entregas tests/oc_presupuesto tests/extraccion tests/productos tests/imports -q` → 393 passed. Parent spot check `pytest tests/oc_entregas -q` → 47 passed.

- RDD T3 (`4ae48b7..c7b3736`): medium, `slice_budget_reached` → consent granted → `review-reliability` → approved, acknowledged (lineage `review-caea8523d706122e`). Reviewed boundary is now `c7b3736`.
- Review advisories fixed right away (they were real defects), strict TDD with RED first:
  - `a731f30`: all reads happen before the delete, and the delete filters `estado = 'pendiente'`. When the deleted count ≠ the count read earlier, it raises 409 and skips inserts. Residual: in that race the still-pending deliveries were already deleted, so the plan is partially gone and the user must re-plan.
  - `fb12e4b`: a duplicate `oc_item_id` in one delivery → 422. `MAX_ENTREGAS_SUGERIDAS = 24` caps the GET suggestion, and a PUT with more than 24 deliveries → 422. The cap of 24 was chosen by the parent; the user was told and can change it.
  - `3c8a57c`: test cleanup guard.
  - `pytest tests/oc_entregas -q` → 52 passed (parent spot check). Assess `c7b3736..3c8a57c`: medium, `under_budget`, pending in the slice.

- RDD fixes+T4 (`c7b3736..d873e81`): medium, `slice_budget_reached` → consent granted → `review-reliability` → approved, acknowledged (lineage `review-6eda349a54886c47`). Reviewed boundary is now `d873e81`.
  - `82a2e96` fixed the advisories. Decimal fields travel as JSON strings (verified with a router test on the real DB) and are now parsed at the `ocEntregas.ts` boundary. Row sums are rounded to cents. A delivery with every line at 0 blocks Save. The planning query is invalidated after save. Frontend `npm test` → 413 passed; `pytest tests/oc_entregas` → 52 passed. Assess `d873e81..82a2e96`: medium, `under_budget` (375 lines), pending in the slice.
  - Residual, not fixed: in the rare race where a delivery leaves `pendiente` during a replace, the still-pending deliveries were already deleted before the 409.
  - Follow-up out of scope: `frontend/src/lib/api/ocMatching.ts` also types Decimal fields as `number` without parsing, so `AvisoReutilizacion.tsx` compares strings.
- Browser check (parent, TEST DB, user-authorized on OC 986 `e57f8b69-…`):
  - With 7 pending lines, the planning screen shows the blocked message, and the matching button is disabled with a hint.
  - After 1 discard + 6 confirms in matching, the button is enabled. The grid shows presentations x10/x1/x5/x30/x60/x30 and the discarded note.
  - N=3 suggestion is correct (800 x10 → 270/270/260; 400 x5 → 135/135/130).
  - 275 shows "No es múltiplo de 10. usar 270", restante −5 in red, Save disabled.
  - After fixing the sum (275/270/255), save succeeds with the server advertencias.
  - DB: 3 `pendiente` deliveries × 6 items, totals 9320 = sum of confirmed lines, no discarded line, `cantidad_entregas = 3`. Reload shows `plan_actual`.
  - Original state of OC 986 (to restore): all 7 `oc_items` had NULL `producto_id`/`presupuesto_item_id`/`vinculo_origen`/`vinculo_confirmado_at`, `vinculo_descartado = false`, `cantidad_entregas = 1`, and no `entregas_oc`.

## Next step

Stacked PRs (user decision on push/PR).

## Historical note (T3 brief)

Paused by the user on 2026-09-27, resumed 2026-09-28. A T3 writer was started and stopped before writing anything. The planned brief:

- Step A, hardening commit:
  - `_parsear_cantidad_entregas` never raises: ASCII `^[0-9]+$` only, capped at int4, else 1.
  - `parsear_unidades_por_presentacion` accepts ASCII digits only, capped at int4, else None.
  - Make 0031 idempotent (guard `ADD CONSTRAINT`) and bound the backfill to `[0-9]{1,9}`.
- Step B, new module `services/presupuestacion/oc_entregas/`, modeled on `oc_presupuesto`:
  - `GET /ordenes-compra/{id}/entregas/planificacion` returns:
    - the confirmed lines with `unidades_por_presentacion`;
    - pending and discarded counts;
    - `puede_planificar` and `motivo`;
    - `plan_sugerido`: whole packs split evenly with `repartir_cantidad`, the remainder goes to the last delivery. Example: 110 units, x25, N=3 → 50/25/35;
    - `plan_actual`.
  - `PUT` of the same path creates or replaces the plan:
    - 409 when there are pending lines, or when the plan is locked (a delivery is no longer `pendiente`);
    - 422 when delivery numbers are not 1..N, when a line is foreign or not confirmed, and when a line's sum ≠ its quantity;
    - writes `ordenes_compra.cantidad_entregas = N`;
    - returns non-blocking `advertencias` with `cantidad_sugerida` (nearest lower multiple, or u if that is 0);
    - never touches stock.
