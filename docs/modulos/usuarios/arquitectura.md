# Arquitectura — Usuarios

## Dependencias hacia Core

`usuarios/` no importa de ningún otro módulo de negocio de `presupuestacion/`; depende
exclusivamente de Core (y de `services/shared/auth.py`, que Core reexporta). El paquete
hermano `auth/` depende de Core y de `usuarios/` (`auth/service.py:10-11`). [IMPLEMENTADO]
— confirmado por inspección de imports en la rama `feat/login-usuario-alta-admin`.

| Import | Origen | Uso |
|---|---|---|
| `UsuarioPerfil` | `core/auth.py` (shim de `services/shared/auth.py`) | Tipo del `creador`/`usuario` autenticado en `service.py:8`, `router.py:4`, `auth/service.py:7`, `auth/router.py:5`. |
| `get_current_user` | `core/auth.py` | Dependencia de `GET /usuarios` y `PATCH /usuarios/me`, sin exigir rol (`router.py:33`, `:105`). Rechaza con 403 si hay cambio de contraseña pendiente. |
| `get_current_user_con_password_pendiente`, `exigir_password_al_dia` | `services/shared/auth.py` | Importadas directo (no están en el shim de Core). `GET /usuarios/{usuario_id}` usa la permisiva y aplica `exigir_password_al_dia` si el id no es el propio (`router.py:26`, `:42`, `:47-48`); `POST /auth/cambiar-password` usa la permisiva (`auth/router.py:6`, `:21`). |
| `require_roles` | `core/auth.py` | Dependencia de POST, `PATCH /rol`, `/activo`, `/password`, `/username` y `DELETE`, exige `ROLES_GESTION_USUARIOS` = `superadmin`/`admin`/`gerencia` (`router.py:57`, `:66`, `:75`, `:84`, `:95`, `:113`; constante en `service.py:20`). |
| `get_settings` | `core/config.py` (shim de `services/shared/config.py`) | Resuelve `auth_email_domain` para el email interno opaco del alta (`service.py:9`, `:103`). Ya no se usa `frontend_url` en este módulo. `auth/repository.py:30` lo usa para `supabase_url`/`supabase_anon_key`. |
| `get_service_client` | `core/database.py` | Cliente sin RLS, resuelto por los 7 wrappers `*_para_endpoint` (`service.py:309-344`) y por los 2 de `auth/service.py:68-73`. |
| `get_user_client` | `core/database.py` | Cliente con RLS, inyectado directo en los 2 endpoints GET (`router.py:34`, `:43`). |
| `build_resilient_httpx_client` | `services/shared/http_client.py` | httpx propio por login, cerrado al terminar (`auth/repository.py:33`, `:48`). |
| `ForbiddenError`, `NotFoundError`, `ValidationError`, `ConflictError`, `AuthenticationError` | `core/exceptions.py` | Errores de dominio de `service.py`, `repository.py`, `router.py` y `auth/service.py` (`AuthenticationError` del login, `auth/service.py:9`). |

## Asimetría de capas: GET directo a BD vs escritura vía `service.py`

- **`GET /usuarios` y `GET /usuarios/{usuario_id}`** (`router.py:31-36`, `:39-52`)
  consultan la tabla `usuarios` **directamente** con `user_client`, sin pasar por
  `repository.py` ni por `service.py`. El alcance de filas lo decide RLS.
- **`POST /usuarios` y los `PATCH` de gestión (`/rol`, `/activo`, `/password`,
  `/username`) y `DELETE`** (`router.py:55-99`, `:110-115`) exigen
  `require_roles(*ROLES_GESTION_USUARIOS)` y delegan en su wrapper `*_para_endpoint`,
  que resuelve `get_service_client()` (sin RLS) y aplica las reglas de `service.py`.
- **`PATCH /usuarios/me`** (`router.py:102-107`): `get_current_user` + service client; su
  autorización es estructural (el `usuario_id` sale del token).
- **`POST /auth/login`** (`auth/router.py:11-14`): público. Usa el service client para
  resolver username → id → email interno, y un cliente anon nuevo para el sign-in
  (`auth/repository.py:24-49`) — nunca el service client ni los cacheados por token,
  porque `sign_in_with_password` guarda la sesión en el propio cliente.
- **`POST /auth/cambiar-password`** (`auth/router.py:17-23`): dependencia permisiva (sin el
  bloqueo por cambio pendiente) + service client; el `usuario_id` sale del token.

Para escribir sobre otros usuarios el módulo no confía en RLS: implementa sus reglas en
Python contra un cliente que bypasea RLS. Ver D-USUARIOS-001/002.

## Diagrama textual del flujo de autorización

```
                                   Request HTTP
                                         │
   ┌──────────────┬──────────────────────┼─────────────────────┬──────────────────────┐
   │              │                      │                     │                      │
POST /auth/login  GET /usuarios(/{id})   PATCH /usuarios/me    POST /auth/            POST /usuarios, DELETE
(público)         │                      │                     cambiar-password       PATCH /rol /activo
   │              │                      │                     │                      /password /username
   │        GET /usuarios:         get_current_user      get_current_user_con_        require_roles(...)
   │        get_current_user       (403 si flag)         password_pendiente           → get_current_user
   │        GET /{id}: permisiva   usuario.id del        (sin 403 por flag;             (403 si flag)
   │        + exigir_password_     token                 401 si inactivo)             → whitelist de rol
   │        al_dia si id ajeno           │                     │                      │
   │              │                service client        service client               *_para_endpoint
   │        user_client (RLS)      actualizar_perfil_    cambiar_password             → service client
   │        SELECT directo         propio                (auth/service.py:48-65)      → reglas RN-USUARIOS
   │        (usuarios_sel)                                                            → repository.py
   │
service client: username → fila → email interno (Admin API)
cliente anon nuevo: sign_in_with_password → sesión (auth/service.py:18-45)
```

El chequeo de `debe_cambiar_password` vive en `services/shared/auth.py:60-83`, no en
este módulo: `usuarios/` y `auth/` solo eligen qué dependencia usa cada endpoint.
