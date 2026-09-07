# Design: Gestor de PCP

## Technical Approach

New top-level module `services/pcp/` (sibling of `services/terceros/` and `services/productos/`), one sub-package per capability, each with the `models`/`repository`/`service`/`router` quartet, aggregated by `services/pcp/router.py` and mounted once in `services/presupuestacion/main.py`. Schema is additive: seven new tables plus one additive column pair on `precios_proveedor`. `precios_proveedor` stays the price record; a PCP-owned result table carries the negotiation *outcome*, so `no_cotiza` never fabricates a price row. Migration `0011_pcp_modelo.sql` follows the 0008 style: one file = one transaction, ordered steps, `UNIQUE (id, drogueria_id)` on every table so children use composite tenant-safe FKs, `WITH (security_invoker = true)` on any recreated view, explicit `GRANT`s, `NOTIFY pgrst`.

## Architecture Decisions

### D1 — Module placement: `services/pcp/` (top-level)

| Option | Tradeoff |
|---|---|
| **`services/pcp/` (chosen)** | PCP is a Compras domain with its own tables, roles and lifecycle; `presupuestacion` is only a read dependency plus two service-level calls. Matches the established extraction pattern. |
| Under `services/presupuestacion/pcp/` | Cheaper wiring, but buries a Compras-owned bounded context inside the Comercial service and makes the future extraction a second refactor. |

**Dependency rule** (mirrors `tests/terceros/test_dependencias.py`, enforced by a new `tests/pcp/test_dependencias.py` using `ast`): `services/pcp/**` may import `services.presupuestacion.pricing.service`, `services.presupuestacion.notificaciones.service`, `services.terceros.api` and `services.productos` — public service layers only, **never** a `repository` of another module. `services.presupuestacion` may import `services.pcp` only in `main.py` (router mount). No cycle: `pricing.service` does not import `main`.

### D2 — PCP header + renglón

`pcp` (header): `id`, `drogueria_id`, `presupuesto_id` FK → `presupuestos(id)`, `proceso_comercial_id` (denormalized, list filtering), `estado` `CHECK IN ('nueva','en_gestion','esperando_respuesta','cerrada')` default `nueva`, `fecha_entrega_solicitada DATE` (primary filter), `solicitante_id` → `usuarios(id)`, `sector_id` → `sectores_contacto(id, drogueria_id)` (reuses the 0008 catalog), `origen`, `regla_pcp_id`, `notas`, `cerrada_at`/`cerrada_por`, audit columns. **Confirmed by user: only one open PCP per presupuesto** — `UNIQUE (presupuesto_id) WHERE estado <> 'cerrada'`. Index `(drogueria_id, estado, fecha_entrega_solicitada)` partial `WHERE estado <> 'cerrada'`.

`pcp_renglones`: `pcp_id` → `pcp(id, drogueria_id)` `ON DELETE CASCADE`, **`item_proceso_id NOT NULL` → `items_proceso(id)`** (the stable anchor; `presupuesto_items.id` is DELETE+INSERT'd per RN-PRICING-008), `producto_id` (nullable — matching may be pending), `cantidad` and `precio_referencia` as **value snapshots** taken at selection time (no FK, immune to regeneration), `origen CHECK IN ('manual','regla','import_legado')`, `regla_pcp_id`, `estado CHECK IN ('pendiente','resuelto','descartado')`, `UNIQUE (pcp_id, item_proceso_id)`, index `(drogueria_id, producto_id)` for the grouping suggestion.

**No cost column anywhere in the PCP tables.** `costos_productos` is role-restricted to `admin`/`gerencia`/`compras` (`rls_final.sql:186-191`). Per the user's confirmed read-visibility decision (D11), PCP read access is restricted to that same role set — `comercial`/`lider_comercial` do not see PCP screens at all, so this is no longer a leak-prevention boundary, but the rule stands for a simpler reason: a stored `costo_usado` would drift the moment `precios_proveedor` or `costos_productos` change, since PCP rows are not repriced live. The value is always derivable on read. Rejected: mirroring the cost for convenience.

### D3 — Producto↔proveedor catalog: `producto_proveedores`

Minimal association: `producto_id`, `proveedor_id` → `proveedores(id, drogueria_id)`, `codigo_proveedor` (supplier SKU), `preferido`, `activo`, `notas`, audit. `UNIQUE (drogueria_id, producto_id, proveedor_id)`; partial unique `(drogueria_id, producto_id) WHERE preferido AND activo`; index `(drogueria_id, producto_id) WHERE activo`. Starts empty; ad-hoc creation during a PCP is a normal write. Rejected: deriving suppliers from `precios_proveedor` history (that is a quote log, not a catalog — a supplier who never quoted can never appear). Seeding from history stays S16.

### D4 — `no_cotiza`: PCP-owned result table, `precios_proveedor` untouched

`precios_proveedor.precio_unitario` is `NOT NULL` with `ck_pp_precio (>= 0)`, and `pricing/repository.py::buscar_precio_especial_puntual` picks the cheapest active row by `item_proceso_id`. A sentinel price (`0`, `NULL`-able column) would either break the constraint or hand the pricing engine a free product.

`pcp_renglon_resultados`: `pcp_renglon_id`, `proveedor_id`, `consulta_id` (nullable), `resultado CHECK IN ('precio_obtenido','no_cotiza','sin_respuesta')`, `precio_proveedor_id` → `precios_proveedor(id)` (nullable), `motivo`, `registrado_por`, `created_at`. Invariant: `CHECK ((resultado = 'precio_obtenido') = (precio_proveedor_id IS NOT NULL))`. `UNIQUE (pcp_renglon_id, proveedor_id)`. Only `precio_obtenido` inserts a `precios_proveedor` row (with `item_proceso_id` set = precio puntual, so `v_precios_especiales_vigentes` and the pricing engine pick it up for free). Rejected: a nullable `precio_unitario` + status column on `precios_proveedor` (changes a table three views and the pricing engine already read).

### D5 — `plazo_pago_dias` → FK, additive with a one-release rollback

`ALTER TABLE precios_proveedor ADD condicion_pago_id UUID NULL, ADD forma_pago_id UUID NULL` with composite FKs `(x_id, drogueria_id)` → `condiciones_pago`/`formas_pago(id, drogueria_id)`, exactly as `clientes`/`proveedores` in 0008 M5. Backfill: per `drogueria_id`, find-or-create a `condiciones_pago` row with `plazos_dias = '{N}'` and `nombre = N || ' días'`, then set the FK. `plazo_pago_dias` stays in place, nullable, unused by new code, for one release; dropping it is a separate later change. `v_precios_especiales_vigentes` and `v_presupuesto_revision` must be DROP+CREATEd (they select `pp.plazo_pago_dias`) to read `COALESCE(cp_pp.plazos_dias[1], pp.plazo_pago_dias, cp_prov.plazos_dias[1])`, preserving `WITH (security_invoker = true)`.

### D6 — `pcp_historial`: dedicated and append-only

`EntidadAuditable` in `core/audit.py` is a closed 5-value Literal duplicated in `auditoria/models.py`; extending it drags PCP into the Comercial audit router and its visibility matrix. Instead: `pcp_historial` with `pcp_id`, `pcp_renglon_id` (nullable), `tipo_evento CHECK IN ('creada','estado_cambiado','renglon_agregado','renglon_quitado','consulta_enviada','resultado_registrado','sugerencia_aplicada','notificacion_enviada','importada')`, `payload JSONB NOT NULL DEFAULT '{}'`, `origen`, `usuario_id`, `created_at`. No `updated_at`. Append-only is enforced by omitting UPDATE/DELETE policies entirely and granting only `SELECT, INSERT` to `authenticated`. Index `(drogueria_id, pcp_id, created_at DESC)`. Payloads carry no cost fields (D2).

### D7 — Rules seam only: `reglas_pcp`

Table + FK targets, no engine, no rows, no service code. Shape follows `reglas_pricing` (drogueria-scoped, NULL scope = default, `prioridad`-ordered): `nombre`, nullable scopes `cliente_id`/`categoria_id`/`producto_id`/`clase_proceso`, `condicion JSONB`, `prioridad`, `activa`. It exists so `pcp.regla_pcp_id` and `pcp_renglones.regla_pcp_id` already have a referent the day `origen='regla'` is first written. Rejected: extending `automatizaciones.entidad_objetivo` (a Comercial-owned generic engine; line-level targeting would change its Literal and its blast radius).

### D8 — Legacy import: `pcp_legacy_map` + `upsert_pcp_legacy`

`pcp_legacy_map`: `pcp_id`, `sistema_origen` default `'legacy'`, `codigo_legacy`, `datos_legacy JSONB`, `importado_at`; idempotency key `UNIQUE (drogueria_id, sistema_origen, codigo_legacy)`. Unlike `terceros_legacy_map` there is no `entidad_legacy` discriminator — PCP is a single entity, so the code spaces cannot collide. **Confirmed by user: the legacy export carries a renglón-level code/identifier**, so `pcp_renglones.item_proceso_id` can be resolved during import via a matching step (analogous to the existing presupuesto/items_proceso matching) rather than needing a nullable column — this was the design's one hard blocker on the import slice and is now resolved; `sdd-tasks` should still confirm the exact legacy field name and matching rule against the real export file once available. RPC `upsert_pcp_legacy(p_drogueria_id, p_sistema_origen, p_filas JSONB, p_usuario_id) RETURNS TABLE (codigo_legacy, pcp_id, accion)` mirrors `upsert_terceros_legacy` step for step: `SELECT ... FOR UPDATE` on the map, insert-or-update the header, `INSERT ... ON CONFLICT DO NOTHING` on the map, then renglones with `origen='import_legado'`. `LANGUAGE plpgsql`, `SET search_path = public, pg_temp`, **no** `SECURITY DEFINER` (invoked via `get_service_client()`, which already bypasses RLS), `REVOKE EXECUTE` from `PUBLIC`/`anon`/`authenticated`, `GRANT` to `service_role`.

### D9 — Grouped consulta, PDF, and the delivery port

Grouping is a real many-to-many, not a query: `pcp_consultas` (`proveedor_id`, `contacto_id` → `terceros_contactos(id, drogueria_id)`, `estado CHECK IN ('borrador','enviada','respondida','cancelada')`, `canal`, `fecha_envio`, `fecha_respuesta_esperada`, `documento_path`) has **no** `pcp_id`; `pcp_consulta_renglones` (`consulta_id`, `pcp_renglon_id`, `cantidad_consultada`, `UNIQUE (consulta_id, pcp_renglon_id)`) is what lets renglones from several PCPs land in one supplier consulta.

**PDF**: no generator exists in the repo — `pypdf`/`pdfplumber` only read and split. `pymupdf` (already a dependency) can generate PDFs via `Story`, but it is dual-licensed AGPL-3.0/Artifex-commercial (confirmed: installed `pymupdf==1.27.2.3` metadata reads "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License") — **the user chose not to use it for this new, more central use case** and asked for a non-AGPL library instead, even at the cost of a new dependency. Chosen: **`reportlab`** (BSD-licensed, pure Python, no system libraries — same Docker/Windows-friendly property PyMuPDF would have had) driven from the same Jinja2 templates for the row/table data, behind a `PdfRenderer` port in `services/pcp/documentos/` so the renderer stays a one-class swap if this decision changes later. `sdd-tasks`/`sdd-apply` must pin an exact `reportlab` version and re-confirm its license classifier before adding it to `pyproject`/`requirements`. Rejected: WeasyPrint (GTK/Pango system libs complicate Docker/Windows), headless Chromium (heavy), PyMuPDF (AGPL, explicitly declined by the user for this use case).

**Delivery**: `services/pcp/mensajeria/port.py` defines `MensajeriaPort` with `enviar_email` and `enviar_whatsapp`; the default `LoggingMensajeriaAdapter` records a `ResultadoEnvio(entregado=False, proveedor_externo="log")` and sends nothing. `get_mensajeria()` selects the adapter from `PCP_MENSAJERIA_ADAPTER` (default `log`) — this is the feature flag in the proposal's rollback plan. **No vendor is named anywhere in code or config defaults.**

### D10 — Comercial feedback loop

Closing a PCP (`negociacion/service.py::cerrar_pcp`) renders the result PDF and calls `get_mensajeria().enviar_email(...)` to the `usuarios.email` of `pcp.solicitante_id`, then writes a `notificacion_enviada` history event with the `ResultadoEnvio`. With the default adapter this is a recorded no-op, so the module ships without a messaging vendor. The later path adds one value (`pcp_cerrada`) to the `TipoNotificacion` Literal in `notificaciones/models.py` — an additive edit — and calls `notificaciones.service.crear_notificacion`. Auto-repricing calls the existing public seam `pricing.service.generar_presupuesto_para_endpoint(proceso_comercial_id=..., drogueria_id=..., disparado_por=...)`, which already owns the `service_role` client; no new pricing code and no boundary violation. Guarded twice: config flag `PCP_REPRICING_AUTOMATICO` (default off) and a precondition that the originating `presupuestos.estado` is still `generado`/`en_revision` — never after `aprobado`/`presentado`.

### D11 — RLS and roles

**Confirmed by user: PCP read visibility is restricted to `compras`, `gerencia`, `admin`** — narrower than the initial draft's tenant-wide read. `comercial`/`lider_comercial` do not see PCP screens at all, not even their own; this does not conflict with the D10 feedback loop, because Comercial is notified about their *presupuesto* (which they already have normal access to), never routed through a PCP screen. `superadmin` keeps read access as the standing cross-tenant support-role convention already used for `terceros`/`productos` (not something the user was asked to reconsider here).

Every new table: `ENABLE ROW LEVEL SECURITY`; `SELECT USING ((select get_rol()) IN ('superadmin','admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)))`; `INSERT`/`UPDATE` `WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras') AND (select mismo_tenant(drogueria_id)))` — write side identical to `precios_proveedor` (`rls_final.sql:158-162`); `DELETE USING (select es_superadmin())`. Exception: `pcp_historial` has SELECT + INSERT policies only, same restricted SELECT role set. `GRANT SELECT, INSERT, UPDATE ... TO authenticated` (SELECT+INSERT for history), `+ DELETE TO service_role`, then `NOTIFY pgrst, 'reload schema'`. `trg_set_updated_at` on every table carrying `updated_at`. Routers use `require_roles()` as the authoritative check per `docs/reglas-globales.md` §2.3: `_ROLES_LECTURA_PCP = ("superadmin","admin","gerencia","compras")`, `_ROLES_ESCRITURA_PCP = ("admin","gerencia","compras")`.

### D12 — Suggestions are queries, not tables

`pcp-sugerencias` adds no schema. Quantity grouping: aggregate `pcp_renglones` joined to `pcp` where `estado <> 'cerrada'` and `fecha_entrega_solicitada` is within N days, grouped by `producto_id`, having more than one distinct `pcp_id`. Recent-price reuse: read the existing `v_precios_especiales_vigentes` (already filters `activa` + `mantenimiento_hasta >= CURRENT_DATE` and exposes supplier, quantity band and `dias_restantes`) filtered by `producto_id`. A bad heuristic becomes a query change, not a migration. Persisting accept/dismiss decisions stays S12.

## Data Flow

    presupuesto (Comercial)
         │  select renglones (item_proceso_id snapshot)
         ▼
    pcp ──1:N──► pcp_renglones ──N:M──► pcp_consultas ──► documentos (Jinja2→reportlab)
         │              │                     │                    │
         │              │                     └──► mensajeria port ─┘ (log | email | whatsapp)
         │              ▼
         │      pcp_renglon_resultados
         │         │ precio_obtenido → precios_proveedor (item_proceso_id) → pricing engine
         │         │ no_cotiza / sin_respuesta → outcome only, no price row
         ▼
    pcp_historial (append-only)  ◄── every state change, consulta, result, notification
         │  on cerrar_pcp
         └──► mensajeria.enviar_email (now) | notificaciones + generar_presupuesto_para_endpoint (later, flagged)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `supabase/migrations/0011_pcp_modelo.sql` (+ `.down.sql`) | Create | 7 tables, `precios_proveedor` FK columns + backfill, 2 view recreations, RLS/GRANTs/triggers, `upsert_pcp_legacy` |
| `services/pcp/{gestion,renglones,catalogo,negociacion,consultas,historial,imports,sugerencias}/` | Create | One sub-package per capability, `models`/`repository`/`service`/`router` |
| `services/pcp/{router,api,errors}.py` | Create | Router aggregator, unidirectional facade, module errors |
| `services/pcp/documentos/` | Create | `PdfRenderer` port + `reportlab` renderer + Jinja2 templates |
| `services/pcp/mensajeria/` | Create | `MensajeriaPort` + `LoggingMensajeriaAdapter` + `get_mensajeria()` |
| `services/presupuestacion/main.py` | Modify | `app.include_router(pcp_router, tags=["pcp"])` |
| `services/presupuestacion/notificaciones/models.py` | Modify | Add `pcp_cerrada` to `TipoNotificacion` (later slice) |
| `services/presupuestacion/core/config.py` | Modify | `PCP_MENSAJERIA_ADAPTER`, `PCP_REPRICING_AUTOMATICO` |
| `docs/modulos/pricing/pendientes.md` | Modify | Close the P1(4) `precios_proveedor` dead-write gap |
| `docs/modulos/pcp/` | Create | Module docs per project convention |
| `tests/pcp/test_dependencias.py` | Create | `ast` check of the D1 import rule |

## Interfaces / Contracts

```python
# services/pcp/mensajeria/port.py
class MensajeAdjunto(BaseModel):
    nombre: str
    contenido: bytes
    content_type: str = "application/pdf"

class ResultadoEnvio(BaseModel):
    entregado: bool
    proveedor_externo: str            # adapter id; "log" when nothing was sent
    referencia_externa: str | None = None
    error: str | None = None

class MensajeriaPort(Protocol):
    def enviar_email(self, *, destinatario: str, asunto: str, cuerpo: str,
                     adjuntos: Sequence[MensajeAdjunto] = ()) -> ResultadoEnvio: ...
    def enviar_whatsapp(self, *, destinatario: str, plantilla: str,
                        variables: Mapping[str, str],
                        adjuntos: Sequence[MensajeAdjunto] = ()) -> ResultadoEnvio: ...
```

Recipients are always resolved from `terceros_contactos` / `usuarios` inside the tenant — never from client-supplied input — so no adapter can be pointed at an arbitrary address.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | State machine transitions, `ck_ppr_resultado` invariant in the service, grouping/reuse suggestion logic, `PdfRenderer` output is a valid PDF | pytest with fake repositories, `pytest-mock` |
| Unit | D1 import rule | `ast` walk over `services/pcp/**`, mirroring `tests/terceros/test_dependencias.py` |
| Integration | `upsert_pcp_legacy` idempotency (same payload twice → 0 duplicates), `no_cotiza` writes no `precios_proveedor` row, `precio_obtenido` is picked up by `buscar_precio_especial_puntual`, `pcp_historial` UPDATE is denied, tenant isolation per RLS policy | Supabase test project, `execute_sql` fixtures |
| Integration | `plazo_pago_dias` backfill produces one `condiciones_pago` row per distinct value per droguería; both views still resolve | migration applied on a seeded copy |
| E2E | Router role matrix (`require_roles`) for read vs. write endpoints; close-PCP path with the logging adapter | `httpx` against the FastAPI app |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. Outbound messaging is a network integration behind a port whose default adapter sends nothing; recipient addresses are never client-supplied (see Interfaces).

## Migration / Rollout

Slice order, each independently deliverable: (1) `0011_pcp_modelo.sql` schema + RLS; (2) `pcp-gestion`/`pcp-renglones`/`pcp-historial`; (3) `pcp-catalogo-proveedores`; (4) `pcp-negociacion` + `plazo_pago_dias` FK migration; (5) `pcp-legacy-import`; (6) `pcp-consultas-agrupadas` internal grouping + PDF; (7) `pcp-sugerencias`; (8) outbound delivery adapter (last, droppable). Rollback: drop the seven tables (nothing outside `services/pcp/` reads them) and revert the two views; `plazo_pago_dias` survives nullable for one release, so reverting slice 4 is code-only. **The migration MUST be authored against live schema verified through Supabase MCP `list_tables`/`execute_sql`** — `docs/schema/extractor_final.sql` is known stale and this design was written from it plus migration 0008.

## Open Questions

All four resolved by the user after this design's first draft:

- [x] **Legacy PCP export contract.** Confirmed: the export carries a renglón-level code/identifier. `item_proceso_id` resolves via a matching step during import (D8); exact field name/matching rule to be confirmed against the real export file during `sdd-tasks`/`sdd-apply`.
- [x] **Multiple open PCPs per presupuesto?** Confirmed: no. `UNIQUE (presupuesto_id) WHERE estado <> 'cerrada'` added to `pcp` (D2).
- [x] **PCP read visibility.** Confirmed: restricted to `compras`/`gerencia`/`admin` (+ `superadmin` per standing convention) — narrower than the tenant-wide draft. Updated in D11; D2's cost-column rationale corrected accordingly.
- [x] **PDF library licensing.** Confirmed: not PyMuPDF (AGPL). Switched to `reportlab` (BSD) in D9, accepting the new dependency.
