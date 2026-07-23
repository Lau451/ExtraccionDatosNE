# API pública — Droguerías

Firmas verificadas contra el código real en esta sesión.

## `droguerias/models.py`

```python
_CUIT_RE = re.compile(r"^\d{2}-\d{8}-\d$")
# models.py:5

def _validar_formato_cuit(valor: str) -> str: ...
# models.py:8-11
# Valida solo formato NN-NNNNNNNN-N, no dígito verificador (RN-DROGUERIAS-001).

class DrogueriaCreate(BaseModel):
    nombre: str
    razon_social: str
    cuit: str
    ciudad: str
    provincia: str
    codigo_postal: str | None = None
    contacto_email: str
    contacto_telefono: str

    _validar_cuit = field_validator("cuit")(_validar_formato_cuit)
# models.py:14-24

class DrogueriaUpdate(BaseModel):
    nombre: str | None = None
    razon_social: str | None = None
    cuit: str | None = None
    ciudad: str | None = None
    provincia: str | None = None
    codigo_postal: str | None = None
    contacto_email: str | None = None
    contacto_telefono: str | None = None
    activa: bool | None = None
    plan_id: str | None = None

    @field_validator("cuit")
    @classmethod
    def _validar_cuit(cls, valor: str | None) -> str | None: ...
# models.py:27-44
# El validador se salta si valor is None (campo no enviado), ver models.py:42-43.

class DrogueriaOut(BaseModel):
    id: str
    nombre: str
    razon_social: str
    cuit: str
    ciudad: str
    provincia: str
    codigo_postal: str | None
    contacto_email: str
    contacto_telefono: str
    activa: bool
    plan_id: str | None
# models.py:47-58
```

## `droguerias/repository.py`

Capa delgada de acceso a datos, sin lógica de negocio. Todas las funciones reciben
`client: Client` explícito.

```python
def obtener_drogueria(client: Client, *, drogueria_id: str) -> dict[str, Any] | None: ...
# repository.py:6-8
# SELECT * WHERE id=? LIMIT 1. Usada solo por service.py (existencia previa a UPDATE/DELETE).

def crear_drogueria(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:11-12

def actualizar_drogueria(client: Client, *, drogueria_id: str, campos: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:15-16

def eliminar_drogueria(client: Client, *, drogueria_id: str) -> None: ...
# repository.py:19-20
# DELETE real (no soft-delete). Puede levantar postgrest.exceptions.APIError por FK.
```

## `droguerias/service.py`

```python
def crear_drogueria(client: Client, *, body: DrogueriaCreate) -> dict[str, Any]: ...
# service.py:12-13
# Sin validación de duplicados de cuit (ver flujo.md Flujo 1).

def actualizar_drogueria(
    client: Client, *, drogueria_id: str, body: DrogueriaUpdate
) -> dict[str, Any]: ...
# service.py:16-24
# RN-DROGUERIAS-002 (existencia) + RN-DROGUERIAS-003 (parcial).

def eliminar_drogueria(client: Client, *, drogueria_id: str) -> None: ...
# service.py:27-38
# RN-DROGUERIAS-002 (existencia) + RN-DROGUERIAS-004 (APIError → ConflictError).

def crear_drogueria_para_endpoint(*, body: DrogueriaCreate) -> dict[str, Any]: ...
# service.py:41-42

def actualizar_drogueria_para_endpoint(*, drogueria_id: str, body: DrogueriaUpdate) -> dict[str, Any]: ...
# service.py:45-46

def eliminar_drogueria_para_endpoint(*, drogueria_id: str) -> None: ...
# service.py:49-50
```

Los 3 `*_para_endpoint` resuelven `get_service_client()` internamente
(`core/database.py`, ver [`../core/`](../core/)) y delegan en la función homónima sin
sufijo.

## `droguerias/router.py`

```python
router = APIRouter()
# router.py:14
```

| Método | Path | Request | Response | Roles requeridos | Cliente Supabase | Archivo |
|---|---|---|---|---|---|---|
| GET | `/droguerias` | — | `list[DrogueriaOut]` | cualquier autenticado (RLS acota) | `user_client` | `router.py:17-24` |
| GET | `/droguerias/{drogueria_id}` | — | `DrogueriaOut` | cualquier autenticado (RLS acota) | `user_client` | `router.py:27-36` |
| POST | `/droguerias` | `DrogueriaCreate` | `DrogueriaOut` | `superadmin` | `service_client` | `router.py:39-43` |
| PATCH | `/droguerias/{drogueria_id}` | `DrogueriaUpdate` | `DrogueriaOut` | `superadmin` | `service_client` | `router.py:46-52` |
| DELETE | `/droguerias/{drogueria_id}` | — | `204 No Content` | `superadmin` | `service_client` | `router.py:55-60` |

Excepciones de dominio levantadas por este módulo y su status HTTP (mapeo centralizado
en `core/exceptions.py`, ver [`../core/api.md`](../core/api.md)): `NotFoundError`→404
(`GET /droguerias/{id}` inline en el router, RN-DROGUERIAS-002 en `PATCH`/`DELETE`),
`ConflictError`→409 (RN-DROGUERIAS-004, `DELETE` con datos asociados),
`ValidationError` de Pydantic (422, no de `core/exceptions.py`) en `POST`/`PATCH` si el
`cuit` tiene formato inválido (RN-DROGUERIAS-001).
