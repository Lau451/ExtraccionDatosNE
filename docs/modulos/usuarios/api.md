# API pública — Usuarios

Firmas releídas y reverificadas contra el código real (rama
`feat/login-usuario-alta-admin`, odd/tasks/login-usuario-alta-admin.md).

## `usuarios/models.py`

```python
Rol = Literal["superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras"]
# models.py:7
# Nota: la BD también permite "sistema" vía CHECK (docs/schema/rls_final.sql:38), pero
# este Literal de Python no lo incluye — ver decisiones.md D-USUARIOS-004.

class UsuarioCreate(BaseModel):
    username: str
    password: str          # contraseña temporal: el usuario la cambia en el primer login
    nombre: str
    apellido: str
    rol: Rol
    drogueria_id: str | None = None
# models.py:10-17
# `email` ya NO forma parte de este modelo — el alta es con username + contraseña
# temporal (RN-USUARIOS-030), sin invitación por email.

class UsuarioRolUpdate(BaseModel):
    rol: Rol
# models.py:20-21

class UsuarioActivoUpdate(BaseModel):
    activo: bool
# models.py:24-25

class UsuarioPasswordUpdate(BaseModel):   # NUEVO (blanqueo, RN-USUARIOS-036)
    password: str
# models.py:28-29

class UsuarioUsernameUpdate(BaseModel):   # NUEVO (edición de username, RN-USUARIOS-037)
    username: str
# models.py:32-33

class UsuarioPerfilUpdate(BaseModel):
    nombre: str | None = None
    apellido: str | None = None
# models.py:36-38

class UsuarioOut(BaseModel):
    id: str
    drogueria_id: str | None
    rol: str
    nombre: str
    apellido: str | None
    es_sistema: bool
    activo: bool
    username: str                 # NUEVO
    debe_cambiar_password: bool   # NUEVO
# models.py:41-50
# Sin campo `email`: el email de Auth es interno y nunca sale del backend.
```

## `usuarios/repository.py`

Capa delgada de acceso a datos, sin lógica de negocio propia — salvo el mapeo de
excepciones de Supabase Auth a errores de dominio.

```python
def crear_usuario_auth(
    client: Client, *, email: str, password: str, nombre: str, apellido: str, rol: str
) -> str: ...
# repository.py:12-39
# Reemplaza a invitar_usuario_auth (que usaba invite_user_by_email, ELIMINADA).
# client.auth.admin.create_user({"email", "password", "email_confirm": True,
# "user_metadata": {"nombre", "apellido", "rol"}}) (:19-26): cuenta confirmada en el acto,
# sin email de invitación. `email` es la dirección interna opaca. Atrapa AuthApiError
# (:27-38): status 429 → ConflictError, cualquier otro → ValidationError
# ("No se pudo crear el usuario: ..."). Devuelve el id de auth.users.

def descartar_usuario_auth(client: Client, *, usuario_id: str) -> None: ...
# repository.py:42-48 — NUEVO. Compensación del alta: delete_user de la cuenta recién
# creada si el perfil no se pudo insertar. No relanza (loguea con logger.exception).

def actualizar_password_auth(client: Client, *, usuario_id: str, password: str) -> None: ...
# repository.py:51-55 — NUEVO. update_user_by_id(usuario_id, {"password": ...}); AuthApiError
# → ValidationError("No se pudo cambiar la contraseña: ..."). Usado por el blanqueo y por
# POST /auth/cambiar-password.

def obtener_usuario_por_username(client: Client, *, username: str) -> dict[str, Any] | None: ...
# repository.py:58-62 — NUEVO. SELECT * ... WHERE username = <ya normalizado> LIMIT 1.
# Compara por igualdad: la columna se guarda en minúsculas (CHECK de 0038).

def crear_perfil_usuario(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:65-66 — INSERT sobre `usuarios`; devuelve la fila insertada.

def obtener_usuario(client: Client, *, usuario_id: str) -> dict[str, Any] | None: ...
# repository.py:69-71 — SELECT * ... WHERE id = usuario_id LIMIT 1; None si no existe.

def actualizar_rol(client: Client, *, usuario_id: str, rol: str) -> dict[str, Any]: ...
# repository.py:74-75

def actualizar_activo(client: Client, *, usuario_id: str, activo: bool) -> dict[str, Any]: ...
# repository.py:78-79

def actualizar_perfil(client: Client, *, usuario_id: str, campos: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:82-83 — UPDATE genérico. Usado por PATCH /usuarios/me (nombre/apellido),
# por el blanqueo y el cambio propio (debe_cambiar_password) y por la edición de username.

def eliminar_usuario_auth(client: Client, *, usuario_id: str) -> None: ...
# repository.py:86-95 — delete_user; la FK usuarios.id -> auth.users.id tiene ON DELETE
# CASCADE. Atrapa CUALQUIER AuthApiError y lo traduce a ConflictError (RN-USUARIOS-027).
```

## `usuarios/service.py`

Constantes y helpers de módulo:

```python
ROLES_GESTION_USUARIOS = ("superadmin", "admin", "gerencia")
# service.py:20 — importada por router.py para los endpoints de gestión.
ROLES_GESTIONABLES_POR_GERENCIA = ("gerencia", "lider_comercial", "comercial", "compras")
# service.py:24
_PATRON_USERNAME = re.compile(r"[a-z0-9._-]{3,30}")   # service.py:28 (mismo que el CHECK de 0038)
PASSWORD_LARGO_MINIMO = 8                             # service.py:29

def normalizar_username(username: str) -> str | None: ...
# service.py:40-43 — strip().lower(); None si no cumple el patrón. Reusada por auth/service.py.

def validar_password(password: str) -> None: ...
# service.py:46-50 — ValidationError si len < 8. Reusada por auth/service.py.

def _username_valido(username: str) -> str: ...             # service.py:53-57
def _es_username_duplicado(exc: Exception) -> bool: ...     # service.py:60-61 (APIError code 23505)
def _validar_objetivo_de_gerencia(creador, objetivo) -> None: ...  # service.py:64-66
def _objetivo_gestionable(client, *, creador, usuario_id, mensaje_propio,
                          mensaje_protegido) -> dict[str, Any]: ...
# service.py:211-240 — autorización compartida por blanqueo y edición de username, la misma
# que activar/desactivar (RN-USUARIOS-036/037).
```

Funciones de negocio:

```python
def crear_usuario(client: Client, *, creador: UsuarioPerfil, body: UsuarioCreate) -> dict[str, Any]: ...
# service.py:76-131 — RN-USUARIOS-001 a 007, 029, 030 a 034.

def cambiar_rol(client: Client, *, creador: UsuarioPerfil, usuario_id: str, nuevo_rol: str) -> dict[str, Any]: ...
# service.py:134-162 — RN-USUARIOS-008 a 012, 014, 015, 029.

def cambiar_activo(client: Client, *, creador: UsuarioPerfil, usuario_id: str, activo: bool) -> dict[str, Any]: ...
# service.py:165-186 — RN-USUARIOS-016 a 020, 029.

def eliminar_usuario(client: Client, *, creador: UsuarioPerfil, usuario_id: str) -> None: ...
# service.py:189-208 — RN-USUARIOS-022 a 027, 029.

def blanquear_password(client: Client, *, creador: UsuarioPerfil, usuario_id: str, password: str) -> dict[str, Any]: ...
# service.py:243-269 — NUEVO. RN-USUARIOS-032, 035, 036, 044 (flag antes que Auth).

def cambiar_username(client: Client, *, creador: UsuarioPerfil, usuario_id: str, username: str) -> dict[str, Any]: ...
# service.py:272-296 — NUEVO. RN-USUARIOS-031, 033, 037.

def actualizar_perfil_propio(client: Client, *, usuario_id: str, body: UsuarioPerfilUpdate) -> dict[str, Any]: ...
# service.py:299-306 — RN-USUARIOS-028.
```

Los 7 wrappers `*_para_endpoint` (`service.py:309-344`) resuelven `get_service_client()`
(sin RLS) y delegan en su función de negocio homónima.

## `usuarios/router.py`

```python
router = APIRouter()
# router.py:28
```

| Método | Path | Request | Response | Dependencia de auth | Archivo |
|---|---|---|---|---|---|
| GET | `/usuarios` | — | `list[UsuarioOut]` | `get_current_user` (bloqueado con cambio pendiente) | `router.py:31-36` |
| GET | `/usuarios/{usuario_id}` | — | `UsuarioOut` (404 si no existe/no visible por RLS) | `get_current_user_con_password_pendiente`; si `usuario_id != usuario.id` aplica además `exigir_password_al_dia` | `router.py:39-52` |
| POST | `/usuarios` | `UsuarioCreate` | `UsuarioOut` | `require_roles(*ROLES_GESTION_USUARIOS)` | `router.py:55-59` |
| PATCH | `/usuarios/{usuario_id}/rol` | `UsuarioRolUpdate` | `UsuarioOut` | `require_roles(...)` | `router.py:62-68` |
| PATCH | `/usuarios/{usuario_id}/activo` | `UsuarioActivoUpdate` | `UsuarioOut` | `require_roles(...)` | `router.py:71-77` |
| PATCH | `/usuarios/{usuario_id}/password` **[NUEVO]** | `UsuarioPasswordUpdate` | `UsuarioOut` | `require_roles(...)` | `router.py:80-88` |
| PATCH | `/usuarios/{usuario_id}/username` **[NUEVO]** | `UsuarioUsernameUpdate` | `UsuarioOut` | `require_roles(...)` | `router.py:91-99` |
| PATCH | `/usuarios/me` | `UsuarioPerfilUpdate` | `UsuarioOut` | `get_current_user` (bloqueado con cambio pendiente) | `router.py:102-107` |
| DELETE | `/usuarios/{usuario_id}` | — | `204 No Content` | `require_roles(...)` | `router.py:110-115` |

`require_roles` depende de `get_current_user`, así que todos los endpoints de gestión
también quedan bloqueados (403) mientras el solicitante tenga un cambio de contraseña
pendiente (RN-USUARIOS-035). `gerencia` pasa el guard del router pero el service la acota
a su droguería y a roles inferiores a `admin` (RN-USUARIOS-029).

## `auth/models.py`

```python
class LoginIn(BaseModel):
    username: str
    password: str
# auth/models.py:4-6

class LoginUsuario(BaseModel):
    id: str
# auth/models.py:9-10

class LoginOut(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    expires_at: int | None
    token_type: str
    user: LoginUsuario
# auth/models.py:13-21 — campos de la sesión de Supabase que el frontend pasa a
# supabase.auth.setSession.

class CambiarPasswordIn(BaseModel):
    password_actual: str
    password_nueva: str
# auth/models.py:24-26
```

## `auth/repository.py`

```python
MENSAJE_RATE_LIMIT = "Demasiados intentos. Probá de nuevo en unos minutos."   # auth/repository.py:23
MENSAJE_AUTH_NO_DISPONIBLE = (
    "El servicio de autenticación no está disponible. Probá de nuevo en unos minutos."
)   # auth/repository.py:25-27 — NUEVO (RN-USUARIOS-047)

def _status_http(exc: AuthError) -> int | None: ...
# auth/repository.py:30-38 — exc.status de AuthApiError/CustomAuthError; para
# AuthUnknownError (body no JSON) lo lee del httpx.HTTPStatusError en __cause__/__context__.

def _error_de_servicio(exc: AuthError) -> DomainError | None: ...
# auth/repository.py:41-49 — 429 → RateLimitError (RN-USUARIOS-043); AuthRetryableError,
# AuthUnknownError o status >= 500 → ServicioExternoNoDisponibleError (RN-USUARIOS-047);
# None = error de credenciales/datos.

def obtener_email_auth(client: Client, *, usuario_id: str) -> str | None: ...
# auth/repository.py:52-68 — client.auth.admin.get_user_by_id. 429/5xx/body no
# parseable → el error de _error_de_servicio; httpx.RequestError (red) → 503; otro
# AuthApiError → None; cualquier otro AuthError se relanza. None también si no hay usuario.
# El email nunca sale del backend.

def iniciar_sesion(*, email: str, password: str) -> Session | None: ...
# auth/repository.py:71-104 — crea un cliente anon NUEVO por llamada (create_client con
# supabase_anon_key, persist_session=False, auto_refresh_token=False y un httpx propio que
# se cierra en el finally, :81-103) y llama a sign_in_with_password. Errores de servicio
# → el error de _error_de_servicio (:91-94); httpx.RequestError → 503 (:100-101);
# AuthApiError o AuthInvalidCredentialsError (password vacía, antes del HTTP) → None
# (:97-98); cualquier otro AuthError se relanza.
# No usa el service client ni los cacheados por token: sign_in_with_password guarda la
# sesión en el propio cliente (docstring :72-77).
```

## `auth/service.py`

```python
MENSAJE_LOGIN_INVALIDO = "Usuario o contraseña incorrectos"   # auth/service.py:16
_LOCAL_EMAIL_INEXISTENTE = "login-inexistente"                  # :21
_USERNAME_INEXISTENTE = "login inexistente"                     # :26 — placeholder (RN-USUARIOS-045)
_ID_INEXISTENTE = "00000000-0000-0000-0000-000000000000"        # :27 — placeholder (RN-USUARIOS-045)

def email_login_inexistente() -> str: ...                       # :30-31

def login(client: Client, *, body: LoginIn) -> dict[str, Any]: ...
# auth/service.py:34-66 — RN-USUARIOS-038 y RN-USUARIOS-045 (siempre lookup de username,
# lookup en Auth y sign-in, con placeholders si el username no resuelve a una cuenta).

def cambiar_password(client: Client, *, usuario: UsuarioPerfil, body: CambiarPasswordIn) -> None: ...
# auth/service.py:69-86 — RN-USUARIOS-039.

def login_para_endpoint(*, body: LoginIn) -> dict[str, Any]: ...                  # :89-90
def cambiar_password_para_endpoint(*, usuario: UsuarioPerfil, body: CambiarPasswordIn) -> None: ...  # :93-94
# Ambos con get_service_client().
```

## `auth/router.py`

| Método | Path | Request | Response | Dependencia de auth | Archivo |
|---|---|---|---|---|---|
| POST | `/auth/login` | `LoginIn` | `LoginOut` (401 `Usuario o contraseña incorrectos`; 429 `Demasiados intentos. Probá de nuevo en unos minutos.`; 503 `El servicio de autenticación no está disponible. Probá de nuevo en unos minutos.`; los tres iguales para todo username) | Ninguna (público) | `auth/router.py:11-14` |
| POST | `/auth/cambiar-password` | `CambiarPasswordIn` | `204 No Content` (422 de RN-USUARIOS-039; 429 y 503 con los mismos mensajes del login, también si falla el lookup del email) | `get_current_user_con_password_pendiente` (permitido con cambio pendiente) | `auth/router.py:17-23` |

## Errores de dominio y status HTTP

Mapeo centralizado en `services/shared/exceptions.py:54-64` (`STATUS_MAP`), ver
[`../core/api.md`](../core/api.md):

- `ForbiddenError` → 403: RN-USUARIOS-001, 002, 008, 009, 010, 014, 015, 016, 017, 019,
  020, 022, 023, 025, 026, 029, 036, 037, y el 403 por cambio de contraseña pendiente
  (RN-USUARIOS-035, `Debés cambiar tu contraseña antes de continuar`).
- `NotFoundError` → 404: RN-USUARIOS-011, 018, 024, el objetivo inexistente de 036/037, y
  el 404 directo de `router.py:50-51`.
- `ValidationError` → 422: RN-USUARIOS-005, 006, 031 (formato de username), 032
  (contraseña corta), la rama no-429 de RN-USUARIOS-040, y los errores de
  `POST /auth/cambiar-password` (RN-USUARIOS-039).
- `ConflictError` → 409: RN-USUARIOS-033 (username repetido), la rama 429 de
  RN-USUARIOS-040 y RN-USUARIOS-027 (eliminar con actividad asociada).
- `AuthenticationError` → 401: `POST /auth/login` con credenciales inválidas
  (RN-USUARIOS-038), y `get_current_user`/`get_current_user_con_password_pendiente`
  cuando `activo=False` (RN-USUARIOS-021).
- `RateLimitError` → 429 (**[NUEVO]**, `exceptions.py:38-39`, `:60`): Supabase Auth
  respondió 429 (con o sin body JSON) en el lookup o el sign-in de `POST /auth/login` o
  de `POST /auth/cambiar-password` (RN-USUARIOS-043). Body
  `{"detail": "Demasiados intentos. Probá de nuevo en unos minutos."}`. El 429 de
  `create_user` en el alta sigue siendo 409 (RN-USUARIOS-040).
- `ServicioExternoNoDisponibleError` → 503 (**[NUEVO]**, `exceptions.py:42-43`, `:61`):
  Supabase Auth no respondió o respondió 5xx (502-504, 500 con o sin JSON, red caída) en
  el lookup o el sign-in de `POST /auth/login` o de `POST /auth/cambiar-password`
  (RN-USUARIOS-047). Body
  `{"detail": "El servicio de autenticación no está disponible. Probá de nuevo en unos minutos."}`.
- Un error de PostgREST por el trigger de `0039`/`0040`/`0041` (SQLSTATE `42501`,
  RN-USUARIOS-042, 046, 049) solo
  lo ve quien escribe `usuarios` con su JWT por fuera del backend; ningún endpoint del
  módulo lo dispara, porque escriben con el service client.
