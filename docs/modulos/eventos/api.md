# API pública — Eventos

Firmas verificadas contra el código real en esta sesión.

## `eventos/models.py`

```python
TipoEvento = Literal[
    "compra", "recepcion", "entrega", "seguimiento", "reclamo", "facturacion", "pago",
    "llamada", "reunion", "recordatorio", "vencimiento", "observacion", "otro",
]
EstadoEvento = Literal["pendiente", "bloqueado", "en_progreso", "completado", "cancelado", "vencido"]
Prioridad = Literal["baja", "media", "alta", "urgente"]
OrigenEvento = Literal["usuario", "ia", "sistema", "automatico"]
# models.py:6-12

class EventoCreate(BaseModel):
    tipo: TipoEvento
    titulo: str
    descripcion: str | None = None
    prioridad: Prioridad = "media"
    proceso_comercial_id: str | None = None
    comparativa_id: str | None = None
    orden_compra_id: str | None = None
    cliente_id: str | None = None
    proveedor_id: str | None = None
    responsable_id: str | None = None
    depende_de_id: str | None = None
    fecha_programada: datetime | None = None
    fecha_limite: datetime | None = None
    metadata: dict | None = None
# models.py:15-29

class EventoUpdate(BaseModel):
    titulo: str | None = None
    descripcion: str | None = None
    prioridad: Prioridad | None = None
    responsable_id: str | None = None
    fecha_programada: datetime | None = None
    fecha_limite: datetime | None = None
    estado: Literal["cancelado"] | None = None
    metadata: dict | None = None
# models.py:32-40
# estado solo admite "cancelado" (RN-EVENTOS-007); no puede reasignarse titulo/
# proceso_comercial_id/tipo/etc. distinto del set declarado acá.

class EventoOut(BaseModel):
    id: str
    drogueria_id: str
    tipo: str
    titulo: str
    descripcion: str | None
    estado: str
    prioridad: str
    origen: str
    proceso_comercial_id: str | None
    comparativa_id: str | None
    orden_compra_id: str | None
    cliente_id: str | None
    proveedor_id: str | None
    responsable_id: str | None
    depende_de_id: str | None
    evento_recurrente_id: str | None
    fecha_programada: datetime | None
    fecha_limite: datetime | None
    fecha_real: datetime | None
    metadata: dict | None
# models.py:43-63
# No expone created_by/updated_by/deleted_at/deleted_by/created_at/updated_at/
# regla_automatizacion_id, aunque existan como columnas en la tabla (ver base_de_datos.md).

class EventoBloqueoOut(BaseModel):
    evento_id: str
    drogueria_id: str
    tipo: str
    titulo: str
    estado: str
    prioridad: str
    fecha_limite: datetime | None
    responsable_id: str | None
    depende_de_id: str | None
    depende_de: str | None
    estado_dependencia: str | None
    puede_avanzar: bool
# models.py:66-78
# Payload de GET /eventos/{id}/bloqueo, espejo de v_eventos_bloqueo.

class CalendarioItem(BaseModel):
    evento_id: str
    drogueria_id: str
    tipo: str
    titulo: str
    estado: str
    prioridad: str
    origen: str
    proceso_comercial_id: str | None
    cliente_id: str | None
    cliente: str | None
    responsable_id: str | None
    responsable: str | None
    fecha_programada: datetime | None
    fecha_limite: datetime | None
    fecha_real: datetime | None
    vencido: bool
# models.py:81-97
# Payload de GET /calendario, espejo de v_calendario. "vencido" es el único campo
# booleano de estado de todo el módulo (ver estados.md) -- distinto de EstadoEvento.

class EventoRecurrenteCreate(BaseModel):
    tipo: TipoEvento
    titulo: str
    descripcion: str | None = None
    prioridad: Prioridad = "media"
    responsable_id: str | None = None
    cliente_id: str | None = None
    proveedor_id: str | None = None
    metadata: dict | None = None
    rrule: str
    fecha_inicio: date
    fecha_fin: date | None = None
# models.py:100-111

class EventoRecurrenteUpdate(BaseModel):
    titulo: str | None = None
    descripcion: str | None = None
    prioridad: Prioridad | None = None
    responsable_id: str | None = None
    rrule: str | None = None
    fecha_fin: date | None = None
    activa: bool | None = None
# models.py:114-121

class EventoRecurrenteOut(BaseModel):
    id: str
    drogueria_id: str
    tipo: str
    titulo: str
    descripcion: str | None
    prioridad: str
    responsable_id: str | None
    cliente_id: str | None
    proveedor_id: str | None
    rrule: str
    fecha_inicio: date
    fecha_fin: date | None
    proxima_ejecucion: datetime | None
    ultima_generacion: datetime | None
    instancias_generadas: int
    activa: bool
# models.py:124-140
```

## `eventos/repository.py`

Capa delgada de acceso a datos, sin lógica de negocio. Todas las funciones reciben
`client: Client` explícito, sin resolverlo internamente.

```python
# -- eventos ------------------------------------------------------------------
def crear_evento(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...            # :8-9
def obtener_evento(client: Client, *, evento_id: str) -> dict[str, Any] | None: ...       # :12-21, filtra deleted_at IS NULL
def listar_eventos(client, *, drogueria_id, estado=None, proceso_comercial_id=None, responsable_id=None) -> list[dict]: ...  # :24-39, ORDER BY fecha_limite
def actualizar_evento(client: Client, *, evento_id: str, campos: dict[str, Any]) -> dict[str, Any]: ...  # :42-43
def soft_delete_evento(client: Client, *, evento_id: str, usuario_id: str) -> None: ...   # :46-49
def listar_bloqueados_por_dependencia(client: Client, *, depende_de_id: str) -> list[dict[str, Any]]: ...  # :52-60, SELECT id WHERE depende_de_id=? AND estado='bloqueado'
def bloqueo_de_evento(client: Client, *, evento_id: str) -> dict[str, Any] | None: ...    # :63-67, sobre v_eventos_bloqueo
def calendario(client, *, drogueria_id, desde=None, hasta=None) -> list[dict[str, Any]]: ...  # :70-78, sobre v_calendario, ORDER BY fecha_programada

# -- eventos_recurrentes --------------------------------------------------------
def crear_evento_recurrente(client: Client, fila: dict[str, Any]) -> dict[str, Any]: ...  # :83-84
def obtener_evento_recurrente(client: Client, *, evento_recurrente_id: str) -> dict[str, Any] | None: ...  # :87-95, NO filtra deleted_at
def listar_eventos_recurrentes(client, *, drogueria_id, activa=None) -> list[dict[str, Any]]: ...  # :98-104, ORDER BY titulo
def actualizar_evento_recurrente(client, *, evento_recurrente_id, campos) -> dict[str, Any]: ...  # :107-116
def listar_recurrentes_a_ejecutar(client: Client) -> list[dict[str, Any]]: ...  # :119-128, SIN filtro de drogueria_id -- activa=True AND proxima_ejecucion <= now()
```

## `eventos/service.py`

```python
_ORIGEN_EVENTO_A_ORIGEN_CAMBIO: dict[OrigenEvento, str] = {...}  # :24-29, RN-EVENTOS-004

# -- eventos ------------------------------------------------------------------
def crear_evento(client, *, drogueria_id, body: EventoCreate, usuario_id, origen: OrigenEvento = "usuario") -> dict: ...  # :33-82, RN-EVENTOS-001 + RN-EVENTOS-004
def obtener_evento(client, *, evento_id, drogueria_id) -> dict: ...  # :85-89, NotFoundError si no existe o es de otro tenant
def listar_eventos(client, *, drogueria_id, estado=None, proceso_comercial_id=None, responsable_id=None) -> list[dict]: ...  # :92-106, passthrough
def actualizar_evento(client, *, evento_id, drogueria_id, body: EventoUpdate, usuario_id) -> dict: ...  # :109-138, diff real + auditoría condicional
def completar_evento(client, *, evento_id, drogueria_id, usuario_id) -> dict: ...  # :141-183, RN-EVENTOS-002, sin guarda de estado_anterior
def eliminar_evento(client, *, evento_id, drogueria_id, usuario_id) -> None: ...  # :186-197, soft delete + auditoría de ciclo de vida
def obtener_bloqueo(client, *, evento_id, drogueria_id) -> dict: ...  # :200-205
def calendario(client, *, drogueria_id, desde=None, hasta=None) -> list[dict]: ...  # :208-211, passthrough

def crear_evento_para_endpoint(*, drogueria_id, body, usuario_id) -> dict: ...  # :214-215, resuelve get_service_client()
def actualizar_evento_para_endpoint(*, evento_id, drogueria_id, body, usuario_id) -> dict: ...  # :218-223
def completar_evento_para_endpoint(*, evento_id, drogueria_id, usuario_id) -> dict: ...  # :226-229
def eliminar_evento_para_endpoint(*, evento_id, drogueria_id, usuario_id) -> None: ...  # :232-233

# -- eventos_recurrentes -------------------------------------------------------
def crear_evento_recurrente(client, *, drogueria_id, body: EventoRecurrenteCreate, usuario_id) -> dict: ...  # :238-266, RN-EVENTOS-003 (valida RRULE)
def listar_eventos_recurrentes(client, *, drogueria_id, activa=None) -> list[dict]: ...  # :269-272, passthrough
def actualizar_evento_recurrente(client, *, evento_recurrente_id, drogueria_id, body, usuario_id) -> dict: ...  # :275-293, NotFoundError si no existe/otro tenant

def crear_evento_recurrente_para_endpoint(*, drogueria_id, body, usuario_id) -> dict: ...  # :296-301
def actualizar_evento_recurrente_para_endpoint(*, evento_recurrente_id, drogueria_id, body, usuario_id) -> dict: ...  # :304-313

def generar_instancias_recurrentes(client: Client, *, usuario_scheduler_id: str) -> int: ...  # :316-378, RN-EVENTOS-003, RN-EVENTOS-006 (sin disparador real)
```

## `eventos/router.py`

```python
router = APIRouter()  # :30
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")   # :32
_ROLES_ESCRITURA = ("admin", "gerencia", "lider_comercial", "comercial", "compras")                # :33
```

Ver [`casos_de_uso.md`](./casos_de_uso.md) para la tabla completa de los 11 endpoints
con método, path, roles, request/response y línea exacta — no se repite acá para evitar
duplicación.

Excepciones de dominio levantadas por este módulo (mapeo centralizado en
`core/exceptions.py`, ver [`../core/api.md`](../core/api.md)):

| Excepción | Status | Dónde |
|---|---|---|
| `ValidationError` | 422 | `crear_evento` (dependencia inexistente, RN-EVENTOS-001); `crear_evento_recurrente` (`RRULE` inválida, RN-EVENTOS-003) |
| `NotFoundError` | 404 | `obtener_evento` (evento inexistente o de otro tenant); `obtener_bloqueo` (idem, vía `obtener_evento`); `actualizar_evento_recurrente` (plantilla inexistente o de otro tenant) |
