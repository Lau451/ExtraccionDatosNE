# routers-por-modulo — stage 6 (X-ARQ-006)

`services/presupuestacion/main.py` stops mounting 26 loose routers: each target module of
`docs/arquitectura/mapa-modulos.md` gets one aggregate router, and main mounts one per module.
Branch `feat/routers-por-modulo` from `dev` 49b62dd.

## Specs

- **S1** (L1 option "A: un router por módulo, sin mover carpetas"): a new `services/presupuestacion/modulos.py` defines one `APIRouter` per target module and the ordered list `MODULOS`. Grouping from the map: `plataforma` = auth, usuarios, droguerias, planes, auditoria, eventos, notificaciones; `productos` = productos, imports; `terceros` = terceros, clientes; `comercial` = procesos_comerciales, matching, pricing, presupuestos, comparativas, extraccion; `compras` = pcp, compras; `ordenes_compra` = oc_presupuesto, oc_entregas, oc_resumen, compromisos; `integracion_progress` = integracion_progress, oc_export; `automatizaciones` = automatizaciones. No folder moves.
- **S2** (L1 "las rutas HTTP quedan idénticas (P10) y un test compara la tabla de rutas antes y después"): every HTTP route keeps its path, methods, endpoint, dependencies and OpenAPI tag; for every route, a request to its path resolves to the same endpoint as before (no shadowing from the new mount order). Checked by a differential script base vs branch (not committed) over the ordered route table.
- **S3** Guard `tests/arquitectura/test_routers_por_modulo.py`: `main.py` imports no `*.router` module and mounts only the routers of `MODULOS`, one `include_router` per module; `MODULOS` names are exactly the eight modules above; no (path, method) is registered twice in the app.
- **S4** Docs: `docs/arquitectura/README.md` stage 6 done, X-ARQ-006 resolved in `mapa-modulos.md`, pointing at `modulos.py`.

## Tasks

- [x] T1 S1-S3 — modulos.py, main.py, guard, differential — inline — commit: f595e1f
- [x] T2 S4 — docs — inline — commit: this docs commit

## Log

- **L1** (user, 2026-11-08): "bahjalos y empeza la etapa 6". Design question answered: "A: un router por módulo, sin mover carpetas (Recomendada)" — "Cada módulo objetivo tiene su router agregador (ej. comercial = procesos+matching+pricing+presupuestos+comparativas+extraccion) y main.py monta ~8. Chico y reversible; mover carpetas queda para cuando se toque cada módulo (P10)." Question text: "En los dos casos las rutas HTTP quedan idénticas (P10) y un test compara la tabla de rutas antes y después."
- **L2** Constraint found: the aggregate routers must live in `services/presupuestacion` (the composition root): `services/terceros` and `services/productos` cannot import `presupuestacion` (`tests/arquitectura/test_capas.py`), and `presupuestacion` imports `services.pcp` only from `main.py` (`tests/pcp/test_dependencias.py`) — so `modulos.py` needs that guard to allow it too.
- **L3** Evidence: guard RED first (3 failed: 26 router imports, 26 include_router calls, no modulos.py), GREEN after (arquitectura + pcp/integracion_progress/terceros dependency guards: 81 passed). Differential base vs branch (script in $TEMP, not committed): 173 routes identical in path, methods, endpoint, dependencies, tags, status and response model; OpenAPI paths and tags identical; route order changes (grouped by module) but 177/177 method+sample-path requests resolve to the same endpoint. Full backend suite: 2154 passed, 1 failed — tests/pcp/sugerencias/test_service.py::test_precio_reciente_vigente_se_sugiere_como_referencia (29 == 30): pre-existing timezone flake, the test uses local date.today() while the DB CURRENT_DATE is UTC (run at 22:04 UTC-3 = next day in UTC); not touched by this feature, left as a follow-up.
