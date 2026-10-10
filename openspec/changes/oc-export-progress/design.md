# Diseño: Exportación de orden de compra a Progress + calendario de compromisos

> Idioma: español neutro/profesional, como `proposal.md` y los cambios archivados.

## Technical Approach

Módulo nuevo `services/presupuestacion/oc_export/` con la estructura de sus hermanos
(`models`, `repository`, `service`, `router`), más dos piezas internas separadas a propósito:

- `filas.py`: construcción **pura** de las filas del CSV (sin I/O, sin Supabase).
- `escritor.py`: serialización, encoding y escritura atómica en disco.

El service orquesta: lee la OC (service client + filtro explícito por `drogueria_id`, patrón de
`oc_entregas/`), valida precondiciones, arma filas, escribe el archivo y registra la exportación en
`ordenes_compra` con un `UPDATE` condicional. El calendario es una vista SQL de solo lectura más un
endpoint `GET`.

## Correcciones de hechos sobre la propuesta

- **C1 — La OC no cambia de estado al exportar.** Las OC extraídas nacen `emitida`
  (`services/presupuestacion/extraccion/service.py:804`) y `confirmar_orden_compra` también lleva
  `pendiente`→`emitida` (`compras/service.py:116-146`). La precondición "OC en `pendiente`" nunca se
  cumpliría, y `emitida` ya habilita registrar entregas físicas (`compras/service.py:23`). La marca
  de exportación es `ordenes_compra.exportado_at IS NOT NULL`; `estado` no se toca.
- **C2 — El calendario filtra por `exportado_at`, no por `estado = 'emitida'`**, por el mismo motivo.
- **C3 — `productos.codigo_interno` es `NOT NULL`** (`docs/schema/extractor_final.sql:357`). La
  precondición se reduce a "todo renglón tiene `producto_id`".
- **C4 — El código de cliente puede ser ambiguo.** `uq_tlm_codigo` es único por código, no por tercero
  (`0008_terceros_modelo.sql:150`): un tercero puede tener varios códigos `cliente`. Ver D3.
- **C5 — Ya existe `v_calendario`** (sobre `eventos`) y el ítem de menú "Calendario"
  (`frontend/src/features/shell/Sidebar.tsx:23`, deshabilitado) le corresponde. Los compromisos usan
  nombre y ruta propios (D10) para no pisar ese espacio.
- **C6 — La planificación tiene que quedar bloqueada después de exportar.** Hoy el `PUT` de
  `oc_entregas` solo bloquea si alguna entrega dejó de estar `pendiente`. Si se replanifica una OC ya
  exportada, el plan nuestro y el de Progress divergen sin aviso. Ver D7.

## Architecture Decisions

### D1 — Marca de exportación: tres columnas en `ordenes_compra`

`exportado_at TIMESTAMPTZ NULL`, `exportado_por UUID NULL` (FK `usuarios`), `archivo_exportado TEXT
NULL`, con `CHECK` "las tres NULL o las tres NOT NULL". Columnas y no tabla de historial: una OC se
exporta una sola vez por versión. Si más adelante se habilita la reexportación, se evalúa una tabla.

### D2 — Precondiciones (todas `ValidationError` 422, con mensaje que nombra el dato faltante)

1. `exportado_at IS NULL` (si no: `ConflictError` 409, "ya exportada el <fecha> por <usuario>").
2. `estado <> 'cancelada'`, `deleted_at IS NULL`, `es_vigente`.
3. `cliente_id IS NOT NULL`.
4. Código de cliente resuelto sin ambigüedad (D3).
5. Todo renglón tiene `producto_id`. El mensaje lista los `numero_renglon` faltantes.
6. Hay al menos una entrega y todas tienen `fecha_entrega_planificada`.
7. Por renglón, `SUM(cantidad_planificada) = oc_items.cantidad`. El mensaje lista los renglones que
   no cierran.

Se validan **todas** y se reportan juntas, para que el usuario no corrija de a un error por intento.

### D3 — Resolución del código de cliente

`terceros_legacy_map` con `tercero_id = ordenes_compra.cliente_id` (`clientes.id == terceros.id`,
`extractor_final.sql:245-263`), `entidad_legacy = 'cliente'` y misma `drogueria_id`. Exactamente una
fila: se usa. Cero o más de una: `ValidationError`. Elegir una "por las dudas" mandaría a Progress el
cliente equivocado sin que nadie lo note.

### D4 — Construcción de filas (`filas.py`, pura)

`construir_filas(oc, renglones, entregas, codigo_cliente, cuit) -> list[list[str]]`. Una fila por
renglón × entrega con `cantidad_planificada > 0`, ordenadas por `numero_renglon` y luego
`numero_entrega`. Formato de cada valor:

| Tipo | Formato | Ejemplo |
|---|---|---|
| Cantidades y precios | 2 decimales, decimal `,`, sin separador de miles | `1520,50` |
| Fechas | `dd/mm/yyyy` | `15/10/2026` |
| Enteros identificadores (`version`, `numero_renglon`, `numero_entrega`) | Sin decimales | `3` |
| Texto | Tal cual, `strip()` | `Ibuprofeno 400mg, caja x 20` |
| NULL opcional (`direccion_entrega`, `cuit_cliente`, `fecha_emision`) | Cadena vacía | |

Como todo importe lleva 2 decimales con `,`, siempre contiene coma y `csv.QUOTE_MINIMAL` lo encierra
entre comillas, que es la convención acordada (`"1520,50"`). No hace falta forzar comillas a mano.

### D5 — Escritura (`escritor.py`)

- Carpeta: `{PROGRESS_DOCS_DIR}/oc`, creada con `mkdir(parents=True, exist_ok=True)`.
- Nombre: `OC_{codigo_cliente}_{numero_oc}_v{version}_{yyyyMMddHHmmss}.csv`. `codigo_cliente` y
  `numero_oc` se sanean: `strip()`, cualquier carácter fuera de `[A-Za-z0-9-]` pasa a `-`. Hora local
  `America/Argentina/Buenos_Aires`.
- `csv.writer(delimiter=",", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")`, con fila de
  encabezados.
- Encoding: `OC_EXPORT_ENCODING` (default `cp1252`) con `errors="replace"`: un carácter no
  representable sale como `?` en lugar de abortar.
- Atomicidad: escribe en `.{nombre}.tmp` en la misma carpeta y hace `os.replace`. Si falla a mitad,
  borra el temporal.
- Si el nombre final ya existe: `ConflictError` (no se pisa nunca un archivo).

### D6 — Orden de efectos y concurrencia

1. Validar (D2).
2. Escribir el archivo (D5).
3. `UPDATE ordenes_compra SET exportado_* ... WHERE id = :id AND drogueria_id = :d AND exportado_at
   IS NULL`, un CAS como el que ya usa el proyecto para concurrencia.
4. Si el `UPDATE` afecta 0 filas (doble clic, otro usuario ganó) o falla: se borra el archivo recién
   escrito y se responde `ConflictError` o se re-lanza el error. Es la misma compensación manual que
   `oc_entregas/service.py:393-399`.
5. `registrar_cambio(...)` de auditoría, como `compras/service.py:136-147`.

Riesgo residual aceptado: si Progress toma el archivo entre el paso 2 y una falla del 3, queda un CSV
sin marca en la OC. Es improbable (milisegundos) y visible: Progress tendría una OC que nosotros
mostramos como no exportada.

### D7 — Bloqueo de planificación post-exportación

El `PUT /ordenes-compra/{id}/entregas/planificacion` responde `ConflictError` si `exportado_at IS NOT
NULL`. El `GET` de planificación suma un bloque `exportacion` (`exportado_at`, `exportado_por`,
`archivo_exportado`, o `null`) para que la pantalla muestre el estado y oculte la edición.

### D8 — Configuración

En `services/shared/config.py` (compartido con `services/terceros`, por eso con defaults):
`progress_docs_dir: str | None = None` y `oc_export_encoding: str = "cp1252"`. Si
`progress_docs_dir` es `None`, la exportación responde 503 con una excepción nueva
`IntegracionNoConfigurada` en `services/shared/exceptions.py`. El resto de la app no se ve
afectado.

`docker-compose.yml`, servicio `presupuestacion-api`, se agrega un bind mount **de escritura**,
separado del volumen `:ro` existente:

```yaml
    environment:
      - PROGRESS_DOCS_DIR=C:/app/documentos_ia
      - OC_EXPORT_ENCODING=cp1252
    volumes:
      - extraccion-output:C:/app/output:ro
      - C:/SACPro/documentos_ia:C:/app/documentos_ia
```

`C:\SACPro\documentos_ia` debe existir en el host antes de `docker compose up`, porque Docker con
contenedores Windows no la crea.

### D9 — Vista `v_compromisos_entregas`

`WITH (security_invoker = true)`, como el resto de las vistas (`0008:338`). Granularidad: **una fila
por ítem de entrega**, para mostrar qué y cuánto se compromete.

```sql
SELECT oc.drogueria_id, oc.id AS orden_compra_id, oc.numero_oc, oc.version_numero,
       oc.exportado_at, t.razon_social AS cliente,
       e.id AS entrega_oc_id, e.numero_entrega, e.fecha_entrega_planificada,
       oi.numero_renglon, p.codigo_interno AS codigo_articulo, oi.descripcion,
       ei.cantidad_planificada,
       CASE WHEN e.fecha_entrega_planificada
                 < (now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date
            THEN 'vencida' ELSE 'futura' END AS situacion,
       GREATEST((now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date
                - e.fecha_entrega_planificada, 0) AS dias_atraso
FROM entregas_oc e
JOIN ordenes_compra oc   ON oc.id = e.orden_compra_id AND oc.drogueria_id = e.drogueria_id
JOIN entregas_oc_items ei ON ei.entrega_oc_id = e.id
JOIN oc_items oi          ON oi.id = ei.oc_item_id
LEFT JOIN productos p     ON p.id = oi.producto_id
LEFT JOIN terceros t      ON t.id = oc.cliente_id AND t.drogueria_id = oc.drogueria_id
WHERE oc.exportado_at IS NOT NULL AND oc.deleted_at IS NULL AND oc.es_vigente
  AND oc.estado <> 'cancelada' AND e.estado = 'pendiente';
```

La fecha "hoy" se calcula en hora argentina: con `CURRENT_DATE` (UTC en Supabase), entre las 21:00
y las 24:00 una entrega de mañana figuraría como de hoy. El día de hoy cuenta como `futura`.

### D10 — Endpoints

| Método | Ruta | Roles | Respuesta |
|---|---|---|---|
| `POST` | `/ordenes-compra/{id}/exportar-progress` | `_ROLES_OC` (`admin`, `gerencia`, `lider_comercial`, `comercial`) | `{archivo, exportado_at, exportado_por, filas}` |
| `GET` | `/compromisos-entregas?desde&hasta` | `_ROLES_LECTURA` (incluye `compras`) | Lista de filas de la vista, filtrada por `drogueria_id` del usuario |

Sin `desde`, el `GET` devuelve todas las vencidas más las futuras de los próximos 6 meses. El rango
máximo es de 24 meses (`ValidationError`).

### D11 — Frontend

- **Exportar**: botón "Exportar a Progress" en `features/oc-entregas/PlanificacionEntregas.tsx`,
  habilitado solo con plan guardado y sin `exportacion`. Pide confirmación ("no se podrá modificar el
  plan"), muestra los errores de precondición tal como vienen y, si sale bien, el nombre del archivo.
  Ya exportada: banner "Exportada a Progress el … por …" y la edición queda en solo lectura.
- **Compromisos**: ruta nueva `/compromisos`, ítem de menú "Compromisos de entrega". No hay
  librería de calendario en el proyecto (`frontend/package.json`) y no se agrega una: la v1 es una
  **vista agenda**, con una sección "Vencidas sin confirmar" arriba y luego grupos por mes y por
  fecha. Cada entrega muestra cliente, OC y sus renglones con cantidades. Una grilla mensual queda
  para una versión posterior si Compras la pide.

## Data Flow

```
PlanificacionEntregas ──POST exportar-progress──▶ oc_export.router
                                                     │ require_roles(_ROLES_OC)
                                                     ▼
                                              oc_export.service
                     repository (service client) ◀──┤ D2 precondiciones, D3 código cliente
                                                     ├──▶ filas.construir_filas  (puro)
                                                     ├──▶ escritor.escribir      ──▶ C:/app/documentos_ia/oc/*.csv
                                                     ├──▶ UPDATE CAS exportado_* (compensa borrando el archivo)
                                                     └──▶ registrar_cambio
Compromisos (/compromisos) ──GET compromisos-entregas──▶ v_compromisos_entregas
```

## File Changes

| Archivo | Acción |
|---|---|
| `supabase/migrations/0032_oc_exportacion_progress.sql` / `.down.sql` | Nuevo: columnas D1 + vista D9 |
| `docs/schema/extractor_final.sql` | Modificado: snapshot |
| `services/shared/config.py`, `services/shared/exceptions.py` | Modificado: D8 |
| `services/presupuestacion/oc_export/{__init__,models,repository,filas,escritor,service,router}.py` | Nuevo |
| `services/presupuestacion/oc_entregas/{service,models}.py` | Modificado: D7 |
| `services/presupuestacion/main.py` | Modificado: registrar router |
| `docker-compose.yml` | Modificado: D8 |
| `frontend/src/lib/api/ocExport.ts`, `frontend/src/lib/api/compromisos.ts` | Nuevo |
| `frontend/src/features/oc-entregas/PlanificacionEntregas.tsx` (+ tipos) | Modificado: D11 |
| `frontend/src/features/compromisos/` + `routes/_authenticated.compromisos.tsx` | Nuevo |
| `frontend/src/features/shell/Sidebar.tsx` | Modificado: ítem de menú |
| `tests/oc_export/` (`test_filas.py`, `test_escritor.py`, `test_service.py`, `test_router.py`, `conftest.py`) | Nuevo |
| `tests/oc_entregas/` | Modificado: bloqueo D7 |

## Interfaces / Contracts

```python
def construir_filas(oc: OcExport, renglones: list[RenglonExport],
                    entregas: list[EntregaExport], *, codigo_cliente: str,
                    cuit_cliente: str | None) -> list[list[str]]: ...

def escribir_csv(filas: list[list[str]], *, carpeta: Path, nombre: str,
                 encoding: str) -> Path: ...

def exportar_orden_compra(client: Client, *, orden_compra_id: str, drogueria_id: str,
                          usuario_id: str, settings: Settings) -> ResultadoExportacion: ...
```

`ResultadoExportacion`: `archivo: str`, `exportado_at: datetime`, `exportado_por: UUID`,
`filas: int`.

## Testing Strategy

Test-first por capa:

- **Unitarios, sin red:**
  - `filas.py`: formato decimal, fechas, orden, entregas con cantidad 0 omitidas, cabecera repetida
    y NULL opcionales.
  - `escritor.py` en `tmp_path`:
    - Releer en `cp1252` y verificar ñ y acentos.
    - Descripción con coma y con comillas: `csv.reader` la reconstruye igual.
    - Emoji pasa a `?`.
    - CRLF.
    - No quedan temporales y no se pisa un archivo existente.
  - `service.py` con mocks:
    - Cada precondición D2.
    - Reporte acumulado.
    - D3 con 0, 1 y 2 códigos.
    - Compensación D6: falla del `UPDATE` o 0 filas, y el archivo se borra.
- **Integración (`@pytest.mark.integration`):**
  - Router con JWT real por rol: `comercial` exporta, `compras` recibe 403.
  - Exportación real a `tmp_path`, CAS contra doble exportación y bloqueo D7 del `PUT`.
  - La vista devuelve solo OC exportadas, con `vencida` y `futura`.
- **Migración:** aplicar, `down` limpio y reaplicar en el proyecto de test, como en 0026.
- **Frontend (vitest):** estados del botón, render de errores y agrupación de la agenda.

## Threat Matrix

| Amenaza | Mitigación |
|---|---|
| Path traversal vía `numero_oc` o código de cliente en el nombre de archivo | Saneo a `[A-Za-z0-9-]`; la carpeta la fija la configuración, nunca la request |
| Exportar OC de otra droguería | Service client con filtro explícito por `drogueria_id` del usuario; OC ajena = `NotFoundError` |
| Rol sin permiso exporta | `require_roles(_ROLES_OC)` + test de integración 403 |
| Inyección de fórmulas al abrir el CSV en Excel (`=`, `+`, `-`, `@` al inicio de una descripción) | Fuera de alcance: el consumidor es Progress, no Excel. Se documenta |

## Performance

Una OC tiene decenas de renglones y pocas entregas: la exportación son 3-4 lecturas y un archivo de
KB. La vista usa los índices existentes de `entregas_oc` y `ordenes_compra`. Se agrega un índice
parcial `ON ordenes_compra (drogueria_id) WHERE exportado_at IS NOT NULL` para el filtro del
calendario.

## Migration / Rollout

1. Aplicar `0032` en test, verificar, `down`, reaplicar.
2. Desplegar el backend con `PROGRESS_DOCS_DIR` sin definir: la exportación responde 503 y el resto
   no cambia.
3. Crear `C:\SACPro\documentos_ia` en el servidor, actualizar `docker-compose.yml` y levantar.
4. Exportar una OC real de prueba y pasarle el CSV a Sistemas para validar encoding y comillas en
   Progress.

`down`: `DROP VIEW v_compromisos_entregas`, `DROP INDEX`, `DROP CONSTRAINT` y `DROP COLUMN` de las tres
columnas. Se pierde el registro de qué OC se exportaron, mientras que los archivos en disco quedan.

## Open Questions

Ninguna bloqueante. Para validar con Sistemas en el paso 4 del rollout: encoding real (`-cpstream`)
y que el importador respete las comillas.
