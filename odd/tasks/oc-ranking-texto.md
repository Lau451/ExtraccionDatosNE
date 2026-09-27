# OC budget ranking with description similarity

## Objective

Rank candidate budgets for a purchase order by price **and** description, so coincidental price matches in unrelated budgets stop outranking the right one.

## Problem

`rankear_presupuestos_candidatos` (`services/presupuestacion/oc_presupuesto/service.py`) scores a budget by how many OC lines share an exact unit price with any of its lines. As a client accumulates budgets, common prices match by chance. Date cannot be used: OCs can arrive up to 6 months after the budget. Budget `estado` cannot be used: legacy-imported budgets are always `generado`. `producto_id` cannot be used: the legacy import never resolves it.

## Scope

- Backend: ranking service, repository (descriptions for price-matched budget lines), `CandidatoPresupuesto` model.
- Frontend: mirror type in `frontend/src/lib/api/ocMatching.ts` and the candidate label in `SelectorPresupuesto`.
- Out of scope: line-level vinculación (`_candidatos_para_renglon`), price filter semantics, date tie-break.

## Design

1. Exact price stays the mandatory filter.
2. Primary score: OC lines whose price matches a line of the budget **and** whose best description similarity against those price-matched lines is ≥ 70 (`fuzz.WRatio` over `normalizar_descripcion`, same machinery and threshold as `matching/service.py::_UMBRAL_SUGERIDO`).
3. Secondary score: price-only matches (current score).
4. Tie-break: `generado_at` desc, then id (unchanged).
5. Text only reorders, never filters: a price-only budget still appears.
6. New field `renglones_oc_con_coincidencia_texto` on `CandidatoPresupuesto`; existing `renglones_oc_con_coincidencia` keeps its meaning.

## Constraints

- TDD: strict (session config). Backend runner: `venv/Scripts/python -m pytest tests/oc_presupuesto -q`. Frontend runner: `npm test` in `frontend/`.
- Delivery strategy: `ask-on-risk`; chain strategy cached `feature-branch-chain`. Forecast ≈ 250–400 authored lines.

## Tasks

- [x] T1 — Backend: descriptions for price-matched budget lines + OC line descriptions; pure `_rankear_presupuestos` scores text+price then price; model field; tests.
- [x] T2 — Frontend: mirror type + candidate label shows both counts; tests.

## Acceptance criteria

- A budget matching fewer OC lines by price but more by price+description ranks above one with more price-only matches.
- Budgets with zero text matches still appear, ordered by price score.
- No extra query when the OC has no price matches.

## Checks

- `venv/Scripts/python -m pytest tests/oc_presupuesto -q` → 75 passed in 99s.
- `npm test` in `frontend/` → 373 passed (39 files).
- `npm run build` in `frontend/` → built ok (tsc passes, no CandidatoPresupuesto
  construction site left unmigrated).
- `npx oxlint src/features/oc-matching` in `frontend/` → clean, exit 0.

## Route

- T1–T2: delegated direct (writer trigger: backend + frontend, 2+ non-trivial files).

## Progress

- Branch `feat/oc-ranking-texto` from `dev` @ 0ec2571. Baseline: `tests/oc_presupuesto` 70 passed.
- T1 done — commit `b125cb0` (`feat(oc-presupuesto): rank candidate budgets by price and description`).
  - `_rankear_presupuestos` signature changed: `precios_oc: list[Decimal]` → `renglones_oc: list[dict]`
    (`{"precio_unitario": Decimal, "descripcion": str}`); return type changed
    `list[tuple[dict, int]]` → `list[tuple[dict, int, int]]` (`presupuesto, puntaje_texto,
    puntaje_precio`). Both callers (`rankear_presupuestos_candidatos`,
    `_top_presupuesto_sugerido`) and every pure-function test updated for the new shape
    (semantics of `renglones_oc_con_coincidencia` unchanged — it's `puntaje_precio`).
  - New: `_UMBRAL_SIMILITUD_TEXTO = 70`, `_mejor_similitud_texto`, `_renglones_oc`,
    `_presupuesto_items_con_descripcion` (guards the "no extra query without price
    matches" criterion) in `services/presupuestacion/oc_presupuesto/service.py`.
  - `repo.listar_oc_items_precios` now also selects `descripcion`.
  - `CandidatoPresupuesto.renglones_oc_con_coincidencia_texto: int` added to
    `services/presupuestacion/oc_presupuesto/models.py`.
  - `_top_presupuesto_sugerido` (used by the matching-screen fallback,
    `_resolver_presupuesto_activo`) updated to the same texto+precio ranking, so the
    suggested budget stays consistent between the candidates screen and the matching
    screen's auto-resolution — the docstring already claimed "mismo cálculo".
  - RED: 9 failing (`tests/oc_presupuesto/test_service.py -k "not integration"`) — 5
    pre-existing pure-function tests broken by the intentional signature change, plus 4
    new tests (3 pure-function acceptance-criteria tests a/b/d + 1 wiring test), 54
    passed, 3 deselected (integration marker name match).
  - GREEN: `venv/Scripts/python -m pytest tests/oc_presupuesto/test_service.py -q -k
    "not integration"` → 63 passed, 3 deselected.
  - Full suite (incl. integration, hits the real Supabase test project):
    `venv/Scripts/python -m pytest tests/oc_presupuesto -q` → 75 passed in 99s (baseline
    70 + 5 new tests; the `renglones_oc_con_coincidencia` integration assertion is
    unaffected since it reads the unchanged price score).
- T2 done — commit `6db50b6` (`feat(oc-matching): show price+description match count in
  candidate label`).
  - `renglones_oc_con_coincidencia_texto: number` mirrored in
    `frontend/src/lib/api/ocMatching.ts::CandidatoPresupuesto`.
  - `SelectorPresupuesto.tsx` label changed from `{con_coincidencia}/{totales}
    coincidencias` to `{con_coincidencia_texto} de {totales} por precio y descripción ·
    {con_coincidencia} por precio`.
  - RED: `npx vitest run src/features/oc-matching/components/SelectorPresupuesto.test.tsx`
    → 1 failed (new label-format test), 3 passed (fixtures updated for the new required
    field first, so only the new assertion was red).
  - GREEN: same command → 4 passed.
  - `OcMatchingDetalle.test.tsx` and `ColumnaPresupuesto.test.tsx` don't construct
    `CandidatoPresupuesto` objects (only `CandidatoVinculo`), so they needed no fixture
    changes; confirmed by the full suite and `npm run build` (tsc) below.

### Native review (RDD)

- Assess on `0ec2571..c5011ee`: risk `medium`, `review_due` (`slice_budget_reached`, 538 changed lines).
- Consent: granted. Lens: reliability. Outcome: approved and acknowledged (lineage `review-bb6dbad4b14ca583`). Reviewed boundary advances to `c5011ee`.
- Advisory (non-blocking) findings, follow-up candidates:
  - WARNING `service.py:422-424` — `_top_presupuesto_sugerido` (matching-screen fallback) now ranks text-then-price and reads `items_proceso`, but no test covers that path; only the candidates endpoint is tested end to end.
  - SUGGESTION `SelectorPresupuesto.test.tsx:80-81` — label assertions use partial regexes; assert the full label string.

### Review follow-ups (user-authorized)

- `944f634` → slice `8670990`: `test_top_presupuesto_sugerido_prioriza_texto_sobre_precio_como_el_ranking` covers the matching-screen fallback (text-first order, one `items_proceso` lookup).
- `921d695` → slice `e454d4e`: `SelectorPresupuesto` asserts the full label string.
- Characterization tests (behavior already existed): proven by mutation. Swapping the sort to price-first failed the backend test (1 failed); rendering totals instead of the price count failed the frontend test (1 failed). Code restored.
- `pytest tests/oc_presupuesto -q` → 76 passed; `npm test` → 373 passed; `npx oxlint src/features/oc-matching` clean.

## Delivery

- Strategy `ask-on-risk` → chain `feature-branch-chain` (cached user choice). Tracker PR (draft) `feat/oc-ranking-texto` → `dev`.
- `01-backend`: ranking + model + repository + tests (a1b5057, 2619117, 8670990). +467/-68 — over the 400 budget: 266 lines are tests and 80 the feature record; the ranking signature change and its tests cannot land apart. `size:exception` requested.
- `02-frontend`: mirror type + label + review record + label test (74f9423, 41ca543, b9d4daf, e454d4e, this record). ~+80/-4.
- Slices rebuilt by cherry-pick from the linear branch; final tree identical to it.
