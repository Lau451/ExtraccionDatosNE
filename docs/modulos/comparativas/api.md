# API pública — Comparativas

## `models.py`

```python
class AsignarProveedorRequest(BaseModel):
    proveedor_id: str

class RenglonGanado(BaseModel):
    proceso_comercial_id: str
    proceso: str
    cliente: str | None
    oferta_item_id: str
    renglon_id: str | None
    descripcion: str | None
    precio_unitario: Decimal
    cantidad_ofertada: Decimal | None
    ganado_oficial: bool
    ganado_estimado: bool
    nivel: str | None

class OfertaSinMatchear(BaseModel):
    texto_crudo: str
    drogueria_id: str
    apariciones: int
    veces_ganador: int
```

(`models.py:1-29`)

## `repository.py`

Acceso a datos puro — sin lógica de negocio, todas reciben `client: Client` como
primer parámetro posicional, resto de argumentos `keyword-only` (`*`).

| Función | Firma | Línea |
|---|---|---|
| `buscar_oferta_item` | `(client, *, oferta_item_id: str) -> dict[str, Any] \| None` | `6-10` |
| `buscar_proveedor` | `(client, *, proveedor_id: str) -> dict[str, Any] \| None` | `13-21` |
| `actualizar_oferta_item` | `(client, *, oferta_item_id: str, campos: dict[str, Any]) -> dict[str, Any]` | `24-33` |
| `listar_renglones_ganados` | `(client, *, proceso_comercial_id: str) -> list[dict[str, Any]]` | `36-43` |
| `listar_ofertas_sin_matchear` | `(client) -> list[dict[str, Any]]` | `46-47` |

## `service.py`

| Función | Firma | Línea | Uso |
|---|---|---|---|
| `asignar_proveedor` | `(client: Client, *, oferta_item_id: str, proveedor_id: str) -> dict[str, Any]` | `10-25` | Caso de uso completo; recibe el cliente como parámetro — es la función que llaman los tests de integración directamente. |
| `asignar_proveedor_para_endpoint` | `(*, oferta_item_id: str, proveedor_id: str) -> dict[str, Any]` | `28-33` | Wrapper que resuelve `get_service_client()` y delega en `asignar_proveedor`; es lo único que importa `router.py`. |

Sin funciones privadas (prefijo `_`) — a diferencia de módulos más grandes como
`extraccion/`, todo el módulo cabe en 2 funciones públicas.

## `router.py`

| Endpoint | Función | Línea |
|---|---|---|
| `GET /procesos/{proceso_id}/renglones-ganados` | `renglones_ganados_endpoint` | `21-27` |
| `GET /proveedores/sin-matchear` | `ofertas_sin_matchear_endpoint` | `30-35` |
| `POST /ofertas/{oferta_id}/asignar-proveedor` | `asignar_proveedor_endpoint` | `38-59` |

`router = APIRouter()` (`router.py:15`), sin prefijo propio — se monta tal cual en
`main.py:46`. Los 2 endpoints `GET` llaman a `repository.py` directamente, sin pasar
por `service.py` (no hay caso de uso que envolver en una lectura sin reglas de
negocio); solo el `POST` pasa por `service.py`.

## Constantes de módulo

| Constante | Valor | Línea | Archivo |
|---|---|---|---|
| `_ROLES_ASIGNAR` | `("admin", "gerencia", "lider_comercial", "comercial")` | `17` | `router.py` |
| `_ROLES_LECTURA` | `("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")` | `18` | `router.py` |
