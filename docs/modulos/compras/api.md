# API pública — Compras

Firmas verificadas contra el código real en esta sesión. `compras/__init__.py` está
vacío — no re-exporta nada; cada firma se importa directamente de su submódulo.

## `compras/models.py`

```python
class OrdenCompraItemRequest(BaseModel):
    numero_renglon: int
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    oferta_item_id: str | None = None
    producto_id: str | None = None
# models.py:7-13

class CrearOrdenCompraRequest(BaseModel):
    proceso_comercial_id: str
    numero_oc: str
    fecha_emision: date | None = None
    fecha_entrega_estimada: date | None = None
    direccion_entrega: str | None = None
    notas: str | None = None
    items: list[OrdenCompraItemRequest]
# models.py:16-23

class ResultadoOrdenCompra(BaseModel):
    orden_compra_id: str
    numero_oc: str
    estado: str
    monto_total: Decimal | None
    items_cantidad: int
# models.py:26-31

class EntregaItemRequest(BaseModel):
    oc_item_id: str
    cantidad_entregada: Decimal
    cantidad_rechazada: Decimal = Decimal("0")
    motivo_rechazo: str | None = None
    lote: str | None = None
    vencimiento: date | None = None
# models.py:34-40

class CrearEntregaRequest(BaseModel):
    fecha_entrega_planificada: date | None = None
    fecha_entrega_real: date | None = None
    observaciones: str | None = None
    items: list[EntregaItemRequest]
# models.py:43-47

class ResultadoEntrega(BaseModel):
    entrega_id: str
    estado: str
    orden_compra_estado: str
# models.py:50-53
```

## `compras/repository.py`

Acceso a datos puro; todas las funciones reciben `client: Client` como primer
parámetro posicional.

```python
def buscar_proceso_comercial(client: Client, *, proceso_comercial_id: str) -> dict[str, Any] | None: ...
# repository.py:6-14

def crear_orden_compra(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:17-18

def insertar_oc_items(client: Client, filas: list[dict[str, Any]]) -> list[dict[str, Any]]: ...
# repository.py:21-24 — no-op (retorna []) si `filas` está vacío.

def buscar_orden_compra(client: Client, *, orden_compra_id: str) -> dict[str, Any] | None: ...
# repository.py:27-31

def listar_oc_items(client: Client, *, orden_compra_id: str) -> list[dict[str, Any]]: ...
# repository.py:34-41

def actualizar_orden_compra(client: Client, *, orden_compra_id: str, campos: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:44-53 — UPDATE sin condición optimista (a diferencia de core.stock).

def buscar_oferta_item(client: Client, *, oferta_item_id: str) -> dict[str, Any] | None: ...
# repository.py:56-60

def marcar_oferta_adjudicada(client: Client, *, oferta_item_id: str) -> None: ...
# repository.py:63-64

def crear_entrega(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...
# repository.py:67-68

def insertar_entrega_items(client: Client, filas: list[dict[str, Any]]) -> list[dict[str, Any]]: ...
# repository.py:71-74 — no-op si `filas` está vacío.

def listar_entregas_por_orden(client: Client, *, orden_compra_id: str) -> list[dict[str, Any]]: ...
# repository.py:77-84

def listar_entrega_items_por_oc_items(client: Client, *, oc_item_ids: list[str]) -> list[dict[str, Any]]: ...
# repository.py:87-98 — no-op si `oc_item_ids` está vacío.
```

## `compras/service.py`

Casos de uso (reciben `client: Client` explícito, para tests con `service_client` real):

```python
def crear_orden_compra(
    client: Client, *, drogueria_id: str, usuario_id: str, body: CrearOrdenCompraRequest
) -> ResultadoOrdenCompra: ...
# service.py:44-109

def confirmar_orden_compra(
    client: Client, *, orden_compra_id: str, usuario_id: str
) -> ResultadoOrdenCompra: ...
# service.py:112-149

def crear_entrega(
    client: Client,
    *,
    orden_compra_id: str,
    items: list[EntregaItemRequest],
    fecha_entrega_planificada: date | None,
    fecha_entrega_real: date | None,
    observaciones: str | None,
) -> ResultadoEntrega: ...
# service.py:198-285
```

Wrappers para el endpoint (resuelven `get_service_client()` internamente):

```python
def crear_orden_compra_para_endpoint(
    *, drogueria_id: str, usuario_id: str, body: CrearOrdenCompraRequest
) -> ResultadoOrdenCompra: ...
# service.py:288-295

def confirmar_orden_compra_para_endpoint(
    *, orden_compra_id: str, usuario_id: str
) -> ResultadoOrdenCompra: ...
# service.py:298-303

def crear_entrega_para_endpoint(
    *,
    orden_compra_id: str,
    items: list[EntregaItemRequest],
    fecha_entrega_planificada: date | None,
    fecha_entrega_real: date | None,
    observaciones: str | None,
) -> ResultadoEntrega: ...
# service.py:306-323
```

Helpers privados (prefijo `_`):

```python
def _q(valor: Decimal) -> Decimal: ...
# service.py:26-27 — quantize a 2 decimales, ROUND_HALF_UP.

def _decimal_o_none(valor: Any) -> Decimal | None: ...
# service.py:30-31

def _resultado_oc(oc: dict[str, Any]) -> ResultadoOrdenCompra: ...
# service.py:34-41

def _calcular_estado_entrega(items: list[EntregaItemRequest]) -> str: ...
# service.py:152-160 — RN-COMPRAS-009.

def _recalcular_estado_orden_compra(client: Client, *, orden_compra_id: str) -> str: ...
# service.py:163-195 — RN-COMPRAS-012.
```

Constantes:

```python
_DOS_DECIMALES = Decimal("0.01")     # service.py:21
_UNIQUE_VIOLATION = "23505"          # service.py:22
_ESTADOS_PARA_ENTREGA = ("emitida", "en_entrega", "parcialmente_entregada")
                                      # service.py:23
```

## `compras/router.py`

```python
router = APIRouter()
# router.py:19

_ROLES_OC = ("admin", "gerencia", "lider_comercial", "comercial")
# router.py:21
_ROLES_ENTREGA = ("admin", "gerencia", "lider_comercial", "comercial", "compras")
# router.py:22
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")
# router.py:23

def _validar_oc_de_la_drogueria(
    user_client: Client, usuario: UsuarioPerfil, orden_compra_id: str
) -> None: ...
# router.py:26-41

@router.post("/ordenes-compra", response_model=ResultadoOrdenCompra)
def crear_orden_compra_endpoint(...) -> ResultadoOrdenCompra: ...
# router.py:44-66

@router.post("/ordenes-compra/{orden_compra_id}/confirmar", response_model=ResultadoOrdenCompra)
def confirmar_orden_compra_endpoint(...) -> ResultadoOrdenCompra: ...
# router.py:69-78

@router.post("/ordenes-compra/{orden_compra_id}/entregas", response_model=ResultadoEntrega)
def crear_entrega_endpoint(...) -> ResultadoEntrega: ...
# router.py:81-95

@router.get("/entregas/pendientes")
def entregas_pendientes_endpoint(...) -> list[dict]: ...
# router.py:98-103 — sin response_model.

@router.get("/compras/vs-cotizado")
def compras_vs_cotizado_endpoint(...) -> list[dict]: ...
# router.py:106-113 — sin response_model; whitelist de roles inline, distinta de las 3 constantes.
```
