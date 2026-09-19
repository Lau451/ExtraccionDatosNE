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

- [x] 1.1 Ejecutadas contra el proyecto Supabase de test (`grnamollopxdlstcpxhc`) las 6 queries de
  verificación previa. El batch de `sdd-apply` no tuvo herramienta de SQL directo (sin MCP de
  Supabase, sin `psql`/CLI); el orquestador completó los 2 checks pendientes con el MCP de Supabase
  directamente contra `pg_constraint`. Evidencia completa:
  - ✅ **Verificado en vivo**: `entregas_oc_items` NO tiene `cantidad_planificada` (probe PostgREST:
    `{"code":"42703","message":"column entregas_oc_items.cantidad_planificada does not exist"}` y
    ausente de `definitions.entregas_oc_items.properties` en el OpenAPI de `/rest/v1/`).
  - ✅ **Verificado en vivo**: `extraction_results` NO tiene `grupo_id` (mismo patrón: `42703` +
    ausente del OpenAPI).
  - ✅ **Verificado en vivo**: `mismo_tenant(uuid)`, `get_rol()`, `es_superadmin()` existen —
    `POST /rest/v1/rpc/get_rol` → `200 null`; `POST /rest/v1/rpc/es_superadmin` → `200 false`;
    `POST /rest/v1/rpc/mismo_tenant {"p_drogueria": "<uuid>"}` → `200 null` (el primer intento con
    un nombre de parámetro incorrecto devolvió `PGRST202` con el hint
    `"Perhaps you meant to call the function public.mismo_tenant(p_drogueria)"`, confirmando además
    la firma real del parámetro).
  - ⚠️ **Confirmado indirectamente, no como constraint nombrado** (evidencia de PostgREST, sdd-apply):
    el OpenAPI de `/rest/v1/` para `ordenes_compra` muestra en vivo las columnas
    `deleted_at`/`created_by`/`updated_by`/`deleted_by` (evidencia independiente de C4, ver 1.6).
  - ✅ **Verificado con MCP de Supabase (`pg_constraint`), orquestador**: `uq_oc` existe en
    `ordenes_compra` con ese nombre exacto — `pg_get_constraintdef` devuelve
    `UNIQUE (numero_oc, version_numero)`.
  - ✅ **Verificado con MCP de Supabase, orquestador**: ninguna FK referencia `uq_oc` — query sobre
    `information_schema.table_constraints`/`constraint_column_usage`/`key_column_usage` filtrando
    `constraint_type = 'FOREIGN KEY'` y `ccu.constraint_name = 'uq_oc'` devuelve 0 filas.
  - **No se intentó ninguna verificación mutante** (insertar filas para forzar un conflicto de
    constraint) porque la tarea es explícitamente de solo lectura.
- [x] 1.2 Creado `supabase/migrations/0025_orden_compra_desde_extraccion.sql` — transcripción
  literal de `design.md` § Migration: guard de versión de Postgres, `ALTER TABLE ordenes_compra`
  (`proceso_comercial_id` nullable + `ck_oc_anclaje`), drop de `uq_oc` y alta de
  `uq_oc_por_cliente`/`uq_oc_por_proceso`, `entregas_oc_items.cantidad_planificada` +
  `ck_eoci_planificada`, tabla `oc_cliente_alias` completa con sus 4 políticas RLS
  (`oca_sel/ins/upd/del`) y `GRANT`s, `extraction_results.grupo_id` + `idx_er_grupo`. Ningún hallazgo
  de 1.1 contradijo las asunciones de `design.md`, así que no fue necesario ajustar el SQL.
- [x] 1.3 Creado `supabase/migrations/0025_orden_compra_desde_extraccion.down.sql` con los 4 avisos
  documentados (orden datos-antes-que-esquema, `uq_oc` global más restrictivo, pérdida de
  `oc_cliente_alias`, disolución de grupos pendientes) y los `DROP`/`ALTER` en el orden inverso.
- [x] 1.4 Aplicada `0025` contra el proyecto Supabase de test (MCP `apply_migration`, orquestador) y
  verificado en vivo con `pg_constraint`/`pg_indexes`/`pg_policies`/`information_schema`:
  - `ck_oc_anclaje`: `CHECK (((proceso_comercial_id IS NOT NULL) OR (cliente_id IS NOT NULL)))`.
  - `uq_oc_por_cliente` y `uq_oc_por_proceso` existen con el `WHERE` correcto (`cliente_id IS NOT
    NULL` / `cliente_id IS NULL` respectivamente).
  - `oc_cliente_alias`: `relrowsecurity = true`; las 4 políticas presentes (`oca_sel` SELECT,
    `oca_ins` INSERT, `oca_upd` UPDATE, `oca_del` DELETE).
  - Grants a `authenticated`/`service_role` presentes. Nota: `information_schema.role_table_grants`
    devuelve un set más amplio que los `GRANT` explícitos del script (incluye DELETE/REFERENCES/
    TRIGGER/TRUNCATE para `authenticated`) — verificado que es un patrón de privilegios por defecto
    de todo el proyecto (`terceros` tiene exactamente el mismo set), no una regresión de esta
    migración; RLS sigue siendo el gate real a nivel de fila.
  - `idx_er_grupo` existe como índice parcial: `... USING btree (grupo_id) WHERE (grupo_id IS NOT
    NULL)`.
  - `mcp__supabase__get_advisors(type: security)` corrido después de aplicar: sin hallazgos nuevos
    para `oc_cliente_alias` ni ninguna tabla tocada por esta migración (los 2 warnings preexistentes,
    funciones `SECURITY DEFINER` y leaked-password-protection, no están relacionados).
- [x] 1.5 Aplicada la down migration (MCP `execute_sql`, orquestador) sobre el mismo entorno de
  test: revirtió sin error. Reaplicada `0025` inmediatamente después (mismo método) para dejar el
  entorno listo para las Fases 2–5.
- [x] 1.6 Actualizado `docs/schema/extractor_final.sql`: `ordenes_compra` ahora declara
  `proceso_comercial_id` nullable + `ck_oc_anclaje`, `created_by`/`updated_by`/`deleted_at`/
  `deleted_by` (corrige el drift de C4 — **confirmado en vivo** vía el OpenAPI de `/rest/v1/`, que sí
  lista esas 4 columnas para `ordenes_compra` en la base de test); `uq_oc` reemplazado por
  `uq_oc_por_cliente`/`uq_oc_por_proceso` en la sección de índices; `entregas_oc_items` con
  `cantidad_planificada` + `ck_eoci_planificada`; tabla nueva `oc_cliente_alias` con su comentario y
  FKs; `extraction_results.grupo_id` + `idx_er_grupo`. La parte de "reflejar el contenido de 0025"
  se hizo por transcripción directa de la migración (1.2); la parte de C4 se verificó contra la base
  viva vía el probe de PostgREST descripto en 1.1, no contra el `CREATE TABLE` desactualizado.

## Phase 2: Extracción — Tramo 1 (`services/extraccion/`)

> Depende de Phase 1 solo por completitud de esquema (esta fase no escribe en las tablas nuevas
> directamente; `extraction_results.grupo_id` sí se usa aquí).

- [x] 2.1 [RED] Creado `tests/fixtures/orden_compra/` con 3 documentos de muestra reales — PDF
  (`01_pdf_con_renglon/documento.pdf`, generado con `reportlab`), Excel
  (`02_excel_sin_renglon/documento.xlsx`, `openpyxl`) e imagen
  (`03_imagen_con_renglon/documento.png`, `Pillow`) — más sus `esperado.csv` según la gramática de
  D6. El script generador (`_generar_fixtures.py`) queda junto a los fixtures para poder
  regenerarlos. **Obligatorio cumplido**: `02_excel_sin_renglon` es un documento que no numera sus
  renglones en ninguna forma (ni columna, ni referencia textual); su `esperado.csv` tiene
  `numero_renglon` vacío en las 2 filas — es el caso C10. `01` y `03` sí declaran número de línea
  (1/2 y 1/2/3 respectivamente) y ejercitan además la gramática de `entregas`
  (`50@30|50@60` en 01; `50@15|50@30|50@45` y `40@10|40@20` en 03, con un renglón intermedio sin
  desglose).
- [x] 2.2 [RED] Creado `tests/test_robot_orden_compra.py` (13 tests): `TestConstruirFilas` (5 tests,
  0 mocks — función pura) cubre repetición de cabecera por renglón, `numero_renglon` vacío sin
  fabricarlo (C10), preservación del valor declarado, gramática de `entregas` verbatim y lista vacía
  sin excepción. `TestProcesarOrdenCompra` (3 tests, mockeando `parse_document` y
  `_llamar_gemini_orden_compra`) verifica CSV en disco con `;`, UTF-8, `csv.QUOTE_MINIMAL`, columnas
  D6 en el orden correcto, caso sin numeración sin excepción, y `OrdenCompraSinRenglonesError` si no
  hay renglones. Confirmado RED: `ModuleNotFoundError: No module named
  'services.extraccion.robot_orden_compra'` (1 error de colección, ejecutado antes de 2.3).
- [x] 2.3 [GREEN] Creado `services/extraccion/robot_orden_compra.py`: `_FIELDNAMES` (orden D6),
  `_llamar_gemini_orden_compra()` (mismo patrón que `_llamar_gemini_json` de
  `robot_comparativas.py` — JSON mode, detección de truncamiento antes de parsear),
  `_construir_filas()` (pura, sin I/O — repite cabecera, preserva `numero_renglon` tal cual),
  `_escribir_csv()` (idéntica a `robot_comparativas.py:850-859`: `;`, UTF-8, `QUOTE_MINIMAL`),
  `_mover_a_procesados()`, y `procesar_orden_compra(ruta, nombre, *, session_id=None,
  instrucciones_extra=None) -> Path` — misma firma y estructura que `procesar_comparativa`. El
  prompt prohíbe explícitamente inventar `numero_renglon` con una sección "CRITICAL RULE" dedicada.
  `pytest tests/test_robot_orden_compra.py -q` → **8 passed** (RED anterior confirmado, ahora GREEN).
- [x] 2.4 [REFACTOR] Corridos los 3 fixtures reales de 2.1 contra `procesar_orden_compra` sin mock de
  Gemini (llamada real a `gemini-2.5-flash`, confirmada conectividad antes con un ping
  `generate_with_fallback` → `"PONG"`). Primera corrida: 2/3 coincidieron exactamente; `01` difería
  solo en `precio_unitario` (`"1.250,00"` obtenido vs `"1250,00"` esperado — Gemini preservó el
  separador de miles del documento). Ajustado el prompt: instrucción explícita de no incluir
  separador de miles en `precio_unitario`, con ejemplo literal (`"$1.250,00" -> "1250,00"`). Segunda
  corrida: **3/3 coinciden exactamente**. Repetido 2 veces más (3 corridas reales consecutivas en
  total, 9 documentos procesados) para confirmar estabilidad — sin desvíos en ninguna, incluido el
  caso sin numeración (02). Costo real de API asumido, como ya hacen licitación/comparativa.
- [x] 2.5 [RED] En `tests/test_main_integration.py`, invertida
  `TestProcesarTipoOrdenes::test_tipo_ordenes_retorna_422_sin_llamar_robot` a
  `test_tipo_ordenes_no_devuelve_422_e_invoca_robot_orden_compra` (mockea
  `services.extraccion.main.procesar_orden_compra`, afirma `status_code != 422` y `== 200`, y que el
  mock fue invocado). Agregados 6 tests más en la misma clase: `test_tipo_ordenes_acepta_html` /
  `_acepta_htm` (antes rechazados por `permitidos`, ahora 200), `test_grupo_id_invalido_retorna_422_
  sin_llamar_robot` (no UUID v4 → 422, robot no invocado — mismo patrón SC-25 que `licitacion_id`),
  `test_grupo_id_ausente_se_comporta_como_extraccion_suelta` (`None` propagado),
  `test_grupo_id_valido_se_propaga_a_schedule_persist_output`, y
  `test_grupo_id_ignorado_si_tipo_no_es_ordenes` (un `grupo_id` inválido con `tipo=""` NO aborta —
  se ignora por completo, confirmando que la validación solo corre para `tipo=="ordenes"`).
  Confirmado RED: `pytest tests/test_main_integration.py -k ordenes -q` → **7 failed** (6× `does not
  have the attribute 'procesar_orden_compra'` + 1× `KeyError: 'grupo_id'` en
  `mock_schedule.await_args.kwargs`), ejecutado antes de 2.6.
- [x] 2.6 [GREEN] Modificado `services/extraccion/main.py`: eliminado el `HTTPException(422)` fijo de
  `tipo=="ordenes"`, reemplazado por la validación fail-fast de `grupo_id` (nueva, ver abajo) que
  solo corre para ese tipo; `permitidos` para `ordenes` extendido con `.html`/`.htm`; mapeo binario
  de `doc_type` reemplazado por mapeo de tres vías (`comparativa`/`orden_compra`/`licitacion`);
  tercera rama en el bloque `_GEMINI_SEMAPHORE` que invoca `procesar_orden_compra` con la misma
  firma (`session_id`, `instrucciones_extra`) que las otras dos ramas; agregado el manejo de
  `OrdenCompraSinRenglonesError` (mismo patrón que `NoProvidersDetectedError`, 422). Nuevo
  `grupo_id: str = Form("")` + función `_validar_grupo_id()` (valida `UUID` + `.version == 4`,
  `HTTPException(422)` si es inválido, `None` si viene vacío o si `tipo != "ordenes"`), propagado a
  `schedule_persist_output`.
- [x] 2.7 [GREEN] Modificado `services/extraccion/persistent_output.py`: `_DOC_TYPES_SOPORTADOS` →
  `{"comparativa", "licitacion", "orden_compra"}`; corregido el comentario obsoleto que decía que
  `orden_compra` "todavía no tiene extractor propio"; `persistir_output_final(..., grupo_id: str |
  None = None)` agrega `grupo_id` a `payload_base` solo si viene (mismo patrón que
  `licitacion_id`/`proceso_comercial_id`).
- [x] 2.8 [GREEN] Modificado `services/extraccion/background_tasks.py`: `grupo_id: str | None = None`
  agregado a `_retry_persist()` y `schedule_persist_output()`, pasante hasta
  `persistir_output_final()` en ambos (llamada directa y rama de reintento recursivo) — sin lógica
  nueva, mismo patrón que `licitacion_id`.
- [x] 2.9 `pytest tests/test_robot_orden_compra.py tests/test_main_integration.py -k ordenes` → **7
  passed** (los 7 tests de `TestProcesarTipoOrdenes`; los tests de `test_robot_orden_compra.py` no
  matchean el keyword `ordenes` por nombre de clase/módulo — confirmados aparte:
  `pytest tests/test_robot_orden_compra.py -q` → **8 passed**). Confirmado que las suites de
  licitación/comparativa en `test_main_integration.py` no se rompieron:
  `pytest tests/test_main_integration.py -q` → **18 passed** (0 regresiones). Suite completa no
  integración: `pytest tests/ -q -m "not integration"` → **280 passed, 434 deselected** (vs. 266
  passed en el baseline de PR1 — +14 tests netos: +8 nuevos de `test_robot_orden_compra.py`, +6
  netos en `TestProcesarTipoOrdenes` tras invertir 1 test por 7).

## Phase 3: Validación — Resolución de cliente (D3/D3.1/D3.2)

> Depende de Phase 1 (tabla `oc_cliente_alias`). No depende de Phase 2.

- [x] 3.1 [RED] Creado `tests/extraccion/test_cliente_candidato.py` con los casos de
  `resolver_cliente_candidato`: nivel 1 gana sobre nivel 2 aunque ambos resuelvan y difieran
  (`test_nivel1_alias_gana_sobre_nivel2_aunque_ambos_resuelvan_y_difieran`, con
  `mock_cuit.assert_not_called()` probando el cortocircuito); nivel 2 CUIT exclusivo → 1 candidato
  (`test_nivel2_cuit_exclusivo_devuelve_un_candidato`); `cuit_no_exclusivo=true` (C6) → N candidatos
  (`test_nivel2_cuit_no_exclusivo_devuelve_n_candidatos`); sin match → `origen='ninguno'`, lista vacía,
  sin excepción (`test_sin_match_en_ningun_nivel_devuelve_ninguno_y_lista_vacia_sin_excepcion`); CUIT
  malformado → nivel 2 salteado + advertencia (`test_cuit_malformado_saltea_nivel2_y_deja_advertencia`,
  con `mock_cuit.assert_not_called()`); tercero con CUIT sin fila en `clientes` → omitido + advertencia
  (`test_tercero_con_cuit_pero_sin_fila_en_clientes_se_omite_con_advertencia`); cliente `activo=false`
  → incluido y marcado (`test_cliente_inactivo_se_incluye_marcado`); **aserción explícita de que no
  escribe** (`test_resolver_cliente_candidato_nunca_escribe`, mockeando
  `repo.upsert_alias_cliente` y confirmando `assert_not_called()`). Confirmado RED:
  `pytest tests/extraccion/test_cliente_candidato.py -m "not integration" -q` → 21 failed / 2 passed
  (los 2 que pasaron son los de `normalizar_descripcion`, función existente que este cambio no toca —
  ver 3.3). Los 21 fallos fueron `AttributeError` por atributos inexistentes en `service`/`repo`, la
  falla RED esperada.
- [x] 3.2 [RED] En el mismo archivo, threat-matrix de resolución de cliente: alias no se escribe sin
  confirmación (`test_alias_no_se_escribe_sin_confirmacion`); corrección pisa `cliente_id` y resetea
  `veces_confirmado=1` (`test_correccion_pisa_y_resetea`, unitario con `MagicMock` del client
  inspeccionando la `fila` enviada a `.upsert()`) — agregado también
  `test_reconfirmacion_identica_incrementa_veces_confirmado` y
  `test_primera_confirmacion_sin_alias_previo_arranca_en_uno` para cubrir las otras 2 ramas de la
  misma función; texto vacío/solo-puntuación no genera alias
  (`test_texto_vacio_no_genera_alias`, `test_texto_none_no_genera_alias`, unitarios contra el guard de
  `_registrar_alias_cliente`, no contra `ck_oca_texto` directamente — ver nota de diseño abajo); alias
  aislado por droguería (`test_alias_aislado_por_drogueria`, **integración en vivo**: alias creado en
  la droguería A, `resolver_cliente_candidato` desde B con el mismo texto cae a `origen='ninguno'`).
- [x] 3.3 [RED] Tests unitarios de `_normalizar_cuit`: los 3 formatos (`"30-12345678-9"`,
  `"30123456789"`, `"30.123.456.78 9"`) → mismos 11 dígitos (parametrizado); `"1234"`, `""`, `None` →
  `None`. Clave de alias: `test_normalizar_descripcion_produce_la_clave_de_alias_esperada` y
  `test_normalizar_descripcion_dos_variantes_tipograficas_colapsan_a_la_misma_clave` — **desviación de
  diseño encontrada y documentada en el test**: el ejemplo de `design.md` § D3.1
  (`normalizar_descripcion("Hospital Público Ñandú S.A. - Sede Nº2") == "HOSPITAL PUBLICO NANDU S A SEDE N 2"`)
  no coincide con el comportamiento real y verificado en vivo de la función (sin tocarla): produce
  `"...SEDE NO2"`, no `"...SEDE N 2"` — NFKD descompone `º` (U+00BA) a la letra `"o"`, que `[^\w\s]` no
  reemplaza porque `"o"` es `\w`. El test de no-regresión quedó con el valor REAL (verificado con
  `python -c "..."` contra la función sin modificar), que es lo relevante para D3.1 (colapsar
  variantes tipográficas a la misma clave), no la prosa del documento. También se corrigió la segunda
  aserción: `"S.A."` normaliza a `"S A"` (con espacio, no a `"SA""`) porque la puntuación se reemplaza
  por espacio, no se elimina — el par de variantes se cambió a uno que sí colapsa de verdad
  (`"Clínica San Roque"` vs `"  clinica   SAN roque  "` → `"CLINICA SAN ROQUE"` en ambos casos).
- [x] 3.4 [GREEN] Agregado a `services/presupuestacion/extraccion/models.py`: `OrigenCandidato`,
  `CandidatoCliente`, `CandidatoClienteOut` — literal a `design.md` § Interfaces/Resolución de
  cliente.
- [x] 3.5 [GREEN] Agregado a `services/presupuestacion/extraccion/repository.py`:
  `buscar_alias_cliente()` (embebe `clientes(tipo, activo, terceros(...))` en la misma consulta, para
  que nivel 1 arme el `CandidatoCliente` completo en un solo viaje), `upsert_alias_cliente()` (no es un
  UPSERT atómico de una sentencia — PostgREST no expone `CASE` en el `SET`; lee el alias previo con
  `buscar_alias_cliente`, decide `veces_confirmado` en Python — mismo cliente incrementa, distinto o
  inexistente resetea/arranca en 1 — y hace `.upsert(fila, on_conflict="drogueria_id,texto_extraido_normalizado")`,
  mismo patrón que `productos/repository.py:315` y `notificaciones/repository.py:69`),
  `buscar_clientes_por_cuit()` (`terceros` ⋈ `clientes` embed LEFT, mismo precedente de acceso directo
  a tabla ajena que `pcp/imports/repository.py:39-51`).
- [x] 3.6 [GREEN] Agregado a `services/presupuestacion/extraccion/service.py`: `_normalizar_cuit()`,
  `_candidato_desde_alias()` / `_candidatos_desde_cuit()` (mappers privados de los embeds de PostgREST
  a `CandidatoCliente`), `resolver_cliente_candidato()` (3 niveles con cortocircuito real — nivel 2 ni
  se consulta si nivel 1 resuelve, confirmado con `mock.assert_not_called()` en los tests — nunca
  escribe, nunca levanta excepción por "no encontrado"), `obtener_cliente_candidato()` (lee
  `cuit_cliente`/`razon_social_cliente` de la primera fila del CSV propio de la extracción — **nota**:
  esto no estaba en la firma explícita de `design.md`, que solo especifica
  `resolver_cliente_candidato(client, *, drogueria_id, cuit_extraido, texto_extraido)`; el diseño no
  dice de dónde saca esos dos parámetros el endpoint GET, así que se agregó esta función wrapper
  siguiendo el patrón de `leer_filas_extraccion` — Phase 3 no depende de Phase 4, así que lee el CSV
  propio, no `_leer_filas_grupo()`), `_registrar_alias_cliente()` (guard de texto vacío/None antes de
  llamar a `repo.upsert_alias_cliente`, no expuesta en ningún endpoint todavía — la invocará Phase 5
  desde `_materializar_orden_compra()` tras una confirmación exitosa).
- [x] 3.7 [GREEN] Agregado a `services/presupuestacion/extraccion/router.py`:
  `GET /extracciones/{id}/cliente-candidato`, roles `_ROLES_VALIDAR` (existente, sin tupla nueva),
  reusando `_verificar_pertenencia` con `select="id, drogueria_id, csv_disk_path"`.
  `pytest tests/extraccion/test_cliente_candidato.py -m "not integration" -q` → **23 passed** (GREEN
  confirmado tras 3.4-3.7).
- [x] 3.8 [REFACTOR] Corrido `pytest tests/extraccion/test_cliente_candidato.py -m integration -q`
  contra el proyecto Supabase de test (`grnamollopxdlstcpxhc`) → **5 passed**:
  `test_alias_aislado_por_drogueria` (alias de A invisible desde B, crea y borra una segunda
  droguería), `test_resolver_cliente_candidato_nivel1_alias_en_vivo` (alias real + variante
  tipográfica en el texto extraído sigue matcheando por la clave normalizada),
  `test_resolver_cliente_candidato_nivel2_cuit_exclusivo_en_vivo`,
  `test_resolver_cliente_candidato_cuit_compartido_en_vivo` (2 sedes con el mismo CUIT
  `cuit_no_exclusivo=true` → 2 candidatos), `test_upsert_alias_cliente_ciclo_completo_en_vivo` (primera
  confirmación `veces_confirmado=1` → reconfirmación idéntica incrementa a 2 → corrección de cliente
  pisa `cliente_id` y resetea a 1, las 3 aserciones del ciclo del design.md § Tests/Integration en una
  sola fila real, con cleanup en `finally`). Se agregaron 2 fixtures nuevas en
  `tests/extraccion/conftest.py`: `seed_cliente_factory` (alta en dos pasos `terceros`+`clientes`,
  mismo patrón que `tests/conftest.py::seed_proveedor`, con cleanup por cascada desde `terceros`) y
  `seed_alias_cliente_factory` (alta directa de `oc_cliente_alias` para armar el estado inicial exacto
  de cada test). Verificación de no-regresión: `pytest tests/ -q -m "not integration"` → **303 passed,
  436 deselected** (vs. 280 del baseline de PR2 — +23 tests netos, todos de este archivo; 0
  regresiones fuera de Phase 3).

## Phase 4: Validación — Agrupación multi-archivo (D13)

> Depende de Phase 1 (`extraction_results.grupo_id`). No depende de Phase 3.

- [x] 4.1 [RED] Creado `tests/extraccion/test_grupo_extracciones.py`: `_leer_filas_grupo` con
  `grupo_id IS NULL` → forma idéntica a la de un archivo suelto
  (`test_leer_filas_grupo_grupo_id_null_se_comporta_como_archivo_suelto`, con
  `mock_listar_grupo.assert_not_called()` probando que ni siquiera consulta miembros de grupo); 3
  miembros → filas concatenadas en orden `created_at ASC, id ASC`
  (`test_leer_filas_grupo_tres_miembros_concatena_en_orden_de_grupo`), con `_archivo`/
  `_extraction_id` poblados por fila; **aserción explícita de que NO transforma**
  (`test_renglones_repetidos_no_se_suman`, también threat-matrix de 4.4): 3 archivos que declaran el
  mismo conjunto de `numero_renglon` (`1`, `2`) devuelven 6 filas (suma exacta 2+2+2), sin fusionar
  ni sumar cantidades; `editable` se evalúa sobre el total concatenado contra `MAX_FILAS_EDITABLES`
  (500) en `test_leer_filas_grupo_editable_se_evalua_sobre_el_total_concatenado` (3 miembros × 200
  filas = 600 > 500, aunque ningún miembro individual supere el límite). Confirmado RED: `pytest
  tests/extraccion/test_grupo_extracciones.py -q` → 19 failed, todos `AttributeError` por
  `service._leer_filas_grupo`/`repo.listar_miembros_de_grupo`/`service.agrupar_extracciones`
  inexistentes — la falla RED esperada, corrida antes de 4.5-4.7.
- [x] 4.2 [RED] En el mismo archivo, `_conciliar_cabecera`: `numero_oc` distinto entre miembros →
  bloqueo (`test_conciliar_cabecera_numero_oc_distinto_bloquea`, `ValidationError`);
  `razon_social`/`fecha_emision`/`direccion_entrega`/`cantidad_entregas` distintos → advertencia sin
  bloqueo (`test_conciliar_cabecera_otros_campos_distintos_advierten_sin_bloquear`, 3 advertencias
  para 3 campos discrepantes); valor más frecuente gana
  (`test_conciliar_cabecera_valor_mas_frecuente_gana`, 2 de 3 miembros); empate → primer miembro
  (`test_conciliar_cabecera_empate_gana_el_primer_miembro`). Implementación cubre también
  `cuit_cliente` como campo de advertencia (tabla completa de D13.1 § Cabecera inconsistente entre
  archivos, un campo más que el listado literal de esta tarea).
- [x] 4.3 [RED] Las 5 precondiciones de `agrupar_extracciones`, una por test:
  `test_agrupar_requiere_al_menos_2_ids_sin_repetidos`,
  `test_agrupar_extraccion_inexistente_da_404` (`NotFoundError`),
  `test_agrupar_extraccion_de_otra_drogueria_da_403` (`ForbiddenError`),
  `test_agrupar_document_type_distinto_da_422` (`ValidationError`),
  `test_agrupar_mas_de_un_grupo_id_distinto_da_409` (`ConflictError`) — la quinta precondición
  ("ninguna `validado=true`") se comparte con la threat-matrix de 4.4
  (`test_agrupar_validada_rechazado`) para no duplicar el mismo caso con dos nombres. Agregado
  también `test_agrupar_exitoso_genera_grupo_id_nuevo_y_actualiza_ambas` (camino feliz, inspecciona
  los kwargs reales enviados a `repo.actualizar_grupo_id`) y
  `test_desagrupar_deja_grupo_id_null_y_disuelve_el_de_un_solo_miembro_restante` (desagrupar "a" de
  un grupo de 2 dónde queda un solo miembro restante "c" → "c" también se desagrupa) +
  `test_desagrupar_extraccion_validada_rechazado`.
- [x] 4.4 [RED] Threat-matrix de agrupación: agrupar una extracción ya validada → `ConflictError`
  antes del `UPDATE` (`test_agrupar_validada_rechazado`, con `mock_actualizar.assert_not_called()`);
  renglones repetidos entre archivos nunca se fusionan ni suman
  (`test_renglones_repetidos_no_se_suman`, ver 4.1); documento sin número de línea en un grupo de N
  archivos no bloquea ni se rellena (`test_grupo_sin_numero_de_renglon_se_materializa`, celda vacía
  en las 2 filas de salida); un miembro del grupo sin CSV en disco levanta
  `ExtraccionNoDisponibleError` en la primera lectura que falle (`test_miembro_sin_csv_aborta`, con
  la función real `_leer_filas_csv_con_columnas` sin mockear, sobre un `csv_disk_path` genuinamente
  inexistente en `tmp_path`). En `tests/extraccion/test_router.py`, agregado
  `test_agrupar_multi_tenant_rechazado`: `_verificar_pertenencia` stubeada (exenta para `superadmin`,
  ya cubierta por los tests existentes de GET .../filas) para ids de dos droguerías distintas →
  `service.agrupar_extracciones` rechaza con `ValidationError` (no `ForbiddenError`: no hay
  "droguería del usuario" contra la cual comparar cuando quien agrupa es `superadmin` — el rechazo es
  porque los N miembros deben compartir `drogueria_id` entre sí). Confirmado RED:
  `pytest tests/extraccion/test_router.py -k "not integration" -q` → `ImportError:
  AgruparExtraccionesRequest` (falla de colección, la falla RED esperada, corrida antes de 4.5).
- [x] 4.5 [GREEN] Agregado a `services/presupuestacion/extraccion/models.py`: `MiembroGrupo`,
  `AgruparExtraccionesRequest` (`extraction_ids: list[str] = Field(min_length=2)`, reusado también
  para `POST /extracciones/desagrupar` — mismo shape, no se justifica un modelo separado para la
  inversa); extendida `FilasExtraccionOut` con `grupo_id: str | None = None`,
  `miembros: list[MiembroGrupo] = []`, `advertencias_cabecera: list[str] = []` (sin
  `modo_fusion_sugerido` — D13.1 lo elimina; estos 3 campos quedan sin wiring en el endpoint GET
  .../filas hasta Phase 5, que extiende `_TIPOS_CON_LECTURA_DE_FILAS` con `orden_compra`).
- [x] 4.6 [GREEN] Agregado a `services/presupuestacion/extraccion/repository.py`:
  `listar_miembros_de_grupo()` (orden `created_at ASC, id ASC`), `actualizar_grupo_id()`,
  `marcar_validadas()` (bulk sobre el grupo vía `.in_("id", extraction_ids)`, para uso de Phase 5
  desde `_materializar_orden_compra()`).
- [x] 4.7 [GREEN] Agregado a `services/presupuestacion/extraccion/service.py`: `_leer_filas_grupo()`
  (concatena tal cual, sin dedup/fusión/renumeración — D13.1; `grupo_id IS NULL` trata a la propia
  extracción como grupo de un solo miembro, sin consultar `listar_miembros_de_grupo`),
  `_conciliar_cabecera()` (con `_valor_mas_frecuente()` como helper puro), `agrupar_extracciones()` /
  `desagrupar_extracciones()` con las 5 precondiciones validadas **antes** del `UPDATE`, más
  `agrupar_extracciones_para_endpoint()` / `desagrupar_extracciones_para_endpoint()` (mismo patrón
  `*_para_endpoint` que `validar_extraccion_para_endpoint`, corren con `get_service_client()`).
  **Confirmado: no se creó `_fusionar_filas()`** — `grep -n "_fusionar_filas"
  services/presupuestacion/extraccion/service.py` no devuelve nada. `pytest
  tests/extraccion/test_grupo_extracciones.py -q` → **19 passed** (GREEN confirmado tras 4.5-4.7).
- [x] 4.8 [GREEN] Agregado a `services/presupuestacion/extraccion/router.py`: `POST
  /extracciones/agrupar` (devuelve `{"grupo_id": str}`), `POST /extracciones/desagrupar`
  (`status_code=204`), roles `_ROLES_VALIDAR` (sin tupla nueva), `_verificar_pertenencia` aplicado
  **por cada id** de la lista con el user client antes de tocar nada con el service client — mismo
  patrón `*_para_endpoint` ya establecido por `validar_extraccion_endpoint`. `pytest
  tests/extraccion/test_router.py -k "not integration" -q` → **1 passed** (GREEN confirmado:
  `test_agrupar_multi_tenant_rechazado`).
- [x] 4.9 [REFACTOR] Agregadas 2 pruebas de integración a `test_grupo_extracciones.py`
  (`test_leer_filas_grupo_en_vivo_concatena_los_miembros_del_grupo`,
  `test_agrupar_y_desagrupar_extracciones_en_vivo`, con fixtures CSV reales de OC vía
  `seed_extraction_result_factory("orden_compra", ...)`) y 1 a `test_router.py`
  (`test_agrupar_extracciones_endpoint_en_vivo`, ejercitando el endpoint completo agrupar→desagrupar)
  — mismo patrón de `seed_extraction_result_factory`/teardown de Phase 3, sin fixtures nuevas
  (`grupo_id` es un override directo que el fixture ya soporta vía `**overrides`). Corrido contra el
  proyecto Supabase de test (`grnamollopxdlstcpxhc`): `pytest
  tests/extraccion/test_grupo_extracciones.py -m integration -q` → **2 passed**; `pytest
  tests/extraccion/test_router.py -k agrupar -q` → **2 passed** (el filtro `-k agrupar` matchea
  también `test_agrupar_multi_tenant_rechazado`, ya que "desagrupar" contiene "agrupar" como
  substring). Verificación de no-regresión: `pytest tests/ -q -m "not integration"` → **323 passed,
  442 deselected** (vs. 303 del baseline de PR3 — +20 tests netos: 19 de
  `test_grupo_extracciones.py` + 1 de `test_router.py`; 0 regresiones fuera de Phase 4). Refactor
  evaluado: el código quedó sin necesidad de extracción adicional (`_valor_mas_frecuente` ya nace
  como helper puro separado); no se aplicaron cambios de REFACTOR más allá de correr la suite de
  integración.

## Phase 5: Validación — Materialización (D1, D7, D8, D13.1)

> Depende de Phase 1, 3 (necesita `resolver_cliente_candidato`/`_registrar_alias_cliente` ya
> definidas, aunque el endpoint de confirmación es nuevo acá) y 4 (necesita `_leer_filas_grupo` para
> el caso multi-archivo). Es la fase más grande — considerar partirla en dos PRs si el diff real
> supera el estimado.

- [x] 5.1 [RED→GREEN] Creado `tests/extraccion/test_orden_compra.py` con tabla de casos de
  `repartir_cantidad` (D8) parametrizada: `(100,3)`, `(100,1)`, `(7,2)`, `(0,3)` enteros +
  `(10.5,4)` decimal + property test parametrizado (6 cantidades × 6 conteos de entregas = 36
  combinaciones) que confirma `sum(resultado) == cantidad` siempre. **Desviación del prompt de esta
  fase, documentada en el propio test**: el prompt listaba `(100,3) -> [34,34,32]`, que **no**
  satisface el algoritmo literal de `design.md` § D8 ("las primeras `resto` entregas reciben
  base+1, las restantes base" → `100 // 3 = 33`, resto `1` → `[34,33,33]`, no `[34,34,32]`). Se
  siguió `design.md` (autoritativo, con alternativas consideradas y rationale explícito) en vez del
  ejemplo del prompt — el resto de los casos (`(7,2)->[4,3]`, `(100,1)->[100]`, `(0,3)->[0,0,0]`) sí
  coinciden entre prompt y diseño, confirmando que el algoritmo implementado es el correcto y el
  ejemplo del prompt tenía un error puntual. Confirmado RED antes de 5.8: `ModuleNotFoundError`/
  `AttributeError: module 'service' has no attribute 'repartir_cantidad'` (función inexistente).
- [x] 5.2 [RED→GREEN] En el mismo archivo, `_validar_orden_compra_override`: suma de `entregas` por
  línea ≠ `cantidad` del renglón (`test_suma_de_entregas_por_linea_distinta_de_cantidad_levanta_error`);
  `entregas: []` confirmado que viola `min_length=1` **a nivel de pydantic**, antes de llegar a la
  función (`test_entregas_vacia_viola_min_length_del_modelo`, `pytest.raises(PydanticValidationError)`);
  lista no vacía sin desglose válido (`test_entregas_no_vacia_sin_desglose_valido_no_coincide_con_cantidad`);
  `precio_unitario` vacío (`test_precio_vacio_bloquea_confirmacion`, nombre exacto pedido) y no numérico
  (`test_precio_unitario_no_numerico_levanta_error`); clave de `cantidades_por_posicion` fuera de
  rango (`test_clave_de_cantidades_por_posicion_fuera_de_rango`); acumulación de múltiples errores en
  un solo `ValidationError` (`test_validar_override_acumula_errores_de_multiples_problemas_en_un_solo_422`,
  mismo patrón que el test existente de licitación/comparativa); `cliente_id` inexistente
  (`test_cliente_id_inexistente_levanta_error_antes_del_primer_write`, con
  `mock_buscar.assert_called_once()`) y de otra droguería (`test_cliente_id_de_otra_drogueria_levanta_error`).
  **Confirmado explícitamente que no existe el caso "`numero_renglon` duplicado"**
  (`test_no_existe_validacion_de_numero_renglon_duplicado`, inspecciona el código fuente de la
  función vía `inspect.getsource` y confirma que no menciona `numero_renglon`). Confirmado RED antes
  de 5.8: `AttributeError` por `service._validar_orden_compra_override`/`repo.buscar_cliente_por_id`
  inexistentes.
- [x] 5.3 [RED→GREEN] Tests unitarios de la asignación de `numero_renglon` sobre
  `_materializar_orden_compra` (D13.1), con todos los writes mockeados
  (`_preparar_mocks_materializacion`, inspecciona `filas_items` reales enviadas a
  `repo.insertar_oc_items`): `numero_renglon_documento` `"7","3",None` → `oc_items.numero_renglon`
  `1,2,3` (`test_numero_renglon_se_asigna_por_posicion_no_del_documento`); dos filas con el mismo
  `numero_renglon_documento` → `1,2` sin conflicto
  (`test_filas_con_mismo_numero_renglon_documento_no_generan_conflicto`); todas sin número de
  documento → `1..N` igual (`test_todas_las_filas_sin_numero_documento_asignan_1_a_n_igual`).
  Test de no-regresión (D13.2): `_materializar_licitacion` sigue con
  `int(fila["item"].strip())` sin fallback, verificado por inspección de código fuente
  (`test_materializar_licitacion_sigue_leyendo_item_sin_fallback_no_regresion`) — función no tocada,
  confirmado también por la suite completa de licitación/comparativa en verde (ver 5.13).
- [x] 5.4 [RED→GREEN] Invertido en `tests/extraccion/test_service.py`
  `test_validar_orden_compra_no_implementado` (integración, **live**) a
  `test_validar_orden_compra_materializa_oc_items_y_entregas`: dado `seed_cliente_factory` +
  `seed_extraction_result_factory("orden_compra", ...)`, `validar_extraccion(...,
  orden_compra=OrdenCompraOverride(...))` crea filas reales en `ordenes_compra`/`oc_items`/
  `entregas_oc`/`entregas_oc_items`, con `estado='emitida'`, `proceso_comercial_id IS NULL`,
  `extraction_id`/`cantidad_entregas` poblados, `oc_items.numero_renglon` en `[1,2]`,
  `entregas_oc.estado='pendiente'`, suma de `cantidad_planificada` = 10+20 = 30 (reparto automático
  de 1 entrega), `cantidad_entregada`/`cantidad_rechazada` en 0. **Invariante duro "confirmar no
  descuenta stock"**: `stock.entregar_stock_producto` mockeado vía `monkeypatch` y
  `mock_entregar_stock.assert_not_called()` explícito tras la confirmación real contra la DB de
  test. `extraction_results.validado` queda `true` con `validado_por` poblado. Confirmado RED antes
  de 5.7-5.12: el test original (`pytest.raises(ValidationError)`) invertido ya no aplica una vez
  agregados los modelos — corrida antes de la implementación, falló con
  `AttributeError`/`ImportError` por `OrdenCompraOverride` inexistente.
- [x] 5.5 [RED→GREEN] Test de confirmación de grupo (live, depende de Phase 4):
  `test_validar_orden_compra_agrupada_materializa_una_sola_oc_y_valida_todo_el_grupo` — 2 archivos
  con el mismo `grupo_id`, confirmar desde el ancla produce **una sola** fila en `ordenes_compra`
  (`extraction_id = ancla`), y **ambos** miembros quedan `validado=true` con idéntico
  `validado_por`/`validado_at` (aserción de igualdad exacta de `validado_at` entre ambas filas).
  `test_validar_orden_compra_agrupada_con_miembro_ya_validado_da_conflict_sin_escribir`: un miembro
  ya `validado=true` en el grupo → `ConflictError` **antes de escribir nada** (aserción: 0 filas en
  `ordenes_compra` con ese `extraction_id` tras la excepción).
- [x] 5.6 [RED→GREEN] Test de unicidad (D5) end-to-end vía `validar_extraccion` (live):
  `test_validar_orden_compra_mismo_numero_oc_clientes_distintos_ambas_confirman` — mismo `numero_oc`
  contra 2 clientes distintos de la misma droguería → ambas confirmaciones OK (`uq_oc_por_cliente`
  scoped por `cliente_id`). `test_validar_orden_compra_mismo_numero_oc_mismo_cliente_da_conflict` —
  mismo `numero_oc` + mismo cliente → segunda confirmación levanta `ConflictError` (capturado el
  `APIError` `23505` de PostgREST y traducido en `_materializar_orden_compra`).
- [x] 5.7 [GREEN] Agregado a `services/presupuestacion/extraccion/models.py`: `FilaOrdenCompraIn`,
  `EntregaPlanIn`, `OrdenCompraOverride` (`entregas: list[EntregaPlanIn] = Field(min_length=1)`) —
  **sin** `modo_fusion` ni `ModoFusion`, literal a `design.md` § Interfaces. `ValidarExtraccionRequest.
  orden_compra: OrdenCompraOverride | None = None`. `ResultadoValidarExtraccion.proceso_comercial_id`
  pasa de `str` a `str | None`; agregados `orden_compra_id`, `entregas_creadas`,
  `renglones_sin_producto`, `extracciones_validadas`.
- [x] 5.8 [GREEN] Agregado a `services/presupuestacion/extraccion/service.py`: `repartir_cantidad()`
  (D8, usando `Decimal`/`ROUND_DOWN`, sin punto flotante), `_validar_orden_compra_override()` (lee
  `repo.buscar_cliente_por_id` para el chequeo de cliente; acumula todos los errores de
  precio/desglose/cliente en un único `ValidationError`). **Nota de alcance sobre "coherencia de
  `numero_oc` entre miembros del grupo"**: esa validación específica se implementó reusando
  `_conciliar_cabecera()` (Phase 4, ya la implementa y ya la testea) desde
  `_validar_y_materializar_orden_compra()` en vez de duplicarla dentro de
  `_validar_orden_compra_override()` — sigue corriendo antes del primer write, sigue siendo un solo
  `ValidationError` bloqueante, pero vive en la función que ya tiene esa responsabilidad (DRY, D13.1
  ya la diseña como la dueña de la reconciliación de cabecera).
- [x] 5.9 [GREEN] Agregado a `services/presupuestacion/extraccion/service.py`:
  `_materializar_orden_compra()` — asigna `numero_renglon = 1..N` por posición, inserta
  `ordenes_compra`/`oc_items`/`entregas_oc`(`estado='pendiente'`)/`entregas_oc_items`
  (`cantidad_planificada` desde `repartir_cantidad()` en modo automático o
  `cantidades_por_posicion` en modo manual, `cantidad_entregada=0`, `cantidad_rechazada=0`);
  `fecha_entrega_planificada` calculada desde `fecha_emision + plazo_dias` (D6, no explícito en el
  prompt pero literal del diseño); captura `APIError` `23505` de `uq_oc_por_cliente`/
  `uq_oc_por_proceso` y la traduce a `ConflictError` (mismo patrón que `compras/service.py::
  crear_orden_compra`). `_validar_y_materializar_orden_compra()` (nueva, orquesta el flujo completo)
  usa `marcar_validadas()` incondicionalmente (1 o N miembros — simplifica sin cambiar de
  comportamiento, ya que `.in_("id", [...])` funciona igual con una lista de 1), registra
  `registrar_evento_ciclo_vida` + `registrar_cambio` de `estado` `None -> 'emitida'` (D4), e invoca
  `_registrar_alias_cliente()` (Phase 3) solo si `_materializar_orden_compra` no lanzó excepción
  (estructural: el código después de la llamada solo se alcanza si tuvo éxito).
- [x] 5.10 [GREEN] Extendido `_TIPOS_CON_LECTURA_DE_FILAS` (línea real 44, no 39 — el prompt pedía
  verificar la línea real) con `"orden_compra"`, comentario corregido. Agregada la rama
  `orden_compra` en `validar_extraccion()`, **al principio** de la función (antes de
  `_validar_filas_override`/`_resolver_proceso_comercial_id`, no en el bloque `if/elif` de líneas
  442-463 que el prompt señalaba como referencia — la ubicación real difiere porque D4 exige
  **saltear por completo** `_resolver_proceso_comercial_id`, no solo la materialización): delega en
  `_validar_y_materializar_orden_compra()`, que usa `_leer_filas_grupo()` (D13, funciona igual con 1
  o N miembros), corre `_conciliar_cabecera()` (numero_oc bloqueante) +
  `_validar_orden_compra_override()` + `_materializar_orden_compra()`. Confirmado con `grep`:
  `_materializar_licitacion` no fue tocada (mismo cuerpo, mismo `int(fila["item"].strip())`).
  **Extensión no listada explícitamente en el prompt de esta fase, pero requerida por design.md §
  Data Flow y por la nota de Phase 4 ("estos 3 campos quedan sin wiring... hasta Phase 5")**:
  `leer_filas_extraccion()` (el `GET /extracciones/{id}/filas` existente) ahora usa
  `_leer_filas_grupo()` para `orden_compra` en vez de leer un solo CSV, poblando `grupo_id`/
  `miembros`/`advertencias_cabecera` de verdad. `numero_oc` discrepante **advierte, no bloquea** en
  este GET (a diferencia de la confirmación) — nuevo helper `_advertencias_cabecera_para_lectura()`
  que reusa `_conciliar_cabecera()` pero degrada su `ValidationError` a advertencia, sin duplicar la
  lógica de conciliación. Requirió agregar `client: Client | None = None` a la firma de
  `leer_filas_extraccion()` (retrocompatible: default `None`, solo se usa en la rama `orden_compra`)
  y pasar `user_client` desde el router. Test unitario agregado:
  `test_leer_filas_extraccion_orden_compra_agrupada_no_bloquea_por_numero_oc_discrepante`.
- [x] 5.11 [GREEN] Agregado a `services/presupuestacion/extraccion/repository.py`:
  `buscar_cliente_por_id()`, `crear_orden_compra()`, `insertar_oc_items()`, `crear_entrega_oc()`,
  `insertar_entregas_oc_items()` — escritura directa a las 4 tablas de `compras/`, sin importar
  `compras/repository.py` (frontera de módulos de `design.md`, mismo precedente que
  `pcp/imports/repository.py`).
- [x] 5.12 [GREEN] Agregado en `services/presupuestacion/extraccion/router.py`: `body.orden_compra`
  pasado tal cual (el modelo pydantic, no un dict) a `validar_extraccion_para_endpoint` en
  `POST /extracciones/{id}/validar` — mismo endpoint existente, sin roles nuevos.
- [x] 5.13 [REFACTOR] `pytest tests/extraccion -m integration -q` completo corrido contra el
  proyecto Supabase de test (`grnamollopxdlstcpxhc`) → **36 passed, 0 regresiones** en
  licitación/comparativa/cliente-candidato/agrupación (incluye los 5 tests nuevos de este batch en
  `test_service.py`, más el resto de la suite de integración de Phases 1-4 en verde). Las filas de `oc_cliente_alias`/
  `ordenes_compra`/`oc_items`/`entregas_oc`/`entregas_oc_items` creadas por los tests de esta fase
  **no se limpiaban correctamente al principio** — se encontró y arregló en el mismo batch (ver
  "Issues Found"): `entregas_oc_items.oc_item_id` (`fk_eoci_oci`) no tiene `ON DELETE CASCADE`, así
  que un `DELETE` directo sobre `ordenes_compra` revienta con violación de FK cuando Postgres intenta
  la cascada a `oc_items` antes de que la cascada paralela vía `entregas_oc` haya limpiado
  `entregas_oc_items`. Se agregó `_borrar_orden_compra_en_cascada()` a
  `tests/extraccion/conftest.py` (mismo orden manual que el helper ya existente
  `tests/compras/conftest.py::limpiar_ordenes_compra`: `entregas_oc_items` → `entregas_oc` →
  `historial_cambios` → `oc_items` → `ordenes_compra`), invocado desde el teardown de
  `seed_extraction_result_factory` (por `extraction_id`) y `seed_cliente_factory` (por `cliente_id`,
  redundante a propósito porque el orden de teardown entre esas 2 fixtures no está garantizado). La
  corrida que expuso el bug dejó 5 filas de `ordenes_compra` huérfanas (con su cascada de
  `oc_items`/`entregas_oc`/`entregas_oc_items`) más sus `terceros`/`clientes`/`droguerias`/
  `extraction_results`/`oc_cliente_alias` asociados (el teardown abortaba a mitad de camino, así que
  ninguna fixture dependiente llegaba a borrarse) — limpiadas a mano contra `grnamollopxdlstcpxhc`
  con el mismo orden de `_borrar_orden_compra_en_cascada`, verificado con `select` antes/después.
  **Confirmado con una segunda corrida completa** (5 tests, mismos `numero_oc` reusados) que ya no
  quedan filas huérfanas: `select ... in_("numero_oc", [...])` devuelve `[]` después del run.

## Phase 6: Frontend — Resolución de cliente (D3/D3.2)

> Depende de Phase 3 (endpoint `GET /extracciones/{id}/cliente-candidato`).

- [x] 6.1 [RED] Creado `frontend/src/features/validar-extraccion/components/ClienteBuscador.test.tsx`
  (convención del proyecto: archivo de test junto al componente, mismo patrón que
  `GestionTerceros.test.tsx`/`ValidarExtraccionDetalle.test.tsx` — `vitest` + `@testing-library/react`
  + `vi.mock` del módulo de API + `QueryClientProvider` de test): `q` de 1 carácter no dispara ningún
  request ni siquiera tras avanzar el debounce (`vi.useFakeTimers` + `advanceTimersByTimeAsync(300)`);
  arranca vacío — sin tipear nada, ningún request al montar; el debounce de 300ms coalesce 4
  pulsaciones (`h`→`ho`→`hos`→`hospital`) en **un solo** request con el valor final
  (`toHaveBeenCalledTimes(1)` + `toHaveBeenCalledWith(objectContaining({q:'hospital'}))` — aserción
  real, sin debounce el mock se habría llamado 4 veces); la llamada lleva `rol: 'todos'` (nunca
  `'clientes'` — test explícito de C7-iii) y filtra en el cliente por `tiene_rol_cliente` (mock
  devuelve un tercero cliente + uno solo-proveedor, se afirma que solo el primero se renderiza).
  Confirmado RED: `corepack pnpm test -- ClienteBuscador OrdenCompraSelector` (vía `frontend/` directo,
  ver nota de tooling en 6.6) → `Failed to resolve import "./ClienteBuscador"` — el componente no
  existe todavía, la falla RED esperada, corrida antes de 6.4.
- [x] 6.2 [RED] Creado
  `frontend/src/features/validar-extraccion/components/OrdenCompraSelector.test.tsx`, con
  `./ClienteBuscador` mockeado para aislar el componente bajo test (patrón de aislamiento de
  subcomponente, no usado antes en este proyecto para features propias pero sí implícito en cómo
  `vi.mock` aísla módulos de API — aplicado acá porque `OrdenCompraSelector` compone `ClienteBuscador`
  como pieza ya testeada por separado en 6.1). **Arnés del invariante humano**
  (`ArnesConBotonConfirmarOC`): envuelve `OrdenCompraSelector` con un botón local "Confirmar OC"
  deshabilitado hasta que el callback `onClienteConfirmado` dispare — reproduce sin necesitar Phase 8
  el contrato real que design.md § D3/D3.2 le exige al selector. Sugerencia de alias se muestra
  preseleccionada (texto visible) pero "Confirmar OC" sigue deshabilitado hasta el click explícito de
  "Confirmar cliente"; tras el click, se habilita (aserción real: el callback debe ejecutarse de
  verdad para que el arnés cambie de estado). "No es este" abre el buscador manual (`ClienteBuscador`
  mockeado, antes ausente de pantalla). N=2 candidatos de CUIT compartido → 2 radio buttons, ninguno
  preseleccionado (`not.toBeChecked()` en cada uno) y "Confirmar OC" sigue deshabilitado. Sin
  sugerencia (`origen: 'ninguno'`) cae directo al buscador sin pasar por "No es este" (ese botón ni
  siquiera se renderiza en ese caso). Confirmado RED: mismo comando que 6.1 →
  `Failed to resolve import "./OrdenCompraSelector"`, corrida antes de 6.5.
- [x] 6.3 [GREEN] Agregado a `frontend/src/lib/api/extracciones.ts`: tipos `OrigenCandidato`
  (`'alias' | 'cuit' | 'cuit_compartido' | 'ninguno'`), `CandidatoCliente`, `CandidatoClienteOut` —
  espejo literal de los modelos Pydantic reales de `services/presupuestacion/extraccion/models.py`
  (leídos antes de escribir, no asumidos desde design.md); función
  `obtenerClienteCandidato(extractionId)` sobre `GET /extracciones/{id}/cliente-candidato` (router.py
  real, Phase 3), mismo patrón `presupuestacionFetch` que el resto del archivo.
- [x] 6.4 [GREEN] Creado `frontend/src/features/validar-extraccion/components/ClienteBuscador.tsx`:
  estado `texto`/`textoDebounced` + `useEffect`/`setTimeout` de 300ms — **mismo patrón exacto** ya en
  producción en `GestionTerceros.tsx` (`DEBOUNCE_BUSQUEDA_MS = 300`), no un mecanismo nuevo; búsqueda
  vía `listarTerceros({ q: textoDebounced, rol: 'todos', pageSize: 20 })` habilitada solo con
  `textoDebounced.length >= 2`; filtrado en cliente por `tercero.tiene_rol_cliente === true` (C7-iii);
  cada resultado muestra `razon_social` + `cuit` + `codigo_interno`. `pytest` no aplica (frontend);
  `corepack pnpm test -- ClienteBuscador` → **4 passed** (GREEN confirmado tras 6.4).
- [x] 6.5 [GREEN] Creado `frontend/src/features/validar-extraccion/components/OrdenCompraSelector.tsx`:
  `useQuery(obtenerClienteCandidato(extractionId))`; rama por `origen` — `'ninguno'` o
  `mostrarBuscador===true` (tras "No es este") → `<ClienteBuscador>`; `'cuit_compartido'` → lista de
  radio buttons (`useState<string|null>` sin valor inicial, así que ninguno nace marcado) + botón
  "Confirmar cliente" deshabilitado hasta que haya un radio elegido; `'alias'`/`'cuit'` (1 candidato)
  → tarjeta de sugerencia con botones "Confirmar cliente" / "No es este". El callback
  `onClienteConfirmado(clienteId, razonSocialExtraida)` solo se invoca desde los 3 handlers de click
  explícito (nunca automáticamente al recibir la respuesta del query) — es el contrato que Phase 8
  usará para habilitar su propio "Confirmar OC" real, ya probado con el arnés de 6.2. Sin input de
  código en ningún branch (C5). `corepack pnpm test -- OrdenCompraSelector` → **4 passed** (GREEN
  confirmado tras 6.5).
- [x] 6.6 [REFACTOR] **Nota de tooling descubierta en este batch**: el repo no tiene `package.json` en
  la raíz ni `pnpm-workspace.yaml` (`ExtraccionDatosNE/` no es un workspace pnpm) — `pnpm --filter
  frontend test` del prompt de esta fase falla con `ERR_PNPM_NO_PKG_MANIFEST` porque no hay manifiesto
  que resolver ese filtro. El comando real que corre la suite de `frontend/` es `pnpm test` (o
  `vitest run`) ejecutado **dentro** de `frontend/`, confirmado leyendo `frontend/package.json`
  (`"test": "vitest run"`). Además `pnpm` no estaba en el `PATH` de la shell de este batch; se usó
  `corepack pnpm` (ya presente vía Corepack), que resuelve la misma versión fijada por el proyecto sin
  instalar nada global. `cd frontend && corepack pnpm test -- OrdenCompraSelector ClienteBuscador` →
  **8 passed** (4+4, GREEN confirmado, sin necesidad de refactor — el código de 6.4/6.5 quedó limpio
  en la primera pasada: sin duplicación entre los 3 branches de render, sin mocks de más en los tests
  — máximo 2 mocks por archivo, `listarTerceros`/`obtenerClienteCandidato` respectivamente, más
  `./ClienteBuscador` en el selector). Verificación de no-regresión: `corepack pnpm test` (suite
  completa de `frontend/`) → **148 passed** (140 preexistentes + 8 nuevos, 0 regresiones).
  `corepack pnpm build` (`tsc -b && vite build`) → **sin errores de tipo**, build completo en 909ms.
  **Prueba manual contra el backend real de Phase 3, no alcanzada**: este batch de `sdd-apply` corre
  sin navegador ni sesión interactiva (no hay forma de abrir `pnpm --filter frontend dev` y clickear a
  través de la UI desde este entorno) — el propio prompt de esta fase contempla explícitamente esta
  posibilidad ("notar si este paso manual no es prácticamente alcanzable... y conformarse con la suite
  automatizada sola"). Queda pendiente como verificación manual humana antes de mergear PR6, o como
  parte del flujo end-to-end manual explícito de la tarea 8.7 (que si cubre el mismo camino con los 3
  componentes ya cableados en `ValidarExtraccionDetalle`).

## Phase 7: Frontend — Cabecera de grupo, entregas y carga múltiple (D13, D13.1, D8)

> Depende de Phase 4 (agrupar/desagrupar) para `ValidarExtraccionListado`, y de Phase 2 (`grupo_id`
> en `/procesar`) para `FormCard`. No depende de Phase 6.

- [x] 7.1 [RED] Creado
  `frontend/src/features/validar-extraccion/components/CabeceraOrdenCompra.test.tsx` (4 tests, mismo
  patrón de arnés que `OrdenCompraSelector.test.tsx`: un botón local "Confirmar OC" deshabilitado
  según el `bloqueado` que reporta el componente vía `onCambio`): `numero_oc` en desacuerdo entre 2
  miembros → input con clase `border-red-500` y "Confirmar OC" deshabilitado; editar el campo a un
  valor distinto (`'9999'`, deliberadamente NO igual al valor ya precargado por empate — ver nota de
  diseño en 7.5) lo habilita; desacuerdo en `razon_social_cliente`/`fecha_emision`/`direccion_entrega`
  muestra un aviso (`getByText(/desacuerdo entre archivos del grupo/i)` con las 3 etiquetas dentro del
  mismo nodo, via `toHaveTextContent`) sin deshabilitar "Confirmar OC"; sin desacuerdo → sin aviso y
  habilitado de entrada. Confirmado RED: `corepack pnpm test -- CabeceraOrdenCompra` (desde
  `frontend/`) → `Failed to resolve import "./CabeceraOrdenCompra"` (el componente no existía
  todavía), corrida antes de 7.5.
- [x] 7.2 [RED] Creado
  `frontend/src/features/validar-extraccion/components/EntregasEditor.test.tsx` (3 tests, mismo
  patrón de arnés): con 1 renglón (`cantidad: '100'`) y desglose manual activado, `40+40` en 2
  entregas produce el mensaje **literal** `'renglón 1: la suma de las entregas (80) no coincide con
  la cantidad del renglón (100)'` — copiado carácter a carácter del f-string real de
  `_validar_orden_compra_override` (`services/presupuestacion/extraccion/service.py:677-680`, leído
  antes de escribir el test) — y deshabilita "Confirmar entregas"; sin desglose manual (solo cantidad
  de entregas = 3), el bloque `data-testid="reparto-automatico"` muestra `'34 / 33 / 33'` (reparto
  parejo con resto al frente, D8) y el botón queda habilitado; con desglose manual correcto (`60+40`)
  también queda habilitado. Confirmado RED: `corepack pnpm test -- EntregasEditor` →
  `Failed to resolve import "./EntregasEditor"`, corrida antes de 7.6.
- [x] 7.3 [RED] Creado `frontend/src/features/carga-documentos/components/FormCard.test.tsx` (4
  tests; no existía ningún test de este componente antes de este batch): con `tipo='ordenes'` (tras
  clickear la pestaña) el `<input type="file">` real del DOM tiene `.multiple === true`; con
  `tipo='licitaciones'` (default) `.multiple === false`; con 3 archivos, `procesarDocumento` se llama
  3 veces **en secuencia real** (aserción fuerte: un array `orden` que registra
  `start:<archivo>`/`end:<archivo>` con un `await Promise.resolve()` entre medio, confirmando
  `['start:a.pdf','end:a.pdf','start:b.pdf','end:b.pdf','start:c.pdf','end:c.pdf']` — si fuera en
  paralelo los 3 `start` aparecerían antes que cualquier `end`) y los 3 llevan el **mismo**
  `grupoId` (`crypto.randomUUID()` mockeado con `vi.spyOn`); un archivo que rechaza con un error que
  incluye "409" no aborta el tercero — los 3 `procesarDocumento` se invocan igual y el resultado por
  archivo se ve reflejado en la lista de resultados (`a.pdf`/`c.pdf` con "procesado correctamente",
  `duplicado.pdf` con el mensaje de error conteniendo "409"). Confirmado RED:
  `corepack pnpm test -- FormCard` → los 4 tests fallan porque `TIPO_OPTIONS` marcaba `ordenes` como
  `disabled` (el botón de tab quedaba deshabilitado, sin poder clickearlo) y el input no tenía
  `multiple` condicional ni `grupoId`/secuenciación — corrida antes de 7.8.
- [x] 7.4 [RED] Creado
  `frontend/src/features/validar-extraccion/ValidarExtraccionListado.test.tsx` (6 tests): 3 unitarios
  sobre un guard puro exportado `puedeAgruparSeleccion()` (deshabilitado con <2 filas, deshabilitado
  con tipos mixtos, habilitado con 2+ `orden_compra`) + 3 de integración con la tabla real: "Agrupar
  seleccionadas" arranca deshabilitado y se habilita al tildar 2 checkboxes `orden_compra`; las filas
  `licitacion` no tienen checkbox (`queryByLabelText` ausente — refuerza que "tipos mixtos" es
  defensivo, la UI ya no lo permite); tras agrupar (mock de `agruparExtracciones`), ambas filas
  muestran el texto "Grupo" y "Desagrupar" quedaba deshabilitado hasta reseleccionar esas mismas 2
  filas, momento en que se habilita, se ejecuta y el indicador desaparece. **Nota de diseño
  encontrada en este batch, documentada acá y en 7.9/7.10**: `GET /extracciones` (`ExtraccionResumen`,
  Phase 1-3) no expone `grupo_id` — ni en el modelo pydantic ni en el `select` de
  `repository.py::listar_extracciones` (verificado leyendo el código real, no asumido) — así que el
  indicador de grupo y la habilitación de "Desagrupar" se resuelven con estado en memoria
  (`gruposLocales`, poblado por las propias respuestas de `agruparExtracciones`/
  `desagruparExtracciones` de esta sesión), no con un dato persistido que hoy el endpoint no
  devuelve; extender el backend está fuera del alcance frontend-only de esta fase. Confirmado RED:
  `corepack pnpm test -- ValidarExtraccionListado` → `Failed to resolve import` para
  `puedeAgruparSeleccion`/`agruparExtracciones`/`desagruparExtracciones` (nada de esto existía
  todavía), corrida antes de 7.9-7.11.
- [x] 7.5 [GREEN] Creado
  `frontend/src/features/validar-extraccion/components/CabeceraOrdenCompra.tsx`: cabecera editable
  (`numero_oc`, `fecha_emision`, `direccion_entrega` — los 3 campos que integran `OrdenCompraOverride`)
  precargada con `valorMasFrecuente()` (espejo de `_valor_mas_frecuente`: empate → primer miembro) a
  partir de `representativasPorMiembro()` (espejo de `_filas_representativas_por_miembro`: primera
  fila por `_extraction_id`); bloqueo **solo** por `numero_oc` (`hayDesacuerdoNumeroOc &&
  !numeroOcEditado` — cualquier edición explícita del campo resuelve el bloqueo, sin importar el
  valor final, que es justo el comportamiento pedido "editarlo a un valor único lo habilita"); aviso
  no bloqueante para el resto de `_CAMPOS_CABECERA_ADVERTENCIA` real del backend
  (`razon_social_cliente`, `cuit_cliente`, `fecha_emision`, `direccion_entrega`,
  `cantidad_entregas` — leídos de `service.py:408-414` antes de escribir el componente, un campo más
  que el listado literal de la tarea 7.1). Reporta `(cabecera, bloqueado)` vía `onCambio` en cada
  cambio (mismo contrato callback-driven que `OrdenCompraSelector::onClienteConfirmado`), para que
  Phase 8 lo cablee al "Confirmar OC" real sin reescribir este componente.
- [x] 7.6 [GREEN] Creado
  `frontend/src/features/validar-extraccion/components/EntregasEditor.tsx`: input de cantidad de
  entregas (redimensiona arrays de plazos/desgloses), checkbox "Desglosar cantidad por línea
  manualmente" (desactivado por default → reparto automático), `repartirCantidad()` en TypeScript
  como **espejo literal** de `repartir_cantidad` (D8, `service.py:585-604`: entero → primeras `resto`
  entregas `base+1`, resto `base`; decimal → primeras N-1 truncadas a centésimos, la última se lleva
  el resto) usado para la vista previa `data-testid="reparto-automatico"`; con desglose manual,
  inputs por `entrega × renglón` (`aria-label="entrega N renglón P"`) y validación en vivo que arma
  el mensaje de error **carácter a carácter igual** al f-string real de
  `_validar_orden_compra_override` (`service.py:677-680`) por cada renglón cuya suma no coincide.
  Reporta `(entregas: EntregaPlanEditable[], bloqueado)` vía `onCambio`, con
  `cantidades_por_posicion: null` cuando el modo es automático (mismo contrato que `EntregaPlanIn`
  del backend, D8).
- [x] 7.7 [GREEN] Modificado `frontend/src/lib/api/extraccion.ts`: `DocumentoReciente.document_type`
  suma `'orden_compra'`; `ProcesarPayload.grupoId?: string`; `procesarDocumento` agrega
  `formData.append('grupo_id', grupoId)` solo si viene (mismo patrón condicional que
  `licitacion_id`/`cliente_id` ya existentes en la función).
- [x] 7.8 [GREEN] Modificado `frontend/src/features/carga-documentos/components/FormCard.tsx`:
  quitado `disabled: true` de la opción `ordenes` en `TIPO_OPTIONS` y todo el bloque condicional del
  badge "Próximamente" (los botones de tab ya no reciben `disabled`/`title`); estado `archivo: File |
  null` reemplazado por `archivos: File[]`; `<input type="file" multiple={tipo === 'ordenes'}>`;
  nueva función `procesarMultiple()` que genera `crypto.randomUUID()` **solo** cuando `tipo ===
  'ordenes' && archivos.length > 1` (con 1 solo archivo `orden_compra` no hace falta grupo — D13:
  `grupo_id IS NULL` ya se comporta como un archivo suelto) y llama `procesarDocumento` en un `for
  ...of` con `await` secuencial, capturando cada error por archivo en vez de dejar que aborte el
  `Promise.all`; `esperarNuevoDocumento` ahora recibe `cantidadEsperada` (antes hardcodeado a 1
  implícito vía `> countAntes`) y espera `>= countAntes + cantidadEsperada`; `handleFiles()` limita a
  1 archivo cuando `tipo !== 'ordenes'` aunque el usuario arrastre varios; nueva función
  `cambiarTipo()` limpia `archivos`/el input/la mutación al cambiar de pestaña (antes no hacía falta
  porque `ordenes` estaba deshabilitado). Resultado de la mutación pasa de un mensaje único a una
  lista `resultado.archivo: OK|error` por archivo.
- [x] 7.9 [GREEN] Modificado
  `frontend/src/features/validar-extraccion/ValidarExtraccionListado.tsx`: estado
  `seleccionados: Set<string>` + `gruposLocales: Record<string,string>` (ver nota de diseño de 7.4);
  exportada `puedeAgruparSeleccion()` como guard puro (≥2 filas + mismo `document_type`); 2
  `useMutation` (`agruparExtracciones`/`desagruparExtracciones`) que actualizan `gruposLocales` y
  limpian la selección en `onSuccess`; botón "Agrupar seleccionadas como una sola OC" habilitado por
  el guard sobre `filasSeleccionadas`; botón "Desagrupar" habilitado cuando **todas** las filas
  seleccionadas (≥1) ya están en `gruposLocales`.
- [x] 7.10 [GREEN] Modificado
  `frontend/src/features/validar-extraccion/components/PendientesTable.tsx`: `ETIQUETA_TIPO` **no
  tocado** (confirmado con `grep` antes y después del cambio); nuevas props opcionales
  `seleccionados`/`onAlternarSeleccion`/`gruposLocales`; columna de checkbox nueva al inicio de la
  fila, renderizada **solo** cuando `document_type === 'orden_compra'` (este listado ya filtra
  `validado=false` en la query de `ValidarExtraccionListado`, así que no hace falta re-chequear
  `validado` acá); badge "Grupo" junto al nombre de archivo cuando `gruposLocales[extraccion.id]`
  existe.
- [x] 7.11 [GREEN] Agregado a `frontend/src/lib/api/extracciones.ts`: `MiembroGrupo` (espejo de
  `MiembroGrupo` pydantic), `agruparExtracciones(extractionIds)` (`POST /extracciones/agrupar`,
  mismo body `{extraction_ids}` que `AgruparExtraccionesRequest` real), `desagruparExtracciones(ids)`
  (`POST /extracciones/desagrupar`, 204 sin cuerpo — `presupuestacionFetch` ya maneja body vacío con
  `.json().catch(() => null)`); `FilasExtraccionOut` extendida con `grupo_id?`, `miembros?:
  MiembroGrupo[]`, `advertencias_cabecera?: string[]` (opcionales para no romper los usos existentes
  de licitación/comparativa que no los mandan) — **sin** `modo_fusion_sugerido`, confirmado que no se
  agregó ningún campo con ese nombre.
- [x] 7.12 [REFACTOR] `cd frontend && corepack pnpm test -- CabeceraOrdenCompra EntregasEditor
  FormCard ValidarExtraccionListado` → **165 passed** (los 4 archivos nuevos/afectados, GREEN
  confirmado tras 7.5-7.11: 4+3+4+6 = 17 tests nuevos sobre 148 preexistentes). Suite completa
  `corepack pnpm test` → **165 passed, 0 regresiones**. `corepack pnpm build` (`tsc -b && vite build`)
  → sin errores de tipo, build completo en 1.37s; `frontend/src/routeTree.gen.ts` volvió a
  reordenarse como efecto lateral del build (mismo hallazgo que PR6) — revertido con `git checkout
  --` antes de commitear. **Prueba manual contra el backend real de Phases 2/4, no alcanzada**: mismo
  motivo que 6.6 — este batch de `sdd-apply` corre sin navegador ni sesión interactiva, no hay forma
  de levantar `pnpm --filter frontend dev` y subir 3 archivos a mano desde este entorno; el propio
  prompt de esta fase contempla explícitamente esta posibilidad. Queda pendiente como verificación
  manual humana antes de mergear PR7, o como parte del flujo end-to-end de la tarea 8.7.
- [ ] 7.13 **Cierre de gap post-Phase 7, decidido por el usuario**: `GET /extracciones`
  (`ExtraccionResumen`) no expone `grupo_id`, así que el indicador visual de agrupación y el botón
  "Desagrupar" de `ValidarExtraccionListado`/`PendientesTable` dependen hoy de estado en memoria de la
  sesión (`gruposLocales`), no del dato persistido — se pierde al recargar la página, aunque la
  agrupación real en la base sigue intacta. Cerrar:
  - [RED] Extender el test de `services/presupuestacion/extraccion/repository.py::listar_extracciones`
    (o el que corresponda tras verificar el código real) para afirmar que `grupo_id` viaja en la fila
    devuelta; extender el test de `GET /extracciones` para afirmar que `ExtraccionResumen.grupo_id`
    llega en la respuesta.
  - [GREEN] Agregar `grupo_id: str | None` a `ExtraccionResumen`
    (`services/presupuestacion/extraccion/models.py`) y al `select` de la query que lo arma.
  - [RED→GREEN] Frontend: `ValidarExtraccionListado`/`PendientesTable` leen `grupo_id` real de la
    respuesta de `GET /extracciones` en vez de (o además de, para el caso optimista post-acción)
    `gruposLocales`; el indicador de grupo sobrevive a un refetch/recarga.
  - [REFACTOR] Confirmar no-regresión de la suite completa (backend `pytest tests/ -q -m "not
    integration"` y frontend `corepack pnpm test`).

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
