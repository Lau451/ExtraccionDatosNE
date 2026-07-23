# Base de datos — Extracción-Validación

Todas las operaciones vía `repository.py` usan `supabase-py`. `service.py` recibe el
cliente como parámetro (`client: Client`) en todas sus funciones — es
`get_service_client()` cuando corre desde el endpoint (`service.py:308-319`), o
`service_client` de test cuando corre desde los tests de integración. `router.py`
además usa `user_client` (RLS-aware, `core.database.get_user_client`) para un
`SELECT` propio antes de delegar en el service — ver [`casos_de_uso.md`](./casos_de_uso.md).

## `extraction_results` (no es dueño — solo lector/actualizador)

Tabla dueña del módulo `../extraccion_api/` (backend legacy que la crea). Este módulo
la lee y actualiza, nunca la crea ni la borra.

| Columna | Uso en este módulo |
|---|---|
| `id` | Clave de búsqueda (`buscar_extraction_result`, `repository.py:6-10`). |
| `drogueria_id` | Usada para validar pertenencia del `proceso_comercial_id` indicado (`service.py:48-51`) y para escopear todo lo que se materializa. |
| `proceso_comercial_id` | Leída para resolver si la extracción ya está vinculada (`service.py:32`); escrita si no lo estaba y se indicó uno por parámetro (`service.py:53-57`). |
| `document_type` | Leída para decidir la rama de materialización (`service.py:266`). |
| `csv_disk_path` | Leída para abrir el CSV fuente de las filas a materializar (`service.py:69,145`). |
| `validado` | Leída para rechazar una segunda validación (`service.py:254-255`, `ConflictError`); escrita a `TRUE` al final del caso de uso (`service.py:295`). |
| `validado_por` | Escrita con el `usuario_id` que ejecuta la validación (`service.py:295`). |
| `validado_at` | Escrita con `datetime.now(timezone.utc).isoformat()` (`service.py:291,295`). |

**Operaciones**:
- `SELECT` — `buscar_extraction_result` (`repository.py:6-10`, por `id`), y un
  `SELECT` propio en `router.py:22-28` (columnas `id, drogueria_id`) para el chequeo
  de pertenencia previo a delegar en el service.
- `UPDATE` — `actualizar_extraction_result` (`repository.py:24-33`), usada dos veces
  en `service.py`: para vincular `proceso_comercial_id` (`:53-57`) y para marcar
  `validado`/`validado_por`/`validado_at` al final (`:292-296`).

## `procesos_comerciales` (no es dueño — solo lector)

Dueño real: módulo `procesos_comerciales/` (ver
[`../procesos_comerciales/base_de_datos.md`](../procesos_comerciales/base_de_datos.md)).

| Columna | Uso en este módulo |
|---|---|
| `id, drogueria_id, cliente_id, clase` | `SELECT` puntual por `id` (`buscar_proceso_comercial`, `repository.py:13-21`), usado para validar pertenencia de droguería (`service.py:48-51`) y para resolver `cliente_id` que necesita el matching (`service.py:276`). `clase` se selecciona pero no se usa en este módulo. |

**Operaciones**: solo `SELECT` (`repository.py:13-21`), llamado dos veces en el flujo
principal (`service.py:45,260-262`) — una para resolver/validar el
`proceso_comercial_id`, otra para obtener el proceso definitivo tras la resolución.

## `items_proceso` (materializado por este módulo, tipos licitación/cotización)

| Columna | Origen/uso en este módulo |
|---|---|
| `proceso_comercial_id` | El resuelto en `_resolver_proceso_comercial_id` (`service.py:76`). |
| `drogueria_id` | De la extracción (`service.py:77`). |
| `extraction_id` | El `id` de la extracción validada (`service.py:78`). |
| `numero_renglon` | `int(fila["item"].strip())` del CSV (`service.py:79`). |
| `descripcion` | `fila["descripcion"].strip()` del CSV (`service.py:73,80`). |
| `descripcion_normalizada` | `normalizar_descripcion(descripcion)` (`core.texto`, `service.py:81`). |
| `cantidad` | `fila["cantidad"].strip()` del CSV, como texto (`service.py:82`). |
| `estado_matching`, `producto_id`, `alias_id`, `confianza_matching` | No se escriben en el `INSERT` de este módulo — los completa `matching.service.procesar_matching_item` inmediatamente después, por cada fila (`service.py:88-91`). |

**Operaciones**:
- `INSERT` — `insertar_items_proceso` (`repository.py:36-39`, batch), llamado en
  `_materializar_licitacion` (`service.py:86`).
- `SELECT` — `listar_items_proceso_por_proceso` (`repository.py:42-51`, columnas
  `id, numero_renglon`), usado por `_materializar_comparativa` para vincular ofertas
  a renglones ya materializados (`service.py:147-152`).

## `comparativas` (materializado por este módulo, tipo comparativa)

| Columna | Origen/uso en este módulo |
|---|---|
| `proceso_comercial_id`, `drogueria_id`, `extraction_id` | Igual criterio que en `items_proceso` (`service.py:161-163`). |
| `cantidad_proveedores` | `len({proveedores únicos del CSV})` (`service.py:157,164`). |
| `items_analizados` | `len({renglones únicos del CSV})` (`service.py:158,165`). |
| `version_numero` | `1` por defecto (columna con `DEFAULT 1` en el schema); si hay una vigente previa, `vigente_previa["version_numero"] + 1` (`service.py:168`). |
| `reemplaza_id` | Solo si hay reemplazo: el `id` de la comparativa vigente anterior (`service.py:169`). |
| `motivo_version` | Solo si hay reemplazo: literal `"nueva extracción validada"` (`service.py:170`). |
| `es_vigente` | No se escribe explícitamente en el `INSERT` (usa el `DEFAULT TRUE` del schema); se pone en `FALSE` en la comparativa anterior vía `invalidar_comparativa` (`repository.py:68-69`) cuando hay reemplazo. |

**Operaciones**:
- `SELECT` — `buscar_comparativa_vigente` (`repository.py:54-65`, filtro
  `proceso_comercial_id` + `es_vigente=True`), usado para detectar si hay que
  versionar (`service.py:154`).
- `INSERT` — `crear_comparativa` (`repository.py:72-73`), llamado en
  `service.py:172`.
- `UPDATE` — `invalidar_comparativa` (`repository.py:68-69`, solo `es_vigente=False`),
  llamado en `service.py:184` cuando hay reemplazo.

## `ofertas_items` (materializado por este módulo, tipo comparativa)

| Columna | Origen/uso en este módulo |
|---|---|
| `comparativa_id` | La recién creada (`service.py:211`). |
| `drogueria_id` | De la extracción (`service.py:212`). |
| `item_proceso_id` | Vinculado por `numero_renglon` contra `items_por_renglon` si existe match; `None` si el texto de renglón no es un entero válido o no hay `item_proceso` con ese número (`service.py:203-207,213`). |
| `renglon_id` | `fila["renglon"].strip()` del CSV, como texto libre (`service.py:203,214`). |
| `proveedor` | `fila["proveedor"].strip()` del CSV (`service.py:215`). |
| `descripcion` | **Workaround**: `(fila.get("marca") or "").strip() or None` — reusa la columna `marca` del CSV de comparativa porque no existe columna `marca` en `ofertas_items` ni columna `descripcion` en ese CSV (`service.py:216-218`). Ver RN-EXTRACCIONVALIDACION-006 y D-EXTRACCIONVALIDACION-002. |
| `precio_unitario` | `fila["precio"].strip().replace(",", ".")` del CSV (`service.py:219`). |
| `es_drogueria_propia` | Siempre `False` en el `INSERT` (`service.py:220`) — no se auto-detecta. Ver RN-EXTRACCIONVALIDACION-005 y D-EXTRACCIONVALIDACION-001. |
| `posicion_precio`, `adjudicacion_estimada` | No se escriben en el `INSERT`; se completan con un `UPDATE` posterior por fila, calculado por `_computar_posiciones` (`service.py:96-109,226-231`). |

**Operaciones**:
- `INSERT` — `insertar_ofertas_items` (`repository.py:76-79`, batch), llamado en
  `service.py:224`.
- `UPDATE` — `actualizar_oferta_item` (`repository.py:82-85`), llamado una vez por
  fila creada en `service.py:227-231` para setear `posicion_precio` y
  `adjudicacion_estimada`.

## `usuarios` (no es dueño — solo lector)

Dueño real: módulo `usuarios/`.

| Columna | Uso en este módulo |
|---|---|
| `id` | `SELECT` filtrado por `drogueria_id` + `rol IN (...)` (`listar_usuarios_por_rol`, `repository.py:88-98`), usado para resolver destinatarios de la notificación de reemplazo (`service.py:115-117`, roles en `_ROLES_NOTIFICACION_REEMPLAZO`, `service.py:21`). |

**Operaciones**: solo `SELECT`.

## `notificaciones` (escritura directa, bypaseando `notificaciones/`)

| Columna | Origen/uso en este módulo |
|---|---|
| `drogueria_id`, `destinatario_id`, `tipo`, `titulo`, `mensaje`, `origen`, `proceso_comercial_id`, `comparativa_id` | Armadas en `_notificar_reemplazo_comparativa` (`service.py:112-134`), una fila por destinatario. `tipo` fijo `"comparativa_disponible"`. |

**Operaciones**: `INSERT` — `crear_notificacion` (`repository.py:101-102`), **directo
contra la tabla**, sin pasar por `notificaciones.service.crear_notificacion` — ver
[`arquitectura.md`](./arquitectura.md) y [`pendientes.md`](./pendientes.md). Este
módulo no toca `notificacion_entregas` ni `notificacion_preferencias`.

## `historial_cambios` (auditoría — uso parcial)

Escrita vía `core.audit` (`registrar_evento_ciclo_vida`, `registrar_cambio`), **solo
dentro de `_materializar_comparativa`** (`service.py:173-181,185-196`). Ningún otro
punto del módulo escribe en esta tabla — ver [`pendientes.md`](./pendientes.md) para
el detalle del alcance parcial.

| Operación | Cuándo | Evidencia |
|---|---|---|
| `INSERT` (evento `creacion`) | Al crear cualquier comparativa (con o sin reemplazo) | `service.py:173-181` |
| `INSERT` (cambio de campo `es_vigente`) | Solo si hubo reemplazo, sobre la comparativa anterior | `service.py:185-196` |
