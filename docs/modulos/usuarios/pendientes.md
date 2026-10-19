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
   - **Escritura — [RESUELTO, commit `804d9c5`, pendiente de aplicar]**: la policy
     `usuarios_upd` dejaba que un admin limpiara su propio flag o editara usernames por
     PostgREST con su JWT. El trigger de `0039` lo rechaza (RN-USUARIOS-042).
   - **Lectura — abierto (residual, fuera de alcance de S7)**: un usuario con contraseña
     temporal tiene un JWT válido de Supabase y las policies RLS no miran el flag, así que
     puede leer por PostgREST directo lo que RLS le permita. El frontend no hace llamadas
     directas a `supabase.from/rpc`, pero nada lo impide a nivel de base.
     [RECOMENDACIÓN]: si se quiere cerrar, sumar el flag a `get_rol()`/las policies
     (requiere migración propia).

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

9. **Diferencia de tiempos en el login (enumeración por timing).** El body y el status son
   idénticos para todos los fallos (`tests/auth/test_router.py:197`), pero un username con
   formato inválido o inexistente responde sin llamar a Supabase Auth
   (`auth/service.py:22-24`, `:26-28`), mientras que uno existente hace el sign-in
   (`:34`). La diferencia de tiempo puede revelar qué usernames existen. Abierto: no se
   eligió corregirlo (L5).

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
