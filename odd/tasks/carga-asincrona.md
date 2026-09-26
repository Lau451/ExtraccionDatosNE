# Feature: carga-asincrona

Locator: `odd/tasks/carga-asincrona.md` · Engram mirror: `odd/carga-asincrona/tasks`
Branch: `feat/carga-asincrona` (from `dev`)

## Objective

Make document upload non-blocking and move validation back to its own step, fix the
cramped "Validar extracción" screen, and later tidy the formatting of the extracted
delivery address and notes.

## Problem / why

- `POST /procesar` (services/extraccion/main.py:142) awaits the Gemini robot before responding.
  The user sits on "Procesando…" for the whole call, then gets auto-redirected to validation
  (`FormCard.tsx:148`). Removing the redirect alone would not unblock anything.
- Today no `extraction_results` row exists until persistence finishes, so an in-flight upload is
  invisible and has no dedup protection; a robot failure leaves `processing_sessions` in `running`
  forever.
- `ValidarExtraccionDetalle` is capped at `max-w-4xl`; the OC table squeezes `w-full` inputs and
  pushes the Borrar/Deshacer column into horizontal scroll. The address header field is a single-line input.

## Decisions (user, 2026-09-26)

- Option B: real async processing (202 + background robot + status polling), not a frontend-only tweak.
- Validation screen layout fix approved as proposed.
- Address/notes formatting deferred to the end; needs a real example first.
- Scope choice (parent): async applies to all document types, since they share one endpoint and
  one waiting problem. The auto-redirect to validation is removed for OC.

## Constraints

- Multi-tenant: every row/RPC stays scoped by `drogueria_id`.
- `_GEMINI_SEMAPHORE` must still bound concurrent robot runs in the background path.
- `grupo_id` (multi-file OC) keeps working.
- Migration files follow the `NNNN_name.sql` + `.down.sql` convention. Applying them to the remote
  Supabase TEST project needs explicit user confirmation.

## TDD

Mode: strict (source: global user CLAUDE.md "Strict TDD Mode: enabled").
Runners: `pytest` (pytest.ini, asyncio_mode=auto) for the backend; `pnpm test` (vitest run) in `frontend/`.

## Delivery

Strategy: ask-on-risk. Forecast is about 900 authored lines (T1 ~450, T2 ~250, T3 ~150, T4 TBD), which exceeds the
~400 budget, so the chain strategy gets asked before opening PRs. One work-unit commit per task.

## Tasks

- [x] **T1 — Backend async processing** (route: delegated writer; trigger: 2+ non-trivial files)
  - Migration 0028: `extraction_results.status` accepts `processing` (plus `failed`), add `error_msg`;
    `reserve_extraction` treats `processing` as taken (returns its id) like `completed`.
  - `/procesar`: after dedup + session, insert the `extraction_results` row as `processing`, respond `202`
    with `extraction_id`; run robot + CSV read + finalize in the background (under the semaphore),
    moving temp-file cleanup there. Success → update the row to `completed` with row_count/csv path;
    failure → `failed` + `error_msg` (user-facing message from the existing exception mapping), and close
    the session.
  - Startup sweep: rows stuck in `processing` (server restart) → `failed` "Procesamiento interrumpido".
  - `listar_extracciones` (presupuestacion) and the validation detail only offer `completed` rows.
  - Acceptance: 202 returns in upload time; status transitions covered by tests; duplicates of an
    in-flight upload get 409 with its id; existing tests are updated, not deleted.
- [x] **T1b — Backend hardening from review advisories** (route: delegated writer, after T2)
  - If `crear_extraction_processing` returns None, respond 503 instead of running the robot with no row to update.
  - Startup sweep leaves rows younger than the threshold stuck forever → sweep all `processing` rows at startup
    (no request survives a restart) or add a periodic sweep.
  - `validar_extraccion` status check can KeyError when `status` is missing from the select; one shared constant for
    the validable statuses.
  - ParserError/GeminiAPIError store raw exception text in `error_msg` → fixed Spanish messages.
  - Minor: dangling helper reference in persistent_output docstring, the `extraction_id=None` contract comment,
    and in-flight 409 test coverage.
- [x] **T2 — Frontend non-blocking upload + live status** (route: delegated writer)
  - FormCard: submit returns right after upload(s), no auto-navigation; the form resets for the next document.
  - RecentCard: status badge (Procesando / Listo / Error with message), polls while anything is
    `processing`, "Validar" action on completed unvalidated rows.
  - Duplicate link behavior kept.
- [ ] **T3 — Validar extracción layout** (route: delegated writer)
  - Wider container, per-column min widths, auto-growing description, numeric columns right-aligned with
    tabular-nums, sticky actions column, auto-growing address textarea in the OC header.
  - T2 review advisories: RecentCard live region and polling predicate must use the same list; make the FormCard reset
    assertion meaningful; test the fallback message for a failed row with null `error_msg`.
- [ ] **T4 — Address / notes formatting** (blocked: needs a real example from the user)

## Progress / evidence

- T1 implemented (commit `5d12c22`, delegated writer). Evidence: `pytest tests -q -m "not integration"` → 483 passed;
  `pytest tests/extraccion/` (live TEST DB) → 174 passed; parent spot check of main/persistent_output/background_tasks
  tests → 62 passed. Parent correction: reserve_extraction deletes only `failed` rows; `partial` counts as taken,
  because deleting a validated partial row would violate the non-cascading FKs from items_proceso/comparativas/ordenes_compra.
  BackgroundTasks runs the whole job; the migration is NOT applied remotely yet.
  Review: assessed `high` (hot_path auth test) → consent granted → 4-lens review **approved** and acknowledged
  (lineage review-47925d1b46a8b9a5). Advisory (non-blocking) findings → task T1b.
- Known gaps (flagged, not fixed): check-then-insert race on near-simultaneous identical uploads (pre-existing);
  docs/modulos/extraccion_api/* are stale (pre-existing); mixed statuses inside a multi-file OC group are not specially handled.

- T2 implemented (delegated writer). Evidence: RED FormCard 7 failed / RecentCard 11 failed → GREEN 25/25;
  whole frontend suite 309 passed; `tsc -b --noEmit` clean; scoped oxlint clean (repo lint has pre-existing errors elsewhere).
  Parent spot check: `vitest run src/features/carga-documentos` → 25 passed. `partial` rows also get the Validar action.
  Commit `bd83f10`. Review: `medium` → consent granted → 1-lens (reliability) **approved** and acknowledged
  (lineage review-1aed2420d105537d). Advisories folded into T3: live region vs polling use different lists (top-3 slice vs
  full list); FormCard reset assertion on input.value cannot fail; no test for failed row with null error_msg.

- T1b implemented (delegated writer; its final report was lost to a session limit, so the parent verified from the diff).
  503 + session failed + temp cleanup when the processing row can't be created; startup sweep fails ALL `processing`
  rows (verified: services/extraccion/Dockerfile runs uvicorn without --workers, a single process); shared
  `ESTADOS_VALIDABLES`; fixed Spanish messages for ParserError/GeminiAPIError; comment fixes; in-flight 409 test.
  Parent evidence: `pytest tests -q -m "not integration"` → 489 passed; `pytest tests/extraccion -q` (live TEST) → 175 passed.
  RED evidence was not recoverable from the lost report.

## Next step

T1b (backend hardening) in progress; then T3 (+ T2 advisories); then T4 needs an example from the user.
Migration 0028 still needs user confirmation to apply on the TEST project.
