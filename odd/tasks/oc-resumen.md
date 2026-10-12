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

- [ ] T1 Backend: `oc_resumen` module (models, repository, service, router) + tests.
- [ ] T2 Frontend: API client, route, overview component, compromisos link + tests.

## Evidence

(per task: commit, checks observed)
