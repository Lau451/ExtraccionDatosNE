# Feature: validar-extraccion-organizacion

Locator: `odd/tasks/validar-extraccion-organizacion.md` · Engram mirror: `odd/validar-extraccion-organizacion/tasks`
Branch: `feat/validar-extraccion-organizacion` (from `dev`)

## Objective

Organize the Validar extracción screen by document type, show the lifecycle state of every extraction, and let
each user narrow the list to the extractions they uploaded.

## Problem / why

- One "pending" table mixes Licitación, Directa, Comparativa and Orden de compra; type is only a text column.
- State is invisible: the listing endpoint filters `status IN ('completed','partial')`
  (`services/presupuestacion/extraccion/repository.py:58`), so in-flight and failed uploads never show up and the
  user cannot tell whether a document is still processing or failed.
- Only validated OCs are listed (for matching re-entry); validated documents of other types just disappear.
- `extraction_results` stores no uploader (`client_id` is accepted but not persisted,
  `services/extraccion/persistent_output.py:264`), so "only mine" is impossible today.

## Decisions (user, 2026-09-26)

- Tabs per document type: Licitación, Directa (`cotizacion`), Comparativa, Orden de compra, each with a count.
- States (all types): Procesando (`processing`), Procesado (`completed`), Procesado con advertencias (`partial`),
  Error (`failed`), Validada (`validado = true`). Shown as a badge per row and as a filter inside each tab.
- Visibility: option A — the whole droguería's extractions (current RLS tenant boundary) plus a "Solo mías" filter.
  Requires persisting the uploader; extractions created before this change have no uploader and never match
  "Solo mías".
- Agrupar/Desagrupar only in the Orden de compra tab. Validated OCs keep their matching re-entry link.

## Constraints

- Validation guard stays: only `completed`/`partial` can be validated (`ESTADOS_VALIDABLES`); opening the listing to
  more states must not make processing/failed rows validatable.
- RLS remains the tenant boundary; no manual `drogueria_id` filter (superadmin has NULL drogueria_id).
- Migration files `NNNN_name.sql` + `.down.sql` (next: 0029). Applying to the TEST Supabase project needs explicit
  user confirmation.
- Pre-existing unrelated working-tree changes (`frontend/src/routeTree.gen.ts`, `frontend/pnpm-lock.yaml`) are not
  part of this feature and must not be committed.

## TDD

Mode: strict (source: global user CLAUDE.md). Runners: `pytest` (backend, `pytest.ini` at repo root),
`pnpm test` → `vitest run` in `frontend/`.

## Delivery

Strategy: ask-on-risk. Forecast ~700 authored lines (T1 ~300, T2 ~400). Running count after T1: 561 → over budget.
Chain strategy (user, 2026-09-26): `feature-branch-chain` — T1 and T2 must reach `dev` together (review finding).

- Tracker: `feat/validar-extraccion-organizacion` (reset to `dev` `8cb031b`; draft/no-merge PR → `dev`).
- Slice 01 `feat/validar-extraccion-organizacion-01-backend` → tracker: T1 (`848ec08`) + F1. Over 400 lines
  (~560, about half tests, plus migration comments); no cohesive split — `size:exception` recommended.
- Slice 02 `feat/validar-extraccion-organizacion-02-frontend` → slice 01: T2.
- Nothing pushed; push and PR creation are the user's decision.

## Tasks

- [x] **T1 — Backend: uploader + all states in the listing** (route: delegated writer; trigger: 2+ non-trivial files
  across migration, extractor persistence, presupuestacion listing)
  - Result: migration 0029 (`subido_por` FK `usuarios(id)`, partial index); `POST /procesar` passes `usuario.id`;
    `ExtraccionResumen` + `error_msg`, `subido_por`, `subido_por_nombre` (no `es_mia`: frontend compares with
    `AuthContext` `perfil.id`); `GET /extracciones?solo_mias=true`. Validation guard unchanged.
  - Backfill of old rows not possible: `extraction_results.session_id` is not persisted, so there is no link to
    `processing_sessions.subido_por`.
  - Evidence: RED→GREEN for repository/service (6 tests) and extractor (1 test). Router tests written after the code
    (TDD deviation, disclosed by the writer). Parent spot check: `pytest tests/extraccion/test_service.py
    tests/test_persistent_output.py -m "not integration"` → 68 passed. Full `pytest -q` → 1000 passed, 10 failed:
    6 in `tests/extraccion/test_router.py` (`column extraction_results.subido_por does not exist` — 0029 not applied
    to TEST, pending user confirmation), 4 in `tests/usuarios/test_service.py` (Supabase Auth email rate limit,
    unrelated).
  - Commit `848ec08`. RDD: assessed medium, `slice_budget_reached` (561 lines) → user granted review → 1 lens
    (reliability) → approved, acknowledged (lineage `review-b23e0acdffc202d7`, authority burned). Reviewed boundary
    advances to `848ec08`. Non-blocking follow-ups:
    - Deploy order: migration 0029 must be applied before this code runs (listing selects `subido_por`; uploads
      insert it). Ship T1 and T2 together — the listing now returns processing/failed rows the current UI would
      offer for validation.
    - Missing test that `POST /procesar` forwards `usuario.id` (→ F1).
    - `fk_er_subidopor` has no `ON DELETE` (defaults to restrict); matches existing `created_by` FKs; user hard
      delete is superadmin-only (`usuarios_del`). Left as-is unless the user decides otherwise.
    - "Uploader name hidden by usuarios RLS" — refuted: `usuarios_sel` allows same-droguería rows
      (`docs/schema/rls_final.sql:117`).
- [x] **F1 — Test that `POST /procesar` forwards the uploader** (route: inline; one test file, from review).
  - Evidence: RED (kwarg temporarily removed from `main.py`) → 1 failed; GREEN → `pytest tests/test_main_integration.py
    -m "not integration"` 41 passed. `main.py` restored byte-identical.
  - Migration 0029: `extraction_results.subido_por uuid null` (FK to the users table the project uses) + down.
  - Extractor persists the authenticated uploader when creating the `processing` row.
  - `GET /extracciones`: return `processing`, `completed`, `partial`, `failed`; expose `error_msg`, `subido_por`
    and the uploader's display name; new optional `solo_mias` param filtering by the caller.
  - Validation still rejects non-validatable states (existing tests stay green).
- [x] **T2 — Frontend: tabs by type, state badges/filters, "Solo mías"** (route: delegated writer; trigger: 2+
  non-trivial files in `frontend/src/features/validar-extraccion/`)
  - Tabs with counts; state filter chips; state badge per row; error message visible for Error rows.
  - Only Procesado / Procesado con advertencias rows link to validation.
  - "Solo mías" toggle; Agrupar/Desagrupar only in the OC tab; validated OCs keep the matching link.
  - Result: `estadoExtraccion.ts` (pure derived state, `validado` wins over `status`); `ExtraccionesTable.tsx`
    replaces `PendientesTable`/`ValidadasTable` (deleted, no other importers); accessible tabs + state chips with
    counts; uploader column; "Revisar" only for Procesado/advertencias, "Matching" for validated OCs; checkboxes
    and Agrupar/Desagrupar only in the OC tab. "Tipo" column dropped (the tab conveys it); partial badge orange,
    processing amber.
  - Data loading: two queries — pending `validado=false, limit=200` and validated `validado=true, limit=50`, both
    honoring `solo_mias`. A first single `limit=200` query was rejected by the parent: validated rows accumulate and
    would push older pending rows out of the window. Conditional `refetchInterval` 5s only while a pending row is
    `processing` (same pattern as `carga-documentos/RecentCard.tsx`).
  - Evidence: RED→GREEN for `estadoExtraccion.test.ts` (8) and the listing (17 failed → 24 passed; two-query
    correction 3 failed → green). Parent spot check: `npx vitest run` 351 passed; `npx tsc -b` clean. oxlint: 26
    findings, identical to baseline (writer report).

## Progress

- 2026-09-26: exploration done, decisions recorded, branch created. Next: T1.
