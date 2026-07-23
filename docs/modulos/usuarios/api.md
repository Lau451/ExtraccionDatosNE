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
# service.py:13-49
# Aplica RN-USUARIOS-001 a 007 y RN-USUARIOS-013 (invitación por email). Recibe
# `client` explícito para poder testearse con service_client inyectado, sin HTTP.

def cambiar_rol(
    client: Client, *, creador: UsuarioPerfil, usuario_id: str, nuevo_rol: str
) -> dict[str, Any]: ...
# service.py:52-76
# Aplica RN-USUARIOS-008 a 012 y RN-USUARIOS-014/015. `nuevo_rol` sigue siendo `str`,
# no `Rol` (RN-USUARIOS-012). Orden de validaciones cambió: auto-modificación
# (RN-USUARIOS-014) corre ANTES que la comprobación de existencia (RN-USUARIOS-011).

def cambiar_activo(
    client: Client, *, creador: UsuarioPerfil, usuario_id: str, activo: bool
) -> dict[str, Any]: ...
# service.py:79-98
# NUEVO. Aplica RN-USUARIOS-016 a 020. Mismo esqueleto de validaciones que cambiar_rol
# (rol → auto-modificación → existencia → superadmin/sistema → tenant).

def eliminar_usuario(
    client: Client, *, creador: UsuarioPerfil, usuario_id: str
) -> None: ...
# service.py:101-118
# NUEVO. Aplica RN-USUARIOS-022 a 026 (más RN-USUARIOS-027 en repository.py). Mismo
# esqueleto de validaciones que cambiar_activo, termina en repo.eliminar_usuario_auth.

def actualizar_perfil_propio(
    client: Client, *, usuario_id: str, body: UsuarioPerfilUpdate
) -> dict[str, Any]: ...
# service.py:121-128
# NUEVO. Aplica RN-USUARIOS-028. Sin chequeo de rol; usa
# body.model_dump(exclude_unset=True) para no pisar campos no provistos con None.

def crear_usuario_para_endpoint(*, creador: UsuarioPerfil, body: UsuarioCreate) -> dict[str, Any]: ...
# service.py:131-132

def cambiar_rol_para_endpoint(*, creador: UsuarioPerfil, usuario_id: str, nuevo_rol: str) -> dict[str, Any]: ...
# service.py:135-136

def cambiar_activo_para_endpoint(*, creador: UsuarioPerfil, usuario_id: str, activo: bool) -> dict[str, Any]: ...
# service.py:139-140
# NUEVO wrapper.

def actualizar_perfil_propio_para_endpoint(*, usuario_id: str, body: UsuarioPerfilUpdate) -> dict[str, Any]: ...
# service.py:143-146
# NUEVO wrapper. Sin `creador` — no hay chequeo de rol que requiera el perfil completo
# del solicitante, solo su `id` (ya resuelto por el router desde el token).

def eliminar_usuario_para_endpoint(*, creador: UsuarioPerfil, usuario_id: str) -> None: ...
# service.py:149-150
# NUEVO wrapper.
```

Los 5 wrappers `*_para_endpoint` resuelven `get_service_client()` (sin RLS) y delegan en
su función de negocio homónima — mismo patrón para las 3 funciones nuevas que para las 2
preexistentes.

## `usuarios/router.py`

```python
router = APIRouter()
# router.py:22
```

| Método | Path | Request | Response | Roles requeridos | Archivo |
|---|---|---|---|---|---|
| GET | `/usuarios` | — | `list[UsuarioOut]` | Ninguno (solo autenticado) | `router.py:25-30` |
| GET | `/usuarios/{usuario_id}` | — | `UsuarioOut` (404 si no existe/no visible por RLS) | Ninguno (solo autenticado) | `router.py:33-42` |
| POST | `/usuarios` | `UsuarioCreate` | `UsuarioOut` | `superadmin`, `admin` | `router.py:45-49` |
| PATCH | `/usuarios/{usuario_id}/rol` | `UsuarioRolUpdate` | `UsuarioOut` | `superadmin`, `admin` | `router.py:52-58` |
| PATCH | `/usuarios/{usuario_id}/activo` **[NUEVO]** | `UsuarioActivoUpdate` | `UsuarioOut` | `superadmin`, `admin` | `router.py:61-67` |
| PATCH | `/usuarios/me` **[NUEVO]** | `UsuarioPerfilUpdate` | `UsuarioOut` | Ninguno (propio perfil) | `router.py:70-75` |
| DELETE | `/usuarios/{usuario_id}` **[NUEVO]** | — | `204 No Content` | `superadmin`, `admin` | `router.py:78-83` |

Excepciones de dominio levantadas por este módulo y su status HTTP (mapeo centralizado
en `core/exceptions.py`, ver [`../core/api.md`](../core/api.md)):

- `ForbiddenError` → 403: RN-USUARIOS-001, 002, 008, 009, 010, 014, 015, 016, 017, 019,
  020, 022, 023, 025, 026.
- `NotFoundError` → 404: RN-USUARIOS-011, 018, 024, y el 404 directo de `router.py:41`.
- `ValidationError` → 422: RN-USUARIOS-005, 006, y la rama no-429 de RN-USUARIOS-013.
- `ConflictError` → 409: la rama 429 de RN-USUARIOS-013 (rate limit de invitación) y
  RN-USUARIOS-027 (eliminar con actividad asociada).
- `AuthenticationError` → 401: no la levanta este módulo directamente, pero es el
  resultado de `get_current_user` (`core/auth.py:47-48`) cuando `activo=False`
  (RN-USUARIOS-021), que gatea todos los endpoints salvo los explícitamente públicos.
