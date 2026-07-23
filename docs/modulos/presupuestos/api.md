# API pública — Presupuestos

Firmas verificadas contra el código real en esta sesión.

## `presupuestos/models.py`

```python
EstadoPresupuesto = Literal[
    "generado", "en_revision", "aprobado", "presentado", "adjudicado", "rechazado", "vencido"
]
# models.py:6-8
# Solo 3 de los 7 valores son alcanzables por código en este repositorio — ver estados.md.

class AjustarItemRequest(BaseModel):
    precio_unitario: Decimal | None = None
    cantidad_ofertada: Decimal | None = None
    excluido: bool | None = None
    motivo_exclusion: str | None = None
# models.py:11-15
# Body de PATCH /presupuesto-items/{item_id}. Los 4 campos son opcionales;
# ajustar_item exige que al menos uno no sea None (RN-PRESUPUESTOS-010).

class ResultadoPresupuestoItem(BaseModel):
    id: str
    precio_unitario: Decimal | None
    cantidad_ofertada: Decimal | None
    monto_total: Decimal | None
    metodo_precio: str | None
    margen_resultante_pct: Decimal | None
    precio_original_motor: Decimal | None
    excluido: bool
    motivo_exclusion: str | None
# models.py:18-27
# Declarado pero no usado como response_model de ningún endpoint — ver pendientes.md.

class ResultadoPresupuesto(BaseModel):
    presupuesto_id: str
    estado: EstadoPresupuesto
    monto_total: Decimal | None
    cantidad_items: int
    items_sin_precio: int
# models.py:30-35
# response_model de aprobar_endpoint y presentar_endpoint.
```

## `presupuestos/repository.py`

Capa delgada de acceso a datos. Todas las funciones reciben `client: Client`
explícito.

```python
def buscar_presupuesto(client: Client, *, presupuesto_id: str) -> dict[str, Any] | None: ...
# repository.py:6-15
# presupuestos WHERE id=? AND deleted_at IS NULL LIMIT 1.

def buscar_proceso_comercial(client: Client, *, proceso_comercial_id: str) -> dict[str, Any] | None: ...
# repository.py:18-26
# SELECT id, drogueria_id, clase, estado FROM procesos_comerciales WHERE id=? LIMIT 1.
# Único select de todo el repositorio que trae `estado` de procesos_comerciales.

def listar_items_presupuesto(client: Client, *, presupuesto_id: str) -> list[dict[str, Any]]: ...
# repository.py:29-36
# presupuesto_items WHERE presupuesto_id=? -- sin filtro de excluido, todos los ítems.

def buscar_presupuesto_item(client: Client, *, presupuesto_item_id: str) -> dict[str, Any] | None: ...
# repository.py:39-47
# presupuesto_items WHERE id=? LIMIT 1.

def actualizar_presupuesto_item(
    client: Client, *, presupuesto_item_id: str, campos: dict[str, Any]
) -> dict[str, Any]: ...
# repository.py:50-59
# UPDATE presupuesto_items SET ... WHERE id=?. Genérico, sin lógica de negocio propia.

def actualizar_presupuesto(
    client: Client, *, presupuesto_id: str, campos: dict[str, Any]
) -> dict[str, Any]: ...
# repository.py:62-65
# UPDATE presupuestos SET ... WHERE id=?. Genérico.

def actualizar_proceso_comercial(
    client: Client, *, proceso_comercial_id: str, campos: dict[str, Any]
) -> None: ...
# repository.py:68-71
# UPDATE procesos_comerciales SET ... WHERE id=?. Único UPDATE de esa tabla en
# todo el repositorio. Sin condición sobre el estado anterior.

def listar_presupuesto_comercial(client: Client, *, presupuesto_id: str) -> list[dict[str, Any]]: ...
# repository.py:74-81
# v_presupuesto_comercial WHERE presupuesto_id=?. Sin costo (RN-PRESUPUESTOS-013).

def listar_presupuesto_revision(client: Client, *, presupuesto_id: str) -> list[dict[str, Any]]: ...
# repository.py:84-91
# v_presupuesto_revision WHERE presupuesto_id=?. Con costo y alerta_mantenimiento.
```

## `presupuestos/service.py`

```python
_DOS_DECIMALES = Decimal("0.01")
_ESTADOS_APROBABLES = ("generado", "en_revision")
# service.py:15-16

def _q(valor: Decimal) -> Decimal: ...
# service.py:19-20
# Redondeo ROUND_HALF_UP a 2 decimales -- mismo criterio que pricing._q.

def _decimal_o_none(valor: Any) -> Decimal | None: ...
# service.py:23-24

def _es_item_no_resuelto(item: dict[str, Any]) -> bool: ...
# service.py:27-28
# item["metodo_precio"] == "sin_precio" and not item["excluido"] -- RN-PRESUPUESTOS-002.

def _resultado(presupuesto: dict[str, Any]) -> ResultadoPresupuesto: ...
# service.py:31-38
# Mapea una fila de `presupuestos` a ResultadoPresupuesto.

def _recalcular_totales_presupuesto(
    client: Client, *, presupuesto: dict[str, Any], usuario_id: str
) -> dict[str, Any]: ...
# service.py:41-88
# RN-PRESUPUESTOS-011/012. Excluye ítems excluido=True; solo escribe/audita si
# monto_total o items_sin_precio cambiaron realmente. Devuelve el presupuesto
# (actualizado o el mismo recibido, sin tocar, si no hubo cambio).

def aprobar_presupuesto(
    client: Client, *, presupuesto_id: str, usuario_id: str
) -> ResultadoPresupuesto: ...
# service.py:91-128
# RN-PRESUPUESTOS-001/002. NotFoundError si no existe, ConflictError si el
# estado no es aprobable, ValidationError si hay ítems sin_precio sin resolver.

def ajustar_item(
    client: Client,
    *,
    presupuesto_item_id: str,
    precio_unitario: Decimal | None,
    cantidad_ofertada: Decimal | None,
    excluido: bool | None,
    motivo_exclusion: str | None,
    usuario_id: str,
) -> dict[str, Any]: ...
# service.py:131-177
# RN-PRESUPUESTOS-008/009/010/011/012. Dispara _recalcular_totales_presupuesto
# al final si el presupuesto padre existe. Sin guarda de estado del presupuesto.

def presentar_presupuesto(
    client: Client, *, presupuesto_id: str, usuario_id: str
) -> ResultadoPresupuesto: ...
# service.py:180-255
# RN-PRESUPUESTOS-003/004/005/006/007. La función más compleja del módulo --
# compromete stock condicionalmente (clase == "cotizacion"), revierte todo ante
# fallo parcial, y transiciona procesos_comerciales.estado como efecto colateral.

def aprobar_presupuesto_para_endpoint(*, presupuesto_id: str, usuario_id: str) -> ResultadoPresupuesto: ...
# service.py:258-261
# RN-PRESUPUESTOS-014. service_role -- RLS de presupuestos no incluye superadmin en UPDATE.

def ajustar_item_para_endpoint(
    *,
    presupuesto_item_id: str,
    precio_unitario: Decimal | None,
    cantidad_ofertada: Decimal | None,
    excluido: bool | None,
    motivo_exclusion: str | None,
    usuario_id: str,
) -> dict[str, Any]: ...
# service.py:264-281
# RN-PRESUPUESTOS-014. Mismo motivo de service_role que aprobar.

def presentar_presupuesto_para_endpoint(*, presupuesto_id: str, usuario_id: str) -> ResultadoPresupuesto: ...
# service.py:284-290
# RN-PRESUPUESTOS-015. service_role -- además de presupuestos, comprometer
# stock exige permisos que ni superadmin tiene por RLS sobre stock_productos.
```

A diferencia de [`../pricing/`](../pricing/) (que solo tiene un par
función/`_para_endpoint`, para `generar_presupuesto`), este módulo repite el
patrón función pura + wrapper `_para_endpoint` en las 3 funciones de negocio,
de forma consistente con [`../catalogo/`](../catalogo/).

## `presupuestos/router.py`

```python
router = APIRouter()
# router.py:15

_ROLES_APROBAR = ("superadmin", "admin", "gerencia", "lider_comercial")
_ROLES_AJUSTAR = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial")
_ROLES_PRESENTAR = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial")
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial")
_ROLES_VEN_COSTO = ("superadmin", "admin", "gerencia")
# router.py:17-21

def _validar_presupuesto_de_la_drogueria(
    user_client: Client, usuario: UsuarioPerfil, presupuesto_id: str
) -> None: ...
# router.py:24-39
# NotFoundError si no existe bajo RLS; ForbiddenError si es de otra droguería (salvo superadmin).

def _validar_item_de_la_drogueria(
    user_client: Client, usuario: UsuarioPerfil, presupuesto_item_id: str
) -> None: ...
# router.py:42-57
# Igual, pero sobre presupuesto_items.
```

| Método | Path | Request | Response | Roles requeridos | Archivo |
|---|---|---|---|---|---|
| GET | `/presupuestos/{presupuesto_id}` | — (path param) | `list[dict]` (sin modelo tipado) | `_ROLES_LECTURA` | `router.py:60-76` |
| POST | `/presupuestos/{presupuesto_id}/aprobar` | — (path param) | `ResultadoPresupuesto` | `_ROLES_APROBAR` | `router.py:79-86` |
| POST | `/presupuestos/{presupuesto_id}/presentar` | — (path param) | `ResultadoPresupuesto` | `_ROLES_PRESENTAR` | `router.py:89-96` |
| PATCH | `/presupuesto-items/{item_id}` | `AjustarItemRequest` | `dict` (sin modelo tipado) | `_ROLES_AJUSTAR` | `router.py:99-114` |

Excepciones de dominio levantadas por este módulo y su status HTTP (mapeo
centralizado en `core/exceptions.py`, ver [`../core/api.md`](../core/api.md)):
`NotFoundError`→404, `ForbiddenError`→403 (router, validación de tenant),
`ConflictError`→409 (guardas de transición de estado, RN-PRESUPUESTOS-001/003,
y fallo de stock, RN-PRESUPUESTOS-006), `ValidationError`→422
(RN-PRESUPUESTOS-002/010).
