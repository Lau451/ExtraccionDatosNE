# Base de datos — Productos

> **Actualización (refactor `catalogo/` → `services/productos/`)**: el módulo se
> extrajo de `services/presupuestacion/catalogo/` a `services/productos/`
> (top-level). El wrapper de compatibilidad de `proveedores` descrito en la nota
> siguiente se **eliminó por completo** en este refactor, no se movió — este módulo
> ya no tiene ninguna función ni endpoint de `proveedores`. La sección `proveedores`
> de la tabla de abajo queda solo como registro histórico de cuando la tabla era
> propiedad de este módulo; el estado vigente de `proveedores` está en
> [`../terceros/base_de_datos.md`](../terceros/base_de_datos.md).

> **Actualización (change `terceros-modelo`, Fase 8/10)**: `proveedores` perdió
> `razon_social`/`nombre_comercial`/`cuit`/`plazo_pago_dias`/`condiciones_pago`/
> `codigo_interno` (movidos a `terceros`/`condiciones_pago`) y ganó
> `condicion_pago_id`/`forma_pago_id` (FK). La tabla de abajo describe el esquema
> **anterior**; el estado vigente está en
> [`../terceros/base_de_datos.md`](../terceros/base_de_datos.md).

> **Actualización (migración `0016_productos_marca_envase_caracteristicas`)**:
> `productos.laboratorio` (TEXT libre) queda deprecado — reemplazado para altas
> nuevas por `marca_id` (FK a `marcas`, tabla nueva). La columna `laboratorio`
> **no se eliminó** en esta migración: al momento de escribirla, `productos` ya
> tenía 15 filas de fixtures de test en el proyecto de test (no 0 como se
> esperaba), así que se dejó la columna nullable y sin uso nuevo en vez de un
> `DROP COLUMN` no verificado contra datos reales. Se agregaron además
> `envase_id` (FK a `envases`, tabla nueva — concepto distinto de
> `forma_farmaceutica`: envase es el contenedor físico, no la forma del
> producto) y `alicuota_iva` (dato fiscal, antes inexistente). Características
> especiales (psicotrópico, heladera, vale...) pasan a ser N:M vía la tabla
> puente nueva `producto_caracteristicas`, no un campo de texto único.

Productos es el módulo dueño de 8 tablas activas —`productos`, `categorias`,
`marcas`, `envases`, `caracteristicas`, `producto_caracteristicas`,
`costos_productos`, `stock_productos`— más la sección histórica de `proveedores`
documentada abajo. Ver [`arquitectura.md`](./arquitectura.md) para el detalle de los
módulos que además leen o escriben estas tablas por fuera de este código.

## `productos`

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK. Generada por Postgres al insertar (`repository.py:10-11`). |
| `drogueria_id` | FK a `droguerias`. Fijada al crear con la del solicitante (`service.py:29`); filtro de tenant en `listar_productos` (`repository.py:20`) y comparación de pertenencia en `obtener_producto` (`service.py:53`, RN-PRODUCTOS-001). |
| `codigo_interno` | NOT NULL en `ProductoCreate` (`models.py:14`). Escrita al crear (`service.py:30`). También la usa `imports/repository.py` para matching por lote y para el `UNIQUE(drogueria_id, codigo_interno)` de su upsert masivo (ver [`arquitectura.md`](./arquitectura.md)). |
| `nombre` | NOT NULL. Escrita al crear, actualizable parcialmente. Usada para ordenar el listado (`repository.py:27`). |
| `categoria_id` | Nullable. FK a `categorias`. Escrita al crear, actualizable parcialmente; filtro opcional de `listar_productos` (`repository.py:25-26`, query param `categoria_id`). |
| `clasificacion` | `Clasificacion` (`Literal`, `models.py:7-9`). Nullable. |
| `droga`, `presentacion`, `forma_farmaceutica`, `codigo_anmat` | Nullable. Escritas al crear, actualizables parcialmente. |
| `marca_id` | Nullable. FK a `marcas` (reemplaza `laboratorio` para altas nuevas — ver nota de migración arriba). Escrita al crear/actualizar (`service.py`, dict de `crear_producto`/`actualizar_producto`). |
| `envase_id` | Nullable. FK a `envases`. Distinto de `forma_farmaceutica`: envase es el contenedor físico (caja, frasco, blister), no la forma del producto. |
| `alicuota_iva` | Nullable. `NUMERIC(5,2)`, `CHECK (alicuota_iva IS NULL OR alicuota_iva >= 0)`. Convertida a `str` antes de escribir (mismo patrón que `costo_unitario` en `costos_productos`, evita que el cliente de Supabase reciba un `Decimal` no serializable). |
| `laboratorio` | **Deprecado, sin uso nuevo.** No aparece en `ProductoCreate`/`ProductoUpdate`/`ProductoOut` desde la migración 0016. Columna todavía presente en la tabla (ver nota arriba); retiro definitivo pendiente. |
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
| `activa` | BOOLEAN. Filtro opcional en `listar_categorias` (`repository.py:64-65`, query param `activa`). Reactivable/desactivable vía `PATCH` sin ninguna guarda (RN-PRODUCTOS-004) — no existe soft-delete ni `DELETE /categorias/{id}` en este módulo. |

**CRUD**: Create (`repository.py:58-59`), Read (`obtener_categoria`,
`repository.py:69-71`; `listar_categorias`, `repository.py:62-66`), Update
(`repository.py:74-75`). Sin Delete, ni físico ni lógico.

## `marcas`, `envases`, `caracteristicas` (migración 0016)

Mismo shape entre las tres — catálogo por drogueria sin `descripcion` (a
diferencia de `categorias`: el nombre alcanza para una marca, un envase o una
característica; no se replicó `descripcion` para no sobre-normalizar un
catálogo cuyo único dato relevante es el nombre). `repository.py:80-147`
implementa las tres con un mismo set de helpers genéricos parametrizados por
nombre de tabla (`_crear_catalogo`, `_listar_catalogo`, `_obtener_catalogo`,
`_actualizar_catalogo`, `repository.py:80-99`).

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK. |
| `drogueria_id` | FK a `droguerias`. `UNIQUE(drogueria_id, nombre)` en las tres tablas. |
| `nombre` | NOT NULL. Escrita al crear, actualizable parcialmente. |
| `activa` | BOOLEAN, default `TRUE`. Filtro opcional en los tres `listar_*` (mismo patrón que `categorias.activa`). |

**CRUD**: Create, Read (obtener + listar), Update — igual que `categorias`.
Sin Delete, ni físico ni lógico (mismo criterio que `categorias`).

## `producto_caracteristicas` (migración 0016)

Tabla puente N:M entre `productos` y `caracteristicas` — reemplaza lo que en
el maestro legado era un campo de texto único de "características especiales"
(psicotrópico, heladera, vale...). Sin campo mutable propio: la fila existe o
no existe, así que no hay `UPDATE`, solo alta y baja (`repository.py:150-173`).

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK. |
| `drogueria_id` | FK a `droguerias`. |
| `producto_id` | FK a `productos` (simple, sin `UNIQUE(id, drogueria_id)` compuesto — `productos` no usa ese patrón). |
| `caracteristica_id` | FK a `caracteristicas`. `UNIQUE(producto_id, caracteristica_id)` — un producto no puede tener la misma característica asignada dos veces. |
| `created_by` | Escrita al asignar (`service.py`, `asignar_caracteristica_producto`). |

**CRUD**: Create (asignar, `repository.py:162-163`), Read (`listar_caracteristicas_producto`,
`repository.py:152-159`), Delete físico (quitar, `repository.py:166-173`). Sin Update.

## `proveedores`

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK. |
| `drogueria_id` | FK a `droguerias`. Fijada al crear (`service.py:128`); filtro de tenant en `listar_proveedores` (`repository.py:90`) y comparación de pertenencia en `obtener_proveedor` (`service.py:151`, RN-PRODUCTOS-001). |
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
| `costo_unitario` | `Decimal`. Comparada contra el vigente para decidir si hay que versionar o no (`service.py:201`, RN-PRODUCTOS-005). |
| `fecha_desde` | `date`. Usada para calcular la `fecha_hasta` del costo que se cierra (`service.py:205`, RN-PRODUCTOS-006). |
| `fecha_hasta` | Nullable. `IS NULL` es la condición de "costo vigente" (`repository.py:142`, RN-PRODUCTOS-006) — no hay un enum de estado, es una columna de fecha usada como bandera de vigencia. |
| `origen` | Hardcodeada a `"manual"` en todo alta hecha por este módulo (`service.py:216`, RN-PRODUCTOS-007). `imports/service.py` escribe `"import_sistema"` para la misma tabla, con el mismo algoritmo reimplementado (ver [`arquitectura.md`](./arquitectura.md)). |

**CRUD**: Create/versionado (`crear_costo`, `service.py:195-218` →
`repository.py:149-150`; cierre del vigente, `repository.py:153-154`), Read
(`listar_costos`, `repository.py:126-134`; `costo_vigente`, `repository.py:137-146`).
Sin Update libre (solo `fecha_hasta` vía `cerrar_costo_vigente`) ni Delete.

## `stock_productos`

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK. |
| `producto_id` | FK a `productos`. Parte de la clave `UNIQUE(producto_id, deposito)` usada por el `upsert` (`repository.py:188`, RN-PRODUCTOS-008). |
| `drogueria_id` | FK a `droguerias`. Escrita en cada upsert (`service.py:246`), no leída por este módulo tras la escritura. |
| `deposito` | Nullable en el modelo (`StockAjuste.deposito`, `models.py:124`), pero nunca `None` en la fila final: si no se especifica, se usa `DEPOSITO_SENTINEL` (`"unico"`, ver RN-PRODUCTOS-009). Segunda parte de la clave `UNIQUE(producto_id, deposito)`. |
| `cantidad_disponible` | Único campo que este módulo escribe en `ajustar_stock` (`service.py:236-250`, RN-PRODUCTOS-010). También la descuenta `core/stock.py` al confirmar entregas de OC — ver [`arquitectura.md`](./arquitectura.md) para el detalle de este escritor concurrente. |
| `cantidad_comprometida` | **Nunca escrita por este módulo.** Mantenida exclusivamente por `core/stock.py` (comentario explícito en el código, RN-PRODUCTOS-010). |

**CRUD**: Read (`listar_stock`, `repository.py:159-167`;
`buscar_stock_por_deposito`, `repository.py:170-182`), upsert idempotente
(`upsert_stock`, `repository.py:185-191`, `on_conflict="producto_id,deposito"`). Sin
Delete.

## Resumen CRUD y soft-delete

| Tabla | CRUD | Soft-delete |
|---|---|---|
| `productos` | C/R/U/soft-D | Sí. `deleted_at`/`deleted_by`/`activo=False` (`repository.py:46-53`). |
| `categorias` | C/R/U | No — ni soft ni físico. Sin endpoint `DELETE`. |
| `marcas` | C/R/U | No — ni soft ni físico. |
| `envases` | C/R/U | No — ni soft ni físico. |
| `caracteristicas` | C/R/U | No — ni soft ni físico. |
| `producto_caracteristicas` | C/R/D (físico) | No aplica — es una asociación, se borra directo. |
| `proveedores` | C/R/U/soft-D | Sí. `deleted_at`/`deleted_by`/`activo=False` (`repository.py:114-121`). |
| `costos_productos` | C/R/U (solo `fecha_hasta`) | No. Vigencia se resuelve con `fecha_hasta IS NULL`. |
| `stock_productos` | R/upsert | No aplica — es una tabla de magnitudes, no de entidades dadas de baja. |

Sobre las políticas RLS de estas 5 tablas: no se encontró en este módulo (ni se
verificó en esta sesión) un archivo equivalente a `docs/schema/rls_final.sql` con el
detalle de cada policy — pendiente de definición funcional si se necesita ese nivel
de detalle. Los `GET` de este módulo usan `user_client` (con RLS) y las escrituras
usan `service_client` (sin RLS) vía los wrappers `*_para_endpoint` — ver
[`../core/`](../core/) para el patrón general.
