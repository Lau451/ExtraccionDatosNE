# Base de datos — Compras

Compras es dueño de 4 tablas (`docs/schema/extractor_final.sql:607-688`, "CAPA 8 —
ÓRDENES DE COMPRA Y ENTREGAS"). No es dueño de `stock_productos` (Core, ver
[`../core/base_de_datos.md`](../core/base_de_datos.md)), `procesos_comerciales` (ver
[`../procesos_comerciales/`](../procesos_comerciales/README.md)) ni `ofertas_items`
(ver [`../comparativas/`](../comparativas/README.md)), aunque las 3 las lee (y, en el
caso de `ofertas_items`, también actualiza una columna puntual).

## `ordenes_compra`

| Columna | Tipo | Uso en Compras |
|---|---|---|
| `id` | `UUID` | PK; generado por la base al insertar (`repository.crear_orden_compra`, `compras/repository.py:17-18`). |
| `proceso_comercial_id` | `UUID NOT NULL` | Recibido del body (`CrearOrdenCompraRequest.proceso_comercial_id`, `models.py:17`), insertado tal cual (`service.py:58`). |
| `cliente_id` | `UUID NULL` | Copiado desde `proceso["cliente_id"]` (`service.py:59`), no del body. |
| `drogueria_id` | `UUID NOT NULL` | Recibido como parámetro de `crear_orden_compra` (resuelto por `router.py:60-66` desde el proceso comercial, no del body). |
| `extraction_id` | `UUID NULL` | **No usado por este módulo.** Ninguna fila de `compras/` la escribe (confirmado por `Grep`: cero apariciones en `compras/service.py`/`repository.py`); queda siempre en `NULL` para las OC creadas por este módulo. Ver [`pendientes.md`](./pendientes.md). |
| `numero_oc` | `TEXT NOT NULL` | Recibido del body (`models.py:18`), insertado tal cual (`service.py:61`). Con `UNIQUE (numero_oc, version_numero)` a nivel de constraint (`extractor_final.sql:630`) — ver RN-COMPRAS-003. |
| `estado` | `TEXT NOT NULL DEFAULT 'pendiente'` | Escrito por `crear_orden_compra` (`"pendiente"`, `service.py:62`), `confirmar_orden_compra` (`"emitida"`, `service.py:134`) y `_recalcular_estado_orden_compra` (`"entregada"`/`"parcialmente_entregada"`/`"en_entrega"`, `service.py:185-193`). Ver [`estados.md`](./estados.md). `CHECK` de la base admite además `'cancelada'` (`extractor_final.sql:632`), que ningún código de este módulo escribe. |
| `monto_total` | `NUMERIC(15,2) NULL` | Calculado en Python como suma de `cantidad * precio_unitario` de los ítems, redondeado con `ROUND_HALF_UP` a 2 decimales (`service.py:26-27`, `:53-55`) — no delega en el `GENERATED ALWAYS` de `oc_items.monto_total`. |
| `items_cantidad` | `INTEGER NOT NULL DEFAULT 0` | `len(body.items)` (`service.py:64`). |
| `fecha_emision` | `DATE NULL` | Del body, opcional (`service.py:65`). |
| `fecha_entrega_estimada` | `DATE NULL` | Del body, opcional (`service.py:66-68`). |
| `cantidad_entregas` | `INTEGER NOT NULL DEFAULT 1` | **No usado por este módulo.** Nunca se lee ni se escribe desde `compras/` (confirmado por `Grep`); queda siempre en su default `1` sin importar cuántas entregas reales tenga la OC. Ver [`pendientes.md`](./pendientes.md). |
| `direccion_entrega` | `TEXT NULL` | Del body, opcional (`service.py:69`). |
| `notas` | `TEXT NULL` | Del body, opcional (`service.py:70`). |
| `version_numero` | `INTEGER NOT NULL DEFAULT 1` | **No usado por este módulo.** Mismo patrón que ya está implementado en `comparativas` (`extractor_final.sql:567`), pero acá ningún código lo lee ni lo escribe — queda siempre en `1`. Ver [`pendientes.md`](./pendientes.md) P1. |
| `es_vigente` | `BOOLEAN NOT NULL DEFAULT TRUE` | **No usado por este módulo** — mismo caso que `version_numero`. |
| `reemplaza_id` | `UUID NULL` | **No usado por este módulo** — mismo caso. |
| `motivo_version` | `TEXT NULL` | **No usado por este módulo** — mismo caso. |
| `created_at`, `updated_at` | `TIMESTAMPTZ` | Defaults de la base; no escritos explícitamente por Compras. |

**Operaciones**: INSERT (`repository.crear_orden_compra`, `:17-18`), SELECT
(`repository.buscar_orden_compra`, `:27-31`) y UPDATE sin condición optimista
(`repository.actualizar_orden_compra`, `:44-53`, usado para `estado`). Compras no hace
DELETE sobre esta tabla.

## `oc_items`

| Columna | Tipo | Uso en Compras |
|---|---|---|
| `id` | `UUID` | PK; generado por la base. |
| `orden_compra_id` | `UUID NOT NULL` | FK a `ordenes_compra.id`, seteado en el insert (`service.py:86`). |
| `drogueria_id` | `UUID NOT NULL` | Copiado del parámetro `drogueria_id` de `crear_orden_compra` (`service.py:87`). |
| `oferta_item_id` | `UUID NULL` | Del body (`OrdenCompraItemRequest.oferta_item_id`, `models.py:12`); si viene, es la oferta que `confirmar_orden_compra` puede adjudicar (`service.py:123-131`). |
| `producto_id` | `UUID NULL` | Del body (`models.py:13`); si viene, es el producto de catálogo cuyo stock se ajusta al entregar (`service.py:270-272`). Comentario del schema: "Link al catálogo. Cierra la trazabilidad producto → oferta → OC → entrega y permite descontar stock del producto correcto" (`extractor_final.sql:653`). |
| `numero_renglon` | `INTEGER NOT NULL` | Del body (`models.py:8`); único junto a `orden_compra_id` (`UNIQUE (orden_compra_id, numero_renglon)`, `extractor_final.sql:650`). |
| `descripcion` | `TEXT NOT NULL` | Del body. |
| `cantidad` | `NUMERIC(12,2) NOT NULL` | Del body, como `Decimal` serializado a texto para el insert (`service.py:90`). |
| `precio_unitario` | `NUMERIC(15,2) NOT NULL` | Del body, ídem. |
| `monto_total` | `NUMERIC(15,2) GENERATED ALWAYS AS (precio_unitario * cantidad) STORED` | Calculado por Postgres, no por Compras — columna generada, no insertable. |
| `created_at` | `TIMESTAMPTZ` | Default de la base. |

**Operaciones**: INSERT en bloque (`repository.insertar_oc_items`, `:21-24`, no-op si
la lista está vacía) y SELECT (`repository.listar_oc_items`, `:34-41`). Compras no hace
UPDATE ni DELETE sobre `oc_items`.

## `entregas_oc`

| Columna | Tipo | Uso en Compras |
|---|---|---|
| `id` | `UUID` | PK; generado por la base. |
| `orden_compra_id` | `UUID NOT NULL` | Parámetro de `crear_entrega` (`service.py:241`). |
| `drogueria_id` | `UUID NOT NULL` | Copiado de `oc["drogueria_id"]` (`service.py:242`). |
| `numero_entrega` | `INTEGER NOT NULL` | Calculado como `len(entregas_previas) + 1` (`service.py:236-237`) — correlativo por OC, único junto a `orden_compra_id` (`UNIQUE (orden_compra_id, numero_entrega)`, `extractor_final.sql:670`). Sin locking explícito — ver [`pendientes.md`](./pendientes.md). |
| `fecha_entrega_planificada` | `DATE NULL` | Del body, opcional (`service.py:244-246`). |
| `fecha_entrega_real` | `DATE NULL` | Del body o `date.today()` si no viene (`service.py:247`). |
| `cantidad_items` | `INTEGER NOT NULL DEFAULT 0` | `len(items)` de la entrega (`service.py:248`). |
| `estado` | `TEXT NOT NULL DEFAULT 'pendiente'` | Calculado por `_calcular_estado_entrega` antes del insert (`service.py:238`, `:249`) — nunca `'pendiente'` en la práctica salvo el caso límite sin ítems entregados (ver [`estados.md`](./estados.md)). `CHECK` de la base admite además `'en_transito'` (`extractor_final.sql:671`), que este módulo nunca escribe. |
| `observaciones` | `TEXT NULL` | Del body, opcional. |
| `comprobante_entrega` | `TEXT NULL` | **No usado por este módulo.** No existe en `CrearEntregaRequest` (`models.py:43-47`) ni se escribe en `service.py`. |
| `created_at`, `updated_at` | `TIMESTAMPTZ` | Defaults de la base. |

**Operaciones**: INSERT (`repository.crear_entrega`, `:67-68`) y SELECT
(`repository.listar_entregas_por_orden`, `:77-84`, usado tanto para calcular
`numero_entrega` como, indirectamente a través de `entregas_oc_items`, para recalcular
el estado de la OC). Compras no hace UPDATE ni DELETE sobre `entregas_oc` — una vez
creada, una entrega no se modifica.

## `entregas_oc_items`

| Columna | Tipo | Uso en Compras |
|---|---|---|
| `id` | `UUID` | PK; generado por la base. |
| `entrega_oc_id` | `UUID NOT NULL` | FK, seteado al insertar (`service.py:256`). |
| `drogueria_id` | `UUID NOT NULL` | Copiado de `oc["drogueria_id"]` (`service.py:257`). |
| `oc_item_id` | `UUID NOT NULL` | Del body (`EntregaItemRequest.oc_item_id`, `models.py:35`), validado antes contra `oc_items_por_id` (`service.py:230-234`). Único junto a `entrega_oc_id` (`UNIQUE (entrega_oc_id, oc_item_id)`, `extractor_final.sql:686`) — un ítem de OC no puede aparecer dos veces en la misma entrega. |
| `cantidad_entregada` | `NUMERIC(12,2) NOT NULL` | Del body. `CHECK (cantidad_entregada >= 0 AND cantidad_rechazada >= 0)` a nivel de base (`extractor_final.sql:687`) — no hay validación adicional en Python de que sea positiva o de que no exceda lo pedido en `oc_items.cantidad`. |
| `cantidad_rechazada` | `NUMERIC(12,2) NOT NULL DEFAULT 0` | Del body, default `Decimal("0")` (`models.py:37`). |
| `motivo_rechazo` | `TEXT NULL` | Del body, opcional. |
| `lote` | `TEXT NULL` | Del body, opcional. |
| `vencimiento` | `DATE NULL` | Del body, opcional. |
| `created_at` | `TIMESTAMPTZ` | Default de la base. |

**Operaciones**: INSERT en bloque (`repository.insertar_entrega_items`, `:71-74`) y
SELECT filtrado por `oc_item_id IN (...)` (`repository.listar_entrega_items_por_oc_items`,
`:87-98`, usado por `_recalcular_estado_orden_compra` para agregar lo aceptado por
ítem across todas las entregas de la OC). Compras no hace UPDATE ni DELETE sobre esta
tabla.

## Tablas leídas pero no propias

| Tabla | Qué lee Compras |
|---|---|
| `procesos_comerciales` | `id, drogueria_id, cliente_id` (`repository.buscar_proceso_comercial`, `:6-14`), para validar el origen de una OC nueva. |
| `ofertas_items` | Fila completa (`repository.buscar_oferta_item`, `:56-60`) y `UPDATE {"adjudicada": True}` (`repository.marcar_oferta_adjudicada`, `:63-64`) — la única escritura de Compras sobre una tabla que no es propia. |

## Vistas SQL consumidas por `router.py` (sin tabla/repository dedicados)

- `v_entregas_pendientes` (`extractor_final.sql:1598-1609`): entregas con
  `estado NOT IN ('entregada', 'rechazada')`, consultada directo desde el endpoint
  (`router.py:98-103`), sin pasar por `repository.py`.
- `v_compras_vs_cotizado` (`extractor_final.sql:1637-1655`): compara precio de compra
  real (`compras_proveedor`) contra el precio cotizado (`precios_proveedor`), también
  consultada directo desde el endpoint (`router.py:106-113`). Ninguna de las dos vistas
  tiene función de `repository.py` propia — el `router.py` llama a
  `user_client.table(...)` inline.
