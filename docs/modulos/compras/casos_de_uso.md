# Casos de uso — Endpoints de Compras

Montado en `services/presupuestacion/main.py:12,47`
(`app.include_router(compras_router, tags=["compras"])`), sin prefijo propio — cada
ruta abajo es literal, tal como aparece en `router.py`.

## `POST /ordenes-compra`

- **Qué hace**: crea una OC nueva a partir de un proceso comercial, con sus ítems.
- **Roles**: `_ROLES_OC` = `admin`, `gerencia`, `lider_comercial`, `comercial`
  (`router.py:21`, `:47`).
- **Función**: `crear_orden_compra_endpoint` (`router.py:45-66`) →
  `crear_orden_compra_para_endpoint` (`service.py:288-295`) → `crear_orden_compra`
  (`service.py:44-109`).
- **Body**: `CrearOrdenCompraRequest` (`models.py:16-23`).
- **Response**: `ResultadoOrdenCompra` (`models.py:26-31`).
- **Errores posibles**: `NotFoundError` (proceso comercial inexistente, 404),
  `ForbiddenError` (proceso de otra droguería, resuelto por el router, 403),
  `ValidationError` (mismo caso resuelto por el service si el router no lo atrapó
  antes, 422), `ConflictError` (`numero_oc` duplicado, 409).

## `POST /ordenes-compra/{orden_compra_id}/confirmar`

- **Qué hace**: pasa la OC de `"pendiente"` a `"emitida"` y adjudica condicionalmente
  las ofertas propias ganadoras vinculadas a sus ítems.
- **Roles**: `_ROLES_OC` (igual que el endpoint anterior).
- **Función**: `confirmar_orden_compra_endpoint` (`router.py:70-78`) →
  `confirmar_orden_compra_para_endpoint` (`service.py:298-303`) →
  `confirmar_orden_compra` (`service.py:112-149`).
- **Body**: ninguno (solo el `orden_compra_id` de la URL).
- **Response**: `ResultadoOrdenCompra`.
- **Errores posibles**: `NotFoundError` (OC inexistente, 404), `ForbiddenError` (OC de
  otra droguería, 403), `ConflictError` (OC no está en `"pendiente"`, 409).

## `POST /ordenes-compra/{orden_compra_id}/entregas`

- **Qué hace**: registra una entrega física de mercadería sobre una OC, ajustando el
  stock del catálogo por los ítems con `producto_id`.
- **Roles**: `_ROLES_ENTREGA` = `admin`, `gerencia`, `lider_comercial`, `comercial`,
  `compras` (`router.py:22`, `:85`) — único endpoint de escritura que admite el rol
  `"compras"`.
- **Función**: `crear_entrega_endpoint` (`router.py:82-95`) →
  `crear_entrega_para_endpoint` (`service.py:306-323`) → `crear_entrega`
  (`service.py:198-285`).
- **Body**: `CrearEntregaRequest` (`models.py:43-47`).
- **Response**: `ResultadoEntrega` (`models.py:50-53`).
- **Errores posibles**: `NotFoundError` (OC inexistente o ítem que no pertenece a la
  OC, 404), `ForbiddenError` (OC de otra droguería, 403), `ConflictError` (OC en un
  estado no apto para entrega, 409; o propagado desde `stock.entregar_stock_producto`
  si agota reintentos, 409).

## `GET /entregas/pendientes`

- **Qué hace**: lista filas de la vista `v_entregas_pendientes` (entregas con
  `estado NOT IN ('entregada', 'rechazada')`, con días de atraso calculado).
- **Roles**: `_ROLES_LECTURA` = `superadmin`, `admin`, `gerencia`, `lider_comercial`,
  `comercial`, `compras` (`router.py:23`, `:100`) — el único endpoint del módulo
  accesible a `superadmin`.
- **Función**: `entregas_pendientes_endpoint` (`router.py:98-103`) — sin service ni
  repository propio, consulta la vista directo con `user_client` (RLS activa).
- **Response**: `list[dict]` crudo, sin `response_model` explícito.

## `GET /compras/vs-cotizado`

- **Qué hace**: lista filas de la vista `v_compras_vs_cotizado` (compara precio de
  compra real contra precio cotizado, con flag de `comprado_fuera_de_mantenimiento`).
- **Roles**: whitelist inline `superadmin`, `admin`, `gerencia`, `compras`
  (`router.py:108-110`) — la única whitelist del módulo que **no** incluye
  `lider_comercial` ni `comercial`.
- **Función**: `compras_vs_cotizado_endpoint` (`router.py:106-113`) — igual que el
  anterior, consulta la vista directo con `user_client`, sin service ni repository.
- **Response**: `list[dict]` crudo, sin `response_model` explícito.

## Quién consume estos endpoints

**Ningún frontend los consume todavía.** `Grep` de `ordenes-compra`,
`entregas/pendientes` y `compras/vs-cotizado` en `frontend/` no encontró ningún cliente
HTTP. `frontend/PROGRESS.md:16` confirma la pantalla correspondiente ("Compras") como
`⬜ Pendiente`. Mismo estado que [`../comparativas/`](../comparativas/README.md) al
momento de esta documentación.
