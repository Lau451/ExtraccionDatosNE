# Compromisos calendario: backend data

Backend data the calendar design for `/compromisos` needs (Pencil mockup, frames
"Compromisos de entrega - Calendario/Semana" and "Compromisos - Estados"). Branch `feat/compromisos-calendario-datos`.

## Specs

- S1 Each row of `GET /compromisos-entregas` carries the position of its delivery within the OC plan and the plan size, so the UI can render "Entrega 2 de 3". New fields `posicion_en_plan` and `entregas_en_plan` (int).
- S2 The plan counts only deliveries with at least one item with `cantidad_planificada > 0` (same criterion as 0034), in any state (pending, delivered, rejected). Real deliveries registered by `compras.crear_entrega` (`cantidad_planificada = 0`) are numbered after the plan but are not part of it: they do not change `entregas_en_plan` and do not shift `posicion_en_plan`. Position follows `numero_entrega` order.
- S3 New endpoint `GET /compromisos-entregas/proxima-fecha?despues_de=YYYY-MM-DD` returns `{"fecha": "YYYY-MM-DD"}` with the earliest `fecha_entrega_planificada` strictly after `despues_de` among the user's commitments (same view, same droguería), or `{"fecha": null}` when there is none. It backs the empty-month CTA "Ir a noviembre" ("La próxima está el 2 de noviembre").
- S4 `proxima-fecha` keeps the list endpoint rules: same roles (`_ROLES_LECTURA`, 403 otherwise), per-user RLS client, 422 for a user without droguería; `despues_de` is required (422 when missing or malformed).
- S5 Migration 0035 + down, schema snapshot, Pydantic model and the TS mirror (`frontend/src/lib/api/compromisos.ts`) updated. The existing list behavior (filters, order, pagination, roles, isolation) is unchanged.

## Tasks

- [x] T1 S1, S2, S5 — migration 0035 (`posicion_en_plan`, `entregas_en_plan`) + down + snapshot + model + TS mirror + tests. Inline. Needs the user to apply 0035 in TEST. Commit `c82a940`.
- [x] T2 S3, S4 — `GET /compromisos-entregas/proxima-fecha` (repository, service, router) + unit and integration tests. Inline. Commit `55d68c9`.
- [x] T3 all — independent `gentle-ai-verify` (migration = high risk, item 1). Verdict at `3396906`: S1–S5 PASS (L7).
- [x] T4 S2, S3 — verify follow-ups: integration test for a rejected plan delivery (S2 names "rejected"); strict assertion in the `proxima-fecha` integration test. Inline. Commit `0dee891`.

## Log

- L1 (user, 2026-10-17, after the design listed the two missing data points "Entrega N de M" and the next date for "Ir a noviembre"): "agregalas"
- L2 Evidence: `compras/service.py:237` numbers a real delivery `len(entregas_previas) + 1`, so `numero_entrega` alone cannot express "N de M" (S2).
- L3 Decision: a new endpoint instead of changing the list response shape (an array already consumed by the frontend), to keep the existing contract.
- L4 T1 RED: `-m integration -k "posicion_y_tamano or plan_ignora"` 2 failed with `KeyError: 'posicion_en_plan'` (0035 not applied). Until 0035 is applied in an environment, the list endpoint of this branch fails response validation there: deploy order is migration first.
- L5 T2 RED: 4 unit tests failed with `AttributeError` (no `proxima_fecha`). GREEN: `tests/compromisos -m "not integration"` 21 passed; `-m integration -k proxima` 3 passed against TEST. Frontend: vitest `src/features/compromisos` 9 passed, `tsc -b` 0 errors.
- L6 User applied 0035 in TEST ("ya la apliqué"). T1 GREEN: `-m integration tests/compromisos` 18 passed (2 new + all existing list tests).
- L7 T3 verify (task mvcnc2ge-1-ugoi) at `3396906`: S1–S5 PASS, no candidate-caused blockers (snapshot blocker fixed by `3396906`). Unit suite 579 passed, 1 failed (`test_service_client_no_se_importa_en_ningun_router`, pre-existing on `dev` at `f6c39b5`, `oc_resumen/router.py`); integration `tests/compromisos` 18 passed; vitest 501 passed; `tsc -b` 0. Follow-ups: window over all `entregas_oc` (EXPLAIN later); weak `!=` assertion in a `proxima` test; "rechazada counts in plan" proven by reading only; deploy order 0035 before code.
- L8 (user): "bien, realizamos los pendientes primero". Scope: the verify follow-ups that are tests (T4). The `EXPLAIN` of the plan window and the deploy order stay as notes.
- L9 T4: `-m integration tests/compromisos/test_router.py -k "rechazada_sigue or estrictamente_posterior"` 2 passed against TEST. Test-only change; no RED applicable (behavior already implemented, verify proved it by reading).
- L10 Down cycle in TEST: the user ran `0035_v_compromisos_posicion_plan.down.sql` ("corri .down"). Verified by read (Supabase MCP): 15 columns, same as 0034, without `posicion_en_plan`/`entregas_en_plan`; `security_invoker=true`; filter `cantidad_planificada > (0)::numeric` present; `authenticated` can select; comment ends with "ajustada en 0034.".
- L11 The user reapplied 0035 ("llisto ya corri otrta vez"). Verified by read: 17 columns, ending in `posicion_en_plan, entregas_en_plan`; `security_invoker=true`; plan filter present; `authenticated` can select; comment ends with "ajustada en 0034 y 0035.". `-m integration tests/compromisos` 19 passed. Down cycle closed.
- L12 Commits `6852c9d`, `0dee891` and `c9edcd9` were not created by this session: something else committed its uncommitted work (doc and T4 test) at 14:24-14:27. Their content matches what this session wrote; `e9d097a` ended up holding only the duplicate L9 line, removed here.
