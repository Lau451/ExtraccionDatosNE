# Feature: Legacy presupuestos import screen (CSV)

## Objective
Let write-role users (admin, gerencia, compras) import the legacy presupuestos CSV exported by Progress from the UI, instead of calling `POST /pcp/imports/presupuestos-legacy` by hand. Backend is already merged (PR #55, `6aedef3`).

## Why
Presupuestos must be loaded so purchase-order matching works on real data. The PCP import is NOT used for now (user, 2026-09-24): the team is working on purchase orders. The presupuestos import is standalone and does not depend on PCP.

## Decisions (parent defaults, reversible)
- Route `/presupuestos/importar`, gated with `PCP_WRITE_ROLES` (same roles as the endpoint). Sidebar item "Importar presupuestos" visible only to those roles; the disabled "Presupuestos" placeholder stays as is.
- CSV parsed in the browser (no new dependency): header row with the column names; delimiter auto-detected (`;` or `,`); quoted fields supported; UTF-8 with or without BOM. Unknown columns (e.g. `subtotal_renglon`) are ignored. Decimal comma accepted (`1250,50`). `fecha_generacion` accepts `dd/mm/yyyy` or ISO and is sent as ISO `yyyy-mm-dd`. Empty optional values → omitted/null.
- Client-side validation before sending: required columns present; per-row errors (renglón not an integer, cantidad not numeric, missing numero_presupuesto/descripcion/codigo_cliente) listed with CSV line numbers; nothing is sent if there are errors.
- Preview before import: number of presupuestos and rows detected. Result table per presupuesto: número, acción (creado/existente), renglones procesados, renglones sin producto.
- Backend errors (404 unknown client, etc.) show the backend `detail` message, not a generic text.

## Scope / constraints
- Frontend only. TDD strict with vitest (`pnpm test` in `frontend/`), `tsc --noEmit` clean.
- Branch `feat/presupuestos-legacy-import-ui` from `dev` (6aedef3).

## Tasks
- [x] T1 (delegated — writer trigger: parser + api + screen + route + sidebar) CSV parser (pure, unit-tested), API client, screen (container/presentational), route, sidebar entry, tests.

## Progress / evidence
- T1 — commit `7d41689` (9 files, +866/-1). Parser `features/presupuestos-import/parsearCsvPresupuestos.ts` (RFC4180 tokenizer, BOM, CRLF, `;`/`,` auto-detect, decimal comma, ambiguous '.'+',' → error, dd/mm/yyyy → ISO, proceso_comercial must be 1/2). Container + view, route `/presupuestos/importar` (PCP_WRITE_ROLES), sidebar item, API fn in `lib/api/pcp.ts`, routeTree regenerated (only new-route hunks). RED→GREEN: parser 15 tests, screen 5 tests. `pnpm test` 34 files / 266 passed; `tsc --noEmit` clean; `pnpm build` clean. Parent spot check: `vitest run src/features/presupuestos-import` 20 passed. Note: razon_social_cliente not checked per row (backend accepts empty; only used for the synthesized proceso name).
- Review assess (base 6aedef3): medium, 867 lines → slice_budget_reached; START lineage `review-877caf56cec6cc25`; user granted → reliability approved → acknowledged. Advisory: file-read race, calendar date validation, unterminated quote, physical line numbers → T1b (delegated). OPEN product question: a lone '.' number ('1.250') parses as 1.25 — Argentine exports usually use '.' as thousands separator → silent 1000x error. Waiting on the user for the real Progress number format.

## Tasks (added)
- [x] T1b (delegated) review follow-ups 1-4 above — commit `492bf56` (+210/-30): stale-read guard (monotonic ref), calendar date validation, unterminated-quote error, physical line numbers. RED→GREEN per item; `pnpm test` 273 passed, tsc + build clean.
- [x] T1c (inline — 1 fn + tests) — commit `dd06d7c`. RED: 7 failing (incl. updated happy path); GREEN: `pnpm test` 34 files / 282 passed; `tsc --noEmit` clean; `pnpm build` clean. Error text now shows the expected format. Assess (base 7d41689): medium, 301 lines, under_budget → no review due. Decimal-comma decision in "Decisions" above is SUPERSEDED by this. Number format — user answered 2026-09-24: Progress exports decimal '.' and thousands ',' (e.g. `1,250.50`). Accept `^\d+(\.\d+)?$` and `^\d{1,3}(,\d{3})+(\.\d+)?$` (strip commas); anything else (e.g. `1,25`, `1.250,50`) → per-row error. Starts after T1b (same file).

- Delivery: user approved → PR #56 merged into `dev` (`fa1550a`), branch deleted.

- T1d (inline, 2026-09-25) — user CORRECTED the number format: Progress exports decimal comma and NO thousands separator (`1250,50`). T1c's dot-decimal rule superseded. Accept only `^-?\d+(,\d+)?$`; anything else is a row error. RED: 7 failing; GREEN: `pnpm test` 283 passed, tsc + build clean. Branch `fix/presupuestos-import-decimal-comma`, PR #57 merged into `dev` (`c7ce675`), branch deleted.

## Next step
User tries a real Progress CSV at `/presupuestos/importar`.
