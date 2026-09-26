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
- [x] **T3 — Validar extracción layout** (route: delegated writer)
  - Wider container, per-column min widths, auto-growing description, numeric columns right-aligned with
    tabular-nums, sticky actions column, auto-growing address textarea in the OC header.
  - T2 review advisories: RecentCard live region and polling predicate must use the same list; make the FormCard reset
    assertion meaningful; test the fallback message for a failed row with null `error_msg`.
- [x] **T1c — Follow-ups from the T1b review** (route: small, inline or one writer)
  - Startup sweep has no age filter: unsafe if a second process (e.g. a local dev server) shares the same DB.
    Consider a periodic sweep with a generous age threshold instead.
  - 503 path: guard `cerrar_sesion` with try/finally so temp cleanup and the 503 always happen.
  - `leer_filas_extraccion` defaults a missing status to 'completed' while `validar_extraccion` rejects it; align them.
  - In-flight 409 test is tautological (mocks the RPC); the `processing` = taken rule lives only in SQL.
  - Hoist the fixed ParserError/GeminiAPIError messages to constants shared with the tests.
- [x] **T3b — Follow-ups from the T3 review** (route: same writer as T1c)
  - useAutoGrowTextarea only re-measures on value change: re-measure on width changes too (ResizeObserver), or
    text gets clipped after a resize (overflow-hidden) — the exact symptom the user reported.
  - Dirección is now a textarea with no Enter handling: newlines can leak into direccion_entrega. Keep it
    single-value (Enter does not insert newlines, pasted newlines normalized to ", ") until T4 decides the format.
  - Enter "no newline" test is tautological in jsdom: assert on fireEvent's return value (defaultPrevented).
- [x] **T1d — Heartbeat-based sweep** (route: delegated writer, after T4)
  - Review of T1c (approved, advisory): a 60-min threshold on created_at leaves restart orphans stuck ~65 min (blocking
    re-upload via 409) and can fail long-queued jobs behind _GEMINI_SEMAPHORE. Replace with a heartbeat: the background
    job touches `extraction_results.updated_at` every ~60 s from before acquiring the semaphore until it finishes (the
    trigger t_u_er already maintains updated_at, no migration); the sweep (startup + every 5 min) fails `processing` rows
    whose updated_at is older than ~5 min. Add a live-DB test of the timestamp filter (PostgREST '+' encoding).
  - Minor advisories: move _SWEEP_INTERVALO_SEGUNDOS next to _sweep_periodico; misleading test docstring
    (tests/test_persistent_output.py ~585); line-number reference in tests/extraccion/test_service.py ~209;
    useAutoGrowTextarea StrictMode reconnect (rely on ref(null) instead of a mount-only cleanup); skip the Enter block
    while IME composing (event.nativeEvent.isComposing); stub ResizeObserver as undefined instead of asserting the env.
- [x] **T4 — Address / notes formatting** (route: delegated writer, after T1c/T3b; approved by user 2026-09-26)
  - Root cause (verified on Pruebas/oc_sayago.pdf): scanned PDF → RapidOCR drops spaces between words; the prompt says
    "transcribe as written", so Gemini copies the glued text and flattens multi-line remarks into one line.
  - Prompt (robot_orden_compra._PROMPT): restore OCR-lost spaces and obvious Spanish accents without changing digits, names,
    case or meaning; direccion_entrega single line "street number - place - department/schedule"; locality/postal code
    ONLY from delivery-address fields (never from the issue place/date line, e.g. Tandil "Lugar:"); observaciones one
    remark per line (joined with a newline character), "Label: value", section headings on their own line.
  - Prototype validated in scratchpad on the 3 Pruebas OCs (renglon counts unchanged: 2/7/32).
  - UI: observaciones rendered preserving line breaks wherever OC notes are shown (validation header + OC/matching screens).
  - Existing extractions are not reprocessed.

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

- T1b commit `885c930`. Review: `high` → consent granted → 4-lens **approved** and acknowledged
  (lineage review-6c6b5af9be1d03e9). Advisories → T1c.

- T3 implemented (delegated writer). max-w-7xl; per-column ESTILO_COLUMNA (descripción min 22rem multiline auto-grow,
  numeric right-aligned tabular-nums, reference columns wrap); sticky right actions column; OC header 2-col grid with
  auto-growing dirección/observaciones (shared useAutoGrowTextarea hook); sticky bottom confirm bar. T2 advisories fixed.
  Evidence: RED 6 failing → GREEN; parent spot check `vitest run` → 317 passed, `tsc -b --noEmit` clean; oxlint clean (writer).

- T3 commit `3fb167c`. Review: `medium` → consent granted → 1-lens **approved** and acknowledged
  (lineage review-d8cdff3a2e1394fd). Advisories → T3b.

- T1c + T3b implemented (one delegated writer). T1c: sweep with age threshold 60 min (worst-case Gemini backoff
  280s/call-site x ~3 + persist retries + semaphore queueing, rounded up), runs at startup and every 5 min from the lifespan,
  failure-tolerant; 503 path guards cerrar_sesion; leer_filas/validar aligned on "missing status = not validable";
  real live-DB test for reserve_extraction treating 'processing' as taken; hoisted error-message constants.
  Tradeoff: a row orphaned by a restart stays 'processing' (and blocks re-upload with 409) for up to 60 min.
  T3b: ResizeObserver re-measure (parent narrowed it to width changes only, to avoid re-measuring on its own height
  change); dirección blocks Enter and normalizes pasted newlines to ", "; non-tautological Enter test.
  Evidence (writer): RED per behavior → GREEN; `pytest -m "not integration"` 495, `pytest tests/extraccion` 176 (live),
  reserve_extraction integration 3. Parent: `pytest -m "not integration"` → 495 passed; `vitest run` → 328 passed;
  `tsc -b --noEmit` clean; TEST DB left with only the 5 original completed rows.

- T1c+T3b review: `high` → consent granted → 4-lens **approved** and acknowledged (range 3fb167c..2dd506d). Advisories → T1d.

- T4 implemented (delegated writer + parent). Prompt rules (OCR re-spacing/accents, delivery-only locality, one remark per
  line, never drop a remark as redundant), defensive single-line direccion_entrega in _construir_filas, CSV round-trip test.
  No read-only OC notes view exists in the frontend (the validation textarea already renders newlines), so no UI change.
  Parent additions: `temperature=0` on the OC Gemini config (default temperature made observaciones drop lines and
  Tandil return 31 vs 32 renglones), and a rule to complete the street from the same institution's Domicilio when the
  delivery block has none (with temperature 0, Sayago consistently lost "FRENCH 5090").
  Evidence: RED (writer 8 tests; parent temperature test failed) → GREEN; `pytest -m "not integration"` → see commit;
  live 3x: Sayago 7/7/7 renglones, 9 obs lines, dir "FRENCH 5090 - HOSPITAL PCIAL. SAYAGO - FARMACIA - Horario: 7 a 14 hs";
  Tandil 32/32/32, dir without "Tandil" (1 of 3 runs added extra delivery/payment lines to observaciones — residual
  model variance); Nueva Era 2 renglones, empty dir.

- T4 commit `e6bf13b`: review assessed `medium`, review_due=false (`under_budget`, 198 lines) → pending in the slice,
  to be reviewed together with T1d (last reviewed boundary: 2dd506d).

- T1d implemented (delegated writer). Backend: new `latido_extraccion` (persistent_output.py) does a no-op UPDATE
  filtered by `id` + `drogueria_id` + `status='processing'` (never resurrects a finished row) -- the trigger t_u_er
  refreshes `updated_at` on any UPDATE. `_procesar_documento_background` (main.py) starts a concurrent
  `_latir_periodicamente` task (heartbeat every `_LATIDO_INTERVALO_SEGUNDOS=60`) before entering
  `_GEMINI_SEMAPHORE`, cancelled in the existing `finally` regardless of outcome. Sweep
  (`marcar_processing_interrumpidos`) now filters `.lt("updated_at", cutoff)` instead of `created_at`, with
  `_SWEEP_EDAD_MINIMA_SEGUNDOS_DEFAULT` dropped from 60 min to 5 min (5x the heartbeat interval). `_SWEEP_INTERVALO_SEGUNDOS`
  moved from persistent_output.py to main.py (next to `_sweep_periodico`, the only place that uses it). Added a
  live-DB integration test (`tests/test_persistent_output.py`) that inserts a 'processing' row with a stale
  `updated_at` and a fresh one, runs the sweep, and asserts only the stale one becomes 'failed' -- it passed, so the
  PostgREST '+00:00' offset encoding the review flagged is not actually broken; no fix was needed there.
  Minor advisories: fixed the misleading test docstring implying main.py already passes a custom threshold; replaced
  the stale line-number reference in tests/extraccion/test_service.py with the function name; useAutoGrowTextarea.ts
  now relies solely on the ref callback's `disconnect()` on `ref(null)` (removed the separate mount-only cleanup
  effect that lost the observer in StrictMode dev); CabeceraOrdenCompra's Enter guard now skips
  `event.nativeEvent.isComposing`; useAutoGrowTextarea.test.ts stubs `ResizeObserver` as undefined instead of
  asserting the jsdom environment lacks it.
  Evidence: RED (function/attribute errors + `created_at` vs `updated_at` assertion mismatches, backend; IME test,
  frontend) via a temporary `git stash` of the implementation-only files → GREEN after restoring.
  `pytest -m "not integration"` → 511 passed; `pytest tests/extraccion` (live TEST DB) → 176 passed; the new
  integration test → 1 passed (isolated run); `vitest run` → 329 passed; `tsc -b --noEmit` clean. TEST DB left with
  only the 5 original completed rows (no leftover 'processing'/'failed' test debris).
  Open item: the StrictMode-losing-the-observer bug itself isn't directly reproducible in jsdom via `renderHook`
  (React doesn't re-invoke a manually-set callback ref the way it would a real rendered element's ref during its
  dev double-invoke simulation) -- the test coverage for that fix is the ref(null)-disconnects unit test, not a
  StrictMode reproduction; not fixed further, flagged for the next review.

- T1d implemented (delegated writer). Heartbeat every 60 s from before the semaphore until the job ends (no-op UPDATE
  filtered by id+drogueria_id+status='processing'; trigger t_u_er bumps updated_at); sweep on updated_at older than 5 min,
  at startup and every 5 min — restart orphans now clear in ~5 min and queued jobs stay alive. Live test confirmed the
  PostgREST '+00:00' cutoff filter works. Minor advisories applied (constant placement, docstrings, StrictMode-safe
  observer disconnect via ref(null), IME-composing Enter, ResizeObserver stub).
  Evidence (writer): RED via reverting impl files → GREEN; `pytest -m "not integration"` 511; `pytest tests/extraccion`
  176 (live); new integration test 1; `vitest run` 329; tsc clean; TEST DB left with 5 completed rows.
  Parent: git stash list empty; spot check 70 backend + 111 validar-extraccion tests passed.
  Open: no direct test reproduces the StrictMode double-mount scenario.

- T4+T1d slice review: `medium` → consent granted → 1-lens **approved** and acknowledged (range 2dd506d..31bced3).
  Refuted by the parent: "heartbeat stops before persist" (persist_bg() is awaited inside the same try, main.py:393) and
  "missing asyncio marker" (pytest.ini asyncio_mode=auto). Applied: the live sweep test now uses a 30-min threshold with a
  2-hour-old seed so it can never fail a live job of another process sharing TEST; Safari IME (keyCode 229) no longer
  blocks Enter (RED 1 failed → GREEN, `vitest run` 330, tsc clean; live sweep test 1 passed).
  Left as-is: the post-failure cancel test only compares task counts (weak but not wrong).

## Next step

T1d done. Next: parent review of T1d + the still-pending T4 slice (under_budget), then delivery-strategy chaining
decision (branch forecast is ~900 lines, already over the ~400 budget).
Migration 0028 applied on TEST (grnamollopxdlstcpxhc) on 2026-09-26 with user confirmation.
