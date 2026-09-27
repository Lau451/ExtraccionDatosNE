# OC matching screen usability

## Objective

Make the OC ↔ budget matching screen usable with long budgets (hundreds of lines).

## Problem

- Candidate radios in `RenglonOcFila.tsx` show the raw `presupuesto_item_id` UUID instead of line number + description.
- `ColumnaPresupuesto.tsx` renders every budget line as a flat list: no search, no filter, and highlighted candidates can be off-screen.
- The UI only offers price-matched candidates; the backend already supports manual links (`confirmar_vinculo` marks `vinculo_origen='manual'` when prices differ), but there is no way to pick an arbitrary budget line.

## Scope

Frontend only (`frontend/src/features/oc-matching/`). No backend or API contract changes.

## Constraints

- TDD: strict mode enabled (session config). Runner: `npm test` (vitest run) in `frontend/`. RED → GREEN → REFACTOR.
- Artifacts (code, UI copy, comments) follow the existing project language (Spanish UI copy).
- Delivery strategy: `ask-on-risk`. Forecast ≈ 300–450 authored changed lines.

## Tasks

- [x] T1 — Candidate radios show `Renglón N — descripción — $precio` (+ similitud) resolved from `renglones_presupuesto`.
- [x] T2 — Search box in the budget column filtering by description text or line number; "Solo candidatos" toggle when an OC line is selected.
- [ ] T3 — Selecting an OC line scrolls the first candidate into view in the budget column.
- [ ] T4 — Manual link: with a pending OC line selected, each budget line offers "Vincular a renglón N de la OC"; calls the existing `confirmarVinculo`.

## Acceptance criteria

- No UUIDs visible in the matching screen.
- A 300-line budget can be narrowed to the relevant lines by typing.
- A pending OC line with zero price candidates can be linked manually.

## Checks

- `npm test`, `npm run lint`, `npm run build` in `frontend/`.

## Route

- T1–T4: delegated direct (writer trigger: 3+ non-trivial files — `ColumnaPresupuesto.tsx`, `RenglonOcFila.tsx`, `OcMatchingDetalle.tsx` + tests).

## Progress

- Branch `feat/oc-matching-pantalla` from `dev` @ 9755396.
- TDD mode: strict (session config). Runner: `npm test` (vitest run) in `frontend/`.

### T1 — done
- Files: `frontend/src/features/oc-matching/components/RenglonOcFila.tsx`,
  `frontend/src/features/oc-matching/components/RenglonOcFila.test.tsx`,
  `frontend/src/features/oc-matching/components/ColumnaOrdenCompra.tsx`,
  `frontend/src/features/oc-matching/OcMatchingDetalle.tsx`.
- RED: added test asserting the multi-candidate label reads
  `Renglón 3 — Ibuprofeno 400mg x 20 — $1200 — 91% similitud` and that raw ids
  (`pi-1`, `pi-2`) are never in the document; failed with
  `Unable to find an element with the text: Renglón 3 — ...` (old markup still
  rendered `candidato.presupuesto_item_id`), 1 failed / 5 passed.
  Ran: `npx vitest run src/features/oc-matching/components/RenglonOcFila.test.tsx`.
- GREEN: added `presupuestoPorId: Map<string, RenglonPresupuesto>` prop
  threaded from `OcMatchingDetalle` (built via `useMemo` over
  `matching.renglones_presupuesto`, placed before the loading/error early
  returns to keep hook order stable) through `ColumnaOrdenCompra` into
  `RenglonOcFila`; replaced the raw id span with `etiquetaCandidato(...)`.
  Ran: `npx vitest run src/features/oc-matching` -> 4 files / 16 tests passed.
  `npx tsc --noEmit -p .` -> clean.
- Commit: `40ba8ba`.

### T2 — done
- Files: `frontend/src/features/oc-matching/components/ColumnaPresupuesto.tsx`,
  `frontend/src/features/oc-matching/components/ColumnaPresupuesto.test.tsx`
  (new).
- RED: new test file with 4 cases (text search, accent/case-insensitive, exact
  line-number search, toggle disabled without selection, toggle filters with
  selection) against the pre-T2 component; failed 4/4 —
  `Unable to find a label with the text of: /buscar en el presupuesto/i` (no
  search input existed yet). Ran:
  `npx vitest run src/features/oc-matching/components/ColumnaPresupuesto.test.tsx`.
- GREEN: added local `busqueda`/`soloCandidatos` state, `normalizarTexto`
  (NFD + strip diacritics) and `coincideBusqueda` helpers, a search `<input
  type="search">` and a "Solo candidatos" checkbox (disabled without
  `renglonOcSeleccionado`), and filtered the rendered list through
  `renglonesFiltrados` (useMemo). Ran: `npx vitest run src/features/oc-matching`
  -> 5 files / 20 tests passed. `npx tsc --noEmit -p .` -> clean.
- Note (environmental, pre-existing): `npm run lint` (oxlint) exits 1 on this
  branch and on the pre-T1 base (`git stash` + rerun reproduced identical exit
  code and error set) due to `react-hooks(rules-of-hooks)` errors in unrelated
  route files (`_authenticated.pcp.$pcpId.tsx` and 2 others) plus pre-existing
  warnings across the app. No lint errors or warnings under
  `src/features/oc-matching/`. Not introduced by this feature; out of scope
  for a frontend-only oc-matching change.
- Commit: (recorded after commit).
