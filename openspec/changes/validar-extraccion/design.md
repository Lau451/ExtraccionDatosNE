# Design: Validar extracción

**Change:** validar-extraccion · **Fase:** sdd-design · **Fecha:** 2026-07-25
**Entrada:** `proposal.md` (D1–D7 ya decididos), `exploration.md`.
Este documento es el **cómo**: shapes exactos, orden de operaciones, semántica de errores y
límites transaccionales. No re-decide D1–D7 — sí **corrige tres puntos donde D6 es incompatible
con el schema o con el código que ya existe** (ver §6).

---

## 1. Enfoque técnico

El backend de `validar` ya existe y está probado. El cambio es **aditivo por diseño**: un campo
opcional en el request, dos endpoints de lectura, y un fix de infra. La regla que gobierna todo el
diseño backend es una sola:

> **El override de filas del body tiene exactamente la misma forma que las filas del CSV.**

Con eso, el bucle de materialización **no cambia** — cambia únicamente de dónde salen las filas.
Los 12 tests existentes pasan sin tocarse porque el camino sin `filas` es literalmente el mismo
código.

```
Frontend (features/validar-extraccion/)
   │
   │ GET /extracciones?validado=false        ── listado de pendientes
   │ GET /extracciones/{id}/filas            ── filas parseadas del CSV (read-only mount)
   │ POST /extracciones/{id}/validar {filas} ── edición + confirmación, 1 request
   ▼
router.py  ── require_roles + chequeo de pertenencia (user_client / RLS)
   ▼
service.py ── validar_extraccion()
   │   1. buscar extracción          (lectura)
   │   2. conflict si validado       (lectura)
   │   3. VALIDAR `filas`            (puro, SIN tocar la DB)   ← nuevo, antes de todo write
   │   4. resolver proceso_comercial (primer write)
   │   5. materializar               (filas = body ?? CSV)
   │   6. flip validado = TRUE       (último write)
   │   7. notificar reemplazo        (fire-and-forget, fuera de la ruta crítica)
   ▼
repository.py ── PostgREST (service_client)
```

---

## 2. D2 — Shape exacto del request extendido

### 2.1 `services/presupuestacion/extraccion/models.py` (diff)

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

DocumentType = Literal["comparativa", "licitacion", "cotizacion", "orden_compra"]

MAX_FILAS_EDITABLES = 500          # D7 — mismo valor que frontend/constants.ts


class FilaLicitacionIn(BaseModel):
    """Mismos nombres de columna que el CSV de licitación/cotización."""
    model_config = ConfigDict(extra="forbid")
    item: str
    descripcion: str
    cantidad: str


class FilaComparativaIn(BaseModel):
    """Mismos nombres de columna que el CSV de comparativa."""
    model_config = ConfigDict(extra="forbid")
    renglon: str
    proveedor: str
    marca: str | None = None
    precio: str


class ValidarExtraccionRequest(BaseModel):
    proceso_comercial_id: str | None = None
    # None  -> materializa desde el CSV (comportamiento actual, retrocompatible)
    # lista -> materializa desde acá; el CSV en disco NO se toca (D2)
    filas: list[FilaLicitacionIn] | list[FilaComparativaIn] | None = Field(default=None)
```

**Decisión — unión de listas, no lista de uniones.** `list[A] | list[B]` obliga a que **toda** la
lista matchee una sola rama. Una lista mezclada (fila 1 con forma de licitación, fila 2 con forma
de comparativa) falla las dos ramas y devuelve 422. Si se hubiera modelado como
`list[FilaLicitacionIn | FilaComparativaIn]`, una lista mezclada sería válida y materializaría
basura. Rechazado.

**Decisión — `extra="forbid"`.** Sin esto, una fila que trae *ambos* sets de campos matchea la
primera rama en silencio y descarta los campos de la otra. Con `forbid`, se rechaza.

**Decisión — todo `str`, no `Decimal`/`int`.** Las columnas del CSV son strings y el parseo real
lo hace Postgres al insertar (`cantidad`, `precio_unitario` son `NUMERIC`). Tipar acá como
`Decimal` cambiaría el shape que consume el bucle y rompería la equivalencia con el CSV. El
chequeo numérico se hace en §3, con mensajes de dominio en vez de errores de pydantic.

**Decisión — `row_count` no se toca.** Confirmado con el schema: `extraction_results.row_count`
describe cuántas filas devolvió la IA. `ResultadoValidarExtraccion.filas_creadas` reporta cuántas
confirmó el humano. La diferencia es la señal de calidad (D2).

### 2.2 El bucle de materialización

Se agrega **una** función y se cambia **una** línea por materializador:

```python
def _filas_a_materializar(
    extraction: dict[str, Any], filas_override: list[dict[str, str]] | None
) -> list[dict[str, str]]:
    """Origen único de las filas. El CSV en disco nunca se reescribe (D2)."""
    if filas_override is not None:
        return filas_override
    return _leer_filas_csv(extraction["csv_disk_path"])
```

```diff
 def _materializar_licitacion(
-    client, *, extraction, proceso_comercial_id, drogueria_id, cliente_id,
+    client, *, extraction, proceso_comercial_id, drogueria_id, cliente_id,
+    filas_override: list[dict[str, str]] | None,
 ) -> int:
-    filas_csv = _leer_filas_csv(extraction["csv_disk_path"])
+    filas_csv = _filas_a_materializar(extraction, filas_override)

     filas_items = []
     for fila in filas_csv:
         descripcion = fila["descripcion"].strip()
         ...  # ← sin cambios: fila["item"], fila["cantidad"] ya existen en el override
```

Idéntico en `_materializar_comparativa` (`fila["renglon"]`, `fila["proveedor"]`,
`fila.get("marca")`, `fila["precio"]`). El override entra como
`[f.model_dump() for f in body.filas]`, así que `.get("marca")` sigue funcionando (devuelve `None`,
que la línea `(fila.get("marca") or "").strip() or None` ya contempla).

**Por qué esto importa:** el bucle, el cálculo de `proveedores`/`renglones`, `_computar_posiciones`,
el versionado y el matching quedan **byte-idénticos**. El riesgo de regresión sobre los 12 tests
es estructuralmente cero, no "bajo".

---

## 3. Validación del payload — antes de cualquier write

Corre en `validar_extraccion()` **después** del chequeo de `validado` y **antes** de
`_resolver_proceso_comercial_id()`. Ese orden no es cosmético: `_resolver_proceso_comercial_id`
hace el **primer write** de la operación (`actualizar_extraction_result({proceso_comercial_id})`).
Validar después dejaría la extracción vinculada a un proceso tras un 422.

```python
def _validar_filas_override(
    filas: list[dict[str, str]] | None, *, document_type: str
) -> None:
    if filas is None:
        return
    if not filas:
        raise ValidationError("La lista de filas no puede estar vacía")
    if len(filas) > MAX_FILAS_EDITABLES:
        raise ValidationError(
            f"No se pueden editar más de {MAX_FILAS_EDITABLES} filas en una validación "
            f"(recibidas {len(filas)})"
        )

    es_comparativa = document_type == "comparativa"
    esperado = "comparativa" if es_comparativa else "licitación/cotización"
    if es_comparativa != ("renglon" in filas[0]):
        raise ValidationError(
            f"Las filas enviadas no corresponden a un documento de tipo {esperado}"
        )

    errores: list[str] = []
    for numero, fila in enumerate(filas, start=1):
        if es_comparativa:
            _chequear_entero(errores, numero, "renglon", fila["renglon"])
            _chequear_texto(errores, numero, "proveedor", fila["proveedor"])
            _chequear_decimal(errores, numero, "precio", fila["precio"], minimo=0)
        else:
            _chequear_entero(errores, numero, "item", fila["item"])
            _chequear_texto(errores, numero, "descripcion", fila["descripcion"])
            _chequear_decimal(errores, numero, "cantidad", fila["cantidad"], minimo=0)

    if errores:
        detalle = "; ".join(errores[:10])
        extra = f" (y {len(errores) - 10} más)" if len(errores) > 10 else ""
        raise ValidationError(f"Filas con datos inválidos — {detalle}{extra}")
```

| Chequeo | Regla | Motivo |
|---|---|---|
| `item` / `renglon` | entero > 0 | `items_proceso.numero_renglon` es `INTEGER`; hoy un valor no numérico revienta en medio de la materialización |
| `descripcion` / `proveedor` | no vacío tras `.strip()` | columnas `NOT NULL`; una fila vacía es una fila fantasma en el negocio |
| `cantidad` / `precio` | `Decimal` ≥ 0 tras `,`→`.` | mismo normalizado que hace hoy `_materializar_comparativa` con `.replace(",", ".")` |
| largo | 1 ≤ n ≤ 500 | D7 defensivo (§7) |
| coherencia | shape ↔ `document_type` real | pydantic acepta cualquiera de las dos ramas; el tipo real solo se conoce leyendo la extracción |

**Semántica de "la fila 47 de 80 falla":** se recorren **las 80**, se acumulan todos los errores y
se devuelve **un solo 422** con hasta 10 mensajes (`fila 47: 'cantidad' no es un número válido
("12 unidades")`). No hay write parcial porque no hubo ningún write: el bloque completo corre
antes del primer `.update()`. El usuario corrige todo de una vez en vez de descubrir errores de a
uno.

---

## 4. Semántica transaccional — qué garantiza y qué no

**Aclaración honesta y necesaria:** PostgREST no da transacciones entre requests. "Atómico" en D3
significa **una sola request HTTP**, no una sola transacción de Postgres. Eso ya es así hoy.

| Etapa | Statements | Atomicidad real |
|---|---|---|
| Validación de `filas` | 0 | N/A — puro |
| `proceso_comercial_id` | 1 `UPDATE` | atómico |
| `items_proceso` | 1 `INSERT` multi-fila | **atómico**: las 80 filas entran o ninguna |
| `comparativas` + `ofertas_items` + posiciones | 1 + 1 + N `UPDATE` | **no atómico entre sí** |
| `validado = TRUE` | 1 `UPDATE` | último, siempre |

Mitigaciones adoptadas en este change:

1. **Todo lo que puede fallar por datos falla antes del primer write** (§3). El modo de falla
   frecuente — humano tipea mal un precio — deja estado cero.
2. **El flip de `validado` queda último**, como ya está. Una caída a mitad deja `validado=FALSE`
   y la operación es reintentable.
3. **`matching`** corre por ítem después del `INSERT`; un fallo ahí propaga y deja
   `validado=FALSE` con los `items_proceso` ya creados — **limitación preexistente**, no
   introducida acá.

**Fuera de scope, anotado:** mover la materialización a una RPC transaccional de Postgres es la
solución correcta al punto 3 y merece su propio change. Un reintento tras una caída parcial de
comparativa hoy genera una v+1 en vez de duplicar la vigente (el versionado lo absorbe); en
licitación duplicaría `items_proceso`. Se documenta en `docs/modulos/extraccion_validacion/pendientes.md`.

---

## 5. D4 — Volumen compartido, env faltantes y error de dominio

### 5.1 `docker-compose.yml` (diff exacto)

```diff
 services:
   extraccion-api:
     environment:
       - GEMINI_API_KEYS=${GEMINI_API_KEYS}
       - OUTPUT_BASE_DIR=C:/app/output
+      # Sin estas dos, get_client() devuelve None y NINGUNA extracción se persiste
+      # (services/extraccion/supabase_client.py:77-85). Bug vivo hoy en Docker.
+      - SUPABASE_URL=${SUPABASE_URL}
+      - SUPABASE_SERVICE_KEY=${SUPABASE_SERVICE_KEY}
       - PYTHONDONTWRITEBYTECODE=1
+
+    volumes:
+      # Mismo mount path en ambos servicios: csv_disk_path se guarda ABSOLUTO.
+      - extraccion-output:C:/app/output
     restart: always

   presupuestacion-api:
     environment:
       - SUPABASE_URL=${SUPABASE_URL}
       - SUPABASE_ANON_KEY=${SUPABASE_ANON_KEY}
       - SUPABASE_SERVICE_KEY=${SUPABASE_SERVICE_KEY}
       - PYTHONDONTWRITEBYTECODE=1
+
+    volumes:
+      # Read-only: presupuestacion NUNCA escribe en el output del extractor (D2).
+      - extraccion-output:C:/app/output:ro
     restart: always
+
+volumes:
+  extraccion-output:
```

**Corrección al brief:** `SUPABASE_ANON_KEY` **no se agrega** a `extraccion-api`. Verificado por
grep en `services/extraccion/`: solo se consumen `SUPABASE_URL` (`auth.py:45`,
`supabase_client.py:77`) y `SUPABASE_SERVICE_KEY` (`supabase_client.py:79`, con fallback legacy a
`SUPABASE_KEY`). Agregar una variable sin consumidor es ruido que después alguien tiene que
verificar.

### 5.2 Error de dominio en `_leer_filas_csv`

Hoy hay **dos** rutas a 500 con stack trace, no una: `csv_disk_path` es `TEXT NULL` en el schema,
así que `open(None)` tira `TypeError` antes incluso de que exista el problema del volumen.

```python
# core/exceptions.py
class ExtraccionNoDisponibleError(DomainError):
    """El CSV crudo de la extracción no es accesible desde este servicio."""

STATUS_MAP = {
    ...,
    ExtraccionNoDisponibleError: 503,   # el recurso existe; el almacenamiento no responde
}
```

```python
def _leer_filas_csv(csv_disk_path: str | None) -> list[dict[str, str]]:
    if not csv_disk_path:
        raise ExtraccionNoDisponibleError(
            "Esta extracción no tiene archivo de resultados asociado"
        )
    try:
        with open(csv_disk_path, encoding="utf-8", newline="") as archivo:
            return list(csv.DictReader(archivo, delimiter=";"))
    except OSError as exc:
        raise ExtraccionNoDisponibleError(
            "El archivo de la extracción no está disponible — "
            "puede que el volumen compartido no esté montado"
        ) from exc
```

**`OSError`, no `FileNotFoundError`.** `PermissionError` (montaje `:ro` mal configurado) y
`IsADirectoryError` son hermanos de `FileNotFoundError` bajo `OSError` y producen exactamente el
mismo síntoma para el usuario. Capturar solo el hijo dejaba la mitad de los casos en 500.
`register_exception_handlers` itera `STATUS_MAP`, así que registrar el tipo nuevo alcanza.

**Efecto secundario deseado:** cuando el body trae `filas`, `_leer_filas_csv` **no se llama**. Una
validación con edición funciona aunque el volumen esté caído — degradación útil, no accidental.

---

## 6. D6 — Notificación de reemplazo

### 6.1 Estado real: ya existe, con tres defectos

`service.py:112-134` ya implementa `_notificar_reemplazo_comparativa`. D6 **no es código nuevo,
es un fix**. Verificado contra el schema y contra `notificaciones/service.py`:

| # | Defecto actual | Consecuencia | Fix |
|---|---|---|---|
| 1 | Usa `extraccion/repository.py:crear_notificacion` (INSERT directo) en vez de `notificaciones.service.crear_notificacion` | **No se crean filas en `notificacion_entregas`** → la notificación nunca entra al pipeline de canales; existe en la tabla y no le llega a nadie | llamar al service |
| 2 | Sin `try/except` y corre **dentro** de `_materializar_comparativa`, o sea **antes** del flip de `validado` | un error al notificar deja comparativa + ofertas creadas con `validado=FALSE`: el peor estado parcial posible | mover después del flip + capturar |
| 3 | Sin `url_destino`, sin filtro `activo`, no excluye al actor | el usuario se auto-notifica; usuarios desactivados reciben avisos | ajustar la query |

### 6.2 Correcciones al texto de la proposal (verificadas contra el schema)

- **`tipo="comparativa_reemplazada"` es inválido.** `ck_notif_tipo`
  (`extractor_final.sql:1017-1022`) no lo incluye, y `TipoNotificacion` en
  `notificaciones/models.py` tampoco. El INSERT fallaría. Se usa **`"comparativa_disponible"`**
  (lo que ya usa el código) y la semántica de reemplazo va en `titulo`/`mensaje`/`metadata`.
- **`relaciones={"extraction_result_id": ...}` es inválido.** `relaciones` se hace *spread* dentro
  del dict de INSERT (`notificaciones/service.py:41`) y `notificaciones` no tiene esa columna →
  PostgREST devolvería *column not found*. Las columnas de relación disponibles son
  `proceso_comercial_id`, `comparativa_id`, `orden_compra_id`, `presupuesto_id`, `evento_id`,
  `accion_ejecutada_id`. El `extraction_result_id` va en **`metadata`** (JSONB).
- **Roles:** el código ya notifica a `("admin", "gerencia", "lider_comercial")`. Se **mantiene el
  superset** — `admin` es el rol operativo de la droguería y excluirlo sería una regresión.

### 6.3 Resolución de destinatarios

```python
# extraccion/repository.py
def listar_usuarios_por_rol(
    client, *, drogueria_id: str, roles: tuple[str, ...], excluir_id: str | None = None
) -> list[dict[str, Any]]:
    query = (
        client.table("usuarios")
        .select("id")
        .eq("drogueria_id", drogueria_id)
        .eq("activo", True)          # nuevo — no avisar a usuarios desactivados
        .in_("rol", roles)
    )
    if excluir_id is not None:
        query = query.neq("id", excluir_id)   # nuevo — no auto-notificar al que validó
    return query.execute().data
```

Corre con `service_client` (RLS de `usuarios` no permitiría enumerar compañeros con el token del
usuario). Usa `idx_usuarios_drogueria`. Cardinalidad esperada: unidades, no miles — no hace falta
paginar.

### 6.4 Call site y ubicación en el flujo

`_notificar_reemplazo_comparativa` **sale** de `_materializar_comparativa` y pasa a
`validar_extraccion()`, **después** del flip de `validado`:

```python
    ahora = datetime.now(timezone.utc).isoformat()
    repo.actualizar_extraction_result(
        client, extraction_id=extraction_id,
        campos={"validado": True, "validado_por": usuario_id, "validado_at": ahora},
    )

    # Fire-and-forget (D6): un aviso no es una aprobación. Nada de lo que pase acá
    # puede revertir ni bloquear una validación que YA está confirmada en la DB.
    if reemplazo and comparativa_id is not None:
        try:
            _notificar_reemplazo_comparativa(
                client,
                drogueria_id=extraction["drogueria_id"],
                proceso_comercial_id=proceso_comercial_id_resuelto,
                comparativa_id=comparativa_id,
                extraction_id=extraction_id,
                actor_id=usuario_id,
            )
        except Exception:   # noqa: BLE001 — deliberado, ver comentario de arriba
            logger.exception(
                "No se pudo notificar el reemplazo de comparativa "
                "(extraction_id=%s, comparativa_id=%s)", extraction_id, comparativa_id,
            )
```

```python
def _notificar_reemplazo_comparativa(
    client, *, drogueria_id, proceso_comercial_id, comparativa_id, extraction_id, actor_id
) -> None:
    destinatarios = repo.listar_usuarios_por_rol(
        client, drogueria_id=drogueria_id,
        roles=_ROLES_NOTIFICACION_REEMPLAZO, excluir_id=actor_id,
    )
    for usuario in destinatarios:          # sin destinatarios -> no pasa nada, no es error
        crear_notificacion(                # notificaciones.service, NO el repo local
            client,
            drogueria_id=drogueria_id,
            destinatario_id=usuario["id"],
            tipo="comparativa_disponible",
            titulo="Comparativa reemplazada por una nueva extracción",
            mensaje=(
                "Se validó una nueva extracción que reemplazó la comparativa vigente "
                "de este proceso. La versión anterior quedó invalidada."
            ),
            prioridad="alta",
            url_destino=f"/comparativas/{comparativa_id}",
            origen="sistema",
            relaciones={
                "proceso_comercial_id": proceso_comercial_id,
                "comparativa_id": comparativa_id,
            },
            metadata={
                "extraction_result_id": extraction_id,
                "motivo": "reemplazo_por_validacion",
            },
        )
```

Como `crear_notificacion` inserta N+1 filas por destinatario (1 notificación + 1 entrega por
canal), el `try/except` envuelve **el loop completo**: un fallo en el destinatario 3 de 5 deja a
1–2 notificados y se loguea. Aceptable para un aviso; reintentar dentro de una request HTTP
sincrónica no lo es.

**Nota de acoplamiento:** `extraccion/repository.py:crear_notificacion` queda sin callers y se
**borra** — su existencia es justamente lo que causó el defecto #1 (duplicaba mal el service).

---

## 7. D7 — Tope de 500 filas

Se enforce **en los dos lados, con semántica distinta en cada uno**:

| Capa | Dónde | Qué hace |
|---|---|---|
| Frontend | `features/validar-extraccion/constants.ts` → `MAX_FILAS_EDITABLES = 500` | Gate duro **antes** de pedir las filas: si `row_count > 500`, no se llama a `/filas`. Muestra el estado "documento demasiado grande" |
| Backend | `models.py` → `MAX_FILAS_EDITABLES = 500`, chequeado en §3 | Defensivo: `len(filas) > 500` → 422. **Solo sobre el payload editado** |

**Decisión clave — el tope es sobre la edición, no sobre la validación.** Un CSV de 900 filas se
puede seguir confirmando tal cual (`filas` ausente → camino CSV, sin límite). Si el tope aplicara
a la validación entera, un documento grande quedaría permanentemente sin poder materializarse. Esa
asimetría **es** la salida de emergencia que pide D7.

**UX por arriba del tope** (`DocumentoDemasiadoGrande.tsx`): banner de advertencia con el conteo
real, y dos acciones — *"Confirmar sin editar"* (POST `validar` sin `filas`, con el mismo
`ConfirmDialog` de impacto) y *"Volver al listado"*. Nunca se trunca en silencio: el usuario ve
`row_count` y ve que no puede editarlo.

**Duplicación del 500 en dos lenguajes:** deliberada, no hay codegen en el repo. Cada constante
lleva un comentario cruzado apuntando a la otra, y el test de backend usa el mismo valor.

---

## 8. Endpoints nuevos (D1 — viven en `services/presupuestacion`)

### 8.1 `GET /extracciones`

```
GET /extracciones?validado=false&limit=50&offset=0
Authorization: Bearer <jwt>
```

| Param | Tipo | Default | Nota |
|---|---|---|---|
| `validado` | `bool \| None` | `None` (todas) | `false` = pendientes |
| `limit` | `int` | 50 | máx. 200 |
| `offset` | `int` | 0 | paginación por rango |

```python
class ExtraccionResumen(BaseModel):
    id: str
    document_type: DocumentType
    source_filename: str
    row_count: int
    status: str
    validado: bool
    proceso_comercial_id: str | None
    proceso_comercial_nombre: str | None      # embed vía fk_er_proc
    created_at: datetime
```

Respuesta: `list[ExtraccionResumen]` — **lista pelada, sin envelope**, igual que
`GET /procesos-comerciales`. La paginación es por `limit`/`offset`; no se devuelve `total` porque
PostgREST necesita `count="exact"` (un `COUNT(*)` extra por request) y el listado de pendientes es
naturalmente corto. Si la pantalla llegara a necesitar paginador numerado, se agrega después.

```python
(user_client.table("extraction_results")
    .select("id, document_type, source_filename, row_count, status, validado, "
            "proceso_comercial_id, created_at, procesos_comerciales(nombre)")
    .eq("validado", validado)              # solo si validado is not None
    .order("created_at", desc=True)
    .range(offset, offset + limit - 1)
    .execute())
```

**Índice:** con `validado=false` el plan pega exacto contra
`idx_er_sin_validar ON extraction_results (drogueria_id, created_at DESC) WHERE validado = FALSE`
(`extractor_final.sql:1238`) — índice parcial + orden ya materializado, sin sort. El índice ya
existe: **no hay migración de schema en este change.**

**Auth:** `require_roles(*_ROLES_LECTURA)` con
`("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")`, espejo de
`procesos_comerciales/router.py:19`. La lectura pasa por `get_user_client()` → la policy `er_sel`
(`mismo_tenant(drogueria_id)`) es la frontera real de tenant; **no** se agrega filtro manual por
`drogueria_id` porque `superadmin` tiene `drogueria_id = NULL` y lo dejaría sin resultados.

### 8.2 `GET /extracciones/{extraction_id}/filas`

```python
class FilasExtraccionOut(BaseModel):
    extraction_id: str
    document_type: DocumentType
    row_count: int             # lo que dijo la IA (extraction_results.row_count)
    filas_leidas: int          # lo que realmente se parseó del CSV
    editable: bool             # filas_leidas <= MAX_FILAS_EDITABLES
    columnas: list[str]        # fieldnames del DictReader, en orden
    filas: list[dict[str, str]]
```

- **Sin paginación.** El tope de 500 es la cota. Si `filas_leidas > 500` se devuelve
  `editable=false` y **`filas=[]`** — mandar 50.000 filas que la UI no va a renderizar es
  desperdicio puro. `row_count` vs `filas_leidas` expuestos por separado: si difieren, el CSV en
  disco no coincide con lo que reportó la extracción, y eso es información de diagnóstico que el
  usuario debe ver.
- **Auth:** mismo `require_roles(*_ROLES_VALIDAR)` + mismo chequeo de pertenencia que
  `POST .../validar` (select por `user_client` + comparación de `drogueria_id`). Ver son las filas
  crudas es parte del flujo de validación, no lectura general.
- Primer consumidor del mount read-only; propaga `ExtraccionNoDisponibleError` → 503 (§5.2).

**Bug preexistente detectado, no arreglado acá:** `_ROLES_VALIDAR` no incluye `"superadmin"`, así
que `require_roles` le devuelve 403 y la rama `if usuario.rol != "superadmin"` de
`router.py:33` es código muerto. Se replica el patrón tal cual por consistencia y se anota en
`docs/modulos/extraccion_validacion/pendientes.md`.

---

## 9. Frontend

### 9.1 Rutas (TanStack Router, file-based plano)

| Archivo | Ruta | Componente |
|---|---|---|
| `routes/_authenticated.validar-extraccion.index.tsx` | `/validar-extraccion` | `ValidarExtraccionListado` |
| `routes/_authenticated.validar-extraccion.$extractionId.tsx` | `/validar-extraccion/:id` | `ValidarExtraccionDetalle` |

Mismo patrón plano que `_authenticated.admin.usuarios.tsx`. `beforeLoad: requireAuth` lo aporta el
layout `_authenticated.tsx`; las rutas hijas solo declaran `component`.

`Sidebar.tsx`: se reemplaza el placeholder deshabilitado por una entrada real
`{ label: 'Validar extracción', to: '/validar-extraccion' }` inmediatamente después de "Carga de
documentos" — es el paso siguiente del flujo y el orden del sidebar debe leerse como el flujo.

### 9.2 Componentes — `features/validar-extraccion/`

```
features/validar-extraccion/
├── ValidarExtraccionListado.tsx        container: query + estados (loading/vacío/error)
├── ValidarExtraccionDetalle.tsx        container: filas + estado de edición + mutation
├── components/
│   ├── PendientesTable.tsx             presentational: filas del listado
│   ├── TablaEditable.tsx               presentational: grilla por document_type
│   ├── CeldaEditable.tsx               input + validación por celda + aria-invalid
│   ├── ProcesoComercialSelector.tsx    <select> + NuevaLiciCotiDialog
│   ├── NuevaLiciCotiDialog.tsx         ← movido tal cual desde carga-documentos/
│   ├── ConfirmarValidacionDialog.tsx   wrapper de components/ConfirmDialog
│   └── DocumentoDemasiadoGrande.tsx    estado D7
├── useFilasEditables.ts                hook: estado local, diff, validación
└── constants.ts                        MAX_FILAS_EDITABLES = 500
```

`NuevaLiciCotiDialog.tsx` se mueve con `git mv` **sin editar imports**: hoy no tiene ningún caller
(confirmado en `carga-documentos/spec.md:10` y por lectura de `FormCard.tsx`). Su nuevo caller es
`ProcesoComercialSelector`, que le pasa `clase` derivada del `document_type` de la extracción
(`licitacion` → `'licitacion'`; `cotizacion` → `'cotizacion'`) y recibe el proceso creado por
`onCreated` para setear `proceso_comercial_id`.

`useFilasEditables` mantiene: `filasOriginales` (inmutable, del server), `filas` (editable),
y deriva `{ modificadas, borradas, agregadas, erroresPorCelda }`. El submit se habilita solo con
`erroresPorCelda` vacío y `proceso_comercial_id` resuelto — la validación por celda es la primera
línea; §3 es la red de seguridad del servidor, no el mecanismo de UX.

`ConfirmarValidacionDialog` resume el impacto real antes de ejecutar (D5): N modificadas,
N borradas, N agregadas, y — si `document_type === 'comparativa'` y el proceso ya tiene comparativa
vigente — la advertencia de reemplazo. `ConfirmDialog` recibe `confirmLabel="Confirmar validación"`
(su default es `"Eliminar"`; hoy además hardcodea `"Eliminando…"` en el estado pending, así que se
lo parametriza con un `pendingLabel` opcional — cambio mínimo y retrocompatible).

**Accesibilidad de la tabla editable** (D5 exige navegación por teclado):
`Tab`/`Shift+Tab` recorren celdas en orden visual; `Enter` baja una fila en la misma columna;
`Escape` revierte la celda a su valor original. Cada celda inválida marca `aria-invalid` + mensaje
asociado por `aria-describedby` — el error va junto al campo, no agrupado arriba. Los botones de
borrar fila llevan `aria-label` explícito (no ícono pelado).

### 9.3 Query keys e invalidación

```ts
const EXTRACCIONES_KEY = ['extracciones'] as const
// listado:  ['extracciones', { validado: false }]
// filas:    ['extracciones', extractionId, 'filas']
```

```ts
const mutation = useMutation({
  mutationFn: (payload) => validarExtraccion(extractionId, payload),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: EXTRACCIONES_KEY })  // prefijo: listado + filas
    navigate({ to: '/validar-extraccion' })
  },
})
```

**Sobre la carrera que se arregló en `carga-documentos` — verificado, y la conclusión es doble:**

1. **No aplica al `POST .../validar`.** Confirmado por grep: `services/presupuestacion` **no usa
   `BackgroundTasks` en ningún archivo**. `router.py` llama `validar_extraccion_para_endpoint`
   inline y todos los writes están commiteados antes del 200. Un `invalidateQueries` simple
   alcanza. **Copiar `esperarNuevoDocumento()` acá sería un antipatrón**: agregaría hasta 3,6 s de
   latencia artificial (6 intentos × 600 ms) para resolver una carrera que no existe.
2. **Sí aplica a la *entrada* de esta pantalla.** `POST /procesar` de `services/extraccion`
   persiste `extraction_results` en un `BackgroundTask` (`main.py:269` →
   `schedule_persist_output`). Un usuario que sube un documento y navega inmediatamente a "Validar
   extracción" puede no ver su extracción en el listado. Mitigación **sin polling**: el listado usa
   `staleTime: 0` y el `refetchOnWindowFocus` default de TanStack Query, más un botón explícito
   "Actualizar". Navegar entre pantallas monta el componente y dispara fetch fresco, que cubre el
   caso normal. La solución de fondo —hacer sincrónica la persistencia del extractor— es un change
   aparte y se anota como tal.

### 9.4 `lib/api/presupuestacion.ts` y capa de API

`presupuestacionFetch` no se toca. Se agrega `frontend/src/lib/api/extracciones.ts` (archivo nuevo,
siguiendo el patrón de `procesosComerciales.ts` — un módulo por recurso) con
`listarExtracciones`, `obtenerFilasExtraccion`, `validarExtraccion` y sus tipos. El `ApiError` ya
propaga `body.detail`, que es exactamente el shape que devuelve `register_exception_handlers` —
los mensajes de §3 llegan a la UI sin traducción intermedia.

---

## 10. Archivos afectados

| Archivo | Acción | Qué cambia |
|---|---|---|
| `services/presupuestacion/extraccion/models.py` | Modificar | `FilaLicitacionIn`, `FilaComparativaIn`, `filas` en el request, `MAX_FILAS_EDITABLES`, `ExtraccionResumen`, `FilasExtraccionOut` |
| `services/presupuestacion/extraccion/service.py` | Modificar | `_filas_a_materializar`, `_validar_filas_override`, `filas_override` en ambos materializadores, notificación movida y capturada, `_leer_filas_csv` robusto |
| `services/presupuestacion/extraccion/repository.py` | Modificar | `listar_extracciones`, `listar_usuarios_por_rol` (+`activo`, +`excluir_id`), **borrar** `crear_notificacion` |
| `services/presupuestacion/extraccion/router.py` | Modificar | `GET /extracciones`, `GET /extracciones/{id}/filas`, `body.filas` al service |
| `services/presupuestacion/core/exceptions.py` | Modificar | `ExtraccionNoDisponibleError` → 503 |
| `docker-compose.yml` | Modificar | `volumes:` en ambos servicios + top-level, env de Supabase en `extraccion-api` |
| `frontend/src/features/validar-extraccion/**` | Crear | 11 archivos (§9.2) |
| `frontend/src/features/carga-documentos/components/NuevaLiciCotiDialog.tsx` | Mover | → `features/validar-extraccion/components/` (sin callers hoy) |
| `frontend/src/lib/api/extracciones.ts` | Crear | tipos + 3 funciones |
| `frontend/src/components/ConfirmDialog.tsx` | Modificar | `pendingLabel` opcional |
| `frontend/src/features/shell/Sidebar.tsx` | Modificar | entrada "Validar extracción" |
| `frontend/src/routes/_authenticated.validar-extraccion.*.tsx` | Crear | 2 rutas |
| `docs/modulos/extraccion_api/`, `extraccion_validacion/` | Modificar | deprecación documentada, corrección de `casos_de_uso.md:63`, pendientes nuevos |

Sin migraciones de schema. Sin cambios de RLS. Los índices necesarios ya existen.

---

## 11. Estrategia de testing

| Capa | Qué | Cómo |
|---|---|---|
| Unit (backend) | `_validar_filas_override`: tipo cruzado, no numérico, vacío, >500, acumulación de errores | puro, sin DB, sin marca `integration` |
| Unit (backend) | `_filas_a_materializar`: `None` → CSV, lista → lista | con `tmp_path`, sin DB |
| Integration | licitación con `filas` editadas → `items_proceso` con los valores del body, no del CSV | `seed_extraction_result_factory` (ya existe), marca `integration` |
| Integration | comparativa con fila **agregada** → `ofertas_items` incluye el renglón nuevo y `_computar_posiciones` lo posiciona | idem |
| Integration | fila 47 inválida de 80 → 422 **y** `validado` sigue `FALSE`, sin `items_proceso`, sin `proceso_comercial_id` seteado | asserts de no-escritura, es el corazón de §3 |
| Integration | reemplazo → hay filas en `notificaciones` **y** en `notificacion_entregas`; el actor no está entre los destinatarios | cubre defectos #1 y #3 |
| Integration | `crear_notificacion` monkeypatcheado a `raise` → la validación igual devuelve 200 y `validado=TRUE` | cubre el defecto #2 |
| Integration | `csv_disk_path` inexistente / `NULL` → 503 con `detail` de dominio, no 500 | cubre §5.2 |
| Regresión | los 12 tests actuales corren sin modificación | criterio de aceptación duro de D2 |
| Frontend | `useFilasEditables`: diff de modificadas/borradas/agregadas, errores por celda | Vitest |
| Frontend | `row_count > 500` → no se dispara la query de `/filas`, se renderiza `DocumentoDemasiadoGrande` | Testing Library + mock de fetch |
| E2E manual | flujo completo en Docker Compose con el volumen montado | valida D4 de punta a punta; es lo único que no se puede probar sin contenedores |

El teardown de `conftest.py` ya limpia `notificaciones` por `comparativa_id`; las filas de
`notificacion_entregas` que agrega el fix quedan huérfanas y hay que **extender el teardown** para
borrarlas por `notificacion_id` antes de las notificaciones.

---

## 12. Threat matrix

No hay routing dinámico, shell, subprocesos, automatización de VCS/PR ni clasificación de
ejecutables. Aplica **una sola** fila de superficie:

| Superficie | Aplicabilidad | Comportamiento esperado | Test RED |
|---|---|---|---|
| Lectura de path del filesystem (`csv_disk_path`) | **Aplicable** | El path viene de `extraction_results`, escrito por el otro servicio — **nunca de input del usuario**. El endpoint recibe `extraction_id` (UUID) y resuelve el path por DB. No se concatena input en el path, así que no hay path traversal. El mount es `:ro`: aunque el path apuntara fuera del volumen, no hay escritura posible | `GET /filas` de una extracción de otra droguería → 403 antes de tocar el disco (el chequeo de pertenencia precede al `open`) |
| Routing / shell / subprocess / VCS / ejecutables | **N/A** | ninguna de estas fronteras existe en este change | — |

Riesgo de exposición cubierto por D1: los endpoints nuevos exigen JWT + `require_roles` + RLS, a
diferencia de `GET /api/documentos` de `services/extraccion`, que es público.

---

## 13. Migración / rollout

**Sin migración de datos.** Sin cambios de schema, RLS ni índices.

Orden de despliegue con una dependencia dura:

1. `docker-compose.yml` (volumen + env) — **debe ir primero**. Sin el volumen,
   `GET /filas` devuelve 503 en Docker y la pantalla no arranca. Es además un fix que conviene
   independientemente de esta pantalla: hoy en Docker no se persiste ninguna extracción.
2. Backend (aditivo: campo opcional + 2 endpoints).
3. Frontend.

**Rollback:** revertir el commit de backend deja `validar` exactamente como estaba (`filas` es
opcional; el camino CSV es el mismo código). El frontend se saca quitando la ruta y la entrada del
sidebar. El `docker-compose.yml` conviene **no** revertirlo: arregla un bug que existe con o sin
esta pantalla.

---

## 14. Preguntas abiertas

- [ ] `_ROLES_VALIDAR` no incluye `superadmin`, lo que vuelve muerta la rama
      `if usuario.rol != "superadmin"` de `router.py:33`. Se replica el patrón por consistencia,
      pero hay que decidir si `superadmin` debe poder validar (bugfix aparte).
- [ ] La materialización de comparativa no es transaccional entre statements (§4). Una RPC de
      Postgres lo resolvería; queda como change propio.
- [ ] `POST /procesar` persiste en `BackgroundTask`: el listado de pendientes puede mostrarse
      desactualizado justo después de subir un documento (§9.3). Hacerlo sincrónico es la solución
      de fondo y está fuera de scope.
