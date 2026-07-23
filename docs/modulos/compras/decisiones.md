# Decisiones de diseño — Compras

Numeración D-COMPRAS-NNN, verificada contra el código.

## D-COMPRAS-001 — No revertir una entrega si el ajuste de stock falla

**Decisión**: si `stock.entregar_stock_producto` agota sus reintentos (RN-CORE-002) y
levanta `ConflictError` durante `crear_entrega`, el registro de `entrega`/
`entrega_items` que ya se insertó no se borra ni se revierte — la excepción se propaga
tal cual.

**Motivo**: explícito en el docstring de `crear_entrega`
(`services/presupuestacion/compras/service.py:206-217`): "A diferencia del compromiso
en presupuestos/ (donde revertir un compromiso fallido es seguro y necesario para no
sobre-comprometer), acá la entrega ya ocurrió en la realidad; el registro parcial sirve
de rastro para reconciliar a mano, no hay una versión 'deshacer la entrega' razonable."

**Contraste explícito con `presupuestos/`**: en
[`../presupuestos/`](../presupuestos/README.md) (Flujo A, documentado desde Core en
[`../core/flujo.md`](../core/flujo.md)), comprometer stock es una operación reversible
sin costo real — es una reserva sobre algo que todavía no ocurrió, y revertirla ante un
fallo posterior (`presupuestos/service.py:213-219`, vía `stock.liberar_o_reportar`) deja
el sistema exactamente como si el intento nunca hubiera pasado. En Compras, en cambio,
la entrega de mercadería es un hecho físico: la mercadería salió del proveedor y llegó
(o no, o parcialmente) a destino, independientemente de si el sistema logra reflejar
ese hecho en `stock_productos`. Revertir el registro de la entrega no deshace el hecho
físico — solo borraría la evidencia de que ocurrió.

**Alternativas descartadas**:
- Envolver el INSERT de `entrega`/`entrega_items` y la llamada a `core.stock` en una
  transacción que revierta todo ante cualquier fallo — descartado implícitamente: el
  código no usa ninguna transacción explícita de Supabase/Postgrest para agrupar
  ambas operaciones (el patrón de acceso a datos del repositorio, `.insert().execute()`
  fila por fila, no soporta transacciones multi-tabla desde el cliente Python usado en
  este repositorio). Motivo pendiente de definición funcional para por qué no se
  evaluó una función de base (stored procedure) que agrupe ambos pasos.
- Marcar la entrega con un estado de "error" o "requiere reconciliación" en vez de
  dejarla con su `estado` calculado normalmente (`_calcular_estado_entrega`) — no
  implementado; hoy una entrega cuyo ajuste de stock falló queda con el mismo aspecto
  (mismo `estado`) que una entrega exitosa, sin ninguna marca que distinga el caso. Ver
  [`pendientes.md`](./pendientes.md).

**Ventajas**: preserva el rastro de lo que realmente ocurrió, incluso ante un fallo de
infraestructura; evita el riesgo de un "deshacer" que además tendría que revertir
selectivamente el ajuste de stock ya aplicado en ítems anteriores de la misma entrega
(un problema tan complejo como el que ya resuelve `liberar_compromisos` en
`core/stock.py`, D-CORE-003, pero sin la garantía de que revertir sea lo correcto acá).

**Desventajas**: no hay ningún mecanismo automatizado que detecte o repare una entrega
cuyo ajuste de stock quedó parcial o totalmente sin aplicar — la reconciliación es
enteramente manual, y no hay ninguna marca en la fila de `entregas_oc` que distinga una
entrega "limpia" de una con stock sin reconciliar. Ver [`pendientes.md`](./pendientes.md).

## D-COMPRAS-002 — El estado de OC y de entrega es siempre derivado, nunca seteado manualmente

**Decisión**: ni `ordenes_compra.estado` ni `entregas_oc.estado` se pueden setear a un
valor arbitrario elegido por el usuario. `ordenes_compra.estado` solo cambia a través de
3 rutas fijas: literal a `"pendiente"` en la creación (`service.py:62`), literal a
`"emitida"` en la confirmación (`service.py:134`), o calculado por
`_recalcular_estado_orden_compra` tras cada entrega (`service.py:163-195`).
`entregas_oc.estado` se calcula una única vez, al crear la entrega, por
`_calcular_estado_entrega` (`service.py:152-160`) — no existe ningún endpoint
`PATCH .../estado` para ninguna de las dos tablas.

**Motivo**: "Motivo pendiente de definición funcional" — no hay un comentario textual
en el código que declare esta intención de diseño explícitamente. Es una inferencia
respaldada por evidencia estructural: ni `CrearOrdenCompraRequest` ni
`CrearEntregaRequest` (`models.py`) exponen un campo `estado` en su body, y
`repository.actualizar_orden_compra` (la única función de UPDATE sobre
`ordenes_compra`) solo se invoca desde dentro de `service.py`, nunca con un valor que
provenga directamente y sin transformar del body de un endpoint.

**Ventajas**: el estado siempre refleja una regla de negocio verificable a partir de
datos concretos (cantidades pedidas vs. aceptadas) en vez de depender de que un usuario
lo actualice correctamente a mano; reduce la superficie de estados inconsistentes (p.
ej. una OC marcada `"entregada"` sin que ningún ítem tenga cantidad aceptada).

**Desventajas**: no hay forma de corregir manualmente un estado que quedó "atascado"
por una inconsistencia de datos (p. ej. una entrega registrada con datos erróneos que
dejó la OC en un estado que ya no refleja la realidad) sin editar la base directamente
— no existe un endpoint de corrección administrativa. Tampoco existe una vía para
cancelar una OC (`estado = 'cancelada'`, valor admitido por el `CHECK` de la base pero
nunca escrito por este módulo) — ver [`pendientes.md`](./pendientes.md).

## D-COMPRAS-003 — Los 3 casos de uso de escritura corren con `service_role`, siguiendo el criterio del resto del repositorio

**Decisión**: `crear_orden_compra_para_endpoint`, `confirmar_orden_compra_para_endpoint`
y `crear_entrega_para_endpoint` usan `get_service_client()` (bypasea RLS) en vez del
`user_client` del request.

**Motivo**: explícito en los docstrings de cada wrapper — la RLS de
`ordenes_compra`/`oc_items` "no incluye 'superadmin' en INSERT — mismo criterio que el
resto de los módulos" (`service.py:291-292`), y liberar/descontar `stock_productos`
"cuya RLS de UPDATE solo permite admin/gerencia/compras" (`service.py:314-315`).

**Ventajas**: consistente con el patrón ya documentado en
[`../core/decisiones.md`](../core/decisiones.md) D-CORE-006: el bypass de RLS se
concentra en `service.py`, verificable con el mismo test de arquitectura
(`tests/core/test_database.py:8-25`) que ya cubre a todos los módulos, incluido este.

**Desventajas**: las mismas ya documentadas en D-CORE-006 — el enforcement es un
chequeo de substring de texto sobre `router.py`, no un análisis estático real de
imports.
