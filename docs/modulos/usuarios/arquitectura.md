# Arquitectura — Usuarios

## Dependencias hacia Core

Usuarios no importa de ningún otro módulo de negocio de `presupuestacion/`; depende
exclusivamente de Core. [IMPLEMENTADO] — confirmado por inspección de imports de los 4
archivos del módulo, releídos en esta sesión.

| Import | Origen | Uso |
|---|---|---|
| `UsuarioPerfil` | `core/auth.py` | Tipo del `creador`/`usuario` autenticado en `service.py:5` y `router.py:4`. |
| `get_current_user` | `core/auth.py` | Dependencia de los 2 endpoints GET y de `PATCH /usuarios/me`, sin exigir rol (`router.py:4`, `:27`, `:36`, `:73`). |
| `require_roles` | `core/auth.py` | Dependencia de POST, `PATCH /rol`, `PATCH /activo` y `DELETE`, exige `superadmin`/`admin` (`router.py:4`, `:47`, `:56`, `:65`, `:81`). |
| `get_settings` | `core/config.py` | Resuelve `frontend_url` para armar el `redirect_to` de la invitación de email (`service.py:6`, `:30`). **Nuevo en esta sesión.** |
| `get_service_client` | `core/database.py` | Cliente sin RLS, resuelto internamente por los 5 wrappers `*_para_endpoint` (`service.py:7`, `:131-132`, `:135-136`, `:139-140`, `:143-146`, `:149-150`). |
| `get_user_client` | `core/database.py` | Cliente con RLS, inyectado directo en los 2 endpoints GET (`router.py:5`, `:28`, `:37`). |
| `ForbiddenError`, `NotFoundError`, `ValidationError` | `core/exceptions.py` | Errores de dominio levantados por `service.py` (la mayoría de las RN-USUARIOS-NNN) y por `router.py` (`NotFoundError` en `obtener_usuario_endpoint`, `router.py:6`, `:41`). |
| `ConflictError` | `core/exceptions.py` | **Nuevo en esta sesión.** Levantado por `repository.py` al mapear `AuthApiError` de Supabase Auth (RN-USUARIOS-013 rama 429, RN-USUARIOS-027). |

`AuthenticationError` no la importa este módulo directamente, pero su efecto lo alcanza
igual: `get_current_user` (`core/auth.py:47-48`) la levanta cuando `activo=False`
(RN-USUARIOS-021), gateando todos los endpoints de `usuarios/` que dependen de esa
función. Ver [`../core/`](../core/) para la documentación de estas piezas — no se repite
acá.

## Asimetría de capas: GET directo a BD vs escritura vía `service.py`

Este es el rasgo arquitectónico más notable del módulo, sin cambios de fondo respecto de
la revisión anterior — pero ahora aplica a 5 endpoints de escritura en vez de 2:

- **`GET /usuarios` y `GET /usuarios/{usuario_id}`** (`router.py:25-30`, `:33-42`)
  consultan la tabla `usuarios` **directamente** con `user_client` (`Depends(get_user_client)`,
  `router.py:28`, `:37`), sin pasar por `repository.py` ni por `service.py`. La
  autorización depende únicamente de `Depends(get_current_user)` (sin `require_roles`) y
  del filtrado que aplique RLS del lado de Postgres.
- **`POST /usuarios`, `PATCH /usuarios/{usuario_id}/rol`, `PATCH /usuarios/{usuario_id}/activo`
  y `DELETE /usuarios/{usuario_id}`** (`router.py:45-49`, `:52-58`, `:61-67`, `:78-83`)
  exigen `require_roles("superadmin", "admin")` y delegan en su wrapper
  `*_para_endpoint` correspondiente, que resuelve `get_service_client()` (sin RLS) y
  aplica las reglas de negocio de `service.py` antes de tocar `repository.py`.
- **`PATCH /usuarios/me`** (`router.py:70-75`) es un tercer caso, nuevo en esta sesión:
  exige solo `Depends(get_current_user)` (como los GET) pero delega en `service.py` y
  usa `get_service_client()` (como los otros de escritura) — su autorización no es ni
  RLS ni una whitelist de roles, sino estructural: el `usuario_id` que recibe
  `actualizar_perfil_propio` sale del token, no de un parámetro de URL, así que no hay
  forma de que un usuario edite el perfil de otro por esta vía.

En otras palabras: para escribir sobre otros usuarios, el módulo no confía en RLS —
implementa sus propias reglas de autorización en Python contra un cliente que bypasea
RLS. Para leer, y para que un usuario edite su propio perfil, el módulo no aplica ninguna
regla de rol — se apoya en RLS (para leer) o en que el `id` del propio token nunca puede
apuntar a otro usuario (para `PATCH /me`). Ver [`decisiones.md`](./decisiones.md)
D-USUARIOS-001 y D-USUARIOS-002, y el riesgo asociado en [`pendientes.md`](./pendientes.md).

## Diagrama textual del flujo de autorización

```
                              Request HTTP a /usuarios*
                                        │
        ┌───────────────────┬───────────────────┬───────────────────┐
        │                    │                    │                    │
  GET /usuarios(/{id})  PATCH /usuarios/me   POST /usuarios        DELETE /usuarios/{id}
                                              PATCH /rol, /activo
        │                    │                    │                    │
  Depends(get_current_user)  Depends(get_current_user)  Depends(require_roles(
  (router.py:27, :36)        (router.py:73)               "superadmin", "admin"))
  → JWT válido + perfil      → JWT válido + perfil        (router.py:47, :56, :65, :81)
    en `usuarios`, SIN rol     en `usuarios`, SIN rol    → exige además que
    específico                  específico                 usuario.rol esté en
        │                    │                              esa whitelist
  Depends(get_user_client)   usuario.id (del token,                │
  (router.py:28, :37)        no de la URL) se pasa      *_para_endpoint resuelve
  → cliente CON RLS          como usuario_id             get_service_client()
        │                    (router.py:75)              (service.py:131-150)
  SELECT directo sobre             │                              │
  `usuarios` (router.py:30, :39)  get_service_client()   → cliente SIN RLS
        │                    (service.py:143-146)                │
  Aislamiento por tenant            │                    crear_usuario / cambiar_rol /
  (si existe) depende de la  actualizar_perfil_propio    cambiar_activo / eliminar_usuario
  policy `usuarios_sel` de   (service.py:121-128)         (service.py:13-118)
  Postgres — no verificable  → sin reglas de rol,         → reglas RN-USUARIOS-NNN
  solo con este módulo         solo campos provistos        evaluadas en Python
  (ver pendientes.md)                                              │
                                                          repository.py (INSERT/UPDATE/DELETE)
```

Notar que las tres ramas usan mecanismos de autorización distintos y no comparables
directamente: la de lectura es declarativa (policy de RLS en la base), la de escritura
sobre otros usuarios es imperativa (if/raise en `service.py`), y la de autoservicio de
perfil propio no es ninguna de las dos — es una garantía estructural (el `id` sale del
token) sin ningún `if` de autorización explícito.
