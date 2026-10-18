# API pública — Usuarios

Firmas releídas y reverificadas contra el código real en esta sesión de actualización.

## `usuarios/models.py`

```python
Rol = Literal["superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras"]
# models.py:5
# Nota: la BD también permite "sistema" vía CHECK (docs/schema/rls_final.sql:38), pero
# este Literal de Python no lo incluye — ver decisiones.md D-USUARIOS-004.

class UsuarioCreate(BaseModel):
    email: str
    nombre: str
    apellido: str          # NUEVO — obligatorio, sin default
    rol: Rol
    drogueria_id: str | None = None
# models.py:8-13
# `password` ya NO forma parte de este modelo — el alta es por invitación de email
# (RN-USUARIOS-013), no por password directa.

class UsuarioRolUpdate(BaseModel):
    rol: Rol
# models.py:16-17

class UsuarioActivoUpdate(BaseModel):     # NUEVO
    activo: bool
# models.py:20-21

class UsuarioPerfilUpdate(BaseModel):     # NUEVO
    nombre: str | None = None
    apellido: str | None = None
# models.py:24-26

class UsuarioOut(BaseModel):
    id: str
    drogueria_id: str | None
    rol: str
    nombre: str
    apellido: str | None   # NUEVO
    es_sistema: bool
    activo: bool
# models.py:29-36
```

## `usuarios/repository.py`

Capa delgada de acceso a datos, sin lógica de negocio propia — salvo el mapeo de
excepciones de Supabase Auth a errores de dominio, agregado en esta sesión.

```python
def invitar_usuario_auth(
    client: Client, *, email: str, redirect_to: str, nombre: str, apellido: str, rol: str
) -> str: ...
# repository.py:9-33
# Reemplaza a crear_usuario_auth (que usaba client.auth.admin.create_user con password).
# Usa client.auth.admin.invite_user_by_email(email, {"redirect_to": redirect_to,
# "data": {"nombre", "apellido", "rol"}}). Atrapa AuthApiError (:20-32): status 429 →
# ConflictError, cualquier otro → ValidationError. Sin este catch, la excepción caía al
# 500 default de FastAPI, que corre fuera de CORSMiddleware — "Failed to fetch" en el
# navegador. Devuelve el id (UUID como str) del usuario creado en auth.users.

def crear_perfil_usuario(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:36-37
# INSERT sobre `usuarios`; devuelve la fila insertada. Sin cambios de firma.

def obtener_usuario(client: Client, *, usuario_id: str) -> dict[str, Any] | None: ...
# repository.py:40-42
# SELECT * ... WHERE id = usuario_id LIMIT 1; None si no existe. Sin cambios.

def actualizar_rol(client: Client, *, usuario_id: str, rol: str) -> dict[str, Any]: ...
# repository.py:45-46
# UPDATE usuarios SET rol = rol WHERE id = usuario_id. Sin cambios.

def actualizar_activo(client: Client, *, usuario_id: str, activo: bool) -> dict[str, Any]: ...
# repository.py:49-50
# NUEVO. UPDATE usuarios SET activo = activo WHERE id = usuario_id.

def actualizar_perfil(client: Client, *, usuario_id: str, campos: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:53-54
# NUEVO. UPDATE genérico con el dict de campos provisto (usado por PATCH /usuarios/me).

def eliminar_usuario_auth(client: Client, *, usuario_id: str) -> None: ...
# repository.py:57-66
# NUEVO. client.auth.admin.delete_user(usuario_id); la FK usuarios.id -> auth.users.id
# tiene ON DELETE CASCADE, así que borra también la fila de `usuarios`. Atrapa
# CUALQUIER AuthApiError (sin distinguir por status, a diferencia de
# invitar_usuario_auth) y lo traduce a ConflictError — pensado para el caso de FKs sin
# cascada (eventos, historial_cambios) que bloquean el borrado en cascada.
```

## `usuarios/service.py`

```python
def crear_usuario(
    client: Client, *, creador: UsuarioPerfil, body: UsuarioCreate
) -> dict[str, Any]: ...
# service.py:24-63
# Aplica RN-USUARIOS-001 a 007, RN-USUARIOS-013 (invitación por email) y RN-USUARIOS-029
# (gerencia solo crea roles inferiores a admin). Recibe
# `client` explícito para poder testearse con service_client inyectado, sin HTTP.

def cambiar_rol(
    client: Client, *, creador: UsuarioPerfil, usuario_id: str, nuevo_rol: str
) -> dict[str, Any]: ...
# service.py:66-94
# Aplica RN-USUARIOS-008 a 012, RN-USUARIOS-014/015 y RN-USUARIOS-029. `nuevo_rol` sigue siendo `str`,
# no `Rol` (RN-USUARIOS-012). Orden de validaciones cambió: auto-modificación
# (RN-USUARIOS-014) corre ANTES que la comprobación de existencia (RN-USUARIOS-011).

def cambiar_activo(
    client: Client, *, creador: UsuarioPerfil, usuario_id: str, activo: bool
) -> dict[str, Any]: ...
# service.py:97-118
# NUEVO. Aplica RN-USUARIOS-016 a 020 y RN-USUARIOS-029. Mismo esqueleto de validaciones
# que cambiar_rol (rol → auto-modificación → existencia → superadmin/sistema →
# alcance de gerencia → tenant).

def eliminar_usuario(
    client: Client, *, creador: UsuarioPerfil, usuario_id: str
) -> None: ...
# service.py:121-140
# NUEVO. Aplica RN-USUARIOS-022 a 026 y RN-USUARIOS-029 (más RN-USUARIOS-027 en repository.py). Mismo
# esqueleto de validaciones que cambiar_activo, termina en repo.eliminar_usuario_auth.

def actualizar_perfil_propio(
    client: Client, *, usuario_id: str, body: UsuarioPerfilUpdate
) -> dict[str, Any]: ...
# service.py:143-150
# NUEVO. Aplica RN-USUARIOS-028. Sin chequeo de rol; usa
# body.model_dump(exclude_unset=True) para no pisar campos no provistos con None.

def crear_usuario_para_endpoint(*, creador: UsuarioPerfil, body: UsuarioCreate) -> dict[str, Any]: ...
# service.py:153-154

def cambiar_rol_para_endpoint(*, creador: UsuarioPerfil, usuario_id: str, nuevo_rol: str) -> dict[str, Any]: ...
# service.py:157-158

def cambiar_activo_para_endpoint(*, creador: UsuarioPerfil, usuario_id: str, activo: bool) -> dict[str, Any]: ...
# service.py:161-162
# NUEVO wrapper.

def actualizar_perfil_propio_para_endpoint(*, usuario_id: str, body: UsuarioPerfilUpdate) -> dict[str, Any]: ...
# service.py:165-168
# NUEVO wrapper. Sin `creador` — no hay chequeo de rol que requiera el perfil completo
# del solicitante, solo su `id` (ya resuelto por el router desde el token).

def eliminar_usuario_para_endpoint(*, creador: UsuarioPerfil, usuario_id: str) -> None: ...
# service.py:171-172
# NUEVO wrapper.
```

Constantes de módulo (matriz de roles, odd/tasks/roles-permisos-matriz.md S7):

```python
ROLES_GESTION_USUARIOS = ("superadmin", "admin", "gerencia")
# service.py:12 — importada por router.py para los 4 endpoints de gestión.
ROLES_GESTIONABLES_POR_GERENCIA = ("gerencia", "lider_comercial", "comercial", "compras")
# service.py:16 — roles sobre los que gerencia puede operar y que puede asignar.

def _validar_objetivo_de_gerencia(creador: UsuarioPerfil, objetivo: dict[str, Any]) -> None: ...
# service.py:19-21 — RN-USUARIOS-029 sobre el usuario objetivo.
```

Los 5 wrappers `*_para_endpoint` resuelven `get_service_client()` (sin RLS) y delegan en
su función de negocio homónima — mismo patrón para las 3 funciones nuevas que para las 2
preexistentes.

## `usuarios/router.py`

```python
router = APIRouter()
# router.py:23
```

| Método | Path | Request | Response | Roles requeridos | Archivo |
|---|---|---|---|---|---|
| GET | `/usuarios` | — | `list[UsuarioOut]` | Ninguno (solo autenticado) | `router.py:26-31` |
| GET | `/usuarios/{usuario_id}` | — | `UsuarioOut` (404 si no existe/no visible por RLS) | Ninguno (solo autenticado) | `router.py:34-43` |
| POST | `/usuarios` | `UsuarioCreate` | `UsuarioOut` | `ROLES_GESTION_USUARIOS`: `superadmin`, `admin`, `gerencia` | `router.py:46-50` |
| PATCH | `/usuarios/{usuario_id}/rol` | `UsuarioRolUpdate` | `UsuarioOut` | `ROLES_GESTION_USUARIOS` | `router.py:53-59` |
| PATCH | `/usuarios/{usuario_id}/activo` **[NUEVO]** | `UsuarioActivoUpdate` | `UsuarioOut` | `ROLES_GESTION_USUARIOS` | `router.py:62-68` |
| PATCH | `/usuarios/me` **[NUEVO]** | `UsuarioPerfilUpdate` | `UsuarioOut` | Ninguno (propio perfil) | `router.py:71-76` |
| DELETE | `/usuarios/{usuario_id}` **[NUEVO]** | — | `204 No Content` | `ROLES_GESTION_USUARIOS` | `router.py:79-84` |

`gerencia` pasa el guard del router pero el service la acota a su droguería y a roles
inferiores a `admin` (RN-USUARIOS-029).

Excepciones de dominio levantadas por este módulo y su status HTTP (mapeo centralizado
en `core/exceptions.py`, ver [`../core/api.md`](../core/api.md)):

- `ForbiddenError` → 403: RN-USUARIOS-001, 002, 008, 009, 010, 014, 015, 016, 017, 019,
  020, 022, 023, 025, 026, 029.
- `NotFoundError` → 404: RN-USUARIOS-011, 018, 024, y el 404 directo de `router.py:42`.
- `ValidationError` → 422: RN-USUARIOS-005, 006, y la rama no-429 de RN-USUARIOS-013.
- `ConflictError` → 409: la rama 429 de RN-USUARIOS-013 (rate limit de invitación) y
  RN-USUARIOS-027 (eliminar con actividad asociada).
- `AuthenticationError` → 401: no la levanta este módulo directamente, pero es el
  resultado de `get_current_user` (`core/auth.py:47-48`) cuando `activo=False`
  (RN-USUARIOS-021), que gatea todos los endpoints salvo los explícitamente públicos.
