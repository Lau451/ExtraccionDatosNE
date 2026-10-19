# Pendientes — Auditoría técnica de Usuarios

Clasificación P1 (bloqueante para desplegar) / P2 (deuda técnica relevante) / P3 (menor),
reverificada contra el código de la rama `feat/login-usuario-alta-admin`.

## P1 — Abiertos del login con nombre de usuario (odd/tasks/login-usuario-alta-admin.md)

1. **La migración `0038_usuarios_username` no está aplicada en ninguna base.** El SQL se
   revisó pero no se ejecutó (no hubo Postgres descartable). **Orden de despliegue: aplicar
   `0038` antes de desplegar el backend de esta rama.** El backend nuevo selecciona
   `debe_cambiar_password` en cada request autenticado (`services/shared/auth.py:47`) y
   busca por `username` en el login (`usuarios/repository.py:58-62`); sin la migración,
   esos `SELECT` fallan y ningún usuario puede entrar ni usar la API. Después de aplicarla,
   revisar los usernames generados por el backfill (RN-USUARIOS-041) y comunicárselos a los
   usuarios existentes: su email deja de servir para entrar.

2. **El rate limit de sign-in por IP de Supabase Auth ahora lo comparten todos los
   usuarios.** Como el login pasa por el backend (D-USUARIOS-011), todos los
   `sign_in_with_password` salen desde la IP del servidor (`auth/repository.py:36`), igual
   que la verificación de la contraseña actual en `POST /auth/cambiar-password`
   (`auth/service.py:56`). Un pico de logins (o un intento de fuerza bruta) puede bloquear
   el ingreso de todos. Un 429 de Supabase hoy se ve como `Usuario o contraseña
   incorrectos` (`iniciar_sesion` devuelve `None` ante cualquier `AuthApiError`,
   `auth/repository.py:37-38`). [RECOMENDACIÓN]: revisar los límites del proyecto en el
   dashboard de Supabase y evaluar un rate limit propio por username/IP del cliente.

3. **`debe_cambiar_password` se aplica solo en el backend, no en RLS.** El bloqueo vive en
   `get_current_user` (`services/shared/auth.py:60-73`). Un usuario con contraseña temporal
   tiene un JWT válido de Supabase y las policies RLS no miran el flag, así que podría leer
   por PostgREST directo lo que RLS le permita. El frontend no hace llamadas directas a
   `supabase.from/rpc`, pero nada lo impide a nivel de base. [RECOMENDACIÓN]: si se quiere
   cerrar, sumar el flag a `get_rol()`/las policies (requiere migración propia).

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
   `tests/usuarios/test_router.py:295` y `:590`, pero ese rechazo ocurre en
   `require_roles`, no en el service.

6. **El mapeo 429/otros de `crear_usuario_auth` (RN-USUARIOS-040) no tiene test
   automatizado.** [RECOMENDACIÓN]: mockear `client.auth.admin.create_user` para simular
   ambos status.

7. **Sin test con JWT real del 401 de usuario desactivado ni del 403 por cambio
   pendiente.** `tests/shared/test_auth.py` y `tests/auth/test_router.py` sobreescriben
   dependencias; ninguno hace un request real con un JWT de Supabase.

8. **Blanqueo no atómico.** `blanquear_password` cambia la contraseña en Auth
   (`service.py:255`) antes de marcar `debe_cambiar_password=True` (`:256-258`); si el
   `UPDATE` fallara, el usuario quedaría con la contraseña nueva sin cambio forzado. Lo
   mismo en `cambiar_password` al revés (contraseña cambiada, flag sin limpiar →
   el usuario tendría que cambiarla de nuevo). Impacto bajo, sin compensación.

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
