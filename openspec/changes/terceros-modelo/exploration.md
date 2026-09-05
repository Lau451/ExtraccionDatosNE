## Exploration: terceros-modelo

### Current State
`clientes` and `proveedores` are two independent flat tables (0 rows each, verified live) with overlapping identity concepts (CUIT only on proveedores, codigo_interno on both, both carry plazo_pago_dias int + condiciones_pago free text). Contacts exist only for clientes (`cliente_contactos`, single `nombre` field, no sector/apellido/celular, no `proveedor_contactos` equivalent). No `forma_pago` column exists anywhere in the schema. Code-wise:
- Clientes CRUD lives in `services/presupuestacion/clientes/` (models.py, repository.py, service.py, router.py) — repository.py issues raw `client.table("clientes")` / `client.table("cliente_contactos")` queries assuming the current flat shape.
- Proveedores CRUD does **not** have its own module — it lives inside `services/presupuestacion/catalogo/` (models.py has `ProveedorCreate/Update/Out`; repository.py has `crear_proveedor`/`listar_proveedores`/etc. against `client.table("proveedores")`; router.py exposes `/proveedores*`). This is a discovery beyond the user's brief: proveedores is a sub-concern of "catalogo", not a peer module of "clientes".
- `services/presupuestacion/imports/` is the confirmed legacy-ETL hook: `importar_clientes`/`importar_proveedores` in `imports/service.py` (+ `imports/repository.py`) upsert directly into `clientes`/`proveedores` keyed by `codigo_interno` per `drogueria_id`, with idempotent create/update/deactivate semantics. This is the single highest-blast-radius consumer of any schema split.
- `services/extraccion/routers/clientes.py` only reads `id, nombre` filtered by `drogueria_id, activo` — low risk, columns survive the split.
- `docs/schema/extractor_final.sql` is the DDL source of truth (separately confirmed stale specifically for `clientes` columns per the orden-compra change; other tables checked here matched the live DB).
- The parallel, uncommitted `openspec/changes/orden-compra/` change anchors `ordenes_compra.cliente_id` to `clientes.id` via `codigo_interno` lookup and does not touch condiciones_pago/forma_pago at all — no overlap in DDL targets, but both changes touch `clientes`/`proveedores`-adjacent schema and need explicit sequencing.

### Affected Areas
- `services/presupuestacion/clientes/models.py|repository.py|service.py|router.py` — flat-schema CRUD + `ClienteContactoCreate/Out` (single `nombre`, no sector) must become terceros-aware and replaced by the generalized contact model.
- `services/presupuestacion/catalogo/models.py|repository.py|service.py|router.py` — proveedores CRUD lives here; `es_competidor`/`es_proveedor_compra` boolean pair is the pre-existing ad-hoc precedent for role modeling the user's brief already calls out.
- `services/presupuestacion/imports/models.py|service.py|repository.py|router.py` — `importar_clientes`/`importar_proveedores` upsert-by-codigo_interno logic must split inserts across `terceros` + role table while preserving idempotency; no proveedor-specific or contact-specific tests exist today for this path.
- `services/extraccion/routers/clientes.py` — low risk, read-only, minimal columns.
- `docs/schema/extractor_final.sql` — needs `terceros`, `tercero_direcciones`, `terceros_contactos`, `sectores_contacto`, `condiciones_pago`, `formas_pago`, legacy-map table; narrower `clientes`/`proveedores` with `id` FK'd to `terceros(id)`; retire `cliente_contactos`.
- Confirmed unaffected-by-FK-break (PK-sharing protects them): `procesos_comerciales.cliente_id`, `cliente_producto_alias.cliente_id`, `cliente_formato_documentos.cliente_id`, `cliente_observaciones.cliente_id`, `compras_proveedor.proveedor_id`, `precios_proveedor.proveedor_id`, `proveedor_producto_alias.proveedor_id`, plus `eventos.cliente_id`/`eventos.proveedor_id` (found via schema read — not in the user's original list).
- `ordenes_compra.cliente_id` — confirmed out of scope, owned by the parallel `orden-compra` change; PK-sharing keeps its FK valid without modification.
- Tests: `tests/test_clientes_api.py`, `tests/catalogo/test_service.py` (+conftest), `tests/imports/test_service.py` (+conftest) — all assert current flat shape.
- `docs/modulos/clientes/decisiones.md`, `docs/modulos/catalogo/decisiones.md`, `docs/modulos/imports/decisiones.md` — living decision logs documenting pre-existing debt (3 exception types for tenant-isolation checks, `cliente_contactos.activo` has no functional effect, soft-delete only on root entity) that intersects with this change.

### Approaches
1. **Clean-slate DDL rewrite (single migration)** — recreate `clientes`/`proveedores` as narrow subtype tables with `id` FK'd to a new `terceros(id)` (not a fresh PK), add `tercero_direcciones`, `terceros_contactos`, `sectores_contacto`, `condiciones_pago`, `formas_pago`, legacy-map table; retire `cliente_contactos`.
   - Pros: 0 rows in both tables today (verified) removes all backfill/downtime risk; one coherent migration instead of staged drift; single generalized contacts table instead of two.
   - Cons: every function in `clientes/` and `catalogo/` (proveedores) plus all of `imports/` must be rewritten in lockstep; needs explicit sequencing with the parallel `orden-compra` change.
   - Effort: Medium (schema is simple because there's no data; code churn is the real cost).

2. **Additive parallel-table approach** — add `terceros` + catalogs alongside untouched `clientes`/`proveedores`, backfill a `tercero_id` FK column without changing their PK.
   - Pros: less immediate code churn; `imports/`, `catalogo/`, `ordenes_compra.cliente_id` need no immediate changes.
   - Cons: directly contradicts the already-decided scope (PK compartida, id = tercero_id); creates a second identity duality exactly like the `es_competidor`/`es_proveedor_compra` ad-hoc pattern already flagged as a problem; defers the real work.
   - Effort: Low short-term, pays interest later — rejected, listed only for completeness.

### Recommendation
Approach 1 (clean-slate rewrite). The 0-row state removes the single biggest risk of a class-table-inheritance migration, and Approach 2 was already ruled out by the user's own scope decision.

### Risks
- `es_competidor`/`es_proveedor_compra` on `proveedores` is the pre-existing ad-hoc role-modeling precedent; scope doesn't say whether to fold them into the new role model — needs an explicit propose-phase decision.
- No existing table in this codebase clearly represents "a document" to carry the "condición/forma aplicada" snapshot for clientes or proveedores (comparativas/ofertas/compras_proveedor are candidates); `ordenes_compra`/`oc_items` are explicitly out of scope and owned by the parallel change — propose must name the target table(s).
- Possible redundancy between existing `plazo_pago_dias` (int) and the new `condiciones_pago` catalog if catalog entries encode day-terms — propose should state the relationship.
- `imports/` upserts are keyed purely on `codigo_interno`; splitting inserts across `terceros` + role table must preserve idempotency (re-running a CSV must not duplicate `terceros` rows) — currently has no proveedor- or contact-specific test coverage, highest silent-regression risk.
- If design chooses a backward-compatible view for reads, views bypass RLS by default (Supabase security checklist) and need `WITH (security_invoker = true)` on PG15+; this project's Postgres version could not be confirmed by the parallel `orden-compra` change either.
- Pre-existing debt in `docs/modulos/clientes/decisiones.md` (3 exception types for the same tenant check, ineffective `activo` flag, root-only soft-delete) risks being copy-pasted into the new tables unless design explicitly revisits it.
- Sequencing risk with the parallel, uncommitted `orden-compra` change — both touch `clientes`/`proveedores`-adjacent schema; no DDL target overlap found, but migration order should be explicit in the proposal.

### Scope Update (post-exploration, user-confirmed)
The original brief assumed `clientes`/`proveedores` are populated mainly via `services/presupuestacion/imports/` (legacy CSV from the old system) and that this change only needs to keep that import path working against the new shape. The user has since clarified: the new system should manage terceros/clientes/proveedores/direcciones/contactos/condiciones de pago/formas de pago **natively**, not just receive them via import. This expands scope from "schema restructuring + minimal touch-up of existing CRUD" to "schema restructuring + first-class CRUD" for:
- `terceros` (create/update/deactivate, independent of import)
- `clientes` / `proveedores` role assignment on a tercero
- `tercero_direcciones` (add/edit/remove, manage usos)
- `terceros_contactos` (add/edit/remove, manage sector/principal)
- `sectores_contacto`, `condiciones_pago`, `formas_pago` catalogs (CRUD, drogueria-scoped)

`services/presupuestacion/imports/` remains a supported path (idempotent upsert from legacy CSV) but is no longer the only way these entities get created — propose/design must define the native CRUD surface (models/repository/service/router) following the existing module patterns in `services/presupuestacion/clientes/` and `services/presupuestacion/catalogo/`.

### Ready for Proposal
Yes — scope, live schema, and code surface are confirmed. Open questions above are normal propose/design-phase decisions, not blockers.
