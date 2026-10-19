# Base de datos — Usuarios

## `usuarios`

Usuarios es el módulo dueño de esta tabla en sentido de negocio: modelo, roles válidos
y reglas de creación/edición viven acá. Core la lee de forma acotada
(`id, drogueria_id, rol, activo, debe_cambiar_password`) para resolver el perfil del
solicitante — ver [`../core/base_de_datos.md`](../core/base_de_datos.md#usuarios) — pero
no la modela ni la administra.

| Columna | Qué hace este módulo |
|---|---|
| `id` | PK, FK a `auth.users` con `ON DELETE CASCADE` (`docs/schema/rls_final.sql:36`). Generada por Supabase Auth Admin en `repo.crear_usuario_auth` (`repository.py:12-39`) y usada como PK al insertar el perfil (`service.py:116`). Filtro en `obtener_usuario`, `actualizar_rol`, `actualizar_activo`, `actualizar_perfil` y `eliminar_usuario_auth` (`repository.py:69-95`). |
| `drogueria_id` | Nullable, FK a `droguerias`. Escrita al crear (RN-USUARIOS-003/004) y validada según el rol (RN-USUARIOS-005/006). Leída para comparar contra la droguería del creador `admin`/`gerencia` (RN-USUARIOS-010/020/026/036/037). |
| `rol` | TEXT con CHECK en la base (incluye `"sistema"`, no representado en el `Literal Rol` — D-USUARIOS-004). Escrita al crear (`service.py:118`) y actualizada por `actualizar_rol` (`repository.py:74-75`). Leída para la protección de `superadmin`/`sistema` y el alcance de `gerencia`. |
| `nombre` | TEXT NOT NULL. Escrita al crear (`service.py:119`) y editable vía `PATCH /usuarios/me` (RN-USUARIOS-028). |
| `apellido` | TEXT nullable (`supabase/migrations/0007_apellido_y_planes.sql:19-23`). Obligatorio en `UsuarioCreate` (`models.py:15`); editable vía `PATCH /usuarios/me`. |
| `es_sistema` | BOOLEAN, default `FALSE`. Solo se escribe, siempre `False` (`service.py:121`, RN-USUARIOS-007). |
| `activo` | BOOLEAN, default `TRUE`. Escrita por `cambiar_activo` (`repository.py:78-79`); Core la evalúa en `_cargar_perfil` (`services/shared/auth.py:55-56`) para bloquear con 401 (RN-USUARIOS-021). |
| `username` | **[NUEVA, `0038`]** TEXT NOT NULL, formato `^[a-z0-9._-]{3,30}$` (CHECK `ck_usuarios_username_formato`), único sin distinguir mayúsculas (índice `ux_usuarios_username_lower` sobre `lower(username)`). DEFAULT aleatorio `'u' \|\| 12 hex` para filas insertadas por fuera del backend (seeds, fixtures). Escrita al crear (`service.py:122`) y por `cambiar_username` (`service.py:281`); leída por `obtener_usuario_por_username` (`repository.py:58-62`) en el alta, la edición y el login. |
| `debe_cambiar_password` | **[NUEVA, `0038`]** BOOLEAN NOT NULL DEFAULT `FALSE`. `TRUE` al crear (`service.py:123`) y al blanquear (`service.py:256-258`); `FALSE` tras `POST /auth/cambiar-password` (`auth/service.py:60-62`). Core la evalúa en `get_current_user` (RN-USUARIOS-035). |
| `created_at`, `updated_at` | No expuestas en ningún modelo del módulo. `created_at` define el orden del backfill de `0038`. |

El email **no** es una columna de `usuarios`: vive en `auth.users.email`. Desde
login-usuario-alta-admin, para cuentas nuevas es una dirección interna opaca
`<uuid hex>@<AUTH_EMAIL_DOMAIN>` (`service.py:103`); para cuentas anteriores sigue siendo
el email real con el que se crearon. Solo lo lee `auth/repository.py:9-16` (login y
verificación de la contraseña actual).

**Operaciones de este módulo**:

- **Create**: `repo.crear_usuario_auth` (`client.auth.admin.create_user` con
  `email_confirm=True`, `repository.py:12-39`) seguido de `repo.crear_perfil_usuario`
  (INSERT, `repository.py:65-66`). Si el INSERT falla, compensación con
  `repo.descartar_usuario_auth` (`repository.py:42-48`, RN-USUARIOS-034).
- **Read**: `repo.obtener_usuario` (`repository.py:69-71`) y
  `repo.obtener_usuario_por_username` (`repository.py:58-62`); los 2 GET hacen su propio
  SELECT directo desde `router.py:36`, `:49`.
- **Update**: `repo.actualizar_rol`, `repo.actualizar_activo` y `repo.actualizar_perfil`
  (UPDATE genérico: `nombre`/`apellido`, `username`, `debe_cambiar_password`); en Auth,
  `repo.actualizar_password_auth` (`update_user_by_id`, `repository.py:51-55`).
- **Delete**: `repo.eliminar_usuario_auth` (`repository.py:86-95`) — borra en Auth y
  cascadea a `usuarios` (RN-USUARIOS-027).

## Migración `0038_usuarios_username`

`supabase/migrations/0038_usuarios_username.sql` (down en
`0038_usuarios_username.down.sql`):

1. Agrega `debe_cambiar_password BOOLEAN NOT NULL DEFAULT FALSE` (`:24-25`): los usuarios
   existentes quedan en `FALSE` y conservan su contraseña.
2. Agrega `username TEXT` (`:30-31`) y lo completa en un bloque `DO` (`:33-65`) para las
   filas con `username IS NULL`, en orden `created_at, id`: parte local de
   `auth.users.email` en minúsculas, sin caracteres fuera del formato, recortada a 27;
   vacía → `usuario`; 1-2 caracteres → se completa con `0`; si choca, sufijo desde 2
   (`jperez`, `jperez2`, ...). RN-USUARIOS-041.
3. DEFAULT aleatorio (`:67-68`), `NOT NULL` (`:70-71`), CHECK de formato (`:73-75`) e
   índice único sobre `lower(username)` (`:77`).
4. Re-ejecutable: el backfill solo toca filas con `username NULL`; `IF NOT EXISTS`/
   `DROP CONSTRAINT IF EXISTS` en el resto.

El down (`.down.sql:4-7`) borra el índice, el CHECK y ambas columnas.

**Estado**: [IMPLEMENTADO] en SQL, revisado, **no aplicada a ninguna base**. Hay que
aplicarla **antes** de desplegar el backend de esta rama: el backend nuevo selecciona
`debe_cambiar_password` en cada request autenticado (`services/shared/auth.py:47`) —
ver [`pendientes.md`](./pendientes.md).

## Policy RLS `usuarios_sel`

`docs/schema/rls_final.sql:117`:

```sql
CREATE POLICY usuarios_sel ON usuarios FOR SELECT USING (
  (select es_superadmin())
  OR drogueria_id = (select get_drogueria_id())
  OR id = (select auth.uid())
);
```

De esta policy dependen `GET /usuarios` y `GET /usuarios/{usuario_id}` para acotar qué
filas ve cada usuario (sin filtro `.eq("drogueria_id", ...)` en Python, `router.py:36`,
`:49`). `0038` no toca RLS: `debe_cambiar_password` **no** se evalúa en ninguna policy
(el bloqueo es solo del backend, ver [`pendientes.md`](./pendientes.md)).

`docs/schema/rls_final.sql:118-124` define además `usuarios_ins`, `usuarios_upd` y
`usuarios_del`, pero ninguna aplica al camino de escritura de este módulo: todos los
endpoints de escritura usan `get_service_client()`, que bypasea RLS.

**Advertencia sobre el origen de `rls_final.sql`**: según `docs/schema/README.md:3-7` es un
snapshot de referencia de las policies aplicadas manualmente, no una migración
versionada. La `CREATE TABLE usuarios` completa y sus policies siguen sin migración; las
columnas `apellido` (`0007`) y `username`/`debe_cambiar_password` (`0038`) sí la tienen.
