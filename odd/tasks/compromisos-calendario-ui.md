# Compromisos calendario: frontend

Implements the Pencil design (`pencil-new.pen`, frames "Compromisos de entrega - Calendario", "Compromisos de entrega - Semana", "Compromisos - Estados") on `/compromisos`.
Backend data from `odd/tasks/compromisos-calendario-datos.md` (same branch `feat/compromisos-calendario-datos`).

## Specs

- S1 View toggle "Mes" / "Semana" / "Lista". "Mes" is the default. "Lista" is the current agenda (overdue first, then month and date groups) with its behavior unchanged.
- S2 Month view: Monday-to-Sunday grid ("LUN".."DOM") covering every week of the month. Each day shows its deliveries as chips "<numero_oc> · <cliente>", red for `vencida` and blue for `futura`, at most 3 per day plus "+N más". Today has its number highlighted and the "Hoy" label; days outside the month are dimmed; the selected day is outlined.
- S3 Toolbar: previous/next buttons, period label ("Octubre 2026" in Mes, "19 – 25 de octubre 2026" in Semana), "Hoy" button (back to today's period, selects today), chips "N vencidas sin confirmar" and "N entregas en octubre" / "N entregas esta semana", and a "Buscar cliente u OC" search that filters deliveries by client or OC number.
- S4 Side panel (month view): "Vencidas sin confirmar" block with the total, the 3 oldest overdue deliveries (OC, client, "dd/mm · N días") and "Ver las N vencidas →" (switches to Lista). Hidden when there are no overdue deliveries. Below, the selected day: weekday, "23 de octubre", "N entregas · M renglones", and each delivery with client, OC link, "Entrega 2 de 3" and its line items with quantities.
- S5 Week view: one column per day (weekend columns narrower), column header with weekday, day number and "N entregas"; "Sin entregas" on empty weekdays. Each delivery is a card with client, OC link, "Entrega 2 de 3" and "N renglones · total u."; selecting a card expands its line items.
- S6 States of the calendar area: loading skeleton; empty period with "No hay entregas en octubre" / "No hay entregas esta semana", "Las entregas aparecen cuando una OC se exporta a Progress." and, when `proxima-fecha` returns a date, "La próxima está el 2 de noviembre." plus "Ir a noviembre" (or "Ir a esa semana" in Semana), which navigates there and selects that date; error with the message and "Reintentar".
- S7 "Today" is the Buenos Aires date (same reference as the backend). Dates `YYYY-MM-DD` are handled as calendar dates, never through `new Date('YYYY-MM-DD')` (UTC shift).

## Tasks

- [x] T1 S3, S6, S7 — data layer: `listarCompromisos({desde, hasta})`, `obtenerProximaFecha`, date helpers (`fechas.ts`), `agruparEntregas` with `posicion_en_plan`/`entregas_en_plan`. Inline. Commit `b8645c6`.
- [x] T2 S1, S2, S3 — page shell (header, view toggle, toolbar, stats, search), Lista moved to `VistaLista` unchanged, month grid. Inline. Commit `cbc90bb`.
- [x] T3 S4, S6 — side panel (overdue + selected day) and calendar states (loading, empty with next date, error). Inline. Commit `fff0208`.
- [x] T4 S5 — week view. Inline. Commit `0f9cb1a`.

## Log

- L1 (user, 2026-10-17): "bien queiro diseñar la pantalla de comproisos de entrega, la idea es que se vea mas como un calendario"
- L2 (user, after the month view mockup): "me gusta"; then "agregalas" for the missing backend data.
- L3 (user, after the backend closed): "implementemos en esta rama"
- L4 Decisions: no icon library is installed, so chevrons are small inline SVGs (adding a dependency is a delivery risk). The calendar fetches the visible range (`desde`/`hasta`) plus overdue deliveries (`hasta` = yesterday), so navigation is not limited to the default 6 months. View, period and selection live in component state (not URL search params). Search applies to Mes, Semana and Lista.
- L5 T1 RED: 5 tests failed (missing functions, `fechas.ts` absent). GREEN: vitest `src/features/compromisos` + `lib/api/compromisos.test.ts` 22 passed; `tsc -b` 0 errors after `Compromisos.tsx` stopped passing `listarCompromisos` directly as `queryFn` (its new optional parameter clashed with the React Query context); fix amended into `b8645c6`.
- L6 Task split changed: the grid and the shell are coupled, so T2 takes the month grid and T3 takes the side panel and the states.
- L7 T2: the old agenda moved to `VistaLista` (`git mv`) with its 4 tests unchanged, plus a search test written after the filter (no RED observed for that one). Page RED: `Compromisos.test.tsx` failed to import (`./Compromisos` absent). GREEN: vitest `src/features/compromisos` 26 passed; `tsc -b` 0; oxlint clean. The toggle shows Mes and Lista only; Semana is added in T4.
- L8 T3 RED: 8 new page tests failed (no side panel, no states); "no overdue block when there are none" passed vacuously. GREEN: vitest `src/features/compromisos` 35 passed; `tsc -b` 0; oxlint clean. The empty month means no unfiltered delivery dated in the month; `proxima-fecha` is asked after the month's last day. An active search with no matches shows "Ninguna entrega coincide con la búsqueda" and does not call `proxima-fecha`.
- L9 T4 RED: 4 week-view tests failed (no Semana toggle). A test expectation was wrong and fixed before GREEN: 19-25 October holds 6 deliveries, not 7. Two tests looked for cards before the period loaded (the columns render during loading); they now wait. GREEN: vitest `src/features/compromisos` 39 passed; `tsc -b` 0; oxlint clean.
- L10 Design change in T4: the selected day is the single source of truth for the visible period (month and week derive from it). Consequence: clicking a day of a neighbouring month in the grid moves the calendar to that month. The week view has no side panel; overdue deliveries keep their counter in the toolbar.
- L11 Full frontend vitest before the T4 commit: 55 files, 533 tests passed.
