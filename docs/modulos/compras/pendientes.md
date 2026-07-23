# Pendientes — Compras

Auditoría técnica P1 (bloqueante/riesgo alto) / P2 (riesgo medio, corregir pronto) / P3
(mejora, sin urgencia), verificada contra el código y los tests reales en esta sesión.

## P1 — Riesgo alto

### 1. Versionado de OC no implementado, pese a que el schema ya lo prepara

El propio código admite el gap: el mensaje de `ConflictError` ante un `numero_oc`
duplicado dice textualmente "si es una modificación de una OC existente, hace falta el
endpoint de versionado (todavía no implementado)"
(`services/presupuestacion/compras/service.py:78-81`).

**Evidencia de que no es solo un comentario aspiracional, sino un gap concreto**:
`ordenes_compra` ya tiene en el schema las 4 columnas necesarias —
`version_numero INTEGER NOT NULL DEFAULT 1`, `es_vigente BOOLEAN NOT NULL DEFAULT TRUE`,
`reemplaza_id UUID NULL`, `motivo_version TEXT NULL`
(`docs/schema/extractor_final.sql:622-625`), con los mismos `CHECK`
(`ck_oc_version`, `ck_oc_motivo`, `:633-634`) que ya tiene `comparativas`
(`extractor_final.sql:567-570`, `:575-576`) — módulo donde ese mismo patrón **sí** está
implementado (`_materializar_comparativa` en `extraccion/service.py`, según
`services/presupuestacion/ROADMAP.md:26` que confirma "mismo patrón
`version_numero`/`es_vigente`/`reemplaza_id` que sí se implementó para
`comparativas`"). En Compras, ninguna de las 4 columnas se lee ni se escribe —
confirmado por `Grep` de `version_numero`/`es_vigente`/`reemplaza_id`/`motivo_version`
en `compras/service.py` y `compras/repository.py`: cero resultados. Toda OC creada por
este módulo queda con `version_numero = 1`, `es_vigente = TRUE`, `reemplaza_id = NULL`
por default de la base, sin que el código lo garantice ni lo use.

**Impacto real**: no existe hoy ninguna forma de corregir una OC ya creada salvo
crearla de nuevo con un `numero_oc` distinto (evadiendo el propósito del constraint
único) o editar la base directamente. Cualquier corrección legítima de una OC emitida
(cambio de cantidad, de precio, de fecha de entrega) queda sin camino soportado por el
sistema.

**Prioridad**: Alta — funcionalidad reconocida como faltante por el propio código, con
el patrón de solución ya construido y probado en otro módulo del mismo repositorio.

**Recomendación** [RECOMENDACIÓN]: implementar el flujo de versionado siguiendo el
patrón ya validado en `comparativas`/`extraccion/service.py` — un endpoint que, al
recibir una modificación sobre una OC vigente, marque la fila actual `es_vigente =
FALSE`, inserte una nueva fila con `version_numero` incrementado, `reemplaza_id`
apuntando a la OC anterior y `motivo_version` obligatorio.

### 2. `es_drogueria_propia` nunca se auto-detecta ni se setea manualmente — la adjudicación queda bloqueada de facto

Ya documentado desde el lado de origen en
[`../comparativas/pendientes.md`](../comparativas/pendientes.md) P1. Confirmado desde
este módulo: `confirmar_orden_compra` solo marca `adjudicada = TRUE` sobre una oferta
si `oferta.get("es_drogueria_propia")` es verdadero
(`services/presupuestacion/compras/service.py:130-131`), y el propio comentario del
código reconoce el problema (`service.py:127-129`): "es_drogueria_propia hoy no se
auto-detecta (ver matching de comparativas) así que en la práctica esto no dispara
hasta que exista el PATCH manual de asignación — comportamiento esperado."

**Impacto real desde el ángulo de Compras**: `RN-COMPRAS-005`
(adjudicación condicionada) es código muerto en la práctica — la rama
`if oferta is not None and oferta.get("es_drogueria_propia")` nunca es verdadera con
los datos que produce el resto del repositorio hoy, porque (confirmado en
[`../comparativas/pendientes.md`](../comparativas/pendientes.md) P1)
`asignar_proveedor` — el único candidato conocido para setear ese flag manualmente —
solo escribe `proveedor_id`, nunca `es_drogueria_propia`. Es decir: **confirmar una OC
nunca adjudica ninguna oferta en el estado actual del repositorio**, sin importar
cuántas ofertas propias hayan ganado un renglón.

**Prioridad**: Alta — bloquea de forma efectiva una regla de negocio central del
módulo (RN-COMPRAS-005), no solo un caso límite.

**Recomendación** [RECOMENDACIÓN]: la misma que ya propone
[`../comparativas/pendientes.md`](../comparativas/pendientes.md) — extender
`asignar_proveedor` en `comparativas/` para derivar `es_drogueria_propia` a partir de
`proveedores.es_competidor`/`proveedores.tipo`. Este módulo no puede resolverlo por sí
mismo: no tiene ningún caso de uso de escritura sobre `ofertas_items` más allá de
`marcar_oferta_adjudicada` (que ya depende del flag, no lo produce).

## P2 — Riesgo medio

### 1. `crear_entrega` no deja ningún rastro de auditoría

`Grep` de `core.audit`/`registrar_cambio`/`registrar_evento_ciclo_vida` en
`compras/service.py`: 3 resultados (`service.py:17`, import; `:99`,
`registrar_evento_ciclo_vida` en `crear_orden_compra`; `:136`, `registrar_cambio` en
`confirmar_orden_compra`), ninguno dentro de `crear_entrega` (`service.py:198-285`).
Ni el registro de la entrega en sí, ni el cambio de `ordenes_compra.estado` que
`_recalcular_estado_orden_compra` persiste tras cada entrega (`service.py:192-194`),
quedan auditados en `historial_cambios`.

**Impacto**: `GET /historial/{entidad}/{entidad_id}` (módulo
[`../core/`](../core/README.md)) puede mostrar quién creó y quién confirmó una OC, pero
no puede mostrar quién registró una entrega ni cuándo la OC pasó de `"emitida"` a
`"parcialmente_entregada"` o `"entregada"` — justamente los eventos que ajustan stock
real y que más valor tendrían para una reconciliación posterior (ver punto P2(3) de
abajo, sobre la falta de reconciliación automática).

**Consistencia con el resto del repositorio**: igual que señala
[`../comparativas/pendientes.md`](../comparativas/pendientes.md) P2, `EntidadAuditable`
(`core/audit.py:7-9`) no incluye ningún valor equivalente a "entrega" —
`_COLUMNA_FK_POR_ENTIDAD` solo mapea `proceso_comercial`, `comparativa`,
`orden_compra`, `presupuesto`, `evento`. Auditar el registro de una entrega en sí
(no solo el cambio de estado de la OC que la contiene) requeriría primero extender esa
infraestructura.

**Recomendación** [RECOMENDACIÓN]: como mínimo, agregar un `registrar_cambio` al final
de `_recalcular_estado_orden_compra` para dejar rastro del cambio de estado de la OC
(mismo patrón que ya usa `confirmar_orden_compra`); evaluar aparte si extender
`EntidadAuditable` con `"entrega"` es necesario para auditar el registro de la entrega
en sí.

### 2. `numero_entrega` correlativo calculado sin locking — riesgo de carrera en entregas concurrentes

`numero_entrega = len(entregas_previas) + 1` (`service.py:236-237`, RN-COMPRAS-008) se
calcula leyendo el estado actual y no está protegido con optimistic locking, a
diferencia de los ajustes de `stock_productos` en `core/stock.py` (RN-CORE-001). Dos
llamadas concurrentes a `crear_entrega` sobre la misma OC podrían calcular el mismo
`numero_entrega`. El `UNIQUE (orden_compra_id, numero_entrega)` de la base
(`extractor_final.sql:670`) evitaría el duplicado silencioso, pero el código no captura
ni maneja ese `23505` en este punto (a diferencia del manejo específico que sí existe
para `numero_oc` en `crear_orden_compra`, RN-COMPRAS-003) — la segunda llamada
concurrente recibiría un `APIError` sin traducir a `DomainError`, cayendo al handler
genérico de status `500` (ver RN-CORE-009/D-CORE-007 en
[`../core/`](../core/README.md)).

**Recomendación** [RECOMENDACIÓN]: aplicar el mismo manejo explícito de
`UNIQUE_VIOLATION` que ya existe para `numero_oc` (RN-COMPRAS-003), traduciendo el
`23505` sobre `entregas_oc` a un `ConflictError` con un mensaje que sugiera reintentar.

### 3. Sin reconciliación automática cuando una entrega queda con stock sin ajustar

Consecuencia directa de D-COMPRAS-001: si `stock.entregar_stock_producto` falla tras
agotar reintentos, el registro de `entrega`/`entrega_items` queda persistido con el
mismo `estado` que tendría una entrega exitosa (`_calcular_estado_entrega` no tiene en
cuenta si el ajuste de stock posterior tuvo éxito, porque se calcula **antes** de
intentarlo, `service.py:238`). No hay ninguna columna ni marca en `entregas_oc` que
distinga una entrega cuyo stock se ajustó completamente de una que quedó parcial o
totalmente sin reconciliar — mismo patrón de riesgo ya señalado para
`liberar_compromisos` en [`../core/pendientes.md`](../core/pendientes.md) (Core:
"no existe en el código revisado ningún mecanismo automatizado de reconciliación
posterior").

**Recomendación** [RECOMENDACIÓN]: agregar una columna (p. ej.
`stock_reconciliado BOOLEAN` o `stock_pendiente_reconciliar`) a `entregas_oc`, seteada
en `FALSE` si `stock.entregar_stock_producto` levanta `ConflictError` para algún ítem,
capturando la excepción en `crear_entrega` en vez de dejarla propagar sin marcar nada.

### 4. Ningún test fuerza el escenario de fallo de `stock.entregar_stock_producto` dentro de `crear_entrega`

Los 3 tests de entrega en `tests/compras/test_service.py`
(`test_crear_entrega_completa_libera_stock_y_marca_oc_entregada`,
`test_crear_entrega_parcial_deja_oc_parcialmente_entregada`,
`test_crear_entrega_con_rechazo_no_descuenta_disponible_por_lo_rechazado`) ejercitan el
camino feliz de `core.stock` con `service_client` real, sin mockear ni forzar una
carrera que agote los 5 reintentos de RN-CORE-002. RN-COMPRAS-011 (no reversión ante
fallo) no tiene cobertura de test directa en este módulo — a diferencia de
`core/stock.py`, que sí tiene tests de carrera forzada
(`tests/core/test_stock.py:77-128`, `:214-300`, según
[`../core/reglas.md`](../core/reglas.md) RN-CORE-002).

## P3 — Menor

### 1. Ningún test cubre `router.py` directamente

Los 9 tests de `tests/compras/test_service.py` llaman a `crear_orden_compra`,
`confirmar_orden_compra` y `crear_entrega` (los `service.py`) directamente con
`service_client`, nunca al endpoint HTTP vía `TestClient`. No hay evidencia de un test
que ejercite:

- `_validar_oc_de_la_drogueria` (`router.py:26-41`, RN-COMPRAS-014) — el chequeo de
  pertenencia de droguería del **usuario** contra la OC, en los endpoints de
  confirmación y entrega.
- El ruteo por rol de los 5 endpoints (`_ROLES_OC` vs. `_ROLES_ENTREGA` vs.
  `_ROLES_LECTURA` vs. la whitelist inline de `compras_vs_cotizado_endpoint`,
  RN-COMPRAS-013).
- Los 2 endpoints de lectura sobre vistas (`GET /entregas/pendientes`,
  `GET /compras/vs-cotizado`), que no tienen ningún test en absoluto (ni de service ni
  de router, porque no tienen `service.py` propio).

Mismo patrón ya documentado en
[`../comparativas/pendientes.md`](../comparativas/pendientes.md) P2 ("Ningún test
cubre `router.py` directamente") y en
[`../core/pendientes.md`](../core/pendientes.md) — parece ser una convención
consistente del proyecto, no un descuido aislado de este módulo.

### 2. `response_model` ausente en los 2 endpoints de lectura sobre vistas

`GET /entregas/pendientes` y `GET /compras/vs-cotizado` retornan `list[dict]` crudo sin
`response_model` (`router.py:98-103`, `:106-113`) — a diferencia de los 3 endpoints de
escritura, que sí declaran `response_model=ResultadoOrdenCompra`/`ResultadoEntrega`.
Mismo patrón ya señalado en
[`../comparativas/pendientes.md`](../comparativas/pendientes.md) P3 para
`POST /ofertas/{oferta_id}/asignar-proveedor`. No es un bug (FastAPI serializa el
`dict` igual), pero las filas de `v_entregas_pendientes`/`v_compras_vs_cotizado` no
quedan documentadas en el schema OpenAPI generado. Motivo pendiente de definición
funcional: no hay evidencia de si fue intencional u omisión.

**Recomendación** [RECOMENDACIÓN]: definir modelos de respuesta explícitos para ambas
vistas, reflejando las columnas que exponen (`extractor_final.sql:1598-1609`,
`:1637-1655`).

### 3. Columnas de `ordenes_compra` que este módulo nunca usa

`extraction_id` y `cantidad_entregas` existen en el schema
(`extractor_final.sql:612`, `:619`) pero ningún código de `compras/service.py` ni
`compras/repository.py` las lee ni las escribe (confirmado por `Grep`: cero
resultados en todo `services/`, incluyendo `extraccion/`, para `extraction_id` sobre
`ordenes_compra` específicamente). Toda OC queda con `extraction_id = NULL` y
`cantidad_entregas = 1` (su default) sin importar cuántas entregas reales tenga. No es
un bug funcional (nada depende hoy de estas columnas), pero son candidatas a quedar
obsoletas o a necesitar una decisión explícita sobre su propósito. Motivo pendiente de
definición funcional.

### 4. No existe ningún camino para llegar a `ordenes_compra.estado = 'cancelada'`

El `CHECK` de la base admite `'cancelada'` (`extractor_final.sql:632`), pero ningún
archivo de este módulo la escribe (confirmado por `Grep`: cero resultados) y no hay
ningún endpoint de cancelación. Ver [`estados.md`](./estados.md). Motivo pendiente de
definición funcional: no hay evidencia de si la cancelación de una OC es un caso de uso
previsto para una iteración futura o un valor que quedó en el `CHECK` sin un flujo
asociado.

### 5. `entregas_oc.estado = 'en_transito'` es un valor inalcanzable con el código actual

Mismo caso que el punto anterior, pero sobre `entregas_oc`
(`extractor_final.sql:671`) — ver [`estados.md`](./estados.md). Ninguna entrega
registrada por este módulo puede quedar en `"en_transito"`, porque `crear_entrega`
siempre registra un hecho ya ocurrido (ver [`arquitectura.md`](./arquitectura.md)), no
un estado intermedio "en camino".

### 6. Casos límite de `_calcular_estado_entrega` sin test dedicado

RN-COMPRAS-009 tiene 4 ramas posibles; los tests existentes cubren `"entregada"`
(`tests/compras/test_service.py:246-306`) y `"parcial"`
(`tests/compras/test_service.py:362-423`). No hay test dedicado a `"rechazada"` (todos
los ítems entregados rechazados en su totalidad) ni al caso límite `"pendiente"`
(ningún ítem con `cantidad_entregada > 0`).

### 7. `RN-COMPRAS-007` (pertenencia de ítem a la OC) sin test dedicado

`service.py:227-234` levanta `NotFoundError` si un `oc_item_id` de la entrega no
pertenece a la OC destino — no hay ningún test en
`tests/compras/test_service.py` que ejercite este camino.
