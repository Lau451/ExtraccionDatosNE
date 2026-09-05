# API pública — Catálogo

Firmas verificadas contra el código real en esta sesión.

## `catalogo/models.py`

```python
Clasificacion = Literal[
    "medicamento", "descartable", "insumo", "equipamiento", "perfumeria", "otro"
]
TipoProveedor = Literal["laboratorio", "drogueria", "distribuidor", "cooperativa", "otro"]
# models.py:7-10

class ProductoCreate(BaseModel):
    codigo_interno: str
    nombre: str
    categoria_id: str | None = None
    clasificacion: Clasificacion | None = None
    droga: str | None = None
    presentacion: str | None = None
    forma_farmaceutica: str | None = None
    laboratorio: str | None = None
    codigo_anmat: str | None = None
# models.py:13-22

class ProductoUpdate(BaseModel):
    # todos los campos de ProductoCreate salvo codigo_interno, opcionales, más:
    activo: bool | None = None
# models.py:25-34

class ProductoOut(BaseModel):
    id: str
    drogueria_id: str
    codigo_interno: str
    nombre: str
    categoria_id: str | None
    clasificacion: str | None
    droga: str | None
    presentacion: str | None
    forma_farmaceutica: str | None
    laboratorio: str | None
    codigo_anmat: str | None
    activo: bool
# models.py:37-49

class CategoriaCreate(BaseModel):
    nombre: str
    descripcion: str | None = None
# models.py:52-54

class CategoriaUpdate(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    activa: bool | None = None
# models.py:57-60

class CategoriaOut(BaseModel):
    id: str
    drogueria_id: str
    nombre: str
    descripcion: str | None
    activa: bool
# models.py:63-68

class ProveedorCreate(BaseModel):
    razon_social: str
    nombre_comercial: str | None = None
    cuit: str | None = None
    tipo: TipoProveedor = "otro"
    es_competidor: bool = True
    es_proveedor_compra: bool = False
    plazo_pago_dias: int | None = None
    condiciones_pago: str | None = None
# models.py:71-79

class ProveedorUpdate(BaseModel):
    # todos los campos de ProveedorCreate, opcionales, más:
    activo: bool | None = None
# models.py:82-91

class ProveedorOut(BaseModel):
    id: str
    drogueria_id: str
    codigo_interno: str | None
    razon_social: str
    nombre_comercial: str | None
    cuit: str | None
    tipo: str
    es_competidor: bool
    es_proveedor_compra: bool
    plazo_pago_dias: int | None
    condiciones_pago: str | None
    activo: bool
# models.py:94-106

class CostoCreate(BaseModel):
    costo_unitario: Decimal
    fecha_desde: date
# models.py:109-111
# Sin campo origen — este módulo siempre lo hardcodea a "manual" (RN-CATALOGO-007).

class CostoOut(BaseModel):
    id: str
    producto_id: str
    costo_unitario: Decimal
    fecha_desde: date
    fecha_hasta: date | None
    origen: str
# models.py:114-120

class StockAjuste(BaseModel):
    deposito: str | None = None
    cantidad_disponible: Decimal
# models.py:123-125
# Sin campo cantidad_comprometida — no es escribible desde este módulo (RN-CATALOGO-010).

class StockOut(BaseModel):
    id: str
    producto_id: str
    deposito: str | None
    cantidad_disponible: Decimal
    cantidad_comprometida: Decimal
# models.py:128-133
```

## `catalogo/repository.py`

Capa delgada de acceso a datos, sin lógica de negocio. Todas las funciones reciben
`client: Client` explícito. Único import cruzado del módulo:
`DEPOSITO_SENTINEL` de `services.presupuestacion.imports.service` (`repository.py:6`).

```python
# -- productos --

def crear_producto(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:10-11

def listar_productos(
    client: Client, *, drogueria_id: str, activo: bool | None = None, categoria_id: str | None = None
) -> list[dict[str, Any]]: ...
# repository.py:14-27
# WHERE drogueria_id=? AND deleted_at IS NULL [AND activo=?] [AND categoria_id=?] ORDER BY nombre.

def obtener_producto(client: Client, *, producto_id: str) -> dict[str, Any] | None: ...
# repository.py:30-39
# SELECT * WHERE id=? AND deleted_at IS NULL LIMIT 1.

def actualizar_producto(client: Client, *, producto_id: str, campos: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:42-43

def soft_delete_producto(client: Client, *, producto_id: str, usuario_id: str) -> None: ...
# repository.py:46-53
# UPDATE deleted_at=now(), deleted_by=usuario_id, activo=False.

# -- categorias --

def crear_categoria(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:58-59

def listar_categorias(client: Client, *, drogueria_id: str, activa: bool | None = None) -> list[dict[str, Any]]: ...
# repository.py:62-66
# WHERE drogueria_id=? [AND activa=?] ORDER BY nombre. Sin filtro deleted_at (no existe la columna).

def obtener_categoria(client: Client, *, categoria_id: str) -> dict[str, Any] | None: ...
# repository.py:69-71

def actualizar_categoria(client: Client, *, categoria_id: str, campos: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:74-75
# Sin función de borrado — RN-CATALOGO-004.

# -- proveedores --

def crear_proveedor(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:80-81

def listar_proveedores(client: Client, *, drogueria_id: str, activo: bool | None = None) -> list[dict[str, Any]]: ...
# repository.py:84-95
# WHERE drogueria_id=? AND deleted_at IS NULL [AND activo=?] ORDER BY razon_social.

def obtener_proveedor(client: Client, *, proveedor_id: str) -> dict[str, Any] | None: ...
# repository.py:98-107

def actualizar_proveedor(client: Client, *, proveedor_id: str, campos: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:110-111

def soft_delete_proveedor(client: Client, *, proveedor_id: str, usuario_id: str) -> None: ...
# repository.py:114-121

# -- costos --

def listar_costos(client: Client, *, producto_id: str) -> list[dict[str, Any]]: ...
# repository.py:126-134
# ORDER BY fecha_desde DESC.

def costo_vigente(client: Client, *, producto_id: str) -> dict[str, Any] | None: ...
# repository.py:137-146
# WHERE producto_id=? AND fecha_hasta IS NULL LIMIT 1.

def crear_costo(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:149-150

def cerrar_costo_vigente(client: Client, *, costo_id: str, fecha_hasta: str) -> None: ...
# repository.py:153-154
# Único UPDATE parcial del módulo: solo toca fecha_hasta.

# -- stock --

def listar_stock(client: Client, *, producto_id: str) -> list[dict[str, Any]]: ...
# repository.py:159-167
# ORDER BY deposito.

def buscar_stock_por_deposito(client: Client, *, producto_id: str, deposito: str | None) -> dict[str, Any] | None: ...
# repository.py:170-182
# deposito=None → usa DEPOSITO_SENTINEL (RN-CATALOGO-009).

def upsert_stock(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:185-191
# on_conflict="producto_id,deposito" — RN-CATALOGO-008.
```

## `catalogo/service.py`

```python
# -- productos --

def crear_producto(client: Client, *, drogueria_id: str, body: ProductoCreate, usuario_id: str) -> dict[str, Any]: ...
# service.py:23-42

def listar_productos(
    client: Client, *, drogueria_id: str, activo: bool | None = None, categoria_id: str | None = None
) -> list[dict[str, Any]]: ...
# service.py:45-48
# Wrapper directo sobre repo.listar_productos.

def obtener_producto(client: Client, *, producto_id: str, drogueria_id: str) -> dict[str, Any]: ...
# service.py:51-55
# RN-CATALOGO-001.

def actualizar_producto(
    client: Client, *, producto_id: str, drogueria_id: str, body: ProductoUpdate, usuario_id: str
) -> dict[str, Any]: ...
# service.py:58-64
# RN-CATALOGO-001 + RN-CATALOGO-002.

def eliminar_producto(client: Client, *, producto_id: str, drogueria_id: str, usuario_id: str) -> None: ...
# service.py:67-69
# RN-CATALOGO-001 + RN-CATALOGO-003.

def crear_producto_para_endpoint(*, drogueria_id: str, body: ProductoCreate, usuario_id: str) -> dict[str, Any]: ...
# service.py:72-73

def actualizar_producto_para_endpoint(
    *, producto_id: str, drogueria_id: str, body: ProductoUpdate, usuario_id: str
) -> dict[str, Any]: ...
# service.py:76-81

def eliminar_producto_para_endpoint(*, producto_id: str, drogueria_id: str, usuario_id: str) -> None: ...
# service.py:84-85

# -- categorias --

def crear_categoria(client: Client, *, drogueria_id: str, body: CategoriaCreate) -> dict[str, Any]: ...
# service.py:90-93

def listar_categorias(client: Client, *, drogueria_id: str, activa: bool | None = None) -> list[dict[str, Any]]: ...
# service.py:96-97

def actualizar_categoria(
    client: Client, *, categoria_id: str, drogueria_id: str, body: CategoriaUpdate
) -> dict[str, Any]: ...
# service.py:100-107
# Pertenencia (variante categoría de RN-CATALOGO-001) + RN-CATALOGO-002.
# Sin eliminar_categoria — RN-CATALOGO-004.

def crear_categoria_para_endpoint(*, drogueria_id: str, body: CategoriaCreate) -> dict[str, Any]: ...
# service.py:110-111

def actualizar_categoria_para_endpoint(
    *, categoria_id: str, drogueria_id: str, body: CategoriaUpdate
) -> dict[str, Any]: ...
# service.py:114-117

# -- proveedores --

def crear_proveedor(client: Client, *, drogueria_id: str, body: ProveedorCreate, usuario_id: str) -> dict[str, Any]: ...
# service.py:122-140

def listar_proveedores(client: Client, *, drogueria_id: str, activo: bool | None = None) -> list[dict[str, Any]]: ...
# service.py:143-146

def obtener_proveedor(client: Client, *, proveedor_id: str, drogueria_id: str) -> dict[str, Any]: ...
# service.py:149-153
# RN-CATALOGO-001.

def actualizar_proveedor(
    client: Client, *, proveedor_id: str, drogueria_id: str, body: ProveedorUpdate, usuario_id: str
) -> dict[str, Any]: ...
# service.py:156-162

def eliminar_proveedor(client: Client, *, proveedor_id: str, drogueria_id: str, usuario_id: str) -> None: ...
# service.py:165-167

def crear_proveedor_para_endpoint(*, drogueria_id: str, body: ProveedorCreate, usuario_id: str) -> dict[str, Any]: ...
# service.py:170-171

def actualizar_proveedor_para_endpoint(
    *, proveedor_id: str, drogueria_id: str, body: ProveedorUpdate, usuario_id: str
) -> dict[str, Any]: ...
# service.py:174-179

def eliminar_proveedor_para_endpoint(*, proveedor_id: str, drogueria_id: str, usuario_id: str) -> None: ...
# service.py:182-185

# -- costos --

def listar_costos(client: Client, *, producto_id: str, drogueria_id: str) -> list[dict[str, Any]]: ...
# service.py:190-192
# Valida pertenencia del producto antes de listar (única lectura del módulo que lo hace).

def crear_costo(client: Client, *, producto_id: str, drogueria_id: str, body: CostoCreate) -> dict[str, Any]: ...
# service.py:195-218
# RN-CATALOGO-001 + RN-CATALOGO-005 + RN-CATALOGO-006 + RN-CATALOGO-007.

def listar_costos_para_endpoint(*, producto_id: str, drogueria_id: str) -> list[dict[str, Any]]: ...
# service.py:221-222

def crear_costo_para_endpoint(*, producto_id: str, drogueria_id: str, body: CostoCreate) -> dict[str, Any]: ...
# service.py:225-226

# -- stock --

def listar_stock(client: Client, *, producto_id: str, drogueria_id: str) -> list[dict[str, Any]]: ...
# service.py:231-233
# Valida pertenencia del producto antes de listar.

def ajustar_stock(client: Client, *, producto_id: str, drogueria_id: str, body: StockAjuste) -> dict[str, Any]: ...
# service.py:236-250
# RN-CATALOGO-001 + RN-CATALOGO-008 + RN-CATALOGO-009 + RN-CATALOGO-010.
# Docstring textual citado en reglas.md RN-CATALOGO-010 (service.py:239-240).

def listar_stock_para_endpoint(*, producto_id: str, drogueria_id: str) -> list[dict[str, Any]]: ...
# service.py:253-254

def ajustar_stock_para_endpoint(*, producto_id: str, drogueria_id: str, body: StockAjuste) -> dict[str, Any]: ...
# service.py:257-258
```

Todos los `*_para_endpoint` resuelven `get_service_client()` internamente
(`core/database.py`, ver [`../core/`](../core/)) y delegan en la función homónima
sin sufijo — **12 pares en total** (confirmado por grep en esta sesión sobre
`^def .*_para_endpoint` en `service.py`; corrige el conteo de "8 pares" del
descubrimiento previo del módulo): 3 de producto, 2 de categoría (sin par de
eliminar — RN-CATALOGO-004), 3 de proveedor, 2 de costo y 2 de stock. Ver
[`decisiones.md`](./decisiones.md) D-CATALOGO-001.

## `catalogo/router.py`

```python
router = APIRouter()
# router.py:41

_ROLES_LECTURA_CATALOGO = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")
_ROLES_ESCRITURA_CATALOGO = ("admin", "gerencia", "compras")
_ROLES_ESCRITURA_CATEGORIAS = ("admin", "gerencia")
_ROLES_LECTURA_COSTOS = ("superadmin", "admin", "gerencia", "compras")
# router.py:43-46
```

| Método | Path | Request | Response | Roles requeridos | Archivo |
|---|---|---|---|---|---|
| GET | `/productos` | `activo?`, `categoria_id?` (query) | `list[ProductoOut]` | `_ROLES_LECTURA_CATALOGO` | `router.py:51-60` |
| POST | `/productos` | `ProductoCreate` | `ProductoOut` | `_ROLES_ESCRITURA_CATALOGO` | `router.py:63-68` |
| GET | `/productos/{producto_id}` | — | `ProductoOut` | `_ROLES_LECTURA_CATALOGO` | `router.py:71-77` |
| PATCH | `/productos/{producto_id}` | `ProductoUpdate` | `ProductoOut` | `_ROLES_ESCRITURA_CATALOGO` | `router.py:80-88` |
| DELETE | `/productos/{producto_id}` | — | `204 No Content` | `("admin", "gerencia")` hardcodeado | `router.py:91-98` |
| GET | `/categorias` | `activa?` (query) | `list[CategoriaOut]` | `_ROLES_LECTURA_CATALOGO` | `router.py:103-109` |
| POST | `/categorias` | `CategoriaCreate` | `CategoriaOut` | `_ROLES_ESCRITURA_CATEGORIAS` | `router.py:112-117` |
| PATCH | `/categorias/{categoria_id}` | `CategoriaUpdate` | `CategoriaOut` | `_ROLES_ESCRITURA_CATEGORIAS` | `router.py:120-128` |
| GET | `/proveedores` | `activo?` (query) | `list[ProveedorOut]` | `_ROLES_LECTURA_CATALOGO` | `router.py:133-139` |
| POST | `/proveedores` | `ProveedorCreate` | `ProveedorOut` | `_ROLES_ESCRITURA_CATALOGO` | `router.py:142-147` |
| GET | `/proveedores/{proveedor_id}` | — | `ProveedorOut` | `_ROLES_LECTURA_CATALOGO` | `router.py:150-156` |
| PATCH | `/proveedores/{proveedor_id}` | `ProveedorUpdate` | `ProveedorOut` | `_ROLES_ESCRITURA_CATALOGO` | `router.py:159-167` |
| DELETE | `/proveedores/{proveedor_id}` | — | `204 No Content` | `("admin", "gerencia")` hardcodeado | `router.py:170-177` |
| GET | `/productos/{producto_id}/costos` | — | `list[CostoOut]` | `_ROLES_LECTURA_COSTOS` | `router.py:182-187` |
| POST | `/productos/{producto_id}/costos` | `CostoCreate` | `CostoOut` | `_ROLES_ESCRITURA_CATALOGO` | `router.py:190-196` |
| GET | `/productos/{producto_id}/stock` | — | `list[StockOut]` | `_ROLES_LECTURA_CATALOGO` | `router.py:201-206` |
| PATCH | `/productos/{producto_id}/stock` | `StockAjuste` | `StockOut` | `_ROLES_ESCRITURA_CATALOGO` | `router.py:209-215` |

Excepciones de dominio levantadas por este módulo y su status HTTP (mapeo
centralizado en `core/exceptions.py`, ver [`../core/api.md`](../core/api.md)):
`NotFoundError`→404 (RN-CATALOGO-001, actualización de categoría inexistente). No se
encontró ningún `raise` de `ValidationError` ni `ForbiddenError` en este módulo — a
diferencia de [`../clientes/`](../clientes/), Catálogo usa una sola excepción de
dominio en todos sus casos.
