# Base de datos — Core

Core toca 3 tablas de Supabase/Postgres. No es dueño de ninguna de las tres en sentido
estricto de "módulo que define su modelo de negocio": son tablas de infraestructura
(`historial_cambios`, propiedad conceptual de Core) o tablas que Core solo lee para
resolver identidad (`usuarios`, `stock_productos`).

## `stock_productos`

Leída y actualizada exclusivamente por `core/stock.py`. Core no la crea ni la borra; el
alta/baja de filas de esta tabla es responsabilidad de otros módulos (fuera de
alcance de esta documentación).

| Columna | Uso en Core |
|---|---|
| `id` | Identificador de fila; usado como filtro `.eq("id", fila_id)` en todos los UPDATE condicionales (`services/presupuestacion/core/stock.py:37`, `:51`, `:26-28`). |
| `producto_id` | Filtro de `listar_stock_por_producto` (`core/stock.py:19`). |
| `drogueria_id` | Filtro de `listar_stock_por_producto` (`core/stock.py:20`); acota el pool de depósitos a una sola droguería. |
| `cantidad_comprometida` | Leída y actualizada con optimistic locking (`WHERE cantidad_comprometida = valor_leído`) en `actualizar_comprometida_si_no_cambio` (`core/stock.py:31-41`). Se incrementa al comprometer (`core/stock.py:80-86`) y se decrementa al liberar (`core/stock.py:107-113`, `:225-231`). |
| `cantidad_disponible` | Leída para calcular "libre" (`disponible - comprometida`, `core/stock.py:75`) y actualizada con optimistic locking análogo en `actualizar_disponible_si_no_cambio` (`core/stock.py:44-54`), descontada solo al confirmar una entrega aceptada (`core/stock.py:256-262`). |

**Operaciones**: SELECT (`listar_stock_por_producto`, `core/stock.py:13-23`;
`buscar_fila_stock`, `core/stock.py:26-28`) y UPDATE condicional sobre
`cantidad_comprometida` o `cantidad_disponible` (nunca ambas en la misma sentencia).
Core no hace INSERT ni DELETE sobre esta tabla.

## `historial_cambios`

Escrita por `core/audit.py`, leída por `auditoria/router.py`. Es la tabla más propia de
Core en el sentido de que su forma (columnas, semántica de `tipo_cambio`) está definida
por el propio módulo.

| Columna | Uso en Core |
|---|---|
| `drogueria_id` | Insertada en cada fila (`core/audit.py:52`, `:106`); no se usa como filtro de lectura en `auditoria/router.py` (el filtro de droguería, si existe, lo aplica RLS vía `get_user_client`, no una cláusula explícita del router). |
| `<entidad>_id` (una de `proceso_comercial_id`, `comparativa_id`, `orden_compra_id`, `presupuesto_id`, `evento_id`) | Columna FK dinámica, resuelta vía `_COLUMNA_FK_POR_ENTIDAD[entidad]` al insertar (`core/audit.py:53`, `:107`) y al filtrar en la lectura (`auditoria/router.py:20`, `:24`). |
| `batch_id` | Generado con `uuid.uuid4()` si no se pasa explícito (`core/audit.py:76`, `:104`); agrupa varios cambios de una misma operación. |
| `tipo_cambio` | `"estado"` o `"campo"` según el campo auditado (`core/audit.py:55`), o directamente el valor pasado (`"creacion"`, `"eliminacion"`, `"restauracion"`) para eventos de ciclo de vida (`core/audit.py:109`). |
| `campo` | Nombre del campo modificado; ausente (no se incluye la clave) en eventos de ciclo de vida (`core/audit.py:105-112`, no hay clave `campo`). |
| `valor_anterior`, `valor_nuevo` | Serializados con `_a_texto` (`core/audit.py:21-28`, usado en `:57-58`). |
| `origen` | Uno de los valores de `OrigenCambio` (`"usuario"`, `"ia"`, `"automatizacion"`, `"webhook"`, `"api"`, `"sistema"`, `core/audit.py:10`). |
| `usuario_id` | Id del usuario (o del usuario de sistema) que originó el cambio. |
| `created_at` | No la escribe Core explícitamente (columna con default de la base, `services/presupuestacion/auditoria/models.py:27` la modela como `datetime` de salida); usada para ordenar en la lectura (`auditoria/router.py:25`, `.order("created_at", desc=True)`). |

**Operaciones**: INSERT (`registrar_cambio`, `core/audit.py:31-62`;
`registrar_evento_ciclo_vida`, `core/audit.py:93-114`) y SELECT
(`auditoria/router.py:21-27`). Core no hace UPDATE ni DELETE sobre esta tabla — es un
log append-only.

## `usuarios`

Leída únicamente por `core/auth.py`. **Core NO es dueño de esta tabla.** El modelo,
las columnas completas y las reglas de negocio de `usuarios` (alta, roles disponibles,
edición de perfil) pertenecen al módulo `usuarios/` de `presupuestacion/`; Core solo la
consulta de forma acotada para resolver el perfil del solicitante autenticado.

| Columna | Uso en Core |
|---|---|
| `id` | Filtro `.eq("id", claims.sub)` para ubicar la fila del usuario autenticado (`services/presupuestacion/core/auth.py:40`). |
| `drogueria_id` | Proyectada en el `SELECT` y mapeada a `UsuarioPerfil.drogueria_id` (`core/auth.py:39`, `:20`); nullable (`str | None`). |
| `rol` | Proyectada en el `SELECT` y usada por `require_roles` para autorizar (`core/auth.py:39`, `:53`). |
| `activo` | Proyectada en el `SELECT` y mapeada a `UsuarioPerfil.activo`; si es `False`, `_cargar_perfil` levanta `AuthenticationError` en vez de devolver el perfil (`services/shared/auth.py:55-56` — ver RN-CORE-026). |
| `debe_cambiar_password` | **[NUEVA, migración `0038`]** Proyectada en el `SELECT` y mapeada a `UsuarioPerfil.debe_cambiar_password` (default `False`); si es `True`, `get_current_user` levanta `ForbiddenError` (403) salvo en la dependencia permisiva (`services/shared/auth.py:60-83` — ver RN-CORE-027). |

**Operaciones**: SELECT únicamente (`services/shared/auth.py:45-51`, reexportado por
`core/auth.py`), acotado a `id, drogueria_id, rol, activo, debe_cambiar_password`. Sin fila
para el `sub` del token → `NotFoundError` (`:52-53`). Requiere la migración `0038` aplicada:
sin la columna, este `SELECT` falla en todo request autenticado (ver
[`../usuarios/pendientes.md`](../usuarios/pendientes.md)).

## Helpers de RLS (`get_drogueria_id`, `get_rol`, `es_superadmin`, `mismo_tenant`, `password_al_dia`)

Core no los define ni los llama: viven en la base y los usan las policies RLS que se
aplican a todo lo que pasa por `get_user_client` (incluida la lectura de `usuarios` de
`_cargar_perfil`). No están en ninguna migración salvo `0041`; la definición de referencia
es `docs/schema/rls_final.sql:106-152`. Todos son `LANGUAGE sql STABLE SECURITY DEFINER`
con `search_path = public` y leen la fila de `usuarios` con `id = auth.uid()`;
`mismo_tenant(uuid)` es `es_superadmin() OR p_drogueria = get_drogueria_id()`.

**[MODIFICADA, migración `0041`]** `get_drogueria_id()`, `get_rol()` y `es_superadmin()`
suman `AND NOT debe_cambiar_password`: con el cambio de contraseña pendiente devuelven
`NULL`/`NULL`/`false`, como para alguien sin fila en `usuarios`, y `mismo_tenant()` deja de
dar acceso. El helper nuevo `password_al_dia()` (`FALSE` solo para quien tiene el flag en
`true`; `EXECUTE` también a `anon`) cubre las lecturas que no pasan por los otros
(`planes_sel`, `no_sel`, `ne_sel`, `np_sel`, `licitaciones_all_access`). La rama
`id = auth.uid()` de `usuarios_sel` no cambia, así que `_cargar_perfil` sigue leyendo la
propia fila y el backend puede responder el 403 de RN-CORE-027. Con el flag en `false`, los
helpers devuelven lo mismo que antes. Detalle en
[`../usuarios/reglas.md`](../usuarios/reglas.md) RN-USUARIOS-048.

**Estado**: [IMPLEMENTADO] en SQL (commit `e099547`), **no ejecutado ni aplicado**. Antes de
aplicarla hay 3 chequeos en el SQL Editor del proyecto real (detalle en
[`../usuarios/pendientes.md`](../usuarios/pendientes.md) P1-3): (1) que la definición,
dueño y permisos actuales de los helpers coincidan con `rls_final.sql`, porque `0041` los
recrea suponiendo esa definición; (2) que las policies que reescribe (`planes_sel`,
`no_sel`, `ne_sel`, `np_sel`, `licitaciones_all_access`) coincidan con lo que restaura su
`.down.sql`; (3) que no queden caminos de lectura que no pasen por los helpers ni por
`password_al_dia()` (policies con `auth.uid()` propio o `USING (true)`, vistas, RPCs).
