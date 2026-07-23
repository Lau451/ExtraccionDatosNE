# API pública por archivo — Automatizaciones

Firmas transcriptas literalmente del código leído en esta sesión. `*` marca parámetros
solo-por-nombre (keyword-only).

## `models.py`

```python
EntidadObjetivo = Literal["proceso_comercial", "comparativa", "orden_compra",
                           "presupuesto", "evento", "extraction_result", "entrega"]
TipoAccion = Literal["crear_evento", "crear_oc", "enviar_notificacion", "enviar_email",
                      "enviar_whatsapp", "ejecutar_agente_ia", "cambiar_estado", "webhook"]
ModoEjecucion = Literal["inmediato", "cola"]

class ReglaAutomatizacionCreate(BaseModel):
    nombre: str
    descripcion: str | None = None
    evento_disparador: str
    entidad_objetivo: EntidadObjetivo
    condicion: dict | None = None
    tipo_accion: TipoAccion
    parametros_accion: dict | None = None
    modo_ejecucion: ModoEjecucion = "cola"
    max_reintentos: int = 3
    prioridad: int = 0

class ReglaAutomatizacionUpdate(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    condicion: dict | None = None
    parametros_accion: dict | None = None
    modo_ejecucion: ModoEjecucion | None = None
    max_reintentos: int | None = None
    prioridad: int | None = None
    activa: bool | None = None

class ReglaAutomatizacionOut(BaseModel):
    id: str
    drogueria_id: str
    nombre: str
    descripcion: str | None
    evento_disparador: str
    entidad_objetivo: str
    condicion: dict | None
    tipo_accion: str
    parametros_accion: dict | None
    modo_ejecucion: str
    max_reintentos: int
    prioridad: int
    activa: bool

class MetricaAutomatizacionOut(BaseModel):
    regla_id: str
    drogueria_id: str
    nombre: str
    tipo_accion: str
    modo_ejecucion: str
    ejecuciones: int
    exitosas: int
    fallidas: int
    duracion_promedio_ms: float | None
    duracion_max_ms: int | None
    intentos_promedio: float | None
    ultima_ejecucion: datetime | None
```

Nota: `ReglaAutomatizacionCreate.evento_disparador` es `str` libre (sin `Literal`), a
diferencia de `entidad_objetivo` y `tipo_accion`, que sí son `Literal` cerrados
reflejando los `CHECK` de BD. `ReglaAutomatizacionUpdate` **no incluye**
`evento_disparador`, `entidad_objetivo` ni `tipo_accion` como editables — solo
`nombre`, `descripcion`, `condicion`, `parametros_accion`, `modo_ejecucion`,
`max_reintentos`, `prioridad` y `activa`. Cambiar el disparador o el tipo de acción de
una regla existente requiere borrarla y recrearla (y no hay `DELETE`, ver
[`casos_de_uso.md`](./casos_de_uso.md)).

## `repository.py`

```python
COLUMNA_FK_POR_ENTIDAD: dict[str, str]   # 5 entradas, ver base_de_datos.md

def crear_regla(client: Client, fila: dict[str, Any]) -> dict[str, Any]
def obtener_regla(client: Client, *, regla_id: str) -> dict[str, Any] | None
def listar_reglas(client: Client, *, drogueria_id: str, activa: bool | None = None) -> list[dict[str, Any]]
def actualizar_regla(client: Client, *, regla_id: str, campos: dict[str, Any]) -> dict[str, Any]
def reglas_activas_para(client: Client, *, drogueria_id: str, entidad_objetivo: str, evento_disparador: str) -> list[dict[str, Any]]
def crear_accion_ejecutada(client: Client, fila: dict[str, Any]) -> dict[str, Any]
def actualizar_accion_ejecutada(client: Client, *, accion_id: str, campos: dict[str, Any]) -> dict[str, Any]
def listar_acciones_pendientes(client: Client) -> list[dict[str, Any]]   # sin drogueria_id
def metricas(client: Client, *, drogueria_id: str) -> list[dict[str, Any]]
```

## `service.py`

```python
# CRUD de reglas
def crear_regla(client: Client, *, drogueria_id: str, body: ReglaAutomatizacionCreate, usuario_id: str) -> dict[str, Any]
def listar_reglas(client: Client, *, drogueria_id: str, activa: bool | None = None) -> list[dict[str, Any]]
def actualizar_regla(client: Client, *, regla_id: str, drogueria_id: str, body: ReglaAutomatizacionUpdate, usuario_id: str) -> dict[str, Any]
def metricas(client: Client, *, drogueria_id: str) -> list[dict[str, Any]]

# Wrappers para el router (resuelven get_service_client() internamente)
def crear_regla_para_endpoint(*, drogueria_id: str, body: ReglaAutomatizacionCreate, usuario_id: str) -> dict[str, Any]
def actualizar_regla_para_endpoint(*, regla_id: str, drogueria_id: str, body: ReglaAutomatizacionUpdate, usuario_id: str) -> dict[str, Any]

# Motor (privado)
def _evaluar_condicion(condicion: dict | None, datos: dict[str, Any]) -> bool
def _ejecutar_accion(client: Client, *, regla: dict[str, Any], entidad_objetivo: str, entidad_id: str, drogueria_id: str, usuario_id: str) -> tuple[bool, Any]

# Motor (público, SIN caller en producción -- RN-AUTOMATIZACIONES-006)
def disparar_reglas(client: Client, *, drogueria_id: str, entidad_objetivo: str, evento_disparador: str, entidad_id: str, datos: dict[str, Any], usuario_id: str) -> list[dict[str, Any]]
def procesar_acciones_pendientes(client: Client, *, usuario_scheduler_id: str) -> int
```

Constante sin uso: `_ACCIONES_INMEDIATAS_SOPORTADAS = {"crear_evento",
"enviar_notificacion"}` (`:20`) — declarada, nunca referenciada. Ver
[`decisiones.md`](./decisiones.md).

`listar_reglas` y `metricas` de `service.py` son wrappers de una línea que solo
reexportan la función homónima de `repository.py` sin transformación — no tienen
wrapper `_para_endpoint` porque ambas se llaman siempre con `user_client` desde el
router (`router.py:30`, `:53`).

## `router.py`

```python
router = APIRouter()
_ROLES = ("admin", "gerencia")

@router.get("/automatizaciones/reglas", response_model=list[ReglaAutomatizacionOut])
def listar_reglas_endpoint(activa: bool | None = None, usuario=Depends(require_roles(*_ROLES)), user_client=Depends(get_user_client)) -> list[ReglaAutomatizacionOut]

@router.post("/automatizaciones/reglas", response_model=ReglaAutomatizacionOut)
def crear_regla_endpoint(body: ReglaAutomatizacionCreate, usuario=Depends(require_roles(*_ROLES))) -> ReglaAutomatizacionOut

@router.patch("/automatizaciones/reglas/{regla_id}", response_model=ReglaAutomatizacionOut)
def actualizar_regla_endpoint(regla_id: str, body: ReglaAutomatizacionUpdate, usuario=Depends(require_roles(*_ROLES))) -> ReglaAutomatizacionOut

@router.get("/automatizaciones/metricas", response_model=list[MetricaAutomatizacionOut])
def metricas_endpoint(usuario=Depends(require_roles(*_ROLES)), user_client=Depends(get_user_client)) -> list[MetricaAutomatizacionOut]
```

## `__init__.py`

Vacío — sin superficie pública unificada; cada consumidor importa directamente del
submódulo que necesita (mismo patrón que `core/__init__.py` y `eventos/__init__.py`).
