# Flujos — Usuarios

6 flujos (antes 3). Cada paso cita `archivo:línea` releído y verificado en esta sesión de
actualización.

## Flujo 1 — Alta de usuario por invitación (`POST /usuarios`)

1. El router exige `require_roles("superadmin", "admin")`
   (`usuarios/router.py:46-47`); si el usuario autenticado no tiene uno de esos roles, la
   dependencia levanta `ForbiddenError` antes de que se ejecute el handler
   (ver [`../core/`](../core/)).
2. `crear_usuario_endpoint` llama a `crear_usuario_para_endpoint(creador=usuario,
   body=body)` (`usuarios/router.py:49`).
3. `crear_usuario_para_endpoint` resuelve `get_service_client()` y delega en
   `crear_usuario` (`usuarios/service.py:131-132`).
4. `crear_usuario` valida en este orden (`usuarios/service.py:14-28`):
   1. RN-USUARIOS-001 — el creador es `superadmin`/`admin` (`:14-15`).
   2. RN-USUARIOS-002 — si `body.rol in ("superadmin", "admin")`, el creador debe ser
      `superadmin` (`:17-18`).
   3. RN-USUARIOS-003/004 — resuelve `drogueria_id`: la del creador si es `admin`
      (`:20-21`), o la del body si es `superadmin` (`:22-23`).
   4. RN-USUARIOS-005/006 — valida consistencia entre `body.rol` y el `drogueria_id`
      resuelto (`:25-28`).
5. Si todas las validaciones pasan, se arma `redirect_to =
   f"{get_settings().frontend_url}/accept-invite"` (`:30`) y se llama a
   `repo.invitar_usuario_auth(client, email=body.email, redirect_to=redirect_to,
   nombre=body.nombre, apellido=body.apellido, rol=body.rol)` (`:31-38`), que invoca
   `client.auth.admin.invite_user_by_email` con `nombre`/`apellido`/`rol` como metadata
   de la invitación (`repository.py:9-19`). Supabase Auth crea la cuenta **sin
   contraseña asignada** y dispara el email de invitación al `redirect_to` indicado
   (RN-USUARIOS-013).
6. Si Supabase Auth responde con error, `invitar_usuario_auth` lo traduce a un error de
   dominio en vez de propagar la excepción cruda (`repository.py:20-32`): `429` →
   `ConflictError`, cualquier otro código → `ValidationError`. En ambos casos la
   respuesta HTTP llega con `CORSMiddleware` aplicado y un mensaje legible — ver
   RN-USUARIOS-013.
7. `repo.crear_perfil_usuario` inserta la fila de perfil en `usuarios` con el `id`
   devuelto por Auth, `drogueria_id`, `rol`, `nombre`, `apellido` y `es_sistema=False`
   hardcodeado (RN-USUARIOS-007) (`usuarios/service.py:39-49`,
   `usuarios/repository.py:36-37`).
8. El endpoint responde con `UsuarioOut` construido a partir de la fila insertada
   (`usuarios/router.py:45`, `response_model=UsuarioOut`).

Si cualquier validación del paso 4 falla, se levanta la excepción de dominio
correspondiente **antes** de llamar a Auth Admin — no queda una cuenta de Auth huérfana
sin fila de perfil por una regla de negocio rechazada. Si el propio `INSERT` del paso 7
fallara después de que Auth Admin ya envió la invitación (paso 5), no hay compensación
automática en el código revisado — pendiente de definición funcional (no observado en
los tests). El usuario terminaría de definir su contraseña recién cuando acepta la
invitación desde `{frontend_url}/accept-invite`, fuera del alcance de este backend.

## Flujo 2 — Cambio de rol (`PATCH /usuarios/{usuario_id}/rol`)

1. El router exige `require_roles("superadmin", "admin")`
   (`usuarios/router.py:52-56`).
2. `cambiar_rol_endpoint` llama a `cambiar_rol_para_endpoint(creador=usuario,
   usuario_id=usuario_id, nuevo_rol=body.rol)` (`usuarios/router.py:58`).
3. `cambiar_rol_para_endpoint` resuelve `get_service_client()` y delega en `cambiar_rol`
   (`usuarios/service.py:135-136`).
4. `cambiar_rol` valida en este orden (`usuarios/service.py:52-76`) — **el orden cambió
   respecto de la revisión anterior**: el chequeo de auto-modificación ahora corre antes
   que la comprobación de existencia:
   1. RN-USUARIOS-008 — el creador es `superadmin`/`admin` (`:55-56`).
   2. RN-USUARIOS-014 — `usuario_id != creador.id` (`:58-59`), **nuevo**, antes de tocar
      la base.
   3. RN-USUARIOS-011 — el usuario objetivo existe (`repo.obtener_usuario`, `:61-63`); si
      no, `NotFoundError`.
   4. RN-USUARIOS-009 — ni el rol actual del objetivo ni `nuevo_rol` son `superadmin` o
      `sistema` (`:65-68`, extendido a `sistema` en esta sesión).
   5. RN-USUARIOS-015 — si `nuevo_rol == "admin"`, el creador debe ser `superadmin`
      (`:70-71`), **nuevo**.
   6. RN-USUARIOS-010 — si el creador es `admin`, el objetivo pertenece a su misma
      `drogueria_id` (`:73-74`).
5. Si todas las validaciones pasan, `repo.actualizar_rol(client, usuario_id=usuario_id,
   rol=nuevo_rol)` hace el `UPDATE` de la columna `rol` (`usuarios/service.py:76`,
   `usuarios/repository.py:45-46`).
6. El endpoint responde con `UsuarioOut` construido a partir de la fila actualizada
   (`usuarios/router.py:52`, `response_model=UsuarioOut`).

Notar que la auto-modificación (paso 4.2) y la existencia (4.3) ocurren **antes** que las
reglas de protección de rol (4.4/4.5) y de tenant (4.6): un `admin` que intenta cambiar
su propio rol recibe `ForbiddenError` de auto-modificación sin importar si el `nuevo_rol`
pedido también hubiera sido rechazado por otra regla.

## Flujo 3 — Activar/desactivar usuario (`PATCH /usuarios/{usuario_id}/activo`) — **[NUEVO]**

1. El router exige `require_roles("superadmin", "admin")` (`usuarios/router.py:61-65`).
2. `cambiar_activo_endpoint` llama a `cambiar_activo_para_endpoint(creador=usuario,
   usuario_id=usuario_id, activo=body.activo)` (`usuarios/router.py:67`).
3. `cambiar_activo_para_endpoint` resuelve `get_service_client()` y delega en
   `cambiar_activo` (`usuarios/service.py:139-140`).
4. `cambiar_activo` valida, en el mismo orden que `cambiar_rol`
   (`usuarios/service.py:79-98`):
   1. RN-USUARIOS-016 — el creador es `superadmin`/`admin` (`:82-83`).
   2. RN-USUARIOS-017 — `usuario_id != creador.id` (`:85-86`).
   3. RN-USUARIOS-018 — el usuario objetivo existe (`:88-90`).
   4. RN-USUARIOS-019 — el objetivo no es `superadmin` ni `sistema` (`:92-93`).
   5. RN-USUARIOS-020 — si el creador es `admin`, el objetivo pertenece a su misma
      `drogueria_id` (`:95-96`).
5. Si todas las validaciones pasan, `repo.actualizar_activo(client, usuario_id=usuario_id,
   activo=activo)` hace el `UPDATE` de la columna `activo` (`usuarios/service.py:98`,
   `usuarios/repository.py:49-50`).
6. El endpoint responde con `UsuarioOut` (`usuarios/router.py:61`,
   `response_model=UsuarioOut`).
7. **Efecto diferido, en otro módulo (RN-USUARIOS-021)**: el `UPDATE` en sí no bloquea al
   usuario de inmediato en ninguna sesión ya autenticada del lado del token JWT — el
   bloqueo ocurre en la **siguiente** vez que ese usuario pase por `get_current_user`
   (`core/auth.py:33-49`), que ahora incluye `activo` en el `SELECT` (`:39`) y levanta
   `AuthenticationError` (401) si `activo=False` (`:47-48`), sin importar que el JWT de
   Supabase siga técnicamente vigente hasta su expiración.

## Flujo 4 — Eliminar usuario (`DELETE /usuarios/{usuario_id}`) — **[NUEVO]**

1. El router exige `require_roles("superadmin", "admin")` (`usuarios/router.py:78-81`).
2. `eliminar_usuario_endpoint` llama a `eliminar_usuario_para_endpoint(creador=usuario,
   usuario_id=usuario_id)` (`usuarios/router.py:83`).
3. `eliminar_usuario_para_endpoint` resuelve `get_service_client()` y delega en
   `eliminar_usuario` (`usuarios/service.py:149-150`).
4. `eliminar_usuario` valida, exactamente el mismo alcance que `cambiar_activo`
   (`usuarios/service.py:101-118`):
   1. RN-USUARIOS-022 — el creador es `superadmin`/`admin` (`:102-103`).
   2. RN-USUARIOS-023 — `usuario_id != creador.id` (`:105-106`).
   3. RN-USUARIOS-024 — el usuario objetivo existe (`:108-110`).
   4. RN-USUARIOS-025 — el objetivo no es `superadmin` ni `sistema` (`:112-113`).
   5. RN-USUARIOS-026 — si el creador es `admin`, el objetivo pertenece a su misma
      `drogueria_id` (`:115-116`).
5. Si todas las validaciones pasan, `repo.eliminar_usuario_auth(client,
   usuario_id=usuario_id)` llama a `client.auth.admin.delete_user(usuario_id)`
   (`usuarios/service.py:118`, `usuarios/repository.py:57-61`). La FK
   `usuarios.id → auth.users.id` tiene `ON DELETE CASCADE`
   (`docs/schema/rls_final.sql:36`), así que borrar en Auth alcanza para borrar también
   la fila de `usuarios` — no hay un `DELETE` explícito sobre `usuarios` en este módulo.
6. Si el usuario tiene actividad asociada por FK sin cascada (eventos, historial de
   cambios), el `DELETE` en cascada la viola y Supabase Auth devuelve `AuthApiError`,
   que `eliminar_usuario_auth` traduce a `ConflictError` (RN-USUARIOS-027,
   `repository.py:62-66`) en vez de propagar el error crudo.
7. El endpoint responde `204 No Content` sin body (`usuarios/router.py:78`,
   `status_code=204`).

## Flujo 5 — Editar perfil propio (`PATCH /usuarios/me`) — **[NUEVO]**

1. El router exige únicamente `Depends(get_current_user)` (`usuarios/router.py:73`), sin
   `require_roles` — cualquier usuario autenticado con perfil válido puede invocarlo.
2. `actualizar_perfil_propio_endpoint` llama a
   `actualizar_perfil_propio_para_endpoint(usuario_id=usuario.id, body=body)`
   (`usuarios/router.py:75`) — **el `usuario_id` sale del token resuelto por
   `get_current_user`, nunca de un parámetro de la URL** (RN-USUARIOS-028); no hay forma
   de editar el perfil de otro usuario por esta vía.
3. `actualizar_perfil_propio_para_endpoint` resuelve `get_service_client()` y delega en
   `actualizar_perfil_propio` (`usuarios/service.py:143-146`).
4. `actualizar_perfil_propio` no aplica ninguna regla de rol; solo calcula
   `body.model_dump(exclude_unset=True)` (`:127`) para no pisar con `None` los campos que
   el cliente no envió, y llama a `repo.actualizar_perfil(client, usuario_id=usuario_id,
   campos=campos)` (`:128`, `repository.py:53-54`), un `UPDATE` genérico con el dict de
   campos provisto.
5. El endpoint responde con `UsuarioOut` actualizado (`usuarios/router.py:70`,
   `response_model=UsuarioOut`).

## Flujo 6 — Listado y obtención (`GET /usuarios`, `GET /usuarios/{usuario_id}`)

Sin cambios respecto de la revisión anterior: ninguno de los dos pasa por
`repository.py` ni por `service.py` — el router consulta la tabla directo.

1. El router exige únicamente `Depends(get_current_user)` (`usuarios/router.py:27`,
   `:36`), sin `require_roles`: cualquier usuario autenticado con perfil válido en
   `usuarios` puede invocar estos endpoints.
2. Se inyecta `user_client` vía `Depends(get_user_client)` (`usuarios/router.py:28`,
   `:37`) — el cliente **con RLS**, autenticado con el JWT del propio solicitante.
3. **Listado**: `user_client.table("usuarios").select("*").order("nombre").execute().data`
   (`usuarios/router.py:30`) — sin ningún filtro `.eq("drogueria_id", ...)` explícito en
   Python.
4. **Obtención por id**:
   `user_client.table("usuarios").select("*").eq("id", usuario_id).limit(1).execute()`
   (`usuarios/router.py:39`); si no hay resultado, `NotFoundError("No se encontró el
   usuario")` (`usuarios/router.py:40-41`); si lo hay, se devuelve la primera fila
   (`:42`).
5. En ambos casos, qué filas devuelve efectivamente el `SELECT *` — es decir, el
   aislamiento por droguería, si existe — depende exclusivamente de la policy
   `usuarios_sel` que evalúa Postgres del lado del servidor
   (`docs/schema/rls_final.sql:117`, ver [`base_de_datos.md`](./base_de_datos.md)), no de
   ningún código de este módulo.
6. **Nota de consistencia**: un usuario con `activo=False` sigue apareciendo en estos
   listados si RLS lo deja ver (el campo se filtra en `get_current_user` para bloquear al
   propio usuario desactivado, RN-USUARIOS-021, pero no se usa como filtro de estos dos
   `SELECT *`) — es decir, un `admin` puede ver en `GET /usuarios` usuarios desactivados
   de su droguería con `activo: false` en la respuesta, sin filtro adicional.
