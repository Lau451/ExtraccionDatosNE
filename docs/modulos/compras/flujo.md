# Flujos — Compras

Tres flujos principales. Cada paso cita `archivo:línea` verificado en esta sesión. El
ajuste de stock del Flujo 3 ya está documentado en detalle desde el lado de Core en
[`../core/flujo.md`](../core/flujo.md) Flujo D — acá se referencia sin repetirlo.

## Flujo 1 — Creación de una orden de compra

Disparado por `POST /ordenes-compra`.

1. El router valida que el usuario tenga uno de los roles de `_ROLES_OC`
   (`router.py:47`, RN-COMPRAS-013) y resuelve el proceso comercial vía `user_client`
   (RLS) para confirmar que pertenece a la droguería del usuario (`router.py:50-62`,
   RN-COMPRAS-014) — chequeo distinto y anterior al que hace el service.
2. `crear_orden_compra_para_endpoint` resuelve `get_service_client()`
   (`service.py:293-295`, RN-COMPRAS-015) y delega en `crear_orden_compra`.
3. Se busca el proceso comercial de nuevo (esta vez con `service_client`) y se valida
   que exista y pertenezca a la droguería recibida (`service.py:47-51`,
   RN-COMPRAS-001).
4. Se calcula `monto_total` sumando `cantidad * precio_unitario` de todos los ítems del
   body, redondeado a 2 decimales (`service.py:53-55`, RN-COMPRAS-002).
5. Se arma la fila de `ordenes_compra` con `estado = "pendiente"` y se inserta
   (`service.py:57-74`). Si el `numero_oc` ya existe, se traduce el `APIError` de
   Postgrest (código `23505`) a `ConflictError` con el mensaje sobre versionado
   faltante (`service.py:75-82`, RN-COMPRAS-003).
6. Se insertan los `oc_items` en bloque (`service.py:84-97`).
7. Se registra el evento de ciclo de vida `"creacion"` en `historial_cambios`
   (`registrar_evento_ciclo_vida`, `service.py:99-107`).
8. Se devuelve `ResultadoOrdenCompra` con `estado = "pendiente"` (`service.py:109`).

## Flujo 2 — Confirmación de una orden de compra

Disparado por `POST /ordenes-compra/{orden_compra_id}/confirmar`.

1. El router valida rol (`_ROLES_OC`) y pertenencia de droguería de la **OC** contra el
   usuario (`_validar_oc_de_la_drogueria`, `router.py:75`, RN-COMPRAS-014) —
   distinto del chequeo del Flujo 1, acá ya existe la OC.
2. `confirmar_orden_compra_para_endpoint` resuelve `get_service_client()`
   (`service.py:301-303`) y delega en `confirmar_orden_compra`.
3. Se busca la OC y se valida que exista y que su `estado` sea exactamente
   `"pendiente"` (`service.py:115-119`, RN-COMPRAS-004).
4. Se listan los `oc_items` de la OC. Por cada ítem con `oferta_item_id`, se busca la
   oferta y, solo si `oferta.get("es_drogueria_propia")` es verdadero, se marca
   `adjudicada = TRUE` sobre esa oferta (`service.py:121-131`, RN-COMPRAS-005). En la
   práctica, ninguna oferta llega con ese flag en `TRUE` porque nada en el repositorio
   lo auto-detecta ni lo setea manualmente hoy — ver
   [`../comparativas/pendientes.md`](../comparativas/pendientes.md) P1 y
   [`pendientes.md`](./pendientes.md) de este módulo.
5. Se actualiza `ordenes_compra.estado` a `"emitida"` (`service.py:133-135`).
6. Se registra el cambio de estado (`"pendiente"` → `"emitida"`) en `historial_cambios`
   con un `batch_id` nuevo (`registrar_cambio`, `service.py:136-147`).
7. Se devuelve `ResultadoOrdenCompra` con `estado = "emitida"` (`service.py:149`).

## Flujo 3 — Registro de una entrega

Disparado por `POST /ordenes-compra/{orden_compra_id}/entregas`. El detalle del ajuste
de stock (pasos internos de `stock.entregar_stock_producto`) está documentado en
[`../core/flujo.md`](../core/flujo.md) Flujo D — no se repite acá.

1. El router valida rol (`_ROLES_ENTREGA`, que incluye `"compras"` además de los roles
   de `_ROLES_OC`) y pertenencia de droguería de la OC (`router.py:88`,
   RN-COMPRAS-014).
2. `crear_entrega_para_endpoint` resuelve `get_service_client()` (`service.py:316-323`)
   y delega en `crear_entrega`.
3. Se busca la OC y se valida que su `estado` esté en
   `_ESTADOS_PARA_ENTREGA = ("emitida", "en_entrega", "parcialmente_entregada")`
   (`service.py:218-225`, RN-COMPRAS-006).
4. Se valida que cada `oc_item_id` recibido pertenezca a la OC
   (`service.py:227-234`, RN-COMPRAS-007).
5. Se calcula el `numero_entrega` correlativo (`len(entregas_previas) + 1`,
   `service.py:236-237`, RN-COMPRAS-008) y el `estado` de la entrega vía
   `_calcular_estado_entrega` (`service.py:238`, RN-COMPRAS-009).
6. Se inserta la fila de `entregas_oc` (`service.py:240-252`) y, en bloque, sus
   `entregas_oc_items` (`service.py:254-267`).
7. Por cada ítem de la entrega cuyo `oc_item` asociado tiene `producto_id` (los que no
   lo tienen se saltean, RN-COMPRAS-010), se llama a `stock.entregar_stock_producto`
   (`service.py:269-279`) — ver [`../core/flujo.md`](../core/flujo.md) Flujo D para el
   detalle interno (dos pasadas: liberar comprometido por el total, descontar
   disponible solo por lo aceptado). Si esta llamada agota reintentos y levanta
   `ConflictError`, la excepción se propaga **sin revertir** el registro de la entrega
   ya insertado en el paso 6 (RN-COMPRAS-011, ver
   [`arquitectura.md`](./arquitectura.md)).
8. Se recalcula el estado de la orden de compra a partir de las entregas acumuladas
   (`_recalcular_estado_orden_compra`, `service.py:281`, RN-COMPRAS-012) y se persiste
   ese nuevo estado — sin registrar el cambio en `historial_cambios` (ver
   [`pendientes.md`](./pendientes.md)).
9. Se devuelve `ResultadoEntrega` con el estado de la entrega y el nuevo estado de la
   OC (`service.py:283-285`).
