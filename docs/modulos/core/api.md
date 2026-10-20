# API pública — Core

Firmas verificadas contra el código real en esta sesión, organizadas por archivo
fuente. `core/__init__.py` está vacío
(`services/presupuestacion/core/__init__.py`) — no re-exporta nada; cada firma debajo
se importa directamente de su submódulo.

## `core/exceptions.py`

```python
class DomainError(Exception):
    def __init__(self, message: str) -> None: ...
    # exceptions.py:5-8

class AuthenticationError(DomainError): ...   # exceptions.py:11-12
class ForbiddenError(DomainError): ...        # exceptions.py:15-16
class NotFoundError(DomainError): ...         # exceptions.py:19-20
class ConflictError(DomainError): ...         # exceptions.py:23-24
class ValidationError(DomainError): ...       # exceptions.py:27-28
class RateLimitError(DomainError): ...        # NUEVO, services/shared/exceptions.py:38-39 → 429
# Un servicio externo (p.ej. Supabase Auth) rechazó el pedido por límite de intentos.
# Entrada `RateLimitError: 429` en STATUS_MAP (services/shared/exceptions.py:60). El shim
# core/exceptions.py no la reexporta: se importa de services.shared.exceptions
# (services/presupuestacion/auth/repository.py:14-18). Ver ../usuarios/reglas.md RN-USUARIOS-043.
class ServicioExternoNoDisponibleError(DomainError): ...  # NUEVO, services/shared/exceptions.py:42-43 → 503
# Un servicio externo (p.ej. Supabase Auth) no responde o responde con un error propio (5xx).
# Entrada `ServicioExternoNoDisponibleError: 503` en STATUS_MAP (services/shared/exceptions.py:61).
# Tampoco está en el shim; la importa auth/repository.py. Ver ../usuarios/reglas.md RN-USUARIOS-047.

STATUS_MAP: dict[type[DomainError], int]      # exceptions.py:31-37

def register_exception_handlers(app: FastAPI) -> None: ...
# exceptions.py:40-46
```

## `core/texto.py`

```python
def normalizar_descripcion(texto: str) -> str: ...
# texto.py:5-8
```

## `core/database.py`

```python
def get_bearer_token(authorization: str | None = Header(None)) -> str: ...
# database.py:10-16

@lru_cache
def get_service_client() -> Client: ...
# database.py:19-22

def get_user_client(token: str = Depends(get_bearer_token)) -> Client: ...
# database.py:25-29
```

## `core/stock.py`

Funciones públicas (usadas fuera del módulo):

```python
def listar_stock_por_producto(
    client: Client, *, producto_id: str, drogueria_id: str
) -> list[dict[str, Any]]: ...
# stock.py:13-23

def buscar_fila_stock(client: Client, *, fila_id: str) -> dict[str, Any] | None: ...
# stock.py:26-28

def actualizar_comprometida_si_no_cambio(
    client: Client, *, fila_id: str, valor_esperado: str, nuevo_valor: str
) -> dict[str, Any] | None: ...
# stock.py:31-41

def actualizar_disponible_si_no_cambio(
    client: Client, *, fila_id: str, valor_esperado: str, nuevo_valor: str
) -> dict[str, Any] | None: ...
# stock.py:44-54

def comprometer_stock_producto(
    client: Client, *, producto_id: str, drogueria_id: str, cantidad: Decimal
) -> list[tuple[str, Decimal]]: ...
# stock.py:124-170

def liberar_o_reportar(
    client: Client, compromisos: list[tuple[str, Decimal]], motivo_original: ConflictError
) -> None: ...
# stock.py:173-186

def liberar_compromisos(client: Client, compromisos: list[tuple[str, Decimal]]) -> None: ...
# stock.py:189-208

def entregar_stock_producto(
    client: Client,
    *,
    producto_id: str,
    drogueria_id: str,
    cantidad_entregada: Decimal,
    cantidad_rechazada: Decimal = Decimal("0"),
) -> tuple[Decimal, Decimal]: ...
# stock.py:273-325
```

Helpers privados (prefijo `_`, no pensados para uso fuera de `stock.py`, aunque los
tests sí los importan/mockean directamente):

```python
def _comprometer_hasta(client: Client, *, fila_id: str, monto_deseado: Decimal) -> Decimal: ...
# stock.py:57-92

def _liberar_monto(client: Client, *, fila_id: str, monto: Decimal) -> None: ...
# stock.py:95-121

def _liberar_hasta(client: Client, *, fila_id: str, monto_deseado: Decimal) -> Decimal: ...
# stock.py:211-239

def _descontar_disponible_hasta(client: Client, *, fila_id: str, monto_deseado: Decimal) -> Decimal: ...
# stock.py:242-270
```

Constantes:

```python
_MAX_REINTENTOS = 5                 # stock.py:9
_BACKOFF_BASE_SEGUNDOS = 0.05       # stock.py:10
```

## `core/config.py`

```python
class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str
    usuario_sistema_id: str
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    frontend_url: str = "http://localhost:5173"
    auth_email_domain: str = "usuarios.local"
    # ... (flags de PCP y de exportación de OC)

    @property
    def cors_origins_list(self) -> list[str]: ...
# Implementación real en services/shared/config.py:9-42 (core/config.py es un shim de reexport).
# auth_email_domain (variable de entorno / .env AUTH_EMAIL_DOMAIN, opcional, default
# "usuarios.local", services/shared/config.py:18-21): dominio de los emails internos y opacos
# `<uuid hex>@<dominio>` con los que usuarios/service.py crea las cuentas de Supabase Auth
# (odd/tasks/login-usuario-alta-admin.md S2). Nunca se envía correo a esas direcciones ni se
# muestran en el frontend. frontend_url ya no lo usa usuarios/ (era el redirect de la invitación).

@lru_cache
def get_settings() -> Settings: ...
# config.py:23-25
```

## `core/audit.py`

```python
EntidadAuditable = Literal[
    "proceso_comercial", "comparativa", "orden_compra", "presupuesto", "evento"
]
# audit.py:7-9

OrigenCambio = Literal["usuario", "ia", "automatizacion", "webhook", "api", "sistema"]
# audit.py:10

_COLUMNA_FK_POR_ENTIDAD: dict[EntidadAuditable, str]
# audit.py:12-18

def registrar_cambio(
    client: Client,
    *,
    entidad: EntidadAuditable,
    entidad_id: str,
    drogueria_id: str,
    campo: str,
    valor_anterior: Any,
    valor_nuevo: Any,
    origen: OrigenCambio,
    usuario_id: str,
    batch_id: str,
) -> None: ...
# audit.py:31-62

def registrar_cambios(
    client: Client,
    *,
    entidad: EntidadAuditable,
    entidad_id: str,
    drogueria_id: str,
    cambios: dict[str, tuple[Any, Any]],
    origen: OrigenCambio,
    usuario_id: str,
    batch_id: str | None = None,
) -> str: ...
# audit.py:65-90

def registrar_evento_ciclo_vida(
    client: Client,
    *,
    entidad: EntidadAuditable,
    entidad_id: str,
    drogueria_id: str,
    tipo_cambio: Literal["creacion", "eliminacion", "restauracion"],
    origen: OrigenCambio,
    usuario_id: str,
    batch_id: str | None = None,
) -> str: ...
# audit.py:93-114
```

Helper privado: `_a_texto(valor: Any) -> str | None` (`audit.py:21-28`).

## `core/auth.py`

```python
class UserClaims(BaseModel):
    sub: str
    exp: int
# auth.py:13-15

MENSAJE_CAMBIO_PASSWORD_PENDIENTE = "Debés cambiar tu contraseña antes de continuar"
# shared/auth.py:25

class UsuarioPerfil(BaseModel):
    id: str
    drogueria_id: str | None
    rol: str
    activo: bool = True
    debe_cambiar_password: bool = False
# shared/auth.py:28-33

def get_current_claims(token: str = Depends(get_bearer_token)) -> UserClaims: ...
# shared/auth.py:36-41

def _cargar_perfil(claims: UserClaims, client: Client) -> UsuarioPerfil: ...
# shared/auth.py:44-57 — SELECT id, drogueria_id, rol, activo, debe_cambiar_password; NotFoundError
# sin fila; AuthenticationError("Usuario desactivado") si activo es False (:55-56).

def exigir_password_al_dia(perfil: UsuarioPerfil) -> None: ...
# shared/auth.py:60-62 — ForbiddenError(MENSAJE_CAMBIO_PASSWORD_PENDIENTE) si el flag está en True.

def get_current_user(
    claims: UserClaims = Depends(get_current_claims),
    client: Client = Depends(get_user_client),
) -> UsuarioPerfil: ...
# shared/auth.py:65-73 — _cargar_perfil + exigir_password_al_dia (RN-CORE-026, RN-CORE-027).

def get_current_user_con_password_pendiente(
    claims: UserClaims = Depends(get_current_claims),
    client: Client = Depends(get_user_client),
) -> UsuarioPerfil: ...
# shared/auth.py:76-83 — dependencia permisiva: solo _cargar_perfil, sin el bloqueo por cambio
# pendiente. Solo para leer el propio perfil y cambiar la propia contraseña (RN-CORE-027).

def require_roles(*roles: str) -> Callable[..., UsuarioPerfil]: ...
# shared/auth.py:86-92 — depende de get_current_user, así que también bloquea con cambio pendiente.
```

`core/auth.py` es un shim que reexporta `UserClaims`, `UsuarioPerfil`, `get_current_claims`,
`get_current_user` y `require_roles` desde `services/shared/auth.py`;
`exigir_password_al_dia` y `get_current_user_con_password_pendiente` se importan directo de
`services.shared.auth` (`usuarios/router.py:26`, `auth/router.py:6`).

## `auditoria/models.py`

```python
EntidadAuditable = Literal["proceso_comercial", "comparativa", "orden_compra", "presupuesto", "evento"]
# models.py:6

_COLUMNA_FK_POR_ENTIDAD: dict[str, str]
# models.py:8-14

class HistorialCambioOut(BaseModel):
    id: str
    tipo_cambio: str
    campo: str | None
    valor_anterior: str | None
    valor_nuevo: str | None
    batch_id: str | None
    usuario_id: str | None
    origen: str
    observaciones: str | None
    created_at: datetime
# models.py:17-27
```

## `auditoria/router.py`

```python
router = APIRouter()
# router.py:8

_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")
# router.py:10

@router.get("/historial/{entidad}/{entidad_id}", response_model=list[HistorialCambioOut])
def listar_historial_endpoint(
    entidad: EntidadAuditable,
    entidad_id: str,
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[HistorialCambioOut]: ...
# router.py:13-28
```

## `shared/auth_jwt.py`

```python
class TokenInvalidoError(Exception): ...
# auth_jwt.py:12-13

@lru_cache
def _jwk_client(supabase_url: str) -> PyJWKClient: ...
# auth_jwt.py:16-19

def verificar_token(token: str, *, supabase_url: str) -> dict: ...
# auth_jwt.py:22-36
```
