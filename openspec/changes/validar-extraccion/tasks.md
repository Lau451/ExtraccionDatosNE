# Tasks: Validar extracción

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1600-1800 (backend prod ~420, backend tests ~280, docker-compose ~25, frontend prod ~750, frontend tests ~130, docs ~50) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 → PR3 → PR4 → PR5 (see Work Units) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending — user decision needed |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Focused test | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | `docker-compose.yml` volume+env fix (D4, hard prereq) | PR1 | N/A (infra) | `docker compose up`, confirm `extraction_results` persists and `GET /filas` resolves | revert compose diff alone; existing bug re-appears, no app code affected |
| 2 | Backend read path: `GET /extracciones`, `GET /filas`, `ExtraccionNoDisponibleError` | PR2 | `pytest tests/extraccion -k "not integration"`, `pytest tests/extraccion -m integration` | Docker (PR1) or local volume for `/filas` | revert router/repository/models additions; `POST /validar` untouched |
| 3 | Backend materialization override (`filas` body, D2/D3/D7) | PR3 | same as PR2 + `tests/extraccion/test_service.py` full suite (12 existing must stay green) | local pytest against test Supabase project | `filas` optional; reverting leaves CSV-only path (current behavior) |
| 4 | D6 notification fix (repository+service+conftest teardown) | PR4 | `pytest tests/extraccion -m integration -k notificar` | test Supabase project | revert leaves buggy-but-existing notify path (documented risk, not a regression) |
| 5 | Frontend screen + tests + docs | PR5 | `npm run test -- useFilasEditables`, `npm run test -- DocumentoDemasiadoGrande` | `vite dev` + real Chrome (never `npm run build`) | remove route + Sidebar entry; backend stays intact |

Chain strategy left `pending`: orchestrator must ask user (stacked-to-main vs feature-branch-chain vs size-exception) before `sdd-apply`, per `ask-on-risk`.

## Phase 1: Infra (D4) — hard prerequisite

- [x] 1.1 `docker-compose.yml`: add `volumes: extraccion-output` rw + `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` to `extraccion-api`; same volume `:ro` to `presupuestacion-api`; top-level `volumes:` block (design §5.1 exact diff).
- [ ] 1.2 Verify with real containers: `docker compose up`, confirm extraction persists and volume is readable/writable per side. **Deferred to Phase 8** (8.4) — avoids spinning up containers twice; end-to-end Docker pass covers this.

## Phase 2: Backend — error domain + `_leer_filas_csv`

- [x] 2.1 RED: `tests/extraccion/test_service.py` — `_leer_filas_csv(None)` and `OSError` (not just `FileNotFoundError`) raise `ExtraccionNoDisponibleError`.
- [x] 2.2 GREEN: `core/exceptions.py` add `ExtraccionNoDisponibleError` → 503; rewrite `_leer_filas_csv` in `service.py` per §5.2.

## Phase 3: Backend — read endpoints (D1)

- [x] 3.1 `models.py`: `ExtraccionResumen`, `FilasExtraccionOut` (§8.1/§8.2).
- [x] 3.2 `repository.py`: `listar_extracciones` (filtro `validado`, embed `procesos_comerciales(nombre)`).
- [x] 3.3 `router.py`: `GET /extracciones` — `require_roles(*_ROLES_LECTURA)`, `get_user_client()`.
- [x] 3.4 `router.py`: `GET /extracciones/{id}/filas` — mismo chequeo de pertenencia que `validar`; `editable=false`+`filas=[]` si `filas_leidas>500`.
- [x] 3.5 Integration: `validado=false` devuelve solo pendientes de la droguería (RLS).
- [x] 3.6 Integration: filas tipadas por `document_type` (licitación vs comparativa).
- [x] 3.7 Integration (threat matrix §12): `/filas` de otra droguería → 403 antes de `open()`.
- [x] 3.8 Integration: `csv_disk_path` NULL/inaccesible → 503 con `detail` de dominio, nunca 500.

## Phase 4: Backend — materialización con override (D2/D3/D7)

- [x] 4.1 `models.py`: `FilaLicitacionIn`, `FilaComparativaIn` (`extra="forbid"`), `MAX_FILAS_EDITABLES=500`, `filas: list[A]|list[B]|None` en `ValidarExtraccionRequest` (§2.1).
- [x] 4.2 RED: unit `_validar_filas_override` — tipo cruzado, vacía, no numérica, >500, acumulación multi-error (§3).
- [x] 4.3 GREEN: implementar `_validar_filas_override`, llamada antes de `_resolver_proceso_comercial_id` (primer write).
- [x] 4.4 RED: unit `_filas_a_materializar` — `None`→CSV, lista→lista (`tmp_path`, sin DB).
- [x] 4.5 GREEN: implementar `_filas_a_materializar`; `filas_override` en `_materializar_licitacion`/`_materializar_comparativa` (§2.2 diff).
- [x] 4.6 `router.py`: pasar `body.filas` a `validar_extraccion`.
- [x] 4.7 Integration: licitación con filas editadas → `items_proceso` refleja el body, no el CSV.
- [x] 4.8 Integration: comparativa con fila agregada → `ofertas_items` incluye el renglón nuevo, posiciones recalculadas.
- [x] 4.9 Integration: fila 47/80 inválida → 422, `validado=FALSE`, sin `proceso_comercial_id` ni `items_proceso` escritos (cero writes).
- [x] 4.10 Regresión: los 12 tests actuales de `test_service.py` corren SIN modificarse.

## Phase 5: Backend — D6 notificación de reemplazo (fix, no feature nueva)

- [x] 5.1 `repository.py`: `listar_usuarios_por_rol` + `.eq("activo", True)` + `excluir_id` opcional; **borrar** `crear_notificacion` (insert directo).
- [x] 5.2 `service.py`: mover `_notificar_reemplazo_comparativa` fuera de `_materializar_comparativa`, ejecutar después del flip `validado=TRUE`, envuelta en `try/except`; usar `notificaciones/service.py:crear_notificacion` con `tipo="comparativa_disponible"`, `relaciones={proceso_comercial_id, comparativa_id}`, `extraction_result_id` en `metadata` (§6.4).
- [x] 5.3 `tests/extraccion/conftest.py`: extender teardown — borrar `notificacion_entregas` por `notificacion_id` antes de `notificaciones`.
- [x] 5.4 Integration: reemplazo crea filas en `notificaciones` + `notificacion_entregas`; actor excluido; inactivos/otro rol/otra droguería no reciben nada.
- [x] 5.5 Integration: `crear_notificacion` monkeypatcheado a `raise` → response sigue 200, `validado=TRUE`.
- [x] 5.6 Integration: sin destinatarios elegibles → 200, sin notificación, sin excepción.

## Phase 6: Frontend

- [x] 6.1 `frontend/src/lib/api/extracciones.ts` (nuevo) — tipos + `listarExtracciones`, `obtenerFilasExtraccion`, `validarExtraccion`.
- [x] 6.2 `git mv` `NuevaLiciCotiDialog.tsx` de `carga-documentos/components/` a `validar-extraccion/components/`, sin editar imports. (mover por filesystem, no `git mv` — ver apply-progress)
- [x] 6.3 `ConfirmDialog.tsx`: agregar `pendingLabel` opcional (default actual `"Eliminando…"` preservado).
- [x] 6.4 `features/validar-extraccion/constants.ts` — `MAX_FILAS_EDITABLES = 500`.
- [x] 6.5 RED: Vitest `useFilasEditables` — diff modificadas/borradas/agregadas + `erroresPorCelda`.
- [x] 6.6 GREEN: `useFilasEditables.ts` (§9.2).
- [x] 6.7 `components/PendientesTable.tsx` + `ValidarExtraccionListado.tsx` (container, filtro `validado`, `staleTime: 0`).
- [x] 6.8 `components/CeldaEditable.tsx` + `TablaEditable.tsx` — grilla por `document_type`, Tab/Shift+Tab/Enter/Escape, `aria-invalid`+`aria-describedby` por celda.
- [x] 6.9 `components/ProcesoComercialSelector.tsx` — selector + `NuevaLiciCotiDialog` con `clase` derivada de `document_type`.
- [x] 6.10 RED: Testing Library — `row_count>500` no dispara fetch de `/filas`, renderiza estado bloqueado.
- [x] 6.11 GREEN: `components/DocumentoDemasiadoGrande.tsx` + gate en `ValidarExtraccionDetalle.tsx`.
- [x] 6.12 `components/ConfirmarValidacionDialog.tsx` — resumen N modificadas/borradas/agregadas + advertencia de reemplazo de comparativa vigente (D5).
- [x] 6.13 `ValidarExtraccionDetalle.tsx` — container: query filas + `useMutation` validar + `invalidateQueries(['extracciones'])` + navigate.
- [x] 6.14 `routes/_authenticated.validar-extraccion.index.tsx` + `.$extractionId.tsx` (2 rutas nuevas, patrón plano de `_authenticated.admin.usuarios.tsx`).
- [x] 6.15 `Sidebar.tsx` — reemplazar placeholder deshabilitado por entrada real a `/validar-extraccion`, tras "Carga de documentos".

## Phase 7: Docs

- [x] 7.1 `docs/modulos/extraccion_api/` — marcar `PATCH /api/extraction-results/{id}` y `GET /api/documentos/{doc_id}` como deprecados, con evidencia de que están rotos (columnas/tablas inexistentes).
- [x] 7.2 `docs/modulos/extraccion_validacion/casos_de_uso.md:63` — corregir: no hay relación entre `validar` y el PATCH.
- [x] 7.3 `docs/modulos/extraccion_validacion/pendientes.md` — agregar: gap `superadmin` fuera de `_ROLES_VALIDAR` (§14), materialización de comparativa no atómica entre statements (§4).

## Phase 8: Verificación end-to-end

- [x] 8.1 Chrome real vía `vite dev` (nunca `npm run build`): listado + filtro `validado`, tabla
      editable, editar celda, agregar/borrar fila con deshacer, confirmación con resumen,
      materialización real. Verificado con `c1002_compraagil.pdf` (extracción real, 48 filas):
      `POST /validar` → 200 → `validado=true` en DB → 48 filas en `items_proceso`. **Dos bugs
      reales encontrados y corregidos durante esta verificación** (no estaban cubiertos por los
      tests automatizados — ver sección siguiente).
- [ ] 8.2 Chrome real: reemplazo de comparativa vigente — advertencia visible antes de confirmar.
      NO verificado manualmente en browser (requiere setup de un proceso con comparativa vigente +
      nueva extracción tipo comparativa para el mismo proceso). Cubierto indirectamente por los 3
      tests de integración de la Fase 5 (5.4/5.5/5.6), que verifican el mecanismo a nivel DB.
- [ ] 8.3 Chrome real: `row_count>500` — edición bloqueada. NO verificado manualmente (requeriría
      generar un documento de prueba de >500 filas). Cubierto por los 2 tests Vitest de la Fase 6
      (6.10/6.11), que verifican el gate exacto.
- [ ] 8.4 Docker real (`docker compose up`) — **no disponible en este entorno** (sin Docker CLI en
      la sesión de esta verificación). Se validó en su lugar que `docker-compose.yml` parsea como
      YAML válido y coincide exactamente con el diff de design.md §5.1 (volumen `extraccion-output`
      rw en `extraccion-api`, ro en `presupuestacion-api`, envs de Supabase agregados). La
      verificación real con contenedores queda pendiente para cuando el usuario la corra.

### Bugs encontrados y corregidos durante 8.1 (no cubiertos por tests automatizados)

1. **La tabla nunca se poblaba.** `useFilasEditables` inicializaba su estado con
   `useState(() => filasOriginales.map(...))` — un inicializador lazy que corre una sola vez. Como
   el hook se llama antes de que `GET /filas` resuelva, ese primer render veía `filasOriginales=[]`
   y el estado quedaba congelado vacío para siempre, aunque las filas reales llegaran después. Fix:
   `useEffect` sincronizando el estado cuando `filasOriginales` deja de ser `undefined`.
2. **Ese primer fix causó un loop infinito de renders.** El caller pasaba
   `filasQuery.data?.filas ?? []` — el `?? []` crea un array nuevo en cada render mientras la query
   está pendiente, así que el `useEffect` (dependiente de esa referencia) se disparaba sin parar.
   Fix: el hook acepta `undefined` explícitamente (no default en el caller) y usa la referencia
   estable de React Query como dependencia real.
3. **"Borrar" no tenía forma de deshacerse.** El hook ya soportaba el toggle
   (`_borrada: !fila._borrada`), pero `TablaEditable` filtraba las filas borradas del render antes
   de que el usuario pudiera volver a hacer click. Fix: se muestran todas las filas; las borradas
   quedan tachadas, deshabilitadas, con botón "Deshacer".

**Nota de proceso:** los tres bugs pasaron los 26 tests de Vitest sin ser detectados — ninguno
ejercía el camino real de "React Query resuelve async → el hook recibe datos reales". Los tests
mockeaban `obtenerFilasExtraccion` con `mockResolvedValue` sincrónico dentro del mismo tick, lo cual
no reproduce la condición de carrera del primer bug ni el loop del segundo. Solo aparecieron al
probar contra el backend real en el browser.
