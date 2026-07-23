# API pública — Imports

Firmas verificadas contra el código real en esta sesión.

## `imports/models.py`

```python
Clasificacion = Literal[
    "medicamento", "descartable", "insumo", "equipamiento", "perfumeria", "otro"
]
TipoProveedor = Literal["laboratorio", "drogueria", "distribuidor", "cooperativa", "otro"]
TipoCliente = Literal["hospital", "obra_social", "municipio", "provincia", "nacional", "otro"]
# models.py:7-11 — definidos de forma independiente, no reexportados de
# catalogo/models.py ni de clientes/models.py.

class ImportProductoRow(BaseModel):
    codigo_interno: str
    nombre: str
    categoria_id: str | None = None
    clasificacion: Clasificacion | None = None
    droga: str | None = None
    presentacion: str | None = None
    forma_farmaceutica: str | None = None
    laboratorio: str | None = None
    codigo_anmat: str | None = None
    datos_sistema: dict | None = None
# models.py:14-24

class ImportProductosRequest(BaseModel):
    productos: list[ImportProductoRow]
# models.py:27-28

class ImportProductosResultado(BaseModel):
    creados: int
    actualizados: int
    desactivados: int
# models.py:31-34

class ImportCostoRow(BaseModel):
    codigo_interno: str
    costo_unitario: Decimal
    fecha_desde: date
# models.py:37-40

class ImportCostosRequest(BaseModel):
    costos: list[ImportCostoRow]
# models.py:43-44

class ImportCostosResultado(BaseModel):
    nuevos: int
    actualizados: int
    sin_cambios: int
    no_encontrados: list[str]
# models.py:47-51

class ImportStockRow(BaseModel):
    codigo_interno: str
    deposito: str | None = None
    cantidad_disponible: Decimal
# models.py:54-57

class ImportStockRequest(BaseModel):
    stock: list[ImportStockRow]
# models.py:60-61

class ImportStockResultado(BaseModel):
    upserted: int
    no_encontrados: list[str]
# models.py:64-66

class ImportProveedorRow(BaseModel):
    codigo_interno: str | None = None
    razon_social: str
    nombre_comercial: str | None = None
    cuit: str | None = None
    tipo: TipoProveedor | None = None
    es_competidor: bool | None = None
    es_proveedor_compra: bool | None = None
    plazo_pago_dias: int | None = None
    condiciones_pago: str | None = None
# models.py:69-78

class ImportProveedoresRequest(BaseModel):
    proveedores: list[ImportProveedorRow]
# models.py:81-82

class ImportProveedoresResultado(BaseModel):
    creados: int
    actualizados: int
    desactivados: int
    sin_codigo_interno: int
# models.py:85-89

class ImportClienteRow(BaseModel):
    codigo_interno: str
    nombre: str | None = None
    tipo: TipoCliente | None = None
    direccion: str | None = None
    ciudad: str | None = None
    provincia: str | None = None
    codigo_postal: str | None = None
    plazo_pago_dias: int | None = None
    condiciones_pago: str | None = None
# models.py:92-101
# nombre/tipo opcionales a nivel de Pydantic; requeridos en runtime solo para altas
# nuevas (ValidationError explícito en service.py:294-297, RN-IMPORTS-003).

class ImportClientesRequest(BaseModel):
    clientes: list[ImportClienteRow]
# models.py:104-105

class ImportClientesResultado(BaseModel):
    creados: int
    actualizados: int
    desactivados: int
# models.py:108-111
```

## `imports/repository.py`

Capa delgada de acceso a datos, sin lógica de negocio. Todas las funciones reciben
`client: Client` explícito. Organizado en 4 bloques comentados (`-- productos --`,
`-- costos --`, `-- stock --`, `-- proveedores --`, `-- clientes --`).

```python
# -- productos --
def codigos_existentes_productos(client: Client, *, drogueria_id: str, codigos: list[str]) -> set[str]: ...
# repository.py:7-17

def codigos_activos_productos(client: Client, *, drogueria_id: str) -> set[str]: ...
# repository.py:20-29
# WHERE drogueria_id=? AND activo=True AND deleted_at IS NULL.

def insertar_productos(client: Client, filas: list[dict[str, Any]]) -> None: ...
# repository.py:32-34

def actualizar_productos_existentes(client: Client, filas: list[dict[str, Any]]) -> None: ...
# repository.py:37-39
# upsert con on_conflict="drogueria_id,codigo_interno".

def desactivar_productos(client: Client, *, drogueria_id: str, codigos: list[str], usuario_id: str) -> None: ...
# repository.py:42-46

def mapear_productos_por_codigo(client: Client, *, drogueria_id: str, codigos: list[str]) -> dict[str, str]: ...
# repository.py:49-61
# Compartida por los flujos de costos y stock.

# -- costos --
def costos_vigentes_por_producto(client: Client, *, producto_ids: list[str]) -> dict[str, dict[str, Any]]: ...
# repository.py:66-76
# WHERE producto_id IN (...) AND fecha_hasta IS NULL — una query para todo el lote.

def crear_costo(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:79-80

def cerrar_costo_vigente(client: Client, *, costo_id: str, fecha_hasta: str) -> None: ...
# repository.py:83-84

# -- stock --
def upsert_stock(client: Client, filas: list[dict[str, Any]]) -> None: ...
# repository.py:89-91
# upsert con on_conflict="producto_id,deposito".

# -- proveedores --
def codigos_existentes_proveedores(client: Client, *, drogueria_id: str, codigos: list[str]) -> set[str]: ...
# repository.py:96-108

def codigos_activos_proveedores(client: Client, *, drogueria_id: str) -> set[str]: ...
# repository.py:111-121
# Único de los 3 "codigos_activos_*" con filtro adicional not_.is_("codigo_interno", None).

def insertar_proveedores(client: Client, filas: list[dict[str, Any]]) -> None: ...
# repository.py:124-126

def actualizar_proveedores_existentes(client: Client, filas: list[dict[str, Any]]) -> None: ...
# repository.py:129-131

def desactivar_proveedores(client: Client, *, drogueria_id: str, codigos: list[str], usuario_id: str) -> None: ...
# repository.py:134-138

# -- clientes --
def mapear_clientes_por_codigo(client: Client, *, drogueria_id: str, codigos: list[str]) -> dict[str, str]: ...
# repository.py:143-155
# Sin filtro de activo/deleted_at — encuentra clientes inactivos igual que activos (ver RN-IMPORTS-007).

def codigos_activos_clientes(client: Client, *, drogueria_id: str) -> set[str]: ...
# repository.py:158-168

def insertar_clientes(client: Client, filas: list[dict[str, Any]]) -> None: ...
# repository.py:171-173

def actualizar_cliente(client: Client, *, cliente_id: str, campos: dict[str, Any]) -> None: ...
# repository.py:176-178
# Única función de update de todo el módulo que opera sobre un solo id (no en lote).

def desactivar_clientes(client: Client, *, drogueria_id: str, codigos: list[str], usuario_id: str) -> None: ...
# repository.py:181-185
```

## `imports/service.py`

```python
DEPOSITO_SENTINEL = "unico"
# service.py:18 — reusada por catalogo/repository.py (acoplamiento inverso, ver arquitectura.md).

def _usuario_sistema_id() -> str: ...
# service.py:21-22
# get_settings().usuario_sistema_id — mismo Settings de core/config.py que usa todo el backend.

def importar_productos(client: Client, *, drogueria_id: str, productos: list[ImportProductoRow], usuario_id: str) -> dict: ...
# service.py:27-73 — RN-IMPORTS-001, -011, -012.

def importar_productos_para_endpoint(*, drogueria_id: str, productos: list[ImportProductoRow]) -> dict: ...
# service.py:76-82

def importar_costos(client: Client, *, drogueria_id: str, costos: list[ImportCostoRow], usuario_id: str) -> dict: ...
# service.py:87-144 — RN-IMPORTS-004, -009, -010, -012.

def importar_costos_para_endpoint(*, drogueria_id: str, costos: list[ImportCostoRow]) -> dict: ...
# service.py:147-150

def importar_stock(client: Client, *, drogueria_id: str, stock: list[ImportStockRow], usuario_id: str) -> dict: ...
# service.py:155-183 — RN-IMPORTS-005, -006, -012.

def importar_stock_para_endpoint(*, drogueria_id: str, stock: list[ImportStockRow]) -> dict: ...
# service.py:180-183

def importar_proveedores(client: Client, *, drogueria_id: str, proveedores: list[ImportProveedorRow], usuario_id: str) -> dict: ...
# service.py:188-244 — RN-IMPORTS-002, -008, -011, -012.

def importar_proveedores_para_endpoint(*, drogueria_id: str, proveedores: list[ImportProveedorRow]) -> dict: ...
# service.py:246-254

def importar_clientes(client: Client, *, drogueria_id: str, clientes: list[ImportClienteRow], usuario_id: str) -> dict: ...
# service.py:259-325 — RN-IMPORTS-003, -007, -012.

def importar_clientes_para_endpoint(*, drogueria_id: str, clientes: list[ImportClienteRow]) -> dict: ...
# service.py:327-333
```

`usuario_id` en los 5 `*_para_endpoint` es siempre `_usuario_sistema_id()`, nunca un
parámetro recibido del llamador — a diferencia de `clientes/service.py` y
`catalogo/service.py`, cuyos wrappers `*_para_endpoint` sí reciben `usuario_id` como
argumento explícito desde `router.py`. Ver D-IMPORTS-002 en
[`decisiones.md`](./decisiones.md).

## `imports/router.py`

```python
router = APIRouter(prefix="/imports")
# router.py:24

_ROLES_IMPORT = ("admin", "gerencia", "compras")
# router.py:26
```

| Método | Path | Request | Response | Roles requeridos | Archivo |
|---|---|---|---|---|---|
| POST | `/imports/productos` | `ImportProductosRequest` | `ImportProductosResultado` | `_ROLES_IMPORT` | `router.py:29-37` |
| POST | `/imports/costos` | `ImportCostosRequest` | `ImportCostosResultado` | `_ROLES_IMPORT` | `router.py:40-46` |
| POST | `/imports/stock` | `ImportStockRequest` | `ImportStockResultado` | `_ROLES_IMPORT` | `router.py:49-55` |
| POST | `/imports/proveedores` | `ImportProveedoresRequest` | `ImportProveedoresResultado` | `_ROLES_IMPORT` | `router.py:58-66` |
| POST | `/imports/clientes` | `ImportClientesRequest` | `ImportClientesResultado` | `_ROLES_IMPORT` | `router.py:69-75` |

Sin excepciones de dominio propias más allá de `ValidationError` (RN-IMPORTS-012,
mapeada a 422 según `core/exceptions.py`, ver [`../core/api.md`](../core/api.md)). No
hay `NotFoundError` en ningún punto de este módulo: los 5 flujos son idempotentes por
diseño respecto a filas inexistentes — un `codigo_interno` que no matchea simplemente
se reporta en `no_encontrados` (costos, stock) o se trata como alta nueva
(productos, proveedores, clientes), nunca produce un error HTTP.
