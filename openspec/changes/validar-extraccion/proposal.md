# Proposal: Validar extracción

**Estado: en progreso.** Escrito el 2026-07-25 sobre `exploration.md` del mismo día. Reemplaza el
stub del 2026-07-15, que solo cubría la vinculación a `proceso_comercial` y subestimaba el alcance
real. Pantalla #3 del MVP (`frontend/PROGRESS.md`).

## Intent

Es el único punto del sistema donde un humano mira lo que devolvió Gemini **antes** de que se
convierta en datos de negocio. Hoy el backend que hace esa conversión ya existe
(`POST /extracciones/{id}/validar`, 12 tests, `docs/modulos/extraccion_validacion/`), pero no tiene
pantalla, no tiene listado de pendientes, y **no deja corregir nada**: lee el CSV tal cual quedó en
disco y materializa. Si la IA leyó mal un precio o metió la cabecera como renglón, ese error entra
directo a `items_proceso`/`ofertas_items`, dispara matching, y `validado` es un flag de un solo
sentido — no hay vuelta atrás.

El costo de negocio es concreto: un precio mal extraído se propaga a la comparativa, define
`posicion_precio` y `adjudicacion_estimada` (RN-EXTRACCIONVALIDACION-008), y termina decidiendo una
compra sobre una premisa falsa. Y no se puede arreglar re-subiendo el archivo:
`uq_er_sha256 UNIQUE (source_sha256)` + la RPC `reserve_extraction` devuelven la extracción
existente en vez de re-extraer.

## Scope

### Incluido

1. **Listado de pendientes de validar** — nuevo `GET /extracciones` en `services/presupuestacion`,
   filtrable por `validado`. Hoy ningún endpoint expone ni filtra ese campo.
2. **Lectura de las filas extraídas** — nuevo `GET /extracciones/{id}/filas`, que parsea
   `csv_disk_path`. Hoy no existe forma de ver las filas: el único endpoint que las devolvía
   (`GET /api/documentos/{doc_id}`) lee tablas muertas.
3. **Edición de filas antes de confirmar** — `POST /extracciones/{id}/validar` acepta un `filas`
   opcional en el body; si viene, se materializa desde ahí en vez del CSV. Incluye editar valores,
   borrar filas y **agregar** filas (ver D2).
4. **Pantalla React** `features/validar-extraccion/`: listado de pendientes, tabla editable por
   tipo de documento, selector/creación de proceso comercial reusando `NuevaLiciCotiDialog.tsx`
   (que se reubica desde `features/carga-documentos/`), confirmación explícita e irreversible.
5. **Volumen compartido en `docker-compose.yml`** — sin esto el flujo no funciona en Docker (D4).
6. **Entrada en el sidebar** y ruta bajo `_authenticated`.
7. **Fix del aviso de reemplazo de comparativa vigente** (no es funcionalidad nueva: ya existe y
   notifica hoy, con tres defectos reales) — pasa a usar
   `services/presupuestacion/notificaciones/service.py:crear_notificacion()` en vez del insert
   directo actual. Ver D6.
8. **Tope de filas editables en la tabla** — ver D7.

### Explícitamente fuera de scope

- **Materialización de `orden_compra`**. No hay ningún camino que lo alcance: `persistent_output.py`
  solo acepta `_DOC_TYPES_SOPORTADOS = {"comparativa", "licitacion"}`, así que no puede existir un
  `extraction_results` con ese `document_type`; y la opción "Orden de compra" del upload está
  deshabilitada con badge "Próximamente". Se mantiene el `ValidationError` actual
  (RN-EXTRACCIONVALIDACION-002). Implementarlo ahora sería código muerto sin forma de probarlo
  end-to-end.
- **Auditoría de la edición en `historial_cambios`**. `core.audit` no soporta las entidades
  `item_proceso` ni `extraction_result` (`_COLUMNA_FK_POR_ENTIDAD`, ver
  `extraccion_validacion/pendientes.md` P2); extenderlo es un change aparte. Mitigante: el CSV
  crudo queda intacto (D2), así que el diff humano↔IA siempre es reconstruible.
- **Deshacer una validación.** `validado` sigue siendo de un solo sentido.
- **Corregir los endpoints legacy rotos** de `services/extraccion` — ver "Qué se borra" abajo.
- **Sin implicancias de Gemini**: esta pantalla no llama a la API. Corrige su salida, no la vuelve
  a pedir.

## Decisiones de arquitectura

### D1 — El listado y la lectura de filas viven en `services/presupuestacion`, no en `extraccion`

`services/extraccion` no tiene auth: `GET /api/documentos` es público y resuelve la droguería con
`resolver_drogueria_id_unica()`, un supuesto mono-tenant. Si el listado viviera ahí, un caller sin
autenticar podría enumerar los documentos de cualquier droguería, mientras que la acción sobre esos
mismos documentos (`POST .../validar`) sí exige JWT, `require_roles` y chequeo de pertenencia
(RN-EXTRACCIONVALIDACION-010/011). Esa asimetría es una fuga de información, no un detalle de
prolijidad. Además el frontend ya tiene `presupuestacionFetch` con JWT. Los endpoints nuevos usan
`get_user_client()` (RLS-aware) para leer, igual que hace hoy el router antes de delegar al service.

### D2 — La edición viaja en el body de `validar`; el CSV en disco NO se reescribe

Alternativas descartadas:

- *Reescribir el CSV (`PATCH /extracciones/{id}/filas`)*: el CSV es, por diseño explícito, la única
  fuente de verdad de lo que devolvió la IA — `persistent_output.py` documenta que las filas **no**
  se persisten en Supabase. Pisarlo destruye el único registro de la salida cruda y desalinea
  `source_sha256` (el hash del archivo original deja de corresponder al CSV asociado). Además crea
  un estado intermedio en un disco compartido entre dos contenedores, sin dueño ni lock.
- *Tabla `extraction_rows` en Supabase*: es la evolución correcta si algún día la revisión tiene que
  ser multi-sesión o multi-usuario, pero hoy implica migración de schema + reescribir el camino de
  escritura de `services/extraccion` para una revisión que el usuario hace una vez y confirma.

Elegido: `ValidarExtraccionRequest` gana `filas: list[...] | None = None`, tipado según
`document_type` (`item`/`descripcion`/`cantidad` para licitación-cotización;
`renglon`/`proveedor`/`marca`/`precio` para comparativa) y validado contra el `document_type` real
de la extracción. Es retrocompatible: los 12 tests y cualquier caller que solo mande
`proceso_comercial_id` siguen funcionando leyendo el CSV.

**Agregar filas está permitido** porque la deduplicación por SHA256 hace que re-subir el archivo no
re-extraiga: si Gemini se saltó un renglón, sin esta capacidad el dato es irrecuperable.

**`extraction_results.row_count` no se toca**: describe cuántas filas devolvió la IA.
`ResultadoValidarExtraccion.filas_creadas` reporta cuántas confirmó el humano. La diferencia entre
ambos es señal de calidad de extracción y se pierde si se sobrescribe.

### D3 — Confirmar es una sola llamada atómica

`validado` es irreversible y dispara matching. Partir el flujo en "guardar edición" + "confirmar"
dejaría una extracción a medio corregir sin dueño. La edición y el flip de `validado` ocurren en la
misma request.

### D4 — Volumen compartido con el mismo mount path en ambos contenedores

`extraccion-api` y `presupuestacion-api` no comparten ningún volumen hoy. `csv_disk_path` se guarda
como path **absoluto**, así que el volumen tiene que montarse en la misma ruta (`C:/app/output`) en
los dos, o el `open()` falla. `presupuestacion-api` lo monta **read-only**: nunca escribe ahí (D2).

Además, `_leer_filas_csv` debe fallar con un error de dominio claro ("el archivo de la extracción no
está disponible") en vez de dejar escapar un `FileNotFoundError` como 500 con stack trace — hoy es
exactamente lo que pasaría.

### D5 — UI: la irreversibilidad tiene que verse

La confirmación usa `ConfirmDialog.tsx` (ya existe) y resume el impacto real antes de ejecutar:
cuántas filas se modificaron, cuántas se borraron, cuántas se agregaron, y **si va a reemplazar la
comparativa vigente** (RN-EXTRACCIONVALIDACION-007 versiona e invalida la anterior sin preguntar).
La tabla editable necesita navegación por teclado y validación por celda antes de habilitar el
submit — `cantidad` y `precio` se parsean del lado del backend y hoy un valor no numérico revienta
en medio de la materialización.

### D6 — Notificación de reemplazo: corrección de un mecanismo que YA EXISTE, no una notificación nueva

**Corrección post-design (2026-07-25):** cuando se escribió esta sección se asumió, siguiendo un
hallazgo incompleto de `exploration.md`, que hoy nadie se entera cuando un `comercial` reemplaza la
comparativa vigente. **Eso era falso.** `RN-EXTRACCIONVALIDACION-012` ya está implementado
(`_notificar_reemplazo_comparativa` en `service.py`, con test propio) — el sistema ya notifica hoy.
La fase de diseño (`design.md` §6) verificó tres defectos reales en esa implementación existente:

1. Usa un insert directo a `notificaciones` (`extraccion/repository.py:crear_notificacion`) en vez
   de `notificaciones/service.py:crear_notificacion()` — no crea filas en `notificacion_entregas`,
   así que la notificación nunca sale por ningún canal.
2. Corre **antes** del flip de `validado`, sin `try/except` — un fallo deja `comparativas` +
   `ofertas_items` escritas con `validado=FALSE`, el peor estado parcial posible.
3. No excluye al usuario que hizo la validación ni filtra por `activo`.

D6 pasa a ser: **arreglar esos tres defectos**, no agregar una notificación desde cero. El texto
original que proponía `tipo="comparativa_reemplazada"` y `relaciones={"extraction_result_id": ...}`
era además técnicamente inválido — ninguno de los dos existe en el schema de `notificaciones`
(verificado contra `ck_notif_tipo` y las columnas reales de `relaciones`). Se mantiene
`tipo="comparativa_disponible"` (lo que ya usa el código) y se mantienen los tres roles que ya
notifica hoy (`admin`, `gerencia`, `lider_comercial`) — angostar a solo dos sería una regresión de
alcance sin justificación de negocio. Ver `design.md` §6 para el fix completo, verificado línea por
línea contra el schema.

### D7 — Tope de filas editables: 500, con mensaje explícito por arriba

`row_count` no tiene límite hoy y el warning del backend está en 50.000 (una escala pensada para
otra cosa). Para la tabla editable de esta pantalla, 500 filas es más que suficiente para
licitaciones/comparativas reales — documentos de ese tamaño son la excepción, no la regla. Por
arriba del tope, la pantalla no trunca en silencio: bloquea la edición y muestra un mensaje
explicando que el documento es demasiado grande para revisar fila por fila en esta versión,
dejando solo la opción de confirmar tal cual (sin editar) o rechazar. Evita truncar en silencio sin
que el usuario se entere de que hay filas que no está viendo.

## Qué se borra / deprecia — corrección al brief

**La exploración afirmó que `PATCH /api/extraction-results/{id}` "no tiene caller real". Es falso.**
Verificado: lo llama `services/extraccion/static/licitaciones.js:179` (`_patchExtraction`), servido
por la ruta viva `GET /licitaciones` (`main.py:112-114`). Lo mismo con
`GET /api/documentos/{doc_id}` y `/descargar`, llamados por `templates/historial.html:173,219,262,267`
desde la ruta viva `GET /historial`.

El diagnóstico correcto no es "código muerto" sino **funcionalidad legacy ya rota en producción**:
los tres endpoints seleccionan columnas (`client_id`, `licitacion_id`) o tablas
(`comparativas_results`, `licitaciones_results`) que no existen en el schema actual, así que fallan
en runtime cada vez que alguien usa esos paneles.

Por eso **no se borran en este change**. `carga-documentos` ya fijó la regla de no tocar el HTML
legacy vivo (commit `8de06b0`), y borrarlos acá sería sacar features que alguien todavía puede estar
clickeando, sin haber verificado con el negocio si esos paneles siguen en uso. Lo que sí entra:

- Marcarlos como deprecados en `docs/modulos/extraccion_api/` con la evidencia de que están rotos.
- Corregir `docs/modulos/extraccion_validacion/casos_de_uso.md:63`, que hoy plantea una "relación sin
  definir" entre `validar` y el PATCH: no hay relación, el PATCH no es el mecanismo de esta pantalla.
- Anotar el gap real: `extraccion-api` en `docker-compose.yml` no recibe `SUPABASE_URL` ni
  `SUPABASE_SERVICE_KEY`, así que en Docker `get_client()` devuelve `None` y **ninguna extracción se
  persiste**. Se arregla junto con el volumen (D4) — es el mismo archivo y el mismo tipo de bug.

La baja definitiva de esos tres endpoints (junto con el HTML legacy que los consume) merece su
propio change — **confirmado con el usuario (2026-07-25): `/licitaciones` y `/historial` están
abandonados**, no se usan activamente. Eso habilita la baja, pero se recomienda como change de
limpieza aparte e inmediatamente después de este (no bundlearlo acá: ya creció bastante el scope
con edición de filas, notificaciones y el fix de infra). No se toca en `validar-extraccion`.

## Módulos afectados

| Área | Impacto | Qué cambia |
|---|---|---|
| `services/presupuestacion/extraccion/` | Modificado | `models.py` (filas tipadas), `service.py` (materializar desde body), `repository.py` + `router.py` (listado, filas) |
| `frontend/src/features/validar-extraccion/` | Nuevo | Pantalla completa; recibe `NuevaLiciCotiDialog.tsx` |
| `frontend/src/lib/api/presupuestacion.ts` | Modificado | Funciones de listado, filas y validar |
| `frontend/src/features/shell/Sidebar.tsx`, `src/routes/` | Modificado | Entrada + ruta |
| `docker-compose.yml` | Modificado | Volumen compartido + env faltantes de `extraccion-api` |
| `docs/modulos/extraccion_api/`, `extraccion_validacion/` | Modificado | Deprecación documentada, corrección de `casos_de_uso.md` |
| `services/presupuestacion/notificaciones/` | Reusado, sin cambios | `service.py:crear_notificacion()` llamado desde el flujo de `validar` (D6) |

## Riesgos y rollback

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Validar con filas editadas materializa mal y no hay undo | Media | Confirmación con resumen de impacto (D5); validación de tipos en el body antes de tocar nada; el CSV crudo sobrevive para reconstruir |
| El volumen queda montado en rutas distintas y `validar` rompe en Docker | Media | Mismo mount path en ambos servicios (D4) + error de dominio claro en vez de 500 |
| Reemplazo silencioso de la comparativa vigente | Media | Advertencia explícita en el diálogo antes de confirmar |
| Regresión en los 12 tests existentes de `validar` | Baja | `filas` es opcional; el camino sin body no cambia |
| Notificación falla o no encuentra destinatarios y bloquea la validación | Baja | Fire-and-forget (D6): un error al notificar no revierte ni bloquea el flip de `validado` |

**Rollback**: el backend es aditivo (campo opcional + dos endpoints nuevos) — revertir el commit
deja `validar` exactamente como estaba. El frontend es una feature nueva aislada: se saca la ruta y
la entrada del sidebar. El volumen de `docker-compose.yml` se revierte por separado, pero conviene
dejarlo: arregla un bug que existe con o sin esta pantalla.

## Preguntas abiertas — resueltas con el usuario (2026-07-25)

1. ~~¿Un `comercial` puede validar una comparativa que reemplaza la vigente sin aviso a nadie de su
   nivel?~~ → **Resuelto, y la premisa era incorrecta: ya avisa hoy** (`RN-EXTRACCIONVALIDACION-012`).
   Lo que se agrega al scope es arreglar los 3 defectos reales encontrados en diseño (D6), no crear
   un aviso nuevo.
2. ~~¿Los paneles legacy `/licitaciones` y `/historial` siguen en uso real?~~ → **Resuelto:
   abandonados.** Habilita su baja, pero en un change de limpieza aparte (ver sección anterior).
3. ~~¿Hay un tope razonable de filas editables en pantalla?~~ → **Resuelto: sí, 500** (D7).
