# Casos de uso — Usuarios

Los 9 endpoints de `usuarios/router.py` y los 2 de `auth/router.py`, montados en
`services/presupuestacion/main.py` sin prefijo adicional (`auth_router` en `main.py:62`).

Salvo `POST /auth/login`, todos exigen un JWT válido. Mientras el solicitante tenga
`debe_cambiar_password=true`, todos responden `403 Debés cambiar tu contraseña antes de
continuar` excepto `GET /usuarios/{su propio id}` y `POST /auth/cambiar-password`
(RN-USUARIOS-035).

## `POST /auth/login` — **[NUEVO]**

- **Quién puede llamarlo**: cualquiera (público, `auth/router.py:11-14`).
- **Body**: `LoginIn { username, password }`.
- **Reglas**: RN-USUARIOS-031 y 038 — mismo 401 `Usuario o contraseña incorrectos` para
  username inexistente, formato inválido, cuenta sin Auth o contraseña incorrecta.
  RN-USUARIOS-043, 045 y 047 — 429 `Demasiados intentos. Probá de nuevo en unos minutos.`
  si Supabase Auth limita intentos y 503 `El servicio de autenticación no está disponible.
  Probá de nuevo en unos minutos.` si no responde o responde 5xx; iguales para todo
  username, que siempre hace la misma secuencia de llamadas.
- **Respuesta**: `LoginOut` con los campos de la sesión de Supabase (`access_token`,
  `refresh_token`, `expires_in`, `expires_at`, `token_type`, `user.id`). Nunca el email.

## `POST /auth/cambiar-password` — **[NUEVO]**

- **Quién puede llamarlo**: cualquier usuario autenticado activo, sobre su propia
  contraseña, **incluso con cambio pendiente** (`get_current_user_con_password_pendiente`,
  `auth/router.py:21`).
- **Body**: `CambiarPasswordIn { password_actual, password_nueva }`.
- **Reglas**: RN-USUARIOS-032 y 039 (422 con `La contraseña debe tener al menos 8
  caracteres`, `La nueva contraseña debe ser distinta de la actual` o `La contraseña
  actual es incorrecta`), y el 429/503 de RN-USUARIOS-043 y 047 si Supabase Auth limita
  intentos o no está disponible (también en el lookup del email), sin cambiar nada. En
  éxito, `204` y `debe_cambiar_password=false`.

## `GET /usuarios`

- **Quién puede llamarlo**: cualquier usuario autenticado sin cambio pendiente
  (`router.py:33`, `get_current_user`).
- **Reglas**: ninguna regla de negocio de este módulo; el alcance lo decide la policy
  `usuarios_sel`. La respuesta incluye `username` y `debe_cambiar_password` de cada fila.
- **Archivo**: `services/presupuestacion/usuarios/router.py:31-36`.

## `GET /usuarios/{usuario_id}`

- **Quién puede llamarlo**: cualquier usuario autenticado. Con cambio pendiente, solo
  para su propio id (`router.py:42-48`).
- **Reglas**: `NotFoundError` si el `id` no existe o RLS lo oculta (`router.py:50-51`).
  Es el endpoint con el que el frontend resuelve el perfil propio tras el login.
- **Archivo**: `services/presupuestacion/usuarios/router.py:39-52`.

## `POST /usuarios`

- **Quién puede llamarlo**: `superadmin`, `admin` o `gerencia` (`router.py:57`).
- **Body**: `UsuarioCreate { username, password, nombre, apellido, rol, drogueria_id? }`.
- **Reglas**: RN-USUARIOS-001 a 007, 029 y 030 a 034, 040 — alta con username y
  contraseña temporal, sin email ni invitación; username repetido → 409; contraseña de
  menos de 8 → 422; compensación si falla el perfil.
- **Archivo**: `services/presupuestacion/usuarios/router.py:55-59`.

## `PATCH /usuarios/{usuario_id}/rol`

- **Quién puede llamarlo**: `superadmin`, `admin` o `gerencia` (`router.py:66`).
- **Reglas**: RN-USUARIOS-008 a 012, 014, 015 y 029.
- **Archivo**: `services/presupuestacion/usuarios/router.py:62-68`.

## `PATCH /usuarios/{usuario_id}/activo`

- **Quién puede llamarlo**: `superadmin`, `admin` o `gerencia` (`router.py:75`).
- **Reglas**: RN-USUARIOS-016 a 021 y 029.
- **Body**: `UsuarioActivoUpdate { activo: bool }`.
- **Archivo**: `services/presupuestacion/usuarios/router.py:71-77`.

## `PATCH /usuarios/{usuario_id}/password` — **[NUEVO]**

- **Quién puede llamarlo**: `superadmin`, `admin` o `gerencia` (`router.py:84`).
- **Body**: `UsuarioPasswordUpdate { password }` (contraseña temporal nueva).
- **Reglas**: RN-USUARIOS-032 y 036 — misma autorización que activar/desactivar; deja
  `debe_cambiar_password=true`. Es la única vía de recuperación de contraseña.
- **Archivo**: `services/presupuestacion/usuarios/router.py:80-88`.

## `PATCH /usuarios/{usuario_id}/username` — **[NUEVO]**

- **Quién puede llamarlo**: `superadmin`, `admin` o `gerencia` (`router.py:95`).
- **Body**: `UsuarioUsernameUpdate { username }`.
- **Reglas**: RN-USUARIOS-031, 033 y 037 — misma autorización que el blanqueo; no toca la
  cuenta de Auth.
- **Archivo**: `services/presupuestacion/usuarios/router.py:91-99`.

## `PATCH /usuarios/me`

- **Quién puede llamarlo**: cualquier usuario autenticado sin cambio pendiente, sobre su
  propio perfil (`router.py:105`).
- **Reglas**: RN-USUARIOS-028.
- **Body**: `UsuarioPerfilUpdate { nombre?, apellido? }`.
- **Archivo**: `services/presupuestacion/usuarios/router.py:102-107`.

## `DELETE /usuarios/{usuario_id}`

- **Quién puede llamarlo**: `superadmin`, `admin` o `gerencia` (`router.py:113`).
- **Reglas**: RN-USUARIOS-022 a 027 y 029.
- **Respuesta**: `204 No Content`.
- **Archivo**: `services/presupuestacion/usuarios/router.py:110-115`.

## Consumidores reales

El frontend es el único consumidor:

- `frontend/src/lib/api/auth.ts` — `iniciarSesion` (`POST /auth/login`, con `fetch`
  directo, sin `Authorization`) y `cambiarPasswordPropia` (`POST /auth/cambiar-password`).
- `frontend/src/lib/api/usuarios.ts` — `crearUsuario`, `blanquearPasswordUsuario`,
  `cambiarUsernameUsuario`, `cambiarRolUsuario`, `cambiarActivoUsuario`,
  `eliminarUsuario`, `listarUsuarios`, `actualizarPerfilPropio`. Los usan
  `features/gestion-usuarios/` (`CrearUsuarioDialog`, `BlanquearPasswordDialog`,
  `EditarUsernameDialog`, columna "Usuario" en `GestionUsuarios.tsx:79`, `:163`) y
  `features/gestion-empresas/CrearPrimerAdminDialog.tsx` (primer admin de una droguería).
- `frontend/src/features/auth/AuthContext.tsx:75` — `GET /usuarios/{id}` para el perfil.

Dentro del backend, solo `auth/service.py` importa de `usuarios/`.
