# SDD Research: PCP Frontend (pcp-frontend)

## Executive Summary

Established B2B comparison UX (SAP Fiori's "Comparison Pattern", uxpatterns.dev) converges on a **column-per-supplier, row-per-criterion** table layout with sticky row labels, a highlighted "selected/winner" column, and explicit decision CTAs — this is the dominant pattern for "N supplier offers per line item, pick a winner" flows, not row-per-offer. RFQ-specific tools standardize comparison columns as supplier, unit price, quantity, lead time, and payment/delivery terms. Multi-stage negotiation status is typically shown via discrete stage indicators (Kanban-style columns or a linear stepper) with color/fill encoding completion state per stage.

TanStack Router officially supports arbitrarily deep dynamic segments (`$postId/$revisionId`-style) with parent params automatically inherited into child `useParams()`, and recommends loaders as thin fetch-triggers (`ensureQueryData`/`prefetchQuery`) consumed via live `useQuery`/`useSuspenseQuery` hooks, never `useLoaderData` alone.

TanStack Query documents two optimistic-update strategies (UI-variables vs. cache `setQueryData` with onMutate/onError rollback), but a documented, reproducible defect class shows `cancelQueries()` cannot prevent an already-in-flight stale response from clobbering an optimistic update — directly relevant to the close-PCP cascade, where `onSuccess` cache-merge is safer than blind `invalidateQueries()`.

## Sources

| ID | Class | Title | Publisher | URL | Accessed | Excerpt |
|----|-------|-------|-----------|-----|----------|---------|
| S1 | documentation | Routing Concepts | TanStack Router Docs | https://tanstack.com/router/latest/docs/routing/routing-concepts | 2026-09-07 | Dynamic segments (`$`) capture into `params`; child routes inherit parent params via `Route.useParams()`. |
| S2 | documentation | Optimistic Updates | TanStack Query React Docs (v5) | https://tanstack.com/query/v5/docs/react/guides/optimistic-updates | 2026-09-07 | Two approaches: UI-variables vs. cache `setQueryData` with cancel→snapshot→update→rollback-on-error. |
| S3 | open-web | Comparison Table Pattern | UX Patterns for Developers (uxpatterns.dev) | https://uxpatterns.dev/patterns/data-display/comparison-table | 2026-09-07 | Column-per-option, row-per-feature structure; sticky labels; mobile fallback required. |
| S4 | open-web | TanStack Router and Query | tkdodo.eu (TanStack Query maintainer blog) | https://tkdodo.eu/blog/tan-stack-router-and-query | 2026-09-07 | Loader merely triggers the Query early; always consume via a live Query hook, not `useLoaderData` alone. |
| S5 | open-web | Optimistic updates getting overwritten by stale refetch | GitHub Discussions, TanStack/query #10712 | https://github.com/TanStack/query/discussions/10712 | 2026-09-07 | `cancelQueries()` doesn't guarantee an already-resolved stale response won't update the cache afterward; merge server response in `onSuccess` instead of blanket `invalidateQueries()`. |
| S6 | open-web | Comparison Pattern | SAP Fiori Design System | https://www.sap.com/design-system/fiori-design-web/v1-120/ui-elements/comparison-pattern | 2026-09-07 (search snippet; direct fetch returned HTTP 403) | Select items from a list, display side-by-side to compare characteristics. |
| S7 | open-web | RFQ Software for Procurement Teams | Quotable AI | https://getquotable.ai/rfq-software | 2026-09-07 (search snippet) | RFQ comparison columns: supplier, item description, quantity, unit price, line total, lead time, payment/delivery terms. |
| S8 | open-web | Workflow visualization in a multi-tenant management platform | USPTO Patent 11,907,880 | https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11907880 | 2026-09-07 (search snippet) | Multi-stage workflow UI encodes each stage's completion via color, size, text, and fill. |

## Claims

**Q1 — supplier RFQ / negotiation comparison UX**
1. Dominant B2B comparison-table layout is column-per-option (per-supplier) and row-per-criterion, not row-per-offer — [S3, S6].
2. Supports a highlighted "recommended/selected" column and decision CTAs, matching a "pick a winner" interaction — [S3].
3. RFQ-domain columns: supplier name, item description, quantity, unit price, line total, lead time, payment/delivery terms — [S7].
4. Multi-stage status commonly rendered as discrete per-stage indicators, color/fill encoding completion — [S8].
5. Comparison tables need explicit loading/empty/error states and a deliberate non-tabular mobile fallback — [S3].

**Q2 — TanStack Router nested master-detail routes**
6. Dynamic segments at every path level (`$` prefix) compose into one shared `params` object — `/pcp/$pcpId/renglones/$renglonId` gets both IDs merged and accessible from the child route — [S1].
7. Route context/layout routes are inherited parent→child, an official mechanism to pass parent-loaded data (the PCP record) down to nested renglon routes — [S1].
8. Loader = thin trigger (`ensureQueryData`/`prefetchQuery`) that primes the cache; actual consumption happens via `useQuery`/`useSuspenseQuery` hooks inside components — [S4].
9. Consuming only via `useLoaderData` (bypassing a live Query hook) loses Query's active-observer tracking, affecting refetch/invalidation behavior — [S4].

**Q3 — TanStack Query optimistic updates for multi-step/cascading mutations**
10. Two documented strategies: transient UI-variables vs. direct cache mutation via `onMutate`/`setQueryData` with `onError` rollback from a snapshot — [S2].
11. Confirmed reproducible issue: `cancelQueries()` only aborts still-cancellable fetches; an already-resolved stale response can still land in cache after an optimistic update, causing a visible flash-back — [S5].
12. Mitigation: merge the server response directly into cache in `onSuccess` rather than relying solely on `invalidateQueries()`, keeping related query-key entries for the same entity synchronized together — [S5].

## Gaps

- No official TanStack docs found addressing invalidation strategy for a single mutation that triggers server-side cascading side effects across unrelated resource types (PDF generation, email, historial, repricing) — S5 covers single-entity stale-read races, not multi-resource cascades. Needs design-phase judgment.
- SAP Ariba/Coupa/Procurify product UX docs not directly fetchable in this pass; comparison-pattern evidence is directional (Fiori + RFQ-vertical marketing pages), not primary specs from those named tools.
- `prefetch: 'intent'` hover-prefetch behavior was only surfaced via WebSearch synthesis, not verified against fetched TanStack Router doc content — flag for verification if design relies on it.

## Risks

- Naive `invalidateQueries()` on the close-PCP cascade risks the stale-overwrite race documented in S5 — a visible regression on "cerrar PCP" (status reverting/flashing after close).
- Generic comparison-table layout without a defined mobile/narrow-viewport fallback (per S3) risks an unusable renglones/negociacion screen at reduced widths.

## Next Recommended

`sdd-propose`: draft the PCP frontend proposal incorporating the column-per-supplier comparison table for renglones/negociacion, a discrete per-stage status indicator for the negotiation state machine, nested `$pcpId/$renglonId` routing with parent-context inheritance, and an explicit `onSuccess`-merge (not blanket invalidate) strategy for the close-PCP cascade mutation.
