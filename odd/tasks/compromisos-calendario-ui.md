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

- [ ] T1 S3, S6, S7 — data layer: `listarCompromisos({desde, hasta})`, `obtenerProximaFecha`, date helpers (`fechas.ts`), `agruparEntregas` with `posicion_en_plan`/`entregas_en_plan`. Inline.
- [ ] T2 S1, S3, S6 — page shell: header, view toggle, toolbar, search, states; Lista moved to `VistaLista` unchanged. Inline.
- [ ] T3 S2, S4 — month view and side panel. Inline.
- [ ] T4 S5 — week view. Inline.

## Log

- L1 (user, 2026-10-17): "bien queiro diseñar la pantalla de comproisos de entrega, la idea es que se vea mas como un calendario"
- L2 (user, after the month view mockup): "me gusta"; then "agregalas" for the missing backend data.
- L3 (user, after the backend closed): "implementemos en esta rama"
- L4 Decisions: no icon library is installed, so chevrons are small inline SVGs (adding a dependency is a delivery risk). The calendar fetches the visible range (`desde`/`hasta`) plus overdue deliveries (`hasta` = yesterday), so navigation is not limited to the default 6 months. View, period and selection live in component state (not URL search params). Search applies to Mes, Semana and Lista.
