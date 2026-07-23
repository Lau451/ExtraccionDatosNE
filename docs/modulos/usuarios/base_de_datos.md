# Base de datos — Usuarios

## `usuarios`

Usuarios es el módulo dueño de esta tabla en sentido de negocio: modelo, roles válidos
y reglas de creación/edición de rol viven acá. Core la lee de forma acotada
(`id, drogueria_id, rol`) para resolver el perfil del solicitante — ver
[`../core/base_de_datos.md`](../core/base_de_datos.md#usuarios) — pero no la modela ni
la administra.

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK, FK a `auth.users` con `ON DELETE CASCADE` (`docs/schema/rls_final.sql:36`). Generada por Supabase Auth Admin en `repo.invitar_usuario_auth` (`repository.py:9-33`) y usada como PK al insertar el perfil (`repository.py:36-37`, `service.py:42`). Filtro de lectura/escritura en `obtener_usuario`, `actualizar_rol`, `actualizar_activo`, `actualizar_perfil` y `eliminar_usuario_auth` (`repository.py:40-66`). |
| `drogueria_id` | Nullable, FK a `droguerias`. Escrita al crear (forzada a la del creador si es `admin`, respetada del body si es `superadmin` — RN-USUARIOS-003/004) y validada contra `None` según el rol (RN-USUARIOS-005/006). Leída en `cambiar_rol`, `cambiar_activo` y `eliminar_usuario` para comparar contra la droguería del creador `admin` (RN-USUARIOS-010/020/026). |
| `rol` | TEXT con CHECK en la base (incluye `"sistema"`, no representado en el `Literal Rol` de Python — ver [`decisiones.md`](./decisiones.md) D-USUARIOS-004). Escrita al crear (`service.py:45`) y actualizada por `actualizar_rol` (`repository.py:45-46`). Leída en `cambiar_rol`, `cambiar_activo` y `eliminar_usuario` para las reglas de protección de `superadmin`/`sistema` (RN-USUARIOS-009/019/025). |
| `nombre` | TEXT NOT NULL. Escrita al crear (`service.py:46`) y editable por el propio usuario vía `PATCH /usuarios/me` → `actualizar_perfil_propio` (RN-USUARIOS-028, **nuevo en esta sesión** — antes no había ningún endpoint de edición de perfil). |
| `apellido` | **[NUEVO]** TEXT nullable (`supabase/migrations/0007_apellido_y_planes.sql:19-23` — nullable a propósito, "usuarios creados antes de esta migración no tienen valor de backfill posible"). Obligatorio en `UsuarioCreate` (`models.py:11`) para usuarios nuevos; editable vía `PATCH /usuarios/me` igual que `nombre`. |
| `es_sistema` | BOOLEAN, default `FALSE`. Este módulo **solo la escribe**, siempre hardcodeada en `False` (`service.py:47`, RN-USUARIOS-007); nunca la lee ni la actualiza. No hay vía en esta API para crear un usuario con `es_sistema=True`. |
| `activo` | BOOLEAN, default `TRUE`. **[CAMBIO MAYOR]** Antes de esta sesión el módulo la exponía en `UsuarioOut` pero nunca la leía ni escribía condicionalmente; ahora `cambiar_activo` la escribe explícitamente (`repository.actualizar_activo`, `repository.py:49-50`) vía `PATCH /usuarios/{id}/activo`, y **Core** la lee y la evalúa en `get_current_user` (`core/auth.py:39`, `:47-48`) para bloquear con 401 a cualquier usuario con `activo=False` (RN-USUARIOS-021) — el gate real vive fuera de este módulo, ver [`arquitectura.md`](./arquitectura.md). |
| `created_at`, `updated_at` | No expuestas en ningún modelo Pydantic del módulo (`models.py`); no citadas en ningún archivo de `usuarios/`. |

**Operaciones de este módulo**:

- **Create**: `repo.invitar_usuario_auth` (Supabase Auth Admin,
  `client.auth.admin.invite_user_by_email`, `repository.py:9-33` — **reemplaza a
  `crear_usuario_auth`/`create_user` con password**) seguido de `repo.crear_perfil_usuario`
  (INSERT sobre `usuarios`, `repository.py:36-37`).
- **Read**: `repo.obtener_usuario` (SELECT por `id`, `repository.py:40-42`, usado desde
  `cambiar_rol`, `cambiar_activo` y `eliminar_usuario` para validar el objetivo); los 2
  endpoints GET hacen su propio SELECT directo desde `router.py` (`:30`, `:39`), sin
  pasar por `repository.py`.
- **Update**: `repo.actualizar_rol` (columna `rol`, `repository.py:45-46`),
  `repo.actualizar_activo` (columna `activo`, `repository.py:49-50`, **nuevo**) y
  `repo.actualizar_perfil` (UPDATE genérico de `nombre`/`apellido`,
  `repository.py:53-54`, **nuevo**, usado por autoservicio de perfil propio).
- **Delete**: **[NUEVO]** `repo.eliminar_usuario_auth` (`repository.py:57-66`) — borra el
  usuario en Auth Admin, que cascadea a `usuarios` por la FK `ON DELETE CASCADE`; no hay
  un `DELETE` explícito sobre `usuarios` en el código de este módulo. Si el usuario tiene
  actividad asociada por otra FK sin cascada (eventos, historial de cambios), el borrado
  en cascada la viola y se traduce a `ConflictError` (RN-USUARIOS-027).

## Policy RLS `usuarios_sel`

`docs/schema/rls_final.sql:117` (releído y reverificado en esta sesión — sin cambios de
contenido respecto de la revisión anterior, solo se movió de línea):

```sql
CREATE POLICY usuarios_sel ON usuarios FOR SELECT USING (
  (select es_superadmin())
  OR drogueria_id = (select get_drogueria_id())
  OR id = (select auth.uid())
);
```

Esta es la policy de la que dependen enteramente `GET /usuarios` y
`GET /usuarios/{usuario_id}` para acotar qué filas ve cada usuario, dado que ninguno de
los dos endpoints aplica un filtro `.eq("drogueria_id", ...)` explícito en Python
(`router.py:30`, `:39`) — ver [`arquitectura.md`](./arquitectura.md). Por lectura de la
expresión: un `superadmin` ve todo; cualquier otro usuario ve las filas de su propia
`drogueria_id` y, adicionalmente, su propia fila (aunque ya esté cubierta por la
condición anterior si tiene `drogueria_id`).

`docs/schema/rls_final.sql:118-124` define además `usuarios_ins`, `usuarios_upd` y
`usuarios_del` sobre la misma tabla, pero **ninguna de las tres aplica** al camino de
escritura de este módulo: todos los endpoints de escritura (`POST`, los 2 `PATCH` de
rol/activo, `PATCH /me` y `DELETE`) usan `get_service_client()`
(`service.py:131-150`), que bypasea RLS por completo (ver
[`../core/arquitectura.md`](../core/arquitectura.md#patrón-service_client-vs-user_client)).
Se citan acá únicamente como contexto del estado completo de RLS sobre la tabla.

**Advertencia sobre el origen de este archivo, actualizada en esta sesión**:
`docs/schema/rls_final.sql` sigue siendo, según `docs/schema/README.md:3-7`, un snapshot
de referencia de las políticas tal como quedaron aplicadas manualmente en el proyecto
Supabase de test (`grnamollopxdlstcpxhc`) — **no es una migración ejecutable ni
versionada**, y eso sigue aplicando a la `CREATE TABLE usuarios` completa y a sus 4
policies. Pero a diferencia de lo que decía la revisión anterior, **ya no es cierto que
"ningún archivo de `supabase/migrations/` menciona la tabla `usuarios`"**: ahora hay 7
migraciones (`0001_initial.sql` a `0007_apellido_y_planes.sql`), y la última sí la toca —
`ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS apellido TEXT`
(`supabase/migrations/0007_apellido_y_planes.sql:19-20`). Es decir: la columna
`apellido` tiene historial de cambios versionado; el resto de la tabla (constraints,
columnas preexistentes) y toda su RLS siguen sin tenerlo — la única fuente de verdad de
esas partes en el repositorio sigue siendo el snapshot manual. Ver
[`pendientes.md`](./pendientes.md) para el riesgo asociado, actualizado con esta
precisión.
