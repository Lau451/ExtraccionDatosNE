# Arquitectura — Presupuestos

## Dependencias hacia Core

| Import | Origen | Uso |
|---|---|---|
| `registrar_cambio` | `core/audit.py` | Auditoría de todos los cambios de campo: estado de presupuesto (`service.py:8`, `:116-127`, `:227-238`), estado de proceso comercial (`:242-253`) y totales recalculados (`:76-87`). |
| `get_service_client` | `core/database.py` | Cliente sin RLS, resuelto internamente por los 3 wrappers `_para_endpoint` (`service.py:9`, `:261`, `:274`, `:290`). |
| `ConflictError`, `NotFoundError`, `ValidationError` | `core/exceptions.py` | Las 3 excepciones de dominio de este módulo (`service.py:10`); no se encontró ningún `raise ForbiddenError` ni `AuthenticationError` dentro de `service.py` — esas las levanta el router o `core/auth.py`. |
| `stock` (`comprometer_stock_producto`, `liberar_o_reportar`) | `core/stock.py` | Compromiso y reversión de stock al presentar un presupuesto de clase `"cotizacion"` (`service.py:11`, `:206-219`). Ver [`../core/flujo.md`](../core/flujo.md) Flujo A. |
| `UsuarioPerfil`, `require_roles` | `core/auth.py` | Perfil del solicitante y autorización por rol en los 4 endpoints (`router.py:4`, `:17-20`). |
| `get_user_client` | `core/database.py` | Cliente con RLS, inyectado en los 4 endpoints para validar pertenencia a la droguería antes de delegar (`router.py:5`, `:63`, `:83`, `:93`, `:104`). |
| `ForbiddenError`, `NotFoundError` | `core/exceptions.py` | Levantadas por el router: `ForbiddenError` si la droguería del presupuesto/ítem no coincide con la del solicitante (`router.py:6`, `:39`, `:57`); `NotFoundError` si no existe el presupuesto/ítem consultado por el router mismo, además del que puede levantar el `service.py` (`router.py:35`, `:53`, `:75`). |

Ver [`../core/`](../core/) para la documentación de estas piezas — no se repite
acá. Presupuestos es, junto con `compras/`, uno de los **2 únicos consumidores**
de `core/stock.py` en todo el repositorio (ya cuantificado desde el lado de Core
en [`../core/README.md`](../core/README.md)).

## `core/stock.py` — confirmado desde este lado

[`../core/flujo.md`](../core/flujo.md) Flujo A ya documenta paso a paso, desde el
lado de Core, el compromiso de stock disparado por `presentar_presupuesto`. Cita
verificada en esta sesión, sigue siendo exacta: los pasos 1-2 (`presentar_presupuesto`
valida estado `"aprobado"` y filtra ítems no excluidos con `producto_id` y
`cantidad_ofertada`) citan `presupuestos/service.py:183-187` y `:195-201`,
coincidente con el código leído acá; el paso 3 (`stock.comprometer_stock_producto`,
`presupuestos/service.py:206-211`) y el paso 4 (reversión de ítems anteriores ante
`ConflictError` de cualquier ítem posterior, `presupuestos/service.py:213-219`, vía
`stock.liberar_o_reportar`) también coinciden exactamente con el código actual. No
se repite el detalle interno de `core/stock.py` (optimistic locking, orden de
depósitos, reintentos) acá — ver el documento de Core.

## El patrón de dos vistas SQL por rol

`obtener_presupuesto_endpoint` (`router.py:60-76`) no arma la respuesta a mano:
selecciona entre dos vistas de solo lectura según el rol del solicitante,
resueltas en `repository.py`:

```python
filas = (
    repo.listar_presupuesto_revision(user_client, presupuesto_id=presupuesto_id)
    if usuario.rol in _ROLES_VEN_COSTO
    else repo.listar_presupuesto_comercial(user_client, presupuesto_id=presupuesto_id)
)
```
`router.py:69-73`, con `_ROLES_VEN_COSTO = ("superadmin", "admin", "gerencia")`
(`router.py:21`).

- `listar_presupuesto_comercial` (`repository.py:74-81`) consulta
  `v_presupuesto_comercial`.
- `listar_presupuesto_revision` (`repository.py:84-91`) consulta
  `v_presupuesto_revision`.

Ambas vistas están definidas en el schema de referencia
(`docs/schema/rls_final.sql:320-355` para `v_presupuesto_comercial`;
`docs/schema/extractor_final.sql:1490-1533` como definición base de
`v_presupuesto_revision`, reemplazada por `CREATE OR REPLACE VIEW` en
`docs/schema/rls_final.sql:454-501` para agregar el nombre de quien ajustó el
precio). `v_presupuesto_comercial` expone `precio_unitario`, `cantidad_ofertada`,
`monto_total`, `margen_resultante_pct`, `precio_mercado_usado`, `metodo_precio`,
`stock_verificado`, `stock_al_generar`, `excluido`, `motivo_exclusion` — y
explícitamente **no** expone `costo_usado`, `origen_costo`,
`precio_proveedor_id` ni `detalle_calculo` (comentario SQL textual,
`rls_final.sql:343`, `:351`). `v_presupuesto_revision` expone las mismas
columnas más `costo_usado`, `origen_costo`, `ajustado_por_humano`,
`proveedor_compra`, `plazo_pago_proveedor`/`plazo_pago_cliente`,
`mantenimiento_hasta_usado` y `alerta_mantenimiento` (`rls_final.sql:472-489`).
Ver [`reglas.md`](./reglas.md) RN-PRESUPUESTOS-013 y
[`decisiones.md`](./decisiones.md) D-PRESUPUESTOS-002 para el detalle y el
motivo (parcialmente documentado en el propio SQL, ver más abajo).

**Motivo, según comentario textual del schema**: `docs/schema/rls_final.sql:15-18`
("NOTA sobre costos: RLS filtra filas, no columnas. comercial y lider_comercial
NO deben consultar costos_productos ni las columnas de costo de
presupuesto_items directamente. Usan la vista v_presupuesto_comercial [...] La
app dirige cada rol a la vista correcta") explica por qué existen dos vistas: RLS
en Postgres solo puede restringir filas, no columnas, así que ocultar `costo_usado`
a un rol requiere una vista separada sin esa columna, seleccionada explícitamente
por la aplicación — exactamente el mecanismo que implementa `router.py:69-73`.
[IMPLEMENTADO] — motivo documentado en el código, no inferido.

## Escritura cruzada hacia `procesos_comerciales.estado`

Ya documentado en detalle, con la misma cita exacta, desde el otro lado en
[`../procesos_comerciales/estados.md`](../procesos_comerciales/estados.md) y
[`../procesos_comerciales/arquitectura.md`](../procesos_comerciales/arquitectura.md)
("Ciclo de vida partido con `presupuestos/`"). Confirmado acá:
`presentar_presupuesto` (`service.py:180-255`) llama a
`repo.actualizar_proceso_comercial(client, proceso_comercial_id=proceso["id"],
campos={"estado": "presentado"})` (`service.py:239-241`), que ejecuta
`repository.py:actualizar_proceso_comercial` (`:68-71`): un `UPDATE` genérico sin
`SELECT` previo del estado actual y sin condición `WHERE estado=...` de ningún
tipo — el mismo hallazgo, misma cita, mismo archivo, confirmado en esta sesión
leyendo `presupuestos/service.py` y `presupuestos/repository.py` completos.

**Por qué es este módulo, y no `procesos_comerciales/`, el que dispara la
transición**: Motivo pendiente de definición funcional — no hay comentario en el
código que lo explique. Hipótesis razonable a partir de la estructura del
repositorio (no confirmada): `procesos_comerciales/service.py` (27 líneas, según
[`../procesos_comerciales/README.md`](../procesos_comerciales/README.md)) solo
tiene lógica de alta y no expone ningún `PATCH`/`PUT`; el cambio de estado del
proceso a `"presentado"` es, desde la perspectiva del dominio, un **efecto
colateral** de presentar el presupuesto asociado (un evento del ciclo de vida del
presupuesto, no una operación que el usuario invoque directamente sobre el
proceso comercial) — de ahí que quien ya tiene la transacción abierta y el
contexto (`proceso`, `presupuesto`) sea quien la ejecuta, en vez de hacer una
segunda llamada HTTP a un endpoint de `procesos_comerciales/` que hoy no existe.
Ver [`decisiones.md`](./decisiones.md) D-PRESUPUESTOS-003 y
[`pendientes.md`](./pendientes.md) para el riesgo de esta implementación (ausencia
de guarda sobre el estado anterior del proceso).

## Diagrama de acoplamiento

```
                          presupuestos (tabla)
                               │
              ┌────────────────┴────────────────┐
              │                                  │
         pricing/                          presupuestos/
   (INSERT inicial "generado",         (aprobar/ajustar/presentar,
    DELETE+INSERT de items)            service_role para bypasear RLS
                                        de presupuestos/stock_productos)
                                              │
                                              │  compromete/revierte
                                              ▼
                                        core/stock.py
                                   (optimistic locking,
                                    2 consumidores: compras/, presupuestos/)
                                              │
                                              │  efecto colateral de
                                              │  presentar_presupuesto,
                                              │  sin guarda de transición
                                              ▼
                                   procesos_comerciales.estado
                              (único UPDATE de toda la tabla,
                               ver procesos_comerciales/estados.md)
```

Ver [`../pricing/arquitectura.md`](../pricing/arquitectura.md) para el detalle
completo del solapamiento de responsabilidad con Pricing (ya documentado ahí,
incluyendo el recálculo de `monto_total`/`items_sin_precio` con criterio propio
que hace este módulo vía `_recalcular_totales_presupuesto`,
`service.py:41-88`) y [`../procesos_comerciales/arquitectura.md`](../procesos_comerciales/arquitectura.md)
para el diagrama completo de consumidores de `procesos_comerciales`.
