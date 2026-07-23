# API pública — Procesos Comerciales

Firmas verificadas contra el código real en esta sesión.

## `procesos_comerciales/models.py`

```python
Clase = Literal["cotizacion", "licitacion"]
Modalidad = Literal["mail", "pliego"]
Estado = Literal[
    "abierto", "presupuestado", "presentado", "en_evaluacion",
    "adjudicado", "perdido", "cerrado", "cancelado",
]
# models.py:7-18

class ProcesoComercialCreate(BaseModel):
    nombre: str
    clase: Clase
    cliente_id: str | None = None
    categoria_id: str | None = None
    monto_estimado: Decimal | None = None
    notas: str | None = None
    apertura: date | None = None
    vencimiento: date | None = None
    tipo_gestion: str | None = None
    modalidad: Modalidad | None = None
    comparativa_pedida: bool = False
# models.py:21-32

class ProcesoComercialResumen(BaseModel):
    id: str
    nombre: str
    clase: Clase
    estado: Estado
# models.py:35-39
# Payload mínimo devuelto por GET /procesos-comerciales.

class ProcesoComercialOut(BaseModel):
    id: str
    drogueria_id: str
    cliente_id: str | None
    clase: Clase
    nombre: str
    categoria_id: str | None
    fecha: date
    estado: Estado
    monto_estimado: Decimal | None
    notas: str | None
    apertura: date | None
    vencimiento: date | None
    tipo_gestion: str | None
    modalidad: Modalidad | None
    comparativa_pedida: bool
    created_at: datetime
    updated_at: datetime
# models.py:42-59
# Payload completo devuelto por POST /procesos-comerciales.
```

## `procesos_comerciales/repository.py`

Capa delgada de acceso a datos, sin lógica de negocio. Todas las funciones reciben
`client: Client` explícito.

```python
_ESTADOS_TERMINALES = ("adjudicado", "perdido", "cerrado", "cancelado")
# repository.py:9
# Comentario explicativo en repository.py:5-8 — ver reglas.md RN-PROCESOS-002.

def crear_proceso_comercial(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:12-13
# INSERT directo, devuelve la primera fila insertada.

def listar_procesos_comerciales(
    client: Client, *, drogueria_id: str, activos: bool = True
) -> list[dict[str, Any]]: ...
# repository.py:16-27
# SELECT id, nombre, clase, estado WHERE drogueria_id=? AND deleted_at IS NULL
# [AND estado NOT IN _ESTADOS_TERMINALES si activos=True] ORDER BY nombre.
```

## `procesos_comerciales/service.py`

```python
def _validar_campos_de_seguimiento(body: ProcesoComercialCreate) -> None: ...
# service.py:12-34
# Guarda de negocio RN-PROCESOS-001. No devuelve nada; levanta ValidationError si
# corresponde. No-op si body.clase != "cotizacion".

def crear_proceso_comercial(
    client: Client, *, drogueria_id: str, body: ProcesoComercialCreate, usuario_id: str
) -> dict[str, Any]: ...
# service.py:37-69
# Orquesta: _validar_campos_de_seguimiento -> repo.crear_proceso_comercial ->
# registrar_evento_ciclo_vida (RN-PROCESOS-003) -> devuelve la fila creada.

def crear_proceso_comercial_para_endpoint(
    *, drogueria_id: str, body: ProcesoComercialCreate, usuario_id: str
) -> dict[str, Any]: ...
# service.py:72-77
# Wrapper que resuelve get_service_client() internamente y delega en
# crear_proceso_comercial.

def listar_procesos_comerciales(
    client: Client, *, drogueria_id: str, activos: bool = True
) -> list[dict[str, Any]]: ...
# service.py:80-83
# Passthrough directo a repo.listar_procesos_comerciales, sin lógica adicional.
```

## `procesos_comerciales/router.py`

```python
router = APIRouter()
# router.py:16

_ROLES_ESCRITURA = ("admin", "gerencia", "lider_comercial", "comercial")
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")
# router.py:18-19
```

| Método | Path | Request | Response | Roles requeridos | Cliente Supabase | Archivo |
|---|---|---|---|---|---|---|
| GET | `/procesos-comerciales` | `activos: bool = True` (query) | `list[ProcesoComercialResumen]` | `_ROLES_LECTURA` | `user_client` | `router.py:22-30` |
| POST | `/procesos-comerciales` | `ProcesoComercialCreate` | `ProcesoComercialOut` | `_ROLES_ESCRITURA` | `service_client` (vía wrapper) | `router.py:33-40` |

Excepción de dominio levantada por este módulo y su status HTTP (mapeo centralizado en
`core/exceptions.py`, ver [`../core/api.md`](../core/api.md)): `ValidationError`→422
(RN-PROCESOS-001, exclusivo de `POST` con `clase="cotizacion"`).
