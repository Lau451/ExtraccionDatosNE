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

- [ ] T1 S1, S2, S5 — migration 0035 (`posicion_en_plan`, `entregas_en_plan`) + down + snapshot + model + TS mirror + tests. Inline. Needs the user to apply 0035 in TEST.
- [x] T2 S3, S4 — `GET /compromisos-entregas/proxima-fecha` (repository, service, router) + unit and integration tests. Inline. Commit `55d68c9`.
- [ ] T3 all — independent `gentle-ai-verify` (migration = high risk, item 1).

## Log

- L1 (user, 2026-10-17, after the design listed the two missing data points "Entrega N de M" and the next date for "Ir a noviembre"): "agregalas"
- L2 Evidence: `compras/service.py:237` numbers a real delivery `len(entregas_previas) + 1`, so `numero_entrega` alone cannot express "N de M" (S2).
- L3 Decision: a new endpoint instead of changing the list response shape (an array already consumed by the frontend), to keep the existing contract.
- L4 T1 RED: `-m integration -k "posicion_y_tamano or plan_ignora"` 2 failed with `KeyError: 'posicion_en_plan'` (0035 not applied). Until 0035 is applied in an environment, the list endpoint of this branch fails response validation there: deploy order is migration first.
- L5 T2 RED: 4 unit tests failed with `AttributeError` (no `proxima_fecha`). GREEN: `tests/compromisos -m "not integration"` 21 passed; `-m integration -k proxima` 3 passed against TEST. Frontend: vitest `src/features/compromisos` 9 passed, `tsc -b` 0 errors.
