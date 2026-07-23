# Base de datos — Matching

Todas las operaciones vía `repository.py` usan `supabase-py`. `service.py` recibe el
cliente como parámetro (`client: Client`) en `procesar_matching_item`,
`confirmar_matching` y `marcar_sin_match` — es `get_service_client()` cuando corre
desde los endpoints de confirmación/sin-match (`service.py:214-229`), o
`service_client` de test cuando corre desde los tests de integración. `router.py`
además usa `user_client` (RLS-aware, `core.database.get_user_client`) para sus
propios `SELECT` — ver [`casos_de_uso.md`](./casos_de_uso.md).

## `items_proceso` (no es dueño — solo lector/actualizador)

Tabla dueña de `extraccion/` (la crea) y, funcionalmente, de `procesos_comerciales/`
(es su hija). Definición: `docs/schema/extractor_final.sql:416-438`.

| Columna | Uso en este módulo |
|---|---|
| `id` | Clave de búsqueda (`buscar_item_proceso`, `repository.py:7-11`) y de actualización (`actualizar_item_matching`, `repository.py:103-106`). |
| `proceso_comercial_id` | Leída para resolver el proceso y de ahí el `cliente_id` (`confirmar_matching`, `service.py:151-152`). |
| `drogueria_id` | Leída de la fila del item (`service.py:153`); usada además para escopear `listar_productos_activos` y `matching_candidatos`. |
| `descripcion` | Insumo para `normalizar_descripcion` (`service.py:43`, `service.py:159-161` en confirmación). |
| `descripcion_normalizada` | Escrita en cada llamada a `procesar_matching_item`, tanto en el camino de alias (`service.py:55`) como en el fuzzy (`service.py:97`). Leída en `confirmar_matching` si ya estaba seteada (`service.py:159`). |
| `producto_id` | Escrita: al camino automático (`service.py:56`, el `producto_id` del alias), al confirmar (`service.py:176`, el elegido por el humano) y a `None` al marcar sin match (`service.py:201`). No se escribe en el camino fuzzy — solo se registran candidatos, el `producto_id` del item queda `NULL` hasta que alguien confirme. |
| `alias_id` | Escrita: al camino automático (`service.py:57`, el alias que resolvió), al confirmar (`service.py:177`, el alias creado/reusado por `_upsert_alias`). |
| `estado_matching` | Escrita en los 4 casos de uso: `"automatico"` (`service.py:58`), `"sugerido"`/`"pendiente"` (`service.py:98`), `"confirmado"` (`service.py:178`), `"sin_match"` (`service.py:201`). Ver [`estados.md`](./estados.md). |
| `confianza_matching` | Escrita como `None` en el camino automático (`service.py:59`) y a `None` al marcar sin match; escrita con el mejor score fuzzy (como texto, `str(mejor_confianza)`) en el camino de sugerencia (`service.py:99`). No se reescribe al confirmar — `confirmar_matching` solo la lee para devolverla en la respuesta (`service.py:182-188`). |

**Operaciones**:
- `SELECT` — `buscar_item_proceso` (`repository.py:7-11`, por `id`, `select("*")`),
  llamado en `confirmar_matching` (`service.py:147`) y `marcar_sin_match`
  (`service.py:194`). También un `SELECT id, drogueria_id` propio de `router.py:22-31`
  (con `user_client`) y un `SELECT *` sobre la vista `v_matching_pendiente`
  (`router.py:68`).
- `UPDATE` — `actualizar_item_matching` (`repository.py:103-106`), usada en los 3
  casos de uso públicos de `service.py` (`:51-61`, `:93-101`, `:172-180`, `:198-201`).

## `cliente_producto_alias` (dueño de este módulo)

Definición: `docs/schema/extractor_final.sql:251-271`. Constraint relevante:
`uq_alias_vigente` — índice único parcial sobre `(cliente_id, descripcion_normalizada)
WHERE vigente = TRUE` (`extractor_final.sql:267-269`), que garantiza a nivel de base
que solo puede haber un alias vigente por combinación cliente+descripción.

| Columna | Uso en este módulo |
|---|---|
| `cliente_id`, `descripcion_normalizada` | Filtro de búsqueda del alias vigente (`buscar_alias_vigente`, `repository.py:25-37`). |
| `vigente` | Filtro adicional de la búsqueda (`=True`); escrita a `False` al invalidar (`invalidar_alias`, `repository.py:61-62`). |
| `veces_usado` | Incrementada en `+1` cada vez que el alias resuelve un matching automático (`marcar_alias_usado`, `repository.py:52-58`, llamado en `service.py:50`). |
| `ultimo_uso_at` | Escrita con `datetime.now(timezone.utc).isoformat()` en el mismo `UPDATE` que `veces_usado` (`repository.py:55-56`). |
| `producto_id`, `descripcion_original`, `drogueria_id`, `creado_por` | Escritas al crear un alias nuevo (`crear_alias`, `repository.py:71-89`, llamado en `_upsert_alias`, `service.py:132-140`). |

**Operaciones**:
- `SELECT` — `buscar_alias_vigente` (`repository.py:25-37`), llamada dos veces por
  flujo distinto: en `procesar_matching_item` (`service.py:46-48`, matching
  automático) y en `_upsert_alias` (`service.py:123-125`, al confirmar, para decidir
  si reusar/invalidar/crear).
- `UPDATE` — `marcar_alias_usado` (`repository.py:52-58`, incrementa contador) y
  `invalidar_alias` (`repository.py:61-62`, solo `vigente=False`).
- `INSERT` — `crear_alias` (`repository.py:71-89`).

## `matching_candidatos` (dueño de este módulo)

Definición: `docs/schema/extractor_final.sql:446-460`. Constraints: `uq_mc` —
único por `(item_proceso_id, producto_id)` (evita duplicar el mismo candidato para el
mismo renglón); `ck_mc_conf` — `confianza` entre 0 y 100; `ck_mc_metodo` — `metodo IN
('exact', 'fuzzy', 'embedding', 'manual')`, aunque el código de este módulo solo
inserta `metodo="fuzzy"` (ver [`reglas.md`](./reglas.md)).

| Columna | Uso en este módulo |
|---|---|
| `item_proceso_id`, `drogueria_id`, `producto_id` | Armadas en batch por `_generar_candidatos` + el bloque de inserción de `procesar_matching_item` (`service.py:74-86`). |
| `confianza` | El score de `rapidfuzz`, redondeado a 2 decimales y convertido a texto (`str(c.confianza)`, `service.py:80`, `Decimal(str(round(score, 2)))` en `service.py:31`). |
| `metodo` | Siempre `"fuzzy"` en este módulo (`service.py:32,81`). |
| `detalle_scoring` | `{"scorer": "WRatio"}` fijo (`service.py:33,82`) — JSONB, sin más metadata (ni el score crudo, ni el nombre del producto comparado). |
| `elegido` | `False` por defecto (schema); pasada a `True` en `confirmar_matching` vía `marcar_candidato_elegido` (`repository.py:97-100`, `service.py:155`) — es un `UPDATE` condicional por `(item_proceso_id, producto_id)`: si no existe una fila de candidato con ese par (p. ej. el producto elegido no vino del fuzzy, sino que el usuario lo buscó manualmente en el catálogo), el `UPDATE` no afecta ninguna fila y no falla — no hay verificación de `rowcount`. |

**Operaciones**:
- `INSERT` — `insertar_candidatos` (`repository.py:92-95`, batch, no-op si la lista
  está vacía), llamada en `procesar_matching_item` (`service.py:86`) solo cuando el
  fuzzy generó al menos un candidato.
- `UPDATE` — `marcar_candidato_elegido` (`repository.py:97-100`), llamada en
  `confirmar_matching` (`service.py:155`), siempre, sin importar si el `producto_id`
  confirmado tiene o no una fila de candidato previa.

## `proveedor_producto_alias` (existe en el schema — sin código en este módulo)

Definición: `docs/schema/extractor_final.sql:956-973`, mismas columnas que
`cliente_producto_alias` pero con `proveedor_id` en vez de `cliente_id` (sin el
índice único parcial equivalente a `uq_alias_vigente` — no se encontró en el schema).
Comentario de schema: "Memoria de matching descripción→producto por PROVEEDOR (espejo
de cliente_producto_alias). Distintos proveedores nombran el mismo producto de formas
diferentes; mejora el matching de comparativas." (`extractor_final.sql:973`).

Confirmado en esta sesión: **ninguna función de `matching/repository.py` ni
`matching/service.py` lee o escribe esta tabla.** El propio `repository.py:65-68`
tiene un comentario explícito reconociendo la deuda:

```python
# proveedor_producto_alias (espejo por proveedor de cliente_producto_alias, §2 del spec)
# no tiene ningún código propio todavía -- ni lectura ni escritura. Scope futuro, igual
# que orden_compra/compras vs. comparativas en su momento: no bloquea el cierre de esta
# ronda porque nada del pipeline actual depende de esa tabla.
```

Consistente con `services/presupuestacion/ROADMAP.md:43-49`, que documenta lo mismo
desde la auditoría de seguridad: "Tabla y columnas ya existen en el schema... pero no
tiene ningún código propio — ni lectura ni escritura... No bloquea el matching
cliente→producto que sí está implementado; el matching proveedor→producto nunca se
pidió construir en esta ronda." Ver [`pendientes.md`](./pendientes.md) P2.

## `productos` (no es dueño — solo lector, tabla de `catalogo/`)

| Columna | Uso en este módulo |
|---|---|
| `id`, `nombre` | `listar_productos_activos` (`repository.py:40-49`) trae `id, nombre` de todos los productos `activo=True AND deleted_at IS NULL` de la droguería — insumo del fuzzy matching (`service.py:20,24`). |

**Operaciones**: solo `SELECT`, sin filtro de cantidad ni paginación. Ver
[`arquitectura.md`](./arquitectura.md) (acoplamiento con `catalogo/`) y
[`pendientes.md`](./pendientes.md) (riesgo de escalabilidad).

## `procesos_comerciales` (no es dueño — solo lector)

| Columna | Uso en este módulo |
|---|---|
| `id, drogueria_id, cliente_id` | `buscar_proceso_comercial` (`repository.py:14-22`), usado en `confirmar_matching` para resolver el `cliente_id` del renglón que se está confirmando (`service.py:151-152`) — necesario para el `_upsert_alias` posterior. |

**Operaciones**: solo `SELECT`, por `id`.
