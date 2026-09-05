# Base de datos — Catálogo

> **Actualización (change `terceros-modelo`, Fase 8/10)**: `proveedores` perdió
> `razon_social`/`nombre_comercial`/`cuit`/`plazo_pago_dias`/`condiciones_pago`/
> `codigo_interno` (movidos a `terceros`/`condiciones_pago`) y ganó
> `condicion_pago_id`/`forma_pago_id` (FK). La tabla de abajo describe el esquema
> **anterior**; el estado vigente está en
> [`../terceros/base_de_datos.md`](../terceros/base_de_datos.md).

Catálogo es el módulo dueño de las 5 tablas siguientes. Ver
[`arquitectura.md`](./arquitectura.md) para el detalle de los 5 módulos que además
leen o escriben estas tablas por fuera de este código.

## `productos`

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK. Generada por Postgres al insertar (`repository.py:10-11`). |
| `drogueria_id` | FK a `droguerias`. Fijada al crear con la del solicitante (`service.py:29`); filtro de tenant en `listar_productos` (`repository.py:20`) y comparación de pertenencia en `obtener_producto` (`service.py:53`, RN-CATALOGO-001). |
| `codigo_interno` | NOT NULL en `ProductoCreate` (`models.py:14`). Escrita al crear (`service.py:30`). También la usa `imports/repository.py` para matching por lote y para el `UNIQUE(drogueria_id, codigo_interno)` de su upsert masivo (ver [`arquitectura.md`](./arquitectura.md)). |
| `nombre` | NOT NULL. Escrita al crear, actualizable parcialmente. Usada para ordenar el listado (`repository.py:27`). |
| `categoria_id` | Nullable. FK a `categorias`. Escrita al crear, actualizable parcialmente; filtro opcional de `listar_productos` (`repository.py:25-26`, query param `categoria_id`). |
| `clasificacion` | `Clasificacion` (`Literal`, `models.py:7-9`). Nullable. |
| `droga`, `presentacion`, `forma_farmaceutica`, `laboratorio`, `codigo_anmat` | Nullable. Escritas al crear, actualizables parcialmente. |
| `activo` | BOOLEAN. Filtro opcional en `listar_productos` (`repository.py:23-24`); forzada a `False` por `soft_delete_producto` (`repository.py:51`). Leída directo (sin pasar por este módulo) por `matching/repository.py:42` e `imports/repository.py`. |
| `deleted_at`, `deleted_by` | Escritas únicamente por `soft_delete_producto` (`repository.py:49-50`). Filtro `is_("deleted_at", None)` en `obtener_producto` (`repository.py:35`) y `listar_productos` (`repository.py:21`). |
| `created_by`, `updated_by` | `created_by`/`updated_by` escritas al crear (`service.py:39-40`); `updated_by` reescrita en cada `actualizar_producto` (`service.py:63`). |

**CRUD**: Create (`repository.py:10-11`), Read (`obtener_producto`,
`repository.py:30-39`; `listar_productos`, `repository.py:14-27`), Update
(`repository.py:42-43`), soft-Delete (`repository.py:46-53`).

## `categorias`

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK. |
| `drogueria_id` | FK a `droguerias`. Escrita al crear (`service.py:92`); filtro de tenant en `listar_categorias` (`repository.py:63`) y comparación de pertenencia en `actualizar_categoria` (`service.py:104`). |
| `nombre` | NOT NULL. Escrita al crear, actualizable parcialmente. Usada para ordenar el listado (`repository.py:66`). |
| `descripcion` | Nullable. Escrita al crear, actualizable parcialmente. |
| `activa` | BOOLEAN. Filtro opcional en `listar_categorias` (`repository.py:64-65`, query param `activa`). Reactivable/desactivable vía `PATCH` sin ninguna guarda (RN-CATALOGO-004) — no existe soft-delete ni `DELETE /categorias/{id}` en este módulo. |

**CRUD**: Create (`repository.py:58-59`), Read (`obtener_categoria`,
`repository.py:69-71`; `listar_categorias`, `repository.py:62-66`), Update
(`repository.py:74-75`). Sin Delete, ni físico ni lógico.

## `proveedores`

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK. |
| `drogueria_id` | FK a `droguerias`. Fijada al crear (`service.py:128`); filtro de tenant en `listar_proveedores` (`repository.py:90`) y comparación de pertenencia en `obtener_proveedor` (`service.py:151`, RN-CATALOGO-001). |
| `codigo_interno` | Nullable. No escrita por `crear_proveedor` de este módulo (no aparece en el dict de `service.py:125-140`) — mismo patrón que `clientes.codigo_interno` (ver [`../clientes/pendientes.md`](../clientes/pendientes.md) P3(4)); sí la usa `imports/repository.py` para matching y upsert masivo por lote. |
| `razon_social` | NOT NULL. Escrita al crear, actualizable parcialmente. Usada para ordenar el listado (`repository.py:95`). |
| `nombre_comercial`, `cuit`, `condiciones_pago` | Nullable. Escritas al crear, actualizables parcialmente. |
| `tipo` | `TipoProveedor` (`Literal`, `models.py:10`), default `"otro"` (`models.py:75`). |
| `es_competidor` | BOOLEAN, default `True` (`models.py:76`). |
| `es_proveedor_compra` | BOOLEAN, default `False` (`models.py:77`). Leída directo por `comparativas/repository.py:15` (`buscar_proveedor`). |
| `plazo_pago_dias` | Nullable `int`. |
| `activo` | BOOLEAN. Filtro opcional en `listar_proveedores` (`repository.py:93-94`); forzada a `False` por `soft_delete_proveedor` (`repository.py:119`). |
| `deleted_at`, `deleted_by` | Escritas únicamente por `soft_delete_proveedor` (`repository.py:117-118`). Filtro `is_("deleted_at", None)` en `obtener_proveedor` (`repository.py:103`) y `listar_proveedores` (`repository.py:91`). |
| `created_by`, `updated_by` | Análogo a `productos` (`service.py:137-138`, `:161`). |

**CRUD**: Create (`repository.py:80-81`), Read (`obtener_proveedor`,
`repository.py:98-107`; `listar_proveedores`, `repository.py:84-95`), Update
(`repository.py:110-111`), soft-Delete (`repository.py:114-121`).

## `costos_productos`

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK. |
| `producto_id` | FK a `productos`. Filtro de `listar_costos`/`costo_vigente` (`repository.py:130`, `:141`). |
| `drogueria_id` | FK a `droguerias`. Escrita al crear (`service.py:212`), no leída por este módulo tras la escritura. |
| `costo_unitario` | `Decimal`. Comparada contra el vigente para decidir si hay que versionar o no (`service.py:201`, RN-CATALOGO-005). |
| `fecha_desde` | `date`. Usada para calcular la `fecha_hasta` del costo que se cierra (`service.py:205`, RN-CATALOGO-006). |
| `fecha_hasta` | Nullable. `IS NULL` es la condición de "costo vigente" (`repository.py:142`, RN-CATALOGO-006) — no hay un enum de estado, es una columna de fecha usada como bandera de vigencia. |
| `origen` | Hardcodeada a `"manual"` en todo alta hecha por este módulo (`service.py:216`, RN-CATALOGO-007). `imports/service.py` escribe `"import_sistema"` para la misma tabla, con el mismo algoritmo reimplementado (ver [`arquitectura.md`](./arquitectura.md)). |

**CRUD**: Create/versionado (`crear_costo`, `service.py:195-218` →
`repository.py:149-150`; cierre del vigente, `repository.py:153-154`), Read
(`listar_costos`, `repository.py:126-134`; `costo_vigente`, `repository.py:137-146`).
Sin Update libre (solo `fecha_hasta` vía `cerrar_costo_vigente`) ni Delete.

## `stock_productos`

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK. |
| `producto_id` | FK a `productos`. Parte de la clave `UNIQUE(producto_id, deposito)` usada por el `upsert` (`repository.py:188`, RN-CATALOGO-008). |
| `drogueria_id` | FK a `droguerias`. Escrita en cada upsert (`service.py:246`), no leída por este módulo tras la escritura. |
| `deposito` | Nullable en el modelo (`StockAjuste.deposito`, `models.py:124`), pero nunca `None` en la fila final: si no se especifica, se usa `DEPOSITO_SENTINEL` (`"unico"`, ver RN-CATALOGO-009). Segunda parte de la clave `UNIQUE(producto_id, deposito)`. |
| `cantidad_disponible` | Único campo que este módulo escribe en `ajustar_stock` (`service.py:236-250`, RN-CATALOGO-010). También la descuenta `core/stock.py` al confirmar entregas de OC — ver [`arquitectura.md`](./arquitectura.md) para el detalle de este escritor concurrente. |
| `cantidad_comprometida` | **Nunca escrita por este módulo.** Mantenida exclusivamente por `core/stock.py` (comentario explícito en el código, RN-CATALOGO-010). |

**CRUD**: Read (`listar_stock`, `repository.py:159-167`;
`buscar_stock_por_deposito`, `repository.py:170-182`), upsert idempotente
(`upsert_stock`, `repository.py:185-191`, `on_conflict="producto_id,deposito"`). Sin
Delete.

## Resumen CRUD y soft-delete

| Tabla | CRUD | Soft-delete |
|---|---|---|
| `productos` | C/R/U/soft-D | Sí. `deleted_at`/`deleted_by`/`activo=False` (`repository.py:46-53`). |
| `categorias` | C/R/U | No — ni soft ni físico. Sin endpoint `DELETE`. |
| `proveedores` | C/R/U/soft-D | Sí. `deleted_at`/`deleted_by`/`activo=False` (`repository.py:114-121`). |
| `costos_productos` | C/R/U (solo `fecha_hasta`) | No. Vigencia se resuelve con `fecha_hasta IS NULL`. |
| `stock_productos` | R/upsert | No aplica — es una tabla de magnitudes, no de entidades dadas de baja. |

Sobre las políticas RLS de estas 5 tablas: no se encontró en este módulo (ni se
verificó en esta sesión) un archivo equivalente a `docs/schema/rls_final.sql` con el
detalle de cada policy — pendiente de definición funcional si se necesita ese nivel
de detalle. Los `GET` de este módulo usan `user_client` (con RLS) y las escrituras
usan `service_client` (sin RLS) vía los wrappers `*_para_endpoint` — ver
[`../core/`](../core/) para el patrón general.
