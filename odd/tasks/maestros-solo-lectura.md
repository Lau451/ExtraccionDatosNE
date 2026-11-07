# Etapa 7 — maestros de solo lectura

Stage 7 of docs/arquitectura/README.md: Progress owns product and tercero altas (L3 of odd/tasks/costos-un-dueno.md); the app keeps only the fields Progress does not send.
Branch `feat/maestros-solo-lectura` from `dev` (`01a2cbf`). No migrations. Closed endpoints are deleted (endpoint, service, frontend API client, screen), not left answering errors (L2).

## Specs

- **S1** Contract (L1): "Se escribe el contrato de propiedad por campo en `docs/arquitectura`" — new `docs/arquitectura/maestros-progress.md`, one table per table (`productos`, `costos_productos`, `stock_productos`, `terceros`, `clientes`, `proveedores`, their app-owned children) saying who writes each column: Progress (via `/imports/*`) or the app. Linked from README.
- **S2** Productos (L2 Q1 "Sin alta/baja; solo características"): delete `POST /productos`, `PATCH /productos/{id}`, `DELETE /productos/{id}`. Keep `POST /productos/{id}/caracteristicas` and `DELETE /productos/{id}/caracteristicas/{cid}`. Catalog endpoints (`categorias`, `marcas`, `envases`, `caracteristicas`) stay: the import references their ids.
- **S3** Costos y stock (L2 Q2 "Cerrar los dos y sacar sus pantallas"): delete `POST /productos/{id}/costos` and `PATCH /productos/{id}/stock`. `GET` of costos and stock stay. `cantidad_comprometida` (core/stock.py) is not touched. The batch `versionar_costos` (stage 3) stays; manual `crear_costo` goes.
- **S4** Terceros (L2 Q3 "Alta e identidad a Progress; resto en la app"): delete `POST /terceros`, `POST /terceros/{id}/clientes`, `POST /terceros/{id}/proveedores`. `PATCH /terceros/{id}` accepts only `nombre_fantasia, email, telefono, sitio_web, notas`; `PATCH .../clientes` only `condicion_pago_id, forma_pago_id`; `PATCH .../proveedores` only `condicion_pago_id, forma_pago_id`. A Progress-owned field in the body (`codigo_interno, razon_social, cuit, activo, tipo, es_competidor, es_proveedor_compra`) answers 422 and changes nothing. Direcciones, contactos and the payment catalogs stay as they are.
- **S5** Legacy clientes (same decision): delete `POST /clientes` and `DELETE /clientes/{id}`; `PATCH /clientes/{id}` accepts only `email, telefono, condicion_pago_id, forma_pago_id` (422 otherwise). Its contactos, formato-documentos and observaciones stay.
- **S6** Frontend productos: remove create, edit, delete, costo and stock-adjust UI and their API client functions; the screens show the data read-only. Characteristic assignment stays.
- **S7** Frontend terceros: remove tercero create and role-assign UI; edit forms show Progress-owned fields read-only and send only app-owned fields.
- **S8** Docs: stage 7 implemented in README stage table; `mapa-modulos.md` notes `imports` as the only writer of Progress-owned columns; `docs/modulos/{productos,terceros,clientes}` updated; tests of deleted endpoints replaced by one that proves the route no longer exists.

Out of scope: `core/stock.py::_descontar_disponible_hasta` lowers `cantidad_disponible` on OC delivery (app writes a Progress-owned column) — recorded in the contract as a known deviation. The `/imports/*` endpoints stay as they are.

## Tasks

| ID | Specs | Route | Commit |
|----|-------|-------|--------|
| T1 | S1 | inline: contract doc | docs(arquitectura): field ownership contract |
| T2 | S2, S3 | worker: productos backend, tests | feat(productos): delete manual alta, edición, baja, costo and stock |
| T3 | S4, S5 | worker: terceros + clientes backend, tests | feat(terceros): Progress owns tercero alta and identity |
| T4 | S6 | worker: frontend productos | feat(frontend): product masters are read-only |
| T5 | S7 | worker: frontend terceros | feat(frontend): tercero identity and roles are read-only |
| T6 | S8 | inline: docs | docs: record stage 7 read-only masters |

## Log

- **L1** (user, 2026-11-07): "vamos con la 7" (stage 7 as recorded in docs/arquitectura/README.md: "Maestros de solo lectura: las altas de productos y terceros las hace Progress. Se escribe el contrato de propiedad por campo y se cierran o restringen los endpoints manuales de alta, costo y stock, junto con sus pantallas.")
- **L2** (user answers, 2026-11-07): Q1 Productos — "Sin alta/baja; solo características (Recomendado)" ("Se cierran POST y DELETE /productos y la edición de campos. Queda asignar/quitar características (N:M), que Progress no manda. Categoría/marca/envase pasan a ser de Progress."); Q2 — "Cerrar los dos y sacar sus pantallas (Recomendado)"; Q3 — "Alta e identidad a Progress; resto en la app (Recom.)" ("Se cierran POST /terceros, POST /clientes (legacy, hoy lo puede usar comercial) y la edición de razón social/CUIT/código/tipo. Direcciones, contactos, email, teléfono y condiciones siguen editables."); Q4 — "Borrar endpoint, servicio, API y pantalla (Recom.)".
- **L3** (assistant, derived): catalog CRUD (categorias/marcas/envases/caracteristicas) stays because the import sends their ids; role POSTs close because the import creates roles; `nombre_fantasia, sitio_web, notas` are app-owned because the import never writes them.
- **L4** (assistant, T3): service `crear_tercero`/`TerceroCreate` deleted too (L2 Q4), after reseeding its only remaining caller, a seed in `tests/imports/test_service.py`, with a direct insert.
