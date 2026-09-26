# Feature: Duplicate upload → link to the existing extraction (and validated state)

## Objective
When an upload is a duplicate (409 from `POST /procesar`, same droguería), the user can open the existing extraction. If that extraction was already validated, the validation screen must say so and, for purchase orders, link to its OC instead of offering a second confirmation.

## Why
User request 2026-09-25 ("aplicá la mejora del 409"). While testing, opening an already-validated extraction (oc_sayago → OC 986) showed it as pending with "Confirmar cliente"/"Confirmar validación" enabled; a second confirmation is only stopped by the backend's duplicate-OC conflict. Same happens when opening the URL directly. User approved the fix 2026-09-26.

## Scope / constraints
- Backend: the filas endpoint used by the validation screen (`GET /extracciones/{id}/filas`, `FilasExtraccionOut` in `services/presupuestacion/extraccion/`) exposes `validado` and `orden_compra_id` (lookup via `ordenes_compra.extraction_id`, same approach as `listar_extracciones`). For a multi-file OC group, the OC may be linked to another member — resolve through the group when possible.
- Frontend: `ValidarExtraccionDetalle` shows "Esta extracción ya fue validada" when `validado`; with `orden_compra_id` a button "Ir a la orden de compra" (→ `/ordenes-compra/$ordenCompraId/matching`); hides/disables client confirmation, header editing, table editing and "Confirmar validación". Licitación/comparativa validated: notice only.
- TDD strict. Backend `venv/Scripts/python -m pytest tests/ -m "not integration"` (+ scoped integration if the service test uses the real DB). Frontend `pnpm test`, `tsc --noEmit`.
- Branch `feat/extraccion-duplicado-link` (from dev 58d05ec).

## Tasks
- [x] T1 (inline) 409 link: `ApiError.body`, "Ver extracción existente" button, no wait for new recent documents when nothing was processed — commit `c855869` (vitest 292 passed, tsc clean; live-checked: message < 2 s, link opens the existing extraction).
- [x] T2 (delegated — backend model/service + frontend screen) validated state on the validation screen — commit `47f16dd` (8 files +375/-1). `FilasExtraccionOut` adds `validado` + `orden_compra_id` (resolved via `ordenes_compra.extraction_id` over all group members); `ValidarExtraccionDetalle` early-returns a read-only notice "Esta extracción ya fue validada" + "Ir a la orden de compra" (no selector/editor/table/confirm). RED→GREEN: 3 service unit, 4 router integration (incl. group member → anchor's OC), 3 frontend. Unit 465 passed (parent spot check 465); integration scoped 38 passed; frontend 295 passed; tsc clean. TEST DB still 1 droguería after the integration run.
- Live browser check NOT done: Chrome extension disconnected in this session. Servers restarted (8000/8001/5173 → 200).
- Review assess (base 58d05ec): medium, 11 files, 475 lines → user granted → reliability APPROVED → acknowledged (lineage review-22dfb08811a2d2e2). Findings: (a) validado NULL → 500 REFUTED (`validado BOOLEAN NOT NULL DEFAULT FALSE`, extractor_final.sql:567); (b) 409 body contract unproved REFUTED (backend `tests/test_main_integration.py:199` asserts `extraction_id` in the 409); (c) mixed batch untested → coverage test added in `2eb9a5a` (passes immediately — behavior was already correct, so no RED; FormCard 12 passed, tsc clean).

- Live check (2026-09-26, extension reconnected): upload oc_sayago.pdf → 409 message + "Ver extracción existente" in < 2 s → opens `9a82e703…` → "Esta extracción ya fue validada." + "Ir a la orden de compra" (no editing/confirm UI) → matching of OC 986 with its 7 confirmed links. Pending extraction (OC_TANDIL `c4902835…`) still renders the normal editable screen.

- Delivery: user approved → PR #59 merged into `dev` (`8ab59fc`), branch deleted locally and on origin.

## Next step
None (done).
