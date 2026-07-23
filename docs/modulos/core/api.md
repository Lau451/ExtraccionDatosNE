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

    @property
    def cors_origins_list(self) -> list[str]: ...
# config.py:9-21

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

class UsuarioPerfil(BaseModel):
    id: str
    drogueria_id: str | None
    rol: str
    activo: bool = True
# auth.py:18-22

def get_current_claims(token: str = Depends(get_bearer_token)) -> UserClaims: ...
# auth.py:25-30

def get_current_user(
    claims: UserClaims = Depends(get_current_claims),
    client: Client = Depends(get_user_client),
) -> UsuarioPerfil: ...
# auth.py:33-49 — levanta AuthenticationError si perfil.activo es False (auth.py:47-48)

def require_roles(*roles: str) -> Callable[..., UsuarioPerfil]: ...
# auth.py:48-54
```

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
