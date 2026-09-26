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

- [ ] **T1 — Backend async processing** (route: delegated writer; trigger: 2+ non-trivial files)
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
- [ ] **T2 — Frontend non-blocking upload + live status** (route: delegated writer)
  - FormCard: submit returns right after upload(s), no auto-navigation; the form resets for the next document.
  - RecentCard: status badge (Procesando / Listo / Error with message), polls while anything is
    `processing`, "Validar" action on completed unvalidated rows.
  - Duplicate link behavior kept.
- [ ] **T3 — Validar extracción layout** (route: delegated writer)
  - Wider container, per-column min widths, auto-growing description, numeric columns right-aligned with
    tabular-nums, sticky actions column, auto-growing address textarea in the OC header.
- [ ] **T4 — Address / notes formatting** (blocked: needs a real example from the user)

## Progress / evidence

(none yet)

## Next step

T1 delegated writer.
