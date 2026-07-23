# Base de datos — Pricing

Pricing no es dueño de ninguna tabla. Lee 7 tablas/vistas de otros módulos y escribe
en 2 tablas que comparte con `presupuestos/` (ver
[`arquitectura.md`](./arquitectura.md) para el detalle del solapamiento).

## Solo lectura

### `precios_proveedor`

| Columna | Uso |
|---|---|
| `item_proceso_id` | Filtro de `buscar_precio_especial_puntual` (`repository.py:28`) — precio especial atado a un ítem concreto. `NULL` es el filtro de `buscar_precio_especial_general` (`repository.py:44`, `.is_("item_proceso_id", None)`) — precio especial genérico por producto. |
| `producto_id`, `drogueria_id` | Filtro de `buscar_precio_especial_general` (`repository.py:45-46`). |
| `activa` | Filtro `eq(True)` en ambas búsquedas (`repository.py:29`, `:47`). |
| `mantenimiento_hasta` | Filtro `gte(hoy)` en ambas búsquedas — precio especial vencido no se considera (`repository.py:30`, `:48`). |
| `precio_unitario` | Orden ascendente en la query (`repository.py:31`, `:49`); es el costo especial candidato que compite contra el costo estándar en `resolver_costo` (RN-PRICING-001). |
| `cantidad_minima`, `cantidad_maxima` | Resueltas en Python por `_primero_en_rango` (`repository.py:9-18`), no en la query SQL — la primera fila (ya ordenada por precio) cuyo rango contiene la `cantidad` del ítem. |

**CRUD de este módulo**: solo Read. Confirmado por grep exhaustivo en esta sesión
sobre `services/presupuestacion/`: ningún módulo del backend hace `insert`, `update`
ni `delete` sobre `precios_proveedor` — ver [`pendientes.md`](./pendientes.md) P1. Los
tests de integración (`tests/pricing/test_service.py:71-85`) insertan filas de esta
tabla directo con `service_client`, sin pasar por ninguna función de aplicación.

### `costos_productos`

| Columna | Uso |
|---|---|
| `producto_id` | Filtro de `buscar_costo_estandar_vigente` (`repository.py:59`). |
| `fecha_hasta` | `IS NULL` es la condición de vigencia (`repository.py:60`) — misma semántica que `catalogo.repository.costo_vigente`, reimplementada de forma independiente (ver [`arquitectura.md`](./arquitectura.md)). |
| `costo_unitario` | Es el costo estándar candidato en `resolver_costo` (RN-PRICING-001). |

**CRUD de este módulo**: solo Read (`repository.py:55-64`). El alta/versionado de
esta tabla es responsabilidad de [`../catalogo/`](../catalogo/) (RN-CATALOGO-005/006).

### `reglas_pricing`

| Columna | Uso |
|---|---|
| `drogueria_id` | Filtro `eq` (`repository.py:84`). |
| `activa` | Filtro `eq(True)` (`repository.py:85`). |
| `cliente_id`, `clase_proceso`, `categoria_id` | Cada uno pasa por `_alcance_or` (`repository.py:67-70`): la regla aplica si la columna es `NULL` (alcance general) o coincide con el valor recibido (alcance específico) — ver RN-PRICING-004 y el riesgo de inyección en [`pendientes.md`](./pendientes.md) P1. |
| `prioridad` | `ORDER BY prioridad DESC LIMIT 1` (`repository.py:89-90`) — de entre las reglas que matchean los 3 alcances, gana la de mayor prioridad. |
| `margen_minimo_pct` | Base del piso de margen (RN-PRICING-002). |
| `margen_objetivo_pct` | Fallback cuando no hay precio de mercado (RN-PRICING-006). Puede ser `NULL` — en ese caso, sin mercado, `calcular_precio` devuelve `None` (`service.py:83-85`). |
| `meses_ventana_mercado` | Ventana de meses hacia atrás para buscar muestras de mercado (`repository.py:99`, `relativedelta(months=meses_ventana)`). |
| `descuento_vs_mercado_pct` | Descuento aplicado sobre la mediana de mercado para calcular la `referencia` (RN-PRICING-003). Puede ser `NULL`, tratado como `0` (`service.py:68`). |

**CRUD de este módulo**: solo Read (`repository.py:73-93`). Confirmado por grep
exhaustivo: ningún módulo del backend inserta, actualiza ni elimina filas de
`reglas_pricing` — ver [`pendientes.md`](./pendientes.md) P1. Los tests siembran
reglas directo con `service_client` (`tests/pricing/conftest.py:34-46`).

### `v_precio_mercado_producto` (vista)

| Columna | Uso |
|---|---|
| `producto_id`, `drogueria_id` | Filtro `eq` (`repository.py:103-104`). |
| `ultima_muestra` | Filtro `gte(desde)`, donde `desde = hoy - meses_ventana_mercado` (`repository.py:99-105`). |
| `precio_mediana` | Precio de referencia de mercado (RN-PRICING-003). |
| `muestras` | Cantidad de muestras que componen la mediana, propagada a `DetalleCalculo.muestras` (`service.py:74`) sin usarse en ningún cálculo. |

No se encontró en este repositorio la definición SQL de esta vista (no hay
migraciones de `presupuestacion/` versionadas localmente); a partir de los fixtures
de test (`tests/pricing/test_service.py:130-150`, que siembran `comparativas` +
`ofertas_items` con `adjudicacion_estimada=True` y luego ven reflejado el precio en
`v_precio_mercado_producto`), se infiere que la vista agrega precios de
`ofertas_items`/`comparativas` — inferencia a partir de tests, no verificación
directa de la vista.

### `stock_productos`

| Columna | Uso |
|---|---|
| `producto_id` | Filtro `eq` (`repository.py:115`) — trae **todas** las filas (todos los depósitos) de ese producto. |
| `cantidad_disponible`, `cantidad_comprometida` | Sumadas por separado en Python y restadas: `libre = sum(disponible) - sum(comprometida)` (`repository.py:119-121`) — stock libre total del producto, no por depósito. |

**CRUD de este módulo**: solo Read (`repository.py:112-121`), y solo si
`clase_proceso == "cotizacion"` (RN-PRICING-005). El motor de escritura de esta
tabla es `core/stock.py` (compromiso/descuento) y `catalogo.ajustar_stock` (ajuste
manual) — ver [`../catalogo/base_de_datos.md`](../catalogo/base_de_datos.md).

### `productos`

| Columna | Uso |
|---|---|
| `id` | Filtro `eq` (`repository.py:127`). |
| `categoria_id` | Único dato realmente usado del resultado: se pasa a `buscar_regla_aplicable` para resolver el alcance por categoría (`service.py:127`). |
| `drogueria_id` | Traído por el `select` (`repository.py:127`) pero no usado en ningún punto del módulo tras la consulta. |

**CRUD de este módulo**: solo Read (`repository.py:124-132`).

### `procesos_comerciales`

| Columna | Uso |
|---|---|
| `id` | Filtro `eq` (`repository.py:139`). |
| `drogueria_id`, `cliente_id`, `clase` | Traídos por `generar_presupuesto` para propagar a `calcular_item` de cada ítem (`service.py:230-234`) y, en el caso de `drogueria_id`, para las filas nuevas de `presupuestos`/`presupuesto_items`. |

**CRUD de este módulo**: solo Read (`repository.py:135-143`).

### `items_proceso`

| Columna | Uso |
|---|---|
| `proceso_comercial_id` | Filtro `eq` (`repository.py:162`). |
| `producto_id` | Filtro `NOT NULL` (`repository.py:163`, `.not_.is_("producto_id", None)`) — **los ítems sin producto identificado quedan completamente fuera de `generar_presupuesto`**, no generan fila `sin_precio`, no cuentan en `cantidad_items` ni en `items_sin_precio`. Ver RN-PRICING-007 en [`reglas.md`](./reglas.md). |
| `cantidad`, `id` (como `item_proceso_id`) | Usados en el cálculo de cada ítem. |

**CRUD de este módulo**: solo Read (`repository.py:158-166`). El alta de ítems y su
resolución de `producto_id` es responsabilidad de otros módulos (matching/carga
manual del proceso comercial), no documentados en este archivo.

## Escritura (compartida con `presupuestos/`)

### `presupuestos`

| Columna | Qué escribe este módulo |
|---|---|
| `proceso_comercial_id`, `drogueria_id` | Fijadas al crear (`service.py:256-257`). |
| `estado` | Fijado a `"generado"` únicamente al crear (`service.py:258`) — este módulo nunca hace una transición de estado, solo la inserción inicial. |
| `monto_total`, `cantidad_items`, `items_sin_precio` | Escritos al crear (`service.py:259-261`) y reescritos por completo en cada regeneración (`service.py:277-282`), con auditoría de los campos que efectivamente cambiaron (`service.py:290-304`). |
| `id` | Leído de vuelta tras el `insert` (`service.py:263`) para encadenar la inserción de `presupuesto_items`. |

**CRUD de este módulo**: Create (alta inicial) y Update (regeneración de un
presupuesto abierto). Sin Delete. La transición a `"aprobado"`/`"presentado"`/etc. la
hace `presupuestos/` — ver [`arquitectura.md`](./arquitectura.md).

### `presupuesto_items`

| Columna | Qué escribe este módulo |
|---|---|
| Todas las columnas de `ResultadoPricingItem` (ver `_a_fila_presupuesto_item`, `service.py:187-216`) | `presupuesto_id`, `drogueria_id`, `item_proceso_id`, `producto_id`, `precio_unitario`, `cantidad_ofertada`, `regla_pricing_id`, `metodo_precio`, `costo_usado`, `origen_costo`, `precio_proveedor_id`, `mantenimiento_hasta_usado`, `precio_mercado_usado`, `margen_resultante_pct`, `detalle_calculo` (JSON), `stock_verificado`, `stock_al_generar`. |

**CRUD de este módulo**: Create (alta inicial, `service.py:308`) y Delete+Create
completo en cada regeneración (`service.py:275`, `:307-308`) — nunca un `UPDATE`
parcial de una fila existente. El ajuste manual de una fila individual
(`precio_unitario`, `cantidad_ofertada`, `excluido`, `motivo_exclusion`) es
responsabilidad de `presupuestos.ajustar_item` — y se **pierde** si `pricing`
regenera después (ver [`arquitectura.md`](./arquitectura.md)).

## Resumen CRUD

| Tabla/vista | CRUD de este módulo |
|---|---|
| `precios_proveedor` | R |
| `costos_productos` | R |
| `reglas_pricing` | R |
| `v_precio_mercado_producto` | R |
| `stock_productos` | R (condicional, RN-PRICING-005) |
| `productos` | R |
| `procesos_comerciales` | R |
| `items_proceso` | R |
| `presupuestos` | C/U (compartida con `presupuestos/`, que agrega el resto del ciclo de vida) |
| `presupuesto_items` | C/D+C (compartida con `presupuestos/`, que agrega U parcial vía `ajustar_item`) |
