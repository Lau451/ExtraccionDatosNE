# Proposal: Gestor de PCP (supplier price-improvement requests — Compras)

> "PCP" is kept as the untranslated domain term. It is NOT an "orden de compra": the deferred
> `orden-compra` change models client→droguería sales orders. No table, name, or code is shared.

## Intent

A PCP is a price-improvement request raised from a commercial presupuesto. Today Comercial picks the
renglones by hand and Compras negotiates them outside the system: no central worklist, no supplier
catalog, no traceable negotiation history, and one ad-hoc query per product instead of one per
supplier. This change centralizes the flow in a Compras-owned module, records every negotiation
outcome, and shapes the schema so future rule-based PCP generation needs no rework.

## Scope

### In Scope

- New `pcp` module (header + renglones), 1:1 with a single `presupuesto`; states `nueva` →
  `en_gestion` → `esperando_respuesta` → `cerrada`; list view with filters, primarily by Comercial's requested
  delivery date.
- Renglón identity anchored on `item_proceso_id` (never `presupuesto_items.id`, which is
  DELETE+INSERT'd on every presupuesto regeneration — RN-PRICING-008).
- `origen` discriminator on renglón selection (`manual` | `regla` | `import_legado`) so the manual
  toggle, the legacy import, and future automatic rules coexist.
- Legacy import path for PCPs, keyed by `codigo_legacy` upsert, mirroring the
  `upsert_terceros_legacy` + `terceros_legacy_map` pattern. This is how the module gets real data on
  day one.
- New producto↔proveedor association table (a real supplier catalog per product).
- Negotiation result written to the existing, currently unwritten `precios_proveedor`
  (`item_proceso_id`-scoped rows, already verified never to touch `costos_productos`). Modelled as a
  real outcome type: `precio_obtenido` | `no_cotiza` | pendiente.
- Migrate `precios_proveedor.plazo_pago_dias` (raw INTEGER) to the
  `condicion_pago_id` / `forma_pago_id` FK pattern from `terceros/catalogos/`.
- Dedicated PCP history table (the closed 5-entity `EntidadAuditable` Literal stays untouched).
- Grouped supplier query: several products of one supplier, across one or many PCPs, become a single
  consulta — with real outbound delivery (PDF + email + WhatsApp Business API to the supplier
  contact).
- Multi-tenant `drogueria_id` + `mismo_tenant()` / `get_rol()` RLS; write access for `admin`,
  `gerencia`, `compras`, matching `precios_proveedor` RLS exactly, plus router-level
  `require_roles()`.
- Feedback loop to Comercial when a PCP closes, phased like the origin path:
  - **Now** (legacy system still primary): email the closed PCP's result PDF to the requesting
    Comercial user's mailbox.
  - **Later** (once `presupuestacion` is the system of record): an internal notification (reusing
    the existing `services/presupuestacion/notificaciones/` module) that the PCP is ready, AND
    closing the PCP automatically triggers repricing of the still-open originating presupuesto for
    the affected renglones (today `POST /procesos/{id}/generar-presupuesto` is a manual, Comercial-
    triggered action — this is a new automatic invocation path, not a UI change to that action).
- Two intelligence features confirmed for v1 (per the user's spec, these were described "from the
  start," with a concrete suggestion dialog, not under the later "future" list — corrected from the
  first draft, which had misclassified them as deferred suggestions):
  - **Quantity-grouping suggestion**: detect the same article across several PCPs nearing their
    requested delivery date and suggest a joint quote with the aggregated quantity. Suggestion only —
    it never merges or restructures PCP records; Compras decides and requests manually.
  - **Recent-price-reuse suggestion**: detect an already-negotiated, still-valid `precios_proveedor`
    row for an article and surface it as a reference (supplier, date, `mantenimiento_hasta`, quantity
    band) when a new PCP renglón for that article is opened.

### Out of Scope

- The PCP auto-generation rules engine itself. It gets its own PCP-owned rules subsystem later
  (spirit of `reglas_pricing`: drogueria-scoped, priority-ordered, NULL scope = default), explicitly
  NOT the generic `automatizaciones` engine and NOT `reglas_pricing`. Only the schema seams land now.
- The presupuestador "es PCP" per-renglón toggle UI (arrives when `presupuestacion` becomes the
  system of record; `origen='manual'` already accommodates it).
- Every item in "Suggestions for Evaluation" below.
- Any change to `costos_productos` or general product costing.

## Capabilities

### New Capabilities

- `pcp-gestion`: PCP header, state machine, listing and filters, tenancy and role access.
- `pcp-renglones`: renglón detail, product/supplier context, supplier selection (one/several/all).
- `pcp-catalogo-proveedores`: producto↔proveedor association powering "proveedores disponibles".
- `pcp-negociacion`: negotiation outcome recording into `precios_proveedor` (price, supplier,
  conditions, `mantenimiento_hasta`, payment terms, notes) including the `no_cotiza` outcome.
- `pcp-consultas-agrupadas`: cross-PCP grouping into one supplier consulta + outbound delivery.
- `pcp-historial`: dedicated, append-only PCP management history.
- `pcp-legacy-import`: `codigo_legacy`-keyed idempotent PCP import from the legacy system.
- `pcp-sugerencias`: quantity-grouping and recent-price-reuse suggestions (confirmed v1 scope, see
  above), plus the Comercial feedback loop (email now / internal notification + auto-repricing later).

### Modified Capabilities

- None. No existing spec in `openspec/specs/` changes its requirements; `catalogos-comerciales` is
  consumed, not modified.

## Approach

Ship as a new sibling module following the `terceros/` and `productos/` extraction pattern
(`models` / `repository` / `service` / `router`); final placement (`services/pcp/` vs. under
`services/presupuestacion/`) is a design decision. Schema is additive except the
`plazo_pago_dias` FK migration. Reuse over invention: `precios_proveedor` becomes its first real
writer, and `v_compras_vs_cotizado` (already joining real purchases against quoted prices) is the
natural read side for price-history intelligence.

Sequence the work so the delivery integration is the last, independently droppable slice: schema +
module + import + negotiation recording must not be blocked by the unresolved messaging vendors.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `services/pcp/` (new) | New | PCP module: models, repository, service, router |
| `docs/schema/` + migrations | Modified | New PCP tables, supplier catalog, `plazo_pago_dias` FK migration, RLS |
| `services/presupuestacion/pricing/repository.py` | Modified | Loses its documented `precios_proveedor` read-only invariant |
| `services/presupuestacion/presupuestos/` | Read-only dep | Origin of PCP-eligible renglones |
| `services/terceros/` | Read-only dep | Proveedor identity, contacts, `condiciones_pago`/`formas_pago` |
| `services/productos/` | Read-only dep | Product context for the renglón detail view |
| New outbound messaging adapter | New | Email + WhatsApp Business API; vendor undecided |
| `docs/modulos/pricing/pendientes.md` | Modified | Closes P1(4) dead-write gap |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Messaging vendors undecided (email + WhatsApp Business API) | High | Isolate delivery as the last slice behind an adapter interface; resolve in `sdd-design` or a dedicated research pass |
| WhatsApp Business needs a verified number, template approval, and a verified sending domain — lead time outside our control | High | Start provisioning in parallel with implementation; the module ships usable without it |
| FK churn if any table references `presupuesto_items.id` | Medium | Hard rule: anchor on `item_proceso_id`; enforce in spec and review |
| `docs/schema/extractor_final.sql` is known stale | Medium | Verify live schema via Supabase MCP `list_tables` / `execute_sql` before writing migrations |
| Legacy PCP export format unknown | Medium | Confirm the legacy contract before the import slice; the rest of the module does not depend on it |
| Supplier catalog starts empty | Medium | Seed from existing `precios_proveedor` history + allow ad-hoc supplier addition during a PCP |
| Terminology confusion with `orden-compra` | Low | No `orden`/`OC` naming anywhere in this module; note it in every spec |

## Rollback Plan

All new tables are additive and isolated: dropping the PCP tables plus the supplier catalog leaves
every existing flow untouched, because nothing outside the module reads them. The single non-additive
step is the `precios_proveedor.plazo_pago_dias` migration — keep the original column in place
(nullable, unused) through at least one release after backfill so reverting is a code-only rollback,
and drop it in a separate later change. The outbound delivery adapter is feature-flagged, so
disabling the flag reverts to internal-only grouping without any schema change.

## Dependencies

- **Open, named**: concrete email provider and concrete WhatsApp Business API provider. Deliberately
  not decided here (the user chose to skip a research pass). New external integration surface, new
  recurring cost, new setup prerequisites. Must be resolved by `sdd-design` or a dedicated research
  pass before the delivery slice only.
- Legacy system's PCP export contract (fields, `codigo_legacy` semantics, transport).
- Existing `terceros/catalogos/` `condiciones_pago` / `formas_pago` rows must cover the payment terms
  Compras actually negotiates.
- Live Supabase schema verification before migration authoring.

## Success Criteria

- [ ] Compras sees every PCP in one list, filterable by Comercial's requested delivery date.
- [ ] Opening a PCP shows its renglones; each renglón shows product context and available suppliers.
- [ ] A negotiation outcome (price, supplier, conditions, `mantenimiento_hasta`, payment terms, notes)
      or an explicit `no_cotiza` can be recorded per renglón and is preserved in history.
- [ ] Recording a result never modifies `costos_productos` or any other renglón's price.
- [ ] Products of the same supplier across one or several PCPs group into a single consulta.
- [ ] Legacy PCPs import idempotently: re-running the same import creates no duplicates.
- [ ] `origen` is populated on every renglón selection; adding an automatic-rule source later requires
      no schema change.
- [ ] No PCP table references `presupuesto_items.id`.
- [ ] Write access is restricted to `admin`, `gerencia`, `compras` at both router and RLS level.

---

## Suggestions for Evaluation

Per the user's own rule, everything below is a **suggestion to evaluate, never a confirmed
requirement**, and must not be implemented without explicit validation. None of it is in scope above.

**From the user's stated intelligence list**

> S1 (quantity consolidation) and S2 (recent-price reuse) were promoted to confirmed v1 scope above
> (`pcp-sugerencias`), not left here — the user's original spec described them "from the start," with
> a concrete suggestion dialog, distinct from the more speculative list below. Numbering below kept
> as S3+ to avoid re-numbering churn against earlier review rounds.

- **S3 — Alternative suppliers.** Flag a supplier who historically improves at least one condition
  (price, payment term, maintenance window) for that article.
- **S4 — Price-vs-history deviation alert.** Warn when a newly recorded price departs sharply from
  that article's own history.
- **S5 — PCPs nearing the requested delivery date.** Follow the `v_calendario` `vencido` CASE pattern
  already in the codebase rather than inventing a new one.
- **S6 — Stale PCPs.** Flag PCPs with no management activity for N days.
- **S7 — Recurring articles across PCPs.** Highlight articles that keep reappearing — candidates for a
  framework agreement instead of repeated one-off negotiation.
- **S8 — Supplier historical performance.** Per article or category: response rate, `no_cotiza` rate,
  average improvement obtained, average response time.
- **S9 — Data-inconsistency detection.** Expired `mantenimiento_hasta`, missing supplier contact,
  duplicate renglones, article with no supplier in the catalog.
- **S10 — Volume negotiation opportunities.** Detect when aggregated quantity crosses a supplier's
  known `cantidad_minima`/`cantidad_maxima` band.

**Additional, identified while writing this proposal**

- **S11 — Feedback loop back to Comercial.** When a PCP closes, notify the requesting user/sector and
  optionally propose repricing the originating presupuesto with the improved cost. The spec asks for
  "results sent back to Comercial" but never says how; this is the biggest unmodelled gap.
- **S12 — Every suggestion is auditable.** Persist each suggestion with the reason it fired plus the
  user's accept/dismiss decision. Without this, suggestion quality can never be measured — and it is
  exactly the training data a future rules engine needs.
- **S13 — Suggestions as a read-only projection.** Compute them as views/queries over PCP and pricing
  data rather than materialized tables, so a bad heuristic is a query change, not a migration.
- **S14 — Response deadline on grouped consultas.** Record when a consulta was sent and what response
  window was expected; this powers S6, S8, and any future automatic follow-up.
- **S15 — Renglón-level partial closing.** Let a PCP close when every renglón is resolved, rather than
  requiring a manual state change — reduces the stale-PCP problem at the source.
- **S16 — Seed the supplier catalog from history.** Bootstrap producto↔proveedor from existing
  `precios_proveedor` and `compras_proveedor` rows so the catalog is not empty on day one.
- **S17 — Grouping preview before sending.** Show the Compras user exactly what will be sent to each
  supplier, with per-supplier confirmation, before any outbound message leaves the system.
