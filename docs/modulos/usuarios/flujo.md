# Flujos — Usuarios

Cada paso cita `archivo:línea` de la rama `feat/login-usuario-alta-admin`.

## Flujo 1 — Alta de usuario por el admin (`POST /usuarios`)

1. El router exige `require_roles(*ROLES_GESTION_USUARIOS)` — `superadmin`, `admin`,
   `gerencia` (`usuarios/router.py:57`, `usuarios/service.py:20`). `require_roles`
   depende de `get_current_user`, así que un creador con cambio de contraseña pendiente
   recibe 403 antes del handler.
2. `crear_usuario_endpoint` llama a `crear_usuario_para_endpoint` (`router.py:59`), que
   resuelve `get_service_client()` y delega en `crear_usuario` (`service.py:309-310`).
3. `crear_usuario` valida en este orden (`service.py:77-99`):
   1. RN-USUARIOS-001 — creador en `ROLES_GESTION_USUARIOS` (`:77-78`).
   2. RN-USUARIOS-002 — `superadmin`/`admin` solo los crea un `superadmin` (`:80-81`).
   3. RN-USUARIOS-029 — `gerencia` solo crea roles inferiores (`:83-84`).
   4. RN-USUARIOS-003/004 — resuelve `drogueria_id` (`:86-89`).
   5. RN-USUARIOS-005/006 — consistencia rol/droguería (`:91-94`).
   6. RN-USUARIOS-031 — formato y normalización del username (`:96`).
   7. RN-USUARIOS-032 — contraseña temporal de al menos 8 caracteres (`:97`).
   8. RN-USUARIOS-033 — username no repetido (`:98-99`).
4. Genera el email interno opaco `<uuid hex>@<auth_email_domain>` (`:103`,
   D-USUARIOS-012) y crea la cuenta en Auth con `repo.crear_usuario_auth`
   (`:104-111`): `create_user` con la contraseña temporal, `email_confirm=True` y
   `nombre`/`apellido`/`rol` como `user_metadata` (`repository.py:19-26`). No se envía
   ningún correo. Errores de Auth → 409 (429) o 422 (resto), RN-USUARIOS-040.
5. Inserta el perfil con `id`, `drogueria_id`, `rol`, `nombre`, `apellido`,
   `es_sistema=False`, `username` y `debe_cambiar_password=True` (`service.py:113-125`).
6. Si el INSERT falla, borra la cuenta de Auth recién creada
   (`repo.descartar_usuario_auth`, `service.py:126-128`) y relanza; si era un unique
   violation del username, como `ConflictError` (`:129-130`). RN-USUARIOS-034.
7. Responde `UsuarioOut` con `debe_cambiar_password: true`. El admin le pasa username y
   contraseña temporal a la persona; en su primer login la obligan a cambiarla (Flujo 8).

Si cualquier validación del paso 3 falla, no se llama a Auth: no queda cuenta huérfana.

## Flujo 2 — Cambio de rol (`PATCH /usuarios/{usuario_id}/rol`)

1. `require_roles(*ROLES_GESTION_USUARIOS)` (`router.py:66`).
2. `cambiar_rol_para_endpoint` → `cambiar_rol` con service client (`service.py:313-314`).
3. `cambiar_rol` valida en este orden (`service.py:137-160`): RN-USUARIOS-008 (`:137-138`),
   014 auto-modificación (`:140-141`), 011 existencia (`:143-145`), 009
   `superadmin`/`sistema` (`:147-150`), 015 solo `superadmin` asigna `admin` (`:152-153`),
   029 alcance de `gerencia` (`:155-157`), 010 droguería (`:159-160`).
4. `repo.actualizar_rol` (`service.py:162`, `repository.py:74-75`) y respuesta `UsuarioOut`.

## Flujo 3 — Activar/desactivar usuario (`PATCH /usuarios/{usuario_id}/activo`)

1. `require_roles(*ROLES_GESTION_USUARIOS)` (`router.py:75`).
2. `cambiar_activo` valida (`service.py:168-184`): RN-USUARIOS-016, 017, 018, 019, 029, 020.
3. `repo.actualizar_activo` (`service.py:186`, `repository.py:78-79`).
4. **Efecto diferido (RN-USUARIOS-021)**: el bloqueo ocurre en el siguiente request del
   usuario afectado, en `_cargar_perfil` (`services/shared/auth.py:55-56`), con 401
   `Usuario desactivado` aunque su JWT siga vigente.

## Flujo 4 — Eliminar usuario (`DELETE /usuarios/{usuario_id}`)

1. `require_roles(*ROLES_GESTION_USUARIOS)` (`router.py:113`).
2. `eliminar_usuario` valida (`service.py:190-206`): RN-USUARIOS-022 a 026 y 029.
3. `repo.eliminar_usuario_auth` (`service.py:208`, `repository.py:86-95`): borra en Auth
   y cascadea a `usuarios`; con actividad asociada → 409 (RN-USUARIOS-027).
4. Responde `204 No Content` (`router.py:110`).

## Flujo 5 — Editar perfil propio (`PATCH /usuarios/me`)

1. `Depends(get_current_user)` (`router.py:105`): 403 si hay cambio pendiente.
2. `actualizar_perfil_propio_para_endpoint(usuario_id=usuario.id, ...)` (`router.py:107`)
   — el id sale del token (RN-USUARIOS-028).
3. `body.model_dump(exclude_unset=True)` y `repo.actualizar_perfil` (`service.py:305-306`).

## Flujo 6 — Listado y obtención (`GET /usuarios`, `GET /usuarios/{usuario_id}`)

1. `GET /usuarios` exige `get_current_user` (`router.py:33`); `GET /usuarios/{id}` exige
   `get_current_user_con_password_pendiente` (`router.py:42`) y, si el id no es el
   propio, aplica `exigir_password_al_dia` (`router.py:47-48`, RN-USUARIOS-035).
2. Ambos usan `user_client` (con RLS) y hacen `SELECT *` directo (`router.py:36`, `:49`);
   `NotFoundError` si no hay fila (`:50-51`).
3. El alcance de filas lo decide la policy `usuarios_sel`; la respuesta incluye
   `username` y `debe_cambiar_password`. Los usuarios desactivados siguen apareciendo en
   el listado con `activo: false`.

## Flujo 7 — Login con nombre de usuario (`POST /auth/login`) — **[NUEVO]**

1. Endpoint público (`auth/router.py:11-14`) → `login_para_endpoint` → `login` con
   service client (`auth/service.py:89-90`).
2. `normalizar_username` (`auth/service.py:44`). Los pasos 3 a 5 se hacen **siempre**,
   para cualquier username (RN-USUARIOS-045): lo que no resuelve a una cuenta sigue con
   placeholders y termina en el 401 genérico.
3. `obtener_usuario_por_username` (`auth/service.py:45-47`, `usuarios/repository.py:58-62`)
   con el username normalizado, o con el placeholder `login inexistente` si el formato es
   inválido.
4. `obtener_email_auth` con `client.auth.admin.get_user_by_id` (`auth/service.py:48-50`,
   `auth/repository.py:52-68`) con el id de la fila, o con el uuid nulo si no hubo fila.
5. `iniciar_sesion(email, password)` (`auth/service.py:53-55`) con el email real o, sin
   cuenta real, con `login-inexistente@<AUTH_EMAIL_DOMAIN>`: cliente anon nuevo con
   `persist_session=False` y httpx propio que se cierra al terminar
   (`auth/repository.py:71-104`). Contraseña incorrecta o sin cuenta real → 401
   genérico (`auth/service.py:56-57`).
   En los pasos 4 y 5: 429 de Supabase Auth (JSON o no) → 429 `Demasiados intentos. Probá
   de nuevo en unos minutos.` (RN-USUARIOS-043); Auth caído o 5xx → 503 `El servicio de
   autenticación no está disponible. Probá de nuevo en unos minutos.` (RN-USUARIOS-047).
6. Devuelve `access_token`, `refresh_token`, `expires_in`, `expires_at`, `token_type` y
   `user.id` (`auth/service.py:59-66`). El email no se devuelve.
7. El frontend instala la sesión con `supabase.auth.setSession` y pide
   `GET /usuarios/{id}` (`frontend/src/features/auth/AuthContext.tsx:121-134`). Si el
   perfil trae `debe_cambiar_password: true`, los guards lo mandan a `/cambiar-password`.

Todos los rechazos de credenciales usan el mismo 401 `Usuario o contraseña incorrectos`
(RN-USUARIOS-038); solo el límite de intentos de Auth (429) y Auth caído (503) se
distinguen, igual para todo username.
Un usuario desactivado con credenciales correctas obtiene sesión y recibe 401
`Usuario desactivado` en el paso 7, con lo que el frontend cierra la sesión.

## Flujo 8 — Cambio de la propia contraseña (`POST /auth/cambiar-password`) — **[NUEVO]**

1. `Depends(get_current_user_con_password_pendiente)` (`auth/router.py:21`): permitido con
   el flag en `true`; 401 si el usuario está desactivado.
2. `cambiar_password` (`auth/service.py:69-86`):
   1. `validar_password(password_nueva)` → 422 si tiene menos de 8 (`:72`).
   2. Nueva igual a la actual → 422 `La nueva contraseña debe ser distinta de la actual`
      (`:73-74`).
   3. Busca el email interno (`obtener_email_auth`) y verifica la actual con un sign-in
      contra Auth; si falla → 422 `La contraseña actual es incorrecta` sin cambiar nada
      (`:76-78`). Si Auth responde 429 → 429 (RN-USUARIOS-043); si Auth no responde o
      responde 5xx, en el lookup o en el sign-in → 503 (RN-USUARIOS-047). En ambos casos sin
      cambiar nada.
   4. `actualizar_password_auth` (`:83`) y después `debe_cambiar_password=False`
      (`:84-86`). Si falla el segundo paso, el flag queda en `true` y el usuario vuelve a la
      pantalla de cambio (falla cerrado, `:80-82`).
3. Responde `204`. El frontend refresca el perfil y sale de la pantalla de cambio.

## Flujo 9 — Blanqueo de contraseña (`PATCH /usuarios/{usuario_id}/password`) — **[NUEVO]**

1. `require_roles(*ROLES_GESTION_USUARIOS)` (`router.py:84`).
2. `blanquear_password` (`service.py:243-269`) llama a `_objetivo_gestionable`
   (`service.py:211-240`): rol del creador, nadie sobre sí mismo, existencia,
   `superadmin`/`sistema` protegidos, alcance de `gerencia`, droguería.
3. `validar_password` (`:254`). **[MODIFICADO]** Orden que falla cerrado
   (RN-USUARIOS-044): guarda el flag previo (`:258`), pone `debe_cambiar_password=True`
   (`:259-261`) y recién después `actualizar_password_auth` (`:263`). Si Auth falla,
   restaura el flag previo (`:264-267`) y relanza el error (`:268`); la contraseña no
   cambió.
4. Responde `UsuarioOut`. En su próximo request el usuario recibe 403 hasta que la cambie
   (Flujo 8). Las sesiones abiertas del usuario no se invalidan, pero quedan bloqueadas
   por el flag.

## Flujo 10 — Edición del nombre de usuario (`PATCH /usuarios/{usuario_id}/username`) — **[NUEVO]**

1. `require_roles(*ROLES_GESTION_USUARIOS)` (`router.py:95`).
2. `cambiar_username` (`service.py:272-296`): `_objetivo_gestionable`, formato
   (`:285`), unicidad ignorando al propio objetivo (`:286-288`); si el valor no cambia,
   devuelve el objetivo sin escribir (`:289-290`); si no, `UPDATE` de `username`
   (`:292`), con unique violation → 409 (`:293-296`).
3. No toca la cuenta de Auth (D-USUARIOS-012): el usuario entra con el nuevo username y
   la misma contraseña.
