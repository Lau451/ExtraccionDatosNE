# Tasks: Gestor de PCP

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~5200-6800 (migrations ~950-1170 combined across PR1+PR2, 9 capability modules ~200-550 each, PDF+mensajeria ~350-420, tests ~2600+, docs ~200) |
| Review budget (project override) | 1000 lines/PR (session preflight `review_budget_lines`, not the 400-line default) |
| 400-line budget risk | Low (per unit, after split) |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 → PR3 → PR4 → PR5 → PR6 → PR7 → PR8 → PR9 → PR10 → PR11 |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low

Note: `review_budget_lines: 1000` from session preflight is used above instead of the skill's 400-line
default, per this project's explicit instruction. Per the user's decision, the original Unit 1 (migration)
and Unit 2 (gestion+renglones+historial) — the two units previously closest to or over the 1000-line
budget — are now split into five self-contained units (PR1-PR5) below. Every unit is estimated comfortably
under the 1000-line budget; no table ships without its own RLS in the same PR.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | `0011_pcp_modelo.sql` core schema + RLS (`pcp`, `pcp_renglones`, `pcp_renglon_resultados`, `producto_proveedores`) — ~450-550 lines | PR1 | `pytest tests/pcp/test_dependencias.py` | `supabase db push` / MCP `apply_migration` against test project | `.down.sql`; additive, all four tables empty |
| 2 | `0012_pcp_extras.sql` schema + RLS (`pcp_historial`, `reglas_pcp`, `pcp_legacy_map`, `pcp_consultas`, `pcp_consulta_renglones`, `precios_proveedor` FK cols, 2 view recreations, `upsert_pcp_legacy` RPC) — ~500-620 lines | PR2 | `pytest tests/pcp/test_backfill_plazo_pago.py` | MCP `apply_migration` against test project; `pg_get_viewdef` check on both views | `.down.sql`; additive, FK cols nullable/unused until PR7 |
| 3 | `pcp-historial` — ~200-280 lines | PR3 | `pytest tests/pcp/historial` | Service-level pytest (no router mounted yet) | Revert PR3; no router mounted, no other module calls it yet |
| 4 | `pcp-gestion` (depends on PR3's `agregar_evento`) — ~450-550 lines | PR4 | `pytest tests/pcp/gestion` | FastAPI `TestClient` against test project | Revert PR4; router not mounted in `main.py` until PR5 |
| 5 | `pcp-renglones` + `services/pcp/{router,api,errors}.py` aggregation (mounts gestion+renglones+historial into `main.py`) — ~450-550 lines | PR5 | `pytest tests/pcp/renglones tests/pcp/test_dependencias.py` | FastAPI `TestClient` against test project | Revert PR5; unmounting the router in `main.py` reverts PR3-PR5's HTTP surface together |
| 6 | `pcp-catalogo-proveedores` — ~250-320 lines | PR6 | `pytest tests/pcp/catalogo` | FastAPI `TestClient` | Revert PR6; independent of PR7/PR9 |
| 7 | `pcp-negociacion` + wiring the `plazo_pago_dias` FK columns — ~300-380 lines | PR7 | `pytest tests/pcp/negociacion` | `TestClient` + direct `precios_proveedor` row assertions | Revert PR7; FK columns stay nullable/unused (design rollback plan) |
| 8 | `pcp-legacy-import` — ~280-350 lines | PR8 | `pytest tests/pcp/imports` | Run same legacy payload twice against test project, assert row counts | Revert PR8; RPC has no other caller |
| 9 | `pcp-consultas-agrupadas` (grouping + PDF only, no send) — ~350-420 lines | PR9 | `pytest tests/pcp/consultas` | `TestClient`; open generated PDF bytes with `pypdf` to assert page/text content | Revert PR9; independent of PR11 |
| 10 | `pcp-sugerencias` (quantity-grouping + recent-price-reuse queries only) — ~200-280 lines | PR10 | `pytest tests/pcp/sugerencias` | `TestClient` against seeded PCP+`precios_proveedor` fixtures | Revert PR10; pure read queries, no schema |
| 11 | Outbound delivery adapter (`MensajeriaPort` + `LoggingMensajeriaAdapter`) + Comercial feedback loop wiring — ~350-420 lines | PR11 | `pytest tests/pcp/mensajeria tests/pcp/negociacion -k cerrar_pcp` | `TestClient` close-PCP path with the logging adapter (`PCP_MENSAJERIA_ADAPTER=log`) | Feature-flagged (`PCP_MENSAJERIA_ADAPTER`, `PCP_REPRICING_AUTOMATICO`); disable flags to fully revert |

## Phase 1: Schema Migration — Core PCP Tables (PR1: `0011_pcp_modelo.sql`)

- [x] 1.1 Verify live schema via Supabase MCP `list_tables`/`execute_sql` for `presupuestos`, `items_proceso`, `presupuesto_items`, `proveedores` — do NOT trust `docs/schema/extractor_final.sql` (read-only, known stale). **Deviation**: the Supabase MCP tool was not available to this `sdd-apply` execution context. Verified instead via direct introspection of the live PostgREST OpenAPI schema (`GET {SUPABASE_URL}/rest/v1/` with the service key) against `grnamollopxdlstcpxhc`, cross-checked against `0008_terceros_modelo.sql`'s documented post-migration shape. Confirmed live: `presupuestos(id, drogueria_id)` UNIQUE (`uq_pre_id_drog`), `items_proceso(id, drogueria_id)` UNIQUE (`uq_ip_id_drog`), `proveedores(id, drogueria_id)` UNIQUE (`uq_prov_id_drog`, post-0008 shape), `productos.id`/`procesos_comerciales.id` with no composite unique (single-column FK, matching existing `items_proceso.producto_id` etc.).
- [x] 1.2 Reconcile table count before writing DDL: design.md's Technical Approach/File Changes say "seven new tables", but D2-D9 name nine (`pcp`, `pcp_renglones`, `producto_proveedores`, `pcp_renglon_resultados`, `pcp_historial`, `reglas_pcp`, `pcp_legacy_map`, `pcp_consultas`, `pcp_consulta_renglones`) — treat the nine as authoritative; this PR covers the first four (`pcp`, `pcp_renglones`, `pcp_renglon_resultados`, `producto_proveedores`), PR2 covers the remaining five; flag the original mismatch in both PR descriptions.
- [x] 1.3 Create `supabase/migrations/0011_pcp_modelo.sql`; version guard consistent with `0008_terceros_modelo.sql`'s M0.
- [x] 1.4 M1: `pcp` table (D2) — `estado` CHECK, `UNIQUE (presupuesto_id) WHERE estado <> 'cerrada'`, partial index `(drogueria_id, estado, fecha_entrega_solicitada)`.
- [x] 1.5 M2: `pcp_renglones` table (D2) — `item_proceso_id NOT NULL` FK, snapshot `cantidad`/`precio_referencia`, `origen`/`estado` CHECKs, `UNIQUE (pcp_id, item_proceso_id)`.
- [x] 1.6 M3: `producto_proveedores` table (D3) — `UNIQUE (drogueria_id, producto_id, proveedor_id)`, partial unique `preferido`.
- [x] 1.7 M4: `pcp_renglon_resultados` table (D4) — `ck_ppr_resultado` invariant, `UNIQUE (pcp_renglon_id, proveedor_id)`.
- [x] 1.8 M5: RLS `ENABLE` + policies per D11 on `pcp`, `pcp_renglones`, `pcp_renglon_resultados`, `producto_proveedores` (SELECT: `superadmin,admin,gerencia,compras`; INSERT/UPDATE: `admin,gerencia,compras`; DELETE: `es_superadmin()`); `GRANT`s; `trg_set_updated_at` where applicable; `NOTIFY pgrst, 'reload schema'`.
- [x] 1.9 Create `supabase/migrations/0011_pcp_modelo.down.sql` mirroring M1-M5 in reverse.
- [x] 1.10 Update `docs/schema/extractor_final.sql` and `docs/schema/rls_final.sql` snapshots for these four tables.
- [x] 1.11 Applied to test Supabase project (`grnamollopxdlstcpxhc`) via MCP `apply_migration` (orchestrator, since Supabase MCP was unavailable to the `sdd-apply` sub-agent — see 1.1). Confirmed via `list_tables`: all four tables present with expected columns/constraints/RLS. `get_advisors(security)`: clean — only pre-existing, unrelated warnings (SECURITY DEFINER helper functions `es_superadmin`/`get_drogueria_id`/`get_rol`/`mismo_tenant` callable by `authenticated`, and leaked-password-protection disabled at the Auth level) — both predate this migration and are out of this PR's scope. `get_advisors(performance)`: flags "unindexed foreign key" on several audit-trail columns (`created_by`/`updated_by`/`cerrada_por`/`registrado_por`) across the four new tables, plus `pcp_renglones.item_proceso_id` and `pcp_renglon_resultados.proveedor_id`/`precio_proveedor_id` — all Low-severity, informational, and consistent with this project's existing pattern of not indexing every audit FK. Not fixed in this PR since design.md did not call out per-FK indexing as a decision; worth a follow-up look if `item_proceso_id` lookups (the module's core anchor pattern) show up as slow once there's real data. Also flags 3 "unused index" warnings on the brand-new indexes, which is expected noise (zero query traffic yet on empty tables) and not actionable.
- [x] 1.12 RED: `tests/pcp/test_dependencias.py` — `ast` walk (mirrors `tests/terceros/test_dependencias.py`): `services/pcp/**` imports only `services.presupuestacion.pricing.service`, `services.presupuestacion.notificaciones.service`, `services.terceros.api`, `services.productos` (never a `repository`); `services.presupuestacion` imports `services.pcp` only in `main.py`. Fails until Phase 5 modules exist (D1). Confirmed RED for the expected reason (`services/pcp/` does not exist yet) via `pytest tests/pcp/test_dependencias.py -v`.

## Phase 2: Schema Migration — PCP Extras (PR2: `0012_pcp_extras.sql`)

- [x] 2.1 Verify live schema via Supabase MCP `list_tables`/`execute_sql` for `precios_proveedor`, `terceros`, `terceros_contactos`, `condiciones_pago`, `formas_pago`, `sectores_contacto`, `usuarios`, `costos_productos`, `v_precios_especiales_vigentes`, `v_presupuesto_revision` — do NOT trust `docs/schema/extractor_final.sql` (read-only, known stale). **Deviation**: the Supabase MCP tool was not available to this `sdd-apply` execution context either (confirmed no `mcp__supabase__*` tools in the tool list) — same situation as PR1 (see 1.1). Verified instead via direct introspection of the live PostgREST OpenAPI schema (`GET {SUPABASE_URL}/rest/v1/` with the service key) against `grnamollopxdlstcpxhc`, cross-checked against `docs/schema/extractor_final.sql`/`rls_final.sql` (both already updated by PR1's orchestrator-applied migration, file mtimes confirm this). All ten tables/views confirmed live with the expected shape, including PR1's four tables already present with their `regla_pcp_id`/`consulta_id` columns still unFK'd as documented.
- [x] 2.2 Create `supabase/migrations/0012_pcp_extras.sql`; version guard consistent with `0011_pcp_modelo.sql`'s M0, applied after PR1 merges.
- [x] 2.3 M1: `pcp_historial` table (D6) — append-only, no `updated_at`, index `(drogueria_id, pcp_id, created_at DESC)`.
- [x] 2.4 M2: `reglas_pcp` table (D7) — seam only, no rows/service code.
- [x] 2.5 M3: `pcp_legacy_map` table (D8) — `UNIQUE (drogueria_id, sistema_origen, codigo_legacy)`.
- [x] 2.6 M4: `pcp_consultas` + `pcp_consulta_renglones` tables (D9) — no `pcp_id` on `pcp_consultas`.
- [x] 2.7 M5: `ALTER TABLE precios_proveedor ADD condicion_pago_id UUID NULL, ADD forma_pago_id UUID NULL` + composite FKs (D5).
- [x] 2.8 M5b: backfill — per `drogueria_id`, find-or-create `condiciones_pago` row for each distinct `plazo_pago_dias`, set the FK; keep `plazo_pago_dias` nullable/unused. **Deviation**: implemented as a named, idempotent SQL function `backfill_condicion_pago_desde_plazo(p_drogueria_id UUID DEFAULT NULL)` (REVOKE/GRANT'd like the module's other RPCs) instead of an anonymous `DO` block, invoked once for all droguerias at the end of M5b. Reason: an anonymous block cannot be re-invoked by task 2.15's integration test against freshly seeded data without depending on the timing of when this migration is actually applied — a named idempotent function can be seeded-and-called on demand. Same net effect on the schema.
- [x] 2.9 M6: DROP+CREATE `v_precios_especiales_vigentes` and `v_presupuesto_revision` reading `COALESCE(cp_pp.plazos_dias[1], pp.plazo_pago_dias, cp_prov.plazos_dias[1])`, preserving `WITH (security_invoker = true)` on both. **Not yet independently verified via `pg_get_viewdef`** — that requires the migration to be live (blocked by 2.14; MCP unavailable to this execution context). Source-level review confirms `WITH (security_invoker = true)` is present on both `CREATE VIEW` statements; the orchestrator should run `pg_get_viewdef` after applying via MCP per this task's original instruction, not skip straight to trusting the source.
- [x] 2.10 M7: RLS `ENABLE` + policies per D11 on `pcp_historial`, `reglas_pcp`, `pcp_legacy_map`, `pcp_consultas`, `pcp_consulta_renglones` (SELECT: `superadmin,admin,gerencia,compras`; INSERT/UPDATE: `admin,gerencia,compras`; DELETE: `es_superadmin()`); `pcp_historial` gets SELECT+INSERT only; `GRANT`s; `trg_set_updated_at` where applicable; `NOTIFY pgrst, 'reload schema'`.
- [x] 2.11 M8: `upsert_pcp_legacy` RPC (D8) — no `SECURITY DEFINER`, `SET search_path = public, pg_temp`, `REVOKE EXECUTE` from `PUBLIC`/`anon`/`authenticated`, `GRANT` to `service_role`. Applied `#variable_conflict use_column` from the first attempt (its OUT params `codigo_legacy`/`pcp_id` collide with real columns in `ON CONFLICT` targets), avoiding the exact bug 0009 had to patch in afterward for `upsert_terceros_legacy`.
- [x] 2.12 Create `supabase/migrations/0012_pcp_extras.down.sql` mirroring M1-M8 in reverse (plus `DROP FUNCTION backfill_condicion_pago_desde_plazo`).
- [x] 2.13 Update `docs/schema/extractor_final.sql` and `docs/schema/rls_final.sql` snapshots for these five tables, the `precios_proveedor` FK columns, and the two recreated views. Also folded PR1's four tables and this PR's five into one unified "nine tables" comment block (extractor_final.sql), removed the now-stale "FK llega en 0012" inline comments, and added the M4b deferred-FK `ALTER TABLE` statements + the RPC/function GRANT documentation to `rls_final.sql`.
- [x] 2.14 Applied to test Supabase project (`grnamollopxdlstcpxhc`) via MCP `apply_migration` (orchestrator, same as PR1's 1.11 — Supabase MCP was unavailable to the `sdd-apply` sub-agent). Confirmed via `pg_get_viewdef`-equivalent (`pg_class.reloptions`): both `v_precios_especiales_vigentes` and `v_presupuesto_revision` correctly carry `security_invoker=true` after the DROP+CREATE. `list_tables` confirms all 5 new tables exist. `get_advisors(security)`: clean, only the same pre-existing unrelated warnings already noted in 1.11 — nothing new from `upsert_pcp_legacy` or `backfill_condicion_pago_desde_plazo` (their non-`SECURITY DEFINER` + `REVOKE`-from-`authenticated` design holds up).
- [x] 2.15 Integration test: `plazo_pago_dias` backfill produces one `condiciones_pago` row per distinct value per `drogueria_id`; both recreated views still resolve against seeded data. `tests/pcp/test_backfill_plazo_pago.py` (4 tests). **Real GREEN confirmed** after 2.14 unblocked — but the first run surfaced a genuine bug in the test file itself (found and fixed by the orchestrator, not the sub-agent): 3 of the 4 tests' own `finally` cleanup blocks deleted `condiciones_pago`/`droguerias` rows *before* the `seed_precio_proveedor_factory` fixture's teardown (which runs after the test body, per pytest's LIFO fixture-teardown order) removed the `precios_proveedor` rows still referencing them via the new `fk_pp_condpago`/`fk_pp_drog` FKs — every assertion inside the test bodies had already passed correctly; only the teardown ordering was wrong. Fixed by releasing/deleting the referencing `precios_proveedor` rows first in each `finally`. All 4 tests pass GREEN now. **Also discovered while writing this test (sub-agent)**: the shared root fixture `tests/conftest.py::seed_proveedor` is broken repo-wide — it inserts `razon_social` directly into `proveedores`, a column migration `0008_terceros_modelo.sql` moved to `terceros` months ago (confirmed the same `PGRST204` failure reproduces against an existing, unrelated `tests/pricing/test_service.py` test). Pre-existing bug, not introduced by gestor-pcp and out of this PR's scope to fix repo-wide; worked around locally with a corrected `tests/pcp/conftest.py::seed_proveedor_pcp` fixture (two-step terceros+proveedores insert) instead of touching the shared fixture. Flagged here for the orchestrator/a follow-up change to fix `tests/conftest.py` itself.

## Phase 3: pcp-historial (PR3)

- [ ] 3.1 Create `services/pcp/historial/models.py`, `repository.py`.
- [ ] 3.2 RED: PCP event lands in `pcp_historial`, never `historial_cambios`.
- [ ] 3.3 RED: edit/delete of a history entry is rejected at the service layer (no method mutates or removes an existing entry).
- [ ] 3.4 Create `services/pcp/historial/service.py` implementing 3.2-3.3 (GREEN) — append-only writer (`agregar_evento`), no update/delete methods exposed.

## Phase 4: pcp-gestion (PR4)

- [ ] 4.1 Create `services/pcp/gestion/models.py`, `repository.py` (Pcp CRUD/state).
- [ ] 4.2 RED: create PCP for eligible presupuesto scopes to its `drogueria_id`.
- [ ] 4.3 RED: second PCP creation for a presupuesto with an open PCP raises `ConflictError`.
- [ ] 4.4 RED: valid `nueva`→`en_gestion` transition; reject skip (`nueva`→`cerrada`); reject backward (`esperando_respuesta`→`en_gestion`).
- [ ] 4.5 RED: list filters by requested-delivery-date range and by `estado`.
- [ ] 4.6 RED: cross-tenant PCP access raises `NotFoundError`.
- [ ] 4.7 RED: a state change writes a `pcp_historial` entry via `services.pcp.historial.service.agregar_evento` with old/new state, user, timestamp (integration with 4.4; depends on Phase 3's `pcp-historial`).
- [ ] 4.8 Create `services/pcp/gestion/service.py` implementing 4.2-4.4 and 4.7 (GREEN), calling `pcp-historial`'s `agregar_evento` on every state transition.
- [ ] 4.9 Create `services/pcp/gestion/router.py` with `require_roles(_ROLES_ESCRITURA_PCP)` on write, `_ROLES_LECTURA_PCP` on read (D11); RED: unauthorized role rejected at router with no row created/modified.

## Phase 5: pcp-renglones + Router Aggregation (PR5)

- [ ] 5.1 Create `services/pcp/renglones/models.py`, `repository.py`.
- [ ] 5.2 RED: renglón anchored on `item_proceso_id` still resolves after `presupuesto_items` DELETE+INSERT; reject a renglón identified only by `presupuesto_items.id`.
- [ ] 5.3 RED: renglón detail shows product identifying data + catalogued suppliers.
- [ ] 5.4 RED: select one supplier vs. select all available suppliers as negotiation targets.
- [ ] 5.5 RED: `origen` CHECK — manual selection tags `manual`; a row without one of `manual`/`regla`/`import_legado` is rejected.
- [ ] 5.6 Create `services/pcp/renglones/service.py` implementing 5.2-5.5 (GREEN) + `router.py`.
- [ ] 5.7 Create `services/pcp/{router,api,errors}.py` aggregating gestion+renglones+historial; mount in `services/presupuestacion/main.py`.
- [ ] 5.8 Re-run `tests/pcp/test_dependencias.py` (1.12) — GREEN now that `services/pcp/` exists.

## Phase 6: pcp-catalogo-proveedores (PR6)

- [ ] 6.1 Create `services/pcp/catalogo/models.py`, `repository.py`.
- [ ] 6.2 RED: list suppliers for a product returns both associated proveedores; empty catalog returns `[]` without error.
- [ ] 6.3 RED: ad-hoc association add from the renglón view makes the supplier immediately selectable; duplicate add raises `ConflictError`.
- [ ] 6.4 RED: cross-tenant association is never returned.
- [ ] 6.5 Create `services/pcp/catalogo/service.py` implementing 6.2-6.4 (GREEN) + `router.py`; wire into `services/pcp/renglones/service.py` for the "available suppliers" list.

## Phase 7: pcp-negociacion + plazo_pago_dias FK Wiring (PR7)

- [ ] 7.1 Create `services/pcp/negociacion/models.py`, `repository.py` (writes `precios_proveedor` + `pcp_renglon_resultados`).
- [ ] 7.2 RED: priced result writes one `precios_proveedor` row scoped to the renglón's `item_proceso_id`, reflecting proveedor/price/conditions.
- [ ] 7.3 RED: payment terms are recorded via `condicion_pago_id`/`forma_pago_id`, never free text or raw integer.
- [ ] 7.4 RED: `no_cotiza` outcome requires no price value; does not block recording a priced outcome for another supplier on the same renglón.
- [ ] 7.5 RED: recording a result leaves `costos_productos` unchanged and leaves other renglones' `precios_proveedor` rows unaffected.
- [ ] 7.6 RED: expired `mantenimiento_hasta` is treated as not currently valid.
- [ ] 7.7 Create `services/pcp/negociacion/service.py` implementing 7.2-7.6 (GREEN) + `router.py`; write `resultado_registrado` historial event.
- [ ] 7.8 Integration test: a `precio_obtenido` result is picked up by `pricing/repository.py::buscar_precio_especial_puntual`.
- [ ] 7.9 Update `services/presupuestacion/pricing/repository.py` docstring — remove/correct the now-inaccurate "`precios_proveedor` is read-only" invariant note.
- [ ] 7.10 Update `docs/modulos/pricing/pendientes.md` — close the P1(4) `precios_proveedor` dead-write gap, referencing this PR.

## Phase 8: pcp-legacy-import (PR8)

- [ ] 8.1 Confirm the exact legacy renglón-level field name and its matching rule to `item_proceso_id` against the real legacy export file (D8 caveat) before writing the import code.
- [ ] 8.2 Create `services/pcp/imports/models.py`, `repository.py` (calls `upsert_pcp_legacy` RPC per batch).
- [ ] 8.3 RED: re-importing the same `codigo_legacy` updates the existing PCP; exactly one row exists after two imports.
- [ ] 8.4 RED: re-importing does not duplicate the matched renglón.
- [ ] 8.5 RED: first import creates one `pcp_legacy_map` row; re-import does not duplicate it.
- [ ] 8.6 RED: legacy-imported renglón carries `origen = 'import_legado'`.
- [ ] 8.7 RED: a natively created PCP later matched by `codigo_legacy` is updated, not duplicated, on import.
- [ ] 8.8 Create `services/pcp/imports/service.py` implementing 8.3-8.7 (GREEN) + `router.py`; write `importada` historial event.

## Phase 9: pcp-consultas-agrupadas — grouping + PDF, no send (PR9)

- [ ] 9.1 Pin an exact `reportlab` version in `pyproject.toml`/`requirements`; confirm its BSD license classifier before adding the dependency (D9).
- [ ] 9.2 Create `services/pcp/consultas/models.py`, `repository.py` (`pcp_consultas` + `pcp_consulta_renglones`).
- [ ] 9.3 RED: grouping renglones from a single PCP creates one consulta with all of them.
- [ ] 9.4 RED: grouping renglones across two open PCPs creates one consulta; each renglón still traces to its own PCP.
- [ ] 9.5 Create `services/pcp/documentos/` — `PdfRenderer` port + `reportlab` renderer driven from Jinja2 templates.
- [ ] 9.6 RED: generated PDF lists every grouped renglón and identifies proveedor P as recipient (assert via `pypdf` text extraction).
- [ ] 9.7 Create `services/pcp/consultas/service.py` implementing 9.3-9.4 (GREEN) + `router.py`; no send call yet.

## Phase 10: pcp-sugerencias — suggestion queries only (PR10)

- [ ] 10.1 Create `services/pcp/sugerencias/repository.py`, `service.py` (D12, no schema — pure queries).
- [ ] 10.2 RED: same article across two open PCPs nearing the requested delivery date surfaces a joint-quote suggestion; ignoring it never merges or modifies the underlying PCPs.
- [ ] 10.3 RED: a `precios_proveedor` row with `activa=true` and unexpired `mantenimiento_hasta` for article A surfaces as a reference (supplier, date, `mantenimiento_hasta`, quantity band) when a renglón for A opens; an expired row is not surfaced.
- [ ] 10.4 Create `services/pcp/sugerencias/router.py` exposing both suggestions read-only.

## Phase 11: Outbound Delivery Adapter + Comercial Feedback Loop (PR11, droppable)

- [ ] 11.1 Create `services/pcp/mensajeria/port.py` — `MensajeAdjunto`, `ResultadoEnvio`, `MensajeriaPort` Protocol exactly per design's Interfaces section.
- [ ] 11.2 Create `services/pcp/mensajeria/adapters.py` — `LoggingMensajeriaAdapter` (default, `entregado=False`, `proveedor_externo="log"`) + `get_mensajeria()` reading `PCP_MENSAJERIA_ADAPTER` (default `log`).
- [ ] 11.3 Add `PCP_MENSAJERIA_ADAPTER`, `PCP_REPRICING_AUTOMATICO` (default off) to `services/presupuestacion/core/config.py`.
- [ ] 11.4 Wire `services/pcp/consultas/service.py`'s send path: resolve recipient from `terceros_contactos` (never client input), call `get_mensajeria()`.
- [ ] 11.5 RED: sending delivers through every enabled configured channel; sending with no delivery-capable contact is rejected with no delivery attempt; a delivery failure leaves the consulta and grouping intact for retry.
- [ ] 11.6 GREEN for 11.5; write `consulta_enviada` historial event on send.
- [ ] 11.7 Implement `negociacion/service.py::cerrar_pcp` (D10): on close, render result PDF, call `enviar_email` to `usuarios.email` of `pcp.solicitante_id`, write `notificacion_enviada` historial event.
- [ ] 11.8 RED: closing a PCP emails the result PDF to the requesting user's mailbox (pcp-sugerencias email-phase scenario).
- [ ] 11.9 Add `pcp_cerrada` to `TipoNotificacion` in `services/presupuestacion/notificaciones/models.py` (additive); guard behind `PCP_REPRICING_AUTOMATICO` + precondition that the originating presupuesto is still `generado`/`en_revision`.
- [ ] 11.10 RED: closing emits an internal notification and triggers automatic repricing via `pricing.service.generar_presupuesto_para_endpoint` when the presupuesto is still open; skips repricing (but still notifies) when it is no longer open.
- [ ] 11.11 GREEN for 11.10.

## Phase 12: Cross-Cutting Docs

- [ ] 12.1 Create `docs/modulos/pcp/` (README, `base_de_datos.md`, `decisiones.md`) per project convention, documenting D1-D12.
- [ ] 12.2 Router role-matrix E2E: `httpx`/`TestClient` covering `_ROLES_LECTURA_PCP`/`_ROLES_ESCRITURA_PCP` across all `services/pcp/` routers.
- [ ] 12.3 Full regression: `pytest tests/pcp tests/terceros tests/productos tests/pricing` — zero unrelated regressions.

## Key Learnings

1. Design's "seven new tables" undercounts D2-D9's nine named tables; task 1.2 forces reconciliation against live schema before DDL is written, avoiding a repeat of migration 0008's missed-view discovery.
2. The schema migration is split into two self-contained PRs (PR1: `0011_pcp_modelo.sql` for the four earliest-needed tables; PR2: `0012_pcp_extras.sql` for the remaining five plus the `precios_proveedor` FK/view work) so neither migration ships without its own RLS in the same PR, and each comfortably fits the 1000-line review budget.
3. `pcp-historial` (PR3) is built before `pcp-gestion` (PR4) because task 4.7 has gestion's state-machine write a `pcp_historial` entry on every transition — historial must exist and be callable first, not merely alongside.
4. `pcp-consultas-agrupadas` (PR9) and the outbound delivery adapter (PR11) stay separate slices because the "Outbound Delivery via Configured Channel(s)" requirement depends on `MensajeriaPort`, which does not exist until PR11 — PR9 only builds grouping and PDF generation.
5. `pcp-sugerencias`' feedback-loop requirements (email phase, internal-notification/auto-repricing phase) land in PR11, not PR10, because both depend on `get_mensajeria()`; PR10 covers only the two pure-query suggestions.
