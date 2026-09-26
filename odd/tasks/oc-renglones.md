# Feature: oc-renglones

Locator: `odd/tasks/oc-renglones.md` · Engram mirror: `odd/oc-renglones/tasks`
Branch: `feat/oc-renglones` (from `dev`)

## Objective

Make the OC line items easier to validate: hide reference columns that do not help, and capture per-line remarks
(typically a minimum expiry such as "VTO. MÍNIMO 12 MESES") in their own renglón field instead of leaving them
mixed into the description.

## Problem / why

- Validar extracción showed Entregas, Archivo and the raw extraction UUID for every OC, making rows tall and noisy.
- Per-line conditions (expiry, required brand, etc.) usually come appended to the line description. Today they stay
  inside `descripcion`, so they are easy to miss, are not a structured field of the OC line, and pollute the
  description used for matching against the presupuesto.

## Decisions (user, 2026-09-26)

- Hide `entregas` and `_extraction_id` always; show `_archivo` only when the OC groups more than one file.
- Clarified: splitting into deliveries is not implemented elsewhere yet (planned phase after matching); the data
  stays in the CSV.
- Per-line remarks: Gemini extracts them into a renglón field and removes them from `descripcion`; editable in
  validation; persisted on the OC line (`oc_items.observaciones`, new column); visible in the matching screen.
- No real example OC exists; the user says the remark is usually written inside the line itself. Verify with
  synthetic cases built from a real OC markdown.

## Constraints

- CSV column order is a contract (D6): new columns are appended at the end; CSVs written before this change
  (without the column) must keep working.
- Header-level remarks stay in the header `observaciones` (e.g. Tandil's general expiry note).
- Migration files `NNNN_name.sql` + `.down.sql`; applying to the TEST Supabase project needs user confirmation.

## TDD

Mode: strict (source: global user CLAUDE.md). Runners: `pytest` (backend), vitest in `frontend/`.

## Delivery

Strategy: ask-on-risk. Forecast ~450 authored lines (T1 ~40 done, T2 ~400).

## Tasks

- [x] **T1 — Hide non-useful reference columns** (route: inline; 2 files, mechanical)
  - Evidence: RED 2 failed → GREEN; `vitest run` 333 passed; tsc clean; checked in the browser. Commit `ae21f7a`.
- [ ] **T2 — Per-renglón observaciones end to end** — CANCELLED by the user 2026-09-26 (on hold) (route: delegated writer; trigger: 2+ non-trivial files, backend + frontend)
  - Prompt: renglón field `observaciones` for remarks that apply only to that line, removed from `descripcion`.
  - CSV: `observaciones_renglon` appended at the end of `_FIELDNAMES`; old CSVs without it still read.
  - Backend: migration 0029 `oc_items.observaciones text null`; `FilaOrdenCompraIn.observaciones` optional; persisted
    on OC confirmation; exposed by the matching endpoint.
  - Frontend: editable multi-line "Observaciones" column in Validar extracción; sent in the override; read-only in
    the matching screen.
  - Live check: synthetic markdown (a real OC with per-line expiry remarks added) through Gemini.

## On hold: expiry (vencimiento) handling

The user's underlying need is broader than a text field: "we sometimes quote with a given expiry and need to know
whether the OC accepts it". Verified on 2026-09-26 that the quoted expiry is not stored anywhere today:
`presupuesto_items` has no expiry column, and the legacy presupuesto CSV (Pruebas/PresupuestoSayago.csv) has no expiry
field (the only expiry columns in the DB are `procesos_comerciales.vencimiento` and `entregas_oc_items.vencimiento`).
Open question for when it resumes: where the quoted expiry lives today (Progress, the presented PDF, elsewhere).
A future design needs (1) what the OC requires (per-line + header, ideally structured, e.g. minimum months) and
(2) what we quoted, then a comparison in the matching screen. The T2 writer was stopped before writing any file.

## Progress / evidence

- T1 done (see above).

## Next step

T1 is committed on feat/oc-renglones (ae21f7a) and not merged yet. T2 and the expiry design wait for the user.
