# API pública — Pricing

Firmas verificadas contra el código real en esta sesión.

## `pricing/models.py`

```python
OrigenCosto = Literal["costo_estandar", "precio_especial"]
MetodoPrecio = Literal["mercado", "piso_margen", "margen_objetivo", "sin_precio"]
# models.py:7-8

class DetalleCalculo(BaseModel):
    origen_mercado: bool
    precio_mediana: Decimal | None
    muestras: int | None
    ventana_meses: int
    descuento_aplicado_pct: Decimal | None
    piso_calculado: Decimal
    referencia_calculada: Decimal | None
    gano: MetodoPrecio
# models.py:11-19
# Persistido como JSON en presupuesto_items.detalle_calculo (service.py:209-213).

class ResultadoPricingItem(BaseModel):
    item_proceso_id: str
    producto_id: str | None
    costo_usado: Decimal | None
    origen_costo: OrigenCosto | None
    precio_proveedor_id: str | None
    mantenimiento_hasta_usado: date | None
    precio_unitario: Decimal | None
    cantidad_ofertada: Decimal | None
    precio_mercado_usado: Decimal | None
    regla_pricing_id: str | None
    metodo_precio: MetodoPrecio
    margen_resultante_pct: Decimal | None
    detalle_calculo: DetalleCalculo | None
    stock_verificado: bool
    stock_al_generar: Decimal | None
# models.py:22-37
# Resultado del cálculo de un ítem; no se expone directo por ningún endpoint,
# se mapea a fila de presupuesto_items vía _a_fila_presupuesto_item (service.py:187-216).

class ResultadoGenerarPresupuesto(BaseModel):
    presupuesto_id: str
    monto_total: Decimal
    cantidad_items: int
    items_sin_precio: int
    regenerado: bool
# models.py:40-45
# response_model de POST /procesos/{id}/generar-presupuesto.
```

## `pricing/repository.py`

Capa delgada de acceso a datos, solo lectura. Todas las funciones reciben
`client: Client` explícito.

```python
def _primero_en_rango(filas: list[dict[str, Any]], cantidad: Decimal) -> dict[str, Any] | None: ...
# repository.py:9-18
# Primera fila (ya ordenada por el caller) cuyo cantidad_minima/cantidad_maxima contiene `cantidad`.

def buscar_precio_especial_puntual(
    client: Client, *, item_proceso_id: str, cantidad: Decimal
) -> dict[str, Any] | None: ...
# repository.py:21-34
# precios_proveedor WHERE item_proceso_id=? AND activa=True AND mantenimiento_hasta>=hoy
# ORDER BY precio_unitario, filtrado por rango de cantidad en Python.

def buscar_precio_especial_general(
    client: Client, *, producto_id: str, drogueria_id: str, cantidad: Decimal
) -> dict[str, Any] | None: ...
# repository.py:37-52
# Igual que la puntual, pero item_proceso_id IS NULL + producto_id + drogueria_id.

def buscar_costo_estandar_vigente(client: Client, *, producto_id: str) -> dict[str, Any] | None: ...
# repository.py:55-64
# costos_productos WHERE producto_id=? AND fecha_hasta IS NULL LIMIT 1.

def _alcance_or(columna: str, valor: str | None) -> str: ...
# repository.py:67-70
# Construye el fragmento PostgREST "{columna}.is.null,{columna}.eq.{valor}" por
# interpolación directa de string, sin escapar `valor`. Ver pendientes.md P1.

def buscar_regla_aplicable(
    client: Client, *, drogueria_id: str, cliente_id: str | None,
    clase_proceso: str, categoria_id: str | None
) -> dict[str, Any] | None: ...
# repository.py:73-93
# reglas_pricing WHERE drogueria_id=? AND activa=True AND alcance(cliente_id)
# AND alcance(clase_proceso) AND alcance(categoria_id) ORDER BY prioridad DESC LIMIT 1.

def buscar_precio_mercado(
    client: Client, *, producto_id: str, drogueria_id: str, meses_ventana: int
) -> dict[str, Any] | None: ...
# repository.py:96-109
# v_precio_mercado_producto WHERE producto_id=? AND drogueria_id=?
# AND ultima_muestra >= (hoy - meses_ventana meses) LIMIT 1.

def buscar_stock_libre(client: Client, *, producto_id: str) -> Decimal: ...
# repository.py:112-121
# sum(cantidad_disponible) - sum(cantidad_comprometida) de todas las filas
# de stock_productos del producto (todos los depósitos).

def buscar_producto(client: Client, *, producto_id: str) -> dict[str, Any] | None: ...
# repository.py:124-132
# SELECT id, categoria_id, drogueria_id FROM productos WHERE id=? LIMIT 1.

def buscar_proceso_comercial(client: Client, *, proceso_comercial_id: str) -> dict[str, Any] | None: ...
# repository.py:135-143
# SELECT id, drogueria_id, cliente_id, clase FROM procesos_comerciales WHERE id=? LIMIT 1.

def buscar_presupuesto_abierto(client: Client, *, proceso_comercial_id: str) -> dict[str, Any] | None: ...
# repository.py:146-155
# presupuestos WHERE proceso_comercial_id=? AND estado IN ('generado','en_revision') LIMIT 1.

def buscar_items_con_producto(client: Client, *, proceso_comercial_id: str) -> list[dict[str, Any]]: ...
# repository.py:158-166
# items_proceso WHERE proceso_comercial_id=? AND producto_id IS NOT NULL.
```

## `pricing/service.py`

```python
def resolver_costo(
    client: Client, *, item: dict[str, Any], drogueria_id: str
) -> tuple[Decimal | None, OrigenCosto | None, str | None, date | None]: ...
# service.py:30-50
# RN-PRICING-001. Devuelve (costo, origen_costo, precio_proveedor_id, mantenimiento_hasta).

def calcular_precio(
    client: Client, *, costo: Decimal, regla: dict[str, Any], producto_id: str, drogueria_id: str
) -> tuple[Decimal, DetalleCalculo] | None: ...
# service.py:53-98
# RN-PRICING-002, RN-PRICING-003, RN-PRICING-006. None si no hay mercado ni margen objetivo.

def verificar_stock(client: Client, *, producto_id: str, cantidad: Decimal) -> tuple[bool, Decimal]: ...
# service.py:101-103
# (libre >= cantidad, libre) — solo lectura, no compromete.

def calcular_item(
    client: Client, *, item: dict[str, Any], drogueria_id: str,
    clase_proceso: str, cliente_id: str | None
) -> ResultadoPricingItem: ...
# service.py:106-180
# Orquesta resolver_costo + buscar_regla_aplicable + calcular_precio + verificar_stock (condicional).

def generar_presupuesto(
    client: Client, *, proceso_comercial_id: str, drogueria_id: str, disparado_por: str
) -> ResultadoGenerarPresupuesto: ...
# service.py:219-316
# RN-PRICING-007, RN-PRICING-008. Alta o regeneración completa del presupuesto y sus ítems.
# Lanza NotFoundError si el proceso comercial no existe (service.py:223-224).

def generar_presupuesto_para_endpoint(
    *, proceso_comercial_id: str, drogueria_id: str, disparado_por: str
) -> ResultadoGenerarPresupuesto: ...
# service.py:319-328
# Único punto donde pricing usa service_role (docstring textual, service.py:322).
```

Funciones internas sin exportar fuera del módulo:
`_q` (redondeo `ROUND_HALF_UP` a 2 decimales, `service.py:22-23`),
`_decimal_o_none` (`service.py:26-27`),
`_decimal_a_texto` (`service.py:183-184`),
`_a_fila_presupuesto_item` (mapeo `ResultadoPricingItem` → fila de
`presupuesto_items`, incluye serialización de `detalle_calculo` a JSON vía
`model_dump_json`, `service.py:187-216`).

A diferencia de [`../catalogo/`](../catalogo/), este módulo **no** sigue el patrón
función pura + wrapper `_para_endpoint` en cada función — solo
`generar_presupuesto` tiene su par `_para_endpoint`; `resolver_costo`,
`calcular_precio`, `verificar_stock` y `calcular_item` son funciones internas de
orquestación sin exposición HTTP directa.

## `pricing/router.py`

```python
router = APIRouter()
# router.py:10

_ROLES_GENERAR_PRESUPUESTO = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial")
_ROLES_PRECIOS_ESPECIALES = ("superadmin", "admin", "gerencia", "compras")
# router.py:12-13
```

| Método | Path | Request | Response | Roles requeridos | Archivo |
|---|---|---|---|---|---|
| POST | `/procesos/{proceso_id}/generar-presupuesto` | — (path param) | `ResultadoGenerarPresupuesto` | `_ROLES_GENERAR_PRESUPUESTO` | `router.py:16-40` |
| GET | `/precios-especiales` | — | `list[dict]` (sin modelo tipado) | `_ROLES_PRECIOS_ESPECIALES` | `router.py:43-48` |

Excepciones de dominio levantadas por este módulo y su status HTTP (mapeo
centralizado en `core/exceptions.py`, ver [`../core/api.md`](../core/api.md)):
`NotFoundError`→404 (proceso comercial inexistente, `router.py:29-30`;
`service.py:223-224`), `ForbiddenError`→403 (droguería del proceso no coincide con
la del solicitante, `router.py:33-34`). No se encontró ningún `raise` de
`ValidationError` ni `ConflictError` en este módulo.
