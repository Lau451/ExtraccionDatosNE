# Pendientes — Auditoría técnica de Usuarios

Clasificación P1 (bloqueante para desplegar) / P2 (deuda técnica relevante) / P3 (menor),
reverificada contra el código de la rama `feat/login-usuario-alta-admin`.

## P1 — Abiertos del login con nombre de usuario (odd/tasks/login-usuario-alta-admin.md)

1. **[RESUELTO 2026-10-19] La migración `0038_usuarios_username` está aplicada en el
   proyecto real.** Chequeo de solo lectura posterior: 5 filas, ningún `username` nulo,
   inválido o duplicado, ninguna con `debe_cambiar_password`. **Orden de despliegue: el
   backend de esta rama va después de `0038`.** El backend nuevo selecciona
   `debe_cambiar_password` en cada request autenticado (`services/shared/auth.py:47`) y
   busca por `username` en el login (`usuarios/repository.py:58-62`); sin la migración,
   esos `SELECT` fallan y ningún usuario puede entrar ni usar la API. Después de aplicarla,
   revisar los usernames generados por el backfill (RN-USUARIOS-041) y comunicárselos a los
   usuarios existentes: su email deja de servir para entrar.

2. **El rate limit de sign-in por IP de Supabase Auth ahora lo comparten todos los
   usuarios.** Como el login pasa por el backend (D-USUARIOS-011), todos los
   `sign_in_with_password` salen desde la IP del servidor (`auth/repository.py:42`), igual
   que la verificación de la contraseña actual en `POST /auth/cambiar-password`
   (`auth/service.py:56`). Un pico de logins (o un intento de fuerza bruta) puede bloquear
   el ingreso de todos. **[RESUELTO en parte, commits `2b4bf79` y `0c8052c`]**: el 429 de
   Supabase ya no se disfraza de `Usuario o contraseña incorrectos`; el login y el cambio
   de contraseña responden 429 `Demasiados intentos. Probá de nuevo en unos minutos.` y el
   frontend lo muestra (RN-USUARIOS-043). Sigue abierto el límite compartido en sí.
   [RECOMENDACIÓN]: revisar los límites del proyecto en el dashboard de Supabase y evaluar
   un rate limit propio por username/IP del cliente.

3. **`debe_cambiar_password` se aplica solo en el backend, no en RLS.** El bloqueo vive en
   `get_current_user` (`services/shared/auth.py:60-73`).
   - **Escritura — [RESUELTO, commit `804d9c5`, aplicada]**: la policy
     `usuarios_upd` dejaba que un admin limpiara su propio flag o editara usernames por
     PostgREST con su JWT. El trigger de `0039` lo rechaza (RN-USUARIOS-042).
   - **Lectura — [RESUELTO en código, commit `e099547`, PENDIENTE DE APLICAR]**: la
     migración `0041_usuarios_password_pendiente_sin_lectura` hace que los helpers de RLS
     ignoren al usuario con el flag en `true` y suma `password_al_dia()` a las lecturas que
     no pasan por ellos (RN-USUARIOS-048). Sin aplicar, la lectura por PostgREST sigue
     abierta.
   - **`UPDATE id` — [RESUELTO en código, commit `e099547`, PENDIENTE DE APLICAR]**: un
     superadmin podía borrar la fila B y hacer `UPDATE id = B` sobre otra fila sin
     referencias. La misma `0041` extiende el guard de `0039` a `id` (RN-USUARIOS-049).

   **Antes de aplicar `0041`, 3 chequeos en el SQL Editor del proyecto real** (la SQL no
   se ejecutó en ninguna base):
   1. **Helpers contra `rls_final.sql`**: los helpers no están en ninguna migración y
      `0041` los recrea con `CREATE OR REPLACE` suponiendo la definición de
      `docs/schema/rls_final.sql`. Consultar `pg_get_functiondef`, dueño (`proowner`) y
      permisos (`proacl`) de `get_drogueria_id`, `get_rol`, `es_superadmin` y
      `mismo_tenant` en `pg_proc` (consulta en el encabezado de `0041`) y confirmar que
      coinciden (misma firma, `STABLE`, `SECURITY DEFINER`, `search_path = public`).
   2. **Policies contra el `down`**: consultar en `pg_policies` `planes_sel`, `no_sel`,
      `ne_sel`, `np_sel` y `licitaciones_all_access` y confirmar que su `qual` actual es el
      que restaura `0041_usuarios_password_pendiente_sin_lectura.down.sql`; si difiere,
      `0041` pisaría una versión distinta y el `down` no volvería al estado real.
   3. **Caminos de lectura que quedan afuera**: buscar en `pg_policies` (y en vistas o
      RPCs) lecturas que no pasen por `get_rol()`/`get_drogueria_id()`/`es_superadmin()`/
      `mismo_tenant()` ni por `password_al_dia()` (p.ej. ramas `auth.uid()` propias o
      `USING (true)`), más allá de `usuarios_sel` (que queda a propósito). Conocidos sin
      relevar: `comparativas_results`/`licitaciones_results` (`0001`).

   Prueba sugerida después de aplicar: con el JWT de un usuario con el flag en `true`, un
   `GET` por PostgREST de cualquier tabla devuelve vacío salvo su fila de `usuarios`, y el
   login, el cambio de contraseña y el `GET /usuarios/{id}` propio siguen funcionando.

4. **Desactivar los sign-ups públicos en el dashboard de Supabase.** Con la anon key
   (pública en el frontend) cualquiera podría llamar a `signUp` contra Supabase Auth y
   crear una cuenta en `auth.users`. Sin fila en `usuarios` no pasa `get_current_user`
   (404), pero no tiene sentido permitirlo: el alta es solo por el admin. Es configuración
   del proyecto Supabase ("Allow new users to sign up" en Authentication), no código.

5. **Tests de integración actualizados pero no ejecutados.** `tests/usuarios/test_service.py`
   y `tests/usuarios/conftest.py` se adaptaron al alta con username + contraseña (todos
   `@pytest.mark.integration`, contra Supabase real), pero no se corrieron en esta rama;
   solo corrió la suite `-m "not integration"`. Correrlos después de aplicar `0038` en la
   base de test.

6. **`frontend/src/routeTree.gen.ts` se editó a mano.** Se agregó `/cambiar-password` y se
   quitaron `/reset-password` y `/accept-invite` sin el generador, porque
   `@tanstack/router-generator` 1.167.19 no coincide con el plugin 1.167.38. La próxima
   corrida del plugin lo regenera; revisar el diff en ese momento.

7. **La migración `0039_usuarios_protege_credenciales` está aplicada en el proyecto real
   (2026-10-19), pero su efecto no se probó.** La existencia del trigger se confirma con
   `select tgname from pg_trigger where tgname = 'trg_usuarios_protege_credenciales';`. **Orden: aplicar `0039` después de `0038`** (el trigger
   referencia `username` y `debe_cambiar_password`). Antes o al aplicarla, confirmar contra
   el proyecto real: (a) que los dueños de la base que corren migraciones y SQL manual son
   `postgres`/`supabase_admin` (si hay otro, el trigger lo bloquea); (b) que bajo PostgREST
   `current_user` es el rol del JWT (`authenticated` para un usuario, `service_role` para
   el backend), como asume el comentario de `0039_usuarios_protege_credenciales.sql:18-19`.
   Prueba sugerida: un `PATCH` por PostgREST con el JWT de un admin que intente poner
   `debe_cambiar_password=false` en su fila debe fallar con `42501`, y el blanqueo por el
   backend debe seguir funcionando.

8. **[RESUELTO 2026-10-19] La migración `0040_usuarios_protege_alta` está aplicada** en el
   proyecto real, después de `0039` (RN-USUARIOS-046, L10 del documento de feature). Su
   efecto no se probó: mismas confirmaciones pendientes que el punto 7; prueba sugerida:
   un `INSERT` por PostgREST con el JWT de un admin debe fallar con `42501` y el alta desde
   la pantalla de usuarios debe seguir funcionando.

9. **[RESUELTO, commit `34bcc44`] Errores de Supabase Auth mal mapeados en login y cambio
   de contraseña.** Un 502-504 o un 429 con body no JSON salían como 500, un 500 con JSON
   como credenciales inválidas (401/422), y un error del `get_user_by_id` que no era
   `AuthApiError` como 500 solo para usernames reales. Ahora Auth caído o 5xx da 503
   `El servicio de autenticación no está disponible. Probá de nuevo en unos minutos.`
   (RN-USUARIOS-047) y el 429 no JSON da 429 (RN-USUARIOS-043), igual para todo username.
   Un `AuthError` de un tipo no listado se sigue relanzando (500).

## P2 — Deuda técnica relevante

1. **Los 2 endpoints GET no exigen rol ni filtran `drogueria_id` en Python.** `GET /usuarios`
   y `GET /usuarios/{usuario_id}` (`router.py:31-52`) dependen de RLS para el alcance,
   mientras que el resto de la gestión exige `require_roles`. `PATCH /usuarios/me` es la
   excepción deliberada (RN-USUARIOS-028). [IMPLEMENTADO] el hecho.

2. **El aislamiento por tenant de los GET depende de una policy RLS sin test.** La policy
   `usuarios_sel` (`docs/schema/rls_final.sql:117`) no vive en una migración versionada y
   ningún test de `tests/usuarios/` la ejercita con un JWT real.
   [RECOMENDACIÓN]: test de integración con `crear_usuario_autenticado`.

3. **Definición de la tabla y RLS sin migración.** `apellido` (`0007`) y
   `username`/`debe_cambiar_password` (`0038`) sí tienen migración; la `CREATE TABLE
   usuarios` y sus policies siguen solo en `docs/schema/rls_final.sql`.

4. **Inconsistencia de capas: los GET bypasean `repository.py`/`service.py`.**
   `router.py:36`, `:49` arman sus propias queries. [IMPLEMENTADO].

5. **Gap de tests: ningún test del service dispara "rol no autorizado" para
   `cambiar_rol`/`cambiar_activo`/`eliminar_usuario`.** Solo `crear_usuario` lo tiene
   (`tests/usuarios/test_service.py:130`). Mitigado vía HTTP por
   `tests/usuarios/test_router.py:295` y `:634`, pero ese rechazo ocurre en
   `require_roles`, no en el service.

6. **El mapeo 429/otros de `crear_usuario_auth` (RN-USUARIOS-040) no tiene test
   automatizado.** [RECOMENDACIÓN]: mockear `client.auth.admin.create_user` para simular
   ambos status. Además, el 429 del alta sigue saliendo como **409** (`repository.py:33-37`),
   no como el 429 que ahora usan el login y el cambio de contraseña (RN-USUARIOS-043).
   Se dejó igual a propósito (fuera de S8); unificarlo cambiaría el contrato del alta.

7. **Sin test con JWT real del 401 de usuario desactivado ni del 403 por cambio
   pendiente.** `tests/shared/test_auth.py` y `tests/auth/test_router.py` sobreescriben
   dependencias; ninguno hace un request real con un JWT de Supabase.

8. **Blanqueo no atómico — [RESUELTO, commit `2b4bf79`]**. `blanquear_password` ahora
   marca `debe_cambiar_password=True` antes de cambiar la contraseña en Auth y restaura el
   flag previo si Auth falla (`service.py:255-269`, RN-USUARIOS-044). `cambiar_password`
   mantiene Auth primero y flag después: si falla el segundo paso, el usuario tiene que
   cambiarla de nuevo (falla cerrado, aceptado en S9).

9. **Diferencia de tiempos en el login — [RESUELTO, commits `ea8648f` y `34bcc44`]**. Todo
   username hace las mismas tres llamadas (lookup de username, `get_user_by_id` y
   sign-in), con placeholders cuando no resuelve a una cuenta (RN-USUARIOS-045). Mismo
   número de idas y vueltas no garantiza el mismo tiempo exacto (Supabase puede tardar
   distinto por cuenta).

10. **El email del cierre de PCP iría a la dirección interna opaca.** `obtener_email_usuario`
    (`services/pcp/negociacion/repository.py:47-62`) lee el email de `auth.users`, que para
    los usuarios creados por el admin es `<uuid>@<AUTH_EMAIL_DOMAIN>` (D-USUARIOS-012).
    Hoy el adaptador de mensajería solo loguea (`services/pcp/mensajeria/adapters.py:32-41`),
    pero un proveedor real de email enviaría a una dirección que nadie lee. Abierto: no se
    eligió corregirlo (L5).

## P3 — Menor

1. **`cambiar_rol(nuevo_rol: str)` sin tipar contra `Rol` (RN-USUARIOS-012).** Una violación
   del CHECK de la base fuera del router probablemente caería en 500. [SUPOSICIÓN, no
   ejercitado].

2. **Discrepancia entre `Rol` (Python) y el CHECK `rol` (BD) sin motivo documentado.** Ver
   D-USUARIOS-004.

3. **`eliminar_usuario_auth` mapea cualquier `AuthApiError` a `ConflictError`.** Ver
   D-USUARIOS-008.

4. **`apellido` nullable en la base pero obligatorio en `UsuarioCreate`.** Los usuarios
   anteriores a `0007` pueden seguir sin apellido.

5. **Compensación del alta puede fallar en silencio.** Si `descartar_usuario_auth` no logra
   borrar la cuenta, solo queda un `logger.exception` (`repository.py:46-48`) y la cuenta
   de Auth huérfana con su email opaco.

6. **Conviven emails reales e internos en `auth.users`.** Los usuarios previos a `0038`
   conservan su email real (D-USUARIOS-012); no hay migración que los pase al formato
   opaco. No afecta el login, pero el email real sigue existiendo en Auth.

7. **[RESUELTO, commit `9f9561c`] Frontend desalineado con el backend en dos detalles.**
   `LoginResponse.expires_at` era `number` y el backend devuelve `int | None` (ahora
   `number | null`, `frontend/src/lib/api/auth.ts`); y el error de formato de username del
   frontend decía "letras minúsculas" (ahora el texto exacto del backend, RN-USUARIOS-031).
