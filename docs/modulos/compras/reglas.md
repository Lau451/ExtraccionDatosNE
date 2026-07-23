# Reglas — Compras

Todas las reglas fueron verificadas contra el código real en esta sesión. Numeración
RN-COMPRAS-NNN, correlativa.

### RN-COMPRAS-001 — El proceso comercial debe existir y pertenecer a la droguería

- **Descripción**: `crear_orden_compra` valida que `proceso_comercial_id` exista y que
  `proceso["drogueria_id"]` coincida con el `drogueria_id` recibido.
- **Condición**: llamada a `crear_orden_compra` con un `proceso_comercial_id` que no
  existe, o que existe pero pertenece a otra droguería.
- **Resultado**: `NotFoundError("No se encontró el proceso comercial")` si no existe
  (`service.py:48-49`); `ValidationError("El proceso comercial no pertenece a esta
  droguería")` si pertenece a otra (`service.py:50-51`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/compras/service.py:47-51`.
- **Observaciones**: [IMPLEMENTADO]. `router.py` hace además su propia validación
  equivalente pero contra la droguería del **usuario** (`router.py:50-62`) antes de
  llamar al service — son dos chequeos con propósito distinto (ver RN-COMPRAS-014).
  Verificado en `tests/compras/test_service.py:70-95`
  (`test_crear_orden_compra_proceso_de_otra_drogueria_falla`).

### RN-COMPRAS-002 — Cálculo de `monto_total` con redondeo `ROUND_HALF_UP` a 2 decimales

- **Descripción**: el monto total de la OC es la suma de `cantidad * precio_unitario`
  de todos los ítems, redondeada a 2 decimales con `ROUND_HALF_UP`.
- **Condición**: cualquier llamada a `crear_orden_compra`.
- **Resultado**: `monto_total` insertado como texto del `Decimal` ya redondeado
  (`service.py:53-55`, `:63`).
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/compras/service.py:21`, `:26-27` (`_q`),
  `:53-55`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/compras/test_service.py:37-39` (`Decimal("1000.00")` para 10 unidades a
  `100.00`).

### RN-COMPRAS-003 — `UNIQUE_VIOLATION` (`23505`) en `numero_oc` se traduce a `ConflictError` con mensaje explícito sobre versionado faltante

- **Descripción**: si el INSERT de `ordenes_compra` falla por el constraint único sobre
  `(numero_oc, version_numero)`, se captura el `APIError` de Postgrest, se verifica que
  el código sea `23505` y se relanza como `ConflictError` con un mensaje que aclara la
  causa de negocio.
- **Condición**: `crear_orden_compra` recibe un `numero_oc` que ya existe (con el mismo
  `version_numero`, que siempre es `1` porque el módulo no lo versiona — ver
  [`pendientes.md`](./pendientes.md) P1).
- **Resultado**: `ConflictError` con el mensaje exacto: "Ya existe una orden de compra
  con el número '{numero_oc}' — si es una modificación de una OC existente, hace falta
  el endpoint de versionado (todavía no implementado)" (`service.py:76-82`). Cualquier
  otro `APIError` (código distinto de `23505`) se relanza sin modificar
  (`service.py:82`, `raise`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/compras/service.py:22` (constante
  `_UNIQUE_VIOLATION`), `:73-82`.
- **Observaciones**: [IMPLEMENTADO]. El mensaje de error es, en sí mismo, admisión
  textual de una funcionalidad faltante (RN documentada también en
  [`pendientes.md`](./pendientes.md) P1). Verificado en
  `tests/compras/test_service.py:52-67`
  (`test_crear_orden_compra_numero_duplicado_levanta_conflict`, solo verifica el tipo
  de excepción, no el mensaje).

### RN-COMPRAS-004 — `confirmar_orden_compra` solo permite el estado `"pendiente"`

- **Descripción**: confirmar una OC exige que su `estado` actual sea exactamente
  `"pendiente"`.
- **Condición**: `confirmar_orden_compra` sobre una OC en cualquier otro estado
  (`"emitida"`, `"en_entrega"`, `"parcialmente_entregada"`, `"entregada"`,
  `"cancelada"`).
- **Resultado**: `ConflictError("Solo se puede confirmar una orden de compra en estado
  'pendiente'")` (`service.py:118-119`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/compras/service.py:115-119`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/compras/test_service.py:195-210`
  (`test_confirmar_orden_compra_ya_confirmada_levanta_conflict`).

### RN-COMPRAS-005 — Adjudicación de oferta condicionada a `es_drogueria_propia`

- **Descripción**: al confirmar una OC, por cada ítem con `oferta_item_id` no nulo se
  busca la oferta y, solo si `oferta.get("es_drogueria_propia")` es verdadero, se marca
  `adjudicada = TRUE` sobre esa oferta. Ítems sin `oferta_item_id`, u ofertas con
  `es_drogueria_propia` falso, no disparan ningún UPDATE.
- **Condición**: `confirmar_orden_compra` sobre una OC con al menos un ítem vinculado a
  una oferta.
- **Resultado**: `repository.marcar_oferta_adjudicada` (`UPDATE ofertas_items SET
  adjudicada = TRUE`) se ejecuta únicamente para las ofertas ganadoras marcadas como
  propias (`service.py:130-131`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/compras/service.py:121-131`.
- **Observaciones**: [IMPLEMENTADO]. Comentario explícito en el código (`service.py:127-129`):
  "§5: solo las ofertas PROPIAS ganadoras se marcan adjudicada=TRUE. es_drogueria_propia
  hoy no se auto-detecta (ver matching de comparativas) así que en la práctica esto no
  dispara hasta que exista el PATCH manual de asignación — comportamiento esperado."
  Ver [`decisiones.md`](./decisiones.md) y [`pendientes.md`](./pendientes.md) P1.
  Verificado en `tests/compras/test_service.py:98-192` (ambos casos: propia y no
  propia).

### RN-COMPRAS-006 — Entregas solo se aceptan en 3 estados de OC

- **Descripción**: `crear_entrega` solo procede si `oc["estado"]` está en
  `("emitida", "en_entrega", "parcialmente_entregada")`.
- **Condición**: `crear_entrega` sobre una OC en `"pendiente"`, `"entregada"` o
  `"cancelada"`.
- **Resultado**: `ConflictError("Solo se puede registrar una entrega para una OC
  emitida, en entrega o parcialmente entregada")` (`service.py:222-225`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/compras/service.py:23` (constante
  `_ESTADOS_PARA_ENTREGA`), `:218-225`.
- **Observaciones**: [IMPLEMENTADO]. Nótese que `"pendiente"` (antes de confirmar) está
  excluido: no se puede entregar mercadería de una OC que todavía no fue confirmada.
  Verificado en `tests/compras/test_service.py:213-242`
  (`test_crear_entrega_en_oc_no_emitida_levanta_conflict`).

### RN-COMPRAS-007 — Cada ítem de la entrega debe pertenecer a la OC

- **Descripción**: todo `oc_item_id` recibido en el body de una entrega debe existir
  entre los `oc_items` de la OC destino.
- **Condición**: `crear_entrega` recibe un `EntregaItemRequest.oc_item_id` que no está
  en `oc_items_por_id` (construido a partir de `repository.listar_oc_items` para esa
  OC).
- **Resultado**: `NotFoundError(f"El ítem {item.oc_item_id} no pertenece a esta orden
  de compra")` (`service.py:231-234`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/compras/service.py:227-234`.
- **Observaciones**: [IMPLEMENTADO]. No hay test dedicado a este caso en
  `tests/compras/test_service.py` (confirmado por lectura completa del archivo) — ver
  [`pendientes.md`](./pendientes.md).

### RN-COMPRAS-008 — `numero_entrega` correlativo, calculado en Python sin locking

- **Descripción**: el número de una entrega nueva es `len(entregas_previas) + 1`,
  donde `entregas_previas` es el resultado de listar todas las entregas existentes de
  la OC en el momento de la llamada.
- **Condición**: cualquier llamada a `crear_entrega`.
- **Resultado**: `numero_entrega` asignado antes del INSERT (`service.py:236-237`,
  `:243`).
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/compras/service.py:236-237`.
- **Observaciones**: [IMPLEMENTADO]. A diferencia de los ajustes de `stock_productos`
  en `core/stock.py` (optimistic locking, RN-CORE-001), este cálculo no tiene ninguna
  protección contra una carrera: dos llamadas concurrentes a `crear_entrega` sobre la
  misma OC podrían leer el mismo `len(entregas_previas)` y competir por el mismo
  `numero_entrega`. El `UNIQUE (orden_compra_id, numero_entrega)` de la base
  (`extractor_final.sql:670`) evitaría un duplicado silencioso (una de las dos
  transacciones fallaría con `23505`, no capturado explícitamente en este flujo — ver
  [`pendientes.md`](./pendientes.md)), pero no hay reintento ni manejo de ese error acá.

### RN-COMPRAS-009 — Cálculo del estado de una entrega (`_calcular_estado_entrega`)

- **Descripción**: dado el conjunto de ítems recibidos en el body de la entrega, se
  filtran primero los que tienen `cantidad_entregada > 0` ("entregados"). Sobre ese
  subconjunto:
  1. Si no hay ningún ítem entregado → `"pendiente"`.
  2. Si **todos** los ítems entregados tienen `cantidad_rechazada >= cantidad_entregada`
     (rechazo total) → `"rechazada"`.
  3. Si **alguno** de los ítems entregados tiene `cantidad_rechazada > 0` (sin ser
     rechazo total de todos) → `"parcial"`.
  4. En cualquier otro caso (nada rechazado) → `"entregada"`.
- **Condición**: cualquier llamada a `crear_entrega`, evaluada antes del INSERT.
- **Resultado**: el valor calculado se usa como `entregas_oc.estado`
  (`service.py:238`, `:249`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/compras/service.py:152-160`.
- **Observaciones**: [IMPLEMENTADO]. El caso 1 (`"pendiente"`) es un caso límite —en la
  práctica un body de entrega sin ningún ítem con `cantidad_entregada > 0` no
  representa una entrega real; el código no lo impide explícitamente (no hay
  `ValidationError` si todos los ítems vienen en `cantidad_entregada = 0`). Verificado
  para los casos `"entregada"` (`tests/compras/test_service.py:246-306`) y `"parcial"`
  (`tests/compras/test_service.py:362-423`); no hay test dedicado a `"rechazada"` ni al
  caso límite `"pendiente"` — ver [`pendientes.md`](./pendientes.md).

### RN-COMPRAS-010 — El ajuste de stock se saltea para ítems sin `producto_id`

- **Descripción**: al recorrer los ítems de una entrega para ajustar stock, se saltean
  (sin llamar a `stock.entregar_stock_producto`) los ítems cuyo `oc_item` asociado no
  tiene `producto_id`.
- **Condición**: un ítem de OC fue creado sin `producto_id` (campo opcional en
  `OrdenCompraItemRequest`, `models.py:13`).
- **Resultado**: ninguna llamada a `core.stock` para ese ítem — el registro de la
  entrega igual se inserta, pero no hay ningún ajuste de `stock_productos` asociado.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/compras/service.py:269-272`.
- **Observaciones**: [IMPLEMENTADO]. Consistente con que `producto_id` es la columna
  que "cierra la trazabilidad producto → oferta → OC → entrega" (comentario del schema,
  `extractor_final.sql:653`) — sin ella, no hay producto de catálogo al cual
  descontarle stock.

### RN-COMPRAS-011 — Una entrega ya registrada no se revierte si el ajuste de stock falla

- **Descripción**: si `stock.entregar_stock_producto` agota reintentos (5, ver
  RN-CORE-002) y levanta `ConflictError` para algún ítem, la excepción se propaga sin
  que `crear_entrega` deshaga el INSERT de `entrega`/`entrega_items` ya realizado.
- **Condición**: contención real sobre `stock_productos` durante el procesamiento de
  una entrega.
- **Resultado**: la respuesta HTTP es un 409 (`ConflictError` → `STATUS_MAP`,
  RN-CORE-009), pero el registro de la entrega queda persistido en la base — no hay
  rollback transaccional entre el INSERT de `entrega_items` y la llamada a
  `core.stock`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/compras/service.py:206-217` (docstring),
  `:269-279` (llamada sin try/except alrededor).
- **Observaciones**: [IMPLEMENTADO]. Decisión de diseño explícita — ver
  [`arquitectura.md`](./arquitectura.md) y [`decisiones.md`](./decisiones.md)
  D-COMPRAS-001. No hay test que fuerce este escenario en
  `tests/compras/test_service.py` (todos los tests usan `service_client` real sin mock
  de fallo de `core.stock`) — ver [`pendientes.md`](./pendientes.md).

### RN-COMPRAS-012 — Recálculo del estado de la OC tras cada entrega (`_recalcular_estado_orden_compra`)

- **Descripción**: tras insertar una entrega, se listan todos los `oc_items` de la OC y
  todos los `entregas_oc_items` asociados a esos ítems (across todas las entregas
  históricas, no solo la recién creada), se suma por ítem
  `cantidad_entregada - cantidad_rechazada` ("aceptado"), y:
  1. Si el aceptado acumulado de **todos** los ítems es `>=` a su `cantidad` pedida →
     `"entregada"`.
  2. Si no, pero **al menos un** ítem tiene aceptado `> 0` → `"parcialmente_entregada"`.
  3. Si ningún ítem tiene aceptado `> 0` → `"en_entrega"`.
- **Condición**: cualquier llamada exitosa a `crear_entrega` (tras insertar la entrega
  y ajustar stock).
- **Resultado**: `ordenes_compra.estado` actualizado al valor calculado
  (`service.py:192-194`), sin registrar el cambio en `historial_cambios` (ver
  [`pendientes.md`](./pendientes.md)).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/compras/service.py:163-195`.
- **Observaciones**: [IMPLEMENTADO]. Los 3 valores exactos son `"entregada"`,
  `"parcialmente_entregada"` y `"en_entrega"` — **no** `"en_evaluacion"` (valor que no
  existe en el `CHECK` de la base, `extractor_final.sql:632`, ni en ningún lugar del
  código; corrección respecto a un insumo previo que mencionaba ese valor). Verificado
  en `tests/compras/test_service.py:286-287` (`"entregada"`),
  `:350` (`"parcialmente_entregada"`). No hay test dedicado a `"en_entrega"` como
  resultado explícito de este recálculo (aparece indirectamente en
  `test_crear_entrega_en_oc_no_emitida_levanta_conflict`, pero ese test no llega a
  ejecutar `crear_entrega` con éxito) — ver [`pendientes.md`](./pendientes.md).

### RN-COMPRAS-013 — Roles por endpoint

- **Descripción**: cada endpoint de escritura exige una whitelist de roles distinta;
  los de lectura, una whitelist más amplia.
- **Condición**: request a cualquiera de los 5 endpoints de `compras/router.py`.
- **Resultado**:
  - `POST /ordenes-compra`, `POST /ordenes-compra/{id}/confirmar` →
    `_ROLES_OC = ("admin", "gerencia", "lider_comercial", "comercial")`
    (`router.py:21`).
  - `POST /ordenes-compra/{id}/entregas` →
    `_ROLES_ENTREGA = ("admin", "gerencia", "lider_comercial", "comercial",
    "compras")` (`router.py:22`) — el único endpoint de escritura que además admite el
    rol `"compras"`.
  - `GET /entregas/pendientes` →
    `_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial",
    "comercial", "compras")` (`router.py:23`).
  - `GET /compras/vs-cotizado` → whitelist inline, distinta de las 3 anteriores:
    `("superadmin", "admin", "gerencia", "compras")` (`router.py:108-110`) — no incluye
    `lider_comercial` ni `comercial`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/compras/router.py:21-23`, `:108-110`.
- **Observaciones**: [IMPLEMENTADO]. `superadmin` no puede crear ni confirmar OCs ni
  registrar entregas (no está en `_ROLES_OC` ni en `_ROLES_ENTREGA`) — solo tiene
  acceso de lectura. No hay test que ejercite `router.py` para verificar el
  enforcement real de roles (ver RN-COMPRAS-014 y [`pendientes.md`](./pendientes.md)).

### RN-COMPRAS-014 — Doble validación de pertenencia de droguería (creación vs. resto)

- **Descripción**: para crear una OC, el router valida que el **proceso comercial**
  pertenezca a la droguería del usuario (`router.py:60-62`); para confirmar una OC o
  registrar una entrega, valida que la **OC** pertenezca a la droguería del usuario
  (`_validar_oc_de_la_drogueria`, `router.py:26-41`).
- **Condición**: usuario autenticado con `rol != "superadmin"` intenta operar sobre un
  recurso de otra droguería.
- **Resultado**: `ForbiddenError("El proceso comercial no pertenece a tu droguería")`
  (creación, `router.py:62`) o `ForbiddenError("La orden de compra no pertenece a tu
  droguería")` (confirmación/entrega, `router.py:41`). `superadmin` está exento de
  ambas comparaciones (`router.py:61`, `:40`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/compras/router.py:26-41` (helper),
  `:50-62` (creación), `:75` (confirmación), `:88` (entrega).
- **Observaciones**: [IMPLEMENTADO]. `_validar_oc_de_la_drogueria` usa `user_client`
  (RLS activa) para el `SELECT` de comprobación (`router.py:29-35`), separado del
  `service_client` que después usa el `service.py` para la operación real — mismo
  patrón que documenta [`../core/arquitectura.md`](../core/arquitectura.md). No hay
  test de `router.py` para este comportamiento (ver [`pendientes.md`](./pendientes.md)).

### RN-COMPRAS-015 — Los 3 casos de uso de escritura corren con `service_role`

- **Descripción**: `crear_orden_compra_para_endpoint`, `confirmar_orden_compra_para_endpoint`
  y `crear_entrega_para_endpoint` resuelven el cliente con
  `core.database.get_service_client()`, no con el `user_client` del request.
- **Condición**: cualquier invocación vía HTTP de los 3 endpoints de escritura.
- **Resultado**: las operaciones de base (INSERT/UPDATE sobre `ordenes_compra`,
  `oc_items`, `ofertas_items`, `entregas_oc`, `entregas_oc_items`, `stock_productos`)
  bypasean RLS.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/compras/service.py:288-295` (creación),
  `:298-303` (confirmación), `:306-323` (entrega).
- **Observaciones**: [IMPLEMENTADO]. Mismo criterio documentado como D-CORE-006/
  RN-CORE-016 en [`../core/`](../core/README.md): el bypass de RLS se limita a
  `service.py`, nunca a `router.py` (confirmado: `compras/router.py` no importa
  `get_service_client`, solo `get_user_client`).
