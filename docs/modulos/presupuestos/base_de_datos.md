# Base de datos — Presupuestos

Presupuestos no es dueño (`owner`) de ninguna tabla nueva: opera sobre
`presupuestos`/`presupuesto_items` (creadas por `pricing/`, ver
[`../pricing/base_de_datos.md`](../pricing/base_de_datos.md)), hace el único
`UPDATE` acotado de `procesos_comerciales.estado`, y toca `stock_productos` de
forma indirecta a través de `core/stock.py`. Columnas verificadas contra
`docs/schema/extractor_final.sql:491-550` y `docs/schema/rls_final.sql`.

## `presupuestos`

Definición completa: `docs/schema/extractor_final.sql:491-515`.

| Columna | Tipo | Uso desde este módulo |
|---|---|---|
| `id` | `UUID` | Filtro `eq` en toda lectura/escritura (`repository.py:10`, `:56`, `:64`). |
| `proceso_comercial_id` | `UUID NOT NULL` | Leído para resolver el proceso comercial asociado en `presentar_presupuesto` (`repository.py:6-15` trae la fila completa; `service.py:189-191` usa el campo). |
| `drogueria_id` | `UUID NOT NULL` | Propagado a cada `registrar_cambio` como `drogueria_id` de la auditoría (`service.py:80`, `:120`, `:231`). |
| `estado` | `TEXT NOT NULL DEFAULT 'generado'` | **Escrito por este módulo**: `"aprobado"` en `aprobar_presupuesto` (`service.py:114`), `"presentado"` en `presentar_presupuesto` (`service.py:225`). `CHECK ck_pre_estado` (`extractor_final.sql:509-510`) restringe a los 7 valores de `EstadoPresupuesto`. Ver [`estados.md`](./estados.md). |
| `monto_total` | `NUMERIC(15,2) NULL` | Recalculado por `_recalcular_totales_presupuesto` (`service.py:41-88`), excluyendo ítems `excluido=True` — criterio propio, distinto del que usa `pricing/` al crear (ver [`../pricing/arquitectura.md`](../pricing/arquitectura.md)). |
| `cantidad_items` | `INTEGER NOT NULL DEFAULT 0` | Leído para armar `ResultadoPresupuesto` (`service.py:36`); **no** se reescribe en este módulo — solo `pricing/` lo toca. |
| `items_sin_precio` | `INTEGER NOT NULL DEFAULT 0` | Recalculado junto con `monto_total` en `_recalcular_totales_presupuesto` (`service.py:57`, `:63-64`). También usado como guarda de negocio: `aprobar_presupuesto` bloquea si hay ítems `sin_precio` no excluidos, aunque para esa guarda relee directo `presupuesto_items` en vez de confiar en este contador cacheado (`service.py:102-108`, ver [`reglas.md`](./reglas.md) RN-PRESUPUESTOS-002). |
| `aprobado_por`, `aprobado_at` | `UUID NULL`, `TIMESTAMPTZ NULL` | Escritos por `aprobar_presupuesto` (`service.py:114`). FK `fk_pre_aprobadopor` hacia `usuarios` (`rls_final.sql:394`). |
| `presentado_por`, `presentado_at` | `UUID NULL`, `TIMESTAMPTZ NULL` | Escritos por `presentar_presupuesto` (`service.py:225`). FK `fk_pre_presentapor` (`rls_final.sql:395`). |
| `deleted_at` | — | Filtrado con `is_("deleted_at", None)` en `buscar_presupuesto` (`repository.py:11`) — no hay ninguna función de borrado lógico en este módulo; el filtro solo protege la lectura. |

**Constraint de base de datos que complementa la guarda de aplicación**
(`extractor_final.sql:511-514`):

```sql
CONSTRAINT ck_pre_aprobado CHECK (
    estado IN ('generado', 'en_revision', 'vencido') OR
    (aprobado_at IS NOT NULL AND aprobado_por IS NOT NULL)
)
```

Exige que todo presupuesto en `aprobado`, `presentado`, `adjudicado` o
`rechazado` tenga `aprobado_por`/`aprobado_at` seteados — una segunda barrera a
nivel de Postgres, independiente de la guarda de `aprobar_presupuesto`
(`service.py:97-100`). [IMPLEMENTADO], verificado en el schema; no se encontró
un `CHECK` equivalente para `presentado_por`/`presentado_at`.

**CRUD de este módulo**: Read (`buscar_presupuesto`) y Update (`estado`,
`monto_total`, `items_sin_precio`, `aprobado_*`, `presentado_*`). Sin Create ni
Delete — el alta es de `pricing/` (ver [`../pricing/base_de_datos.md`](../pricing/base_de_datos.md)).

## `presupuesto_items`

Definición completa: `docs/schema/extractor_final.sql:517-550`.

| Columna | Tipo | Uso desde este módulo |
|---|---|---|
| `id` | `UUID` | Filtro `eq` (`repository.py:43`, `:56`). |
| `presupuesto_id` | `UUID NOT NULL` | Filtro de `listar_items_presupuesto` (`repository.py:33`); leído de la fila del ítem para resolver el presupuesto padre en `ajustar_item` (`service.py:173`). |
| `drogueria_id` | `UUID NOT NULL` | Leído en `presentar_presupuesto` para pasarlo a `stock.comprometer_stock_producto` (`service.py:209`). |
| `item_proceso_id` | `UUID NOT NULL` | No manipulado directamente por este módulo (solo propagado desde la fila leída). |
| `producto_id` | `UUID NULL` | Filtro de elegibilidad para comprometer stock: solo ítems con `producto_id IS NOT NULL` (`service.py:200`). |
| `precio_unitario` | `NUMERIC(15,2) NULL` | **Escrito** por `ajustar_item` cuando se pasa un valor (`service.py:149`); leído para el cálculo de `monto_total` en el recálculo (`service.py:50`) y como base de `precio_original_motor` si es el primer ajuste (`service.py:147-148`). |
| `cantidad_ofertada` | `NUMERIC(12,2) NULL` | **Escrito** por `ajustar_item` (`service.py:160`); leído para el compromiso de stock (`service.py:200`, `:210`) y el cálculo de `monto_total` (`service.py:50`). |
| `monto_total` | `NUMERIC(15,2) GENERATED ALWAYS AS (precio_unitario * cantidad_ofertada) STORED` | Columna generada por Postgres, **no escrita nunca por Python** — distinta de `presupuestos.monto_total` (agregado de todos los ítems), que sí es responsabilidad de este módulo. |
| `metodo_precio` | `TEXT NULL` | Leído para la guarda de ítems `sin_precio` (`service.py:28`, `:103`); **escrito** a `"manual"` cuando se ajusta el precio a mano (`service.py:151`) — `CHECK ck_pi_metodo` (`extractor_final.sql:548`) incluye `'manual'` entre los 5 valores válidos, además de los 4 que puede producir `pricing/`. |
| `costo_usado` | `NUMERIC(15,2) NULL` | Solo lectura: base del recálculo de `margen_resultante_pct` en `ajustar_item` (`service.py:153-157`) — este módulo nunca lo escribe. |
| `margen_resultante_pct` | `NUMERIC(7,2) NULL` | **Escrito** por `ajustar_item` tras un ajuste de precio (`service.py:155`, `:157`) — recalculado contra `costo_usado`, con guarda `costo_usado > 0` (a diferencia de `pricing/service.py:156`, que no la tiene, ver [`../pricing/reglas.md`](../pricing/reglas.md) RN-PRICING-009). |
| `precio_ajustado_por` | `UUID NULL` | **Escrito** por `ajustar_item` en cada ajuste de precio (`service.py:150`). FK `fk_pi_ajustadopor` (`rls_final.sql:396`); usada por `v_presupuesto_revision` para resolver `ajustado_por` (nombre) y `ajustado_por_humano` (booleano) (`rls_final.sql:481-482`, `:498`). |
| `precio_original_motor` | `NUMERIC(15,2) NULL` | **Escrito solo la primera vez** que se ajusta el precio a mano (`service.py:147-148`) — conserva el precio calculado por el motor de pricing antes del primer ajuste manual. Ver [`reglas.md`](./reglas.md) RN-PRESUPUESTOS-008. |
| `excluido` | `BOOLEAN NOT NULL DEFAULT FALSE` | **Escrito** por `ajustar_item` (`service.py:163`); leído por la guarda de aprobación (`service.py:28`) y por `_recalcular_totales_presupuesto` para filtrar ítems "activos" (`service.py:45`). |
| `motivo_exclusion` | `TEXT NULL` | **Escrito** junto con `excluido` (`service.py:164`) — se guarda incluso si es `None` (sin validación de que sea obligatorio al excluir). |

**CRUD de este módulo**: Read (`listar_items_presupuesto`,
`buscar_presupuesto_item`) y Update parcial de una fila (`actualizar_presupuesto_item`,
solo los campos presentes en el diccionario `campos`). Sin Create ni Delete — el
alta masiva es de `pricing/`.

## `procesos_comerciales` — solo el `UPDATE` de `estado`

Este módulo no es dueño de la tabla (`procesos_comerciales/` lo es, ver
[`../procesos_comerciales/base_de_datos.md`](../procesos_comerciales/base_de_datos.md)).
`buscar_proceso_comercial` (`repository.py:18-26`) lee `id, drogueria_id, clase,
estado` — el único consumidor de todo el repositorio que trae `estado`
explícitamente (ya cuantificado en
[`../procesos_comerciales/arquitectura.md`](../procesos_comerciales/arquitectura.md)).
`actualizar_proceso_comercial` (`repository.py:68-71`) ejecuta el **único
`UPDATE`** de `procesos_comerciales` en todo el repositorio:

```python
def actualizar_proceso_comercial(
    client: Client, *, proceso_comercial_id: str, campos: dict[str, Any]
) -> None:
    client.table("procesos_comerciales").update(campos).eq("id", proceso_comercial_id).execute()
```
`repository.py:68-71`. Invocado desde `presentar_presupuesto` con
`campos={"estado": "presentado"}` (`service.py:239-241`) — sin `SELECT ... FOR
UPDATE` previo, sin condición `WHERE estado=...`. Confirmado, misma cita, en
[`../procesos_comerciales/estados.md`](../procesos_comerciales/estados.md).

**CRUD de este módulo sobre `procesos_comerciales`**: Read (`clase`, `estado`,
`drogueria_id`, `id`) y Update de un único campo (`estado`, hoy siempre a
`"presentado"`). Sin Create ni Delete.

## `stock_productos` — indirecto vía `core/stock.py`

Presupuestos no construye ninguna query propia sobre `stock_productos`: delega
por completo en `core/stock.py` (`comprometer_stock_producto`,
`liberar_o_reportar`, importado en `service.py:11`). Columnas tocadas
(`cantidad_comprometida`, `cantidad_disponible`) y el mecanismo de optimistic
locking están documentados en [`../core/base_de_datos.md`](../core/base_de_datos.md)
y [`../core/flujo.md`](../core/flujo.md) Flujo A — no se repite acá. RLS de
`stock_productos` (`UPDATE` solo `admin`/`gerencia`/`compras`,
`docs/schema/rls_final.sql:190`) es el motivo por el cual
`presentar_presupuesto_para_endpoint` usa `service_role` (`service.py:284-290`,
docstring textual). Ver [`reglas.md`](./reglas.md) RN-PRESUPUESTOS-015.

## Vistas de lectura

### `v_presupuesto_comercial`

Definición: `docs/schema/rls_final.sql:320-355`. Sin costo ni detalle de cálculo
(comentario SQL explícito, `:343`). Consultada por `listar_presupuesto_comercial`
(`repository.py:74-81`).

### `v_presupuesto_revision`

Definición base: `docs/schema/extractor_final.sql:1490-1533`. Reemplazada
(`CREATE OR REPLACE VIEW`) por `docs/schema/rls_final.sql:454-501`, que agrega
`ajustado_por` (nombre de quien ajustó el precio, vía `LEFT JOIN usuarios uaj`).
Incluye `costo_usado`, `origen_costo`, `alerta_mantenimiento`. Consultada por
`listar_presupuesto_revision` (`repository.py:84-91`). Ver
[`arquitectura.md`](./arquitectura.md) para el detalle completo de columnas y el
motivo de la existencia de dos vistas.

## Resumen CRUD

| Tabla/vista | CRUD de este módulo |
|---|---|
| `presupuestos` | R/U (`estado`, `monto_total`, `items_sin_precio`, `aprobado_*`, `presentado_*`) |
| `presupuesto_items` | R/U parcial (`precio_unitario`, `cantidad_ofertada`, `metodo_precio`, `margen_resultante_pct`, `precio_ajustado_por`, `precio_original_motor`, `excluido`, `motivo_exclusion`) |
| `procesos_comerciales` | R (`clase`, `estado`) / U de un único campo (`estado`, único `UPDATE` de la tabla en todo el repositorio) |
| `stock_productos` | U indirecto, vía `core/stock.py`, condicionado a `proceso["clase"] == "cotizacion"` |
| `historial_cambios` | C (vía `core/audit.registrar_cambio`, entidades `"presupuesto"` y `"proceso_comercial"`) |
