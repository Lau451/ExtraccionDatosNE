# Base de datos — Imports

Imports **no es dueño** de ninguna tabla: las 5 tablas que toca pertenecen a
[`catalogo/`](../catalogo/) (`productos`, `costos_productos`, `stock_productos`,
`proveedores`) y a [`clientes/`](../clientes/) (`clientes`). Esta página documenta
únicamente qué columnas escribe y lee **este módulo**; para el detalle completo de cada
tabla (incluyendo columnas que Imports no toca) ver
[`../catalogo/base_de_datos.md`](../catalogo/base_de_datos.md) y
[`../clientes/base_de_datos.md`](../clientes/base_de_datos.md).

## `productos`

| Columna | Qué hace este módulo |
|---|---|
| `drogueria_id` | Fijada del solicitante (`router.py`, vía `usuario.drogueria_id`); filtro de todas las queries (`repository.py:13`, `:24`, `:45`, `:57`). |
| `codigo_interno` | Clave de reconciliación: decide alta vs. actualización (`service.py:54`) y es la clave del `upsert` en `on_conflict="drogueria_id,codigo_interno"` (`repository.py:39`). |
| `nombre`, `categoria_id`, `clasificacion`, `droga`, `presentacion`, `forma_farmaceutica`, `laboratorio`, `codigo_anmat`, `datos_sistema` | Escritas 1:1 desde `ImportProductoRow` en cada alta/actualización (`service.py:39-50`), sin ninguna validación adicional (no resuelve si `categoria_id` existe, por ejemplo). |
| `activo` | Forzada a `True` en cada alta/actualización (`service.py:51`); forzada a `False` por `desactivar_productos` para lo no presente en el lote (RN-IMPORTS-001). |
| `created_by`, `updated_by` | `updated_by` siempre; `created_by` solo en la rama de alta (RN-IMPORTS-011). |
| `deleted_at` | **Nunca escrita por este módulo.** Solo leída como filtro (`is_("deleted_at", None)`) en `codigos_activos_productos` (`repository.py:26`). Contraste: `catalogo.soft_delete_producto` sí la escribe — ver [`arquitectura.md`](./arquitectura.md) y [`pendientes.md`](./pendientes.md) para la implicación de esta diferencia de semántica. |

## `costos_productos`

| Columna | Qué hace este módulo |
|---|---|
| `producto_id` | Resuelto por `mapear_productos_por_codigo` a partir de `codigo_interno` (`repository.py:49-61`); usado para agrupar costos vigentes (`repository.py:66-76`). |
| `drogueria_id` | Escrita en cada `INSERT` (`service.py:111`, `:128`). |
| `costo_unitario` | Comparada contra el vigente para decidir alta/versionado/`sin_cambios` (RN-IMPORTS-009/010). |
| `fecha_desde`, `fecha_hasta` | `fecha_desde` viene del lote; `fecha_hasta=None` en toda fila nueva; el costo cerrado recibe `fecha_hasta = fecha_desde_nueva - 1 día` (`service.py:120-123`). |
| `origen` | Siempre `"import_sistema"` (`service.py:115`, `:132`) — distingue estas filas de las creadas por `catalogo.crear_costo` (`"manual"`). |

**Sin `created_by`/`updated_by`** en este bloque: a diferencia de productos/proveedores/clientes,
las filas de `costos_productos` insertadas por este módulo no llevan atribución de
usuario más allá de `origen`.

## `stock_productos`

| Columna | Qué hace este módulo |
|---|---|
| `producto_id` | Resuelto por `mapear_productos_por_codigo` (compartida con el flujo de costos). |
| `drogueria_id` | Escrita en cada fila del upsert (`service.py:168`). |
| `deposito` | Del lote, o `DEPOSITO_SENTINEL` (`"unico"`) si viene vacío (RN-IMPORTS-006). Parte de la clave `on_conflict="producto_id,deposito"` del upsert (`repository.py:91`). |
| `cantidad_disponible` | Sobrescrita en cada upsert (`service.py:170`). |
| `cantidad_comprometida` | **Nunca tocada por este módulo** — no aparece en el dict del upsert (`service.py:166-174`). Verificado en `tests/imports/test_service.py:348-371` (`test_importar_stock_no_toca_cantidad_comprometida`) — mismo criterio que `catalogo.ajustar_stock` (RN-CATALOGO-010). |

## `proveedores`

| Columna | Qué hace este módulo |
|---|---|
| `drogueria_id` | Filtro de todas las queries del bloque (`repository.py:104`, `:115`, `:137`). |
| `codigo_interno` | Clave de reconciliación cuando existe (RN-IMPORTS-002); si es `None`, la fila siempre se trata como alta (RN-IMPORTS-008). |
| `razon_social`, `nombre_comercial`, `cuit`, `tipo`, `plazo_pago_dias`, `condiciones_pago` | Escritas 1:1 desde `ImportProveedorRow` (`service.py:203-211`); `tipo` con default `"otro"` si no viene (`service.py:207`). |
| `es_competidor`, `es_proveedor_compra` | Con default explícito si el campo viene `None`: `es_competidor` default `True`, `es_proveedor_compra` default `False` (`service.py:208-209`) — únicos dos booleanos de todo el módulo con default distinto de simplemente "omitir". |
| `activo` | Forzada a `True` en cada alta/actualización (`service.py:212`); forzada a `False` por `desactivar_proveedores` para lo no presente en el lote, acotado a los que tienen `codigo_interno` (RN-IMPORTS-002). |
| `created_by`, `updated_by` | Mismo patrón que productos (RN-IMPORTS-011). |
| `deleted_at` | Solo leída como filtro (`repository.py:117`), nunca escrita por este módulo. |

## `clientes`

| Columna | Qué hace este módulo |
|---|---|
| `drogueria_id` | Filtro de todas las queries del bloque (`repository.py:151`, `:162`). |
| `codigo_interno` | Clave de reconciliación (RN-IMPORTS-003). **Es la única vía confirmada en este proyecto que escribe `codigo_interno` en `clientes`** — `clientes.service.crear_cliente` no lo hace (confirmado cruzando con [`../clientes/pendientes.md`](../clientes/pendientes.md) P3(4)). |
| `nombre`, `tipo` | **Requeridos solo en la rama de alta** (`service.py:294-297`, `ValidationError` si faltan); opcionales en la rama de actualización — solo se pisan si vienen en el lote (`service.py:286-289`). |
| `direccion`, `ciudad`, `provincia`, `codigo_postal`, `plazo_pago_dias`, `condiciones_pago` | `campos_opcionales`: solo se incluyen en el dict si el valor no es `None` (`service.py:271-282`) — actualización parcial real, verificada en `tests/imports/test_service.py:529-563` (`test_importar_clientes_actualiza_sin_pisar_campos_no_enviados`). |
| `activo` | Forzada a `True` **solo en la rama de alta** (`service.py:305`); **no se toca en la rama de actualización** — asimetría real respecto a productos/proveedores, ver RN-IMPORTS-007. |
| `created_by`, `updated_by` | `created_by` y `updated_by` en la rama de alta (`service.py:306-307`); solo `updated_by` en la de actualización (`service.py:290`). |
| `deleted_at` | Solo leída como filtro (`repository.py:164`), nunca escrita por este módulo. |

## Resumen: reconciliación por tabla

| Tabla | Reconciliación completa (desactiva lo faltante) | Reactivación al reaparecer |
|---|---|---|
| `productos` | Sí (RN-IMPORTS-001) | Sí — `"activo": True` en cada actualización |
| `proveedores` | Sí, solo con `codigo_interno` (RN-IMPORTS-002) | Sí — mismo patrón que productos |
| `clientes` | Sí (RN-IMPORTS-003) | **No** — RN-IMPORTS-007 |
| `costos_productos` | No — versionado temporal, no hay "faltante" (RN-IMPORTS-004) | N/A |
| `stock_productos` | No — upsert puro, sin lectura de estado previo (RN-IMPORTS-005) | N/A |

Sobre RLS de estas 5 tablas: no se encontró en este módulo ningún archivo de policies
citado; los 5 endpoints usan `service_client` (sin RLS) de forma exclusiva, por lo que
las policies de `SELECT`/`INSERT`/`UPDATE` de estas tablas no son relevantes para el
comportamiento de este módulo — pendiente de definición si se necesita el detalle
completo de cada policy.
