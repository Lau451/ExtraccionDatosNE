# Tasks: Matching de orden de compra contra presupuesto

> Alcance de este checklist: `oc-presupuesto-candidato`, `oc-presupuesto-vinculacion`, y el delta de
> `orden-compra-validacion` (D10/D11). Sigue estrictamente la tabla § File Changes de
> `design.md` (D1-D13) — no la tabla § Affected Areas de `proposal.md`, que las correcciones C1-C7 del
> propio diseño invalidan parcialmente. En particular:
> `services/presupuestacion/extraccion/models.py` y `extraccion/service.py` **solo tocan
> `ExtraccionResumen`/el listado** (D11) — `ResultadoValidarExtraccion` y
> `_materializar_orden_compra` **no se tocan** (C7, ya existen desde `3b37fca3`).
> `services/presupuestacion/presupuestos/repository.py` **no se modifica** (C6): se importa y reusa
> `listar_items_presupuesto` tal cual.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~3.200 (additions + deletions; fixtures excluidas del riesgo autorado) |
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
requiere pregunta ni decisión antes de aplicar — el orquestador procede con la primera porción usando
la estrategia de cadena elegida. Se eligió **feature-branch-chain**, igual que el cambio padre
`orden-compra`: hay una migración de esquema (0026) con plan de rollback documentado que depende de
revertir en orden (datos antes que esquema, § Migration de `design.md`), y una cadena de ramas contra
un branch de tracker da control de rollback más fino que apilar 9 PRs directo a `dev`. Es una
recomendación de planificación, no una pregunta al usuario — el orquestador puede recachear una
estrategia distinta si lo prefiere. Tracker sugerido: rama `orden-compra-matching-presupuesto` con
base `dev` (mismo patrón que el tracker `orden-compra`, ya mergeado).

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Migración 0026 (esquema, sin RLS/GRANTs nuevos — C3) | PR 1 (base = tracker) | `pytest tests/oc_presupuesto -q` (falla hasta PR2-3; en PR1 se verifica con las queries manuales de Fase 1) | Aplicar la migración contra el proyecto Supabase de test (`grnamollopxdlstcpxhc`) y correr las queries de verificación previa/posterior de `design.md` § Migration | `supabase/migrations/0026_*.sql` + `.down.sql`; revertir es aplicar la down migration documentada (aviso de exportar vínculos antes de dropear, `producto_id` heredado no se toca) |
| 2 | Backend — ranking de presupuestos candidatos (D2, D2.1, D3) | PR 2 (base = PR 1) | `pytest tests/oc_presupuesto/test_service.py tests/oc_presupuesto/test_router.py -k candidato -q` | `pytest tests/oc_presupuesto -m integration -k candidato -q` contra el proyecto Supabase de test | Endpoint `GET /{id}/presupuestos-candidatos` + `rankear_presupuestos_candidatos`; ningún consumidor existente lo llama todavía |
| 3 | Backend — vinculación completa (D4-D9): matching, confirmar, deshacer, descartar | PR 3 (base = PR 2) | `pytest tests/oc_presupuesto -q` | `pytest tests/oc_presupuesto -m integration -q` contra el proyecto Supabase de test (crea/borra vínculos reales sobre la fixture SAMCo Rafaela) | Endpoints `GET /{id}/matching`, `POST/DELETE .../vinculo`, `POST .../descartar`; revertir el módulo entero deja `oc_items` con las 5 columnas nuevas en `NULL`, estado idéntico al de hoy |
| 4 | Backend — wiring (`main.py`) + D10/D11 en `extraccion/` (solo `ExtraccionResumen` y el listado) | PR 4 (base = PR 3) | `pytest tests/extraccion -k orden_compra_id -q` | `pytest tests/extraccion -m integration -k listado -q` contra el proyecto Supabase de test | `include_router` en `main.py` (revertir = quitar la línea); `ExtraccionResumen.orden_compra_id` es aditivo y nullable, revertir no rompe consumidores |
| 5 | Frontend — cliente HTTP + ruta (D8, D13) | PR 5 (base = PR 4) | `pnpm --filter frontend test -- ocMatching` (si hay tests de cliente HTTP; si no, `pnpm --filter frontend typecheck`) | `pnpm --filter frontend dev` + navegar manualmente a la URL con `?presupuesto=<id>` y confirmar que persiste al reload | `frontend/src/lib/api/ocMatching.ts` + ruta nueva + `routeTree.gen.ts`; sin consumidores hasta PR6/PR7 (la navegación llega en PR6, la pantalla en PR7), revertir es solo borrar archivos nuevos |
| 6 | Frontend — sincronización de tipos + navegación automática (D10) | PR 6 (base = PR 5) | `pnpm --filter frontend test -- ValidarExtraccionDetalle` | `pnpm --filter frontend dev` + flujo manual: validar una extracción de tipo OC, confirmar que navega a `/ordenes-compra/:id/matching` | `frontend/src/lib/api/extracciones.ts` (4 campos aditivos) + `ValidarExtraccionDetalle.tsx` `onSuccess`; revertir deja la navegación como hoy (siempre al listado) |
| 7 | Frontend — pantalla de matching (`OcMatchingDetalle` + 5 componentes) | PR 7 (base = PR 6) | `pnpm --filter frontend test -- OcMatchingDetalle SelectorPresupuesto ColumnaPresupuesto ColumnaOrdenCompra RenglonOcFila AvisoReutilizacion` | `pnpm --filter frontend dev` + flujo manual end-to-end contra la fixture SAMCo Rafaela: elegir presupuesto, confirmar 2 vínculos, ver `producto_id` heredado | `frontend/src/features/oc-matching/` completo (directorio nuevo); revertir no afecta ninguna otra pantalla |
| 8 | Frontend — re-entrada: sección "Órdenes de compra validadas" (D11) | PR 8 (base = PR 7) | `pnpm --filter frontend test -- ValidarExtraccionListado` | `pnpm --filter frontend dev` + flujo manual: confirmar una OC, volver al listado, verificar que aparece en la sección nueva con link a matching | `ValidarExtraccionListado.tsx` (query + sección nueva); revertir deja el listado exactamente como hoy |
| 9 | Documentación + verificación integral (tracker → `dev`) | PR 9 (base = PR 8, es el tracker) | `pytest tests/ --cov=services` | `pnpm --filter frontend build` + `pytest tests/ --cov=services` completos + checklist de Success Criteria de `proposal.md` | `docs/schema/extractor_final.sql` (ya actualizado en Fase 1); sin código de producción nuevo en esta unidad |

---

## Phase 1: Esquema — migración 0026 (Foundation, bloquea todo lo demás)

- [x] 1.1 [Verificación previa, solo lectura] Ejecutar contra el proyecto Supabase de test
  (`grnamollopxdlstcpxhc`) las 6 verificaciones de `design.md` § Migration → Verificación previa
  obligatoria. **Evidencia** (ejecutado por el orquestador con `mcp__supabase__execute_sql`, tras
  confirmar `get_project_url` = `grnamollopxdlstcpxhc.supabase.co`; el `sdd-apply` original quedó sin
  ese tool disponible, ver nota de proceso más abajo): (a) `uq_pi_id_drog` no existía en
  `presupuesto_items` → `[]`; (b) ninguna de las 5 columnas nuevas existía en `oc_items` → `[]`; (c)
  `oc_items.drogueria_id` existe, `is_nullable = NO`; (d) `oci_upd` (`cmd=UPDATE`) sigue exigiendo
  `get_rol() = ANY ('admin','gerencia','lider_comercial','comercial')` + `drogueria_id = tenant OR
  es_superadmin()`; (e) `presupuesto_items.excluido` → `NOT NULL DEFAULT false`,
  `precio_unitario` → nullable, sin default; (f) `to_regclass('public.presupuesto_legacy_map')` →
  existe. Las 6 verificaciones pasaron.
- [x] 1.2 Crear `supabase/migrations/0026_oc_vinculo_presupuesto.sql` — transcripción literal del SQL
  de `design.md` § Migration: guard de versión Postgres 15+, `ADD CONSTRAINT uq_pi_id_drog UNIQUE
  (id, drogueria_id)` en `presupuesto_items` (C2), 5 columnas aditivas en `oc_items`
  (`presupuesto_item_id`, `vinculo_descartado`, `vinculo_origen`, `vinculo_confirmado_por`,
  `vinculo_confirmado_at`), FK compuesta `fk_oci_presupuesto_item` con `ON DELETE SET NULL`, los 3
  `CHECK` (`ck_oci_vinculo_excluyente`, `ck_oci_vinculo_origen`, `ck_oci_vinculo_origen_val`),
  comentarios de columna, índice parcial `idx_oci_presupuesto_item`. **Sin RLS ni GRANTs nuevos**
  (C3) — no se agregó ninguno.
  **Evidencia**: archivo creado, 90 líneas, transcripción carácter a carácter del bloque SQL de
  `design.md` líneas 1051-1130 (verificado con diff manual, sin desvíos).
- [x] 1.3 Crear `supabase/migrations/0026_oc_vinculo_presupuesto.down.sql` — reversa en orden inverso,
  con el aviso de exportar (`COPY ... TO`) antes de dropear `presupuesto_item_id`, y la nota
  explícita de que `oc_items.producto_id` ya heredado **no se toca** en el rollback (dato de negocio
  legítimo, § Rollback Plan de `proposal.md`). `uq_pi_id_drog` se deja (puede tener FKs futuras
  apuntándole), con la query de verificación en comentario.
  **Evidencia**: archivo creado, transcripción literal de `design.md` líneas 1134-1167, sin desvíos.
- [x] 1.4 Aplicar `0026` contra el proyecto Supabase de test (MCP `apply_migration`) y verificar en
  vivo. **Evidencia** (orquestador, `mcp__supabase__apply_migration` → `{"success":true}`, contenido
  idéntico al archivo de 1.2): `uq_pi_id_drog` → `UNIQUE (id, drogueria_id)` exacto; 5 columnas en
  `oc_items` con tipo/nullable/default correctos (`presupuesto_item_id uuid NULL`,
  `vinculo_descartado boolean NOT NULL DEFAULT false`, `vinculo_origen text NULL`,
  `vinculo_confirmado_por uuid NULL`, `vinculo_confirmado_at timestamptz NULL`); los 3 `CHECK`
  presentes con `pg_get_constraintdef` idéntico al SQL fuente; `fk_oci_presupuesto_item` →
  `FOREIGN KEY (presupuesto_item_id, drogueria_id) REFERENCES presupuesto_items(id, drogueria_id) ON
  DELETE SET NULL`; `idx_oci_presupuesto_item` → índice parcial `WHERE presupuesto_item_id IS NOT
  NULL` confirmado. `mcp__supabase__get_advisors(type: security)`: 2 hallazgos, ambos preexistentes
  y ajenos a esta migración (`SECURITY DEFINER` de `es_superadmin/get_drogueria_id/get_rol/
  mismo_tenant`, y protección de contraseñas filtradas deshabilitada) — cero hallazgos nuevos sobre
  `oc_items`/`presupuesto_items`.
- [x] 1.5 Aplicar la down migration sobre el mismo entorno de test y confirmar reversión sin error;
  reaplicar `0026` inmediatamente después. **Evidencia** (orquestador): down ejecutado vía
  `mcp__supabase__execute_sql` con el contenido literal de `.down.sql` (menos el DROP de
  `uq_pi_id_drog`, que el propio down.sql deja intacto a propósito) → sin error; verificación
  post-revert de las 5 columnas → `[]` (limpio, ninguna residual); reaplicado `0026` completo
  inmediatamente después → `{"success":true}`; verificación final de las 5 columnas → las 5
  presentes. Entorno de test queda en el estado esperado para Fases 2-3.
- [x] 1.6 Actualizar `docs/schema/extractor_final.sql`: reflejar `uq_pi_id_drog` en
  `presupuesto_items`, las 5 columnas nuevas + 3 `CHECK` + FK compuesta + índice parcial en
  `oc_items`. **Desviación respecto de la instrucción literal**: la tarea pide verificar contra la
  base viva aplicada en 1.4, no contra el snapshot (C4 del cambio padre); como 1.4 está bloqueado,
  esta transcripción se hizo directamente desde el archivo de migración de 1.2 (que sí es la fuente
  de verdad del SQL, ya validada carácter a carácter en 1.2) en vez de contra una base viva que no
  se pudo tocar en ese momento. Sigue el mismo patrón inline de comentarios `-- 0026: ...` que el
  archivo ya usa para 0025. **Cerrado**: 1.4 confirmó contra la base viva que el SQL aplicado es
  carácter a carácter el mismo que este snapshot ya reflejaba — no hubo divergencia que corregir.

> **Nota de proceso (1.1/1.4/1.5)**: la invocación original de `sdd-apply` para esta fase no tuvo
> ningún tool `mcp__supabase__*` disponible en su lista de funciones (el rol `sdd-apply` no lo
> incluye en su definición), pese a que `.mcp.json` configura el servidor contra
> `grnamollopxdlstcpxhc`. El orquestador completó 1.1/1.4/1.5 directamente con esos tools después.
> Vale la pena que una futura fase de backend (2-3, que si necesita escribir/leer contra Supabase
> desde Python, no desde el MCP) confirme si tiene el mismo problema antes de asumir que puede
> correr sus tests de integración sin intervención manual.

## Phase 2: Backend — módulo `oc_presupuesto/`, ranking de presupuestos candidatos (D2, D2.1, D3, D12)

> Depende de Phase 1 solo por `uq_pi_id_drog`/columnas nuevas de completitud de esquema; el ranking
> en sí no las usa (lee `presupuesto_items`/`items_proceso` existentes). Cubre
> `oc-presupuesto-candidato` completa.

- [x] 2.1 [RED] Crear `tests/oc_presupuesto/fixtures/` con el caso real ya validado end-to-end:
  cliente SAMCo Rafaela (CUIT 30-67428388-8), presupuesto `00246033` (2 renglones con
  `precio_unitario` conocido), OC real Nro 00104857 (2 renglones que matchean exacto contra esos 2).
  Reusar el patrón de fixtures/factories de `tests/extraccion/conftest.py`
  (`seed_cliente_factory`) para poder sembrar el caso en el proyecto de test y limpiarlo en
  `finally`.
- [x] 2.2 [RED] Crear `tests/oc_presupuesto/test_service.py` con la tabla de casos de
  `rankear_presupuestos_candidatos` (D2): orden por `renglones_oc_con_coincidencia DESC,
  generado_at DESC, presupuesto_id ASC`; tope de 5 candidatos aplicado **después** de ordenar;
  `presupuestos_del_cliente` cuenta el total sin filtrar (0 coincidencias sigue apareciendo con
  puntaje 0, no se excluye — spec `oc-presupuesto-candidato` § "Ningún renglón... coincide en
  precio"); `presupuesto_sugerido_id = candidatos[0]` cuando hay candidatos, sin autoconfirmar nada
  (spec § "Selección explícita del presupuesto por el usuario", incluso con un solo candidato).
  Confirmar RED: `ModuleNotFoundError: No module named 'services.presupuestacion.oc_presupuesto'`.
- [x] 2.3 [RED] En el mismo archivo, casos vacíos de D2 (spec § "Estado explícito cuando el cliente
  no tiene presupuestos cargados", HTTP 200 en los 3 casos): cliente sin ningún presupuesto
  (`candidatos=[]`, `presupuestos_del_cliente=0`, advertencia A); cliente con presupuestos pero
  ninguno coincide en precio (`candidatos=[]`, `presupuestos_del_cliente=N`, advertencia B,
  **distinta** de la anterior); OC anclada por proceso comercial (`cliente_id IS NULL`) →
  `ValidationError` (422), no una respuesta vacía.
- [x] 2.4 [RED] Tests unitarios de la normalización de escala de precio (D3, § Testing Strategy):
  `Decimal("109.750").quantize(Decimal("0.01"))` produce la misma cadena que
  `Decimal("109.75")`; comparación siempre sobre `Decimal`, nunca `float`; `precio_unitario IS NULL`
  queda fuera del conjunto de filtro sin lanzar excepción; `excluido = TRUE` se excluye del conjunto
  de candidatos (C4).
- [x] 2.5 [RED] Test unitario del troceo de `in_()` en lotes de 200 (D3): una lista de 450 ids
  produce 3 llamadas al cliente Supabase mockeado, con la concatenación de resultados intacta.
- [x] 2.6 [GREEN] Crear `services/presupuestacion/oc_presupuesto/__init__.py` (módulo nuevo, D12).
- [x] 2.7 [GREEN] Crear `services/presupuestacion/oc_presupuesto/models.py` con **todos** los modelos
  de `design.md` § Interfaces/Contracts (se usan en Phases 2 y 3, un solo archivo): `EstadoVinculo`,
  `OrigenVinculo`, `CandidatoPresupuesto`, `PresupuestosCandidatosOut`, `RenglonPresupuesto`,
  `CandidatoVinculo`, `RenglonOrdenCompra`, `MatchingOut`, `ConfirmarVinculoRequest` (con
  `model_config = ConfigDict(extra="forbid")`). Transcripción literal de los `BaseModel` del
  diseño, sin campos adicionales.
- [x] 2.8 [GREEN] Crear `services/presupuestacion/oc_presupuesto/repository.py` — solo las funciones
  del camino de ranking por ahora: resolución de `procesos_comerciales`/`presupuestos` del cliente
  (C6, dos pasos: `presupuestos` no tiene `cliente_id`), select de `presupuesto_items` con
  `in_(precios)` + `eq("excluido", False)` (D3, con troceo de 200 de 2.5), select de `items_proceso`
  para descripción (C5), lookup de `numero_presupuesto` vía `presupuesto_legacy_map` con el
  **service client**, acotado a los `presupuesto_id` ya autorizados (D2.1, fallback `null` si no hay
  fila).
- [x] 2.9 [GREEN] Crear `services/presupuestacion/oc_presupuesto/service.py` —
  `rankear_presupuestos_candidatos()`: arma el conjunto de precios de la OC, cuenta coincidencias
  por presupuesto, ordena por el criterio de D2, aplica el tope de 5, arma las dos advertencias de
  casos vacíos.
- [x] 2.10 [GREEN] Crear `services/presupuestacion/oc_presupuesto/router.py` con
  `_ROLES_MATCHING = ("admin", "gerencia", "lider_comercial", "comercial")` (tupla local nueva,
  desviación explícita de D12) y el endpoint `GET /ordenes-compra/{orden_compra_id}
  /presupuestos-candidatos`. Autorización por endpoint (D12): `require_roles(_ROLES_MATCHING)` →
  lectura de la OC con *user client* → `NotFoundError` si no aparece (404, no confirma existencia de
  OC de otra droguería).
  `pytest tests/oc_presupuesto/test_service.py -m "not integration" -q` → confirmar GREEN.
- [x] 2.11 [RED→GREEN] Crear `tests/oc_presupuesto/test_router.py` con la tabla de autorización del
  endpoint: rol fuera de `_ROLES_MATCHING` → 403; OC de otra droguería (RLS) → 404; OC anclada por
  proceso comercial → 422. Confirmar RED antes de escribirlos contra el router de 2.10 (deben fallar
  por `ImportError`/`AttributeError` antes del `router.py`, pasar después).
- [x] 2.12 [REFACTOR] Correr `pytest tests/oc_presupuesto -m integration -k candidato -q` contra el
  proyecto Supabase de test (fixture SAMCo Rafaela de 2.1): el presupuesto `00246033` aparece
  primero con `renglones_oc_con_coincidencia = 2`. Verificación de no-regresión:
  `pytest tests/ -q -m "not integration"` contra el baseline previo a esta fase.

> **Evidencia de Phase 2 (2.1-2.12), sdd-apply**: implementación y tests de esta unidad se
> escribieron en el mismo lote de este batch (no ciclo RED-observado→GREEN estrictamente
> secuencial por tarea, como sí ocurrió en Phase 1). Para no reportar RED sin haberlo visto de
> verdad, se movió `services/presupuestacion/oc_presupuesto/` fuera del árbol una vez escrito todo
> y se corrió `pytest tests/oc_presupuesto/test_service.py -m "not integration" -q`: falló en la
> colección con exactamente `ModuleNotFoundError: No module named
> 'services.presupuestacion.oc_presupuesto'` (texto idéntico al predicho en 2.2). Se restauró el
> módulo y se confirmó GREEN a continuación. Esto cubre el RED de 2.1-2.5 y de 2.11 (que importa
> del mismo módulo movido).
>
> - **2.1**: `tests/oc_presupuesto/fixtures/samco_rafaela.py` (`sembrar`/`limpiar`, no un pytest
>   fixture en sí) + `tests/oc_presupuesto/conftest.py::seed_caso_samco_rafaela` que lo envuelve
>   con `try/finally`. **Desviación de dato respecto de proposal.md**: `ck_terceros_cuit` exige 11
>   dígitos sin guiones (`docs/schema/extractor_final.sql`); el CUIT humano `30-67428388-8` de la
>   propuesta se normalizó a `30674283888` (mismos dígitos, formato que la base exige). Sin fila en
>   `presupuesto_legacy_map` a propósito (D2.1: cargado a mano, `numero_presupuesto` debe viajar
>   `null`).
> - **2.2**: `_rankear_presupuestos` (función pura, sin cliente Supabase) probada con: orden por
>   coincidencias, desempate por `generado_at`/`id`, `None` en `precio_unitario` sin romper, conteo
>   por renglón de OC (no por `presupuesto_item`, para no sobre-contar precios repetidos), tope de 5
>   sin esconder al mejor, cola con puntaje 0 visible cuando hay al menos un candidato con puntaje
>   > 0, `presupuesto_sugerido_id` nunca autoconfirma.
> - **2.3**: `test_cliente_sin_ningun_presupuesto_devuelve_candidatos_vacio_con_advertencia_a`,
>   `test_cliente_con_presupuestos_pero_ninguno_coincide_devuelve_candidatos_vacio_con_advertencia_b`,
>   `test_advertencia_sin_presupuestos_es_distinta_de_advertencia_ninguno_coincide` (confirma texto
>   de advertencia distinto entre los dos casos vacíos) y
>   `test_oc_anclada_por_proceso_comercial_sin_cliente_levanta_validation_error`.
> - **2.4**: `test_q2_normaliza_escala_109_750_igual_a_109_75`, `test_q2_siempre_devuelve_decimal`,
>   `test_rankear_precio_unitario_none_en_presupuesto_item_queda_fuera_sin_romper` (función pura) y
>   `test_listar_presupuesto_items_por_precio_excluye_excluido_true` (cliente Supabase mockeado,
>   confirma que la query real pide `.eq("excluido", False)` -- la exclusión ocurre en Postgres, no
>   en la función pura de ranking, así que ese caso se testea a nivel repository).
> - **2.5**: `test_en_lotes_de_450_ids_produce_3_lotes_de_200_200_50` (función pura `_en_lotes`) +
>   `test_listar_presupuestos_de_procesos_trocea_450_ids_en_3_llamadas_al_cliente_mockeado`
>   (`MagicMock` con `side_effect` en `.in_()`: 450 ids → 3 llamadas de tamaño 200/200/50,
>   `len(resultado) == 450` confirma la concatenación intacta).
> - **2.6-2.9**: `services/presupuestacion/oc_presupuesto/{__init__,models,repository,service}.py`.
>   `models.py` verificado carácter a carácter contra `design.md` § Interfaces/Contracts (líneas
>   772-859), sin campos añadidos. **Desviación menor en 2.8**: el select de `items_proceso` para
>   descripción (C5) no se incluyó todavía -- ningún endpoint de Phase 2 lo necesita
>   (`CandidatoPresupuesto` no tiene campo de descripción, solo `nombre_proceso` de
>   `procesos_comerciales`); queda para Phase 3 (`obtener_matching`), que sí lo necesita.
>   `pytest tests/oc_presupuesto/test_service.py -m "not integration" -q` → `17 passed`.
> - **2.10**: `services/presupuestacion/oc_presupuesto/router.py`. **No se tocó `main.py`** a
>   propósito -- `include_router` es task 4.1 (Phase 4), fuera del alcance de esta invocación; el
>   test de router de 2.11 monta una `FastAPI()` descartable, mismo patrón que
>   `tests/pcp/gestion/test_router.py`.
> - **2.11**: `tests/oc_presupuesto/test_router.py`, 3 tests de integración
>   (`crear_usuario_con_token` + `TestClient`, llamar al endpoint como función de Python no ejercita
>   `Depends(require_roles(...))`). Se encontraron y corrigieron 2 bugs de datos en los propios
>   tests durante la verificación en vivo, no en el código de producción: (a) el CUIT con guiones de
>   2.1 violaba `ck_terceros_cuit` (11 dígitos exactos); (b) el `finally` de
>   `test_oc_de_otra_drogueria_da_404_por_rls_sin_confirmar_su_existencia` intentaba borrar la
>   droguería de test antes que la fila `usuarios` que la referencia (`fk_usuarios_drogueria`) --
>   corregido borrando `usuarios` primero, mismo criterio que `tests/compras/conftest.py`.
> - **2.12**: `pytest tests/oc_presupuesto -m integration -q` → `4 passed` (sin filtro `-k
>   candidato`: el nombre real del test es
>   `test_ranking_integracion_samco_rafaela_pone_el_presupuesto_primero_con_2_coincidencias`, y
>   correr sin `-k` no pierde cobertura de los otros 3 de `test_router.py`). El test confirma:
>   `presupuestos_del_cliente == 1`, `len(candidatos) == 1`, `candidato.presupuesto_id` =
>   `presupuesto_id` de la fixture, `renglones_oc_con_coincidencia == 2`,
>   `renglones_oc_totales == 2`, `numero_presupuesto is None` (D2.1, cargado a mano),
>   `presupuesto_sugerido_id` = `presupuesto_id` de la fixture. No-regresión:
>   `pytest tests/ -q -m "not integration"` → `404 passed` (baseline completo del proyecto,
>   incluye las 17 unidades nuevas no-integration de `tests/oc_presupuesto`), sin fallas fuera de
>   `tests/oc_presupuesto/`.

## Phase 3: Backend — vinculación renglón a renglón (D4-D9, D12)

> Depende de Phase 2 (mismos `models.py`/módulo). Cubre `oc-presupuesto-vinculacion` completa.

- [x] 3.1 [RED] En `tests/oc_presupuesto/test_service.py`, tabla de `obtener_matching` (D8):
  resolución del presupuesto activo en el orden documentado — vínculos confirmados de la OC primero,
  luego query param, luego el sugerido del ranking; **invariante duro**: todos los vínculos
  confirmados de una misma OC pertenecen al mismo presupuesto (verificado antes de escribir, no solo
  al leer).
- [x] 3.2 [RED] Tests de `_ordenar_por_similitud` (D7, spec § "Varios matches del mismo precio se
  ordenan por similitud de descripción"): ordena descendente por `fuzz.WRatio`, **no filtra** por
  score — incluir explícitamente un par con score < 70 que debe seguir apareciendo; `None` cuando
  hay un solo candidato (no hay nada que desempatar); reusa `normalizar_descripcion` importado tal
  cual, sin parametrizar.
- [x] 3.3 [RED] Tests de herencia de `producto_id` (D6, spec § "Herencia de `producto_id` al
  confirmar un vínculo"): tabla de 4 casos del `COALESCE(presupuesto_items.producto_id,
  items_proceso.producto_id)` — ambos presentes (gana el del presupuesto), solo presupuesto, solo
  item_proceso, ninguno (`producto_id` queda `None`, **sin excepción y sin estado de UI especial**,
  confirmando explícitamente que no hay precondición de bloqueo).
- [x] 3.4 [RED] Tests de `confirmar_vinculo` (D4, D13, spec § "Sugerencia de vínculo por precio
  exacto" y § "Confirmación humana obligatoria y granular por renglón"): un solo `UPDATE` después de
  todas las validaciones; acepta un vínculo cuyo precio **no** coincide con `vinculo_origen='manual'`
  (nunca bloquea, "el precio sugiere, no autoriza"); confirmar sobre un renglón ya confirmado
  reemplaza el vínculo sin error (idempotencia, D13); confirmar contra un presupuesto distinto del
  que ya tiene vínculos → `ValidationError` 422 nombrando el presupuesto actual (D8); `oc_item_id`
  que no pertenece a la OC → `NotFoundError` 404; `presupuesto_item_id` de otra droguería/cliente →
  `NotFoundError` 404 (no 403); `presupuesto_item_id` con `excluido=TRUE` → `ValidationError` 422.
- [x] 3.5 [RED] Tests de `deshacer_vinculo` (D9, spec § implícita en el ciclo de confirmación — no
  hay requirement propio en el spec de vinculación para deshacer, documentar la referencia a D9 de
  `design.md` como fuente): revierte el renglón a `pendiente` sirviendo tanto para `confirmado` como
  para `sin_presupuesto`; revierte `producto_id` a `NULL` **solo** si sigue siendo el valor que el
  vínculo dio (recalculado en el momento); lo deja intacto si fue cambiado por otro camino después;
  no-op si ya era `NULL`.
- [x] 3.6 [RED] Tests de `descartar_renglon` (D4): marca `vinculo_descartado=True` →
  `estado='sin_presupuesto'`, distinto de `pendiente` ("todavía no lo miré" vs. "lo miré y no
  está").
- [x] 3.7 [RED] Tests del aviso N:1 (D5, spec § "Relación N:1 permitida, con aviso no bloqueante"):
  dos `oc_items` (incluso de **distintas** OC de la misma droguería) apuntando al mismo
  `presupuesto_item_id` → `renglones_oc_vinculados=2`, `renglones_oc_vinculados_otras_oc` cuenta las
  de otra OC, `cantidad_vinculada` suma cantidades, **ninguna excepción ni bloqueo en ningún caso**.
- [x] 3.8 [RED] Test del invariante duro (spec § "`items_proceso.estado_matching` y
  `confianza_matching` quedan fuera de alcance"): snapshot de ambos campos antes/después de una
  sesión completa (confirmar + deshacer + descartar sobre varios renglones) → sin cambios.
- [x] 3.9 [RED] Test de integración con la fixture SAMCo Rafaela (spec § "Caso validado con datos
  reales — dos renglones sin ambigüedad"): los 2 renglones de la OC 00104857 reciben exactamente un
  renglón de presupuesto sugerido cada uno, sin desempate necesario, confirmar ambos hereda
  `producto_id` correctamente.
  Confirmar RED de 3.1-3.9 con `pytest tests/oc_presupuesto/test_service.py -m "not integration" -q`
  antes de 3.10.
- [x] 3.10 [GREEN] Extender `services/presupuestacion/oc_presupuesto/repository.py`: select de
  `oc_items` de la droguería con `presupuesto_item_id` en el conjunto (aviso N:1, usa
  `idx_oci_presupuesto_item`), el `UPDATE` único de confirmación/deshacer/descarte.
- [x] 3.11 [GREEN] Extender `services/presupuestacion/oc_presupuesto/service.py`:
  `obtener_matching()`, `confirmar_vinculo()`, `deshacer_vinculo()`, `descartar_renglon()`, con el
  orden de validación-antes-de-escribir de D12 (pertenencia de `oc_item` ∈ OC, `presupuesto_item` ∈
  presupuesto elegido ∈ cliente de la OC, **antes del primer write**).
- [x] 3.12 [GREEN] Extender `services/presupuestacion/oc_presupuesto/router.py` con los 4 endpoints
  restantes de D13: `GET /{id}/matching?presupuesto_id=`, `POST /{id}/items/{oc_item_id}/vinculo`,
  `DELETE /{id}/items/{oc_item_id}/vinculo`, `POST /{id}/items/{oc_item_id}/descartar` — todos con
  `_ROLES_MATCHING`, todos devuelven `MatchingOut` completo (D13, no solo el renglón tocado).
  `pytest tests/oc_presupuesto/test_service.py -m "not integration" -q` → confirmar GREEN.
- [x] 3.13 [GREEN] Extender `tests/oc_presupuesto/test_router.py`: tabla completa de errores de D13
  (404 pertenencia, 422 presupuesto cruzado/excluido/OC sin cliente, idempotencia del
  re-confirmar) como tests de integración con cliente Supabase mockeado.
  `pytest tests/oc_presupuesto/test_router.py -m "not integration" -q` → confirmar GREEN.
- [x] 3.14 [REFACTOR] Correr `pytest tests/oc_presupuesto -m integration -q` contra el proyecto
  Supabase de test: fixture SAMCo Rafaela completa (confirmar los 2 vínculos reales), aviso N:1 con
  datos reales, invariante `estado_matching` sin modificar. Verificación de no-regresión:
  `pytest tests/ -q -m "not integration"` sin regresiones fuera de `tests/oc_presupuesto/`.

> **Evidencia de Phase 3 (3.1-3.14), sdd-apply**: mismo patrón que Phase 2 — implementación y tests
> de esta unidad se escribieron en el mismo lote (RED confirmado retroactivamente, no ciclo
> estrictamente secuencial tarea por tarea). Se extendieron los 3 archivos existentes del módulo
> (`repository.py`, `service.py`, `router.py`, ya creados en Phase 2 — sin archivos nuevos, D12 ya
> resuelto) más `tests/oc_presupuesto/test_service.py` y `test_router.py`.
>
> **RED confirmado**: se corrió `git stash push -- services/presupuestacion/oc_presupuesto/{repository,router,service}.py`
> (deja el módulo en el estado exacto de Phase 2, sin las funciones de Phase 3) y
> `pytest tests/oc_presupuesto/test_service.py -m "not integration" -q` → `41 failed, 17 passed`,
> todas las fallas nuevas por `AttributeError: module '...repository' has no attribute
> 'actualizar_oc_item'/'buscar_oc_item'/etc.` (exactamente los símbolos de Phase 3, ningún falso
> positivo) y los 17 tests de Phase 2 intactos. `git stash pop` restauró la implementación.
>
> - **3.1**: `_resolver_presupuesto_activo` (función pura sobre dicts + un helper `_top_presupuesto_sugerido`
>   monkeypatcheable) probada con: prioriza vínculos confirmados sobre query param; usa query param
>   sin vínculos; cae al sugerido del ranking sin ninguno de los dos; devuelve la advertencia correcta
>   (sin presupuestos / ninguno coincide) cuando el ranking no sugiere nada; el invariante duro
>   (vínculos de una misma OC en presupuestos distintos) levanta `ValidationError` — verificado tanto
>   al leer (acá) como antes de escribir (3.4).
> - **3.2**: `_ordenar_por_similitud` — orden descendente por `WRatio`; el caso real de D7
>   (`HCT 50MG X30` vs `HIDROCLOROTIAZIDA 50MG COMP`, score bajo) sigue apareciendo sin filtrarse;
>   `None` con un solo candidato; se confirma con un espía que reusa `normalizar_descripcion` tal cual
>   (no una copia parametrizada).
> - **3.3**: `_heredar_producto_id`, función pura, los 4 casos del `COALESCE` — ninguno lanza
>   excepción, incluido `item_proceso=None`.
> - **3.4**: `confirmar_vinculo` con `repo`/`presupuestos_repo` monkeypatcheados y `obtener_matching`
>   reemplazado por un sentinel (aísla la lógica de validación-y-write de la lógica de lectura, ya
>   cubierta por los tests de `obtener_matching`): un solo `actualizar_oc_item` tras validar; precio no
>   coincidente → `vinculo_origen='manual'`; re-confirmar el propio renglón no choca contra su vínculo
>   anterior (se excluye a sí mismo del chequeo de invariante); presupuesto cruzado → `ValidationError`
>   con el id del presupuesto activo en el mensaje; `oc_item` ajeno, `presupuesto_item` de otra
>   droguería, y de otro cliente (misma droguería, distinto `proceso_comercial`) → `NotFoundError`;
>   `excluido=TRUE` → `ValidationError`; OC sin cliente → `ValidationError`.
> - **3.5**: `deshacer_vinculo` — revierte `producto_id` a `NULL` solo si coincide exactamente con el
>   recalculado en el momento; lo deja **intacto** (ni la clave `producto_id` viaja en el `UPDATE`) si
>   fue cambiado por otro camino; no-op si ya era `NULL`; sirve para `sin_presupuesto` también.
> - **3.6**: `descartar_renglon` — `vinculo_descartado=True` + `presupuesto_item_id=None` en el mismo
>   `UPDATE` (obligatorio por `ck_oci_vinculo_excluyente`, aunque el renglón estuviera `pendiente`).
> - **3.7**: `_agregar_aviso_n1`, función pura — cuenta total/otras-OC y suma `cantidad_vinculada`
>   correctamente con datos de más de una OC; lista vacía no rompe.
> - **3.8/3.9**: integración contra `grnamollopxdlstcpxhc` con la fixture SAMCo Rafaela existente
>   (sin reescribirla): 3.9 crea 2 productos reales, los asigna a los 2 `presupuesto_items`, confirma
>   ambos vínculos vía `obtener_matching`+`confirmar_vinculo` y verifica candidato único sin desempate
>   más herencia correcta de `producto_id`; 3.8 corre una sesión completa (2 confirmar + 1 deshacer +
>   1 descartar) y confirma que `items_proceso.estado_matching`/`confianza_matching` no cambian.
>   **Nota de proceso**: el primer intento de 3.9 falló en su propio `finally` (no en las
>   aserciones) por `fk_pi_prod`/`fk_oci_prod` (RESTRICT) — los productos de test no se pueden borrar
>   mientras `presupuesto_items`/`oc_items` todavía los referencian, y el teardown de
>   `seed_caso_samco_rafaela` borra esas filas recién *después* de que el `finally` del test corre
>   (orden de fixtures). Corregido soltando ambas referencias (`producto_id=NULL`) antes de borrar los
>   productos; se limpiaron a mano 2 productos y 1 droguería huérfanos que quedaron de los 2 intentos
>   fallidos (`get_service_client()` directo, mismo criterio que la nota de 1.1).
> - **3.10-3.12**: `services/presupuestacion/oc_presupuesto/{repository,service,router}.py`
>   extendidos (mismos archivos, D12: "cero módulos nuevos" ya resuelto en Phase 2).
>   `pytest tests/oc_presupuesto/test_service.py -m "not integration" -q` → `58 passed`.
> - **3.13**: `tests/oc_presupuesto/test_router.py` extendido con 8 tests de integración nuevos
>   (ciclo HTTP completo, mismo patrón que 2.11): `GET matching` 200 con columnas completas; `POST
>   vinculo` 200 con herencia + idempotencia del re-confirmar; `POST vinculo` 422 excluido; `POST
>   vinculo` 404 `oc_item` ajeno y 404 `presupuesto_item` inexistente; `DELETE vinculo` + `POST
>   descartar` 200 revirtiendo a `pendiente`/`sin_presupuesto`.
>   `pytest tests/oc_presupuesto/test_router.py -m "not integration" -q` → `0 passed, 9 deselected`
>   (todos los tests del archivo son de integración; confirma que el archivo colecciona sin errores).
> - **3.14**: `pytest tests/oc_presupuesto -m integration -q` → `12 passed` (4 de Phase 2 + 8 nuevos
>   de Phase 3: matching, vinculo x2, excluido, oc_item ajeno, presupuesto_item inexistente,
>   deshacer+descartar, SAMCo Rafaela completo, sesión-sin-modificar-estado_matching). No-regresión:
>   `pytest tests/ -q -m "not integration"` → `445 passed` (404 baseline de Phase 2 + 41 tests nuevos
>   de Phase 3 no-integration), sin fallas fuera de `tests/oc_presupuesto/`.

## Phase 4: Backend — wiring + D10/D11 en `extraccion/` (solo `ExtraccionResumen`/listado, C7)

> Depende de Phase 3 (router completo para `include_router`). No depende de Phase 1/2/3 para D11,
> podría correr en paralelo, pero se secuencia después para no bifurcar la cadena de PRs.

- [x] 4.1 [GREEN] Modificar `services/presupuestacion/main.py`: `include_router` del router de
  `oc_presupuesto/` (D12). **No confundir con `ResultadoValidarExtraccion`**: ese modelo y
  `_materializar_orden_compra()` **no se tocan** — ya devuelven/propagan `orden_compra_id` desde
  `3b37fca3` (C7).
  **Evidencia**: import + `app.include_router(oc_presupuesto_router, tags=["oc_presupuesto"])`
  agregados (2 líneas). Verificado con `python -c "from services.presupuestacion.main import app; ..."`
  → `app` importa sin error, 167 rutas totales (antes 162); las 5 rutas de `oc_presupuesto/router.py`
  confirmadas presentes: `GET/POST/DELETE .../items/{oc_item_id}/vinculo`,
  `POST .../items/{oc_item_id}/descartar`, `GET .../matching`, `GET .../presupuestos-candidatos`.
- [x] 4.2 [RED] En `tests/extraccion/test_service.py` (o archivo dedicado si el existente crece
  demasiado), test del listado de extracciones validadas con `orden_compra_id` poblado (D11): dado
  un lote de extracciones que incluye una `orden_compra` validada, el listado devuelve
  `ExtraccionResumen.orden_compra_id` con el id real de `ordenes_compra` (lookup por
  `ordenes_compra.extraction_id`); licitación/comparativa devuelven `orden_compra_id=None`. Caso de
  grupo multi-archivo (D13 del cambio padre + nota de D11): solo **una** de las N extracciones del
  grupo lleva `orden_compra_id` no nulo (`ordenes_compra.extraction_id` guarda una sola), las N-1
  restantes quedan en `None` — comportamiento **aceptado explícitamente**, el test lo afirma en vez
  de asumir que debería ser distinto. Confirmar RED:
  `AttributeError`/campo inexistente en `ExtraccionResumen`.
  **Evidencia**: 5 tests unitarios agregados a `tests/extraccion/test_service.py` (mapeo del lookup
  vía `monkeypatch.setattr(repo, ...)`, lote vacío no llama al lookup, troceo de `_en_lotes` en
  200/200/50, troceo de `listar_ordenes_compra_por_extraction_ids` con cliente mockeado, lookup con
  lista vacía no llama al cliente — mismo patrón que `tests/oc_presupuesto/test_service.py`) + 2 tests
  de integración en `tests/extraccion/test_router.py` (extracción validada de tipo OC vs.
  licitación; grupo multi-archivo con solo el ancla poblado). RED confirmado:
  `pytest tests/extraccion/test_service.py -m "not integration" -q` → `5 failed, 15 passed` — las 5
  fallas nuevas por `AttributeError: module '...repository' has no attribute
  'listar_ordenes_compra_por_extraction_ids'` (3 tests) y `has no attribute '_en_lotes'` (1 test) y
  la misma causa raíz en el test de mapeo (falla al monkeypatchear el símbolo inexistente) — exactamente
  los símbolos de 4.3-4.5, ningún falso positivo; los 15 tests preexistentes del archivo intactos.
- [x] 4.3 [GREEN] Modificar `services/presupuestacion/extraccion/models.py`: agregar
  `orden_compra_id: str | None = None` **solo** a `ExtraccionResumen`. `ResultadoValidarExtraccion`
  queda sin tocar (C7).
  **Evidencia**: campo agregado con comentario que distingue explícitamente este campo del
  `orden_compra_id` de `ResultadoValidarExtraccion` (C7, campo distinto en modelo distinto, ya
  existente desde `3b37fca3`). `ResultadoValidarExtraccion` confirmado sin diff (verificado con
  `git diff` acotado al archivo: único hunk es el de `ExtraccionResumen`).
- [x] 4.4 [GREEN] Modificar `services/presupuestacion/extraccion/repository.py`: función de lookup de
  `ordenes_compra` por `extraction_id` acotada a las extracciones del lote que se está listando
  (`in_()`, mismo patrón de troceo que el módulo nuevo si el lote puede ser grande).
  **Evidencia**: `_TAMANO_LOTE = 200` + `_en_lotes()` (idénticos a
  `oc_presupuesto/repository.py`/`imports/repository.py`, replicados localmente por frontera de
  módulos — ningún módulo importa el helper privado de otro, mismo criterio que D12) y
  `listar_ordenes_compra_por_extraction_ids(client, *, extraction_ids) -> list[dict]` (`select("id,
  extraction_id")`, `in_("extraction_id", lote)`, troceado, `[]` sin llamar al cliente si
  `extraction_ids` está vacío).
- [x] 4.5 [GREEN] Modificar `services/presupuestacion/extraccion/service.py`: poblar
  `ExtraccionResumen.orden_compra_id` en la función que arma el listado, usando el lookup de 4.4.
  `_materializar_orden_compra()` queda sin tocar (C7).
  **Evidencia**: `listar_extracciones()` arma `orden_compra_id_por_extraccion` (dict
  `extraction_id -> orden_compra_id`) desde el lookup de 4.4 (solo si `filas` no está vacío, confirmado
  por el test de 4.2 que verifica que un lote vacío no dispara la llamada) y lo aplica con
  `.get(fila["id"])` al construir cada `ExtraccionResumen` — `None` por defecto para
  licitación/comparativa y para los N-1 miembros no-ancla de un grupo (D11, aceptado). `git diff`
  acotado al archivo: único cambio es dentro de `listar_extracciones()`, ninguna otra función tocada.
- [x] 4.6 [REFACTOR] Correr `pytest tests/extraccion -m "not integration" -q` y
  `pytest tests/extraccion -m integration -k listado -q` contra el proyecto de test. Verificación de
  no-regresión: `pytest tests/ -q -m "not integration"` completo, confirmando que las suites de
  licitación/comparativa/OC de `orden-compra` (Tramos 1-2) siguen en verde sin cambios.
  **Evidencia**: `pytest tests/extraccion -m "not integration" -q` → `120 passed` (115 baseline +
  5 nuevos de 4.2). El comando literal `-k listado` de la tarea no matchea ningún test real (los
  nombres del archivo usan `listar_extracciones`, no `listado`); se corrió en su lugar
  `pytest tests/extraccion -m integration -k "orden_compra_id or grupo_multiarchivo" -q` → `2 passed`
  (los 2 tests de 4.2) contra `grnamollopxdlstcpxhc`. **Nota de proceso**: el primer intento contra el
  proyecto de test devolvió `521 Web server is down` (Cloudflare) y luego `PGRST205 — schema cache`
  al despertar de pausa por inactividad; se esperó a que el REST endpoint respondiera 200 sobre
  `droguerias` antes de reintentar, sin cambios de código de por medio — infraestructura externa, no
  un defecto. El primer intento de los tests también reveló que faltaba `cliente_id` en el insert
  manual de `ordenes_compra` de los propios tests (`ck_oc_anclaje` — una OC sin
  `proceso_comercial_id` necesita `cliente_id`, C7/D8 del diseño de `orden-compra`); corregido en el
  test con `seed_cliente_factory`, no en código de producción. No-regresión:
  `pytest tests/ -q -m "not integration"` → `450 passed` (445 baseline de Phase 3 + 5 nuevos de esta
  fase), sin fallas fuera de `tests/extraccion/`.

## Phase 5: Frontend — cliente HTTP + ruta (D8, D13)

> Depende de Phase 3 (los 5 endpoints ya existen en el backend). Se adelanta respecto de la
> sincronización de navegación (Phase 6) a propósito: `useNavigate` de TanStack Router tipa `to`
> contra `routeTree.gen.ts`, así que el `navigate({ to: '/ordenes-compra/$ordenCompraId/matching' })`
> de Phase 6 no compilaría si la ruta todavía no existe. Este orden evita ese error de tipos.

- [x] 5.1 [RED→GREEN] Crear `frontend/src/lib/api/ocMatching.ts`: espejos TypeScript literales de los
  modelos Pydantic de `oc_presupuesto/models.py` (`snake_case`, comentario que nombra el modelo de
  origen, misma convención que `extracciones.ts`), y las 5 funciones:
  `obtenerPresupuestosCandidatos`, `obtenerMatching`, `confirmarVinculo`, `deshacerVinculo`,
  `descartarRenglon` — firmas literales de `design.md` § Espejos TypeScript.
  **Evidencia**: `EstadoVinculo`, `OrigenVinculo`, `CandidatoPresupuesto`,
  `PresupuestosCandidatosOut`, `RenglonPresupuesto`, `CandidatoVinculo`, `RenglonOrdenCompra`,
  `MatchingOut` transcriptos carácter a carácter contra
  `services/presupuestacion/oc_presupuesto/models.py` (verificado leyendo el archivo real, no
  `design.md`), con la misma convención de comentario-por-campo. Los campos `Decimal` de Python se
  mapean a `number` en TS — **no** a `string`: se siguió el precedente real de
  `frontend/src/lib/api/pcp.ts` (`precio_referencia`, `precio_unitario` → `number | null`), que es
  el módulo que sí mirroriza respuestas `Decimal` del backend; `extracciones.ts` usa `string` para
  `cantidad`/`precio_unitario`, pero ahí son inputs de formulario/CSV sin tipar (`FilaOrdenCompraIn`),
  no la forma de un `BaseModel` de respuesta — no es el precedente aplicable. Los campos `datetime`
  (`generado_at`) se mapean a `string`, mismo criterio que `created_at` en `ExtraccionResumen`. Las 5
  funciones llaman a `presupuestacionFetch` (reusado tal cual, sin cliente nuevo) contra las rutas
  literales de D13; `obtenerMatching` omite `presupuesto_id` del querystring cuando no se pasa
  (mismo patrón `URLSearchParams` que `listarExtracciones`).
- [x] 5.2 [GREEN] Crear
  `frontend/src/routes/_authenticated.ordenes-compra.$ordenCompraId.matching.tsx`: ruta con
  `validateSearch` de `presupuesto` (query param opcional, D8 — sobrevive a reload, compartible por
  link).
  **Evidencia**: mismo patrón `createFileRoute` + `validateSearch` que
  `_authenticated.validar-extraccion.$extractionId.tsx` (la ruta análoga más cercana). Sin
  `beforeLoad`/guard de rol propio: `_authenticated.tsx` (layout padre) ya exige sesión
  (`requireAuth`) para toda la rama, y `validar-extraccion` — el predecesor inmediato en el flujo —
  tampoco guarda por rol en el frontend (la autorización real vive en el backend, D12,
  `_ROLES_MATCHING`); no se inventó una tupla de roles de frontend fuera del alcance de esta fase.
  **Desviación explícita, documentada en el propio archivo**: `OcMatchingDetalle` (Phase 7,
  `frontend/src/features/oc-matching/`) todavía no existe — esta fase se adelantó a propósito
  (nota de dependencia al inicio de esta Phase 5) solo para que `routeTree.gen.ts` tipe el
  `navigate({ to: ... })` de Phase 6. El componente de la ruta es un placeholder mínimo que resuelve
  `Route.useParams()`/`Route.useSearch()` con la forma final (D8) y los renderiza; Phase 7 reemplaza
  el cuerpo sin tocar la firma de la ruta.
- [x] 5.3 [Generado] Regenerar `frontend/src/routeTree.gen.ts` con TanStack Router (`pnpm --filter
  frontend dev` o el comando del generador del proyecto) tras crear la ruta de 5.2.
  **Evidencia**: no hay comando `typecheck`/generador dedicado en `package.json` (solo `dev`,
  `build`, `lint`, `preview`, `test`); el plugin `@tanstack/router-plugin/vite` (`vite.config.ts`)
  regenera el árbol como side-effect de cualquier build/dev de Vite, así que se corrió
  `pnpm exec vite build` (más rápido y no interactivo que `pnpm dev`) — terminó en 1.37s, generó
  `dist/` (gitignorado, sin rastro en `git status`) y emitió el chunk nuevo
  `_authenticated.ordenes-compra._ordenCompraId.matching-*.js`, confirmando que el router lo
  descubrió. Verificado con `rg` sobre el archivo regenerado: la ruta nueva aparece en las 8
  ubicaciones esperadas (import, `.update()`, los 3 mapas de tipos `FileRoutesByFullPath`/
  `FileRoutesByTo`/`FileRoutesById`, el bloque `FileRouteTypes`, `routesByPath` y el árbol final).
  **Nota sobre el diff pre-existente**: `git status` ya mostraba `frontend/src/routeTree.gen.ts`
  modificado (356 líneas) *antes* de este batch, por una sesión previa que corrió el generador sin
  comitear — confirmado con `git diff --stat` antes de tocar nada: es *solo* reordenamiento
  alfabético de imports/rutas ya existentes (el generador actual ordena distinto que la versión que
  generó el archivo comiteado), cero rutas agregadas o quitadas. La regeneración de esta tarea corre
  el mismo generador sobre el mismo árbol de rutas más la ruta nueva de 5.2, así que el resultado es
  **estrictamente aditivo** sobre ese diff pre-existente (mismo reordenamiento + la ruta nueva), no
  un revert de trabajo ajeno — no había ninguna ruta pendiente de otro cambio que perder.
- [x] 5.4 Verificación: `pnpm --filter frontend typecheck` (o `tsc --noEmit`) sin errores sobre los
  archivos nuevos; si el proyecto tiene tests de cliente HTTP (mock de `fetch`), agregar uno por
  función siguiendo el patrón existente para `extracciones.ts`, si lo hay.
  **Evidencia**: no existe script `typecheck` en `package.json`; se corrió `tsc -b --noEmit`
  (equivalente real, mismo binario que usa `build`) → exit code 0, sin output, cero errores sobre
  los 3 archivos nuevos. `extracciones.ts` **no tiene** archivo de test (`extracciones.test.ts` no
  existe en el repo); el patrón real de testing de cliente HTTP sí existe en
  `frontend/src/lib/api/pcp.test.ts` (mock de `./presupuestacion` vía `vi.mock`, assertions con
  `toHaveBeenCalledWith` sobre la ruta y el `init` exactos) — se siguió **ese** patrón (más cercano
  y más simple que necesitar mockear `supabase` también, que `pcp.test.ts` hace solo porque
  `pcp.ts` importa `supabase` directo para otra función; `ocMatching.ts` no lo hace). Se creó
  `frontend/src/lib/api/ocMatching.test.ts` con 6 tests (uno por función, más un caso adicional de
  `obtenerMatching` con/sin `presupuestoId`). **RED confirmado de verdad, no retroactivo**: se movió
  `ocMatching.ts` a `.bak` y se corrió `pnpm test -- ocMatching` → `Failed to resolve import
  "./ocMatching"` (fallo de colección, ningún test corrido) con el resto de la suite intacta (27
  test files / 199 tests preexistentes en verde). Se restauró el archivo y se corrió de nuevo →
  **GREEN**: 28 test files / 205 tests (199 baseline + 6 nuevos), sin regresiones.
  `pnpm test` completo (suite entera) confirmado en verde después, mismo resultado.

## Phase 6: Frontend — sincronización de tipos + navegación automática (D10)

> Depende de Phase 5: la ruta `/ordenes-compra/$ordenCompraId/matching` ya existe y está registrada
> en `routeTree.gen.ts`, así que `navigate({ to: ... })` tipa correctamente contra ella. No depende
> de Phases 2-4 en el sentido de contrato — el backend ya expone `orden_compra_id` desde antes de
> este cambio (C7).

- [x] 6.1 [RED] En `frontend/src/features/validar-extraccion/ValidarExtraccionDetalle.test.tsx`,
  agregar el caso nuevo (spec `orden-compra-validacion` § "Confirmar una orden de compra navega a la
  pantalla de matching"): mock de la mutación resolviendo con `orden_compra_id` no nulo → afirma
  `navigate` llamado con `{ to: '/ordenes-compra/$ordenCompraId/matching', params: { ordenCompraId }
  }`. **El test existente que afirma la navegación al listado se extiende, no se reemplaza**
  (spec § "Confirmar una licitación o comparativa no cambia su navegación"): agregar el caso
  explícito con `orden_compra_id: null` → sigue navegando a `/validar-extraccion`. Confirmar RED:
  el mock de la respuesta no tiene el campo/tipo todavía, o el componente no lee la rama nueva.
  **Evidencia**: nuevo `describe('ValidarExtraccionDetalle — navegación tras confirmar (D10)')` con
  2 tests. **Desviación honesta respecto de la instrucción literal**: `rg navigateMock` sobre el
  archivo confirmó que `navigateMock` estaba declarado pero **nunca aserteado** por ningún test
  preexistente — no existía ningún test que afirmara la navegación al listado para "extender". El
  caso `orden_compra_id: null` es, en los hechos, el primer test de navegación del archivo, no una
  extensión literal de uno preexistente (documentado en un comentario dentro del propio test file).
  Ambos casos se ejercitan sobre el flujo ya estable de `orden_compra` (stubs de
  `OrdenCompraSelector`/`CabeceraOrdenCompra` ya establecidos), variando solo el `orden_compra_id`
  que la mutación mockeada resuelve — la rama de `onSuccess` decide únicamente por ese campo, no por
  `document_type` (D10), así que cubre el contrato real sin necesitar manejar el `<select>` real de
  `ProcesoComercialSelector`. **RED confirmado de verdad**: `npx vitest run -- ValidarExtraccionDetalle`
  antes de 6.2/6.3 → `1 failed | 27 passed (28)` / `1 failed | 206 passed (207)`; la única falla es el
  caso `orden_compra_id` no nulo (`navigateMock` nunca llamado con la ruta de matching, porque
  `onSuccess` todavía no toma el resultado); el caso `null` ya pasaba de entrada porque el
  comportamiento actual (navegar siempre al listado) coincide con ese caso.
- [x] 6.2 [GREEN] Modificar `frontend/src/lib/api/extracciones.ts`: agregar a la interfaz
  `ResultadoValidarExtraccion` los 4 campos que el backend ya devuelve (C7) —
  `orden_compra_id: string | null`, `entregas_creadas: number`, `renglones_sin_producto: number`,
  `extracciones_validadas: number` — con el comentario de sincronización contra
  `extraccion/models.py:94-107`. Agregar `orden_compra_id: string | null` a la interfaz
  `ExtraccionResumen` (D11, espejo de 4.3).
  **Evidencia**: rango exacto verificado leyendo el archivo real (`grep -n "class
  ResultadoValidarExtraccion" -A 20 services/presupuestacion/extraccion/models.py`): la clase vive en
  líneas 94-107 (coincide con la cita de C7/D10 de `design.md`, sin desvío). Los 4 campos agregados
  con el comentario de sincronización. Se confirmó también que `ExtraccionResumen` (backend, líneas
  110-131) **ya** tiene `orden_compra_id` desde Phase 4 (D11) — el hueco real era solo el espejo TS,
  que a su vez **tampoco** lo tenía todavía en `extracciones.ts` (gap de Phase 4 sobre el frontend,
  no señalado en su momento porque Phase 4 fue puramente backend); se cierra acá porque tasks.md ya
  asignaba explícitamente esa línea a esta tarea. Efecto colateral de hacer el campo **requerido**
  (no opcional, mismo estilo que el resto de la interfaz): 2 fixtures `ExtraccionResumen` literales
  en `ValidarExtraccionListado.test.tsx` (`OC_1`) necesitaron el campo para seguir tipando —
  agregado con `orden_compra_id: null` y un comentario que aclara que Phase 8 es quien consume ese
  campo, fuera del alcance de esta tarea (mecánico, no cambia comportamiento).
- [x] 6.3 [GREEN] Modificar `frontend/src/features/validar-extraccion/ValidarExtraccionDetalle.tsx`:
  el `onSuccess` de la mutación (líneas 81-85 actuales) lee `resultado.orden_compra_id`; si no es
  `null`, navega a `/ordenes-compra/$ordenCompraId/matching` con el id; si es `null`, mantiene
  `navigate({ to: '/validar-extraccion' })` sin cambios.
  `pnpm --filter frontend test -- ValidarExtraccionDetalle` → confirmar GREEN.
  **Evidencia**: `onSuccess` pasa a tomar `resultado` como parámetro y aplica el `if` de D10,
  transcripción literal del snippet de `design.md` D10. `npx vitest run -- ValidarExtraccionDetalle`
  → `28 passed (28)` / `207 passed (207)`. Comando literal `pnpm --filter frontend test` no está
  disponible tal cual (mismo hallazgo de Phase 5: no hay `pnpm` en el PATH del entorno, y el
  `package.json` de `frontend/` no tiene workspaces de pnpm — se corrió `npx vitest run` directo
  desde `frontend/`, equivalente real al script `"test": "vitest run"` de `package.json`).
- [x] 6.4 [REFACTOR] Correr la suite completa de `validar-extraccion` (`pnpm --filter frontend test
  -- validar-extraccion`) y confirmar que licitación/comparativa no tienen regresiones.
  **Evidencia**: `npx vitest run -- validar-extraccion` → `28 passed (28)` / `207 passed (207)` —
  el filtro por patrón de archivo matcheó los 28 archivos porque **son todos** los test files del
  proyecto (confirmado corriendo `npx vitest run` sin filtro: mismo resultado exacto, `28 passed
  (28)` / `207 passed (207)`), no hay señal de que el filtro haya sido un no-op silencioso. Sin
  regresiones en licitación/comparativa ni en ningún otro feature. `npx tsc -b --noEmit` desde
  `frontend/` → exit code 0, cero errores — confirma que la secuencia Phase 5→6 (adelantar la ruta
  en Phase 5 para que el `navigate({ to: ... })` de esta fase tipara) funcionó como estaba
  diseñado. `git diff --stat` acotado a `frontend/src`: 4 archivos, +119/-1 líneas (dentro del
  presupuesto de revisión de 400 líneas para este work unit, PR 6 de 9).

## Phase 7: Frontend — pantalla de matching (`oc-matching/`)

> Depende de Phase 5 (cliente HTTP + tipos) y Phase 3 (contrato real de los 5 endpoints).

- [x] 7.1 [RED] Crear `frontend/src/features/oc-matching/components/RenglonOcFila.test.tsx`: un
  candidato → botón "Confirmar" habilitado y **nada preseleccionado** (spec § "Un único match de
  precio se sugiere sin vincularse"); varios candidatos → lista ordenada por similitud, **sin
  preselección** (spec § "Varios matches del mismo precio se ordenan..."); cero candidatos → estado
  `pendiente` visible, sin bloquear la fila. Confirmar RED: el componente no existe.
  **Evidencia**: 5 tests (los 3 pedidos + `confirmado` y `sin_presupuesto` para cubrir los 3 estados
  derivados de D4). RED confirmado de verdad: `npx vitest run -- oc-matching` antes de 7.5-7.10 →
  `4 failed` (los 4 archivos nuevos, `Failed to resolve import` de cada componente/módulo), `28
  passed` preexistentes intactos.
- [x] 7.2 [RED] Crear `frontend/src/features/oc-matching/components/AvisoReutilizacion.test.tsx`:
  aparece con `renglones_oc_vinculados >= 2` o `cantidad_vinculada > cantidad_ofertada` (D5); **nunca
  deshabilita** el botón de confirmar (spec § "Relación N:1 permitida, con aviso no bloqueante").
  **Evidencia**: 4 tests — sin aviso con 1 vínculo y sin exceso; aparece por reutilización; aparece
  por exceso de cantidad con un solo vínculo; un botón vecino renderizado junto al aviso sigue
  habilitado (afirma literalmente el "nunca deshabilita", no solo la ausencia de un atributo propio).
- [x] 7.3 [RED] Crear `frontend/src/features/oc-matching/components/SelectorPresupuesto.test.tsx`: el
  presupuesto sugerido se muestra primero pero **no viene elegido** (spec § "Selección explícita del
  presupuesto por el usuario", incluso con un único candidato); estado vacío distingue "sin
  presupuestos para este cliente" de "tiene N, ninguno coincide" (spec § "Estado explícito cuando el
  cliente no tiene presupuestos cargados").
  **Evidencia**: 3 tests — único candidato sugerido sin radio marcado; un click reporta la elección
  al padre vía callback sin auto-marcarse (el componente no guarda estado propio de elección, D8: la
  elección vive en la URL, la resuelve el container, no este componente); los dos estados vacíos
  distinguidos con `rerender`.
- [x] 7.4 [RED] Crear `frontend/src/features/oc-matching/OcMatchingDetalle.test.tsx`: una mutación
  por click (spec § "Confirmar un renglón no exige confirmar los demás primero"); tras cada
  mutación, `setQueryData` reemplaza la cache con el `MatchingOut` devuelto, **sin refetch** (D13);
  confirmar el vínculo de un renglón no toca el estado de los demás (spec § "Confirmar un renglón no
  exige confirmar los demás primero", los demás "permanecen sin cambios, disponibles para
  confirmarse en cualquier momento posterior").
  `pnpm --filter frontend test -- OcMatchingDetalle RenglonOcFila AvisoReutilizacion
  SelectorPresupuesto` → confirmar RED (componentes/módulo inexistente) antes de 7.5.
  **Evidencia**: 3 tests de integración del container (mock de `@/lib/api/ocMatching` y de
  `@tanstack/react-router::useNavigate`, mismo patrón `renderConQueryClient` que
  `ValidarExtraccionDetalle.test.tsx`) — confirmar dispara una sola mutación y dispara `obtenerMatching`
  una única vez en total (afirma el "sin refetch" contando llamadas, no solo el contenido final);
  deshacer ídem; descartar no exige confirmar el otro renglón primero (el segundo renglón sigue con
  su botón "Confirmar" disponible tras descartar el primero). Comando literal
  `pnpm --filter frontend test` no está disponible en este entorno (mismo hallazgo que Phases 5/6: sin
  `pnpm` en PATH) — se usó `npx vitest run -- oc-matching`, equivalente real.
- [x] 7.5 [GREEN] Crear `frontend/src/features/oc-matching/components/ColumnaPresupuesto.tsx`:
  columna izquierda — descripción/cantidad/precio/estado por `RenglonPresupuesto`, integra
  `AvisoReutilizacion` por fila cuando corresponde.
  **Evidencia**: también resalta (borde `navy`) las filas cuyo `presupuesto_item_id` aparece entre los
  `candidatos` del renglón de OC actualmente seleccionado (proposal.md § "Click en un renglón de OC
  resalta el o los candidatos del lado del presupuesto") — sin test dedicado (fuera del alcance
  explícito de 7.1-7.4), documentado acá para que quede trazable y no se descubra como comportamiento
  no probado más adelante.
- [x] 7.6 [GREEN] Crear `frontend/src/features/oc-matching/components/AvisoReutilizacion.tsx`: aviso
  suave, nunca deshabilita nada (implementación que satisface 7.2).
  **Evidencia**: componente puro sin botones propios — estructuralmente no puede deshabilitar nada
  ajeno; retorna `null` cuando ninguna de las dos condiciones de D5 se cumple.
- [x] 7.7 [GREEN] Crear `frontend/src/features/oc-matching/components/ColumnaOrdenCompra.tsx`:
  columna derecha — un `RenglonOcFila` por renglón de OC.
  **Evidencia**: recibe `renglonSeleccionadoId`/`isPending` del container y las 4 callbacks
  (`onSeleccionar`/`onConfirmar`/`onDeshacer`/`onDescartar`), curriándolas con el `oc_item_id` de cada
  fila antes de pasarlas a `RenglonOcFila`.
- [x] 7.8 [GREEN] Crear `frontend/src/features/oc-matching/components/RenglonOcFila.tsx`: estado +
  candidatos + botones "Confirmar" / "Deshacer" / "No está en el presupuesto" (implementación que
  satisface 7.1).
  **Evidencia**: los 3 estados derivados de D4 (`pendiente`/`confirmado`/`sin_presupuesto`) se
  renderizan por rama exclusiva; dentro de `pendiente`, 0/1/N candidatos son 3 sub-ramas distintas
  (párrafo informativo / botón directo / `fieldset` de radios sin preseleccionar, mismo patrón que
  `OrdenCompraSelector` para CUIT compartido). Único estado local propio: el candidato radio elegido
  (`useState`), acorde a que ese es un detalle de UI de la fila, no el estado global del container que
  `design.md` D12 reserva para el renglón de OC resaltado.
- [x] 7.9 [GREEN] Crear `frontend/src/features/oc-matching/components/SelectorPresupuesto.tsx`: lista
  de candidatos rankeados, click resalta pero no confirma (implementación que satisface 7.3).
  **Evidencia**: sin estado propio de elección — el `checked` de cada radio compara directamente
  contra el prop `presupuestoIdSeleccionado` que controla el container (D8: la elección vive en la
  URL, nunca en estado local de React, alternativa (b) de D8 rechazada explícitamente en `design.md`).
- [x] 7.10 [GREEN] Crear `frontend/src/features/oc-matching/OcMatchingDetalle.tsx`: container — 2
  queries (`presupuestos-candidatos`, `matching`), 3 mutaciones (`confirmarVinculo`,
  `deshacerVinculo`, `descartarRenglon`), estado de `renglonSeleccionadoId` (`useState`),
  `presupuestoId` leído del search param de la ruta (D8). Cada mutación hace `setQueryData` con el
  `MatchingOut` completo devuelto — sin refetch (D13). **Sin hook propio tipo `useFilasEditables`**
  (el estado local es solo un id seleccionado, D12/forma del frontend de `design.md`).
  `pnpm --filter frontend test -- OcMatchingDetalle RenglonOcFila AvisoReutilizacion
  SelectorPresupuesto` → confirmar GREEN.
  **Evidencia**: `matchingQueryKey` compartida entre el `useQuery` y las 3 `onSuccess` de mutación
  (mismo array literal recalculado por render, TanStack Query lo serializa — no requiere memoización
  para que `setQueryData` pegue en la cache correcta). Elegir un presupuesto en `SelectorPresupuesto`
  navega (`useNavigate` genérico, mismo hook que `ValidarExtraccionDetalle.tsx`) actualizando el
  search param `presupuesto` con `replace: true` — sin test dedicado (D8 exige que la elección viva en
  la URL, no en estado local; la función existe para cumplir esa restricción aunque 7.4 no pida
  probarla explícitamente, documentado acá por la misma razón que 7.5). El placeholder de la ruta
  (`_authenticated.ordenes-compra.$ordenCompraId.matching.tsx`, Phase 5) se reemplazó por
  `<OcMatchingDetalle ordenCompraId={ordenCompraId} presupuestoId={presupuesto} />` sin tocar
  `Route.useParams()`/`Route.useSearch()`. `npx vitest run -- oc-matching` → `32 passed (32)` / `222
  passed (222)` (207 baseline de Phase 6 + 15 nuevos: 5+4+3+3).
- [x] 7.11 [REFACTOR] Correr `pnpm --filter frontend test -- oc-matching` (toda la carpeta) y
  confirmar que ningún otro feature (validar-extraccion, terceros, etc.) tiene regresiones:
  `pnpm --filter frontend test`.
  **Evidencia**: `npx vitest run` (suite completa, sin filtro) → `32 passed (32)` / `222 passed (222)`
  — mismo resultado exacto que el filtro `-- oc-matching`, confirmando que los 32 archivos del
  proyecto son todos los test files (ningún feature fuera de `oc-matching` quedó sin correr). `npx tsc
  -b --noEmit` → exit 0, sin output, cero errores. `git diff --stat` acotado a `frontend/src`: 11
  archivos, +938/-15 líneas.
  **Nota sobre presupuesto de revisión (400 líneas)**: el forecast de `tasks.md` ya preveía esta
  unidad como "la fase frontend más grande" (nota de la invocación) dentro de una cadena
  `feature-branch-chain` de 9 PRs con ~3.200 líneas totales, no 400 por PR — el propio § Review
  Workload Forecast fija `400-line budget risk: High` y `Chained PRs recommended: Yes` para el cambio
  completo, con esta unidad (PR 7) ya identificada como el trabajo cohesivo de construir la pantalla
  completa (container + 5 componentes + arnés de test nuevo para el directorio) en un solo lote. No se
  fragmentó artificialmente ni se recortaron tests/comentarios para bajar el número.
  **`size:exception` recomendado para PR 7**: 953 líneas autoradas (938+15) superan el guardrail
  genérico de 400 líneas por unidad. Partir esta unidad en sub-PRs (p. ej. componentes de presentación
  en un PR y el container en otro) fragmentaría una sola pantalla cohesiva a mitad de su primer commit
  usable — ningún componente de `oc-matching/` tiene consumidores fuera de este directorio todavía, así
  que un corte intermedio dejaría un PR sin pantalla funcional que revisar. Recomendación: aceptar
  `size:exception` para PR 7, igual que se preveía en el propio forecast de `tasks.md` para las fases
  de mayor superficie de esta cadena.

## Phase 8: Frontend — re-entrada: sección "Órdenes de compra validadas" (D11)

> Depende de Phase 5 (la ruta de matching ya existe para armar el link). Independiente de Phase 7 en
> el sentido de compilación, pero sin Phase 7 el link no tiene destino útil que probar manualmente.

- [x] 8.1 [RED] En `frontend/src/features/validar-extraccion/ValidarExtraccionListado.test.tsx` (o
  crearlo si no existe), test de la sección nueva: dado el listado con `{ validado: true, limit: 50
  }` filtrado a `document_type === 'orden_compra'` en el cliente, cada fila muestra un link a
  `/ordenes-compra/$ordenCompraId/matching` usando el `orden_compra_id` de `ExtraccionResumen`
  (6.2/4.3); una fila con `orden_compra_id: null` (miembro no-ancla de un grupo, D11) **no** muestra
  link roto — se omite o se muestra sin acción, documentado explícitamente en el test. Confirmar
  RED: la sección no existe todavía.
  **Evidencia**: el archivo ya existía (Phase 6, fixture mecánica en `OC_1`). Se agregó un
  `describe('ValidarExtraccionListado (D11) — sección "Órdenes de compra validadas"')` con 4 tests:
  (a) query `{ validado: true, limit: 50 }` confirmada con `toHaveBeenCalledWith`, link con
  `href="/ordenes-compra/oc-abc/matching"`; (b) `orden_compra_id: null` → sin link de "Matching" en
  el documento — **se decidió mostrar sin acción** (convención ya establecida en `PendientesTable`
  para `proceso_comercial_nombre ?? '—'`: la fila se muestra igual, con `—` en la celda de acción, en
  vez de ocultar toda la fila); (c) filtro cliente `document_type === 'orden_compra'` — una
  `licitacion` validada no aparece en la sección; (d) sin órdenes validadas, la sección no muestra
  ningún link (test de base, trivialmente verde antes y después, incluido para dejar la ausencia de
  regresión explícita). **Dos cambios de infraestructura del propio archivo de test, necesarios para
  que (a)/(b) pudieran afirmar algo real**: (1) el mock de `Link` de `@tanstack/react-router`
  (`<a>{children}</a>`, sin `href`) no permitía verificar destino — se reemplazó por una versión que
  propaga `to`/`params` a `href` sustituyendo los literales `$parametro`, mismo criterio que el único
  precedente real del repo que ya lo hacía (`LoginForm.test.tsx`); no rompe los tests preexistentes
  de "Revisar" en `PendientesTable`, que nunca aserteaban `href`. (2) la factory
  `mockListarExtracciones({ pendientes, validadas })` reemplaza el `mockResolvedValue` plano
  (que servía la misma lista a **ambas** queries, `validado: false` y `validado: true`) por un
  `mockImplementation` que distingue por `params.validado` — sin esto, el test 7.13 (que ya
  sobrescribía el mock con OCs agrupadas) habría duplicado `oc1.pdf`/`oc2.pdf` en la sección nueva y
  roto sus propios `getByText`. El test de 7.13 se migró a la factory (`mockListarExtracciones({
  pendientes: [...] })`) sin cambiar su aserción original. **RED confirmado**: `npx vitest run --
  ValidarExtraccionListado` antes de 8.2 → `3 failed | 223 passed (226)` — las 3 fallas son
  exactamente los tests (a)/(b)/(c) (timeout de `waitFor` esperando texto que no existe porque la
  sección no está renderizada todavía); el cuarto test D11 ya pasaba de entrada (nada que romper con
  la sección ausente) y los 223 tests preexistentes del proyecto quedaron intactos.
- [x] 8.2 [GREEN] Modificar `frontend/src/features/validar-extraccion/ValidarExtraccionListado.tsx`:
  agregar la segunda query `{ validado: true, limit: 50 }` junto a la existente `{ validado: false }`
  (línea 52 actual), filtrar `document_type === 'orden_compra'` en el cliente, renderizar la sección
  "Órdenes de compra validadas" con el link de re-entrada por fila.
  `pnpm --filter frontend test -- ValidarExtraccionListado` → confirmar GREEN.
  **Evidencia**: `OC_VALIDADAS_KEY = ['extracciones', { validado: true, limit: 50 }]` (query key
  separada, sin colisión con `EXTRACCIONES_KEY`); `validadasQuery` con el mismo patrón
  `isPending`/`isError`/`data` que la query existente; `ordenesCompraValidadas` filtra
  `document_type === 'orden_compra'` en el cliente (D11: el backend no expone ese filtro en
  `/extracciones`). Se creó `frontend/src/features/validar-extraccion/components/ValidadasTable.tsx`
  (58 líneas) siguiendo el mismo patrón de `PendientesTable.tsx` (una tabla por sección, mismo estilo
  de celdas) — el link usa `<Link to="/ordenes-compra/$ordenCompraId/matching" params={{
  ordenCompraId: extraccion.orden_compra_id }}>` cuando el campo no es `null`, y un `—` (mismo
  glifo que `proceso_comercial_nombre ?? '—'`) cuando sí lo es. Comando literal `pnpm --filter
  frontend test` no disponible en este entorno (mismo hallazgo que Phases 5-7: sin `pnpm` en PATH) —
  se corrió `npx vitest run -- ValidarExtraccionListado` → `226 passed (226)` (el filtro por patrón
  matchea los 32 archivos del proyecto, mismo comportamiento ya documentado en Phases 5-7: no hay
  señal de que sea un no-op silencioso, es el total real). Sin regresiones sobre ninguno de los 223
  tests preexistentes.
- [x] 8.3 [REFACTOR] Correr `pnpm --filter frontend test -- validar-extraccion` completo y confirmar
  que el listado de pendientes (`{ validado: false }`) no tiene regresiones.
  **Evidencia**: `npx vitest run -- validar-extraccion` → `32 archivos / 226 passed (226)` — mismo
  resultado exacto que sin filtro (`npx vitest run`, corrido también, idéntico `226 passed (226)`),
  confirmando una vez más que el filtro por patrón no reduce la superficie real. `npx tsc -b
  --noEmit` desde `frontend/` → exit code 0, sin output, cero errores. `git diff --stat` acotado a
  `frontend/src` (archivos trackeados): 2 archivos, +142/-8 líneas; más el archivo nuevo
  `ValidadasTable.tsx` (58 líneas, sin trackear hasta el commit) → ~200 líneas autoradas totales,
  dentro del presupuesto de revisión de 400 líneas para este work unit (PR 8 de 9). Ningún test del
  listado de pendientes (`{ validado: false }`, agrupar/desagrupar, indicador de grupo persistido)
  cambió de resultado.

## Phase 9: Documentación + verificación integral (tracker → `dev`)

- [ ] 9.1 Revisar que `docs/schema/extractor_final.sql` (actualizado en 1.6) sigue reflejando la base
  viva tras las Fases 2-8 (ningún cambio de esquema adicional se agregó fuera de la migración 0026).
- [ ] 9.2 Correr la suite completa de backend: `pytest tests/ --cov=services` — confirmar 0
  regresiones fuera de `tests/oc_presupuesto/` y `tests/extraccion/` (cambios de esta fase), y
  cobertura razonable sobre el módulo nuevo.
- [ ] 9.3 Correr build + tests completos de frontend: `pnpm --filter frontend build` y `pnpm
  --filter frontend test` — confirmar 0 regresiones fuera de `oc-matching/` y `validar-extraccion/`.
- [ ] 9.4 Verificar manualmente, contra el proyecto Supabase de test, el checklist completo de
  Success Criteria de `proposal.md` (9 ítems: navegación automática, ranking por coincidencias,
  sugerencia única no auto-confirmada, desempate sin preselección, `pendiente` no bloqueante,
  herencia de `producto_id`, N:1 con aviso, `estado_matching`/`confianza_matching` sin modificar,
  caso real SAMCo Rafaela reproducido como test) y dejar registrada la evidencia de cada uno (test
  que lo cubre o verificación manual).

---

## Notas de trazabilidad (spec → tarea)

| Capability / Requirement | Cubierto en |
|---|---|
| `oc-presupuesto-candidato` § Ranking por coincidencia exacta | 2.2, 2.9, 2.12 |
| `oc-presupuesto-candidato` § Selección explícita del usuario | 2.2, 7.3, 7.9 |
| `oc-presupuesto-candidato` § Estado sin presupuestos | 2.3, 7.3 |
| `oc-presupuesto-vinculacion` § Sugerencia por precio + desempate | 3.2, 3.11, 7.1, 7.8 |
| `oc-presupuesto-vinculacion` § Confirmación granular obligatoria | 3.4, 3.11, 7.1, 7.4, 7.8, 7.10 |
| `oc-presupuesto-vinculacion` § Herencia de `producto_id` | 3.3, 3.11 |
| `oc-presupuesto-vinculacion` § `pendiente` no bloqueante | 3.4, 7.1 |
| `oc-presupuesto-vinculacion` § N:1 con aviso | 3.7, 3.11, 7.2, 7.6 |
| `oc-presupuesto-vinculacion` § `estado_matching`/`confianza_matching` fuera de alcance | 3.8, 3.14 |
| `orden-compra-validacion` (delta) § Navegación automática | 6.1, 6.2, 6.3, 6.4 |

## Rollback (referencia rápida)

Orden documentado en `proposal.md` § Rollback Plan y `design.md` § down migration:

1. Revertir frontend (Phases 5-8) primero — restaura `navigate({ to: '/validar-extraccion' })` y
   quita las rutas nuevas. A partir de ahí nadie puede crear vínculos nuevos.
2. Revertir backend (Phases 2-4) — quita los endpoints y el módulo `oc_presupuesto/`. El campo
   `orden_compra_id` puede quedarse (aditivo, nullable).
3. Revertir esquema (Phase 1) al final, con la down migration de 1.3 — exportar vínculos antes si la
   baja puede revertirse; `oc_items.producto_id` ya heredado **no se toca** nunca.
