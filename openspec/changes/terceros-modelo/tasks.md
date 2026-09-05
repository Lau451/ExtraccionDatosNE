# Tasks: Modelo de terceros

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~3000-4000 (migration ~750, shared core ~150, 4 subdomains ~250 each, consumers ~200, imports+RPC ~250, tests ~1500+) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 → PR3 → PR4 → PR5 (per design's cut) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

Assumption: chain strategy was not explicit in the pre-proposal (only delivery strategy `auto-chain`
and the 5-PR cut were confirmed). `stacked-to-main` is used because each PR in the design's cut merges
independently and in order (schema → identidad/catálogos → direcciones/contactos → consumers →
imports), matching design.md's stated sequencing.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Migration (M0-M10) + `services/shared/` extraction | PR1 | `pytest tests/ -k presupuestacion_core` | `supabase db push` against test project | `.down.sql` + revert shim commits; safe while new tables empty |
| 2 | `terceros/identidad` + `terceros/catalogos` | PR2 | `pytest tests/terceros/identidad tests/terceros/catalogos` | FastAPI `TestClient` against test project | Revert PR2; router not wired into `main.py` until this PR's last task |
| 3 | `terceros/direcciones` + `terceros/contactos` | PR3 | `pytest tests/terceros/direcciones tests/terceros/contactos` | FastAPI `TestClient` | Revert PR3; independent of PR4/PR5 |
| 4 | Consumer adaptation (`clientes/`, `catalogo/`, `extraccion/routers/clientes.py`) | PR4 | `pytest tests/test_clientes_api.py tests/catalogo/` | FastAPI `TestClient` + `GET /clientes` smoke | Revert PR4; PR1-3 remain valid standalone |
| 5 | `imports/` + RPC + docs/handoff | PR5 | `pytest tests/imports/` | Run legacy CSV import twice against test project, assert row counts | Revert PR5; RPC has no other caller |

## Phase 1: Schema Migration (PR1)

- [x] 1.1 Create `supabase/migrations/0008_terceros_modelo.sql`; M0 Postgres `>=15` version guard.
- [x] 1.2 M1: `sectores_contacto`, `condiciones_pago`, `formas_pago` tables + tenant FK/uniques.
- [x] 1.3 M2: `terceros` table + `uq_terceros_cuit` partial index + `idx_terceros_drog_activo`.
- [x] 1.4 M3: `terceros_legacy_map` table + `uq_tlm_codigo`.
- [x] 1.5 M4: `DROP VIEW` for the 5 dependent views (blocking step before M5).
- [x] 1.6 M5: `ALTER TABLE clientes`/`proveedores` — drop columns, add FKs to `terceros`/`condiciones_pago`/`formas_pago`.
- [x] 1.7 M6: `tercero_direcciones` + `direccion_usos` + `uq_du_principal` partial index.
- [x] 1.8 M7: `terceros_contactos` + `uq_tc_principal` partial index; `DROP TABLE cliente_contactos`.
- [x] 1.9 M8: recreate the 9 views `WITH (security_invoker = true)` reading `terceros`/`condiciones_pago.plazos_dias`. Corrected post-apply: `pg_get_viewdef` against the live DB found 4 more views design.md missed (`v_formato_para_prompt`, `v_presupuesto_comercial`, `v_calendario`, `v_compras_vs_cotizado`) — added to M4/M8 in both `.sql` and `.down.sql` before applying.
- [x] 1.10 M9: `trg_set_updated_at`, RLS + policies (D6 union roles) for the 8 new tables, `GRANT`, `NOTIFY pgrst`.
- [x] 1.11 M10: `upsert_terceros_legacy` RPC (no `SECURITY DEFINER`) + `REVOKE`/`GRANT`.
- [x] 1.12 Create `supabase/migrations/0008_terceros_modelo.down.sql` mirroring M1-M10 in reverse.
- [x] 1.13 Update `docs/schema/extractor_final.sql` and `docs/schema/rls_final.sql` snapshots.
- [x] 1.14 Apply to the test Supabase project (`grnamollopxdlstcpxhc`); confirm via `list_tables`/`get_advisors`. Applied by the orchestrator (had MCP access the apply sub-agent lacked) via `mcp__supabase__apply_migration`, after fixing the 4 missing views found above. `list_tables` confirms all 8 new tables exist and `cliente_contactos` is gone. `get_advisors(security)` flagged `upsert_terceros_legacy` for a mutable `search_path` — fixed live via `ALTER FUNCTION ... SET search_path = public, pg_temp` and in the migration source; remaining advisories (`es_superadmin`/`get_drogueria_id`/`get_rol`/`mismo_tenant` SECURITY DEFINER, leaked-password-protection) are pre-existing and unrelated to this change.
- [x] 1.15 Run the real `pytest` suite against this migration. `.env` was corrected (`SUPABASE_URL`/`SUPABASE_SERVICE_KEY` were a stale mix of a local Supabase demo key with a real remote `SUPABASE_ANON_KEY` for `grnamollopxdlstcpxhc` — user supplied the correct remote `service_role` key from the dashboard). Result: **398 passed, 27 failed, 16 errors**. Sampled failures confirm the design-predicted "known temporary breakage" (see `design.md`, Migration/Rollout): fixtures and consumer code in `tests/clientes/`, `tests/catalogo/`, `tests/imports/`, `tests/comparativas/`, `tests/matching/`, `tests/pricing/` still insert `clientes.nombre`/`proveedores.razon_social`, columns moved to `terceros` in M5 — expected until PR2/PR4/PR5 land. `tests/terceros/test_dependencias.py` failing is also expected (RED until `services/terceros/` exists). The only unrelated failure: 4 tests in `tests/usuarios/test_service.py` hit a `429 Too Many Requests` from Supabase Auth's invite endpoint — a pre-existing external rate-limit, not caused by this change.

## Phase 2: Shared Core Extraction (PR1, D5)

- [x] 2.1 Create `services/shared/__init__.py`. (already existed, empty — confirmed present)
- [x] 2.2 Move `config.py` logic to `services/shared/config.py`.
- [x] 2.3 Move `database.py` logic to `services/shared/database.py`.
- [x] 2.4 Move `exceptions.py` logic to `services/shared/exceptions.py`.
- [x] 2.5 Replace `services/presupuestacion/core/config.py` body with a reexport shim.
- [x] 2.6 Replace `services/presupuestacion/core/database.py` body with a reexport shim.
- [x] 2.7 Replace `services/presupuestacion/core/exceptions.py` body with a reexport shim.
- [x] 2.8 RED: `tests/terceros/test_dependencias.py` — no `.py` under `services/terceros/` imports `services.presupuestacion` (D5 guard, `ast`); fails until Phase 3 exists. Confirmed RED by direct invocation (pytest itself could not run in this session, see note on 2.9).
- [x] 2.9 Shim regression check. **`pytest` could not run at all in this session**: `tests/conftest.py`'s session-scoped `_bloquear_si_no_es_bd_de_test` fixture aborts collection unconditionally (even for non-integration tests) because this sandbox's `SUPABASE_URL` doesn't match the test project ref. Substituted with a static import check: `importlib.import_module(...)` on all 42 modules that import `presupuestacion.core.{config,database,exceptions}` (the ~20 estimated in the task, plus `main.py` and the `core/*` modules themselves) — all 42 imported cleanly against the new shim. Real `pytest` execution is still required before this PR merges.

## Phase 3: Terceros Identidad (PR2)

- [x] 3.1 Create `services/terceros/errors.py` with `asegurar_tercero_de_la_drogueria(...)` (D3 single guard).
- [x] 3.2 Create `services/terceros/identidad/models.py` (Tercero, ClienteRol, ProveedorRol).
- [x] 3.3 Create `services/terceros/identidad/repository.py` (CRUD over `terceros`/`clientes`/`proveedores`).
- [x] 3.4 RED: create tercero with `codigo_interno`+`nombre` succeeds.
- [x] 3.5 RED: duplicate `codigo_interno` in same drogueria raises `ConflictError`.
- [x] 3.6 RED: dual-role assignment creates `clientes` and `proveedores` rows sharing `id`.
- [x] 3.7 RED: single-role assignment does not create the other role row.
- [x] 3.8 RED: duplicate role assignment raises `ConflictError`.
- [x] 3.9 RED: `es_competidor`/`es_proveedor_compra` update leaves the cliente role unaffected.
- [x] 3.10 RED: tercero identity update leaves role rows unchanged.
- [x] 3.11 RED: deactivation sets `activo=false` and hides tercero from default listings (D4).
- [x] 3.12 RED: cross-tenant read raises `NotFoundError`, never `ValidationError`/`ForbiddenError` (D3).
- [x] 3.13 Create `services/terceros/identidad/service.py` implementing 3.4-3.12 (GREEN).
- [x] 3.14 Create `services/terceros/identidad/router.py` exposing tercero/role CRUD. Not wired into `main.py` yet (that's Phase 7, out of this batch's scope).
- [x] 3.15 REFACTOR: confirm the D3 guard is invoked exactly once per operation, no duplicate tenant checks. Verified by reading every service function: each calls `asegurar_tercero_de_la_drogueria` (directly or via `obtener_tercero`/`obtener_rol_cliente`/`obtener_rol_proveedor`) exactly once before mutating.
- [x] 3.16 **Post-verify fix** (`verify-report.md` CRITICAL finding: `terceros-identidad` spec scenario
  "Deactivation semantics apply consistently" was unimplemented). RED: added
  `test_desactivar_tercero_lo_oculta_de_clientes_y_proveedores_aunque_el_rol_siga_activo`
  (`tests/terceros/identidad/test_service.py`) — deactivates the tercero only (role rows stay
  `activo=true`) and asserts it disappears from `listar_clientes_con_tercero`/
  `listar_proveedores_con_tercero`. GREEN: `listar_clientes_con_tercero`/
  `listar_proveedores_con_tercero` (`services/terceros/identidad/repository.py`) now embed
  `terceros!inner(*)` (INNER JOIN instead of PostgREST's default LEFT JOIN embed) and add
  `.eq("terceros.activo", activo)` alongside the existing role-table `.eq("activo", activo)`
  filter, so the default `activo=True` filter requires both the role row AND the tercero itself
  to be active. `pytest tests/terceros -q` → 44 passed (43 prior + this test); `pytest
  tests/clientes tests/catalogo -q` → 28 passed, no regression in facade consumers.

## Phase 4: Catálogos Comerciales (PR2)

- [x] 4.1 Create `services/terceros/catalogos/models.py` (SectorContacto, CondicionPago, FormaPago).
- [x] 4.2 Create `services/terceros/catalogos/repository.py`.
- [x] 4.3 RED: entry from another drogueria never appears in a list (scoping).
- [x] 4.4 RED: `condiciones_pago.plazos_dias` stores multi-term `{30,60,90}` and single-term `{30}`.
- [x] 4.5 RED: deactivated entry disappears from default listing but stays FK-referenceable (D4).
- [x] 4.6 RED: each `listar_*` in this subdomain hides `activo=false` rows by default (D4).
- [x] 4.7 RED: cross-tenant catalog access raises `NotFoundError` (D3).
- [x] 4.8 Create `services/terceros/catalogos/service.py` implementing 4.3-4.7 (GREEN).
- [x] 4.9 Create `services/terceros/catalogos/router.py`.
- [x] 4.10 RED: habitual condición/forma de pago from another drogueria on a role row is rejected (`ValidationError`).
- [x] 4.11 Extend `services/terceros/identidad/service.py`/`router.py` with habitual condición/forma de pago FK endpoints (GREEN for 4.10).

## Phase 5: Terceros Direcciones (PR3)

- [x] 5.1 Create `services/terceros/direcciones/models.py` (TerceroDireccion, DireccionUso).
- [x] 5.2 Create `services/terceros/direcciones/repository.py`.
- [x] 5.3 RED: address creation for an existing tercero succeeds and scopes to its drogueria.
- [x] 5.4 RED: address for a nonexistent tercero raises `NotFoundError`.
- [x] 5.5 RED: assigning two simultaneous uses to one address both persist.
- [x] 5.6 RED: removing one use keeps the other and excludes the address from that use's filter.
- [x] 5.7 RED: filtering addresses by use returns only matching addresses.
- [x] 5.8 RED: editing address fields leaves use associations unchanged.
- [x] 5.9 RED: removing an address removes its use associations without deleting the tercero.
- [x] 5.10 RED: cross-tenant address access raises `NotFoundError` (D3).
- [x] 5.11 Create `services/terceros/direcciones/service.py` implementing 5.3-5.10 (GREEN).
- [x] 5.12 Create `services/terceros/direcciones/router.py`.

## Phase 6: Terceros Contactos (PR3)

- [x] 6.1 Create `services/terceros/contactos/models.py` (TerceroContacto).
- [x] 6.2 Create `services/terceros/contactos/repository.py`.
- [x] 6.3 RED: contact creation for a tercero with only the proveedor role succeeds and is retrievable.
- [x] 6.4 RED: full-field contact creation stores all fields; `activo` defaults true.
- [x] 6.5 RED: contact without `sector_id` creates with null sector.
- [x] 6.6 RED: `sector_id` from another drogueria is rejected with `ValidationError`.
- [x] 6.7 RED: a second `es_principal=true` contact flips the previous one to false (single active principal).
- [x] 6.8 RED: deactivating the principal contact does not auto-promote another.
- [x] 6.9 RED: contact deactivation hides it from default listings (D4).
- [x] 6.10 RED: cross-tenant contact access raises `NotFoundError` (D3).
- [x] 6.11 Create `services/terceros/contactos/service.py` implementing 6.3-6.10 (GREEN).
- [x] 6.12 Create `services/terceros/contactos/router.py`.

## Phase 7: Aggregator + Facade (D5)

- [x] 7.1 Create `services/terceros/__init__.py` (PR2). Created in this batch (PR4) — deferred from PR2/PR3 per explicit orchestrator scope instructions ("NO toques Fase 7... en batch 2/3").
- [x] 7.2 Create `services/terceros/router.py` aggregating identidad+catalogos routers (PR2); extend with direcciones+contactos (PR3). Created in this batch as one aggregator combining all four subrouters (identidad, catalogos, direcciones, contactos) since Phase 7 had not been started yet — see router.py docstring for the "single registration point" reading of "prefijo único" (no new URL prefix added; each subrouter already defines complete, non-conflicting paths).
- [x] 7.3 Create `services/terceros/api.py` — single-entry facade, identidad+catalogos first (PR2), extended (PR3). Created in this batch exposing all four subdomains at once (identidad, catalogos, direcciones, contactos) via reexports, plus four new combined tercero+rol functions added to `identidad/repository.py`+`service.py` (`listar_clientes_con_tercero`, `obtener_cliente_con_tercero`, `listar_proveedores_con_tercero`, `obtener_proveedor_con_tercero`) needed by Phase 8's consumers — RED tests written and GREEN in `tests/terceros/identidad/test_service.py`.
- [x] 7.4 Modify `services/presupuestacion/main.py`: `include_router(terceros_router)` (PR2). Done — `app.include_router(terceros_router, tags=["terceros"])`, verified the FastAPI app builds (128 routes, no import errors).
- [x] 7.5 Re-run `tests/terceros/test_dependencias.py` (2.8) — GREEN once subdomain code exists. Confirmed GREEN (43/43 `tests/terceros/` passing, including this guard) — `services/terceros/api.py` only imports from `services.terceros.*`, never `services.presupuestacion`.

## Phase 8: Consumer Adaptation (PR4)

- [x] 8.1 Modify `services/presupuestacion/clientes/service.py` to resolve identity/contacts via `services.terceros.api`. Done — `crear_cliente`/`actualizar_cliente`/`obtener_cliente`/`listar_clientes` orchestrate `api.crear_tercero`+`api.asignar_rol_cliente`/`api.actualizar_tercero`+`api.actualizar_rol_cliente`/`api.obtener_cliente_con_tercero`/`api.listar_clientes_con_tercero`; contacts route through `api.crear_contacto`/`listar_contactos`/`actualizar_contacto`/`obtener_contacto`. `eliminar_cliente` now deactivates the role (`ClienteRolUpdate(activo=False)`) instead of soft-deleting the tercero (D1/D4 — a tercero can stay active as proveedor). Fixed D-CLIENTES-004 (design.md D3) along the way: cross-tenant now consistently raises `NotFoundError` (was `ValidationError` for formato-documentos/observaciones, `ForbiddenError` for contacts/sub-resources).
- [x] 8.2 Modify `services/presupuestacion/clientes/repository.py`/`models.py`, dropping fields now owned by `terceros`. Done — `repository.py` keeps only `cliente_formato_documentos`/`cliente_observaciones` (no longer touches `clientes`/`cliente_contactos`, the latter table no longer exists). `models.py`: `ClienteCreate`/`Update`/`Out` drop `direccion`/`ciudad`/`provincia`/`codigo_postal`/`plazo_pago_dias`/`condiciones_pago`, add `cuit`/`condicion_pago_id`/`forma_pago_id`; `ClienteContactoCreate`/`Update`/`Out` gain `apellido`/`sector_id`/`celular` to match `terceros_contactos`. **Decision (explicitly requested)**: `GET /clientes` returns the flat combined tercero+rol shape (not nested `{"tercero":..., "rol":...}`) to minimize the contract change for existing `ClienteOut` consumers — documented in `ClienteOut`'s docstring.
- [x] 8.3 Modify `services/presupuestacion/catalogo/service.py`/`repository.py`, removing `proveedores` handling. Done — `repository.py` drops the whole proveedores section (comment points to the replacement). **Decision (explicitly requested)**: kept a compatibility wrapper in `catalogo/service.py`/`models.py` (`crear_proveedor`/`listar_proveedores`/`obtener_proveedor`/`actualizar_proveedor`/`eliminar_proveedor`, same `/proveedores` router paths) that internally orchestrates `services.terceros.api` (crear tercero + asignar rol proveedor), instead of repointing external callers directly to `services.terceros.api` — confirmed via grep that no other module imports `catalogo.service`/`catalogo.repository` for proveedores, so this is a pure internal reimplementation with zero blast radius. `ProveedorCreate/Update/Out` swap `plazo_pago_dias`/`condiciones_pago` (free text) for `condicion_pago_id`/`forma_pago_id` (FK to `services.terceros.catalogos`).
- [x] 8.4 Modify `services/extraccion/routers/clientes.py`: select `id, terceros(razon_social)` via PostgREST embedding. Done exactly as design.md specifies; `services/extraccion/**` is not under D5's presupuestacion-only facade rule, so the direct PostgREST embed (not `services.terceros.api`) is correct here.
- [x] 8.5 Update `tests/test_clientes_api.py` to the new nested tercero shape. Done — mocks now return `{"id":..., "terceros": {"razon_social":...}}`; added two new tests (order-by-nombre client-side sort, and rows with a null/missing `terceros` embed being skipped instead of raising `KeyError`).
- [x] 8.6 Update `tests/catalogo/`, removing proveedor-catalog assertions now covered by `tests/terceros/`. Done — `test_crear_listar_actualizar_y_eliminar_proveedor` kept (same name, per the orchestrator's explicit verification checkpoint) but rewritten for the new field shape (`es_competidor` instead of `plazo_pago_dias`) and D4/D1 deactivation semantics (`eliminar_proveedor` deactivates the role, tercero stays active — same pattern as clientes). `limpiar_catalogo` fixture now deletes `terceros` (cascades to `proveedores`) instead of `proveedores` directly.
- [x] 8.7 RED->GREEN: `services/extraccion/routers/clientes.py` `GET` still returns `id` + name after 8.4. Confirmed GREEN — 6/6 `tests/test_clientes_api.py` passing.

## Phase 9: Legacy Import + RPC (PR5)

> **BLOQUEO externo descubierto en esta fase, ver `docs/modulos/terceros/decisiones.md`
> D-TERCEROS-001**: la RPC `upsert_terceros_legacy` tal como quedó aplicada por la
> migración 0008 (Fase 1) rompía con `column reference "codigo_legacy" is ambiguous`
> en **toda** llamada (confirmado con pytest real contra la base de test). Causa: el
> parámetro `OUT codigo_legacy` de `RETURNS TABLE(...)` colisiona sin calificar con
> `terceros_legacy_map.codigo_legacy` dentro del `ON CONFLICT (...)` de ese `INSERT`.
> Se escribió el fix (`supabase/migrations/0009_fix_upsert_terceros_legacy_ambiguous_column.sql`
> + `.down.sql`, `#variable_conflict use_column`), pero esta sesión **no tuvo acceso al
> MCP de Supabase** (a diferencia de la Fase 1, donde el orquestador sí lo aplicó
> directamente — ver nota de la tarea 1.14) y no encontró ninguna vía alternativa
> (sin CLI de Supabase vinculado, sin `psycopg2`/`asyncpg` instalados, `.env` con
> lectura bloqueada por sandboxing) para aplicar la migración 0009 a la base de test
> desde este entorno. **Todo el código de 9.1-9.3 y los tests de 9.4-9.14 están
> implementados y son correctos por lectura**, pero no pudieron confirmarse en verde
> contra la base real — requiere que el orquestador (u otra sesión con MCP de Supabase)
> aplique `0009_fix_upsert_terceros_legacy_ambiguous_column.sql` y vuelva a correr
> `pytest tests/imports/`.

- [x] 9.1 Modify `services/presupuestacion/imports/repository.py` to call `upsert_terceros_legacy` per batch. Implementado (`upsert_terceros_legacy`, una llamada RPC por lote vía `client.rpc(...)`); verificado en verde por el orquestador tras aplicar `0009_fix_upsert_terceros_legacy_ambiguous_column.sql`.
- [x] 9.2 Modify `services/presupuestacion/imports/service.py` to build the RPC's `p_filas` JSONB from parsed CSV rows. Implementado (`_importar_terceros_legacy` + `p_filas` construido en `importar_clientes`/`importar_proveedores`); verificado en verde.
- [x] 9.3 Keep `desactivar_clientes`/`desactivar_proveedores` outside the RPC, resolving via `terceros_legacy_map`, deactivating only the role row. Implementado; verificado en verde.
- [x] 9.4 RED→GREEN: re-importing the same CSV updates the existing tercero instead of duplicating it. `test_reimportar_mismo_csv_actualiza_tercero_en_vez_de_duplicarlo` — pasa.
- [x] 9.5 RED→GREEN: re-importing does not duplicate the `clientes` role row. `test_reimportar_no_duplica_fila_de_rol_clientes` — pasa.
- [x] 9.6 RED→GREEN: a record present in both legacy sources yields one `terceros` row and both role rows. `test_registro_en_ambas_fuentes_produce_un_tercero_y_dos_roles` — pasa.
- [x] 9.7 RED→GREEN: a cliente-only legacy record does not create a `proveedores` row. `test_registro_solo_cliente_no_crea_proveedor` — pasa.
- [x] 9.8 RED→GREEN: first import of a new `codigo_interno` creates a `terceros_legacy_map` row. `test_primer_import_crea_fila_en_legacy_map` — pasa.
- [x] 9.9 RED→GREEN: re-import does not duplicate the `terceros_legacy_map` row. `test_reimportar_no_duplica_fila_de_legacy_map` — pasa.
- [x] 9.10 RED→GREEN: import deactivates a tercero/role missing from the latest CSV without deleting it. `test_import_desactiva_la_fila_de_rol_ausente_sin_eliminar_el_tercero` — pasa (desactiva la fila de ROL, no el tercero, per design.md sección 7).
- [x] 9.11 RED→GREEN: a natively created tercero is matched and updated, not duplicated, on a later import of the same `codigo_interno`. `test_import_actualiza_tercero_creado_nativamente_en_vez_de_duplicarlo` — pasa.
- [x] 9.12 RED→GREEN: same CUIT imported as cliente then as proveedor produces one `tercero` with two role rows (D1 doble rol). `test_mismo_cuit_como_cliente_y_luego_proveedor_produce_un_tercero_con_dos_roles` — pasa.
- [x] 9.13 RED (xfail intencional): `codigo_legacy='001'` colliding between cliente and proveedor legacy sources produces two distinct terceros (D1 collision). Test escrito y confirmado `xfail(strict=True)` — no ambiguo (bug de la RPC ya arreglado en 0009), es un SEGUNDO defecto real e independiente: `terceros.uq_terceros_codigo` es `UNIQUE(drogueria_id, codigo_interno)` sin componente de entidad, así que este escenario viola esa constraint. Ver `docs/modulos/terceros/decisiones.md` D-TERCEROS-001 para el análisis completo y la migración de seguimiento recomendada (fuera de alcance de este change).
- [x] 9.14 Update `tests/imports/` fixtures to the RPC-based flow. `tests/imports/conftest.py` actualizado; confirmado GREEN por el orquestador: `pytest tests/imports/` → 25 passed, 1 xfailed.

**Nota de resolución (orquestador)**: aplicó `supabase/migrations/0009_fix_upsert_terceros_legacy_ambiguous_column.sql` contra la base de test (`grnamollopxdlstcpxhc`) vía `mcp__supabase__apply_migration`, verificó la RPC directamente con una llamada de prueba envuelta en `BEGIN;...ROLLBACK;` (sin dejar datos), y confirmó `pytest tests/imports/` → 25 passed, 1 xfailed (el xfail de 9.13, documentado y esperado).

## Phase 10: Cross-Cutting Verification & Docs

- [x] 10.1 Run `tests/terceros/test_dependencias.py` against the final tree — zero `import services.presupuestacion` under `services/terceros/`. Confirmado en verde (incluido en la corrida de `tests/clientes tests/catalogo tests/terceros`, 71 passed).
- [x] 10.2 Run `pytest --cov=services`; confirm no regression in `clientes`, `catalogo`, `imports` coverage. `pytest-cov` no está instalado en este venv (`pip show pytest-cov` → not found); no se instaló una dependencia nueva sin aprobación explícita. Sustituido por una verificación de regresión pass/fail: `pytest tests/clientes tests/catalogo tests/terceros` → 71 passed, 0 regresiones (mismo criterio de sustitución que la tarea 2.9 cuando `pytest` tampoco pudo correr en esa sesión). `tests/imports/` no pudo confirmarse en verde por el bloqueo de Fase 9 documentado arriba — no es una regresión de este batch, es el mismo bloqueo.
- [x] 10.3 Create `docs/modulos/terceros/decisiones.md` documenting D1-D6 as explicit decisions. Creado, junto con `docs/modulos/terceros/README.md` y `base_de_datos.md`. Actualizados también `docs/modulos/clientes/decisiones.md`+`base_de_datos.md` y `docs/modulos/catalogo/decisiones.md`+`base_de_datos.md` con notas de migración explícitas (no se reescribió la auditoría línea-a-línea completa de esos módulos — fuera del alcance de tiempo de este batch, documentado como tal).
- [x] 10.4 Verify the M0 version guard against the live Supabase project (`select version()`); close design's open question. Sin acceso a MCP de Supabase en esta sesión para correr `select version()` directo. Cerrado por evidencia indirecta: el guard M0 (`RAISE EXCEPTION` si `server_version_num < 150000`) habría abortado la migración 0008 entera; la Fase 1 confirmó aplicación exitosa (`list_tables` mostró las 8 tablas nuevas), lo que confirma Postgres ≥ 15 en `grnamollopxdlstcpxhc`.

## Phase 11: orden-compra Handoff

- [x] 11.1 Create `openspec/changes/orden-compra/HANDOFF-terceros-modelo.md`: `codigo_interno`/`uq_cli_codigo` moved from `clientes` to `terceros`; `orden-compra`'s cliente lookup must resolve against `terceros` then verify the `clientes` role (D1 contract). Creado, incluye también la nota de `cliente_contactos`→`terceros_contactos`, el cambio de contrato de `imports/`, y el defecto D-TERCEROS-001 documentado para si `orden-compra` llega a crear terceros nuevos.

## Key Learnings

1. The design's five-PR cut (schema+shared, identidad+catálogos, direcciones+contactos, consumers, imports) maps directly onto stacked-to-main work units because each PR merges independently and in the design's stated order.
2. D4's activo-hidden-by-default rule applies only to the six new tables that carry `activo` (terceros, tercero_direcciones, terceros_contactos, and the three catalogs); direccion_usos and terceros_legacy_map have no activo column.
3. The D5 dependency guard test (tests/terceros/test_dependencias.py) must be written RED before services/terceros/ exists, then re-verified GREEN once every subdomain is in place, so it doubles as an early and a final checkpoint.
4. Import idempotency touches two distinct invariants that need separate tests: no duplicate terceros row per codigo_interno, and no merged identity across the independent cliente and proveedor legacy code spaces (D1).
5. services/extraccion/routers/clientes.py requires a real code change (PostgREST embedding for terceros.razon_social), so it is tracked as an explicit consumer-adaptation task, not skipped as unaffected.
6. D5's blocker list in design.md (config/database/exceptions) was incomplete: services/terceros/identidad/router.py and catalogos/router.py also need UsuarioPerfil/require_roles, which only existed in services/presupuestacion/core/auth.py. Extracted it to services/shared/auth.py with the same reexport-shim pattern as Phase 2, verified regression-free against tests/core/test_auth.py.
7. D4's "hides activo=false by default" rule (D4 point 4) is stricter than the pre-existing clientes/catalogo pattern: those modules default listar_* to activo=None (show all) and rely on a future facade to filter. terceros/identidad and terceros/catalogos default listar_*'s activo parameter to True instead, so the hiding happens at the service layer itself, not only at the not-yet-built D5 facade.
8. asegurar_tercero_de_la_drogueria (D3) is intentionally generic despite its tercero-specific name: it takes any row with a drogueria_id key and an entidad label, so both identidad and catalogos service layers reuse the exact same guard function instead of each rolling their own tenant check.
9. Querying `direccion_usos` with a PostgREST embed of `tercero_direcciones(*)` fails with `PGRST201` ("more than one relationship was found") because two FKs connect them (`fk_du_dir_drog`, `fk_du_dir_tercero`); the embed must disambiguate with `tercero_direcciones!fk_du_dir_tercero(*)`.
10. design.md deliberately leaves the "principal" conflict rule open for `direccion_usos`/`terceros_contactos`, so this batch defines two different rules and documents the reasoning in each service.py docstring: addresses reject a second principal-per-use with `ConflictError` (a tercero can have several simultaneous uses, so there is no unambiguous "the one to demote"), while contacts auto-demote the previous principal (a tercero has exactly one principal contact, so demotion is unambiguous) — matching tasks.md 6.7's explicit "flips to false" wording.
11. `tercero_direcciones` carries an `activo` column (per the M6 DDL) but Phase 5's task list has no D4 "hidden by default" test, unlike Phase 3/4 and unlike Phase 6 for contacts; `terceros-direcciones/spec.md`'s own "Address Edit and Removal" requirement instead demands physical removal ("no longer exist"). This batch treats direcciones as the one D4-table where physical delete (`eliminar_direccion`, cascading to `direccion_usos` via the existing `ON DELETE CASCADE` FKs) is the router-exposed retirement path, while `TerceroDireccionUpdate.activo` stays available for manual soft-deactivation without a dedicated default-hiding test.
