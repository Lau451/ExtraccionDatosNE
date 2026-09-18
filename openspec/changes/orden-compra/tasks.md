# Tasks: Orden de compra — Tramo 1 (extracción) + Tramo 2 (validación)

> Alcance de este checklist: solo `orden-compra-extraccion` y `orden-compra-validacion`.
> Tramo 3 (`nota-pedido-export`, `entregas-import`, `csv_progress.py`, endpoints de nota de pedido e
> importación del retorno de Progress) queda explícitamente fuera — ver sección "Scope" del prompt
> de esta fase y § Approach de `proposal.md`. La columna `entregas_oc_items.cantidad_planificada` y
> el resto de la migración 0025 se crean acá porque Tramo 2 los escribe al confirmar, aunque Tramo 3
> los use después.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~4.700 (additions + deletions, fixtures excluidas del riesgo autorado) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 → PR3 → PR4 → PR5 → PR6 → PR7 → PR8 → PR9 (feature-branch-chain) |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

**Nota sobre la elección de estrategia**: la sesión cachea `delivery_strategy=auto-chain`, que no
requiere pregunta ni decisión antes de aplicar — el propio contrato de la skill indica proceder con
la primera porción usando la estrategia de cadena elegida. Se eligió **feature-branch-chain** (en vez
de stacked-to-main) porque el cambio incluye una migración de esquema con RLS nueva y un plan de
rollback documentado en `proposal.md`/`design.md` que depende de revertir en orden; una cadena de
ramas contra el branch del feature da control de rollback más fino que apilar 9 PRs directo a main.
Esto es una recomendación de planificación, no una pregunta al usuario — el orquestador puede
recachear una estrategia distinta si lo prefiere.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Migración 0025 (esquema + RLS + docs) | PR 1 (base = tracker `orden-compra`) | `pytest tests/extraccion tests/compras -k grupo_id or oc_cliente_alias` (falla hasta PR3-5; en PR1 se verifica con las queries manuales de la Fase 1) | Aplicar la migración contra el proyecto Supabase de test (`grnamollopxdlstcpxhc`) y correr las queries de verificación previa/posterior de design.md § Migration | `supabase/migrations/0025_*.sql` + `.down.sql`; revertir es aplicar la down migration documentada, con los 4 avisos de design.md |
| 2 | Extracción Tramo 1: tercer extractor Gemini + ruteo + agrupación al subir | PR 2 (base = PR 1) | `pytest tests/test_robot_orden_compra.py tests/test_main_integration.py -k ordenes` | `pytest tests/test_main_integration.py::TestProcesarTipoOrdenes` (mock de Gemini, sin llamada real) | `services/extraccion/robot_orden_compra.py` (archivo nuevo) + reversión puntual de los 3 archivos modificados de Tramo 1 |
| 3 | Validación — resolución de cliente (D3/D3.1/D3.2) | PR 3 (base = PR 2) | `pytest tests/extraccion/test_cliente_candidato.py` | `pytest tests/extraccion/test_cliente_candidato.py -m integration` contra el proyecto Supabase de test | Endpoint `GET /extracciones/{id}/cliente-candidato` + funciones nuevas de `service.py`/`repository.py`; ningún consumidor existente las llama todavía |
| 4 | Validación — agrupación multi-archivo (D13) | PR 4 (base = PR 3) | `pytest tests/extraccion/test_grupo_extracciones.py` | `pytest tests/extraccion/test_grupo_extracciones.py -m integration` contra el proyecto Supabase de test | Endpoints `POST /extracciones/agrupar`/`desagrupar` + `_leer_filas_grupo`; `GET /extracciones/{id}/filas` sigue funcionando igual con `grupo_id IS NULL` |
| 5 | Validación — materialización (D7/D8/D13.1) | PR 5 (base = PR 4) | `pytest tests/extraccion/test_orden_compra.py tests/extraccion/test_service.py -k orden_compra` | `pytest tests/extraccion -m integration` contra el proyecto Supabase de test (crea filas reales en `ordenes_compra`/`oc_items`/`entregas_oc`) | Rama `orden_compra` de `validar_extraccion()` + inserts nuevos de `repository.py`; revertir no afecta las ramas de licitación/comparativa |
| 6 | Frontend — resolución de cliente | PR 6 (base = PR 5) | `pnpm --filter frontend test -- OrdenCompraSelector ClienteBuscador` | `pnpm --filter frontend dev` + flujo manual: abrir una extracción OC, ver sugerencia, confirmar | `frontend/src/features/validar-extraccion/components/OrdenCompraSelector.tsx` + `ClienteBuscador.tsx` (archivos nuevos, sin otros consumidores) |
| 7 | Frontend — cabecera de grupo + entregas + carga múltiple | PR 7 (base = PR 6) | `pnpm --filter frontend test -- CabeceraOrdenCompra EntregasEditor FormCard` | `pnpm --filter frontend dev` + flujo manual: subir 3 archivos con `tipo=ordenes`, ver el listado agruparlos | `CabeceraOrdenCompra.tsx`, `EntregasEditor.tsx` (nuevos); `FormCard.tsx`/`ValidarExtraccionListado.tsx`/`PendientesTable.tsx` revierten a su diff anterior sin afectar licitación/comparativa |
| 8 | Frontend — wiring final (`ValidarExtraccionDetalle`, `useFilasEditables`, tipos de API) | PR 8 (base = PR 7) | `pnpm --filter frontend test -- ValidarExtraccionDetalle useFilasEditables` | `pnpm --filter frontend dev` + flujo manual end-to-end: cargar OC → validar → confirmar | `ValidarExtraccionDetalle.tsx` rama `orden_compra` + `useFilasEditables.ts`; revertir deja licitación/comparativa exactamente como están hoy (ramas separadas por `documentType`) |
| 9 | Documentación + verificación integral (tracker → main) | PR 9 (base = PR 8, es el tracker) | `pytest tests/ --cov=services` | `pnpm --filter frontend build` + `pytest tests/ --cov=services` completos | `docs/modulos/compras/README.md`; sin código de producción nuevo, revertir es solo docs |

---

## Phase 1: Esquema (Foundation) — bloquea todo lo demás

- [ ] 1.1 Ejecutar contra el proyecto Supabase de test (`grnamollopxdlstcpxhc`) las 6 queries de
  verificación previa de `design.md` § "Verificación previa obligatoria": `uq_oc` existe con ese
  nombre exacto; ninguna FK la referencia; `entregas_oc_items` no tiene ya `cantidad_planificada`;
  `clientes` tiene `uq_cli_id_drog UNIQUE (id, drogueria_id)`; existen `mismo_tenant(uuid)`,
  `get_rol()`, `es_superadmin()`; `extraction_results` no tiene ya `grupo_id`. Registrar el
  resultado de cada query antes de continuar.
- [ ] 1.2 Crear `supabase/migrations/0025_orden_compra_desde_extraccion.sql` (read-only reference:
  contenido completo ya especificado en `design.md` § Migration) — guard de versión de Postgres,
  `ALTER TABLE ordenes_compra` (`proceso_comercial_id` nullable + `ck_oc_anclaje`), drop de `uq_oc` y
  alta de `uq_oc_por_cliente`/`uq_oc_por_proceso`, `entregas_oc_items.cantidad_planificada` +
  `ck_eoci_planificada`, tabla `oc_cliente_alias` completa con sus 4 políticas RLS
  (`oca_sel/ins/upd/del`) y `GRANT`s, `extraction_results.grupo_id` + `idx_er_grupo`.
- [ ] 1.3 Crear `supabase/migrations/0025_orden_compra_desde_extraccion.down.sql` con los 4 avisos
  documentados (orden datos-antes-que-esquema, `uq_oc` global más restrictivo, pérdida de
  `oc_cliente_alias`, disolución de grupos pendientes) y los `DROP`/`ALTER` en el orden inverso.
- [ ] 1.4 Aplicar `0025` contra el proyecto Supabase de test y verificar en vivo: `ck_oc_anclaje`
  rechaza una fila con ambos anclajes en `NULL`; `uq_oc_por_cliente` y `uq_oc_por_proceso` existen y
  tienen el `WHERE` correcto; `oc_cliente_alias` tiene RLS habilitada y las 4 políticas; los `GRANT`
  a `authenticated`/`service_role` están aplicados; `idx_er_grupo` existe como índice parcial.
- [ ] 1.5 Aplicar la down migration sobre el mismo entorno de test para confirmar que revierte sin
  error partiendo de una base sin filas que colisionen, y volver a aplicar `0025` para dejar el
  entorno listo para las fases siguientes.
- [ ] 1.6 Actualizar `docs/schema/extractor_final.sql`: reflejar `0025` completa (`ck_oc_anclaje`,
  los dos índices parciales, `cantidad_planificada`, `CREATE TABLE oc_cliente_alias` con su RLS,
  `extraction_results.grupo_id`) y corregir el drift de C4 (`ordenes_compra` en el snapshot no lista
  `deleted_at`/`created_by`/`updated_by`/`deleted_by`, que sí existen en la base viva) verificando
  contra la base real, no contra el `CREATE TABLE` desactualizado.

## Phase 2: Extracción — Tramo 1 (`services/extraccion/`)

> Depende de Phase 1 solo por completitud de esquema (esta fase no escribe en las tablas nuevas
> directamente; `extraction_results.grupo_id` sí se usa aquí).

- [ ] 2.1 [RED] Crear `tests/fixtures/orden_compra/` con al menos 3 documentos de muestra (PDF,
  imagen, Excel — HTML opcional) y sus CSV esperados según la gramática de D6
  (`numero_oc;fecha_emision;cuit_cliente;razon_social_cliente;direccion_entrega;cantidad_entregas;numero_renglon;descripcion;cantidad;precio_unitario;entregas`).
  **Obligatorio**: al menos un fixture cuyo documento NO declare número de línea, con
  `numero_renglon` vacío en todas las filas del CSV esperado (detecta si el prompt inventa
  números — C10).
- [ ] 2.2 [RED] Crear `tests/test_robot_orden_compra.py` con tests que mockean la llamada a Gemini y
  verifican: `procesar_orden_compra(ruta, nombre) -> Path` escribe un CSV en disco con el
  delimitador `;`, UTF-8, `csv.QUOTE_MINIMAL` (igual que `robot_comparativas.py:850-859`); las
  columnas de D6 en el orden correcto; el caso sin número de línea produce celda vacía sin excepción;
  un plan `entregas` con gramática `"50@30|50@60"` se escribe tal cual (el parseo ocurre después, en
  validación, no acá).
- [ ] 2.3 [GREEN] Crear `services/extraccion/robot_orden_compra.py`: prompt Gemini +
  `procesar_orden_compra(ruta, nombre) -> Path`, misma firma y estructura que `procesar_comparativa`.
  El prompt debe **prohibir explícitamente** inventar `numero_renglon` — instrucción literal de dejar
  la celda vacía cuando el documento no declara número de línea, sin autoincrementar ni derivar del
  orden de aparición.
- [ ] 2.4 [REFACTOR] Correr los fixtures reales de 2.1 contra `procesar_orden_compra` (sin mock de
  Gemini, llamada real controlada) y ajustar el prompt hasta que los 3+ goldens coincidan
  exactamente con el CSV esperado, incluido el caso sin numeración.
- [ ] 2.5 [RED] En `tests/test_main_integration.py`, invertir
  `TestProcesarTipoOrdenes::test_tipo_ordenes_retorna_422_sin_llamar_robot` (líneas 442-460) a
  `test_tipo_ordenes_no_devuelve_422_e_invoca_robot_orden_compra`: mockea
  `services.extraccion.main.procesar_orden_compra`, sube con `tipo="ordenes"` y afirma
  `response.status_code != 422` y que el mock **sí** fue invocado. Agregar además: `.html`/`.htm`
  aceptados para `tipo=ordenes`; `grupo_id` inválido (no UUID v4) rechazado sin abortar el resto del
  formulario; `grupo_id` ausente se comporta igual que hoy (extracción suelta).
- [ ] 2.6 [GREEN] Modificar `services/extraccion/main.py`: eliminar el `HTTPException(422)` de
  `tipo=="ordenes"` (líneas 162-167); extender `permitidos` para `ordenes` con `.html`/`.htm`;
  reemplazar el mapeo binario `doc_type = "comparativa" if ... else "licitacion"` (línea 220) por un
  mapeo de tres vías que incluya `orden_compra`; tercera rama en el bloque `_GEMINI_SEMAPHORE`
  (líneas 240-255) que invoca `procesar_orden_compra`; nuevo `grupo_id: str = Form("")`, validado
  como UUID v4, propagado a `schedule_persist_output`, ignorado si `tipo != "ordenes"`.
- [ ] 2.7 [GREEN] Modificar `services/extraccion/persistent_output.py`: `_DOC_TYPES_SOPORTADOS`
  (línea 31) → `{"comparativa", "licitacion", "orden_compra"}`, actualizar el comentario obsoleto de
  las líneas 28-30; `persistir_output_final(..., grupo_id: str | None = None)` agrega `grupo_id` a
  `payload_base` solo si viene.
- [ ] 2.8 [GREEN] Modificar `services/extraccion/background_tasks.py`: `schedule_persist_output` pasa
  `grupo_id` a `persistir_output_final` (parámetro pasante, sin lógica nueva).
- [ ] 2.9 Correr `pytest tests/test_robot_orden_compra.py tests/test_main_integration.py -k ordenes`
  en verde y confirmar que las suites existentes de licitación/comparativa en el mismo archivo no se
  rompieron.

## Phase 3: Validación — Resolución de cliente (D3/D3.1/D3.2)

> Depende de Phase 1 (tabla `oc_cliente_alias`). No depende de Phase 2.

- [ ] 3.1 [RED] Crear `tests/extraccion/test_cliente_candidato.py` con los casos de
  `resolver_cliente_candidato`: nivel 1 (alias exacto tras `normalizar_descripcion`) gana sobre nivel
  2 aunque ambos resuelvan y difieran; nivel 2 con CUIT exclusivo → 1 candidato; CUIT con
  `cuit_no_exclusivo=true` (C6) → N candidatos; sin match en ningún nivel → `origen='ninguno'`, 200 y
  lista vacía (no excepción); CUIT malformado (≠11 dígitos tras normalizar) → se saltea nivel 2,
  `advertencias[]`; tercero con CUIT pero sin fila en `clientes` → candidato omitido + advertencia;
  cliente con `activo=false` → incluido pero marcado; **aserción explícita de que la función no hace
  ningún write** (mock de escritura, o verificación de que la tabla no cambió).
- [ ] 3.2 [RED] En el mismo archivo, cubrir el threat-matrix de resolución de cliente: alias no se
  escribe sin confirmación humana (`test_alias_no_se_escribe_sin_confirmacion`); corrección de alias
  pisa `cliente_id` y resetea `veces_confirmado=1` (`test_correccion_pisa_y_resetea`); texto de
  cabecera vacío o solo puntuación no genera alias, rechazado por `ck_oca_texto`
  (`test_texto_vacio_no_genera_alias`); alias de la droguería A invisible desde B
  (`test_alias_aislado_por_drogueria`).
- [ ] 3.3 [RED] Tests unitarios de `_normalizar_cuit`: `"30-12345678-9"`, `"30123456789"`,
  `"30.123.456.78 9"` → mismos 11 dígitos; `"1234"` → `None` + advertencia. Y de la clave de alias:
  `normalizar_descripcion("Hospital Público Ñandú S.A. - Sede Nº2") == "HOSPITAL PUBLICO NANDU S A SEDE N 2"`,
  dos variantes tipográficas del mismo encabezado colapsan a la misma clave (test de no-regresión:
  `services/presupuestacion/core/texto.py` no se modifica en este cambio).
- [ ] 3.4 [GREEN] Agregar a `services/presupuestacion/extraccion/models.py`: `OrigenCandidato`
  (`Literal["alias", "cuit", "cuit_compartido", "ninguno"]`), `CandidatoCliente`, `CandidatoClienteOut`
  — exactamente como en `design.md` § Interfaces/Resolución de cliente.
- [ ] 3.5 [GREEN] Agregar a `services/presupuestacion/extraccion/repository.py`:
  `buscar_alias_cliente(texto_normalizado)`, `upsert_alias_cliente(...)` (UPSERT sobre `uq_oca`,
  incrementa `veces_confirmado` en reconfirmación idéntica, resetea a 1 en corrección),
  `buscar_clientes_por_cuit(cuit_normalizado)` (join `terceros` ⋈ `clientes`, respeta
  `cuit_no_exclusivo`).
- [ ] 3.6 [GREEN] Agregar a `services/presupuestacion/extraccion/service.py`: `_normalizar_cuit()`,
  `resolver_cliente_candidato(client, *, drogueria_id, cuit_extraido, texto_extraido) ->
  CandidatoClienteOut` (3 niveles con cortocircuito, nunca escribe, nunca levanta excepción por "no
  encontrado"), `_registrar_alias_cliente()` (UPSERT, se invoca solo dentro de una confirmación
  exitosa — ver Phase 5, no expuesto todavía).
- [ ] 3.7 [GREEN] Agregar a `services/presupuestacion/extraccion/router.py`:
  `GET /extracciones/{id}/cliente-candidato`, roles `_ROLES_VALIDAR` (existente, sin tupla nueva —
  D12), con `_verificar_pertenencia` existente.
- [ ] 3.8 [REFACTOR] Correr `pytest tests/extraccion/test_cliente_candidato.py -m integration` contra
  el proyecto Supabase de test y confirmar los 3 niveles, la precedencia, y el aislamiento
  multi-tenant en vivo.

## Phase 4: Validación — Agrupación multi-archivo (D13)

> Depende de Phase 1 (`extraction_results.grupo_id`). No depende de Phase 3.

- [ ] 4.1 [RED] Crear `tests/extraccion/test_grupo_extracciones.py`: `_leer_filas_grupo` con
  `grupo_id IS NULL` → forma idéntica a la de un archivo suelto (no-regresión de
  licitación/comparativa); 3 miembros → filas concatenadas en orden `created_at ASC, id ASC`, con
  `_archivo`/`_extraction_id` poblados; **aserción explícita de que NO transforma**: la cantidad de
  filas devueltas es la suma exacta de las de cada miembro y ninguna `cantidad`/`numero_renglon`
  cambia respecto del CSV de origen, ni siquiera cuando los 3 archivos declaran el mismo conjunto de
  números de línea; `editable` se evalúa sobre el total concatenado contra `MAX_FILAS_EDITABLES`
  (500).
- [ ] 4.2 [RED] En el mismo archivo, `_conciliar_cabecera`: `numero_oc` distinto entre miembros →
  bloqueo; `razon_social`/`fecha_emision`/`direccion_entrega`/`cantidad_entregas` distintos →
  advertencia sin bloqueo; valor más frecuente gana; empate → primer miembro.
- [ ] 4.3 [RED] Las 5 precondiciones de `agrupar_extracciones` (una por test): ≥2 ids sin repetidos;
  todas existen y son de la droguería del usuario (404/403); todas `document_type='orden_compra'`
  (422); ninguna `validado=true` (409); a lo sumo un `grupo_id` distinto ya presente entre ellas
  (409). Más: `desagrupar_extracciones` deja `grupo_id=NULL` y disuelve el grupo de un solo miembro
  restante.
- [ ] 4.4 [RED] Threat-matrix de agrupación: agrupar una extracción ya validada → `ConflictError`
  antes del `UPDATE` (`test_agrupar_validada_rechazado`); renglones repetidos entre archivos nunca se
  fusionan ni suman (`test_renglones_repetidos_no_se_suman`); documento sin número de línea en un
  grupo de N archivos no bloquea ni se rellena (`test_grupo_sin_numero_de_renglon_se_materializa`);
  un miembro del grupo sin CSV en disco (volumen no montado) levanta `ExtraccionNoDisponibleError` en
  la primera lectura que falle, antes de cualquier write (`test_miembro_sin_csv_aborta`). En
  `tests/extraccion/test_router.py`, agregar `test_agrupar_multi_tenant_rechazado`: ids de dos
  droguerías (solo posible como `superadmin`, exento del chequeo de tenant por id) → `ValidationError`
  porque los N miembros deben compartir `drogueria_id` entre sí.
- [ ] 4.5 [GREEN] Agregar a `services/presupuestacion/extraccion/models.py`: `MiembroGrupo`,
  `AgruparExtraccionesRequest` (`extraction_ids: list[str] = Field(min_length=2)`); extender
  `FilasExtraccionOut` con `grupo_id: str | None`, `miembros: list[MiembroGrupo] = []`,
  `advertencias_cabecera: list[str] = []` (sin `modo_fusion_sugerido` — D13.1 lo elimina).
- [ ] 4.6 [GREEN] Agregar a `services/presupuestacion/extraccion/repository.py`:
  `listar_miembros_de_grupo()`, `actualizar_grupo_id()`, `marcar_validadas()` (bulk sobre el grupo).
- [ ] 4.7 [GREEN] Agregar a `services/presupuestacion/extraccion/service.py`: `_leer_filas_grupo()`
  (concatena tal cual, sin dedup/fusión/renumeración — D13.1; `grupo_id IS NULL` se comporta como hoy
  con N=1), `_conciliar_cabecera()`, `agrupar_extracciones()` / `desagrupar_extracciones()` con las 5
  precondiciones validadas **antes** del `UPDATE`. Confirmar explícitamente que **no** se crea
  `_fusionar_filas()`.
- [ ] 4.8 [GREEN] Agregar a `services/presupuestacion/extraccion/router.py`: `POST
  /extracciones/agrupar`, `POST /extracciones/desagrupar`, roles `_ROLES_VALIDAR` (sin tupla nueva),
  `_verificar_pertenencia` aplicado **por cada id** de la lista con el user client antes de tocar
  nada con el service client — mismo patrón `*_para_endpoint` ya establecido.
- [ ] 4.9 [REFACTOR] Correr `pytest tests/extraccion/test_grupo_extracciones.py -m integration` y
  `pytest tests/extraccion/test_router.py -k agrupar` contra el proyecto Supabase de test.

## Phase 5: Validación — Materialización (D1, D7, D8, D13.1)

> Depende de Phase 1, 3 (necesita `resolver_cliente_candidato`/`_registrar_alias_cliente` ya
> definidas, aunque el endpoint de confirmación es nuevo acá) y 4 (necesita `_leer_filas_grupo` para
> el caso multi-archivo). Es la fase más grande — considerar partirla en dos PRs si el diff real
> supera el estimado.

- [ ] 5.1 [RED] Crear `tests/extraccion/test_orden_compra.py` con tabla de casos de
  `repartir_cantidad` (D8): `(100, 3) -> [34,34,32]`; `(100, 1) -> [100]`; `(7, 2) -> [4,3]`;
  `(10.5, 4)`; `(0, 3)`. **Property test**: `sum(repartir_cantidad(c, n)) == c` para un rango de `c`
  y `n>=1` generados.
- [ ] 5.2 [RED] En el mismo archivo, `_validar_orden_compra_override`: suma de `entregas` por línea
  ≠ `cantidad` del renglón; cero entregas (`entregas: []` viola `min_length=1` del modelo, cubrir
  también el caso de lista no vacía pero sin desglose válido); `precio_unitario` vacío/no numérico;
  clave de `cantidades_por_posicion` fuera del rango `1..len(filas)`; acumulación de múltiples
  errores en un solo 422 (mismo patrón que
  `test_validar_filas_override_acumula_errores_de_multiples_filas` existente); `cliente_id` que no
  existe / no es cliente / es de otra droguería → `ValidationError` antes del primer write. Confirmar
  que **no** existe el caso "`numero_renglon` duplicado" (imposible por construcción, D13.1).
  Threat-matrix: documento sin `precio_unitario` detectable no bloquea la extracción, pero el editor
  lo exige antes de confirmar (`test_precio_vacio_bloquea_confirmacion`).
- [ ] 5.3 [RED] Test unitario de la asignación de `numero_renglon` (D13.1): filas con
  `numero_renglon_documento` `"7","3",None` en ese orden → `oc_items.numero_renglon` `1,2,3`; dos
  filas con el mismo `numero_renglon_documento` → `1,2` sin conflicto; todas las filas sin número de
  documento → `1..N` igual. Test de no-regresión: `_materializar_licitacion` sigue leyendo
  `int(fila["item"])` sin cambios (D13.2) — no tocar esa función.
- [ ] 5.4 [RED] Invertir en `tests/extraccion/test_service.py` (líneas 385-401)
  `test_validar_orden_compra_no_implementado` a un test de materialización exitosa: dado un
  `seed_extraction_result_factory("orden_compra", ...)` y un `cliente_id` válido,
  `validar_extraccion(..., orden_compra=OrdenCompraOverride(...))` crea filas en `ordenes_compra` /
  `oc_items` / `entregas_oc` / `entregas_oc_items`, con `estado='emitida'`,
  `proceso_comercial_id IS NULL`, `extraction_id` y `cantidad_entregas` poblados. Agregar en el mismo
  archivo: `_materializar_orden_compra` crea `entregas_oc_items.cantidad_planificada` sumando la
  cantidad de cada renglón; **ninguna llamada a `entregar_stock_producto`** (aserción explícita sobre
  el mock — invariante duro "confirmar no descuenta stock"); `proceso_comercial_id` ausente no
  levanta error en esta rama; `extraction_results.validado` queda en `true`.
- [ ] 5.5 [RED] Test de confirmación de grupo (depende de Phase 4): una sola fila en
  `ordenes_compra` a partir de N archivos; `extraction_id` = el ancla (la extracción que el usuario
  abrió); **todos** los miembros del grupo quedan `validado=true` con el mismo `validado_por`/
  `validado_at`; si un miembro ya estaba `validado=true`, `ConflictError` antes de escribir.
- [ ] 5.6 [RED] Test de unicidad (D5) end-to-end vía `validar_extraccion`: mismo `numero_oc` + dos
  `cliente_id` distintos de la misma droguería → ambas confirmaciones OK; mismo `numero_oc` + mismo
  cliente → `ConflictError`.
- [ ] 5.7 [GREEN] Agregar a `services/presupuestacion/extraccion/models.py`: `FilaOrdenCompraIn`
  (`numero_renglon_documento: str | None = None`, `descripcion`, `cantidad`, `precio_unitario`,
  `producto_id: str | None = None`), `EntregaPlanIn` (`numero_entrega`, `plazo_dias`,
  `cantidades_por_posicion: dict[str, str] | None`), `OrdenCompraOverride` (`numero_oc`,
  `cliente_id`, `razon_social_extraida`, `fecha_emision`, `direccion_entrega`, `notas`,
  `filas: list[FilaOrdenCompraIn]`, `entregas: list[EntregaPlanIn]` con `min_length=1`) — **sin**
  `modo_fusion` ni alias `ModoFusion`. Extender `ValidarExtraccionRequest.orden_compra:
  OrdenCompraOverride | None = None`. Extender `ResultadoValidarExtraccion`:
  `proceso_comercial_id: str | None` (era `str`), `orden_compra_id: str | None = None`,
  `entregas_creadas: int = 0`, `renglones_sin_producto: int = 0`,
  `extracciones_validadas: int = 1`.
- [ ] 5.8 [GREEN] Agregar a `services/presupuestacion/extraccion/service.py`: `repartir_cantidad()`
  (D8: reparto entero con resto al frente; reparto decimal con resto al final, usando `Decimal`),
  `_validar_orden_compra_override()` (puro, corre antes del primer write: valida `cliente_id`,
  coherencia de `numero_oc` entre miembros del grupo, suma de entregas por posición == `cantidad` del
  renglón, acumula todos los errores en un solo `ValidationError`).
- [ ] 5.9 [GREEN] Agregar a `services/presupuestacion/extraccion/service.py`:
  `_materializar_orden_compra()` — asigna `numero_renglon = 1..N` por posición sobre `override.filas`
  (descartando `numero_renglon_documento`, D13.1), inserta `ordenes_compra`
  (`cliente_id`, `proceso_comercial_id=NULL`, `estado='emitida'`, `extraction_id=<ancla>`,
  `cantidad_entregas`), `oc_items`, `entregas_oc` (`estado='pendiente'`) y `entregas_oc_items`
  (`cantidad_planificada` desde `repartir_cantidad`/`cantidades_por_posicion`, `cantidad_entregada=0`,
  `cantidad_rechazada=0`); si el grupo tiene más de un miembro, marca **todos** como `validado=true`
  vía `marcar_validadas()`; registra `registrar_evento_ciclo_vida(entidad="orden_compra",
  tipo_cambio="creacion", origen="usuario")` + `registrar_cambio` de `estado` `None -> 'emitida'`
  (mismo patrón de auditoría que `crear_orden_compra`, D4). Al final, invoca
  `_registrar_alias_cliente()` (Phase 3) **solo si** la materialización tuvo éxito.
- [ ] 5.10 [GREEN] Extender `_TIPOS_CON_LECTURA_DE_FILAS` (línea 39) con `"orden_compra"` y corregir
  su comentario. Agregar la rama `orden_compra` en `validar_extraccion()` (líneas 442-463): usa
  `_leer_filas_grupo()` si corresponde, corre `_validar_orden_compra_override()` y
  `_materializar_orden_compra()`, **saltea** `_resolver_proceso_comercial_id`. Confirmar que
  `_materializar_licitacion` (línea 234) **no se toca**.
- [ ] 5.11 [GREEN] Agregar a `services/presupuestacion/extraccion/repository.py` los inserts de
  `ordenes_compra` / `oc_items` / `entregas_oc` / `entregas_oc_items` para la ruta de extracción,
  respetando la nota de frontera de módulos de `design.md` (escritura directa a tablas de `compras/`
  sin importar `compras/repository.py`).
- [ ] 5.12 [GREEN] Agregar en `services/presupuestacion/extraccion/router.py` el paso de
  `body.orden_compra` a `validar_extraccion_para_endpoint` en `POST /extracciones/{id}/validar`
  (mismo endpoint existente, sin roles nuevos).
- [ ] 5.13 [REFACTOR] Correr `pytest tests/extraccion -m integration` completo contra el proyecto
  Supabase de test; confirmar cero regresiones en licitación/comparativa y que las filas de
  `oc_cliente_alias`/`ordenes_compra`/`oc_items`/`entregas_oc`/`entregas_oc_items` creadas en los
  tests de integración se limpian correctamente entre corridas (fixtures de `conftest.py`).

## Phase 6: Frontend — Resolución de cliente (D3/D3.2)

> Depende de Phase 3 (endpoint `GET /extracciones/{id}/cliente-candidato`).

- [ ] 6.1 [RED] Tests de `ClienteBuscador` (nuevo archivo de test junto al componente, convención del
  proyecto): `q` de 1 carácter no dispara request; debounce de 300 ms coalesce pulsaciones; la
  llamada lleva `rol: 'todos'` (no `'clientes'` — test explícito de C7-iii) y filtra por
  `tiene_rol_cliente`; sin `q` no hay ningún request al montar (arranca vacío).
- [ ] 6.2 [RED] Tests de `OrdenCompraSelector`: sugerencia de alias se muestra preseleccionada pero
  "Confirmar OC" sigue deshabilitado hasta el click explícito de "Confirmar cliente" (test del
  invariante humano); "No es este" abre `ClienteBuscador`; N candidatos de CUIT compartido → N radio
  buttons, ninguno preseleccionado; sin sugerencia → cae directo al buscador.
- [ ] 6.3 [GREEN] Modificar `frontend/src/lib/api/extracciones.ts`: tipos `CandidatoCliente`,
  `CandidatoClienteOut`, `OrigenCandidato`; función `obtenerClienteCandidato(extractionId)`.
- [ ] 6.4 [GREEN] Crear `frontend/src/features/validar-extraccion/components/ClienteBuscador.tsx`:
  búsqueda manual sobre `listarTerceros({ q, rol: 'todos', pageSize: 20 })` (D3.2), `q` mínimo 2
  caracteres, debounce 300 ms, filtrado en cliente por `tiene_rol_cliente`, muestra `razon_social` +
  `cuit` + `codigo_interno`.
- [ ] 6.5 [GREEN] Crear `frontend/src/features/validar-extraccion/components/OrdenCompraSelector.tsx`:
  muestra la sugerencia (alias o CUIT) con botones "Confirmar" / "No es este"; con N candidatos de
  CUIT compartido, lista de radio buttons; sin sugerencia o tras rechazarla, cae a `ClienteBuscador`;
  botón de confirmar la OC deshabilitado hasta que haya `cliente_id` elegido; sin input de código.
- [ ] 6.6 [REFACTOR] Correr `pnpm --filter frontend test -- OrdenCompraSelector ClienteBuscador` en
  verde; probar manualmente contra el backend de Phase 3 (`pnpm --filter frontend dev` +
  `GET /extracciones/{id}/cliente-candidato` real).

## Phase 7: Frontend — Cabecera de grupo, entregas y carga múltiple (D13, D13.1, D8)

> Depende de Phase 4 (agrupar/desagrupar) para `ValidarExtraccionListado`, y de Phase 2 (`grupo_id`
> en `/procesar`) para `FormCard`. No depende de Phase 6.

- [ ] 7.1 [RED] Tests de `CabeceraOrdenCompra`: `numero_oc` en desacuerdo entre miembros → campo en
  rojo y confirmar deshabilitado; editarlo a un valor único lo habilita; desacuerdo de
  `razon_social`/`fecha_emision`/`direccion_entrega` muestra aviso pero no bloquea.
- [ ] 7.2 [RED] Tests de `EntregasEditor`: la suma por renglón que no cuadra deshabilita confirmar,
  con el mismo mensaje que el espejo del servidor (`_validar_orden_compra_override`); reparto
  automático parejo visible cuando el usuario solo carga cantidad de entregas.
- [ ] 7.3 [RED] Tests de `FormCard` multi-archivo: con `tipo='ordenes'` el input acepta múltiples
  archivos; con 3 archivos se disparan 3 `procesarDocumento` en secuencia con **el mismo**
  `grupoId` (`crypto.randomUUID()`); un 409 de duplicado en el segundo archivo no aborta el tercero y
  se reporta por archivo; con `tipo='licitaciones'` el input **no** es múltiple.
- [ ] 7.4 [RED] Tests de `ValidarExtraccionListado`: acción "Agrupar seleccionadas" deshabilitada con
  <2 filas seleccionadas o con tipos mixtos; tras agrupar, las filas muestran el indicador de grupo;
  acción inversa "Desagrupar" disponible sobre un grupo existente.
- [ ] 7.5 [GREEN] Crear `frontend/src/features/validar-extraccion/components/CabeceraOrdenCompra.tsx`:
  cabecera única editable para todo el grupo, precargada con el valor más frecuente entre miembros,
  campos en desacuerdo marcados, bloqueo solo por `numero_oc`.
- [ ] 7.6 [GREEN] Crear `frontend/src/features/validar-extraccion/components/EntregasEditor.tsx`:
  cantidad de entregas + plazo por entrega + desglose opcional por línea, validación en vivo.
- [ ] 7.7 [GREEN] Modificar `frontend/src/lib/api/extraccion.ts`: `DocumentoReciente.document_type`
  suma `'orden_compra'`; `ProcesarPayload.grupoId?: string`; `procesarDocumento` lo manda como campo
  `grupo_id` del `FormData`.
- [ ] 7.8 [GREEN] Modificar `frontend/src/features/carga-documentos/components/FormCard.tsx`: quitar
  `disabled: true` de la opción `ordenes` (línea 37) y su badge "Próximamente"; `<input type="file"
  multiple>` solo cuando `tipo === 'ordenes'`; con N>1 archivos genera `crypto.randomUUID()` y hace N
  `procesarDocumento` en secuencia con ese `grupoId`, reportando el resultado por archivo;
  `esperarNuevoDocumento` pasa a esperar que el conteo crezca en N.
- [ ] 7.9 [GREEN] Modificar `frontend/src/features/validar-extraccion/ValidarExtraccionListado.tsx`:
  estado de selección múltiple + acción "Agrupar seleccionadas como una sola OC" (habilitada solo con
  ≥2 filas `orden_compra` no validadas seleccionadas) + acción inversa "Desagrupar".
- [ ] 7.10 [GREEN] Modificar `frontend/src/features/validar-extraccion/components/PendientesTable.tsx`:
  columna de checkbox (solo en filas `orden_compra` no validadas) + indicador visual de pertenencia a
  un grupo (`ETIQUETA_TIPO` ya contempla `orden_compra`, línea 8 — no tocar).
- [ ] 7.11 [GREEN] Agregar a `frontend/src/lib/api/extracciones.ts`: `agruparExtracciones(ids)`,
  `desagruparExtracciones(ids)`; extender `FilasExtraccionOut` con `miembros`/`advertencias_cabecera`
  (sin `modo_fusion_sugerido`).
- [ ] 7.12 [REFACTOR] Correr `pnpm --filter frontend test -- CabeceraOrdenCompra EntregasEditor
  FormCard ValidarExtraccionListado` en verde; probar manualmente el flujo de carga de 3 archivos
  contra el backend de Phase 2 y 4.

## Phase 8: Frontend — Wiring final (`ValidarExtraccionDetalle`, `useFilasEditables`)

> Depende de Phase 5 (payload `orden_compra` real), 6 y 7 (todos los componentes nuevos).

- [ ] 8.1 [RED] Tests de `useFilasEditables`: entrada `orden_compra` en
  `CAMPOS_POR_DOCUMENT_TYPE`; nuevo `CampoTipo` `'decimal-positivo'` valida `precio_unitario`;
  `parsearPlanEntregas()` parsea `"50@30|50@60"` y rechaza gramática malformada; columnas
  `_archivo`/`_extraction_id`/`numero_renglon` se muestran pero no son editables (click no abre
  `CeldaEditable`); `numero_renglon` se renderiza vacío cuando el documento no lo declaró.
- [ ] 8.2 [RED] Tests de `ValidarExtraccionDetalle`: con `documentType === 'orden_compra'` no
  renderiza `ProcesoComercialSelector`, renderiza `CabeceraOrdenCompra` + `OrdenCompraSelector` +
  `EntregasEditor`; el payload enviado lleva `orden_compra` y no `filas`; `puedeConfirmar` exige
  `cliente_id` confirmado y ≥1 entrega válida y cabecera sin bloqueos; `onBorrarFila`/`onAgregarFila`
  siguen cableadas igual que hoy (líneas 127-128) — no se tocan.
- [ ] 8.3 [RED] Test explícito de reconciliación manual (D13.1): con un grupo de 3 miembros, la tabla
  muestra la suma de las filas; `borrarFila` sobre una fila duplicada la saca del payload enviado; no
  existe ningún selector de modo de fusión en la pantalla.
- [ ] 8.4 [GREEN] Modificar `frontend/src/features/validar-extraccion/useFilasEditables.ts`: entrada
  `orden_compra` en `CAMPOS_POR_DOCUMENT_TYPE`; `CampoTipo` `'decimal-positivo'`;
  `parsearPlanEntregas()`; columnas sintéticas/de referencia no editables — `borrarFila`/`agregarFila`
  (líneas 118, 124) no se tocan.
- [ ] 8.5 [GREEN] Modificar `frontend/src/features/validar-extraccion/ValidarExtraccionDetalle.tsx`:
  rama `documentType === 'orden_compra'` que renderiza `CabeceraOrdenCompra` + `OrdenCompraSelector` +
  `EntregasEditor` en vez de `ProcesoComercialSelector`; envía `orden_compra` en vez de `filas`;
  `puedeConfirmar` con las tres condiciones.
- [ ] 8.6 [GREEN] Extender `frontend/src/lib/api/extracciones.ts` con los tipos restantes:
  `FilaOrdenCompraIn`, `EntregaPlanIn`, `OrdenCompraOverride`, `ValidarExtraccionPayload.orden_compra`;
  `ResultadoValidarExtraccion.proceso_comercial_id: string | null` (cambio de contrato — verificar que
  ningún consumidor rompe, `ValidarExtraccionDetalle.tsx:62-66` solo invalida y navega).
- [ ] 8.7 [REFACTOR] Correr `pnpm --filter frontend test -- ValidarExtraccionDetalle
  useFilasEditables` en verde. Flujo manual end-to-end completo contra el backend real: subir 1
  archivo → validar con sugerencia de alias → confirmar → verificar `ordenes_compra`/`oc_items`/
  `entregas_oc` en la base de test. Repetir con 3 archivos agrupados al subir y con 2 extracciones
  agrupadas post-hoc.

## Phase 9: Documentación y verificación integral

- [ ] 9.1 Modificar `docs/modulos/compras/README.md`: documentar que la dirección del flujo es hacia
  el cliente (no hacia el proveedor) y el ciclo plan → export → Progress → import, dejando explícito
  que export/import (Tramo 3) quedan fuera de este cambio y siguen como trabajo futuro.
- [ ] 9.2 Anotar en `openspec/changes/orden-compra/design.md` (ya escrito, sin re-editar el
  contenido) que las Open Questions "R1 — validación de formato con Progress v8" y "Reconciliar
  `orden-compra-validacion` al archivar" siguen abiertas y no bloquean el archive de este tramo,
  para que `sdd-archive` no las de por resueltas.
- [ ] 9.3 Correr la suite completa `pytest tests/ --cov=services` y `pnpm --filter frontend build` +
  `pnpm --filter frontend test`, confirmar cero regresiones fuera del alcance de este cambio
  (licitación, comparativa, terceros, PCP).
- [ ] 9.4 Revisar manualmente cada escenario Given/When/Then de
  `openspec/changes/orden-compra/specs/orden-compra-extraccion/spec.md` y
  `openspec/changes/orden-compra/specs/orden-compra-validacion/spec.md` contra el comportamiento
  real, dejando constancia de cuáles quedaron cubiertos por qué test (insumo directo para
  `sdd-verify`).

---

## Notas de dependencia entre fases

```
Phase 1 (esquema)
   │
   ├──► Phase 2 (extracción Tramo 1)          ── independiente de 3/4/5
   │
   ├──► Phase 3 (resolución de cliente)        ── independiente de 4
   │
   ├──► Phase 4 (agrupación)                   ── independiente de 3
   │
   └──► Phase 5 (materialización) ◄── depende de 3 y 4

Phase 3 ──► Phase 6 (frontend cliente)
Phase 2 + Phase 4 ──► Phase 7 (frontend cabecera/entregas/carga múltiple)
Phase 5 + Phase 6 + Phase 7 ──► Phase 8 (frontend wiring final)
Phase 8 ──► Phase 9 (docs + verificación integral)
```

Phases 2, 3 y 4 pueden ejecutarse en paralelo por distintos work units una vez cerrada Phase 1 (no
comparten funciones ni archivos productivos entre sí, aunque comparten `models.py`/`repository.py`/
`router.py` de `extraccion/` como archivos — mergear con cuidado si se paralelizan work units 2/3/4
literalmente en simultáneo; el orden secuencial PR2→PR3→PR4 sugerido arriba evita ese conflicto de
archivo).
