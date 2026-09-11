# Exploration: PCP Frontend (pcp-frontend)

## Current State

`services/pcp/` (FastAPI, mounted in `services/presupuestacion/main.py:64`, same base URL the frontend already calls via `presupuestacionFetch`) has 10 sub-packages, but only **7 expose an HTTP router**; 3 are internal-only.

### HTTP-exposed (aggregated in `services/pcp/router.py`)

- `gestion/router.py` — POST `/pcp`, GET `/pcp` (estado/fecha filters), GET `/pcp/{pcp_id}`, PATCH `/pcp/{pcp_id}/estado`. `EstadoPcp = nueva|en_gestion|esperando_respuesta|cerrada`.
- `renglones/router.py` — POST/GET `/pcp/{pcp_id}/renglones`, GET `.../renglones/{renglon_id}` (detail enriched with producto + supplier catalog), POST `.../renglones/{renglon_id}/proveedores` (supplier selection to negotiate).
- `catalogo/router.py` — GET/POST `/pcp/catalogo/productos/{producto_id}/proveedores` (ad-hoc producto↔proveedor association).
- `negociacion/router.py` — POST/GET `.../proveedores/{proveedor_id}/resultado`, POST `/pcp/{pcp_id}/cerrar` (triggers server-side PDF + email + historial + repricing).
- `consultas/router.py` — POST `/pcp/consultas` (groups selected renglones by supplier, can create several consultas in one POST), GET `/pcp/consultas/{id}`, GET `.../pdf` (binary download), POST `.../enviar`.
- `sugerencias/router.py` — 2 read-only GETs (grouping by quantity, recent prices).
- `imports/router.py` — POST `/pcp/imports/legacy` (bulk idempotent import keyed by `codigo_legacy`).

### No HTTP router (3)

- `historial/` — service-level `agregar_evento`/`listar_eventos` only; a timeline UI would need a new endpoint (out of scope for a frontend-only change unless explicitly approved).
- `documentos/` — invoked internally by `consultas.service`; the only frontend touchpoint is the `/pdf` GET above, no dedicated feature needed.
- `mensajeria/` — `MensajeriaPort` with default adapter `LoggingMensajeriaAdapter` (env var `PCP_MENSAJERIA_ADAPTER=log`, no-op): the "enviar consulta" button will appear to succeed without delivering anything until a real adapter is configured — a backend limitation, not fixable from the frontend.

### Roles (`services/pcp/roles.py`, single pair reused by all 7 routers)

```python
ROLES_LECTURA_PCP = ("superadmin", "admin", "gerencia", "compras")
ROLES_ESCRITURA_PCP = ("admin", "gerencia", "compras")
```

**Discrepancy found**: the archived `gestor-pcp` `design.md` (D11) documented 6 read roles including `lider_comercial`/`comercial`, but the shipped `roles.py` only implements 4, excluding both. This determines whether those two roles see the PCP nav item — needs explicit confirmation in `sdd-propose`.

### Frontend reference pattern (`terceros`/`productos`)

`lib/api/<resource>.ts` over `presupuestacionFetch` → `features/<feature>/roles.ts` (`READ_ROLES`/`WRITE_ROLES` + `puedeRol`) → `Gestion<Feature>.tsx` (TanStack Query list) + `<Entidad>Detalle.tsx` + colocated dialogs → routes `_authenticated.<feature>.tsx` (layout+guard) / `.index.tsx` / `.$id.tsx`. Terceros/Productos do NOT gate their nav item because their `READ_ROLES` cover all 6 business roles; PCP (4 roles) would need explicit nav gating, same pattern as the Usuarios/Empresas items in `Sidebar.tsx`. Tests: Vitest + Testing Library, colocated.

### Backend build order (reference, Engram `sdd/gestor-pcp/tasks`, obs #536)

historial → gestion → renglones+router → catalogo → negociacion → imports → consultas → sugerencias → mensajeria → docs (11 PR units, 96 tasks).

## Affected Areas

- `frontend/src/lib/api/pcp.ts` — new, typed client for the 7 routers.
- `frontend/src/features/pcp/` — new, roles.ts + components.
- `frontend/src/routes/_authenticated.pcp*.tsx` — new, layout+index+`$pcpId`.
- `frontend/src/features/shell/Sidebar.tsx` — modified, one role-gated nav item.
- Nothing in `services/pcp/**` is touched — pure consumer of an already-archived, stable API.

## Approaches

1. **Single change `pcp-frontend`** covering all 6 real UI modules with tasks in chained PRs (same pattern as `gestor-pcp`). Pros: one exploration/proposal/design covers the whole domain. Cons: large proposal/design/tasks, risk of exceeding the per-PR review budget if chaining isn't done well. Effort: High.
2. **Split into 2-3 SDD changes** (core: gestion+renglones+catalogo+negociacion; consultas+sugerencias; legacy import). Pros: each change independently verifiable/archivable. Cons: coordination of shared `roles.ts`/`pcp.ts` across changes. Effort: Medium x 2-3 full iterations.
3. **MVP-first**: only the negotiation loop (gestion+renglones+catalogo+negociacion), consultas/sugerencias/import as follow-up. Pros: fast value. Cons: negotiation flow has no way to group/send a consulta from the UI yet. Effort: Low-Medium for v1.

## Recommendation

Approach 1, aligned with how the backend was built and with the user's explicit choice to use full SDD given the scope — but `sdd-propose` must first resolve role-gating and the `historial` scope (open questions below) before fixing PR order.

## Open Questions for sdd-propose

1. Role-gating: replicate the current 4 roles in `roles.py` as-is (nav gated), or treat the missing `lider_comercial`/`comercial` as a separate gap to raise?
2. Single `pcp-frontend` change or split into several?
3. Does `historial` need a UI? If yes, it requires a new backend endpoint — in scope for this change or out?
4. Confirmed: `documentos` needs no dedicated feature, just a download button — agreed?
5. Should the "Enviar consulta" button warn that delivery is simulated (no-op adapter) until a real `mensajeria` adapter is configured?
6. Dedicated legacy-import screen, or low priority/deferred?
7. `sugerencias` as inline badges or a separate panel?
8. Suggested build order (not fixed): gestion → renglones → catalogo → negociacion → consultas → sugerencias → imports.

## Risks

- If `historial` is decided to need a UI, the change stops being "frontend-only" and touches the backend (new router), changing scope and declared review budget.
- Replicating the current `roles.py` without resolving the discrepancy with `design.md` silently locks in behavior the original design considered different.
- `mensajeria` without a real adapter leaves "enviar consulta" visually complete but with no effect in production — out of scope for this change.
- 7 write endpoints + 6 screens is comparable in size to the backend itself (11 PR units) — `sdd-tasks` must forecast a similar split.

## Ready for Proposal

Yes — with the caveat that `sdd-propose` must present open questions 1-3 to the user before fixing `proposal.md`, not assume defaults.
