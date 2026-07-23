# API pública — Extracción-Validación

## `models.py`

```python
DocumentType = Literal["comparativa", "licitacion", "cotizacion", "orden_compra"]

class ValidarExtraccionRequest(BaseModel):
    proceso_comercial_id: str | None = None

class ResultadoValidarExtraccion(BaseModel):
    extraction_id: str
    document_type: DocumentType
    proceso_comercial_id: str
    filas_creadas: int
    comparativa_id: str | None = None
    reemplazo_version_anterior: bool = False
```

(`models.py:1-19`)

## `repository.py`

Acceso a datos puro — sin lógica de negocio, todas reciben `client: Client` como
primer parámetro posicional.

| Función | Firma | Línea |
|---|---|---|
| `buscar_extraction_result` | `(client, *, extraction_id: str) -> dict \| None` | `6-10` |
| `buscar_proceso_comercial` | `(client, *, proceso_comercial_id: str) -> dict \| None` | `13-21` |
| `actualizar_extraction_result` | `(client, *, extraction_id: str, campos: dict) -> dict` | `24-33` |
| `insertar_items_proceso` | `(client, filas: list[dict]) -> list[dict]` | `36-39` |
| `listar_items_proceso_por_proceso` | `(client, *, proceso_comercial_id: str) -> list[dict]` | `42-51` |
| `buscar_comparativa_vigente` | `(client, *, proceso_comercial_id: str) -> dict \| None` | `54-65` |
| `invalidar_comparativa` | `(client, *, comparativa_id: str) -> None` | `68-69` |
| `crear_comparativa` | `(client, fila: dict) -> dict` | `72-73` |
| `insertar_ofertas_items` | `(client, filas: list[dict]) -> list[dict]` | `76-79` |
| `actualizar_oferta_item` | `(client, *, oferta_item_id: str, campos: dict) -> None` | `82-85` |
| `listar_usuarios_por_rol` | `(client, *, drogueria_id: str, roles: tuple[str, ...]) -> list[dict]` | `88-98` |
| `crear_notificacion` | `(client, fila: dict) -> None` | `101-102` |

## `service.py`

Funciones privadas (prefijo `_`, no se importan desde otros módulos):

| Función | Firma | Línea |
|---|---|---|
| `_leer_filas_csv` | `(csv_disk_path: str) -> list[dict[str, str]]` | `24-26` |
| `_resolver_proceso_comercial_id` | `(client, *, extraction: dict, proceso_comercial_id: str \| None) -> str` | `29-58` |
| `_materializar_licitacion` | `(client, *, extraction, proceso_comercial_id, drogueria_id, cliente_id) -> int` | `61-93` |
| `_computar_posiciones` | `(filas: list[dict]) -> list[tuple[str, int, bool]]` | `96-109` |
| `_notificar_reemplazo_comparativa` | `(client, *, drogueria_id, proceso_comercial_id, comparativa_id) -> None` | `112-134` |
| `_materializar_comparativa` | `(client, *, extraction, proceso_comercial_id, drogueria_id, usuario_id) -> tuple[str, int, bool]` | `137-241` |

Funciones públicas:

| Función | Firma | Línea | Uso |
|---|---|---|---|
| `validar_extraccion` | `(client: Client, *, extraction_id: str, usuario_id: str, proceso_comercial_id: str \| None) -> ResultadoValidarExtraccion` | `244-305` | Caso de uso completo; recibe el cliente como parámetro — es la función que llaman los tests de integración directamente. |
| `validar_extraccion_para_endpoint` | `(*, extraction_id: str, usuario_id: str, proceso_comercial_id: str \| None) -> ResultadoValidarExtraccion` | `308-319` | Wrapper que resuelve `get_service_client()` y delega en `validar_extraccion`; es lo único que importa `router.py`. |

## `router.py`

| Endpoint | Función | Línea |
|---|---|---|
| `POST /extracciones/{extraction_id}/validar` | `validar_extraccion_endpoint` | `15-40` |

`router = APIRouter()` (`router.py:10`), sin prefijo propio — se monta tal cual en
`main.py:45`.

## Constantes de módulo

| Constante | Valor | Línea | Archivo |
|---|---|---|---|
| `_TIPOS_ITEMS_PROCESO` | `{"licitacion", "cotizacion"}` | `19` | `service.py` |
| `_ROLES_NOTIFICACION_REEMPLAZO` | `("admin", "gerencia", "lider_comercial")` | `21` | `service.py` |
| `_ROLES_VALIDAR` | `("admin", "gerencia", "lider_comercial", "comercial")` | `12` | `router.py` |
