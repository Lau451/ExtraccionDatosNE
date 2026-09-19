# Módulo Compras — `services/presupuestacion/compras/`

## Qué es

Compras cubre el ciclo de vida de una orden de compra (OC) de Drogueria Nueva Era a un
proveedor: crearla a partir de un proceso comercial ya ganado, confirmarla (lo que
adjudica condicionalmente la oferta ganadora) y registrar las entregas físicas de
mercadería que van llegando, ajustando el stock del catálogo en el mismo paso.

El módulo tiene 4 archivos con código (`__init__.py` está vacío): `models.py` (54
líneas, 6 modelos Pydantic), `repository.py` (99 líneas, 10 funciones de acceso a datos
puro), `service.py` (324 líneas, el archivo más largo del módulo — 3 casos de uso más
sus wrappers para endpoint y 3 helpers privados) y `router.py` (114 líneas, 5
endpoints).

No es dueño del proceso comercial que origina la OC (eso es de
[`../procesos_comerciales/`](../procesos_comerciales/README.md)) ni de la oferta que
eventualmente adjudica (eso es de [`../comparativas/`](../comparativas/README.md)):
Compras lee esas tablas por su cuenta (sin importar el código Python de esos módulos) y
agrega su propia capa de negocio encima — creación, confirmación y entrega de OCs.

## Dos direcciones de flujo: proveedor (existente) y cliente (nueva, `orden-compra`)

El resto de este README, y de los demás documentos del módulo, describe el flujo **histórico**:
una OC que **nosotros** emitimos hacia un **proveedor**, a partir de un proceso comercial ganado.
Ese flujo sigue exactamente igual — `crear_orden_compra`/`confirmar_orden_compra`/`crear_entrega`
no se tocaron.

El cambio `orden-compra` (`openspec/changes/orden-compra/`) agrega una **segunda dirección de
flujo, hacia el cliente**: una OC que un **cliente** nos envía como documento (PDF/imagen/Excel),
que se extrae, se valida y se materializa **directamente** en `ordenes_compra`/`oc_items`/
`entregas_oc` — sin pasar por `crear_orden_compra` ni por `confirmar_orden_compra` — anclada por
`cliente_id` en vez de `proceso_comercial_id`, y nacida en estado `'emitida'` porque el cliente ya
la emitió; nosotros solo la registramos. El módulo que hace esa extracción y validación es
`services/extraccion/` (tercer extractor Gemini, `robot_orden_compra.py`) y
`services/presupuestacion/extraccion/` (`_materializar_orden_compra()`), no `compras/`: este
módulo (`compras/`) es el que recibe las filas ya materializadas y el que expondrá, a futuro, el
ciclo de intercambio con Progress descripto abajo. Ver
`openspec/changes/orden-compra/design.md` § Technical Approach y D3/D4/D13 para el detalle
completo.

**El ciclo completo, de punta a punta, es plan → export → Progress → import:**

1. **Plan** (Tramo 1 + Tramo 2 de `orden-compra`, **implementado en este cambio**): al confirmar
   la OC extraída, se crean en la misma operación las filas de `entregas_oc`
   (`estado='pendiente'`) y `entregas_oc_items` con `cantidad_planificada` y
   `cantidad_entregada = 0`. Confirmar **no** mueve stock.
2. **Export** (Tramo 3, **fuera de este cambio, trabajo futuro**): un CSV de "nota de pedido" que
   vuelca ese plan (OC + renglones + entregas planificadas) para enviarlo a Progress v8, el ERP
   legacy que gestiona el envío físico al cliente.
3. **Progress** (fuera de este repositorio): Progress procesa la nota de pedido y, en algún
   momento posterior, genera su propio CSV de retorno con lo efectivamente entregado/rechazado por
   línea.
4. **Import** (Tramo 3, **fuera de este cambio, trabajo futuro**): un CSV de retorno que
   **actualiza en el lugar** las mismas filas de `entregas_oc`/`entregas_oc_items` creadas en el
   paso 1 (nunca crea filas nuevas por esa vía) y mueve stock por **delta**, reutilizando
   `entregar_stock_producto`/`_recalcular_estado_orden_compra` sin modificarlos.

El principio que ordena el diseño completo (ver `design.md` D1/D2) es que **el plan y el hecho
viven en la misma fila**: el paso 1 crea la fila con lo planificado, el paso 4 la completa con lo
real. Los pasos 2 y 4 (export/import contra Progress, módulos `nota-pedido-export` y
`entregas-import`, archivo `csv_progress.py`) **no existen todavía** — están diseñados
(`design.md` D10, contratos CSV) pero explícitamente fuera del alcance de `orden-compra` Tramo 1+2
(ver `openspec/changes/orden-compra/proposal.md` § Approach y `tasks.md`), y quedan como una fase
futura separada del mismo change.

## Qué NO hace

- **No auto-detecta `es_drogueria_propia`.** `confirmar_orden_compra` solo marca
  `adjudicada = TRUE` en una oferta si `oferta.get("es_drogueria_propia")` es verdadero
  (`services/presupuestacion/compras/service.py:130-131`), y el propio código admite
  que ese flag "hoy no se auto-detecta ... así que en la práctica esto no dispara hasta
  que exista el PATCH manual de asignación" (comentario textual,
  `compras/service.py:127-129`). Ver [`decisiones.md`](./decisiones.md) y
  [`pendientes.md`](./pendientes.md) para el impacto concreto en este módulo, y
  [`../comparativas/pendientes.md`](../comparativas/pendientes.md) P1 para el gap desde
  el lado que debería resolverlo.
- **No revierte una entrega si `stock.entregar_stock_producto` falla.** El registro de
  `entrega`/`entrega_items` ya insertado en `crear_entrega` queda como está si el ajuste
  de stock agota reintentos — decisión explícita en el docstring de la función
  (`compras/service.py:206-217`). Ver [`arquitectura.md`](./arquitectura.md) y
  [`decisiones.md`](./decisiones.md) D-COMPRAS-001.
- **No implementa versionado de OC**, pese a que `ordenes_compra` ya tiene en el schema
  las columnas `version_numero`, `es_vigente`, `reemplaza_id` y `motivo_version`
  (`docs/schema/extractor_final.sql:622-625`) — el mismo patrón que sí está
  implementado para `comparativas` (`extractor_final.sql:567-570`). Ninguna de esas 4
  columnas se lee ni se escribe en `compras/service.py` ni `compras/repository.py`
  (confirmado por `Grep` en todo el módulo: cero resultados). El propio mensaje de
  `ConflictError` ante un `numero_oc` duplicado lo dice explícitamente: "hace falta el
  endpoint de versionado (todavía no implementado)" (`compras/service.py:78-81`). Ver
  [`pendientes.md`](./pendientes.md) P1.
- **No audita el registro de entregas.** `core.audit` se usa en la creación de la OC
  (`registrar_evento_ciclo_vida`, `compras/service.py:99-107`) y en su confirmación
  (`registrar_cambio`, `compras/service.py:136-147`), pero `crear_entrega` no llama a
  ninguna función de `core.audit` — confirmado por `Grep` de
  `core.audit`/`registrar_cambio`/`registrar_evento_ciclo_vida` en los 4 archivos del
  módulo (3 resultados, todos dentro de `crear_orden_compra`/`confirmar_orden_compra`,
  ninguno en `crear_entrega`). Ver [`pendientes.md`](./pendientes.md).

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `compras/__init__.py` | Vacío. |
| `compras/models.py` | `OrdenCompraItemRequest`/`CrearOrdenCompraRequest` (body de creación), `ResultadoOrdenCompra` (response), `EntregaItemRequest`/`CrearEntregaRequest` (body de entrega), `ResultadoEntrega` (response). |
| `compras/repository.py` | Acceso a datos puro sobre `procesos_comerciales`, `ordenes_compra`, `oc_items`, `ofertas_items`, `entregas_oc`, `entregas_oc_items`: 10 funciones, ningún UPDATE condicional (a diferencia de `core.stock`). |
| `compras/service.py` | `crear_orden_compra`, `confirmar_orden_compra`, `crear_entrega` (los 3 casos de uso) más sus wrappers `_para_endpoint` (corren con `service_role`) y 3 helpers privados (`_q`, `_calcular_estado_entrega`, `_recalcular_estado_orden_compra`). |
| `compras/router.py` | 5 endpoints: 3 de escritura (crear OC, confirmar, crear entrega) y 2 de lectura sobre vistas SQL (`v_entregas_pendientes`, `v_compras_vs_cotizado`). |

## Dependencias

- [`../core/`](../core/README.md) — `core.database` (`get_service_client`,
  `get_user_client`), `core.exceptions` (`NotFoundError`, `ConflictError`,
  `ValidationError`, `ForbiddenError`), `core.auth` (`require_roles`), `core.audit`
  (`registrar_cambio`, `registrar_evento_ciclo_vida`) y, en particular,
  **`core.stock`** (`entregar_stock_producto`) — Compras es uno de solo 2 consumidores
  de `core/stock.py` en todo `presupuestacion/` (el otro es `presupuestos/`, ver
  [`../core/casos_de_uso.md`](../core/casos_de_uso.md)). El ajuste de stock al
  registrar una entrega ya está documentado desde el lado de Core en
  [`../core/flujo.md`](../core/flujo.md) Flujo D — no se repite acá, ver
  [`flujo.md`](./flujo.md).
- [`../comparativas/`](../comparativas/README.md) — origen conceptual de
  `ofertas_items.es_drogueria_propia`, que `confirmar_orden_compra` lee para decidir la
  adjudicación (`compras/service.py:130-131`). No hay import de código Python entre
  ambos módulos: Compras consulta la tabla `ofertas_items` directamente vía
  `repository.buscar_oferta_item`. El gap de que ese flag nunca se auto-detecta está
  documentado desde el lado de Comparativas en
  [`../comparativas/pendientes.md`](../comparativas/pendientes.md) P1; este módulo lo
  confirma y agrega el ángulo de "adjudicación bloqueada de facto" en
  [`pendientes.md`](./pendientes.md).
- [`../procesos_comerciales/`](../procesos_comerciales/README.md) — origen de la OC:
  `crear_orden_compra` valida que el `proceso_comercial_id` recibido exista y
  pertenezca a la droguería del caller (`compras/service.py:47-51`,
  `repository.buscar_proceso_comercial`). Igual que con Comparativas, no hay import de
  código Python: Compras consulta la tabla `procesos_comerciales` directamente.

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — dependencias hacia Core y el patrón de no
  reversión de entregas.
- [`base_de_datos.md`](./base_de_datos.md) — las 4 tablas propias del módulo, columnas
  y CRUD real.
- [`reglas.md`](./reglas.md) — reglas de negocio y técnicas (RN-COMPRAS-NNN).
- [`flujo.md`](./flujo.md) — flujo de creación, confirmación y entrega de OC.
- [`estados.md`](./estados.md) — máquina de estados de `ordenes_compra` y `entregas_oc`.
- [`casos_de_uso.md`](./casos_de_uso.md) — los 5 endpoints, roles y consumidores.
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-COMPRAS-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3.
