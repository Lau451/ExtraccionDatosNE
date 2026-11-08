# pcp-fachadas — stage 4 (X-ARQ-002)

`pcp` reaches other modules only through their `api.py` facades: imports of notificaciones,
pricing and productos internals, and its direct reads of comercial tables. Branch `feat/pcp-fachadas` from `dev` 5e272b4.

## Specs

- **S1** (L1, option "1"): `services/presupuestacion/notificaciones/api.py` and `services/presupuestacion/pricing/api.py` exist as pure re-export facades (same shape as `services/productos/api.py`). `services/pcp/negociacion/service.py` imports `crear_notificacion` and `generar_presupuesto_para_endpoint` only through them. Behavior unchanged.
- **S2** (L1, option "2"): `services/productos/api.py` also exports `obtener_producto` and `ProductoOut`; every `services/pcp/**` file uses them through the facade, never `services.productos.service` / `.models`. Behavior unchanged.
- **S3** (L1, option "3"): the six direct reads of comercial tables in `services/pcp/**` (`presupuestos` in gestion/negociacion/imports, `items_proceso` in renglones/imports, `presupuesto_legacy_map` in imports) are removed from pcp and served by the owner through `services/presupuestacion/presupuestos/api.py` (presupuestos, presupuesto_legacy_map) and a new `services/presupuestacion/procesos_comerciales/api.py` (items_proceso). Same rows as today (the pcp reads do not filter `deleted_at`; the facade keeps that), so pcp behavior is unchanged.
- **S4** Guards: `tests/pcp/test_dependencias.py` allows only facades (`*.api`) from presupuestacion, terceros and productos — `pricing.service`, `notificaciones.service` and the `services.productos` prefix are no longer allowed. A new guard fails if any file in `services/pcp/**` reads or writes a comercial-owned table (`_TABLAS_COMERCIAL` in `tests/arquitectura/test_duenos_tablas.py`).
- **S5** Docs: `docs/arquitectura/README.md` stage 4 done, X-ARQ-002 resolved in `mapa-modulos.md` (plus the stage-2 follow-up "pcp reads comercial tables"), and the pcp docstrings that justified direct table reads are updated.

## Tasks

- [x] T1 S1, S4(imports) — notificaciones/pricing facades + negociacion uses them — inline — commit: 52d2c06
- [x] T2 S2, S4(imports) — productos facade for pcp — inline — commit: 52d2c06
- [x] T3 S3, S4(reads) — comercial read facades, pcp reads removed, read guard — inline — commit: 52d2c06
- [x] T4 S5 — docs — inline — commit: (docs commit, see Log L4)

## Log

- **L1** (user, 2026-11-08): "perfecto entiendo, entonces vamos con la etapa 4". Scope question answered: "1 + 2 + 3: también las lecturas" — (1) notificaciones/pricing internals, (2) productos.service.obtener_producto, (3) the 6 reads of comercial tables, plus the guard in tests/pcp/test_dependencias.py that today allows (1) and (2).
- **L2** Decision: the existing `presupuestos/repository.py::buscar_presupuesto` filters `deleted_at`; the pcp reads did not. To keep behavior identical (no unrequested change), the facade read does not filter it; whether pcp should ignore soft-deleted presupuestos is an open question for the user.
- **L3** Uncommitted frontend fix from earlier (auth/capacidades error screen: `frontend/src/main.tsx`, `features/auth/{AuthContext,AuthContext.test,ErrorCapacidades,ErrorCapacidades.test}.tsx`) travels in the worktree; it is not part of this feature's commits.
- **L4** Evidence: guards RED first (7 forbidden imports, then 6 comercial table reads), GREEN after; affected suites `tests/pcp tests/notificaciones tests/pricing tests/productos tests/presupuestos tests/procesos_comerciales tests/integracion_progress tests/arquitectura`: 527 passed. T1-T3 share one ~340-line code commit (52d2c06, same guard file); T4 docs in the following commit. The stop-hook 'since origin/main' slice count is the accumulated branch, not this feature.
