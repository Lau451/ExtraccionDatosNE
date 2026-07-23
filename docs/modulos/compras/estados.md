# Estados — Compras

A diferencia de [`../core/`](../core/README.md) (que documenta explícitamente por qué
**no** tiene este archivo — no modela ninguna máquina de estados propia, ver
[`../core/README.md`](../core/README.md) "Qué NO es"), Compras sí tiene dos máquinas de
estados reales y derivadas: `ordenes_compra.estado` y `entregas_oc.estado`. Ninguna de
las dos se setea directamente desde un valor arbitrario recibido del usuario — ambas se
calculan en `service.py` a partir de datos concretos (ítems, cantidades, entregas).

## `ordenes_compra.estado`

Valores admitidos por el `CHECK` de la base (`extractor_final.sql:632`): `'pendiente'`,
`'emitida'`, `'en_entrega'`, `'parcialmente_entregada'`, `'entregada'`, `'cancelada'`.
De estos 6, el código de Compras escribe 5 — nunca `'cancelada'` (ver más abajo).

```
   crear_orden_compra          confirmar_orden_compra
  ────────────────────►  pendiente  ────────────────────►  emitida
   (service.py:62)                    (RN-COMPRAS-004,
                                        service.py:118-119,
                                        134)
                                                                │
                                                                │ crear_entrega (1ra vez,
                                                                │ ningún ítem con aceptado > 0)
                                                                ▼
                                                          en_entrega
                                                                │
                                              crear_entrega (algún ítem
                                              con aceptado > 0, no todos
                                              completos) ─┐    │
                                                           │    │ crear_entrega (algún
                                                           ▼    │ ítem con aceptado > 0,
                                          parcialmente_entregada│ no todos completos)
                                                           │    │
                                                           └────┘ (se puede quedar acá
                                                                   entrega tras entrega)
                                                           │
                                              crear_entrega (TODOS los
                                              ítems con aceptado >=
                                              cantidad pedida)
                                                           ▼
                                                       entregada

   'cancelada' — existe en el CHECK de la base, ningún código de este módulo la escribe
```

- **`pendiente`**: estado inicial, seteado literal por `crear_orden_compra`
  (`service.py:62`). Única transición de salida: confirmación (RN-COMPRAS-004) —
  también es el único estado desde el que **no** se puede registrar una entrega
  (RN-COMPRAS-006 excluye `"pendiente"` de `_ESTADOS_PARA_ENTREGA`).
- **`emitida`**: seteado literal por `confirmar_orden_compra`
  (`service.py:134`). Es uno de los 3 estados válidos para recibir una entrega.
- **`en_entrega` / `parcialmente_entregada` / `entregada`**: **nunca** seteados
  literalmente — son siempre el resultado de `_recalcular_estado_orden_compra`
  (`service.py:163-195`, RN-COMPRAS-012), que corre automáticamente al final de cada
  `crear_entrega` exitoso, agregando lo aceptado (`cantidad_entregada -
  cantidad_rechazada`) de **todas** las entregas históricas de la OC por ítem:
  - Si el aceptado acumulado cubre la `cantidad` pedida de **todos** los ítems →
    `entregada` (estado terminal para efectos de esta máquina: `entregada` no está en
    `_ESTADOS_PARA_ENTREGA`, por lo que no admite más entregas).
  - Si no, pero hay aceptado `> 0` en **al menos un** ítem → `parcialmente_entregada`.
  - Si ningún ítem tiene aceptado `> 0` (p. ej. la única entrega registrada fue
    rechazada por completo) → `en_entrega`.
- **`cancelada`**: existe en el `CHECK` de la base pero **ningún archivo de este
  módulo la escribe** (confirmado por `Grep` de `"cancelada"` en `compras/service.py`
  y `repository.py`: cero resultados). No hay endpoint de cancelación de OC. Ver
  [`pendientes.md`](./pendientes.md).

**Guardas de transición**: no existe una tabla de transiciones válidas explícita (mismo
patrón que el resto del repositorio — ver `services/presupuestacion/ROADMAP.md`, sección
sobre máquina de estados configurable, pospuesta). Las únicas guardas reales son las
condiciones de `RN-COMPRAS-004` (confirmar exige `"pendiente"`) y `RN-COMPRAS-006`
(entregar exige uno de los 3 estados intermedios) — ambas en `service.py`, no en la
base de datos (el `CHECK` solo restringe el conjunto de valores posibles, no las
transiciones entre ellos).

## `entregas_oc.estado`

Valores admitidos por el `CHECK` de la base (`extractor_final.sql:671`): `'pendiente'`,
`'en_transito'`, `'entregada'`, `'rechazada'`, `'parcial'`. De estos 5, el código de
Compras escribe 4 — nunca `'en_transito'`.

A diferencia de `ordenes_compra.estado` (que tiene transiciones a lo largo del tiempo,
recalculadas en cada entrega), `entregas_oc.estado` se calcula **una sola vez**, en el
momento de crear la entrega, y nunca se actualiza después (`repository.py` no expone
ninguna función de UPDATE sobre `entregas_oc`) — es un valor de snapshot, no una máquina
con transiciones posteriores.

`_calcular_estado_entrega` (`service.py:152-160`, RN-COMPRAS-009) decide entre 4
valores posibles a partir de los ítems recibidos en el body:

```
                    ¿Hay algún ítem con
                    cantidad_entregada > 0?
                            │
                 No ────────┼──────── Sí
                 │                     │
                 ▼                     ▼
             pendiente     ¿TODOS los entregados tienen
                            cantidad_rechazada >= cantidad_entregada?
                                        │
                             Sí ────────┼──────── No
                             │                      │
                             ▼                      ▼
                         rechazada     ¿ALGÚN entregado tiene
                                        cantidad_rechazada > 0?
                                                    │
                                         Sí ────────┼──────── No
                                         │                      │
                                         ▼                      ▼
                                     parcial               entregada
```

- **`pendiente`**: caso límite, cuando ningún ítem del body tiene
  `cantidad_entregada > 0`. No representa una entrega real con mercadería recibida; el
  código no impide explícitamente enviar un body así.
- **`rechazada`**: todo lo entregado fue rechazado en su totalidad.
- **`parcial`**: hay rechazo en al menos un ítem, pero no todo lo entregado fue
  rechazado.
- **`entregada`**: nada fue rechazado.
- **`en_transito`**: existe en el `CHECK` de la base pero **ningún archivo de este
  módulo la escribe** (confirmado por `Grep`: cero resultados). No hay ningún flujo en
  el código que module un estado intermedio "en camino" antes de la confirmación de
  recepción — la entrega se registra siempre como un hecho ya ocurrido (ver
  [`arquitectura.md`](./arquitectura.md)). Ver [`pendientes.md`](./pendientes.md).

**Quién calcula cada estado**: en ambos casos (`ordenes_compra.estado` y
`entregas_oc.estado`), es siempre `service.py` — nunca el usuario final. Ni
`CrearOrdenCompraRequest` ni `CrearEntregaRequest` (`models.py`) exponen un campo
`estado` en el body; no hay ningún endpoint tipo `PATCH .../estado` que permita setear
un estado arbitrario. El único control indirecto del usuario sobre el estado resultante
es a través de las cantidades (`cantidad_entregada`, `cantidad_rechazada`) que informa
al registrar una entrega.
