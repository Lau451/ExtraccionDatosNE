# API pública — Clientes

Firmas verificadas contra el código real en esta sesión.

## `clientes/models.py`

```python
DocType = Literal["comparativa", "licitacion", "cotizacion", "orden_compra"]
CategoriaObservacion = Literal[
    "general", "pago", "contacto", "logistica", "historial", "alerta", "otro"
]
TipoCliente = Literal["hospital", "obra_social", "municipio", "provincia", "nacional", "otro"]
# models.py:6-10

class ClienteCreate(BaseModel):
    nombre: str
    tipo: TipoCliente
    direccion: str | None = None
    ciudad: str | None = None
    provincia: str | None = None
    codigo_postal: str | None = None
    plazo_pago_dias: int | None = None
    condiciones_pago: str | None = None
# models.py:13-21

class ClienteUpdate(BaseModel):
    # todos los campos de ClienteCreate, opcionales, más:
    activo: bool | None = None
# models.py:24-33

class ClienteOut(BaseModel):
    id: str
    drogueria_id: str
    codigo_interno: str | None
    nombre: str
    tipo: str
    direccion: str | None
    ciudad: str | None
    provincia: str | None
    codigo_postal: str | None
    plazo_pago_dias: int | None
    condiciones_pago: str | None
    activo: bool
# models.py:36-48

class ClienteContactoCreate(BaseModel):
    nombre: str
    cargo: str | None = None
    email: str | None = None
    telefono: str | None = None
    es_principal: bool = False
    notas: str | None = None
# models.py:51-57

class ClienteContactoUpdate(BaseModel):
    # todos los campos de ClienteContactoCreate, opcionales, más:
    activo: bool | None = None
# models.py:60-67

class ClienteContactoOut(BaseModel):
    id: str
    cliente_id: str
    nombre: str
    cargo: str | None
    email: str | None
    telefono: str | None
    es_principal: bool
    notas: str | None
    activo: bool
# models.py:70-79

class ClienteFormatoDocumentoUpsert(BaseModel):
    doc_type: DocType
    descripcion_estructura: str | None = None
    instrucciones_prompt: str | None = None
    archivo_ejemplo_path: str | None = None
    archivo_ejemplo_nombre: str | None = None
    activo: bool = True
# models.py:82-88

class ClienteFormatoDocumentoOut(BaseModel):
    id: str
    cliente_id: str
    doc_type: DocType
    descripcion_estructura: str | None
    instrucciones_prompt: str | None
    archivo_ejemplo_path: str | None
    archivo_ejemplo_nombre: str | None
    activo: bool
# models.py:91-99

class ClienteObservacionCreate(BaseModel):
    categoria: CategoriaObservacion = "general"
    observacion: str
# models.py:102-104

class ClienteObservacionOut(BaseModel):
    id: str
    cliente_id: str
    categoria: CategoriaObservacion
    observacion: str
    creado_por: str | None
    created_at: datetime
# models.py:107-113
```

## `clientes/repository.py`

Capa delgada de acceso a datos, sin lógica de negocio. Todas las funciones reciben
`client: Client` explícito.

```python
def buscar_cliente(client: Client, *, cliente_id: str) -> dict[str, Any] | None: ...
# repository.py:7-15
# SELECT id, drogueria_id ... LIMIT 1 — versión acotada para validar pertenencia.

def obtener_cliente(client: Client, *, cliente_id: str) -> dict[str, Any] | None: ...
# repository.py:18-27
# SELECT * ... WHERE id=? AND deleted_at IS NULL LIMIT 1.

def listar_clientes(
    client: Client, *, drogueria_id: str, activo: bool | None = None
) -> list[dict[str, Any]]: ...
# repository.py:30-41
# SELECT * WHERE drogueria_id=? AND deleted_at IS NULL [AND activo=?] ORDER BY nombre.

def crear_cliente(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:44-45

def actualizar_cliente(client: Client, *, cliente_id: str, campos: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:48-49

def soft_delete_cliente(client: Client, *, cliente_id: str, usuario_id: str) -> None: ...
# repository.py:52-59
# UPDATE deleted_at=now(), deleted_by=usuario_id, activo=False.

def crear_contacto(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:62-63

def listar_contactos(client: Client, *, cliente_id: str) -> list[dict[str, Any]]: ...
# repository.py:66-74
# ORDER BY es_principal DESC.

def actualizar_contacto(client: Client, *, contacto_id: str, campos: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:77-78

def buscar_contacto(client: Client, *, contacto_id: str) -> dict[str, Any] | None: ...
# repository.py:81-85
# SELECT * WHERE id=contacto_id — sin filtrar por cliente_id (ver RN-CLIENTES-006).

def buscar_formato_documento(
    client: Client, *, cliente_id: str, doc_type: str
) -> dict[str, Any] | None: ...
# repository.py:88-99

def crear_formato_documento(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:102-104

def actualizar_formato_documento(
    client: Client, *, formato_id: str, campos: dict[str, Any]
) -> dict[str, Any]: ...
# repository.py:106-115

def listar_formato_documentos(client: Client, *, cliente_id: str) -> list[dict[str, Any]]: ...
# repository.py:118-126
# ORDER BY doc_type.

def crear_observacion(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:129-130

def listar_observaciones(client: Client, *, cliente_id: str) -> list[dict[str, Any]]: ...
# repository.py:133-141
# ORDER BY created_at DESC.
```

## `clientes/service.py`

```python
def _validar_cliente_de_la_drogueria(
    client: Client, *, cliente_id: str, drogueria_id: str
) -> dict[str, Any]: ...
# service.py:18-26
# NotFoundError si no existe; ValidationError si es de otra droguería (RN-CLIENTES-002).

def upsert_formato_documento(
    client: Client, *, cliente_id: str, drogueria_id: str,
    body: ClienteFormatoDocumentoUpsert, usuario_id: str,
) -> dict[str, Any]: ...
# service.py:29-66
# Upsert real por UNIQUE(cliente_id, doc_type) — RN-CLIENTES-003.

def listar_formato_documentos(client: Client, *, cliente_id: str) -> list[dict[str, Any]]: ...
# service.py:69-70
# Wrapper directo sobre repo.listar_formato_documentos.

def crear_observacion(
    client: Client, *, cliente_id: str, drogueria_id: str,
    body: ClienteObservacionCreate, usuario_id: str,
) -> dict[str, Any]: ...
# service.py:73-92

def listar_observaciones(client: Client, *, cliente_id: str) -> list[dict[str, Any]]: ...
# service.py:95-96

def crear_cliente(
    client: Client, *, drogueria_id: str, body: ClienteCreate, usuario_id: str
) -> dict[str, Any]: ...
# service.py:99-117
# Sin validación de duplicados/codigo_interno (ver flujo.md Flujo 1).

def listar_clientes(
    client: Client, *, drogueria_id: str, activo: bool | None = None
) -> list[dict[str, Any]]: ...
# service.py:120-123

def obtener_cliente(client: Client, *, cliente_id: str, drogueria_id: str) -> dict[str, Any]: ...
# service.py:126-130
# RN-CLIENTES-001.

def actualizar_cliente(
    client: Client, *, cliente_id: str, drogueria_id: str,
    body: ClienteUpdate, usuario_id: str,
) -> dict[str, Any]: ...
# service.py:133-139
# RN-CLIENTES-001 + RN-CLIENTES-004.

def eliminar_cliente(client: Client, *, cliente_id: str, drogueria_id: str, usuario_id: str) -> None: ...
# service.py:142-144
# RN-CLIENTES-001 + RN-CLIENTES-005.

def crear_contacto(
    client: Client, *, cliente_id: str, drogueria_id: str, body: ClienteContactoCreate
) -> dict[str, Any]: ...
# service.py:147-163

def listar_contactos(client: Client, *, cliente_id: str) -> list[dict[str, Any]]: ...
# service.py:166-167

def actualizar_contacto(
    client: Client, *, cliente_id: str, contacto_id: str, body: ClienteContactoUpdate
) -> dict[str, Any]: ...
# service.py:170-177
# RN-CLIENTES-006 + RN-CLIENTES-004.

def crear_cliente_para_endpoint(*, drogueria_id: str, body: ClienteCreate, usuario_id: str) -> dict[str, Any]: ...
# service.py:180-181

def actualizar_cliente_para_endpoint(
    *, cliente_id: str, drogueria_id: str, body: ClienteUpdate, usuario_id: str
) -> dict[str, Any]: ...
# service.py:184-189

def eliminar_cliente_para_endpoint(*, cliente_id: str, drogueria_id: str, usuario_id: str) -> None: ...
# service.py:192-193

def crear_contacto_para_endpoint(
    *, cliente_id: str, drogueria_id: str, body: ClienteContactoCreate
) -> dict[str, Any]: ...
# service.py:196-199

def actualizar_contacto_para_endpoint(
    *, cliente_id: str, contacto_id: str, body: ClienteContactoUpdate
) -> dict[str, Any]: ...
# service.py:202-205

def upsert_formato_documento_para_endpoint(
    *, cliente_id: str, drogueria_id: str,
    body: ClienteFormatoDocumentoUpsert, usuario_id: str,
) -> dict[str, Any]: ...
# service.py:208-219
# Docstring textual citado en decisiones.md D-CLIENTES-002 (service.py:211-212).

def crear_observacion_para_endpoint(
    *, cliente_id: str, drogueria_id: str,
    body: ClienteObservacionCreate, usuario_id: str,
) -> dict[str, Any]: ...
# service.py:222-231
```

Todos los `*_para_endpoint` resuelven `get_service_client()` internamente
(`core/database.py`, ver [`../core/`](../core/)) y delegan en la función homónima sin
sufijo.

## `clientes/router.py`

```python
router = APIRouter()
# router.py:34

_ROLES_ESCRITURA = ("admin", "gerencia", "lider_comercial", "comercial")
_ROLES_ELIMINACION = ("admin", "gerencia")
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")
# router.py:36-38

def _validar_cliente_y_obtener_drogueria_id(
    user_client: Client, usuario: UsuarioPerfil, cliente_id: str
) -> str: ...
# router.py:123-139
# NotFoundError si no existe; ForbiddenError si drogueria_id no coincide y el rol no
# es "superadmin" (RN-CLIENTES-007).
```

| Método | Path | Request | Response | Roles requeridos | Archivo |
|---|---|---|---|---|---|
| GET | `/clientes` | `activo?: bool` (query) | `list[ClienteOut]` | `_ROLES_LECTURA` | `router.py:41-47` |
| POST | `/clientes` | `ClienteCreate` | `ClienteOut` | `_ROLES_ESCRITURA` | `router.py:50-57` |
| GET | `/clientes/{cliente_id}` | — | `ClienteOut` | `_ROLES_LECTURA` | `router.py:60-66` |
| PATCH | `/clientes/{cliente_id}` | `ClienteUpdate` | `ClienteOut` | `_ROLES_ESCRITURA` | `router.py:69-77` |
| DELETE | `/clientes/{cliente_id}` | — | `204 No Content` | `_ROLES_ELIMINACION` | `router.py:80-87` |
| GET | `/clientes/{cliente_id}/contactos` | — | `list[ClienteContactoOut]` | `_ROLES_LECTURA` | `router.py:90-97` |
| POST | `/clientes/{cliente_id}/contactos` | `ClienteContactoCreate` | `ClienteContactoOut` | `_ROLES_ESCRITURA` | `router.py:100-108` |
| PATCH | `/clientes/{cliente_id}/contactos/{contacto_id}` | `ClienteContactoUpdate` | `ClienteContactoOut` | `_ROLES_ESCRITURA` | `router.py:111-120` |
| GET | `/clientes/{cliente_id}/formato-documentos` | — | `list[ClienteFormatoDocumentoOut]` | `_ROLES_LECTURA` | `router.py:142-152` |
| POST | `/clientes/{cliente_id}/formato-documentos` | `ClienteFormatoDocumentoUpsert` | `ClienteFormatoDocumentoOut` | `_ROLES_ESCRITURA` | `router.py:155-168` |
| GET | `/clientes/{cliente_id}/observaciones` | — | `list[ClienteObservacionOut]` | `_ROLES_LECTURA` | `router.py:171-181` |
| POST | `/clientes/{cliente_id}/observaciones` | `ClienteObservacionCreate` | `ClienteObservacionOut` | `_ROLES_ESCRITURA` | `router.py:184-197` |

Excepciones de dominio levantadas por este módulo y su status HTTP (mapeo centralizado
en `core/exceptions.py`, ver [`../core/api.md`](../core/api.md)): `NotFoundError`→404
(RN-CLIENTES-001, RN-CLIENTES-002 sin cliente, RN-CLIENTES-006, RN-CLIENTES-007 sin
cliente), `ValidationError`→422 (RN-CLIENTES-002 con cliente de otra droguería),
`ForbiddenError`→403 (RN-CLIENTES-007 con cliente de otra droguería y rol no
`superadmin`).
