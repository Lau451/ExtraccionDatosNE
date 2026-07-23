# Arquitectura — Pricing

## Dependencias hacia Core

| Import | Origen | Uso |
|---|---|---|
| `registrar_cambios`, `registrar_evento_ciclo_vida` | `core/audit.py` | Auditoría de la creación y de la regeneración de un presupuesto (`service.py:8`). |
| `get_service_client` | `core/database.py` | Cliente sin RLS, resuelto internamente por `generar_presupuesto_para_endpoint` (`service.py:9`, `:324`). |
| `NotFoundError` | `core/exceptions.py` | Levantada si el proceso comercial no existe (`service.py:224`). |
| `UsuarioPerfil`, `require_roles` | `core/auth.py` | Perfil del solicitante y autorización por rol en los 2 endpoints (`router.py:4`). |
| `get_user_client` | `core/database.py` | Cliente con RLS, inyectado en `generar_presupuesto_endpoint` para leer `procesos_comerciales` y validar pertenencia antes de delegar (`router.py:5`, `:20`), y en `precios_especiales_endpoint` para leer la vista directo (`router.py:46`). |
| `ForbiddenError` | `core/exceptions.py` | Levantada por el router si la droguería del proceso no coincide con la del solicitante (`router.py:6`, `:34`). |

Ver [`../core/`](../core/) para la documentación de estas piezas — no se repite acá.
Pricing no tiene ningún import cruzado hacia otro módulo de negocio o de soporte que
no sea Core (confirmado leyendo `service.py`, `repository.py` y `router.py`
completos en esta sesión) — a diferencia de [`../catalogo/`](../catalogo/), que sí
importa `DEPOSITO_SENTINEL` de `imports/service.py`.

## Acoplamiento de tabla con Catálogo (fuera de este código Python)

`pricing/repository.py` lee `productos`, `costos_productos` y `stock_productos`
directo, sin pasar por `catalogo.service` ni `catalogo.repository` — mismo patrón de
acoplamiento que ya documenta [`../catalogo/arquitectura.md`](../catalogo/arquitectura.md),
donde Pricing ya figura como uno de los 5 consumidores del diagrama de esa página:

- `repository.py:57` (`buscar_costo_estandar_vigente`): `SELECT * FROM
  costos_productos WHERE producto_id=? AND fecha_hasta IS NULL LIMIT 1` — la misma
  condición de vigencia que usa `catalogo.repository.costo_vigente`
  (`catalogo/repository.py:137-146`), reimplementada de forma independiente en este
  módulo.
- `repository.py:114-121` (`buscar_stock_libre`): lee `cantidad_disponible,
  cantidad_comprometida` de `stock_productos` para **todas** las filas de un
  `producto_id` (todos los depósitos) y calcula `disponible - comprometida` en
  Python, sumando cada columna por separado antes de restar.
- `repository.py:126-132` (`buscar_producto`): `SELECT id, categoria_id,
  drogueria_id FROM productos WHERE id=? LIMIT 1` — usado únicamente para resolver
  `categoria_id` antes de buscar la regla de pricing aplicable (`service.py:121-128`).

Ninguna de las tres reimplementa una regla de negocio de Catálogo con un algoritmo
distinto (a diferencia del caso de `imports/service.py` con el versionado de costo,
documentado en [`../catalogo/arquitectura.md`](../catalogo/arquitectura.md)) — son
lecturas puntuales por `id`, sin lógica de escritura.

## Solapamiento de responsabilidad con `presupuestos/`

Pricing y `presupuestos/` (`services/presupuestacion/presupuestos/`, código ya
existente pero sin documentación formal en `docs/modulos/` a la fecha de esta
sesión) escriben la misma tabla `presupuestos` y comparten un mismo campo derivado
que cada uno calcula con **criterio distinto**.

### Pricing crea; `presupuestos/` gestiona el ciclo de vida posterior

- **Pricing** (`generar_presupuesto`, `service.py:219-316`) es el único punto del
  código que hace el primer `INSERT` en `presupuestos` (`service.py:263`, estado
  inicial `"generado"`) y que borra y reinserta por completo `presupuesto_items` en
  cada regeneración (`service.py:275`, `:307-308`).
- **`presupuestos/`** (`presupuestos/service.py`) opera sobre presupuestos ya
  creados: `aprobar_presupuesto` (`presupuestos/service.py:91-128`, transición a
  `"aprobado"`, valida que no queden ítems `sin_precio` sin resolver),
  `ajustar_item` (`presupuestos/service.py:131-177`, edición manual de
  `precio_unitario`/`cantidad_ofertada`/exclusión de un `presupuesto_item`) y
  `presentar_presupuesto` (`presupuestos/service.py:180-255`, transición a
  `"presentado"`, compromete stock vía `core/stock.py` si el proceso es
  `"cotizacion"`, y actualiza `procesos_comerciales.estado`). Ninguna de estas tres
  funciones vive en `pricing/`, ni `pricing/` las importa.

### El mismo par de campos derivados, recalculado dos veces con criterios distintos

- **Pricing** (`service.py:238-249`): `monto_total` = suma de `precio_unitario *
  cantidad_ofertada` de **todos** los resultados con precio; `cantidad_items` =
  `len(resultados)` (cuenta también los `sin_precio`); `items_sin_precio` = cuenta de
  `metodo_precio == "sin_precio"`. No existe el concepto de ítem excluido en este
  módulo.
- **`presupuestos/`** (`_recalcular_totales_presupuesto`,
  `presupuestos/service.py:41-88`, invocada desde `ajustar_item`): recalcula
  `monto_total` e `items_sin_precio` a partir de `listar_items_presupuesto`, pero
  **excluyendo** los ítems con `excluido=True` (`presupuestos/service.py:45`,
  `activos = [i for i in items if not i["excluido"]]`) — un concepto que no existe
  en el cálculo de Pricing porque `excluido` es un campo que solo `presupuestos/`
  escribe (`ajustar_item`, `presupuestos/service.py:162-164`).

No hay una función compartida entre ambos módulos para este cálculo: son dos
implementaciones independientes de "sumar precio × cantidad de los ítems vigentes",
con una noción de "vigente" que difiere (todos vs. no-excluidos) porque Pricing no
conoce el campo `excluido`. Si `generar_presupuesto` se invoca sobre un presupuesto
que ya tiene ítems ajustados/excluidos manualmente por `presupuestos/`
(`ajustar_item`), **la regeneración los borra y los vuelve a calcular desde cero**
(`service.py:275`, `DELETE ... WHERE presupuesto_id=?` sin excepción para ítems
editados manualmente) — cualquier ajuste manual previo (precio fijado a mano,
exclusión, motivo) se pierde. Ver [`pendientes.md`](./pendientes.md) P1 para el
detalle de riesgo.

### Regenerar después de aprobar/presentar crea un presupuesto nuevo, no reabre el existente

`buscar_presupuesto_abierto` (`repository.py:146-155`) solo considera "abierto" un
presupuesto en estado `"generado"` o `"en_revision"` (`.in_("estado", ["generado",
"en_revision"])`). Si un presupuesto ya avanzó a `"aprobado"`, `"presentado"`,
`"adjudicado"`, `"rechazado"` o `"vencido"` (los 7 valores de `EstadoPresupuesto`,
`presupuestos/models.py:6-8`) y se vuelve a llamar
`POST /procesos/{id}/generar-presupuesto` para el mismo proceso comercial,
`existente` es `None` (`service.py:251-252`) y el código toma la rama de alta
(`service.py:254-272`): **inserta una fila nueva** en `presupuestos` para el mismo
`proceso_comercial_id`, en vez de rechazar la operación o reabrir la existente. No se
pudo verificar en esta sesión si existe una constraint `UNIQUE(proceso_comercial_id)`
o similar a nivel de base de datos que lo impida — no hay migraciones SQL de
`presupuestacion/` en este repositorio (el schema se administra directo en Supabase,
ver memoria de proyecto). Ver [`pendientes.md`](./pendientes.md) P1.

## Diagrama de acoplamiento

```
                    productos / costos_productos / stock_productos
                               │
        ┌──────────┬───────────┼───────────┬──────────────┐
        │          │           │           │              │
   catalogo/   matching/  comparativas/ pricing/     core/stock.py
   (dueño)     (lee       (lee          (lee          (compromete/
               productos) proveedores)  costos,       descuenta
                                        stock,        comprometida/
                                        productos)    disponible)

                          presupuestos (tabla)
                               │
              ┌────────────────┴────────────────┐
              │                                  │
         pricing/                          presupuestos/
   (INSERT inicial "generado",         (aprobar/ajustar/presentar,
    DELETE+INSERT en regeneración      recalcula monto_total con
    de presupuesto_items)              criterio propio: excluye
                                        ítems `excluido=True`)
```

Ver [`../catalogo/arquitectura.md`](../catalogo/arquitectura.md) para el detalle
completo del primer diagrama (ya documentado ahí, con Pricing como consumidor).
