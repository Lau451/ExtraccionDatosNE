# Arquitectura — Compras

## Posición del módulo

Compras depende únicamente de `core/` (`core.database`, `core.exceptions`,
`core.auth`, `core.audit`, `core.stock`); no importa código Python de ningún otro
módulo de negocio. [IMPLEMENTADO] — confirmado por inspección de imports en los 4
archivos del módulo (`compras/models.py`, `repository.py`, `service.py`, `router.py`):
las únicas importaciones fuera de `compras/` y de librerías de terceros
(`postgrest`, `supabase`, `fastapi`, `pydantic`) apuntan a
`services.presupuestacion.core.*`.

```
                    ┌─────────────────────────────┐
                    │            core/              │
                    │ database · exceptions · auth  │
                    │      audit · stock             │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │          compras/               │
                    │  models · repository · service  │
                    │            router               │
                    └───────────────┬───────────────┘
                                    │ SELECT directo (sin import de código)
                 ┌──────────────────┼──────────────────┐
                 │                  │                  │
     procesos_comerciales   ofertas_items      stock_productos
     (tabla, origen de la OC) (tabla, origen de  (tabla, ajustada vía
                              la adjudicación)     core.stock)
```

A diferencia de otros acoplamientos documentados en este repositorio (p. ej.
`presupuestos/` importando `core.stock` directamente), la relación de Compras con
`procesos_comerciales/` y `comparativas/` **no pasa por código Python**: es
acoplamiento a nivel de tabla. `repository.buscar_proceso_comercial` hace un `SELECT`
directo sobre `procesos_comerciales` (`compras/repository.py:6-14`) y
`repository.buscar_oferta_item`/`marcar_oferta_adjudicada` hacen lo propio sobre
`ofertas_items` (`compras/repository.py:56-64`) — ninguno de los dos importa una
función de `procesos_comerciales/service.py` ni de `comparativas/service.py`. Es el
mismo patrón de acoplamiento cruzado por tabla que ya señaló
[`../comparativas/README.md`](../comparativas/README.md) desde su propio lado, al
documentar que `compras/confirmar_orden_compra` lee `es_drogueria_propia` sin que exista
ningún import entre los dos módulos.

## Patrón de no reversión de entregas

Este es el hallazgo arquitectónico central del módulo: **una entrega, a diferencia de
un compromiso de stock, no se revierte si falla el ajuste de `stock_productos` que la
acompaña.**

- En [`../presupuestos/`](../presupuestos/README.md) (documentado desde el lado de
  Core en [`../core/flujo.md`](../core/flujo.md) Flujo A, pasos 3-4), si
  `stock.comprometer_stock_producto` falla para un ítem, `presentar_presupuesto`
  revierte los compromisos ya acumulados de los ítems anteriores del mismo presupuesto
  (`presupuestos/service.py:213-219`, vía `stock.liberar_o_reportar`) y relanza la
  excepción — el presupuesto completo queda sin presentar, como si el intento nunca
  hubiera ocurrido. Es seguro y necesario revertir porque comprometer stock es un acto
  reversible: reserva unidades para un pedido que todavía no se concretó.
- En Compras, `crear_entrega` (`compras/service.py:198-285`) inserta primero la fila de
  `entrega` y sus `entrega_items` (pasos 1-3 de
  [`../core/flujo.md`](../core/flujo.md) Flujo D) y **recién después** llama a
  `stock.entregar_stock_producto` por cada ítem con `producto_id`
  (`compras/service.py:269-279`). Si esa llamada agota reintentos y levanta
  `ConflictError` (ver RN-CORE-002 en [`../core/reglas.md`](../core/reglas.md)), la
  excepción se propaga tal cual — el registro de `entrega`/`entrega_items` que ya se
  insertó **no se borra ni se revierte**.

El propio docstring de `crear_entrega` (`compras/service.py:206-217`) lo explica en
esos términos exactos:

> "Nota de alcance: si `stock.entregar_stock_producto` agota reintentos para ALGÚN
> ítem (contención real), la excepción se propaga tal cual y el registro de
> entrega/items ya insertado en este momento queda como está — no se revierte. A
> diferencia del compromiso en presupuestos/ (donde revertir un compromiso fallido es
> seguro y necesario para no sobre-comprometer), acá la entrega ya ocurrió en la
> realidad; el registro parcial sirve de rastro para reconciliar a mano, no hay una
> versión 'deshacer la entrega' razonable."

La diferencia de fondo: comprometer stock es una reserva sobre algo que todavía no
pasó (revertible sin costo real). Entregar mercadería es un hecho físico que ya
ocurrió — la mercadería salió del proveedor y llegó (o no) a destino independientemente
de si el sistema logra reflejarlo en `stock_productos`. "Deshacer" el registro de la
entrega borraría evidencia de un evento real, en vez de simplemente corregir un dato.
Ver [`decisiones.md`](./decisiones.md) D-COMPRAS-001 para el detalle de esta decisión y
sus alternativas.

Esta asimetría es consistente con el resto de las decisiones de `core/stock.py`
documentadas en [`../core/decisiones.md`](../core/decisiones.md): D-CORE-003 (revertir
compromisos sin abortar ante el primer fallo, tolerando fallos parciales) y RN-CORE-008
(`entregar_stock_producto` no revierte nada si no alcanza) son ambas manifestaciones
del mismo principio de fondo aplicado en distintas capas — Core nunca revierte una
entrega parcialmente aplicada; Compras, un nivel arriba, tampoco revierte el registro
de negocio que la originó.

## `service_client` vs `user_client`

Compras sigue el mismo patrón documentado en
[`../core/arquitectura.md`](../core/arquitectura.md): los 3 casos de uso de escritura
(`crear_orden_compra`, `confirmar_orden_compra`, `crear_entrega`) reciben el `client`
como parámetro y sus wrappers `_para_endpoint` lo resuelven con
`core.database.get_service_client()` (`compras/service.py:293-295`, `:301-303`,
`:316-323`), porque la RLS de `ordenes_compra`/`oc_items`/`entregas_oc` no incluye
`superadmin` en `INSERT` (docstring de `crear_orden_compra_para_endpoint`,
`compras/service.py:291-292`) y porque liberar/descontar `stock_productos` requiere una
RLS de `UPDATE` que solo permiten los roles `admin`/`gerencia`/`compras` (docstring de
`crear_entrega_para_endpoint`, `compras/service.py:314-315`). `router.py`, en cambio,
usa `get_user_client` (RLS activa) para las validaciones de pertenencia de droguería
antes de delegar al service (`router.py:26-42`, `_validar_oc_de_la_drogueria`) y para
los 2 endpoints de solo lectura (`router.py:98-113`).
