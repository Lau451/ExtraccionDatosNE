# Módulo Usuarios — `services/presupuestacion/usuarios/` (+ `services/presupuestacion/auth/`)

## Qué es

Usuarios gestiona el ciclo de vida completo de una cuenta de la aplicación — alta por un
admin con nombre de usuario y contraseña temporal, cambio de rol, activación/desactivación,
blanqueo de contraseña, edición del nombre de usuario, edición de perfil propio y
eliminación — sobre la tabla `usuarios` de Supabase. Es el módulo dueño de esa tabla en
el sentido de negocio (modelo, roles válidos, reglas de creación y de cambio de rol);
Core solo la lee de forma acotada para resolver el perfil del solicitante autenticado —
ver [`../core/base_de_datos.md`](../core/base_de_datos.md#usuarios).

**Login con nombre de usuario (odd/tasks/login-usuario-alta-admin.md)**: desde la
migración `0038` el usuario entra con `username` + contraseña, no con email. El login y
el cambio de la propia contraseña viven en el paquete hermano
`services/presupuestacion/auth/` (`POST /auth/login`, `POST /auth/cambiar-password`),
que se documenta acá porque opera sobre las mismas columnas (`username`,
`debe_cambiar_password`) y reusa las validaciones de `usuarios/service.py`
(`normalizar_username`, `validar_password`). Supabase Auth sigue siendo el motor de
identidad por debajo (tokens, sesiones, RLS sin cambios) — ver
[`decisiones.md`](./decisiones.md) D-USUARIOS-010.

Tamaño actual (`wc -l`): `usuarios/` 4 archivos, 593 líneas (`models.py` 50,
`repository.py` 95, `service.py` 333, `router.py` 115 — se cuentan por archivo, no se
incluye `__init__.py`), 9 endpoints; `auth/` 4 archivos, 160 líneas (`models.py` 26,
`repository.py` 41, `service.py` 70, `router.py` 23), 2 endpoints. Sin máquina de
estados propia.

## Qué NO hace

- **No gestiona usuarios de sistema desde el alta.** Todo usuario creado por este módulo
  tiene `es_sistema=False` hardcodeado (`service.py:121`); no hay ninguna vía en esta API
  para crear un usuario con `es_sistema=True` ni con `rol="sistema"` (la BD lo permite vía
  CHECK, pero el `Literal Rol` de Python no lo incluye — ver
  [`decisiones.md`](./decisiones.md) D-USUARIOS-004). Sí protege explícitamente a
  `rol="sistema"` de ser tocado por `cambiar_rol`, `cambiar_activo`, `eliminar_usuario`,
  `blanquear_password` y `cambiar_username` — ver D-USUARIOS-006.
- **No tiene `estados.md`.** `activo` y `debe_cambiar_password` son toggles binarios, no
  una máquina de estados con transiciones — se sigue omitiendo este documento del set,
  igual que en el módulo Core.
- **No envía emails ni invitaciones.** El alta crea la cuenta de Supabase Auth ya
  confirmada, con una dirección interna opaca (`<uuid hex>@<AUTH_EMAIL_DOMAIN>`,
  `service.py:103`) a la que nunca se manda correo y que nunca sale del backend
  (RN-USUARIOS-030/031). No hay autoservicio de "olvidé mi contraseña": el usuario le pide
  al admin que se la blanquee (RN-USUARIOS-035).
- **No expone el email de Auth.** `UsuarioOut` no tiene campo `email` (`models.py:41-50`)
  y `POST /auth/login` resuelve el email del lado del servidor
  (`auth/service.py:30`).

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `usuarios/__init__.py` | Vacío. |
| `usuarios/models.py` | `Rol` (Literal de 6 roles), `UsuarioCreate` (`username` + `password` temporal, sin `email`), `UsuarioRolUpdate`, `UsuarioActivoUpdate`, `UsuarioPasswordUpdate`, `UsuarioUsernameUpdate`, `UsuarioPerfilUpdate`, `UsuarioOut` (con `username` y `debe_cambiar_password`). |
| `usuarios/repository.py` | Acceso a datos más mapeo de errores de Supabase Auth a excepciones de dominio: alta en Auth sin email (`crear_usuario_auth`), compensación (`descartar_usuario_auth`), cambio de contraseña en Auth (`actualizar_password_auth`), búsqueda por username, insert/select/update/delete sobre `usuarios`. |
| `usuarios/service.py` | Reglas de negocio de las 7 operaciones (`crear_usuario`, `cambiar_rol`, `cambiar_activo`, `eliminar_usuario`, `blanquear_password`, `cambiar_username`, `actualizar_perfil_propio`), validaciones de formato (`normalizar_username`, `validar_password`) y sus wrappers HTTP (`*_para_endpoint`). |
| `usuarios/router.py` | 9 endpoints. Los 2 GET consultan la tabla directo con RLS; POST, los 4 PATCH de gestión (`/rol`, `/activo`, `/password`, `/username`) y el DELETE delegan en `service.py` con `require_roles`; `PATCH /me` delega en `service.py` sin chequeo de rol (autoservicio). |
| `auth/models.py` | `LoginIn`, `LoginOut` (campos de la sesión de Supabase), `CambiarPasswordIn`. |
| `auth/repository.py` | `obtener_email_auth` (email interno vía Admin API) e `iniciar_sesion` (sign-in con un cliente anon nuevo por llamada). |
| `auth/service.py` | `login` (username → email interno → sesión) y `cambiar_password` (cambio propio, limpia `debe_cambiar_password`). |
| `auth/router.py` | `POST /auth/login` (público) y `POST /auth/cambiar-password` (autenticado, permitido con cambio pendiente). |

## Quién lo consume

Los endpoints se montan en `services/presupuestacion/main.py` sin prefijo adicional
(`auth_router` en `main.py:62`, `app.include_router(auth_router, tags=["auth"])`). El
frontend usa esta API para el login (`frontend/src/lib/api/auth.ts`), el cambio de
contraseña (forzado y voluntario) y la gestión de usuarios (alta, roles, activación,
blanqueo, edición de username, "Mi cuenta", eliminación) — ver
[`casos_de_uso.md`](./casos_de_uso.md) "Consumidores reales". `auth/service.py` importa
de `usuarios/` (`auth/service.py:10-11`); fuera de eso, ningún `service.py` de otro
módulo de negocio importa de `usuarios/`.

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — dependencias hacia Core, asimetría de capas
  entre GET y escritura, diagrama del flujo de autorización.
- [`base_de_datos.md`](./base_de_datos.md) — tabla `usuarios`, migración `0038`, qué toca
  y qué no toca este módulo, policy RLS relevante.
- [`reglas.md`](./reglas.md) — reglas de negocio (RN-USUARIOS-NNN).
- [`flujo.md`](./flujo.md) — los flujos principales paso a paso.
- [`casos_de_uso.md`](./casos_de_uso.md) — los 11 endpoints y quién puede invocarlos.
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-USUARIOS-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica y pendientes operativos.

Para `UsuarioPerfil`, `get_current_user`, `get_current_user_con_password_pendiente`,
`require_roles` y el patrón `service_client`/`user_client` que este módulo consume
intensivamente, ver [`../core/`](../core/) — no se repite esa documentación acá.
