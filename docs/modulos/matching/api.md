# API pública — Matching

## `models.py`

```python
EstadoMatching = Literal["pendiente", "automatico", "sugerido", "confirmado", "sin_match"]
MetodoMatching = Literal["exact", "fuzzy", "embedding", "manual"]

class CandidatoMatching(BaseModel):
    producto_id: str
    confianza: Decimal
    metodo: MetodoMatching
    detalle_scoring: dict[str, Any] | None = None

class ResultadoMatchingItem(BaseModel):
    item_proceso_id: str
    producto_id: str | None
    alias_id: str | None
    estado_matching: EstadoMatching
    confianza_matching: Decimal | None
    candidatos: list[CandidatoMatching]

class ConfirmarMatchingRequest(BaseModel):
    producto_id: str

class ItemMatchingPendiente(BaseModel):
    item_proceso_id: str
    proceso_comercial_id: str
    proceso: str
    clase: str
    cliente_id: str | None
    cliente: str | None
    numero_renglon: int
    descripcion: str
    estado_matching: EstadoMatching
    confianza_matching: Decimal | None
    candidatos: int
```

(`models.py:1-42`)

## `repository.py`

Acceso a datos puro — sin lógica de negocio, todas reciben `client: Client` como
primer parámetro posicional.

| Función | Firma | Línea |
|---|---|---|
| `buscar_item_proceso` | `(client, *, item_proceso_id: str) -> dict \| None` | `7-11` |
| `buscar_proceso_comercial` | `(client, *, proceso_comercial_id: str) -> dict \| None` | `14-22` |
| `buscar_alias_vigente` | `(client, *, cliente_id: str, descripcion_normalizada: str) -> dict \| None` | `25-37` |
| `listar_productos_activos` | `(client, *, drogueria_id: str) -> list[dict]` | `40-49` |
| `marcar_alias_usado` | `(client, *, alias_id: str, veces_usado: int) -> None` | `52-58` |
| `invalidar_alias` | `(client, *, alias_id: str) -> None` | `61-62` |
| `crear_alias` | `(client, *, cliente_id, drogueria_id, producto_id, descripcion_original, descripcion_normalizada, creado_por) -> dict` | `71-89` |
| `insertar_candidatos` | `(client, filas: list[dict]) -> None` | `92-95` |
| `marcar_candidato_elegido` | `(client, *, item_proceso_id: str, producto_id: str) -> None` | `97-100` |
| `actualizar_item_matching` | `(client, *, item_proceso_id: str, campos: dict) -> dict` | `103-106` |

Las líneas 65-68 son un comentario (no código) documentando la ausencia de
`proveedor_producto_alias` — ver [`pendientes.md`](./pendientes.md).

## `service.py`

Funciones privadas (prefijo `_`, no se importan desde otros módulos):

| Función | Firma | Línea |
|---|---|---|
| `_generar_candidatos` | `(client, *, drogueria_id: str, descripcion_normalizada: str) -> list[CandidatoMatching]` | `17-36` |
| `_upsert_alias` | `(client, *, item, cliente_id, drogueria_id, producto_id, descripcion_normalizada, usuario_id) -> str` | `113-141` |

Funciones públicas:

| Función | Firma | Línea | Uso |
|---|---|---|---|
| `procesar_matching_item` | `(client: Client, *, item: dict, drogueria_id: str, cliente_id: str \| None) -> ResultadoMatchingItem` | `39-110` | Caso de uso de matching automático (alias o fuzzy); único punto de entrada importado por otro módulo (`extraccion/service.py:15`). Recibe el cliente como parámetro — es la función que llaman los tests de integración directamente. |
| `confirmar_matching` | `(client: Client, *, item_proceso_id: str, producto_id: str, usuario_id: str) -> ResultadoMatchingItem` | `144-190` | Caso de uso de confirmación humana; recibe el cliente como parámetro. |
| `marcar_sin_match` | `(client: Client, *, item_proceso_id: str) -> ResultadoMatchingItem` | `193-211` | Caso de uso de descarte; recibe el cliente como parámetro. |
| `confirmar_matching_para_endpoint` | `(*, item_proceso_id: str, producto_id: str, usuario_id: str) -> ResultadoMatchingItem` | `214-225` | Wrapper que resuelve `get_service_client()` y delega en `confirmar_matching`; es lo único de este par que importa `router.py`. |
| `marcar_sin_match_para_endpoint` | `(*, item_proceso_id: str) -> ResultadoMatchingItem` | `228-229` | Wrapper que resuelve `get_service_client()` y delega en `marcar_sin_match`; es lo único de este par que importa `router.py`. |

## `router.py`

| Endpoint | Función | Línea |
|---|---|---|
| `POST /items/{item_id}/confirmar-matching` | `confirmar_matching_endpoint` | `40-50` |
| `POST /items/{item_id}/sin-match` | `sin_match_endpoint` | `53-60` |
| `GET /matching/pendientes` | `listar_pendientes_endpoint` | `63-69` |

`router = APIRouter()` (`router.py:17`), sin prefijo propio — se monta tal cual en
`main.py:43`. Función privada: `_validar_item_de_la_drogueria` (`router.py:22-37`).

## Constantes de módulo

| Constante | Valor | Línea | Archivo |
|---|---|---|---|
| `_UMBRAL_SUGERIDO` | `Decimal("70")` | `13` | `service.py` |
| `_TOP_K` | `5` | `14` | `service.py` |
| `_ROLES_MATCHING` | `("superadmin", "admin", "gerencia", "lider_comercial", "comercial")` | `19` | `router.py` |
