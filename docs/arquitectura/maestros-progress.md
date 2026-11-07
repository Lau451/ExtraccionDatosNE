# Maestros de Progress: quién escribe cada campo

Productos y terceros se dan de alta en Progress (etapa 7, `odd/tasks/maestros-solo-lectura.md`).
La app los recibe por las importaciones (`POST /imports/{productos,costos,stock,clientes,proveedores}`,
`services/presupuestacion/imports/`) y solo escribe los campos que Progress no manda.

Regla: un campo de **Progress** lo escribe únicamente la importación. Si la app lo
modificara, la próxima importación lo pisaría (P4: lo que viene de Progress es una réplica,
nunca una segunda verdad). Un campo de la **app** no lo toca la importación.

Las columnas técnicas (`id`, `drogueria_id`, `created_at`, `updated_at`, `created_by`,
`updated_by`) las completa quien crea o modifica la fila y no se listan.

## Productos

### `productos`

| Columna | Dueño | Notas |
|---------|-------|-------|
| `codigo_interno` | Progress | Clave del upsert `(drogueria_id, codigo_interno)`. |
| `nombre`, `droga`, `presentacion`, `forma_farmaceutica`, `codigo_anmat`, `alicuota_iva`, `clasificacion` | Progress | |
| `categoria_id`, `marca_id`, `envase_id` | Progress | El archivo trae el id de nuestro catálogo; los catálogos (`categorias`, `marcas`, `envases`) se siguen administrando en la app para que esos ids existan. |
| `unidades_por_presentacion` | Progress | Derivado de `presentacion` al importar (`productos/domain.py`). |
| `datos_sistema` | Progress | Fila original del archivo. |
| `activo` | Progress | Un producto que no viene en el archivo queda `activo = false`. |
| `deleted_at`, `deleted_by` | — | Sin uso: la baja manual se eliminó. |

### `producto_caracteristicas` y catálogos

| Tabla | Dueño | Notas |
|-------|-------|-------|
| `producto_caracteristicas` | App | Progress no las manda; se asignan y quitan desde la ficha del producto. |
| `categorias`, `marcas`, `envases`, `caracteristicas` | App | Catálogos propios. |

### `costos_productos`

| Columna | Dueño | Notas |
|---------|-------|-------|
| Todas | Progress | Se versionan con `services/productos/api.py::versionar_costos` y `origen = 'import_sistema'`. Las filas con `origen = 'manual'` son históricas: el alta manual de costo se eliminó. |

### `stock_productos`

| Columna | Dueño | Notas |
|---------|-------|-------|
| `deposito`, `cantidad_disponible` | Progress | Upsert por `(producto_id, deposito)`. |
| `cantidad_comprometida` | App | La mantiene el motor de compromiso de stock (`services/presupuestacion/core/stock.py`). |

Al confirmar la entrega de una OC la app solo libera `cantidad_comprometida`
(`core/stock.py::entregar_stock_producto`); el descuento de `cantidad_disponible` lo hace
Progress y llega con la próxima importación de stock.

## Terceros

### `terceros`

| Columna | Dueño | Notas |
|---------|-------|-------|
| `codigo_interno`, `razon_social`, `cuit`, `cuit_no_exclusivo` | Progress | Los escribe `upsert_terceros_legacy` (migración 0024). |
| `activo` | Progress | La importación lo reactiva cuando el tercero vuelve a venir. |
| `nombre_fantasia`, `email`, `telefono`, `sitio_web`, `notas` | App | `PATCH /terceros/{id}` acepta solo estos; cualquier otro campo responde 422. |
| `deleted_at`, `deleted_by` | — | Sin uso. |

`terceros_legacy_map` lo escribe solo la importación.

### `clientes` y `proveedores` (roles)

| Columna | Dueño | Notas |
|---------|-------|-------|
| `tipo`, `activo` | Progress | El rol lo crea la importación; un tercero que deja de venir pierde el rol (`activo = false`). |
| `es_competidor`, `es_proveedor_compra` (`proveedores`) | Progress | |
| `condicion_pago_id`, `forma_pago_id` | App | `PATCH /terceros/{id}/clientes` y `.../proveedores` aceptan solo estos. |

El endpoint heredado `PATCH /clientes/{id}` sigue la misma regla: acepta `email`, `telefono`,
`condicion_pago_id` y `forma_pago_id`.

### Datos propios del tercero

| Tabla | Dueño |
|-------|-------|
| `tercero_direcciones`, `direccion_usos` | App |
| `terceros_contactos` | App |
| `sectores_contacto`, `condiciones_pago`, `formas_pago` | App |

## Endpoints eliminados

| Endpoint | Motivo |
|----------|--------|
| `POST /productos`, `PATCH /productos/{id}`, `DELETE /productos/{id}` | Alta, edición y baja de productos en Progress. |
| `POST /productos/{id}/costos` | Costos de Progress. |
| `PATCH /productos/{id}/stock` | Stock de Progress. |
| `POST /terceros` | Alta de terceros en Progress. |
| `POST /terceros/{id}/clientes`, `POST /terceros/{id}/proveedores` | Los roles los crea la importación. |
| `POST /clientes`, `DELETE /clientes/{id}` | Endpoint heredado: alta y baja en Progress. |
