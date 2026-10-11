# Tasks: Exportación de OC a Progress + calendario de compromisos

> Sigue `design.md` (C1-C6, D1-D11). Donde la propuesta y el diseño difieren (por ejemplo, el estado
> de la OC al exportar), manda el diseño.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1.800 (código + tests) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 → PR3 → PR4 → PR5 → PR6 → PR7 (feature-branch-chain) |
| Chain strategy | feature-branch-chain, tracker `feat/oc-export-progress` → `dev` |

### Suggested Work Units

| Unit | Goal | PR | Test command | Rollback boundary |
|---|---|---|---|---|
| 1 | Esquema 0032 | PR1 | Aplicar/down/reaplicar en test | `0032_*.down.sql` |
| 2 | Filas + escritor + config | PR2 | `pytest tests/oc_export -m "not integration"` | Revert del PR |
| 3 | Service + router de exportación + bloqueo D7 | PR3 | `pytest tests/oc_export tests/oc_entregas` | Revert del PR |
| 4 | Endpoint de compromisos | PR4 | `pytest tests/oc_export -k compromisos` | Revert del PR |
| 5 | Frontend: exportar | PR5 | `npx vitest run`, `npx tsc -b --noEmit` | Revert del PR |
| 6 | Frontend: compromisos | PR6 | `npx vitest run`, `npx vite build` | Revert del PR |
| 7 | Docker + verificación integral + docs | PR7 | Suite completa backend + frontend | Revert del PR |

## Phase 1: Esquema — migración 0032 (bloquea todo lo demás)

- [ ] 1.1 `0032_oc_exportacion_progress.sql`: columnas `exportado_at`, `exportado_por` (FK
      `usuarios`), `archivo_exportado`, `CHECK` todas-o-ninguna, idempotente (D1).
- [ ] 1.2 Índice parcial `ON ordenes_compra (drogueria_id) WHERE exportado_at IS NOT NULL`.
- [ ] 1.3 Vista `v_compromisos_entregas` con `security_invoker = true` (D9).
- [ ] 1.4 `0032_oc_exportacion_progress.down.sql`.
- [ ] 1.5 Aplicar en test, verificar columnas y vista, `down` limpio, reaplicar.
- [ ] 1.6 Actualizar el snapshot `docs/schema/extractor_final.sql`.

## Phase 2: Backend — construcción de filas, escritor y configuración (D4, D5, D8)

- [x] 2.1 `progress_docs_dir` y `oc_export_encoding` en `services/shared/config.py`, con defaults;
      `IntegracionNoConfigurada` (503) en `services/shared/exceptions.py`.
- [x] 2.2 RED → GREEN: `tests/oc_export/test_filas.py` y `oc_export/filas.py`:
  - formato decimal, fechas y enteros;
  - orden renglón → entrega; cantidad 0 omitida;
  - NULL opcionales; cabecera repetida.
- [x] 2.3 RED → GREEN: `tests/oc_export/test_escritor.py` y `oc_export/escritor.py`:
  - `cp1252` con ñ/acentos; coma y comillas en descripciones; emoji → `?`; CRLF;
  - temporal + `os.replace`, sin restos ante falla;
  - no pisa un archivo existente; saneo del nombre.

## Phase 3: Backend — exportación (D2, D3, D6, D7, D10)

- [x] 3.1 `oc_export/models.py`, `repository.py`: lectura de la OC, renglones, entregas, código de
      cliente y CUIT con service client y filtro por `drogueria_id`; `UPDATE` CAS.
- [x] 3.2 RED → GREEN: `service.exportar_orden_compra`:
  - precondiciones D2 acumuladas; D3 con 0, 1 y 2 códigos;
  - compensación D6 con borrado de archivo; auditoría `registrar_cambio`;
  - 503 sin configuración.
- [x] 3.3 `router.py`: `POST /ordenes-compra/{id}/exportar-progress` con `_ROLES_OC`; registrar en
      `main.py`.
- [x] 3.4 D7: bloqueo del `PUT` de planificación si ya fue exportada; bloque `exportacion` en el
      `GET`. Tests en `tests/oc_entregas/`.
- [x] 3.5 Integración: `comercial` exporta a `tmp_path`, `compras` recibe 403, doble exportación →
      409, `PUT` post-exportación → 409.

## Phase 4: Backend — compromisos (D9, D10)

- [x] 4.1 RED → GREEN: `GET /compromisos-entregas?desde&hasta` con `_ROLES_LECTURA`, rango por
      defecto y máximo de 24 meses.
- [x] 4.2 Integración: solo OC exportadas; clasificación `vencida` / `futura`; aislamiento por
      droguería.

## Phase 5: Frontend — exportar (D11)

- [x] 5.1 `lib/api/ocExport.ts` y tipos del bloque `exportacion` en `lib/api/ocEntregas.ts`.
- [x] 5.2 Botón "Exportar a Progress" en `PlanificacionEntregas.tsx`:
  - confirmación;
  - errores de precondición;
  - resultado con nombre de archivo;
  - banner y solo lectura si ya fue exportada.
- [x] 5.3 Tests vitest de los estados del botón.

## Phase 6: Frontend — compromisos (D11)

- [x] 6.1 `lib/api/compromisos.ts`.
- [x] 6.2 `features/compromisos/`: agenda con "Vencidas sin confirmar" + grupos por mes y fecha.
- [x] 6.3 Ruta `_authenticated.compromisos.tsx` + ítem "Compromisos de entrega" en `Sidebar.tsx`
      (visible para roles de lectura).
- [x] 6.4 Tests vitest de agrupación y render.

## Phase 7: Despliegue y verificación integral

- [ ] 7.1 `docker-compose.yml`: bind mount de escritura `C:/SACPro/documentos_ia` y variables (D8).
- [ ] 7.2 Suite backend no-integración + `tests/oc_export` + `tests/oc_entregas` de integración.
- [ ] 7.3 Frontend: `tsc`, `vitest`, `vite build`.
- [ ] 7.4 Generar un CSV de prueba con una OC real de test para pasarle a Sistemas.

## Rollback

Revert de los PRs en orden inverso. Esquema: `0032_*.down.sql`. Los archivos ya escritos en
`C:\SACPro\documentos_ia\oc` no se tocan.
