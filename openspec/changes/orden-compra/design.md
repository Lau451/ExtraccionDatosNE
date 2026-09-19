# Diseño: Orden de compra

> Idioma: este documento sigue la convención ya establecida en `openspec/changes/orden-compra/`
> (proposal.md y los 4 specs están en español, igual que los comentarios del código). Registro
> neutro/profesional.

> **Revisión 2** — el dueño de producto revisó la versión 1 y corrigió tres puntos. Cambios de esta
> revisión, todos acotados a **Tramo 1 (extracción) y Tramo 2 (validación)**:
>
> | Qué cambió | Dónde |
> |---|---|
> | **D3 reescrito entero.** El anclaje por `codigo_interno` era estructuralmente imposible: es un ID nuestro y la OC la redacta el cliente. Lo reemplaza una sugerencia en 3 niveles (alias aprendido → CUIT → búsqueda manual) con confirmación humana obligatoria | **C5**, **D3**, **D3.1** (tabla `oc_cliente_alias`), **D3.2** (reúso de `GET /terceros`) |
> | **D6 parchado.** La columna de cabecera `codigo_cliente` sale del CSV; entra `cuit_cliente` | **D6** |
> | **Capacidad nueva: una OC repartida en N archivos**, con agrupación al subir y después | **D13** |
>
> **Tramo 3 (nota de pedido / Progress: D9, D10, D11, D2, D12) queda intacto** — fuera del alcance
> de esta revisión por decisión explícita del dueño de producto. Su diseño continúa después.
> Lo que sí se tocó de D12 es una nota aclaratoria sobre los endpoints nuevos, no su decisión.

> **Revisión 3** — el dueño de producto revisó la revisión 2 y aportó dos hechos sobre los
> documentos reales que **eliminan** un mecanismo, en vez de agregar uno. Cambio único y acotado:
> **cómo se reconcilian y se numeran los renglones dentro de un grupo multi-archivo**.
>
> | Qué cambió | Dónde |
> |---|---|
> | **`modo_fusion` se elimina por completo.** Desaparecen `fusionar_por_renglon`, la detección automática de modo, `modo_fusion_sugerido` y el `SelectorModoFusion` del frontend. Las filas de los N archivos **siempre se concatenan tal cual**; el usuario reconcilia los duplicados con el editor de filas que la pantalla **ya tiene** | **D13.1** (reescrito), **C10** |
> | **`oc_items.numero_renglon` pasa a ser un ordinal interno asignado por el sistema al confirmar**, nunca tomado del documento ni del payload. Desviación deliberada respecto de licitación/comparativa | **D13.1**, **D6**, § Interfaces |
> | **La columna `numero_renglon` del CSV pasa a ser opcional/vacía.** Hay OC de cliente que no declaran número de línea; la extracción **no** debe inventar uno | **D6**, **C10** |
>
> Todo lo demás queda **exactamente como estaba**: D1, D2, D3/D3.1/D3.2 (resolución de cliente),
> D4, D5, D7–D12, y el mecanismo de agrupación en sí (`grupo_id`, camino al subir y camino
> post-hoc). Esta revisión **no** rediseña la agrupación: solo cambia qué pasa con los renglones
> una vez agrupados. Neto: **un modelo, un campo de payload, un componente de frontend y una rama
> de tests menos**.

## Technical Approach

El flujo se implementa como **tres tramos independientes que comparten el modelo ya
preprovisionado de `compras/`**, sin tocar las funciones existentes `crear_orden_compra` /
`confirmar_orden_compra` / `crear_entrega`. **Una sola tabla nueva** en todo el cambio,
`oc_cliente_alias` (D3.1), más dos columnas aditivas
(`entregas_oc_items.cantidad_planificada`, `extraction_results.grupo_id`):

1. **Extracción** (`services/extraccion/`): tercer extractor Gemini (`robot_orden_compra.py`) que
   escribe un CSV plano en disco, exactamente como ya hacen licitación y comparativa. El CSV es la
   fuente de verdad; `extraction_results` solo guarda metadata. Una OC puede llegar repartida en
   **N archivos**: cada archivo se extrae por separado y los N `extraction_results` quedan unidos
   por un `grupo_id` compartido (D13).
2. **Validación** (`services/presupuestacion/extraccion/`): `_materializar_orden_compra()` como
   tercera rama de `validar_extraccion()`, anclando por `cliente_id` en lugar de
   `proceso_comercial_id`, y materializando el **plan de entregas** en `entregas_oc` /
   `entregas_oc_items` con cantidades planificadas y cero entregado. El `cliente_id` se **sugiere**
   con una resolución en 3 niveles (alias aprendido → CUIT → búsqueda manual, D3) y lo **confirma
   siempre un humano**; nada se ancla sin un click explícito.
3. **Intercambio con Progress** (`services/presupuestacion/compras/`): export CSV de nota de pedido
   (lectura pura) e import CSV de retorno que **completa en el lugar** las entregas planificadas y
   mueve stock por **delta**, reutilizando `entregar_stock_producto` y
   `_recalcular_estado_orden_compra` sin modificarlos.

El principio que ordena todo el diseño: **el plan y el hecho viven en la misma fila**. Confirmar
crea la fila de entrega con `cantidad_planificada` y `cantidad_entregada = 0`; importar el retorno
de Progress actualiza esa misma fila. Esto es lo que hace que los specs "confirmar no descuenta
stock" y "la importación descuenta stock" convivan sin duplicar filas ni inventar una tabla de
planificación paralela.

Specs cubiertos: `orden-compra-extraccion` (§ Tramo 1), `orden-compra-validacion` (§ Tramo 2),
`nota-pedido-export` y `entregas-import` (§ Tramo 3).

---

## Correcciones de hechos sobre la propuesta

Verificadas contra el código y el esquema reales durante esta fase. No invalidan la propuesta, pero
cambian el fundamento de varias decisiones y deben propagarse a tasks.

> **C5 es el hallazgo estructural de la revisión 2**: invalida por completo la premisa de anclaje de
> la propuesta y del D3 original. C6–C9 son los hechos que sostienen el D3 nuevo y el D13.
> **C10 es el hallazgo de la revisión 3** y tiene la misma forma que C5 — un dato que se daba por
> disponible en el documento del cliente y no lo está — pero su consecuencia es **quitar** un
> mecanismo, no reemplazarlo por otro.

| # | Afirmación de la propuesta | Hecho verificado | Impacto |
|---|---|---|---|
| C1 | "ya existe `uq_cli_codigo UNIQUE (drogueria_id, codigo_interno)`" en `clientes` | `codigo_interno` **no existe en `clientes`**: vive en `terceros` (`docs/schema/extractor_final.sql:126`), con `uq_terceros_codigo UNIQUE (drogueria_id, codigo_interno)` (línea 143). `clientes` es la tabla de rol, PK compartida con `terceros` vía `fk_cli_tercero (id, drogueria_id)` (línea 262) | La conclusión ("la unicidad ya existe, no hace falta esquema") **se mantiene**, pero el lookup es de dos pasos `terceros` → `clientes`, no una sola tabla. Ver D3 |
| C2 | "Se descarta `UNIQUE ... NULLS NOT DISTINCT` porque no se pudo confirmar la versión de Postgres" | La versión **sí está confirmada: PostgreSQL 15+**. `supabase/migrations/0024_terceros_cuit_no_exclusivo.sql:25-30` aborta con `RAISE EXCEPTION` si `server_version_num < 150000`, y esa migración ya está aplicada | Los índices parciales **siguen siendo la elección correcta**, pero por una razón mejor y verificable. Ver D5 |
| C3 | (implícito) el CSV de licitación/comparativa alcanza para OC | El CSV de licitación/comparativa es **una fila por renglón sin cabecera de documento**. Una OC tiene cabecera (`numero_oc`, cliente, fecha, dirección) + renglones + plan de entregas | El CSV de OC desnormaliza la cabecera y el payload de validación **no** usa el campo `filas` existente. Ver D6 y D7 |
| C4 | `docs/schema/extractor_final.sql` está desactualizado solo para `clientes` | También lo está para `ordenes_compra`: `idx_oc_activos` (línea 1784) y `idx_oc_createdby/updatedby/deletedby` (1805-1807) referencian `deleted_at`/`created_by`/`updated_by`/`deleted_by`, columnas que el `CREATE TABLE` de la línea 1016 no lista | Sin impacto funcional en este cambio, pero la migración 0025 **no debe** asumir el `CREATE TABLE` del snapshot: se verifica contra la base viva antes de aplicar |
| **C5** | "la OC trae el `codigo_interno` del cliente; el anclaje se resuelve con `uq_terceros_codigo (drogueria_id, codigo_interno)`" (premisa de la propuesta y del **D3 original**) | **Estructuralmente imposible.** `terceros.codigo_interno` es un identificador que *nosotros* le asignamos al tercero dentro de *nuestra* droguería (`0024_terceros_cuit_no_exclusivo.sql:85-91` lo escribe desde `codigo_legacy` del import legado de Nueva Era; `frontend/src/lib/api/terceros.ts:10` lo declara `string \| null` y opcional al alta). La OC la **redacta el cliente**: el documento no puede contener un ID de nuestro sistema que el cliente no conoce. El `uq_terceros_codigo` existe y es correcto, pero **no hay dato de entrada que lo consulte** | **D3 se reescribe entero.** Desaparecen `buscar_cliente_por_codigo_interno()`, `GET /clientes/por-codigo-interno`, `ClientePorCodigoOut` y el campo `codigo_cliente` del CSV (D6). El anclaje pasa a ser una **sugerencia en 3 niveles con confirmación humana obligatoria** (D3) |
| **C6** | (implícito en el D3 original y en la corrección conversacional) "un CUIT identifica a un único cliente" | **Falso por diseño ya desplegado.** `supabase/migrations/0024_terceros_cuit_no_exclusivo.sql` agregó `terceros.cuit_no_exclusivo BOOLEAN NOT NULL DEFAULT FALSE` y redefinió el índice como `uq_terceros_cuit ON terceros (drogueria_id, cuit) WHERE cuit IS NOT NULL AND deleted_at IS NULL AND NOT cuit_no_exclusivo` (líneas 36-39). El comentario de la migración da los casos reales: hospitales bajo el CUIT del Ministerio de Salud provincial, estaciones de servicio bajo el CUIT de la petrolera — decenas de cuentas distintas, con entrega y facturación separadas, bajo un CUIT fiscal compartido | La consulta por CUIT del **nivel 2** de D3 puede devolver legítimamente **0, 1 o N filas**. N filas obliga a una lista de candidatos, no a un "match único". Es también el caso que el **nivel 1** (alias aprendido) desambigua de forma permanente |
| **C7** | "`GET /terceros` ya tiene paginación y búsqueda server-side (commit `9cb771e`); se reutiliza tal cual" | **Cierto en el contrato, con dos matices reales.** (i) La **búsqueda** sí baja a PostgREST: `identidad/repository.py:51-56` arma `.or_(razon_social.ilike.%q%,cuit.ilike.%q%,codigo_interno.ilike.%q%)`. (ii) La **paginación no baja a la base**: `repository.listar_terceros` trae *todas* las filas que matchean recorriendo páginas PostgREST de 1000 (líneas 40-66) y `service.listar_terceros_paginado:101-107` recorta en Python. (iii) `_coincide_filtro_rol` (`service.py:72-81`) es **excluyente**: `rol='clientes'` significa `tiene_cliente AND NOT tiene_proveedor`, así que un tercero con ambos roles **queda fuera** | Se reutiliza igual — no se crea endpoint nuevo — pero el picker de OC llama con `rol='todos'` y filtra por `tiene_rol_cliente` en el cliente (usar `rol='clientes'` ocultaría clientes que además son proveedores), y **exige `q` no vacío** para no pagar el barrido completo de los 5541 terceros en cada apertura de la pantalla. Ver D3.2 |
| **C8** | (implícito en la capacidad nueva) "se suben N archivos en una sola acción y llegan fusionados a validación" | `POST /procesar` (`services/extraccion/main.py:152-161`) acepta **exactamente un** `archivo: UploadFile`, responde un fragmento HTML **sin el `extraction_id`**, y la fila de `extraction_results` se escribe **después de la respuesta**, en un `BackgroundTask` (`schedule_persist_output`, líneas 269-281). `FormCard.tsx:23-32` ya convive con eso haciendo polling hasta ver crecer el listado | La agrupación **no puede** resolverse devolviendo ids desde un request multi-archivo sin reescribir `/procesar`. D13 invierte la dirección: el **cliente genera el `grupo_id`** (UUID v4) y lo manda como campo de formulario en cada uno de los N `POST /procesar`; upload-time y post-hoc terminan compartiendo **un solo mecanismo** |
| **C9** | (implícito) "hay que definir una normalización de texto nueva para la clave de alias" | Ya existe `services/presupuestacion/core/texto.py::normalizar_descripcion` — NFKD → ASCII (saca tildes), `[^\w\s] → " "`, colapso de espacios, `.strip().upper()`. La usan `matching/service.py` y `extraccion/service.py:236`, y `items_proceso.descripcion_normalizada` la persiste | **No se inventa nada.** `texto_extraido_normalizado` de `oc_cliente_alias` usa **esa misma función**, sin copiarla ni parametrizarla. Ver D3.1 |
| **C10** | "el `numero_renglon` del documento es un dato confiable, y la forma en que se reparten los renglones entre los N archivos de un grupo es detectable automáticamente" (premisa del `modo_fusion` de la **revisión 2**) | **Falso por dos lados, confirmado por el dueño de producto.** (i) **No hay patrón detectable**: una OC real partida puede traer renglones **distintos** en cada archivo, o **los mismos** renglones repetidos con distinta fecha de entrega. Las dos formas conviven y ninguna señal estructural las distingue. (ii) **Hay documentos de OC de cliente que directamente no declaran número de línea** — no existe campo sobre el cual matchear. La detección de `fusionar_por_renglon` comparaba conjuntos de `numero_renglon` que en esos documentos están vacíos, así que su heurística de "conjuntos idénticos" degeneraba a comparar dos conjuntos vacíos y sugerir fusionar todo. Contraste verificado: en licitación el `item` **sí** es confiable y el código lo consume sin fallback (`extraccion/service.py:164` lo exige entero y `:234` hace `int(fila["item"].strip())`), pero ese es un documento **nuestro**; la OC la redacta el cliente | **`modo_fusion` se elimina entero** (D13.1): sin patrón que detectar no hay modo que sugerir, y sin campo que matchear no hay fusión que hacer. Se concatena siempre y **reconcilia el humano**. Como corolario, el `numero_renglon` del documento deja de ser apto para persistirse: `oc_items.numero_renglon` pasa a ser un **ordinal interno asignado al confirmar** (D13.1), y la columna del CSV pasa a **opcional** (D6) |

---

## Architecture Decisions

### D1 — El plan de entregas y la entrega real comparten fila (`cantidad_planificada`)

**Choice**: agregar `entregas_oc_items.cantidad_planificada NUMERIC(12,2) NOT NULL DEFAULT 0`.
Confirmar la OC inserta filas de `entregas_oc` (`estado='pendiente'`) y de `entregas_oc_items` con
`cantidad_planificada = <lo planificado>`, `cantidad_entregada = 0`, `cantidad_rechazada = 0`.
Importar el retorno de Progress **actualiza** esas mismas filas.

**Alternatives considered**:
- *(a)* No crear `entregas_oc` al confirmar; que las filas nazcan recién al importar, vía
  `crear_entrega`. **Rechazada**: el spec `orden-compra-validacion` exige explícitamente filas de
  `entregas_oc` al confirmar ("THEN se crean las filas correspondientes en `ordenes_compra`,
  `oc_items` y `entregas_oc`"), y el Success Criteria de la propuesta pide que esas filas sumen la
  cantidad completa de cada línea. Sin filas al confirmar, no hay nota de pedido que exportar.
- *(b)* Crear filas de plan al confirmar y, al importar, llamar a `crear_entrega` tal cual.
  **Rechazada**: `crear_entrega` calcula `numero_entrega = len(entregas_previas) + 1`
  (`compras/service.py:237`), así que con 3 entregas planificadas la primera importación crearía la
  entrega **#4**. El resultado serían 6 filas para 3 entregas reales, con las 3 del plan colgadas en
  `'pendiente'` para siempre y `uq_eoc (orden_compra_id, numero_entrega)` desalineado respecto del
  `numero_entrega` que viaja en el CSV a Progress.
- *(c)* Derivar la cantidad planificada en runtime desde `oc_items.cantidad / cantidad_entregas`.
  **Rechazada**: el spec permite al usuario cargar entregas a mano y con desglose por línea, así que
  el plan no siempre es derivable de forma determinista.

**Rationale**: una columna aditiva con `DEFAULT 0` es retrocompatible con `crear_entrega` (que no la
escribe y por lo tanto deja 0 = "no planificada, registrada directo"), no toca ninguna RLS ni FK, y
convierte la conciliación plan-vs-real en una resta dentro de la misma fila en lugar de un join
entre dos poblaciones de filas que hay que distinguir por convención.

### D2 — `crear_entrega` no se modifica, pero tampoco es la función que usa el import

**Choice**: el import usa una función nueva `registrar_entrega_importada()` en
`compras/service.py`, que hace `UPDATE` sobre las filas planificadas y reutiliza **sin cambios**
`stock.entregar_stock_producto()` y `_recalcular_estado_orden_compra()`.

**Alternatives considered**: llamar a `crear_entrega` desde el import (ver D1(b)); o modificar
`crear_entrega` para que acepte un `entrega_oc_id` existente. **Rechazadas**: la primera rompe la
numeración; la segunda viola el "se reutiliza sin cambios" de la propuesta y le agrega un modo a una
función que hoy tiene una sola semántica clara ("registro de algo que ya ocurrió físicamente", su
propio docstring en `compras/service.py:207-217`).

**Rationale**: la propuesta pide reutilizar *el mecanismo* `crear_entrega → entregar_stock_producto`.
Este diseño reutiliza literalmente el tramo que importa (`entregar_stock_producto`,
`_recalcular_estado_orden_compra`, `_calcular_estado_entrega` como referencia) y deja
`crear_entrega` intacta para su caller actual, `POST /ordenes-compra/{id}/entregas`. **Desviación
explícita y consciente respecto de la letra de la propuesta**; el motivo es el conflicto de
numeración documentado en D1(b).

### D3 — El cliente se **sugiere** en 3 niveles; la confirmación es siempre humana

> **Reemplaza por completo al D3 original** ("lookup de cliente por `codigo_interno` en dos pasos").
> Ver C5: esa decisión partía de un dato que el documento del cliente no puede contener.

**Choice**: un resolvedor server-side de un solo viaje,
`resolver_cliente_candidato(client, *, drogueria_id, cuit_extraido, texto_extraido)
-> CandidatoClienteOut`, que corre al abrir la pantalla de validación y devuelve **una sugerencia,
una lista corta de candidatos, o nada**. Nunca escribe. Nunca ancla. El `cliente_id` que viaja en
`POST /extracciones/{id}/validar` es siempre el que el usuario **confirmó con un click**.

Tres niveles, evaluados en orden y con cortocircuito:

| Nivel | Fuente | Entrada | Resultado | Confianza |
|---|---|---|---|---|
| **1** | `oc_cliente_alias` (tabla nueva, D3.1) | `normalizar_descripcion(razon_social_cliente)` | Match exacto por índice único → **1 cliente** | `alias` — la más alta: alguien ya confirmó este texto |
| **2** | `terceros` ⋈ `clientes` por CUIT | `cuit_cliente` normalizado a 11 dígitos | 1 fila y `NOT cuit_no_exclusivo` → **1 cliente**. N filas (solo posible con `cuit_no_exclusivo`, C6) → **lista de candidatos** | `cuit` / `cuit_compartido` |
| **3** | — | — | Nada. El usuario busca a mano contra `GET /terceros` (D3.2) | `ninguna` |

**El gate humano es el mismo en los tres niveles.** Un nivel 1 con match exacto también exige el
click de confirmación: la pantalla lo muestra preseleccionado con el botón "Confirmar cliente"
habilitado, no lo da por hecho. Esto es literalmente el mismo principio que ya gobierna el resto de
este documento ("la pantalla de validación *es* la compuerta humana", D4) y el mismo que
`ProcesoComercialSelector.tsx` aplica hoy para licitación/comparativa — verificado: es un `<select>`
manual de 46 líneas, **sin matching automático de ningún tipo**.

**La única diferencia con `ProcesoComercialSelector` es la escala, y es la que justifica los 3
niveles**: los procesos comerciales abiertos son decenas y entran en un `<select>`; los clientes son
**5541 filas** — exactamente el motivo por el que `GET /terceros` necesitó paginación y búsqueda la
semana pasada (`9cb771e`). Un `<select>` de 5541 opciones no es usable. Los 3 niveles no existen
para sacarle la decisión al humano: existen para que, en el caso frecuente, el humano confirme en
vez de buscar.

**Alternatives considered**:

- *(a)* Match difuso sobre `razon_social` con `rapidfuzz`, reutilizando el motor de
  `matching/service.py`. **Rechazada como nivel automático**: ese motor está calibrado para
  descripciones de productos contra un catálogo, y su umbral produce falsos positivos plausibles.
  Un falso positivo acá no es un renglón mal matcheado: es **una OC entera anclada al cliente
  equivocado**, con su plan de entregas y su nota de pedido a Progress. El alias aprendido (nivel 1)
  da el mismo beneficio con match **exacto** y cero riesgo de confusión. La búsqueda difusa queda
  disponible donde es inofensiva: el `q` de `GET /terceros`, que el usuario dispara y evalúa.
- *(b)* Solo CUIT, sin tabla de alias. **Rechazada**: no resuelve el caso multi-sede de C6 —
  20 hospitales bajo el CUIT del Ministerio devuelven 20 candidatos **todas las veces**, para
  siempre. El alias convierte esa elección en un hecho aprendido: cada sede escribe su propio
  encabezado, y a la segunda OC de esa sede el nivel 1 la resuelve sola.
- *(c)* Solo alias, sin CUIT. **Rechazada**: no arranca. Con la tabla vacía, las primeras N OC de
  cada cliente caen todas al nivel 3.
- *(d)* Auto-confirmar cuando el nivel 1 matchea. **Rechazada**: rompe el invariante del documento.
  Un alias puede haber sido confirmado con un error, o el encabezado puede haber sido reutilizado
  por otra entidad; el costo de un click es despreciable frente al de una OC mal anclada.
- *(e)* `GET /clientes/por-codigo-interno`. **Eliminada, no rechazada** — ver C5, no tiene entrada
  posible.

**Rationale**: el sistema aprende del único dato confiable que existe (lo que un humano ya
confirmó), usa el CUIT como red de arranque porque en una OC argentina **siempre** está — es
obligatorio legalmente y es un dato mucho más estable que la razón social en texto libre — y degrada
a búsqueda manual sin inventar nada. El costo de estar equivocado es un click, nunca un dato mal
escrito.

**Semántica de errores** (resuelve y corrige el spec `orden-compra-validacion`):

| Situación | Comportamiento | HTTP |
|---|---|---|
| Ni alias ni CUIT resuelven | `CandidatoClienteOut(origen="ninguno", candidatos=[])` — **no es un error** | 200 |
| CUIT extraído malformado (≠ 11 dígitos tras normalizar) | Se saltea el nivel 2, se registra en `advertencias[]` de la respuesta | 200 |
| El CUIT resuelve a un tercero **sin** fila en `clientes` | Candidato omitido, `advertencias += "el CUIT corresponde a un tercero que no es cliente"` | 200 |
| El CUIT resuelve a un cliente con `activo = false` | Candidato **incluido** pero marcado `activo=false`; el front lo muestra deshabilitado con el motivo | 200 |
| `cliente_id` confirmado que no existe / no es cliente / es de otra droguería | `ValidationError` en `_validar_orden_compra_override`, **antes del primer write** | 422 |

> El escenario "`codigo_interno` ambiguo" del spec `orden-compra-validacion` queda **sin premisa**
> (C5). No se reemplaza por "ambigüedad de CUIT": la ambigüedad de CUIT no es un error sino un
> resultado legítimo del nivel 2 (C6), que se resuelve con una lista de candidatos. El spec debe
> reconciliarse al archivar.

### D3.1 — `oc_cliente_alias`: el sistema aprende de cada confirmación

**Choice**: tabla nueva `oc_cliente_alias`, una fila por `(drogueria_id, texto_extraido_normalizado)`,
escrita por UPSERT **dentro de la misma transacción lógica de la confirmación**, después de que
`_materializar_orden_compra()` haya tenido éxito.

| Columna | Tipo | Nota |
|---|---|---|
| `id` | `UUID PK DEFAULT gen_random_uuid()` | |
| `drogueria_id` | `UUID NOT NULL` | FK → `droguerias(id)`; alcance del alias |
| `texto_extraido_normalizado` | `TEXT NOT NULL` | Clave de match. Ver normalización abajo |
| `texto_extraido_original` | `TEXT NOT NULL` | Solo para auditoría/debug: qué dijo el documento antes de normalizar |
| `cliente_id` | `UUID NOT NULL` | FK compuesta `(cliente_id, drogueria_id) → clientes (id, drogueria_id)` |
| `veces_confirmado` | `INTEGER NOT NULL DEFAULT 1` | Se incrementa en cada reconfirmación; señal de madurez del alias |
| `created_at` / `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | |
| `created_by` / `updated_by` | `UUID NULL` | Quién lo enseñó / quién lo corrigió por última vez |

Restricción: `CONSTRAINT uq_oca UNIQUE (drogueria_id, texto_extraido_normalizado)`. **La última
confirmación gana**: si el usuario corrige el cliente de un texto ya conocido, el UPSERT pisa
`cliente_id`, resetea `veces_confirmado = 1` y actualiza `updated_by`. Resetear (en vez de
incrementar) es deliberado: un alias corregido es un alias nuevo, y su contador no debe heredar la
confianza acumulada del mapeo equivocado.

**Normalización** — se reutiliza `normalizar_descripcion` de `services/presupuestacion/core/texto.py`
**sin modificarla ni copiarla** (C9). Ya hace exactamente lo pedido y algo más:

```python
# services/presupuestacion/core/texto.py (existente, NO se toca)
def normalizar_descripcion(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    sin_puntuacion = re.sub(r"[^\w\s]", " ", sin_tildes)
    return re.sub(r"\s+", " ", sin_puntuacion).strip().upper()
```

| Requisito | Cubierto por |
|---|---|
| minúsculas/mayúsculas indistintas | `.upper()` (normaliza hacia arriba, no hacia abajo — da igual, es consistente) |
| trim | `.strip()` |
| sin tildes | `NFKD` + `encode("ascii", "ignore")` |
| espacios colapsados | `re.sub(r"\s+", " ")` |
| puntuación indistinta (`S.A.` vs `SA`, `HOSPITAL - SEDE 2`) | `re.sub(r"[^\w\s]", " ")` — **beneficio extra**, no pedido pero correcto acá |

`"Hospital Público Ñandú S.A. - Sede Nº2"` → `"HOSPITAL PUBLICO NANDU S A SEDE N 2"`.

**Alternatives considered**:
- Una función de normalización propia en `extraccion/`. **Rechazada**: duplica una función probada
  y usada por matching y por `items_proceso.descripcion_normalizada`; dos normalizadores que derivan
  es exactamente el bug que nadie encuentra.
- Índice `UNIQUE` sobre una expresión (`lower(unaccent(texto))`) en vez de una columna materializada.
  **Rechazada**: `unaccent` es una extensión que habría que habilitar, y la normalización quedaría
  partida entre Python (al leer) y SQL (al escribir), con reglas que pueden divergir. Columna
  materializada + una sola función Python = una sola definición.
- Guardar el alias a nivel `terceros` en vez de una tabla propia. **Rechazada**: el alias es
  conocimiento del pipeline de OC (qué encabezado de documento corresponde a qué cliente), no un
  atributo de identidad del tercero; meterlo en `terceros` lo expondría a los otros ~12 consumidores
  de esa tabla.

**RLS** — la tabla es nueva, así que **sí hay RLS nueva que habilitar**, siguiendo la convención
literal del proyecto (`mismo_tenant(drogueria_id)` + `get_rol()` + `es_superadmin()` para DELETE,
igual que `terceros`/`tercero_direcciones` en `0008_terceros_modelo.sql:608-638`), más los GRANT
explícitos que Supabase no genera solo. SQL completo en § Migration.

**Índice**: `uq_oca (drogueria_id, texto_extraido_normalizado)` **es** el índice del nivel 1 — un
lookup por igualdad exacta sobre la clave única, sin índice adicional. Se agrega
`idx_oca_cliente (drogueria_id, cliente_id)` solo para poder listar/limpiar los alias de un cliente
al darlo de baja.

### D3.2 — La búsqueda manual reutiliza `GET /terceros`; no se crea endpoint nuevo

**Choice**: el nivel 3 de D3 (y el "rechazar la sugerencia" de los niveles 1 y 2) usa el buscador ya
existente: `GET /terceros?q=...&rol=todos&page=1&page_size=20`, vía `listarTerceros()` de
`frontend/src/lib/api/terceros.ts:210-217`. No se agrega endpoint, no se agrega repository, no se
agrega modelo de respuesta.

**Dos ajustes obligados por C7**, ambos del lado del llamador:

1. **`rol='todos'`, nunca `rol='clientes'`.** `_coincide_filtro_rol` (`identidad/service.py:72-81`)
   define `clientes` como `tiene_cliente AND NOT tiene_proveedor`. Un hospital que también nos vende
   algo quedaría **invisible** para el picker de OC. Se pide `todos` y se filtra en el front por
   `tiene_rol_cliente === true`, que es el flag que el propio listado ya devuelve
   (`identidad/service.py:51-59`).
2. **`q` obligatorio, mínimo 2 caracteres, debounce 300 ms.** La paginación de ese endpoint **no
   baja a la base** (C7-ii): sin `q` cada apertura del picker barre las 5541 filas de la droguería.
   Con `q`, el `.or_(...ilike...)` de `repository.py:51-56` corre en Postgres y lo que vuelve a
   Python es ya el subconjunto. El picker arranca vacío con el placeholder "Buscá por razón social,
   CUIT o código", no con un listado inicial.

**Alternatives considered**:
- Un `GET /clientes/buscar` nuevo, específico de OC. **Rechazada**: duplicaría el filtro `ilike` y
  la sanitización PostgREST (`_sanitizar_termino_or`, `repository.py:24-28`) que ya existen y están
  probadas, para un contrato idéntico. El instinto de "un endpoint por pantalla" es justamente lo
  que este repo evita.
- Arreglar la paginación de `GET /terceros` para que baje a la base (`.range()` + `count='exact'`)
  como parte de este cambio. **Rechazada por alcance**: es una mejora real y está anotada como
  trabajo futuro en Open Questions, pero es un cambio de un módulo ajeno (`services/terceros/`) con
  sus propios consumidores (el picker de proveedores de PCP pide `page_size=5000` a propósito,
  `identidad/router.py:50-54`). Mezclarla acá agranda el blast radius de una OC.
- `rol='clientes'` + aceptar el falso negativo. **Rechazada**: silencioso y sin señal para el
  usuario, que vería "no hay resultados" para un cliente que existe.

**Rationale**: la infraestructura correcta ya está en producción desde hace una semana. Lo que este
diseño aporta no es un buscador nuevo, sino **saber exactamente cómo llamarlo** — y los dos matices
de C7 son precisamente el tipo de detalle que, sin leer el código, se descubre en producción.

### D4 — La OC de extracción nace `emitida`, no `pendiente`

**Choice**: `_materializar_orden_compra()` inserta `ordenes_compra` con `estado='emitida'`
directamente. `confirmar_orden_compra()` **no** participa de esta ruta.

**Alternatives considered**: crear en `'pendiente'` y exigir un segundo paso por
`POST /ordenes-compra/{id}/confirmar`. **Rechazada**: (i) la pantalla de validación de extracción ya
*es* la compuerta humana — un segundo botón "confirmar" sobre lo mismo no agrega control;
(ii) `confirmar_orden_compra` recorre `oferta_item_id` para marcar ofertas adjudicadas
(`compras/service.py:121-131`), lógica que en una OC *de cliente* no tiene ningún
`oferta_item_id` que tocar; (iii) `crear_entrega` y el import exigen
`estado in ('emitida','en_entrega','parcialmente_entregada')` (`_ESTADOS_PARA_ENTREGA`), así que una
OC en `'pendiente'` no podría recibir su propio retorno de Progress.

**Rationale**: el estado refleja el hecho de negocio real — la OC del cliente ya fue emitida por el
cliente; nosotros la estamos registrando, no emitiéndola. Consecuencia aceptada y documentada:
`POST /ordenes-compra/{id}/confirmar` rechaza con `ConflictError` una OC originada en extracción,
que es la respuesta correcta ("ya está confirmada").

Auditoría: se registra `registrar_evento_ciclo_vida(entidad="orden_compra", tipo_cambio="creacion",
origen="usuario")` igual que `crear_orden_compra`, más un `registrar_cambio` de `estado`
`None → 'emitida'` para dejar rastro de que nació emitida.

### D5 — Dos índices únicos parciales (confirmado, con fundamento corregido)

**Choice**: la propuesta. Se elimina `uq_oc` y se crean `uq_oc_por_cliente` y `uq_oc_por_proceso`.

**Alternatives considered**: `UNIQUE (drogueria_id, cliente_id, numero_oc, version_numero) NULLS NOT
DISTINCT`. **Rechazada — y ahora por el motivo correcto**: PostgreSQL 15+ **está confirmado**
(C2), así que `NULLS NOT DISTINCT` *está disponible*. Se descarta igual porque es **semánticamente
incorrecto**: trataría todas las filas con `cliente_id IS NULL` como un único cubo, fusionando en un
solo alcance de unicidad a todas las OC ancladas por proceso comercial sin distinguir *qué* proceso
— exactamente el falso conflicto entre entidades no relacionadas que se quería evitar. Los índices
parciales dan un alcance distinto por ruta de anclaje, que es lo que el dominio pide.

**Rationale**: además, crear los índices es seguro sin verificación previa de duplicados: `uq_oc`
es `(numero_oc, version_numero)` **global**, y ambos alcances nuevos lo contienen como prefijo
lógico más restrictivo por el lado del scope. Cualquier par único globalmente sigue siendo único
dentro de cualquier subconjunto. El riesgo listado en la propuesta ("la creación falla si ya existen
filas que colisionan") es, formalmente, imposible en esa dirección. El riesgo real vive en la
**migración inversa**, donde sí hay que resolver duplicados.

### D6 — El CSV de extracción de OC desnormaliza la cabecera; las entregas viajan en una columna compuesta

**Choice**: una fila por renglón. Los campos de cabecera se repiten en cada fila. El plan de
entregas por línea viaja en una única columna `entregas` con gramática estricta.

```
numero_oc;fecha_emision;cuit_cliente;razon_social_cliente;direccion_entrega;cantidad_entregas;numero_renglon;descripcion;cantidad;precio_unitario;entregas
```

**Cambio respecto de la primera versión de este diseño**: la columna de cabecera `codigo_cliente`
**se elimina** y se reemplaza por `cuit_cliente`. Motivo en C5: `codigo_interno` es un identificador
nuestro y no puede aparecer en un documento que redacta el cliente — la columna nunca habría traído
un valor. `cuit_cliente` sí: en una OC argentina el CUIT del comprador es obligatorio.

| Campo de cabecera | Rol | Obligatorio para confirmar |
|---|---|---|
| `numero_oc` | Clave de negocio; entra en `uq_oc_por_cliente` (D5) | sí |
| `fecha_emision` | Base de cálculo de `fecha_entrega_planificada` | no (default: fecha de confirmación) |
| `cuit_cliente` | **Nivel 2** de la resolución de cliente (D3) | no — es una pista, no un ancla |
| `razon_social_cliente` | **Nivel 1** de D3 (clave del alias, tras `normalizar_descripcion`) y texto que el operador lee para confirmar la sugerencia | no — misma razón |
| `direccion_entrega` | Dato documental de la OC | no |
| `cantidad_entregas` | Cuántas entregas declara el documento; alimenta D8 | no (default 1) |

| Campo de renglón | Rol | Obligatorio para confirmar |
|---|---|---|
| `numero_renglon` | **Solo referencia visual** (C10). Es el número de línea **tal como lo declara el documento**, si lo declara. Ayuda al operador a reconocer a ojo que una fila del archivo 2 es la misma línea que una del archivo 1. **No se persiste**: `oc_items.numero_renglon` es un ordinal que asigna el sistema al confirmar (D13.1) | **no — puede venir vacío** |
| `descripcion` | Texto del renglón | sí |
| `cantidad` | Cantidad del renglón | sí |
| `precio_unitario` | Precio unitario | sí (si la extracción no lo detecta, lo carga el operador) |
| `entregas` | Desglose del plan por línea; gramática abajo | no (vacío = sin desglose) |

**`numero_renglon` es opcional y nullable a propósito** (C10): hay OC de cliente que no declaran
número de línea en ninguna forma. El prompt del extractor debe **dejar la celda vacía** cuando el
documento no lo declara, y tiene prohibido derivarlo, inferirlo o autoincrementarlo para rellenar el
hueco — un número inventado es indistinguible de uno real y el operador lo leería como si el
documento lo dijera. Vacío es un valor válido y no hace fallar la extracción ni la confirmación.
Esto vale para el golden fixture correspondiente: debe existir al menos un caso **sin** número de
línea.

Ninguno de los dos campos de cliente es obligatorio en el CSV, y es deliberado: si Gemini no los
detecta, la extracción **no falla** — el usuario cae al nivel 3 de D3 y busca a mano. Extraer mal el
CUIT degrada la comodidad, nunca la corrección, porque el ancla real es el click de confirmación.

El CUIT se normaliza a 11 dígitos (se le sacan guiones, puntos y espacios) antes de consultar; si lo
extraído no llega a 11 dígitos se saltea el nivel 2 en silencio y se anota en `advertencias[]`.

Gramática de `entregas` (vacío = el documento no declara desglose para esa línea):

```
entregas   := plan ("|" plan)*
plan       := cantidad "@" plazo_dias
cantidad   := decimal con "." o "," como separador
plazo_dias := entero >= 0
```

Ejemplo: `50@30|50@60` = 50 unidades a 30 días, 50 a 60 días.

Ejemplo completo de las dos formas que admite `numero_renglon` — las dos son válidas y producen la
misma OC, porque el número persistido no sale de acá (D13.1):

```csv
numero_oc;fecha_emision;cuit_cliente;razon_social_cliente;direccion_entrega;cantidad_entregas;numero_renglon;descripcion;cantidad;precio_unitario;entregas
OC-4471;12/09/2026;30712345679;HOSPITAL SAN ROQUE;Av. Siempreviva 742;2;1;IBUPROFENO 400MG X 20;100;1250,00;50@30|50@60
OC-4471;12/09/2026;30712345679;HOSPITAL SAN ROQUE;Av. Siempreviva 742;2;2;AMOXICILINA 500MG X 16;80;980,50;
OC-9012;03/09/2026;30555555553;CLINICA DEL SOL;Ruta 9 km 12;1;;GASA ESTERIL 10X10;40;320,00;
OC-9012;03/09/2026;30555555553;CLINICA DEL SOL;Ruta 9 km 12;1;;ALCOHOL EN GEL 250ML;25;410,00;
```

Las dos últimas filas son un documento que **no declara número de línea**: la celda va vacía, sin
comilla, sin cero y sin autoincremento. Al confirmar recibirán `numero_renglon` 1 y 2 igual que las
dos primeras, asignados por el sistema.

**Alternatives considered**:
- *(a)* Dos CSV (cabecera + renglones) **para un mismo documento**. **Rechazada**:
  `extraction_results` tiene **una** columna `csv_disk_path` y `_leer_filas_csv_con_columnas` lee
  **un** archivo; soportar dos archivos por fila obliga a cambiar el contrato de lectura para los
  tres tipos de documento.
  > Esto **no** contradice a D13, que también lee N archivos. La diferencia es dónde vive la
  > pluralidad: D13 tiene **N filas de `extraction_results`, cada una con su `csv_disk_path` único**,
  > y llama N veces a la función sin modificarla. La alternativa (a) pedía **una fila con dos
  > archivos**, que sí rompe el contrato. El contrato que se preserva es
  > `csv_disk_path → list[dict[str,str]]`, no "un CSV por sesión de validación".
- *(b)* Una fila por (renglón × entrega). **Rechazada**: multiplica las filas y rompe el modelo
  mental de la tabla editable (`useFilasEditables` asume una fila = un renglón editable), además de
  inflar `row_count` respecto de los renglones reales de la OC.
- *(c)* JSON en disco en vez de CSV. **Rechazada**: rompería la simetría con los otros dos tipos y
  obligaría a bifurcar `_leer_filas_csv_con_columnas`.

**Rationale**: la desnormalización es el costo mínimo para no tocar el contrato
`csv_disk_path → list[dict[str,str]]` que comparten los tres tipos. La columna compuesta es un olor
reconocido y se mitiga con un parser dedicado y aislado (`parsear_plan_entregas`) más sus tests RED
— es la única columna de todo el pipeline con estructura interna.

Formato del CSV en disco: `;` como delimitador, UTF-8, `csv.QUOTE_MINIMAL` — idéntico a
`robot_comparativas.py:850-859`.

### D7 — El payload de validación de OC es un bloque propio, no el campo `filas`

**Choice**: `ValidarExtraccionRequest` gana un campo nuevo `orden_compra: OrdenCompraOverride |
None`. El campo `filas` existente **no** se extiende a una tercera forma.

**Alternatives considered**: agregar `list[FilaOrdenCompraIn]` a la unión de `filas` y extender
`_validar_filas_override`. **Rechazada**: esa función discrimina la forma con
`es_comparativa != ("renglon" in filas[0])` (`extraccion/service.py:152`) — un booleano que ya está
al límite con dos formas y se vuelve incorrecto con tres. Además, la OC necesita cabecera y plan de
entregas, que no son "filas" bajo ninguna lectura.

**Rationale**: campos distintos para semánticas distintas. `_validar_filas_override` queda
literalmente intacta (su contrato de dos formas sigue siendo cierto), y la validación de OC vive en
su propia función pura `_validar_orden_compra_override`, corrida también **antes del primer write**,
igual que el invariante que ya protege §3 del diseño de `validar-extraccion`.

### D8 — Resolución de OQ #1: reparto parejo con resto al frente

**Choice**: cuando el documento declara solo la *cantidad* de entregas (sin desglose por línea), la
cantidad de cada renglón se reparte así:

- Si la cantidad es **entera**: `base = cantidad // N`, `resto = cantidad % N`. Las **primeras
  `resto` entregas** reciben `base + 1`; las restantes, `base`.
- Si la cantidad tiene **decimales**: las primeras `N-1` entregas reciben
  `quantize(cantidad / N, 0.01, ROUND_DOWN)` y la **última** recibe
  `cantidad - base * (N - 1)`.

**Alternatives considered**:
- Resto en la última entrega también para enteros. **Rechazada**: con 100 unidades en 3 entregas
  daría 33/33/34 igual de parejo, pero si el cronograma se corta antes el cliente recibió menos; al
  frente recibió más. Además, "lo más parejo posible" se cumple igual (diferencia máxima entre dos
  entregas = 1 unidad) en ambos, así que desempata el criterio de negocio.
- División decimal pura (`100 / 3 = 33.33` en las tres). **Rechazada**: no suma
  (`33.33 × 3 = 99.99`) y produce fracciones de unidad no entregables para medicamentos.

**Rationale**: determinista, reproducible, auditable, y garantiza el invariante duro del Success
Criteria — `sum(cantidad_planificada por renglón) == oc_items.cantidad` exactamente, sin depender de
redondeo de punto flotante (se usa `Decimal`, como ya hace todo `compras/service.py`). La asimetría
del caso decimal (resto al final, no al frente) es deliberada: ahí el resto es residuo de redondeo a
centésimos, no unidades enteras, y ponerlo al final evita arrastrar el error.

Invariante verificado en `_validar_orden_compra_override` **antes de escribir**: si el usuario carga
el desglose a mano y la suma no coincide con `cantidad` del renglón, `ValidationError` con el detalle
por línea.

### D9 — Resolución de OQ #2: cumplimiento parcial se mide contra el plan, y no se replanifica solo

**Choice**: el `estado` de la entrega importada se calcula comparando lo aceptado contra
`cantidad_planificada`:

| Condición (sobre todas las líneas de la entrega) | `entregas_oc.estado` |
|---|---|
| `cantidad_entregada == 0` en todas | `pendiente` (sin cambio) |
| `entregada > 0` en alguna y `aceptada == 0` en todas las que tienen entrega | `rechazada` |
| `aceptada >= planificada` en todas | `entregada` |
| Cualquier otro caso (alguna línea con `0 < aceptada < planificada`, o mezcla) | `parcial` |

donde `aceptada = cantidad_entregada - cantidad_rechazada`.

El **faltante** (`planificada - aceptada`) **no** se replanifica automáticamente en una entrega
nueva. Queda expresado como pendiente a nivel OC: `_recalcular_estado_orden_compra()` — que ya suma
`entregada - rechazada` por `oc_item` contra `oc_items.cantidad` (`compras/service.py:163-195`) —
devuelve `parcialmente_entregada`. Un reenvío posterior es una entrega nueva, registrada por el
endpoint manual existente o por un CSV de retorno con otro `numero_entrega`.

**Alternatives considered**:
- Reutilizar `_calcular_estado_entrega` tal cual. **Rechazada**: esa función no conoce el plan
  (recibe solo `list[EntregaItemRequest]`), así que entregar 50 de 100 planificadas le da
  `'entregada'` — precisamente el bug que OQ #2 pedía resolver.
- Crear automáticamente una entrega "de saldo" con el faltante. **Rechazada**: inventa una promesa
  de fecha que nadie acordó con el cliente y desalinea `numero_entrega` con la planilla que Progress
  ya tiene.

**Rationale**: los cinco valores del `CHECK ck_eoc_estado` existente
(`pendiente|en_transito|entregada|rechazada|parcial`) alcanzan sin cambiar el CHECK. El estado
`parcial` pasa a significar "cumplió menos de lo planificado", que es su lectura natural y hoy está
subutilizado. No se replanifica solo porque el faltante es una conversación comercial, no una
inferencia del sistema.

### D10 — Resolución de OQ #4: contratos CSV explícitos, versionados y aislados en un solo módulo

**Choice**: dos contratos fijos, ambos `;` / **CP1252** / **CRLF** / con fila de encabezado, con el
mapeo de columnas concentrado en `services/presupuestacion/compras/csv_progress.py` y nada más.

**Saliente — nota de pedido** (una fila por entrega × renglón planificado):

| Columna | Origen | Formato |
|---|---|---|
| `numero_oc` | `ordenes_compra.numero_oc` | texto |
| `version_oc` | `ordenes_compra.version_numero` | entero |
| `numero_entrega` | `entregas_oc.numero_entrega` | entero |
| `fecha_entrega` | `entregas_oc.fecha_entrega_planificada` | `DD/MM/AAAA` |
| `codigo_cliente` | `terceros.codigo_interno` | texto |
| `razon_social_cliente` | `terceros.razon_social` | texto |
| `numero_renglon` | `oc_items.numero_renglon` | entero |
| `codigo_producto` | `productos.codigo_interno` vía `oc_items.producto_id`; vacío si `NULL` | texto |
| `descripcion` | `oc_items.descripcion` | texto |
| `cantidad` | `entregas_oc_items.cantidad_planificada` | decimal, coma decimal |
| `precio_unitario` | `oc_items.precio_unitario` | decimal, coma decimal |

**Entrante — retorno de Progress**:

| Columna | Destino | Obligatoria |
|---|---|---|
| `numero_oc` | clave de consistencia contra la OC del path | sí |
| `numero_entrega` | clave → `entregas_oc.numero_entrega` | sí |
| `numero_renglon` | clave → `oc_items.numero_renglon` | sí |
| `cantidad_entregada` | `entregas_oc_items.cantidad_entregada` | sí |
| `cantidad_rechazada` | `entregas_oc_items.cantidad_rechazada` | no (default `0`) |
| `motivo_rechazo` | `entregas_oc_items.motivo_rechazo` | no |
| `lote` | `entregas_oc_items.lote` | no |
| `vencimiento` | `entregas_oc_items.vencimiento` | no, `DD/MM/AAAA` |
| `fecha_entrega_real` | `entregas_oc.fecha_entrega_real` | no, `DD/MM/AAAA` |

Clave de matcheo: `(numero_oc, numero_entrega, numero_renglon)`. Columnas desconocidas se ignoran;
columnas obligatorias faltantes abortan el import **antes de cualquier write**.

**Alternatives considered**: UTF-8 + punto decimal + ISO-8601 (lo que ya usa el pipeline interno).
**Rechazada para el borde con Progress**: Progress v8 es un ERP legacy sobre Windows en un contexto
es-AR; CP1252, coma decimal y `DD/MM/AAAA` son la apuesta correcta por defecto. El CSV interno de
extracción **sigue siendo UTF-8** — la conversión ocurre solo en la frontera.

**Rationale y riesgo declarado**: **no existe documentación del formato real de importación de
Progress v8 en el repositorio** (`rg -i "progress|ODBC|OpenEdge" docs/` no devuelve nada del ERP).
Este contrato es una definición de diseño, no una especificación verificada contra el destino. La
mitigación es estructural: **todo** el conocimiento de nombres de columna, orden, encoding,
separador decimal y formato de fecha vive en `csv_progress.py` y en ningún otro archivo, de modo que
adaptarlo al template real de Progress sea un cambio de un solo archivo con sus tests. Ver Risks.

Si el CP1252 no puede representar un carácter (ej. un guión largo pegado por un usuario), el export
falla con `ValidationError` explícita nombrando el renglón, en vez de emitir `?` silenciosos.

**Anti CSV-injection**: todo valor de texto que empiece con `=`, `+`, `-`, `@`, TAB o CR se prefija
con `'` antes de escribirse. Los campos de descripción y `razon_social` provienen de una extracción
de Gemini sobre un documento de terceros; sin esto, un documento malicioso puede inyectar fórmulas
en la planilla que el operador abra antes de importarla a Progress.

### D11 — Resolución de OQ #5: `producto_id` es opcional al validar, pero su ausencia es visible

**Choice**: `oc_items.producto_id` **no** se exige para confirmar (la columna es nullable y así
queda). El editor de validación permite asociarlo opcionalmente. La consecuencia se hace explícita
en dos lugares:

1. `ResultadoValidarExtraccion` (y la respuesta de la UI) incluye `renglones_sin_producto: int`.
2. El resultado del import incluye `lineas_sin_movimiento_de_stock: list[int]` con los
   `numero_renglon` afectados.

**Alternatives considered**: exigir `producto_id` en los N renglones antes de confirmar.
**Rechazada**: bloquearía la digitalización — que es el objetivo del cambio — detrás de la calidad
del catálogo, y el motor de matching existente (`procesar_matching_item`) está acoplado a
`items_proceso`, no a `oc_items`, así que no hay auto-resolución disponible hoy.

**Rationale**: la consecuencia real de `producto_id IS NULL` es que `crear_entrega`/el import hacen
`continue` y **no mueven stock** para esa línea (`compras/service.py:270-272`). Eso es un descuento
silenciosamente omitido. La decisión no es "exigirlo" sino "no dejar que sea silencioso": la OC se
registra igual, pero el operador ve exactamente qué renglones no van a mover stock. Enganchar el
motor de matching a `oc_items` queda como trabajo futuro, fuera de alcance.

### D12 — Resolución de OQ #6: se reutilizan las tuplas de roles existentes, sin inventar ninguna

**Choice**: confirmado contra el código real. No se crea ninguna tupla de roles nueva.

| Operación | Endpoint | Tupla | Valor (verificado) |
|---|---|---|---|
| Leer filas de una extracción OC | `GET /extracciones/{id}/filas` | `_ROLES_VALIDAR` (existente) | `admin, gerencia, lider_comercial, comercial` |
| Validar/confirmar una OC | `POST /extracciones/{id}/validar` | `_ROLES_VALIDAR` (existente, sin cambio) | ídem |
| Sugerir cliente candidato (D3) | `GET /extracciones/{id}/cliente-candidato` | `_ROLES_VALIDAR` (existente) | `admin, gerencia, lider_comercial, comercial` |
| Agrupar/desagrupar extracciones (D13) | `POST /extracciones/agrupar` · `/desagrupar` | `_ROLES_VALIDAR` (existente) | ídem |
| Buscar cliente a mano (D3.2) | `GET /terceros` **ya existente, sin cambios** | `_ROLES_LECTURA` de `terceros/identidad/router.py:37` | `superadmin, admin, gerencia, lider_comercial, comercial, compras` |
| Exportar nota de pedido | `GET /ordenes-compra/{id}/nota-pedido` | `_ROLES_ENTREGA` (existente) | `admin, gerencia, lider_comercial, comercial, compras` |
| Importar retorno de Progress | `POST /ordenes-compra/{id}/entregas/importar` | `_ROLES_ENTREGA` (existente) | ídem |

**Confirmación sobre la hipótesis de la propuesta**: `_ROLES_VALIDAR`
(`extraccion/router.py:23`) y `_ROLES_ESCRITURA` (`clientes/router.py:36`) son **la misma tupla
literal**. La propuesta acertó; el nombre correcto en el archivo que se toca es `_ROLES_VALIDAR`.

> Tras C5 la conclusión se sostiene pero el archivo ya no se toca: `clientes/router.py` queda fuera
> del alcance. Los tres endpoints nuevos viven todos en `extraccion/router.py` y reutilizan su
> `_ROLES_VALIDAR` sin declarar ninguna tupla nueva, así que **D12 sigue siendo cierto por el motivo
> que dice: cero tuplas de roles nuevas en todo el cambio**.

`_ROLES_ENTREGA` incluye `compras` y `_ROLES_VALIDAR` no: deliberado y correcto — el rol `compras`
opera entregas pero no valida documentos comerciales, que es el reparto que el módulo ya tenía. La
RLS de `oc_cliente_alias` (D3.1) hereda ese mismo criterio: escribe quien valida, no quien entrega.

### D13 — Una OC repartida en N archivos: `grupo_id` compartido, un CSV intacto por archivo

> **Capacidad nueva**, no contemplada en la propuesta ni en los specs. Algunas OC llegan partidas en
> varios documentos (el caso reportado: 3 entregas declaradas en 3 archivos separados). Aplica a
> Tramo 1 y Tramo 2.

**Choice**: `extraction_results.grupo_id UUID NULL`. N filas con el mismo `grupo_id` son **una sola
OC**. Cada archivo conserva **su propio CSV en disco, sin tocar**; la **concatenación** ocurre **en
la lectura**, no en el disco ni en la extracción. Concatenar es todo lo que ocurre: no hay fusión,
dedup ni renumeración automática (D13.1).

```
3 archivos ──► 3 × procesar_orden_compra ──► 3 CSV ──► 3 extraction_results (mismo grupo_id)
                                                              │
                                                              ▼
                                              lectura: 3 × _leer_filas_csv_con_columnas
                                                              │
                                                              ▼
                                              UNA sesión de validación (filas concatenadas)
                                                              │
                                                              ▼
                                              UNA fila en ordenes_compra
```

**Los dos caminos de agrupación comparten el mismo mecanismo** — esa es la decisión central:

| Camino | Cuándo | Cómo se setea `grupo_id` |
|---|---|---|
| **(a) Al subir** | El usuario sabe que los N archivos son la misma OC | El **frontend genera un UUID v4** y lo manda como campo de formulario `grupo_id` en cada uno de los N `POST /procesar`, que se disparan en secuencia |
| **(b) Después** | El usuario no se dio cuenta al subir | `POST /extracciones/agrupar { extraction_ids: [...] }` — asigna un `grupo_id` nuevo, o fusiona en el existente si alguna ya lo tiene |

**Por qué (a) no es "un request con N archivos"** (C8): `POST /procesar` acepta exactamente un
`UploadFile`, devuelve un fragmento HTML **sin el `extraction_id`**, y la fila se escribe *después*
de responder, en un `BackgroundTask`. Un endpoint multi-archivo obligaría a reescribir ese contrato
(y su deduplicación por SHA256, y su semáforo de Gemini, y su manejo de errores por archivo) para
los tres tipos de documento. Invertir la dirección — que el **cliente** provea la clave de
agrupación — hace que (a) sea (b) con el `grupo_id` puesto de entrada, y deja `/procesar` con un
único parámetro nuevo, opcional, que los otros dos tipos ignoran.

**Alternatives considered**:
- *(a')* Concatenar los N CSV en un solo archivo en disco al agrupar. **Rechazada**: destruye la
  trazabilidad archivo↔filas (el CSV deja de corresponder a `source_filename`/`source_sha256` de su
  fila), y hace que "desagrupar" sea irreversible. Con `grupo_id`, desagrupar es un `UPDATE ... SET
  grupo_id = NULL`.
- *(b')* Una tabla `extraction_groups` con su propia identidad, FK y RLS. **Rechazada por
  proporción**: el grupo no tiene ningún atributo propio — nombre, estado, dueño — que no viva ya en
  sus miembros. Una columna nullable expresa exactamente lo mismo con una tabla menos, una RLS menos
  y un join menos.
- *(c')* Mandar los N archivos a Gemini en una sola llamada. **Rechazada**: `procesar_orden_compra`
  se diseñó con la firma de `procesar_comparativa` (un archivo → un CSV); multi-documento cambiaría
  el prompt, la ventana de contexto y los golden fixtures, y haría que el fallo de un archivo se
  lleve puestos a los otros. Un archivo, una extracción, un fallo aislado.
- *(d')* Sin agrupar: N extracciones → N OC, y que el usuario las concilie en `compras/`.
  **Rechazada**: produce 3 `ordenes_compra` con el **mismo** `numero_oc` y el mismo cliente, que es
  justo lo que `uq_oc_por_cliente` (D5) prohíbe. La agrupación no es una comodidad de UI: sin ella
  el caso es directamente irrepresentable.

**Rationale**: el contrato `csv_disk_path → list[dict[str,str]]` sigue valiendo fila por fila; lo
único que cambia es **cuántas veces se lo invoca**. `_leer_filas_csv_con_columnas` no se modifica
(verificado: lee un archivo y devuelve `tuple[list[str], list[dict[str,str]]]`); se agrega un
envoltorio que la llama N veces **solo en la rama `orden_compra`**. Licitación y comparativa no se
enteran.

#### Lectura del grupo

```python
def _leer_filas_grupo(
    client: Client, *, extraction: dict[str, Any]
) -> tuple[list[str], list[dict[str, str]], list[dict[str, Any]]]:
    """Solo para document_type='orden_compra'. Devuelve (columnas, filas, miembros).

    Concatena las filas de los N miembros TAL CUAL, en orden de grupo. No deduplica,
    no suma cantidades, no renumera y no infiere nada (D13.1).

    grupo_id NULL -> se comporta exactamente como el caso de un archivo.
    Cada fila lleva `_archivo` (source_filename) y `_extraction_id` para que el
    editor muestre de dónde vino y el usuario pueda corregir con contexto.
    """
```

Orden de los miembros: `created_at ASC, id ASC` — determinista y sin columna extra. Miembros
elegibles: mismo `drogueria_id`, `document_type='orden_compra'`, `validado = false`.

#### D13.1 — Se concatena siempre; el humano reconcilia; el `numero_renglon` persistido lo asigna el sistema

> **Reemplaza por completo al `modo_fusion` de la revisión 2** (`concatenar` /
> `fusionar_por_renglon` con detección automática y selector de modo). Ver **C10**: esa decisión
> partía de dos premisas que el dueño de producto desmintió.

**Choice**, en tres partes que se sostienen entre sí:

1. **Concatenación incondicional.** Las filas de **todos** los miembros de un `grupo_id` entran a la
   tabla de validación tal cual salieron de su CSV, en orden de grupo (`created_at ASC, id ASC`).
   No hay deduplicación, no hay suma de cantidades, no hay detección de nada. `_leer_filas_grupo()`
   concatena y devuelve; **`_fusionar_filas()` deja de existir**.
2. **El `numero_renglon` del documento es una pista visual, no un dato de negocio.** Si el documento
   lo declaró, viaja en el CSV (D6) y se muestra en la tabla como columna **de solo lectura**, junto
   a `_archivo`. Sirve para que el operador reconozca a ojo que "la fila 3 del archivo 2 es la misma
   línea que la fila 3 del archivo 1". Si el documento **no** lo declaró, la celda queda vacía y no
   pasa nada: no bloquea, no advierte, no se rellena.
3. **`oc_items.numero_renglon` lo asigna el sistema al confirmar.** Es un **ordinal interno
   secuencial `1..N`** sobre el conjunto final de filas que el usuario confirmó, en el orden en que
   quedaron en la tabla. No se lee del documento, no se lee del payload, no se deriva del
   `numero_renglon` extraído. Se asigna dentro de `_materializar_orden_compra()`, en el momento de
   construir los inserts de `oc_items`.

**Quién reconcilia entonces los renglones repetidos: el usuario, con lo que ya tiene.** Si el
archivo 2 repite las líneas del archivo 1 con otra fecha de entrega, el operador ve las dos tandas
una debajo de la otra, con su columna `_archivo` y su `numero_renglon` de referencia, y decide:
borra las duplicadas, edita cantidades, o las deja como líneas separadas si eso es lo correcto.
**No hace falta UI nueva**: `useFilasEditables` ya expone `borrarFila` y `agregarFila`
(`useFilasEditables.ts:118,124`), y `ValidarExtraccionDetalle.tsx:127-128` ya las cablea a la tabla.
La capacidad existe y la usan hoy licitación y comparativa.

**Por qué `uq_oci (orden_compra_id, numero_renglon)` deja de ser un problema**: era la restricción
que forzaba todo el mecanismo de fusión — tres archivos numerados `1..N` cada uno colisionaban al
insertar. Con el ordinal asignado por el sistema sobre el conjunto final, la unicidad es
**estructural**: `1..N` contiguo sobre N filas no puede repetir. La restricción se satisface por
construcción, no por una heurística que haya que acertar.

**Alternatives considered**:

- *(a)* Conservar `modo_fusion` con los dos modos y la sugerencia automática (**la decisión de la
  revisión 2**). **Rechazada por C10**, y por dos motivos independientes: (i) la heurística de
  "conjuntos de `numero_renglon` idénticos → fusionar" **no tiene entrada** en los documentos que no
  declaran número de línea — compara dos conjuntos vacíos, los encuentra idénticos y sugiere sumar
  cantidades de líneas que nadie verificó que sean la misma; (ii) aun con número declarado, las dos
  formas del documento son reales y ninguna señal estructural las separa, así que la "sugerencia"
  era una moneda al aire con apariencia de análisis. Un default equivocado que suma cantidades es
  peor que no tener default: el error recién se descubre cuando llega la mercadería.
- *(b)* Renumerar contiguo `1..ΣN` al leer el grupo (el viejo modo `concatenar`), y persistir esa
  numeración. **Rechazada**: es casi lo mismo que se eligió, pero asigna el número **antes** de que
  el usuario edite. Si después borra tres filas duplicadas, la numeración persistida queda con
  huecos o hay que recalcularla igual. Asignar al confirmar, sobre el conjunto final, es un solo
  punto de asignación en vez de dos.
- *(c)* Exigir que la extracción siempre produzca un `numero_renglon`, autoincrementando cuando el
  documento no lo declara. **Rechazada**: fabrica un dato. Un número inventado por el extractor es
  visualmente indistinguible de uno que el documento realmente dice, y el operador lo usaría para
  reconciliar creyendo que es del documento. Vacío es información; un número inventado es
  desinformación.
- *(d)* Dejar `oc_items.numero_renglon` nullable y persistir lo que dijo el documento.
  **Rechazada**: `uq_oci` y todo el Tramo 3 dependen de ese campo — el CSV de nota de pedido lo
  emite y el CSV de retorno lo usa como **clave de matcheo**
  `(numero_oc, numero_entrega, numero_renglon)` (D10). Un campo nulo o duplicado ahí rompe el
  round-trip con Progress. El campo tiene que existir siempre y ser único: por eso lo genera el
  sistema.

**Rationale**: la fusión automática intentaba resolver, con inferencia, un problema que el humano ya
está sentado resolviendo — está en la pantalla de validación, mirando el documento. Este diseño
aplica el mismo principio que gobierna D3 y D4 en el resto del documento (**el sistema señala, el
humano decide, el write ocurre después**), con la diferencia de que acá ni siquiera hace falta que
el sistema señale: le alcanza con mostrar de qué archivo vino cada fila y qué número traía.

#### D13.2 — Desviación deliberada: OC no hereda la confianza en `numero_renglon` de licitación/comparativa

Esto **rompe a propósito** la convención del módulo, y conviene que quede escrito antes de que
alguien lo "corrija" por consistencia.

| | Licitación / comparativa | Orden de compra |
|---|---|---|
| Quién redacta el documento | **Nosotros** (pliego/comparativa de la droguería) | **El cliente** |
| De dónde sale `numero_renglon` | Del documento, **sin fallback**: `int(fila["item"].strip())` (`extraccion/service.py:234`), con el campo exigido entero antes (`:164`) | **Del sistema**, ordinal `1..N` al confirmar |
| Qué pasa si falta | `ValidationError` — es un error del documento | Nada: el campo del CSV es opcional (D6) |

**Verificado en el código real** (`services/presupuestacion/extraccion/service.py`):
`_validar_filas_override` corre `_chequear_entero(errores, numero, "item", fila["item"])` en la
línea 164, y `_materializar_licitacion` hace `"numero_renglon": int(fila["item"].strip())` en la
línea 234 — confiado directamente de la extracción, sin default ni recuperación. La comparativa usa
el mismo campo como **clave de lookup** contra los `items_proceso` ya materializados
(`:322`, `:377`), lo que refuerza el punto: ahí el número ya es nuestro porque lo escribimos
nosotros en el paso anterior.

**Por qué la OC no puede heredar esa confianza**: la numeración de un documento que redactamos
nosotros es, por construcción, nuestra — es consistente porque la generamos. La de un documento que
redacta un tercero no ofrece **ninguna** garantía: puede faltar, puede reiniciar en cada archivo de
un grupo, puede repetirse entre archivos con significados distintos, puede saltear números. Tratarla
como clave de negocio es asumir una disciplina de numeración sobre la que no tenemos ningún control
y que C10 documenta como inexistente. OC rompe la confianza y **siempre** re-deriva su propia
numeración al confirmar.

> **Contexto de negocio (informativo, no es alcance de este cambio)**: el dueño de producto confirmó
> que hay una **fase futura, todavía no diseñada**, en la que las líneas de una OC confirmada se
> matchean contra un `presupuesto` existente. Ahí es donde se va a resolver una numeración de
> renglón/ítem **autoritativa desde el negocio**. Eso es lo que hace seguro a largo plazo tratar
> `oc_items.numero_renglon` como un ordinal interno descartable: no es el número definitivo de nada,
> y un proceso posterior y más autoritativo lo reconcilia. **Este documento no diseña esa fase**; la
> nota existe solo para que la elección de acá no se lea como una deuda olvidada.

#### Cabecera inconsistente entre archivos

La cabecera se desnormaliza en cada fila (D6), así que un grupo de N archivos trae N cabeceras que
pueden no coincidir.

| Campo | Discrepancia entre miembros | Decisión |
|---|---|---|
| `numero_oc` | **Bloquea la confirmación** | Es la identidad de la OC. Si difieren, o son OC distintas (el grupo está mal armado) o uno se extrajo mal. Confirmar igual escribiría un `numero_oc` elegido por el sistema en una fila que entra en `uq_oc_por_cliente` |
| `cuit_cliente`, `razon_social_cliente` | **Advierte**, no bloquea | Son pistas para D3, no anclas. El ancla es el `cliente_id` que el usuario confirma, uno solo para todo el grupo |
| `fecha_emision`, `direccion_entrega` | **Advierte**, no bloquea | Datos documentales |
| `cantidad_entregas` | **Advierte**, no bloquea | Cada archivo declara el cronograma que conoce; el plan real del grupo lo arma el operador en `EntregasEditor` sobre el conjunto ya concatenado. El valor precargado es el más frecuente, igual que el resto de la cabecera |

"Bloquea" no significa callejón sin salida: la pantalla muestra **una sola cabecera editable** para
todo el grupo, precargada con el valor **más frecuente** entre los miembros (empate → el del primer
miembro), y marca en rojo los campos donde hubo desacuerdo. El usuario corrige y confirma. Es el
mismo patrón que el resto del diseño: el sistema señala, el humano decide, el write ocurre después.
El bloqueo se implementa en `_validar_orden_compra_override`, **antes del primer write**, igual que
todas las demás validaciones de D7.

#### Confirmación

`_materializar_orden_compra()` corre **una sola vez** sobre el conjunto de filas **concatenado y ya
reconciliado por el usuario**, y produce **una** fila en `ordenes_compra`. Antes de insertar
`oc_items`, **asigna `numero_renglon = 1..N` por posición** sobre ese conjunto final (D13.1),
descartando por completo el `numero_renglon` que hayan traído el CSV o el payload. Al terminar:

- `ordenes_compra.extraction_id` = el id de la extracción **que el usuario abrió** (el ancla del
  grupo). La columna es escalar y no se cambia su tipo; la trazabilidad al resto del grupo se
  recupera por `extraction_results.grupo_id`.
- **Todos** los miembros del grupo pasan a `validado = true`, con el mismo `validado_por` y
  `validado_at`. Dejar los otros en `false` los mostraría eternamente como "pendientes de validar"
  cuando su contenido ya está materializado.
- Si un miembro del grupo ya estaba `validado = true`, la confirmación aborta con `ConflictError`
  antes de escribir nada.

#### Agrupar después (camino b)

`POST /extracciones/agrupar { extraction_ids: [id1, id2, ...] }`, roles `_ROLES_VALIDAR`.
Precondiciones, todas verificadas antes del `UPDATE`:

| Precondición | Falla con |
|---|---|
| ≥ 2 ids, sin repetidos | `ValidationError` 422 |
| Todas existen y son de la droguería del usuario | `NotFoundError` 404 / `ForbiddenError` 403 |
| Todas tienen `document_type = 'orden_compra'` | `ValidationError` 422 |
| Ninguna tiene `validado = true` | `ConflictError` 409 |
| A lo sumo **un** `grupo_id` distinto ya presente entre ellas | `ConflictError` 409 — fusionar dos grupos ya armados es una operación distinta, y ambigua |

Si ninguna tenía `grupo_id`, se genera uno nuevo; si una o más ya pertenecían al mismo grupo, se
reutiliza ese. Desagrupar: `POST /extracciones/desagrupar { extraction_ids: [...] }` → `grupo_id =
NULL`. Un grupo que queda con un solo miembro se disuelve (su `grupo_id` pasa a `NULL`), para que no
exista un "grupo de uno" que se comporte distinto a una extracción suelta.

#### Deduplicación y grupos

`uq_er_sha256 UNIQUE (source_sha256)` es **global** y no se toca: subir dos veces el mismo archivo
dentro de un grupo devuelve el 409 de duplicado que `/procesar` ya emite hoy (`main.py:208-215`).
Correcto — dos archivos idénticos no son dos entregas distintas. El frontend de subida múltiple
reporta el resultado **por archivo**: si 2 de 3 entran y el tercero es duplicado, el grupo queda
armado con 2 miembros y el error se muestra sin abortar los que ya se procesaron.

---

## Data Flow

```
                        ── TRAMO 1: EXTRACCIÓN ──
  UI /upload (tipo=ordenes, 1..N archivos)
        │
        │  N>1: el front genera UN grupo_id (uuid v4) y lo manda con CADA archivo (D13)
        │
        ▼
  main.py::procesar   ── por archivo, en secuencia ──┐
        │                                            │
        ▼                                            │
  robot_orden_compra.py ──► Gemini ──► JSON          │
        │                               │            │
        │                               ▼            │
        │                       CSV en disco (;, UTF-8)  ← UNO por archivo, intacto
        ▼                               │            │
  persistent_output.py::persistir_output_final ◄─────┘
        │
        ▼
  extraction_results (document_type='orden_compra', csv_disk_path,
                      grupo_id = <el del front | NULL>, validado=false)
        ▲
        │  camino (b): POST /extracciones/agrupar  { extraction_ids: [...] }
        └─────────────────────────────────────────────────────────────────


                        ── TRAMO 2: VALIDACIÓN ──
  UI ValidarExtraccionDetalle
        │
        ├─► GET /extracciones/{id}/filas
        │        └─► _leer_filas_grupo()                        ← D13
        │                 └─► N × _leer_filas_csv_con_columnas  ← SIN CAMBIOS, N=1 si no hay grupo
        │                          └─► filas CONCATENADAS tal cual + columnas + miembros
        │                              (sin dedup, sin fusión, sin renumerar — D13.1)
        │
        │   ┌──────────────────────────────────────────────────────┐
        │   │  El USUARIO reconcilia duplicados entre archivos      │
        │   │  con borrarFila / editar celdas, que la tabla YA      │
        │   │  tiene. numero_renglon del documento = solo lectura   │
        │   └──────────────────────────────────────────────────────┘
        │
        ├─► GET /extracciones/{id}/cliente-candidato             ← D3, solo lectura
        │        ├─ 1) oc_cliente_alias  [normalizar_descripcion(razon_social)]  → 1 cliente
        │        ├─ 2) terceros.cuit ⋈ clientes  → 1 cliente | N candidatos (cuit_no_exclusivo)
        │        └─ 3) nada
        │
        ├─► GET /terceros?q=...&rol=todos   ← D3.2, SOLO si el usuario busca a mano
        │
        │   ┌──────────────────────────────────────────────────────┐
        │   │  CLICK HUMANO OBLIGATORIO: "Confirmar cliente"       │
        │   │  ningún nivel ancla sin esto                         │
        │   └──────────────────────────────────────────────────────┘
        │
        └─► POST /extracciones/{id}/validar  { orden_compra: { cliente_id, filas, entregas, ... } }
                 │
                 ▼
          _validar_orden_compra_override()   ← puro, ANTES del primer write
                 │   · cliente_id existe, es cliente, es de la droguería
                 │   · numero_oc coherente entre miembros del grupo (bloquea)
                 │   · suma de entregas == cantidad por renglón (por POSICIÓN en `filas`)
                 │
                 ▼
          _materializar_orden_compra()       ← UNA sola vez sobre las filas confirmadas
                 │
                 ├─► ordenes_compra   (cliente_id, proceso_comercial_id=NULL,
                 │                     extraction_id=<ancla>, cantidad_entregas,
                 │                     estado='emitida')
                 ├─► oc_items         (numero_renglon = ordinal 1..N ASIGNADO ACÁ  ← D13.1
                 │                     descripcion, cantidad, precio_unitario)
                 └─► entregas_oc      (estado='pendiente', fecha_entrega_planificada)
                          └─► entregas_oc_items (cantidad_planificada=N, entregada=0)
                 │
                 ▼
          UPSERT oc_cliente_alias (drogueria_id, texto_normalizado) → cliente_id   ← D3.1
                 │                 el sistema aprende de la confirmación
                 ▼
          extraction_results.validado = true   ← TODOS los miembros del grupo
                 │
                 ▼
          STOCK: SIN CAMBIOS  ◄── invariante duro del spec


                        ── TRAMO 3: PROGRESS ──
  GET /ordenes-compra/{id}/nota-pedido
        │  (bloquea si estado ∈ {pendiente, cancelada})
        ▼
  csv_progress.py::escribir_nota_pedido ──► CSV (;, CP1252, CRLF) ──► descarga
        │
        ▼
  [ Progress v8 — importación manual, descuento de stock DE PROGRESS ]
        │
        ▼
  CSV de retorno
        │
        ▼
  POST /ordenes-compra/{id}/entregas/importar (multipart)
        │
        ▼
  csv_progress.py::parsear_retorno ──► filas tipadas   ← valida TODO antes de escribir
        │
        ▼
  registrar_entrega_importada()
        │
        ├─► UPDATE entregas_oc_items  (entregada, rechazada, lote, vencimiento)
        ├─► UPDATE entregas_oc        (estado por D9, fecha_entrega_real)
        │
        ├─► entregar_stock_producto(Δentregada, Δrechazada)   ← SIN CAMBIOS, por DELTA
        │        └─► STOCK: único punto de movimiento de todo el flujo
        │
        └─► _recalcular_estado_orden_compra()                 ← SIN CAMBIOS
                 └─► ordenes_compra.estado
```

**Movimiento de stock por delta** (clave de idempotencia): el import calcula
`Δ = valor_del_csv - valor_ya_persistido` y se lo pasa a `entregar_stock_producto`. Primera
importación: `Δ = valor` (movimiento completo). Reimportación del mismo archivo: `Δ = 0`, y
`entregar_stock_producto` no mueve nada (sus dos bucles cortan con `restante <= 0` en la primera
iteración). Corrección al alza: mueve solo la diferencia. Corrección **a la baja** (`Δ < 0`): se
rechaza con `ValidationError` — `entregar_stock_producto` la ignoraría en silencio
(`if monto <= 0: return 0` en `_liberar_hasta`/`_descontar_disponible_hasta`), y una devolución de
stock necesita un ajuste manual explícito, no un import.

---

## File Changes

### Backend — extracción

| Archivo | Acción | Descripción |
|---|---|---|
| `services/extraccion/robot_orden_compra.py` | Crear | Prompt Gemini + `procesar_orden_compra(ruta, nombre) -> Path`. Misma firma y estructura que `procesar_comparativa`. Escribe el CSV de D6. **El prompt debe prohibir explícitamente inventar `numero_renglon`** (C10): si el documento no declara número de línea, la celda va vacía — nada de autoincrementar ni de derivarlo del orden de aparición |
| `services/extraccion/main.py` | Modificar | Eliminar el `HTTPException(422)` de las líneas 162-167. Extender `permitidos` para `ordenes` con `.html`/`.htm`. Reemplazar `doc_type = "comparativa" if ... else "licitacion"` (línea 220) por un mapeo de tres vías. Tercera rama en el bloque `_GEMINI_SEMAPHORE` (líneas 240-255) que invoca `procesar_orden_compra`. **Nuevo `grupo_id: str = Form("")`** (D13), validado como UUID v4 y propagado a `schedule_persist_output`; se ignora si `tipo != "ordenes"` |
| `services/extraccion/persistent_output.py` | Modificar | `_DOC_TYPES_SOPORTADOS` (línea 31) → `{"comparativa", "licitacion", "orden_compra"}` y actualizar el comentario obsoleto de las líneas 28-30. `persistir_output_final(..., grupo_id: str \| None = None)` → se agrega a `payload_base` solo si viene (D13) |
| `services/extraccion/background_tasks.py` | Modificar | `schedule_persist_output` pasa `grupo_id` a `persistir_output_final` (parámetro pasante, sin lógica) |

### Backend — validación

| Archivo | Acción | Descripción |
|---|---|---|
| `services/presupuestacion/extraccion/models.py` | Modificar | Nuevos `FilaOrdenCompraIn`, `EntregaPlanIn`, `OrdenCompraOverride` (con `cliente_id`; **sin `modo_fusion`**, D13.1), `CandidatoCliente`, `CandidatoClienteOut` (D3), `AgruparExtraccionesRequest` (D13). `ValidarExtraccionRequest.orden_compra`. `FilasExtraccionOut` suma `miembros` y `advertencias_cabecera` (**no** `modo_fusion_sugerido`). `ResultadoValidarExtraccion.proceso_comercial_id` pasa a `str \| None` y se agregan `orden_compra_id`, `renglones_sin_producto`, `entregas_creadas`, `extracciones_validadas`. **El alias `ModoFusion` no se crea** |
| `services/presupuestacion/extraccion/service.py` | Modificar | `_TIPOS_CON_LECTURA_DE_FILAS` (línea 39) suma `"orden_compra"` (y su comentario se corrige). Nuevas `_validar_orden_compra_override()`, `repartir_cantidad()` (D8), `_materializar_orden_compra()` (**asigna `numero_renglon = 1..N` por posición**, D13.1), `_leer_filas_grupo()` + `_conciliar_cabecera()` (D13), `resolver_cliente_candidato()` + `_normalizar_cuit()` + `_registrar_alias_cliente()` (D3/D3.1), `agrupar_extracciones()` / `desagrupar_extracciones()` (D13). Rama de `orden_compra` en `validar_extraccion()` (líneas 442-463), que **saltea** `_resolver_proceso_comercial_id`. **`_fusionar_filas()` no se crea** (D13.1): `_leer_filas_grupo` concatena y nada más. `_materializar_licitacion` (línea 234) **no se toca** — su confianza en `fila["item"]` sigue siendo correcta para su tipo de documento (D13.2) |
| `services/presupuestacion/extraccion/repository.py` | Modificar | Inserts de `ordenes_compra` / `oc_items` / `entregas_oc` / `entregas_oc_items` para la ruta de extracción (ver nota de frontera abajo). Además: `listar_miembros_de_grupo()`, `actualizar_grupo_id()`, `marcar_validadas()` (bulk sobre el grupo), `buscar_alias_cliente()`, `upsert_alias_cliente()`, `buscar_clientes_por_cuit()` |
| `services/presupuestacion/extraccion/router.py` | Modificar | Sin tuplas de roles nuevas (D12). `GET /extracciones/{id}/cliente-candidato`, `POST /extracciones/agrupar`, `POST /extracciones/desagrupar` — los tres con `_ROLES_VALIDAR` y `_verificar_pertenencia` (que para agrupar/desagrupar se aplica **por cada id** de la lista). Pasar `body.orden_compra` a `validar_extraccion_para_endpoint` |
| ~~`services/presupuestacion/clientes/*`~~ | **Sin cambios** | **Eliminado del alcance por C5**: no hay `buscar_cliente_por_codigo_interno`, ni `ClientePorCodigoOut`, ni `GET /clientes/por-codigo-interno`. La resolución vive en `extraccion/` (D3) y la búsqueda manual reutiliza `GET /terceros` sin tocarlo (D3.2) |

> **Nota de frontera de módulos**: `_materializar_orden_compra()` vive en `extraccion/` pero escribe
> tablas de `compras/`, y `resolver_cliente_candidato()` lee `terceros`/`clientes`, que son de
> `terceros/`. El repo prohíbe importar el `repository` de otro módulo, pero permite leer y
> escribir sus tablas directamente (precedente documentado en `pcp/imports/repository.py:30-36` y
> `gestion/repository.py::buscar_presupuesto`). Se sigue ese precedente: funciones de lectura y
> escritura propias en `extraccion/repository.py`, sin importar `compras/repository.py` ni
> `terceros/identidad/repository.py`.
>
> `oc_cliente_alias` es la excepción que confirma la regla: **es una tabla de `extraccion/`**. Su
> prefijo `oc_` describe el dominio del dato (órdenes de compra), no su dueño — el único código que
> la lee y la escribe es el pipeline de validación de extracciones. Por eso su RLS usa el set de
> roles de `_ROLES_VALIDAR` y no el de `terceros`.
>
> La búsqueda manual (D3.2) **no** cruza la frontera: es el **frontend** el que llama a
> `GET /terceros`, el endpoint público de ese módulo. Ningún código de `extraccion/` importa nada de
> `terceros/`.

### Backend — Progress

| Archivo | Acción | Descripción |
|---|---|---|
| `services/presupuestacion/compras/csv_progress.py` | Crear | **Único** lugar con conocimiento del formato Progress: `escribir_nota_pedido()`, `parsear_retorno()`, `_escapar_formula()`, constantes de encoding/delimitador/formato de fecha y número (D10) |
| `services/presupuestacion/compras/models.py` | Modificar | `FilaRetornoProgress`, `ResultadoImportEntregas { entregas_actualizadas, lineas_actualizadas, lineas_sin_movimiento_de_stock, orden_compra_estado }` |
| `services/presupuestacion/compras/repository.py` | Modificar | `listar_entregas_con_items()`, `actualizar_entrega()`, `actualizar_entrega_item()`, `buscar_entrega_por_numero()`, `buscar_cliente_de_oc()` |
| `services/presupuestacion/compras/service.py` | Modificar | `generar_nota_pedido()`, `importar_retorno_progress()`, `registrar_entrega_importada()`, `_calcular_estado_entrega_contra_plan()` (D9) y sus `*_para_endpoint`. **`crear_orden_compra`, `confirmar_orden_compra` y `crear_entrega` no se tocan** |
| `services/presupuestacion/compras/router.py` | Modificar | `GET /ordenes-compra/{id}/nota-pedido` y `POST /ordenes-compra/{id}/entregas/importar`, ambos detrás de `_validar_oc_de_la_drogueria` existente y roles `_ROLES_ENTREGA` |

### Esquema

| Archivo | Acción | Descripción |
|---|---|---|
| `supabase/migrations/0025_orden_compra_desde_extraccion.sql` | Crear | Ver § Migration |
| `supabase/migrations/0025_orden_compra_desde_extraccion.down.sql` | Crear | Ver § Migration |
| `docs/schema/extractor_final.sql` | Modificar | Reflejar 0025 completa — `ck_oc_anclaje`, los dos índices parciales, `cantidad_planificada`, el `CREATE TABLE oc_cliente_alias` con su RLS y `extraction_results.grupo_id` — **y** corregir C4 (`ordenes_compra` sin `deleted_at`/`created_by`/`updated_by`/`deleted_by`) verificando contra la base viva |
| `docs/modulos/compras/README.md` | Modificar | La dirección del flujo es hacia el cliente, no hacia el proveedor; documentar el ciclo plan → export → Progress → import |

### Frontend

| Archivo | Acción | Descripción |
|---|---|---|
| `frontend/src/features/validar-extraccion/components/OrdenCompraSelector.tsx` | Crear | **Rediseñado (D3)**: muestra la sugerencia automática (alias o CUIT) con "Confirmar" / "No es este"; con N candidatos de CUIT compartido, una lista corta de radio buttons; sin sugerencia o tras rechazarla, cae al buscador de `ClienteBuscador`. El botón de confirmar la OC queda deshabilitado hasta que haya `cliente_id` elegido. **No** hay input de código |
| `frontend/src/features/validar-extraccion/components/ClienteBuscador.tsx` | Crear | Búsqueda manual sobre `listarTerceros({ q, rol: 'todos', pageSize: 20 })` (D3.2): `q` mínimo 2 caracteres, debounce 300 ms, filtrado por `tiene_rol_cliente`, muestra `razon_social` + `cuit` + `codigo_interno`. Arranca vacío, nunca lista sin `q` |
| `frontend/src/features/validar-extraccion/components/EntregasEditor.tsx` | Crear | Cantidad de entregas + plazo por entrega + desglose opcional por línea; valida en vivo `suma == cantidad` por renglón (espejo de `_validar_orden_compra_override`) |
| `frontend/src/features/validar-extraccion/components/CabeceraOrdenCompra.tsx` | Crear | **Una sola cabecera editable para todo el grupo** (D13): precargada con el valor más frecuente entre miembros, marca en rojo los campos en desacuerdo, bloquea si `numero_oc` difiere y no se resolvió |
| ~~`frontend/src/features/validar-extraccion/components/SelectorModoFusion.tsx`~~ | **No se crea** | **Eliminado del alcance por C10 / D13.1.** No hay modo de fusión que elegir: se concatena siempre y el usuario reconcilia con `borrarFila` / edición de celdas, que la tabla ya tiene |
| `frontend/src/features/validar-extraccion/ValidarExtraccionDetalle.tsx` | Modificar | Rama `documentType === 'orden_compra'`: renderiza `CabeceraOrdenCompra` + `OrdenCompraSelector` + `EntregasEditor` en vez de `ProcesoComercialSelector`; envía `orden_compra` en vez de `filas`; `puedeConfirmar` exige `cliente_id` confirmado **y** ≥1 entrega válida **y** cabecera sin bloqueos. `onBorrarFila`/`onAgregarFila` (líneas 127-128) se cablean igual que hoy — **son la herramienta de reconciliación de D13.1**, no se toca nada de eso |
| `frontend/src/features/validar-extraccion/ValidarExtraccionListado.tsx` | Modificar | Estado de selección múltiple + acción "Agrupar seleccionadas como una sola OC" (D13 camino b), habilitada solo con ≥2 filas `orden_compra` no validadas seleccionadas. Acción inversa "Desagrupar" sobre un grupo |
| `frontend/src/features/validar-extraccion/components/PendientesTable.tsx` | Modificar | Columna de checkbox (solo en filas `orden_compra` no validadas) e indicador visual de pertenencia a un grupo. `ETIQUETA_TIPO` ya contempla `orden_compra` (línea 8) |
| `frontend/src/features/validar-extraccion/useFilasEditables.ts` | Modificar | Entrada `orden_compra` en `CAMPOS_POR_DOCUMENT_TYPE`; nuevo `CampoTipo` `'decimal-positivo'` para `precio_unitario`; `parsearPlanEntregas()` para la columna compuesta de D6; las columnas `_archivo`/`_extraction_id` (D13) **y `numero_renglon`** (D13.1) se muestran pero **no** son editables — las dos primeras son sintéticas y la tercera es una referencia visual del documento que no se persiste. `borrarFila`/`agregarFila` (líneas 118, 124) **no se tocan**: ya existen y son la vía de reconciliación de D13.1 |
| `frontend/src/lib/api/extracciones.ts` | Modificar | Tipos `FilaOrdenCompraIn`/`EntregaPlanIn`/`OrdenCompraOverride`/`CandidatoClienteOut`; `obtenerClienteCandidato(id)`, `agruparExtracciones(ids)`, `desagruparExtracciones(ids)`; `FilasExtraccionOut` suma `miembros`/`advertencias_cabecera` (**sin `modo_fusion_sugerido`**, D13.1); `ValidarExtraccionPayload.orden_compra`; `ResultadoValidarExtraccion.proceso_comercial_id` pasa a `string \| null` |
| ~~`frontend/src/lib/api/clientes.ts`~~ | **Sin cambios** | **Eliminado por C5.** La búsqueda usa `listarTerceros` de `lib/api/terceros.ts`, que ya existe tal cual |
| `frontend/src/lib/api/compras.ts` | Crear | `descargarNotaPedido(ocId)` (blob) e `importarRetornoProgress(ocId, file)` |
| `frontend/src/lib/api/extraccion.ts` | Modificar | `DocumentoReciente.document_type` suma `'orden_compra'` (hoy es `'licitacion' \| 'comparativa'`, línea 13). `ProcesarPayload.grupoId?: string` y `procesarDocumento` lo manda como campo `grupo_id` del `FormData` (D13) |
| `frontend/src/features/carga-documentos/components/FormCard.tsx` | Modificar | Quitar `disabled: true` de la opción `ordenes` (línea 37) y su badge "Próximamente". `<input type="file" multiple>` **solo** cuando `tipo === 'ordenes'`; con N>1 archivos genera `crypto.randomUUID()` y hace N `procesarDocumento` en secuencia con ese `grupoId`, reportando el resultado **por archivo** (un 409 de duplicado no aborta los demás, ver D13). El `esperarNuevoDocumento` existente pasa a esperar que el conteo crezca en N |

### Tests

| Archivo | Acción | Descripción |
|---|---|---|
| `tests/extraccion/test_service.py` | Modificar | `test_validar_orden_compra_no_implementado` se invierte a un test de materialización exitosa |
| `tests/extraccion/test_orden_compra.py` | Crear | `repartir_cantidad` (D8) y `_validar_orden_compra_override` |
| `tests/extraccion/test_cliente_candidato.py` | Crear | Los 3 niveles de D3, la precedencia entre ellos, el CUIT compartido de C6, el CUIT malformado y el UPSERT de alias de D3.1 |
| `tests/extraccion/test_grupo_extracciones.py` | Crear | `_leer_filas_grupo` (concatena sin transformar), `_conciliar_cabecera`, las 5 precondiciones de `agrupar_extracciones` (D13) y la asignación por posición de `numero_renglon` (D13.1). **Sin tests de `_fusionar_filas`**: la función no existe |
| `tests/compras/test_csv_progress.py` | Crear | Round-trip export/import, encoding, anti-injection, columnas faltantes |
| `tests/compras/test_import_entregas.py` | Crear | Delta, idempotencia, delta negativo, estados de D9 |
| `tests/fixtures/orden_compra/` | Crear | Golden fixtures del extractor y CSV de retorno de ejemplo. **Obligatorio incluir un documento que NO declare número de línea** (C10): su CSV esperado lleva la columna `numero_renglon` vacía en todas las filas, y es el golden que detecta si el prompt empieza a inventar números |

---

## Interfaces / Contracts

### Modelos de validación (`extraccion/models.py`)

```python
class FilaOrdenCompraIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # CAMBIO (C10 / D13.1): era `numero_renglon: str` obligatorio y se persistía tal cual.
    # Ahora es OPCIONAL y es SOLO REFERENCIA: lo que el documento del cliente dijo, si
    # dijo algo. NO es lo que se persiste. `oc_items.numero_renglon` es un ordinal
    # 1..N que asigna _materializar_orden_compra() por POSICIÓN en esta lista, al
    # confirmar. Si el documento no declaró número de línea, esto viene None/"" y no
    # pasa nada.
    numero_renglon_documento: str | None = None
    descripcion: str
    cantidad: str
    precio_unitario: str            # obligatorio; manual si la extracción no lo detectó
    producto_id: str | None = None  # opcional (D11)


class EntregaPlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    numero_entrega: int
    plazo_dias: int | None = None
    # None -> reparto automático parejo de cada renglón entre todas las entregas (D8).
    # CAMBIO (D13.1): la clave es la POSICIÓN 1-based de la fila en
    # OrdenCompraOverride.filas -- que es exactamente el numero_renglon que se va a
    # asignar al confirmar. Antes era el numero_renglon del documento, que ahora puede
    # no existir. Clave y valor siguen siendo strings.
    cantidades_por_posicion: dict[str, str] | None = None


class OrdenCompraOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    numero_oc: str
    # CAMBIO (C5): era `codigo_interno_cliente: str`. Ahora es el id del cliente que el
    # usuario CONFIRMÓ en pantalla — venga de un alias, de un CUIT o de la búsqueda
    # manual, el backend no distingue ni lo infiere (D3).
    cliente_id: str
    # Texto de cabecera que originó la confirmación. Es lo que se aprende en
    # oc_cliente_alias (D3.1). None -> no se aprende nada, no es un error.
    razon_social_extraida: str | None = None
    # ELIMINADO (C10 / D13.1): `modo_fusion: ModoFusion`. No hay modo que elegir --
    # las filas del grupo se concatenan siempre y el usuario reconcilia editando.
    # El alias `ModoFusion` tampoco existe.
    fecha_emision: date | None = None     # default: fecha de confirmación (ver nota de plazos)
    direccion_entrega: str | None = None
    notas: str | None = None
    filas: list[FilaOrdenCompraIn]
    entregas: list[EntregaPlanIn]         # min_length=1 — la confirmación no procede sin entregas


class ValidarExtraccionRequest(BaseModel):
    proceso_comercial_id: str | None = None
    filas: list[FilaLicitacionIn] | list[FilaComparativaIn] | None = None
    orden_compra: OrdenCompraOverride | None = None   # NUEVO (D7)


class ResultadoValidarExtraccion(BaseModel):
    extraction_id: str
    document_type: DocumentType
    proceso_comercial_id: str | None          # CAMBIO: era `str` — NULL en la ruta OC
    filas_creadas: int
    comparativa_id: str | None = None
    reemplazo_version_anterior: bool = False
    orden_compra_id: str | None = None        # NUEVO
    entregas_creadas: int = 0                 # NUEVO
    renglones_sin_producto: int = 0           # NUEVO (D11)
    extracciones_validadas: int = 1           # NUEVO (D13) — miembros del grupo marcados
```

#### Contrato de numeración de renglones (D13.1)

Una sola regla, y conviene que sea imposible de saltear por accidente:

```python
# services/presupuestacion/extraccion/service.py, dentro de _materializar_orden_compra()
#
# `numero_renglon` NO se lee de `fila.numero_renglon_documento` ni de ningún otro
# campo del payload. Se asigna acá, por posición, sobre el conjunto final de filas
# que el usuario confirmó (D13.1). `numero_renglon_documento` se descarta: cumplió
# su función como referencia visual en la pantalla y no se persiste en ningún lado.
filas_items = [
    {
        "orden_compra_id": orden_compra_id,
        "drogueria_id": drogueria_id,
        "numero_renglon": posicion,          # <-- ordinal interno 1..N, siempre
        "descripcion": fila.descripcion.strip(),
        "cantidad": fila.cantidad,
        "precio_unitario": fila.precio_unitario,
        "producto_id": fila.producto_id,     # opcional (D11)
    }
    for posicion, fila in enumerate(override.filas, start=1)
]
```

Consecuencias, todas deseadas:

| Invariante | Por qué se cumple |
|---|---|
| `uq_oci (orden_compra_id, numero_renglon)` nunca se viola | `1..N` contiguo sobre N filas no puede repetir. Se cumple por construcción, no por validación |
| No hay huecos ni saltos en la numeración persistida | El ordinal se asigna **después** de que el usuario borró/agregó filas, no antes |
| `numero_renglon` es estable para el round-trip con Progress (D10) | Existe siempre y es único dentro de la OC, que es lo único que `(numero_oc, numero_entrega, numero_renglon)` necesita |
| Un documento sin números de línea se materializa igual que uno con números | El campo del documento nunca entró en la ruta de escritura |

La clave de `EntregaPlanIn.cantidades_por_posicion` es **esa misma posición**, así que el desglose
del plan y el `numero_renglon` persistido coinciden sin ninguna traducción intermedia.

### Resolución de cliente (D3)

```python
OrigenCandidato = Literal["alias", "cuit", "cuit_compartido", "ninguno"]


class CandidatoCliente(BaseModel):
    cliente_id: str
    razon_social: str
    cuit: str | None
    codigo_interno: str | None
    tipo: str
    activo: bool                  # false -> el front lo muestra deshabilitado con el motivo
    cuit_no_exclusivo: bool       # true -> es una sede de un CUIT institucional (C6)


class CandidatoClienteOut(BaseModel):
    origen: OrigenCandidato
    # 1 elemento  -> sugerencia única (alias, o CUIT exclusivo)
    # N elementos -> candidatos de un CUIT compartido; el usuario elige (C6)
    # 0 elementos -> el usuario busca a mano (D3.2)
    candidatos: list[CandidatoCliente]
    cuit_extraido: str | None          # ya normalizado a 11 dígitos, o None
    razon_social_extraida: str | None  # texto crudo, tal cual salió del documento
    advertencias: list[str]            # CUIT malformado, tercero sin rol cliente, etc.
```

Nada acá escribe. El único write de la resolución es el UPSERT de `oc_cliente_alias`, y ocurre
dentro de la confirmación (D3.1), nunca al abrir la pantalla.

```python
def resolver_cliente_candidato(
    client: Client, *, drogueria_id: str, cuit_extraido: str | None, texto_extraido: str | None
) -> CandidatoClienteOut:
    """Sugiere un cliente para una OC extraída. NO ancla nada: la confirmación es
    siempre un click del usuario (D3).

    Nivel 1 — oc_cliente_alias por normalizar_descripcion(texto_extraido): exacto.
    Nivel 2 — terceros.cuit ⋈ clientes: 1 fila (exclusivo) o N (cuit_no_exclusivo, C6).
    Nivel 3 — sin candidatos; el front usa GET /terceros (D3.2).

    Corta en el primer nivel que devuelva algo. Nunca levanta excepción por
    "no encontrado": no encontrar es un resultado válido.
    """
```

### Agrupación multi-archivo (D13)

```python
class MiembroGrupo(BaseModel):
    extraction_id: str
    source_filename: str
    row_count: int
    created_at: datetime


class AgruparExtraccionesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extraction_ids: list[str] = Field(min_length=2)


class FilasExtraccionOut(BaseModel):          # MODIFICADO
    extraction_id: str
    document_type: DocumentType
    row_count: int
    filas_leidas: int
    editable: bool
    columnas: list[str]
    filas: list[dict[str, str]]
    # --- NUEVO (D13). grupo_id NULL -> miembros=[self], advertencias=[] :
    # la forma de un archivo suelto no cambia. ---
    # ELIMINADO (C10 / D13.1): `modo_fusion_sugerido`. El backend no sugiere ningún
    # modo porque no hay ninguno que elegir: `filas` ya viene concatenada tal cual.
    grupo_id: str | None = None
    miembros: list[MiembroGrupo] = []
    advertencias_cabecera: list[str] = []
```

`editable` con grupo se evalúa sobre el **total concatenado** contra `MAX_FILAS_EDITABLES` (500): tres
archivos de 200 filas son 600 filas editables, y la red de seguridad del servidor debe medir lo que
la UI va a renderizar, no lo que trae cada archivo por separado.

> **Cambio de contrato con impacto en el frontend**: `proceso_comercial_id` pasa de `str` a
> `str | None`. En TypeScript, `ResultadoValidarExtraccion.proceso_comercial_id: string | null`.
> Ningún consumidor actual lo lee tras el `onSuccess` (`ValidarExtraccionDetalle.tsx:62-66` solo
> invalida y navega), así que el impacto es de tipos, no de runtime.

### Reparto parejo (D8)

```python
def repartir_cantidad(cantidad: Decimal, entregas: int) -> list[Decimal]:
    """Reparte `cantidad` entre `entregas` de la forma más pareja posible (D8).

    Invariante duro: sum(resultado) == cantidad, exactamente, siempre.
    Entero  -> las primeras (cantidad % entregas) reciben base+1.
    Decimal -> las primeras entregas-1 reciben floor a centésimos; la última, el resto.
    """
```

### Frontera Progress (D10)

```python
_ENCODING = "cp1252"
_DELIMITADOR = ";"
_TERMINADOR = "\r\n"
_FORMATO_FECHA = "%d/%m/%Y"
_SEPARADOR_DECIMAL = ","
_PREFIJOS_FORMULA = ("=", "+", "-", "@", "\t", "\r")

COLUMNAS_NOTA_PEDIDO = (
    "numero_oc", "version_oc", "numero_entrega", "fecha_entrega",
    "codigo_cliente", "razon_social_cliente", "numero_renglon",
    "codigo_producto", "descripcion", "cantidad", "precio_unitario",
)

COLUMNAS_RETORNO_OBLIGATORIAS = (
    "numero_oc", "numero_entrega", "numero_renglon", "cantidad_entregada",
)


def escribir_nota_pedido(*, oc, cliente, items, entregas, productos_por_id) -> bytes: ...
def parsear_retorno(contenido: bytes) -> list[FilaRetornoProgress]: ...
```

### Registro de entrega importada (D2, D9)

```python
def registrar_entrega_importada(
    client: Client,
    *,
    orden_compra_id: str,
    numero_entrega: int,
    filas: list[FilaRetornoProgress],
    fecha_entrega_real: date | None,
) -> ResultadoImportEntregas:
    """Completa en el lugar una entrega planificada. Mueve stock por DELTA contra lo ya
    persistido, de modo que reimportar el mismo CSV sea idempotente.

    Reutiliza SIN CAMBIOS `stock.entregar_stock_producto` y
    `_recalcular_estado_orden_compra`. NO usa `crear_entrega` (ver D2).

    Raises:
        NotFoundError:   la entrega o el renglón no pertenecen a esta OC.
        ValidationError: delta negativo (corrección a la baja), o
                         cantidad_entregada < cantidad_rechazada.
        ConflictError:   la OC no está en un estado que admita entregas.
    """
```

### Endpoints nuevos

| Método | Ruta | Roles | Respuesta |
|---|---|---|---|
| `GET` | `/extracciones/{id}/cliente-candidato` | `_ROLES_VALIDAR` | `CandidatoClienteOut` (D3) |
| `POST` | `/extracciones/agrupar` | `_ROLES_VALIDAR` | `{ grupo_id, extraction_ids }` (D13) |
| `POST` | `/extracciones/desagrupar` | `_ROLES_VALIDAR` | `{ extraction_ids }` (D13) |
| `GET` | `/ordenes-compra/{id}/nota-pedido` | `_ROLES_ENTREGA` | `text/csv` + `Content-Disposition: attachment` |
| `POST` | `/ordenes-compra/{id}/entregas/importar` | `_ROLES_ENTREGA` | `ResultadoImportEntregas` |

**Endpoints reutilizados sin modificar**: `GET /terceros?q=&rol=todos&page=&page_size=` (D3.2) y
`GET /extracciones/{id}/filas` (cuyo *response model* crece, pero cuya ruta y roles no cambian).

**Endpoint eliminado del diseño**: ~~`GET /clientes/por-codigo-interno`~~ — C5.

> `POST /extracciones/agrupar` opera sobre una **lista** de ids, así que no puede usar el
> `_verificar_pertenencia(extraction_id=...)` de `extraccion/router.py:27-50` tal cual. Se lo invoca
> **una vez por id** antes de tocar nada: N verificaciones con el *user client* y recién después el
> `UPDATE` con el service client, que es exactamente el patrón `*_para_endpoint` ya establecido en
> el módulo. `superadmin` (con `drogueria_id` NULL) queda exento del chequeo de tenant igual que hoy,
> pero el `UPDATE` sigue exigiendo que los N miembros compartan `drogueria_id` entre sí — si no, un
> superadmin podría armar un grupo multi-tenant.

---

## Migration / Rollout

### `0025_orden_compra_desde_extraccion.sql`

```sql
-- =============================================================================
-- Migration 0025: orden de compra originada en extracción
--
-- 1. proceso_comercial_id pasa a nullable + CHECK de anclaje: una OC extraída de
--    un documento de cliente se ancla por cliente_id, no por proceso comercial.
-- 2. uq_oc (global) se reemplaza por dos índices únicos parciales, uno por ruta
--    de anclaje. Dos clientes distintos pueden numerar sus OC igual.
-- 3. entregas_oc_items.cantidad_planificada: el plan y el hecho comparten fila
--    (design.md D1). crear_entrega no la escribe -> queda 0 = "registrada
--    directo, sin plan previo", que es exactamente su semántica actual.
-- 4. oc_cliente_alias (TABLA NUEVA): el sistema aprende qué encabezado de
--    documento corresponde a qué cliente, a partir de cada confirmación humana
--    (design.md D3.1). Reemplaza el anclaje por codigo_interno, que era
--    estructuralmente imposible (design.md C5).
-- 5. extraction_results.grupo_id: N archivos = una sola OC (design.md D13).
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'esta migracion requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

-- 1) anclaje ------------------------------------------------------------------
ALTER TABLE ordenes_compra ALTER COLUMN proceso_comercial_id DROP NOT NULL;

ALTER TABLE ordenes_compra
  ADD CONSTRAINT ck_oc_anclaje
  CHECK (proceso_comercial_id IS NOT NULL OR cliente_id IS NOT NULL);

COMMENT ON COLUMN ordenes_compra.proceso_comercial_id IS
  'NULL cuando la OC se origina en una extracción de documento de cliente; en ese caso el anclaje es cliente_id. Garantizado por ck_oc_anclaje.';

-- 2) unicidad por ruta de anclaje ---------------------------------------------
-- uq_oc es (numero_oc, version_numero) GLOBAL. Ambos alcances nuevos son
-- estrictamente más permisivos: cualquier par único globalmente sigue siendo
-- único dentro de cualquier subconjunto, así que la creación no puede fallar por
-- filas preexistentes. El riesgo de duplicados vive en la migración inversa.
-- Ninguna FK depende de uq_oc: todas referencian id o (id, drogueria_id).
ALTER TABLE ordenes_compra DROP CONSTRAINT IF EXISTS uq_oc;

CREATE UNIQUE INDEX uq_oc_por_cliente
  ON ordenes_compra (drogueria_id, cliente_id, numero_oc, version_numero)
  WHERE cliente_id IS NOT NULL;

CREATE UNIQUE INDEX uq_oc_por_proceso
  ON ordenes_compra (drogueria_id, proceso_comercial_id, numero_oc, version_numero)
  WHERE cliente_id IS NULL;
-- ck_oc_anclaje garantiza que dentro de uq_oc_por_proceso (cliente_id IS NULL)
-- la columna proceso_comercial_id nunca es NULL: ninguna ruta queda sin cubrir.

-- 3) plan de entregas ---------------------------------------------------------
ALTER TABLE entregas_oc_items
  ADD COLUMN IF NOT EXISTS cantidad_planificada NUMERIC(12, 2) NOT NULL DEFAULT 0;

ALTER TABLE entregas_oc_items
  ADD CONSTRAINT ck_eoci_planificada CHECK (cantidad_planificada >= 0);

COMMENT ON COLUMN entregas_oc_items.cantidad_planificada IS
  'Lo que se prometió entregar en esta entrega. Se escribe al confirmar la OC (stock SIN tocar) y se compara contra cantidad_entregada al importar el retorno de Progress. 0 = entrega registrada directo, sin plan previo (camino de crear_entrega).';

-- 4) alias aprendido de cliente (D3.1) ----------------------------------------
-- La OC la redacta el cliente: nunca puede traer nuestro codigo_interno (C5).
-- El unico dato confiable para anclar es el que un humano YA confirmo. Esta
-- tabla lo persiste: encabezado normalizado -> cliente, por drogueria.
CREATE TABLE IF NOT EXISTS oc_cliente_alias (
    id                          UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id                UUID            NOT NULL,
    texto_extraido_normalizado  TEXT            NOT NULL,
    texto_extraido_original     TEXT            NOT NULL,
    cliente_id                  UUID            NOT NULL,
    veces_confirmado            INTEGER         NOT NULL DEFAULT 1,
    created_by                  UUID            NULL,
    updated_by                  UUID            NULL,
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_oca UNIQUE (drogueria_id, texto_extraido_normalizado),
    CONSTRAINT ck_oca_texto CHECK (length(trim(texto_extraido_normalizado)) > 0),
    CONSTRAINT ck_oca_veces CHECK (veces_confirmado >= 1),
    CONSTRAINT fk_oca_drogueria FOREIGN KEY (drogueria_id)
        REFERENCES droguerias (id) ON DELETE CASCADE,
    -- FK compuesta contra uq_cli_id_drog (clientes: UNIQUE (id, drogueria_id)):
    -- misma convencion que fk_cli_condpago / fk_cli_formapago. Impide que un
    -- alias apunte a un cliente de otra drogueria aunque la RLS falle.
    CONSTRAINT fk_oca_cliente FOREIGN KEY (cliente_id, drogueria_id)
        REFERENCES clientes (id, drogueria_id) ON DELETE CASCADE
);

-- uq_oca ES el indice del nivel 1 (igualdad exacta sobre la clave unica).
-- Este otro existe solo para listar/limpiar los alias de un cliente dado.
CREATE INDEX IF NOT EXISTS idx_oca_cliente
    ON oc_cliente_alias (drogueria_id, cliente_id);

COMMENT ON TABLE oc_cliente_alias IS
  'Aprendizaje del pipeline de OC: que texto de encabezado de un documento de cliente corresponde a que cliente nuestro. Se escribe por UPSERT en cada confirmacion humana de la pantalla de validacion (design.md D3.1). La ultima confirmacion gana y resetea veces_confirmado.';
COMMENT ON COLUMN oc_cliente_alias.texto_extraido_normalizado IS
  'Clave de match del nivel 1. Producida por services/presupuestacion/core/texto.py::normalizar_descripcion (NFKD -> ascii, puntuacion -> espacio, espacios colapsados, UPPER). NO se reimplementa en SQL: la normalizacion vive en un solo lugar.';
COMMENT ON COLUMN oc_cliente_alias.veces_confirmado IS
  'Cuantas veces se reconfirmo este mapeo. Se resetea a 1 cuando el usuario CORRIGE el cliente: un alias corregido es un alias nuevo y no hereda la confianza del mapeo equivocado.';

ALTER TABLE oc_cliente_alias ENABLE ROW LEVEL SECURITY;

-- Misma convencion de aislamiento por tenant que terceros / tercero_direcciones
-- (0008_terceros_modelo.sql:608-638): mismo_tenant() + get_rol(), envueltos en
-- (select ...) por la optimizacion de 0019 (se evalua una vez, no por fila).
DROP POLICY IF EXISTS oca_sel ON oc_cliente_alias;
CREATE POLICY oca_sel ON oc_cliente_alias FOR SELECT
  USING ((select mismo_tenant(drogueria_id)));

DROP POLICY IF EXISTS oca_ins ON oc_cliente_alias;
CREATE POLICY oca_ins ON oc_cliente_alias FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial')
              AND (select mismo_tenant(drogueria_id)));

DROP POLICY IF EXISTS oca_upd ON oc_cliente_alias;
CREATE POLICY oca_upd ON oc_cliente_alias FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial')
              AND (select mismo_tenant(drogueria_id)));

DROP POLICY IF EXISTS oca_del ON oc_cliente_alias;
CREATE POLICY oca_del ON oc_cliente_alias FOR DELETE USING ((select es_superadmin()));

-- Supabase no auto-expone tablas nuevas al Data API.
GRANT SELECT, INSERT, UPDATE, DELETE ON oc_cliente_alias TO service_role;
GRANT SELECT, INSERT, UPDATE           ON oc_cliente_alias TO authenticated;

-- 5) agrupacion multi-archivo (D13) -------------------------------------------
-- N filas con el mismo grupo_id son UNA sola OC. Nullable a proposito: el caso
-- de un archivo suelto (que es el 100% de las filas existentes y la mayoria de
-- las futuras) no cambia en nada. Sin FK ni tabla propia: el grupo no tiene
-- ningun atributo que no viva ya en sus miembros.
ALTER TABLE extraction_results ADD COLUMN IF NOT EXISTS grupo_id UUID NULL;

-- Parcial: solo indexa las filas agrupadas, que son una minoria. El acceso es
-- siempre "dame los miembros de este grupo".
CREATE INDEX IF NOT EXISTS idx_er_grupo
    ON extraction_results (grupo_id)
    WHERE grupo_id IS NOT NULL;

COMMENT ON COLUMN extraction_results.grupo_id IS
  'NULL = extraccion suelta (caso normal). No NULL = esta fila es una parte de un documento repartido en varios archivos; todas las filas con el mismo grupo_id se validan juntas y producen UNA sola orden_compra (design.md D13). Cada miembro conserva su propio csv_disk_path intacto: las filas se concatenan en la lectura, nunca en disco, y sin deduplicar ni renumerar (design.md D13.1).';
```

> **`uq_er_sha256` no se toca.** Sigue siendo global, así que subir el mismo archivo dos veces dentro
> de un grupo devuelve el 409 de duplicado que `/procesar` ya emite. Es el comportamiento correcto:
> dos archivos binariamente idénticos no son dos entregas distintas.

### `0025_orden_compra_desde_extraccion.down.sql`

```sql
-- Down migration para 0025.
--
-- AVISO 1 (datos antes que esquema): restaurar NOT NULL en proceso_comercial_id
-- exige borrar o rellenar previamente toda OC originada en extracción
-- (proceso_comercial_id IS NULL). El ALTER falla si queda alguna.
--
-- AVISO 2: restaurar uq_oc (alcance GLOBAL) es estrictamente más restrictivo que
-- los índices parciales. Si dos clientes registraron el mismo
-- (numero_oc, version_numero), el ALTER falla. Verificar y resolver antes:
--   SELECT numero_oc, version_numero, count(*)
--     FROM ordenes_compra GROUP BY 1, 2 HAVING count(*) > 1;
--
-- AVISO 3 (perdida de conocimiento): DROP TABLE oc_cliente_alias borra todo lo
-- que el sistema aprendio de cada confirmacion humana (D3.1). No es
-- reconstruible desde las OC ya materializadas: ordenes_compra guarda el
-- cliente_id resuelto, no el texto de encabezado que lo origino. Exportar antes
-- si la baja puede revertirse:
--   COPY (SELECT * FROM oc_cliente_alias) TO '/tmp/oc_cliente_alias.csv' CSV HEADER;
--
-- AVISO 4 (grupos): DROP COLUMN grupo_id disuelve toda agrupacion pendiente. Las
-- extracciones agrupadas y NO validadas quedan como N documentos sueltos, y
-- validarlas por separado produce N ordenes_compra con el mismo numero_oc y el
-- mismo cliente -- que uq_oc_por_cliente rechaza. Verificar que no quede ninguna:
--   SELECT grupo_id, count(*) FROM extraction_results
--    WHERE grupo_id IS NOT NULL AND validado = false GROUP BY 1;

DROP INDEX IF EXISTS idx_er_grupo;
ALTER TABLE extraction_results DROP COLUMN IF EXISTS grupo_id;

DROP INDEX IF EXISTS idx_oca_cliente;
DROP TABLE IF EXISTS oc_cliente_alias;

ALTER TABLE entregas_oc_items DROP CONSTRAINT IF EXISTS ck_eoci_planificada;
ALTER TABLE entregas_oc_items DROP COLUMN IF EXISTS cantidad_planificada;

DROP INDEX IF EXISTS uq_oc_por_cliente;
DROP INDEX IF EXISTS uq_oc_por_proceso;
ALTER TABLE ordenes_compra ADD CONSTRAINT uq_oc UNIQUE (numero_oc, version_numero);

ALTER TABLE ordenes_compra DROP CONSTRAINT IF EXISTS ck_oc_anclaje;
ALTER TABLE ordenes_compra ALTER COLUMN proceso_comercial_id SET NOT NULL;
```

### Verificación previa obligatoria

Antes de aplicar 0025, verificar **contra la base viva** (C4: el snapshot de
`docs/schema/extractor_final.sql` está desactualizado para al menos dos tablas):

1. Que `uq_oc` siga existiendo con ese nombre exacto en `ordenes_compra`.
2. Que ninguna FK la referencie (`pg_constraint.confrelid` + `conkey`).
3. Que `entregas_oc_items` no tenga ya una columna `cantidad_planificada`.
4. Que `clientes` tenga `uq_cli_id_drog UNIQUE (id, drogueria_id)` — es el objetivo de la FK
   compuesta `fk_oca_cliente` de D3.1. (Confirmado en el snapshot,
   `docs/schema/extractor_final.sql:259`, pero vale el mismo criterio de C4: verificar contra la
   base viva.)
5. Que existan las funciones `mismo_tenant(uuid)`, `get_rol()` y `es_superadmin()` usadas por las
   políticas RLS de `oc_cliente_alias` — son las mismas que ya usan `terceros` y sus satélites.
6. Que `extraction_results` no tenga ya una columna `grupo_id`.
7. ~~Que `terceros` tenga `uq_terceros_codigo (drogueria_id, codigo_interno)`~~ — **ya no aplica**:
   D3 no consulta ese índice (C5). El índice sigue existiendo y sigue siendo correcto para el alta
   manual de terceros; simplemente este cambio no depende de él.

### Rollout

Sin feature flag. El orden de despliegue importa:

1. **Migración 0025** primero. Es retrocompatible con el código viejo: `DROP NOT NULL` no rompe
   inserts que ya mandan el valor, `cantidad_planificada` tiene `DEFAULT 0`, `grupo_id` es nullable
   y nadie lo lee todavía, y `oc_cliente_alias` nace vacía y sin ningún consumidor.
2. **Backend** después. Hasta que exista el frontend, cargar una OC deja una extracción validable
   por API pero sin pantalla — estado inerte, no roto.
3. **Frontend** último. Es el único paso que enciende la capacidad para el usuario: hasta que
   `FormCard` no habilite la opción `ordenes` (hoy `disabled: true`, línea 37), nada de esto es
   alcanzable desde la UI. Eso hace que el frontend funcione como interruptor de facto y vuelve
   innecesario un feature flag.

**Arranque en frío de D3**: `oc_cliente_alias` nace vacía, así que las primeras OC de cada cliente
resuelven por CUIT (nivel 2) o a mano (nivel 3). Es el comportamiento esperado, no una degradación:
el nivel 1 gana precisión con el uso. **No se pre-siembra la tabla** desde las OC históricas —
`ordenes_compra` guarda el `cliente_id` resuelto pero no el texto de encabezado que lo originó, así
que no hay dato de dónde derivarla sin inventarlo.

Rollback: revertir código restaura el 422 y el `ValidationError`; ningún flujo existente lee las
columnas nuevas ni la tabla nueva. La migración inversa es el único retroceso no trivial, con los
cuatro avisos de arriba — y el AVISO 3 (pérdida del aprendizaje acumulado) es irreversible si no se
exporta antes.

### RLS y permisos (skill `supabase`)

- **Una tabla nueva**: `oc_cliente_alias` (D3.1). Nace con `ENABLE ROW LEVEL SECURITY` y las cuatro
  políticas `oca_sel/ins/upd/del`, copiadas de la convención literal de `terceros` y
  `tercero_direcciones` (`0008_terceros_modelo.sql:608-638`): `mismo_tenant(drogueria_id)` para
  leer, `mismo_tenant + get_rol() IN (...)` para escribir, `es_superadmin()` para borrar, todo
  envuelto en `(select ...)` por la optimización de RLS de `0019`. Más los `GRANT` explícitos, que
  Supabase **no** genera solo para tablas nuevas.
  - El set de roles de escritura de `oca_*` es `_ROLES_VALIDAR` (`admin, gerencia, lider_comercial,
    comercial`), **no** el de `terceros` (que incluye `compras`): el alias se escribe únicamente
    como efecto de validar una extracción, y `compras` no valida documentos comerciales (D12).
- Las políticas de `ordenes_compra` / `oc_items` / `entregas_oc` / `entregas_oc_items` /
  `extraction_results` quedan **sin cambios**; agregar una columna (`cantidad_planificada`,
  `grupo_id`) no requiere política nueva — no se usa RLS a nivel columna en este proyecto.
- **Autorización**: `require_roles` + `UsuarioPerfil` de `core/auth.py`. Verificado: `user_metadata`
  no aparece en **ningún** archivo bajo `services/` — el rol no proviene del JWT del usuario.
- **Service role**: los endpoints nuevos siguen el patrón `*_para_endpoint` ya establecido — el
  router hace la verificación de pertenencia con el **user client** (`_validar_oc_de_la_drogueria`,
  `_verificar_pertenencia`) y recién después el service corre con `get_service_client()`. El service
  role nunca cruza al frontend.
- **Índices**: los accesos a tablas existentes están cubiertos por índices que ya existen —
  `idx_oc_cliente` (parcial, `WHERE cliente_id IS NOT NULL`), `idx_oc_extraction` (parcial),
  `uq_eoc (orden_compra_id, numero_entrega)`, `uq_eoci (entrega_oc_id, oc_item_id)`,
  `uq_oci (orden_compra_id, numero_renglon)`, y `uq_terceros_cuit` para el nivel 2 de D3 (parcial:
  `WHERE cuit IS NOT NULL AND deleted_at IS NULL AND NOT cuit_no_exclusivo` — **no cubre** las filas
  `cuit_no_exclusivo`, que son justamente las que devuelven N candidatos; ese lado del caso es un
  scan sobre un subconjunto chico y conocido, aceptable). Los índices **nuevos** son los dos
  parciales de D5 más `uq_oca` + `idx_oca_cliente` (D3.1) e `idx_er_grupo` (D13).
- **Costo del nivel 3 (D3.2)**: `GET /terceros` no pagina en la base (C7-ii). Por eso el picker
  **exige `q`**: con término, el `.or_(...ilike...)` corre en Postgres y vuelve un subconjunto; sin
  término, cada apertura de la pantalla barrería las 5541 filas de la droguería. No se agrega índice
  para el `ilike` (un trigram sobre `razon_social` sería lo correcto si esto se vuelve un problema
  medido, no antes) — queda anotado en Open Questions junto con la paginación real.
- **Transacciones cortas**: el import agrupa las lecturas por OC en consultas `in_(...)` (una por
  tabla) y después escribe; no hace N+1 por renglón. `entregar_stock_producto` mantiene su optimistic
  locking existente, sin cambios.

---

## Testing Strategy

Runner: `pytest tests/` (`asyncio_mode=auto`). **Strict TDD**: RED antes de implementar, en todas las
filas de abajo.

| Capa | Qué se prueba | Cómo |
|---|---|---|
| Unit | `repartir_cantidad` (D8) | Tabla de casos: `(100, 3) -> [34,34,32]`; `(100, 1) -> [100]`; `(7, 2) -> [4,3]`; `(10.5, 4)`; `(0, 3)`. **Property**: `sum(repartir(c, n)) == c` para todo `c`, `n>=1` |
| Unit | `_validar_orden_compra_override` | Suma por línea ≠ cantidad; cero entregas; `precio_unitario` vacío/no numérico; clave de `cantidades_por_posicion` fuera del rango `1..len(filas)` → 422; acumulación de múltiples errores en un solo 422 (mismo patrón que `test_validar_filas_override_acumula_errores_de_multiples_filas`). **Ya no existe** el caso "`numero_renglon` duplicado": el número lo asigna el sistema, así que duplicarlo es imposible (D13.1) |
| Unit | `_calcular_estado_entrega_contra_plan` (D9) | Los 4 renglones de la tabla de D9, más el borde `aceptada > planificada` (sobreentrega → `entregada`) |
| Unit | `csv_progress.escribir_nota_pedido` | Encoding CP1252; terminador CRLF; coma decimal; `DD/MM/AAAA`; `codigo_producto` vacío con `producto_id IS NULL`; carácter no representable → `ValidationError` |
| Unit | `csv_progress` anti-injection | Descripción `=cmd\|'/c calc'!A0` sale prefijada con `'`; ídem `+`, `-`, `@`, TAB, CR |
| Unit | `csv_progress.parsear_retorno` | Columna obligatoria faltante; columna desconocida ignorada; `cantidad_rechazada` ausente → 0; decimal con coma y con punto; fecha inválida |
| Unit | `parsear_plan_entregas` (D6) | `"50@30\|50@60"`; vacío; malformado; un solo plan; separador decimal mixto |
| Unit | `_normalizar_cuit` (D3) | `"30-12345678-9"`, `"30123456789"`, `"30.123.456.78 9"` → mismos 11 dígitos; `"1234"` → `None` + advertencia |
| Unit | Clave de alias (D3.1) | `normalizar_descripcion("Hospital Público Ñandú S.A. - Sede Nº2") == "HOSPITAL PUBLICO NANDU S A SEDE N 2"`; dos variantes tipográficas del mismo encabezado colapsan a la misma clave. **Test de no-regresión**: `core/texto.py` no se modifica (el mismo test vive hoy para matching) |
| Unit | Asignación de `numero_renglon` (D13.1) | El ordinal sale de la **posición**, no del payload: filas con `numero_renglon_documento` `"7","3",None` en ese orden → `oc_items.numero_renglon` `1,2,3`; dos filas con el **mismo** `numero_renglon_documento` → `1,2` sin conflicto (el caso que antes exigía `modo_fusion`); **todas** las filas sin número de documento → `1..N` igual. **Test de no-regresión**: `_materializar_licitacion` sigue leyendo `int(fila["item"])` sin cambios (D13.2) |
| Unit | `_conciliar_cabecera` (D13) | `numero_oc` distinto entre miembros → bloqueo; `razon_social` distinta → advertencia, no bloqueo; valor más frecuente gana; empate → primer miembro |
| Integration | `resolver_cliente_candidato` (D3) | Los 3 niveles y su precedencia (alias gana sobre CUIT aunque ambos resuelvan y difieran); CUIT con `cuit_no_exclusivo` → N candidatos (C6); CUIT exclusivo → 1; sin match → `origen='ninguno'`, 200 y lista vacía; tercero con CUIT pero sin fila en `clientes` → omitido + advertencia; **aserción explícita de que no hay ningún write** |
| Integration | UPSERT de alias (D3.1) | Primera confirmación inserta con `veces_confirmado=1`; reconfirmar el mismo texto y cliente incrementa; **corregir** el cliente pisa `cliente_id` y **resetea** a 1; el alias es invisible desde otra `drogueria_id` |
| Integration | Alias y confirmación | Si `_materializar_orden_compra` falla, **no** queda alias escrito (el aprendizaje es consecuencia de una confirmación exitosa, no de un intento) |
| Integration | `_leer_filas_grupo` (D13) | `grupo_id IS NULL` → forma idéntica a la de un archivo suelto (test de no-regresión de licitación/comparativa); 3 miembros → filas concatenadas en orden `created_at, id`, con `_archivo` poblado; `editable` se evalúa sobre el total concatenado contra `MAX_FILAS_EDITABLES`. **Aserción explícita de que NO transforma** (D13.1): la cantidad de filas devuelta es la suma exacta de las de cada miembro, y ninguna `cantidad` ni `numero_renglon` cambió respecto del CSV de origen — ni siquiera cuando los 3 archivos declaran el mismo conjunto de números de línea |
| Integration | `agrupar_extracciones` (D13) | Las 5 precondiciones de la tabla de D13, una por test; grupo de otra droguería → 403; ya validada → 409; dos `grupo_id` distintos → 409; desagrupar deja `NULL` y disuelve el grupo de un solo miembro |
| Integration | Confirmación de grupo | Una sola fila en `ordenes_compra`; `extraction_id` = el ancla; **los 3 miembros** quedan `validado=true` con el mismo `validado_at`; si uno ya estaba validado, `ConflictError` **antes** de escribir |
| Integration | `_materializar_orden_compra` | Crea `ordenes_compra` con `cliente_id` y `proceso_comercial_id IS NULL`, `estado='emitida'`, `extraction_id` y `cantidad_entregas` poblados; `entregas_oc_items.cantidad_planificada` suma la cantidad de cada renglón; **ninguna llamada a `entregar_stock_producto`** (aserción explícita sobre el mock) |
| Integration | `validar_extraccion` ruta OC | `proceso_comercial_id` ausente **no** levanta error en esta ruta; `extraction_results.validado` queda en `true`; el test invertido de `test_service.py:172-189` |
| Integration | `registrar_entrega_importada` | Delta en la primera importación = total; reimportación del mismo CSV → `entregar_stock_producto` recibe 0 y el stock no se mueve; delta negativo → `ValidationError`; `producto_id IS NULL` → línea listada en `lineas_sin_movimiento_de_stock` |
| Integration | Router de export | `estado='pendiente'` → bloqueado; `estado='emitida'` → 200 `text/csv`; OC de otra droguería → 403 vía `_validar_oc_de_la_drogueria` |
| Integration | Unicidad (D5) | Mismo `numero_oc` + dos `cliente_id` distintos → ambas confirmaciones OK; mismo `numero_oc` + mismo cliente → `ConflictError` |
| Golden | Extractor Gemini | Fixtures bajo `tests/fixtures/orden_compra/` (PDF/imagen/Excel/HTML) con su CSV esperado; el prompt no se toca sin regenerar los golden |
| Frontend | `EntregasEditor` | La suma por renglón que no cuadra deshabilita confirmar; el espejo cliente coincide con el mensaje del servidor |
| Frontend | `OrdenCompraSelector` (D3) | Sugerencia de alias → se muestra preseleccionada pero **confirmar la OC sigue deshabilitado hasta el click de "Confirmar cliente"** (el test del invariante humano); "No es este" abre el buscador; N candidatos de CUIT compartido → N radios, ninguno preseleccionado; sin sugerencia → buscador directo |
| Frontend | `ClienteBuscador` (D3.2) | `q` de 1 carácter **no** dispara request; debounce coalesce las pulsaciones; la llamada lleva `rol: 'todos'` (test explícito de C7-iii) y filtra por `tiene_rol_cliente`; sin `q` no hay ningún request al montar |
| Frontend | Reconciliación manual (D13.1) | Con un grupo de 3 miembros, la tabla muestra la **suma** de las filas; `borrarFila` sobre una duplicada la saca del payload enviado; la columna `numero_renglon` **no** es editable (click no abre `CeldaEditable`) y se renderiza vacía cuando el documento no la declaró; **no existe** ningún selector de modo de fusión en la pantalla |
| Frontend | `CabeceraOrdenCompra` (D13) | `numero_oc` en desacuerdo → campo en rojo y confirmar deshabilitado; editarlo a un valor único lo habilita; desacuerdo de `razon_social` muestra aviso pero **no** bloquea |
| Frontend | `FormCard` multi-archivo (D13) | Con `tipo='ordenes'` el input acepta múltiples; 3 archivos → 3 `procesarDocumento` con **el mismo** `grupoId`; un 409 en el segundo no aborta el tercero y se reporta por archivo; con `tipo='licitaciones'` el input **no** es múltiple |
| Frontend | `ValidarExtraccionListado` (D13) | "Agrupar seleccionadas" deshabilitado con <2 seleccionadas y con selección de tipos mixtos; tras agrupar, las filas muestran el indicador de grupo |
| Frontend | `ValidarExtraccionDetalle` | Con `document_type='orden_compra'` **no** renderiza `ProcesoComercialSelector`; el payload enviado lleva `orden_compra` y no `filas` |

**Round-trip end-to-end del contrato CSV**: `escribir_nota_pedido` → `parsear_retorno` sobre su
propia salida (agregándole `cantidad_entregada`) debe reconstruir las mismas claves
`(numero_oc, numero_entrega, numero_renglon)`. Es el test que detecta una desalineación entre las
dos direcciones sin depender de Progress.

---

## Threat Matrix

La matriz de `references/threat-matrix.md` cubre automatización de shell/VCS/PR. Este cambio no
tiene ninguno de esos bordes.

| Boundary | Applicability | Motivo |
|---|---|---|
| Documentation-like paths | **N/A** | No hay clasificación ni ejecución de archivos por nombre/extensión. `permitidos` en `main.py` es una allowlist de extensiones de documento que se pasan a Gemini, nunca se ejecutan |
| Git repository selection | **N/A** | El cambio no invoca `git` ni ningún VCS |
| Commit state | **N/A** | Sin automatización de commits |
| Push state | **N/A** | Sin automatización de push |
| PR commands | **N/A** | Sin automatización de PR |

**Bordes reales de este cambio** (fuera de esa matriz, pero con la misma disciplina: caso adverso →
comportamiento esperado → test RED planificado):

| Borde | Caso adverso | Comportamiento esperado | Test RED |
|---|---|---|---|
| CSV saliente | Descripción extraída de un PDF de tercero empieza con `=`/`+`/`-`/`@`/TAB/CR | Se prefija con `'`; nunca se emite una fórmula viva | `test_csv_progress.py::test_prefija_formulas` |
| CSV entrante | Archivo sin columna obligatoria, o con `numero_oc` de otra OC | Aborta **antes** de cualquier write; la OC queda intacta | `test_csv_progress.py::test_columna_obligatoria_faltante`, `test_import_entregas.py::test_numero_oc_no_coincide_con_el_path` |
| CSV entrante | Reimportación del mismo archivo | Idempotente: delta 0, stock sin mover | `test_import_entregas.py::test_reimportacion_no_mueve_stock` |
| CSV entrante | Archivo gigante o binario disfrazado de CSV | Límite de tamaño de upload y decodificación estricta → 422, no OOM | `test_import_entregas.py::test_archivo_no_decodificable` |
| Multi-tenant | OC de otra droguería en el path | 403 por `_validar_oc_de_la_drogueria` **antes** de que corra el service role | `test_router.py::test_import_oc_de_otra_drogueria` |
| Stock | Corrección a la baja vía reimport | `ValidationError` explícita, no un no-op silencioso | `test_import_entregas.py::test_delta_negativo_rechazado` |
| Extracción | Documento de OC sin `precio_unitario` detectable | La extracción **no** falla; el campo llega vacío y el editor lo exige antes de confirmar | `test_orden_compra.py::test_precio_vacio_bloquea_confirmacion` |
| Resolución de cliente | Un documento de tercero trae una razón social **calcada** de otro cliente para que el alias lo ancle mal | Imposible sin acción humana: el alias solo se escribe **después** de que un usuario confirma. El peor caso es que la sugerencia sea la equivocada y el usuario la acepte por inercia — mitigado porque la pantalla muestra siempre `razon_social` + `cuit` + `codigo_interno` del candidato para contrastar contra el documento | `test_cliente_candidato.py::test_alias_no_se_escribe_sin_confirmacion` |
| Resolución de cliente | Alias envenenado por una confirmación equivocada anterior | Corregible y auto-corregible: la corrección hace UPSERT, pisa el `cliente_id` y **resetea** `veces_confirmado` a 1. No hay estado pegado | `test_cliente_candidato.py::test_correccion_pisa_y_resetea` |
| Resolución de cliente | Texto de encabezado vacío o solo puntuación (`"---"`) | `normalizar_descripcion` devuelve `""`; `ck_oca_texto` rechaza el INSERT y el nivel 1 se saltea sin consultar | `test_cliente_candidato.py::test_texto_vacio_no_genera_alias` |
| Multi-tenant | Alias de la droguería A consultado desde la B | RLS `oca_sel` (`mismo_tenant`) + `uq_oca` con `drogueria_id` en la clave: el texto normalizado **no** es global | `test_cliente_candidato.py::test_alias_aislado_por_drogueria` |
| Multi-tenant | `POST /extracciones/agrupar` con ids de dos droguerías (posible solo como `superadmin`, que está exento del chequeo de tenant) | `ValidationError` — los N miembros deben compartir `drogueria_id` **entre sí**, se verifique o no contra el del usuario | `test_router.py::test_agrupar_multi_tenant_rechazado` |
| Multi-archivo | Agrupar una extracción ya validada | `ConflictError` **antes** del `UPDATE`; su OC ya existe y volver a fusionarla duplicaría renglones | `test_grupo_extracciones.py::test_agrupar_validada_rechazado` |
| Multi-archivo | Confirmar un grupo con renglones repetidos entre archivos | **Nunca se fusiona, ni en silencio ni con permiso** (D13.1): las filas repetidas llegan las dos a la tabla y el usuario decide si son la misma línea. `uq_oci` no llega a violarse porque `numero_renglon` es un ordinal `1..N` asignado al insertar, no el número del documento | `test_grupo_extracciones.py::test_renglones_repetidos_no_se_suman`, `::test_numero_renglon_es_ordinal_por_posicion` |
| Multi-archivo | Documento sin número de línea en un grupo de N archivos | No bloquea y no se rellena: la celda queda vacía, el usuario reconcilia por descripción, y el ordinal persistido se asigna igual (C10 / D13.1) | `test_grupo_extracciones.py::test_grupo_sin_numero_de_renglon_se_materializa` |
| Extracción | El prompt "ayuda" autoincrementando el número de línea que el documento no declara | El golden del fixture sin números falla: el dato inventado es indistinguible de uno real y el operador lo leería como si el documento lo dijera | Golden `tests/fixtures/orden_compra/` (caso sin numeración) |
| Multi-archivo | Un miembro del grupo pierde su CSV (volumen no montado) | `ExtraccionNoDisponibleError` en la primera lectura que falle, **antes** de cualquier write; el grupo no se valida a medias | `test_grupo_extracciones.py::test_miembro_sin_csv_aborta` |

---

## Open Questions

Las 6 preguntas abiertas de la propuesta quedan **resueltas** en este documento:

- [x] **#1** Distribución del resto → **D8** (resto al frente para enteros; al final para decimales).
- [x] **#2** Cumplimiento parcial y `estado` → **D9** (se mide contra `cantidad_planificada`;
      `parcial`; sin replanificación automática).
- [x] **#3** Unicidad de `codigo_interno` → **la pregunta quedó sin objeto (C5)**. No se resuelve:
      se descarta. `codigo_interno` no participa del anclaje porque el documento del cliente no
      puede contenerlo. El anclaje es D3 (alias → CUIT → búsqueda manual), y su unicidad relevante
      es `uq_oca (drogueria_id, texto_extraido_normalizado)` (D3.1), no `uq_terceros_codigo`.
- [x] **#4** Formatos CSV → **D10** (definidos y aislados en `csv_progress.py`). *Resuelto con una
      salvedad*: es una definición de diseño, no verificada contra Progress. Ver Risks R1.
- [x] **#5** `producto_id` obligatorio → **D11** (opcional, pero su consecuencia se reporta).
- [x] **#6** Roles → **D12** (confirmado contra el código: `_ROLES_VALIDAR` y `_ROLES_ENTREGA`
      existentes, sin tupla nueva).

Quedan abiertas, y **ninguna bloquea** empezar a implementar:

- [ ] **R1 — validación del formato CSV con Progress v8.** Se necesita un template real de
      importación de Progress (o un CSV de ejemplo exportado por él). Mientras tanto se implementa
      D10 y se ajusta `csv_progress.py` cuando aparezca. **Acción**: pedirle a operaciones un CSV de
      ejemplo antes de la fase de apply del Tramo 3.
- [ ] **Reconciliar `orden-compra-validacion` al archivar**: el escenario "`codigo_interno` ambiguo"
      parte de una premisa falsa (C5) y **no tiene reemplazo directo** — la ambigüedad de CUIT no es
      un error sino un resultado legítimo (C6). El spec necesita tres escenarios nuevos: sugerencia
      por alias confirmada, candidatos de CUIT compartido elegidos por el usuario, y búsqueda manual
      sin sugerencia. También hay que agregar al spec la capacidad multi-archivo (D13), que no está
      en ningún spec hoy — **incluyendo** que el `numero_renglon` del documento es opcional y que el
      persistido lo asigna el sistema (D13.1). Si algún escenario del spec asume que el renglón
      confirmado conserva el número del documento, hay que reescribirlo.
- [ ] **Fase futura: matcheo de la OC confirmada contra un `presupuesto`.** El dueño de producto la
      confirmó como planificada; **no está diseñada y no es alcance de este cambio**. Es donde se va
      a resolver una numeración de renglón/ítem autoritativa desde el negocio, y es el motivo por el
      que acá alcanza con un ordinal interno (D13.2). Se anota para que la decisión de D13.1 no se
      lea como una deuda técnica olvidada sino como una elección con un sucesor previsto.
- [x] ~~**Forma real de las OC partidas**~~ → **respondida por el dueño de producto, y la respuesta
      disolvió la pregunta** (C10). Las dos formas existen —renglones distintos por archivo, y los
      mismos renglones repetidos con distinta fecha de entrega— **y además hay OC que no declaran
      número de línea en absoluto**. No hay patrón que detectar ni campo sobre el cual matchear, así
      que no se elige un default: **se concatena siempre y reconcilia el usuario** (D13.1). Sigue
      siendo útil pedir 2 o 3 ejemplos reales antes del apply del Tramo 1, pero ya **no para decidir
      nada de diseño**: sirven como fixtures del extractor, y al menos uno debe ser un documento sin
      numeración de línea.
- [ ] **Paginación real de `GET /terceros`** (C7-ii): hoy el repository trae todas las filas que
      matchean y el service recorta en Python. Con `q` obligatorio (D3.2) el costo es aceptable para
      este caso de uso, pero la mejora correcta es `.range()` + `count='exact'` en PostgREST, más un
      índice trigram sobre `razon_social` si la medición lo justifica. **Fuera de alcance**: es un
      cambio en `services/terceros/`, con otros consumidores (el picker de proveedores de PCP pide
      `page_size=5000` a propósito). Anotado, no bloqueante.
- [ ] **`rol='clientes'` es excluyente** (C7-iii): `tiene_cliente AND NOT tiene_proveedor` deja fuera
      a los terceros con ambos roles. Este diseño lo esquiva pidiendo `rol='todos'`, pero el filtro
      probablemente sea un bug latente para cualquier otro consumidor que lo use esperando "todos
      los clientes". **Fuera de alcance**, reportado acá para que exista el registro.
- [ ] **Reconciliar el no-objetivo D-EXTRACCIONVALIDACION-003** ("orden_compra rechazado") del change
      `validar-extraccion`, que este cambio supera. La propuesta ya lo anota.
- [ ] **Enganchar el motor de matching a `oc_items`** para auto-resolver `producto_id` (hoy
      `procesar_matching_item` está acoplado a `items_proceso`). Fuera de alcance, habilitado por
      D11.

### Nota para `sdd-archive` (agregada en Phase 9, no reemplaza lo anterior)

Ninguna edición de este documento se tocó para escribir esta nota — es una anotación agregada al
final de la sección existente, no una reescritura. Su único propósito es que un futuro `sdd-archive`
de este change **no** trate como resueltas dos de las Open Questions de arriba, porque ambas siguen
genuinamente abiertas al cierre de Tramo 1+2 (`orden-compra-extraccion` + `orden-compra-validacion`)
y ninguna de las dos bloqueó, ni bloquea, esta implementación:

- **R1 — validación de formato con Progress v8**: sigue sin un template real de Progress contra el
  cual verificar `csv_progress.py` (Tramo 3 de este mismo change, aún no implementado — ver README
  de `docs/modulos/compras/` actualizado en esta misma fase). No aplica todavía porque Tramo 3 no se
  implementó en Tramo 1+2; queda abierta para cuando se implemente esa fase futura, no para este
  archive.
- **Reconciliar `orden-compra-validacion` al archivar**: los specs `orden-compra-extraccion` y
  `orden-compra-validacion` (`openspec/changes/orden-compra/specs/`) **ya fueron escritos** en esta
  ejecución del change reflejando D3/D3.1/D3.2/D13/D13.1 (alias/CUIT/búsqueda manual, agrupación
  multi-archivo, `numero_renglon` como ordinal del sistema) — no quedó pendiente el escenario
  "`codigo_interno` ambiguo" que esta Open Question original advertía. La trazabilidad spec-a-test de
  la tarea 9.4 de `tasks.md` es la verificación concreta de que esos specs, tal como quedaron
  redactados, están cubiertos por la implementación real. Esta Open Question se deja igual como
  **abierta y no bloqueante** para que un archive automático no la interprete como "cerrada por
  default" solo porque los specs ya existen: el cierre explícito de este ítem requiere que un humano
  confirme, al archivar, que no quedó ningún escenario del spec sin reconciliar contra el código —
  ese es precisamente el insumo que deja 9.4.
