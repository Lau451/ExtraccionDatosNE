# OC overview screen

## Objective

Clicking the OC number in the delivery commitments agenda opens a read-only overview of the purchase
order instead of the delivery planner (user request 2026-10-12; the planner was only chosen in
oc-export-progress T6 because no OC overview existed).

## Scope

- Backend: `GET /ordenes-compra/{orden_compra_id}/resumen`, read-only, roles = commitments readers
  (`superadmin, admin, gerencia, lider_comercial, comercial, compras`), filtered by droguería.
  - Header: numero_oc, cliente (razon_social, cuit via clientes -> terceros), fecha_emision,
    fecha_entrega_estimada, direccion_entrega, notas, estado, version_numero, monto_total, exportacion.
  - Rows: numero_renglon, numero_renglon_documento, descripcion, producto (codigo_interno, nombre),
    cantidad, precio_unitario, monto_total, link state (pendiente / confirmado / sin_presupuesto).
  - Planned deliveries: numero_entrega, fecha_entrega_planificada, estado, items (oc_item_id, cantidad).
- Frontend: route `/ordenes-compra/$ordenCompraId`, overview component, links to matching and planner
  only for matching/planning roles (`admin, gerencia, lider_comercial, comercial`); compromisos link
  retargeted to the overview.

## Non-goals

- No editing on the overview. No PDF viewer. Other links to matching/planner stay as they are.

## Tasks

- [x] T1 Backend: `oc_resumen` module (models, repository, service, router) + tests.
- [x] T2 Frontend: API client, route, overview component, compromisos link + tests.
- [x] T3 Polish (user feedback 2026-10-12): "← Volver a compromisos" link; "Planificar entregas" only when
  the OC is not exported (deliveries are already listed below); amounts with es-AR thousands separators;
  total fallback without silently counting rows with no total as 0; non-UUID id -> 404 instead of 500.

## Evidence

(per task: commit, checks observed)

- T1 — commit `5aa32db`. RED: tests/oc_resumen collection ImportError (module missing). GREEN:
  tests/oc_resumen 9 passed, tests/oc_presupuesto 84 passed. Live smoke TEST (OC 986): cliente HOSPITAL
  PROVINCIAL SAYAGO / 33678351429, 7 rows, 3 deliveries, exportacion with exporter name; header monto_total
  null in TEST (frontend should fall back to the sum of rows). 403 test uses a `sistema` profile override.
- T2 — commit `41919b8`. RED: Compromisos.test.tsx:86 got `/ordenes-compra/oc-1/entregas`;
  OcResumen.test.tsx failed to load (component missing). GREEN: vitest oc-resumen + compromisos + lib
  11 files / 72 tests passed; tsc -b and oxlint clean. routeTree.gen.ts: only the new route (+23, checked
  ignoring EOL). Presupuestación restarted: /resumen present in openapi.
- T3 — commit `dcb52dd`. RED: 4 backend failures (invalid ids reached the repository), formatoMoneda
  import missing, 7 OcResumen failures (e.g. `'$1234567.89'` vs `'$ 1.234.567,89'`, no back link, planner
  link shown when exported, no incomplete-total note). GREEN: tests/oc_resumen 13 passed; vitest
  oc-resumen + compromisos + lib 12 files / 81 tests passed; tsc and oxlint clean. Invalid-id 404 covered
  by a service unit test only (no router test).
